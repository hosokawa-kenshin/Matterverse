"""
Main Matterverse application.
Orchestrates all components and manages application lifecycle.
"""
import asyncio
import signal
import sys
from contextlib import asynccontextmanager
from fastapi import FastAPI

from config import Config
from logger import Logger, get_chip_logger
from database_manager import Database
from data_model_dictionary import DataModelDictionary
from chip_tool_manager import ProcessBasedChipToolManager
from mqtt_interface import MQTTInterface
from websocket_interface import WebSocketInterface
from subscription_manager import SubscriptionManager
from polling_subscription_manager import PollingSubscriptionManager, PollingConfig
from device_manager import DeviceManager
from api_interface import APIInterface


class MatterverseApplication:
    """Main application class for Matterverse."""

    def __init__(self, config_file: str = None):
        """
        Initialize Matterverse application.

        Args:
            config_file: Path to configuration file
        """
        # Load configuration
        self.config = Config(config_file)

        # Setup logging
        Logger.setup(
            level=self.config.log_level,
            enable_colors=self.config.enable_colored_logs
        )
        self.logger = get_chip_logger()

        # Initialize components
        self.database = None
        self.data_model = None
        self.chip_tool = None
        self.mqtt = None
        self.websocket = None
        self.subscription_manager = None
        self.polling_manager = None
        self.device_manager = None
        self.api = None

        # Task management
        self._background_tasks = []
        self._shutdown_event = asyncio.Event()
        self._shutdown_in_progress = False

        # FastAPI app
        self.app = None

    async def initialize(self):
        """Initialize all components."""
        try:
            self.logger.info("Initializing Matterverse application...")

            # Initialize data model
            self.data_model = DataModelDictionary()
            await self._load_data_models()

            # Initialize database
            self.database = Database(self.config.database_path, self.data_model)

            # Initialize chip tool manager
            self.chip_tool = ProcessBasedChipToolManager(
                self.config.chip_tool_path,
                self.config.commissioning_dir,
                self.config.paa_cert_dir_path,
                10,  # max_concurrent_processes
                self.database,
                self.data_model
            )

            # Initialize WebSocket interface
            self.websocket = WebSocketInterface()

            # Initialize MQTT interface
            self.mqtt = MQTTInterface(
                self.config.mqtt_broker_url,
                self.config.mqtt_broker_port
            )
            self.mqtt.set_data_model(self.data_model)
            self.mqtt.set_database(self.database)

            # Initialize polling subscription manager (new)
            polling_config = PollingConfig(
                polling_interval=self.config.get('polling_interval', 30),
                max_concurrent_devices=self.config.get('max_concurrent_devices', 5),
                command_timeout=self.config.get('command_timeout', 30),
                device_error_stop=self.config.get('device_error_stop', True),
                auto_discovery_interval=self.config.get('auto_discovery_interval', 300)
            )
            self.polling_manager = PollingSubscriptionManager(
                self.chip_tool,
                self.data_model,
                self.database,
                polling_config
            )

            # Initialize device manager
            self.device_manager = DeviceManager(
                self.chip_tool,
                self.database,
                self.data_model
            )

            # Initialize API interface
            self.api = APIInterface(
                self.device_manager,
                self.websocket,
                self.chip_tool,
                self.data_model,
                self.mqtt,
                self.polling_manager
            )

            # Setup callbacks
            self._setup_callbacks()

            # Create FastAPI app with lifespan
            self.app = self._create_app()

            self.logger.info("All components initialized successfully")

        except Exception as e:
            self.logger.error(f"Error during initialization: {e}")
            raise

    async def _load_data_models(self):
        """Load data models from XML files."""
        self.logger.info("Loading data models...")

        # Load clusters
        success = self.data_model.parse_clusters_from_directory(self.config.cluster_xml_dir)
        if not success:
            raise RuntimeError("Failed to load cluster data models")

        # Load device types
        success = self.data_model.parse_device_types_from_file(self.config.device_type_xml_file)
        if not success:
            raise RuntimeError("Failed to load device type data models")

        self.logger.info("Data models loaded successfully")

    def _setup_callbacks(self):
        """Setup callbacks between components."""
        # Set chip tool parsed data callback (for direct command results)
        # self.chip_tool.set_parsed_data_callback(self._handle_direct_command_result)

        # Set MQTT command callback
        self.mqtt.set_command_callback(self.chip_tool.execute_command)

        # Set MQTT polling manager for command handling
        self.mqtt.set_polling_manager(self.polling_manager)

        # Set polling notification callback (new)
        self.polling_manager.set_notification_callback(self._handle_polling_notification)

        # Set API device commissioned callback
        self.api.set_device_commissioned_callback(self._handle_device_commissioned)

    async def _handle_direct_command_result(self, json_data: str):
        """
        Handle direct command result from chip tool.
        Called when a command is executed directly via API or MQTT.

        Args:
            json_data: Command result data in JSON format
        """
        # try:
            # self.mqtt.publish_attribute_data(json_data)
            # await self.websocket.send_parsed_data(json_data)
        # except Exception as e:
        #     self.logger.error(f"Error handling direct command result: {e}")

    async def _handle_polling_notification(self, json_data: str):
        """
        Handle polling notification data (new).

        Args:
            json_data: Polling notification data
        """
        try:
            # Forward to MQTT
            self.mqtt.publish_attribute_data(json_data)

            # Broadcast to WebSocket clients
            await self.websocket.send_parsed_data(json_data)

        except Exception as e:
            self.logger.error(f"Error handling polling notification: {e}")

    async def _handle_device_commissioned(self):
        """
        Handle device commissioned event.
        Called when a device is successfully commissioned via API.
        """
        try:
            if self.polling_manager:
                added_count = await self.polling_manager.rescan_and_add_new_devices()
                self.logger.info(f"Added {added_count} new devices to polling after commissioning")
        except Exception as e:
            self.logger.error(f"Error handling device commissioned event: {e}")

    def _create_app(self) -> FastAPI:
        """Create FastAPI application with lifespan management."""

        @asynccontextmanager
        async def lifespan(app: FastAPI):
            """Application lifespan management."""
            # Startup
            await self.startup()
            yield
            # Shutdown
            await self.shutdown()

        app = FastAPI(
            title="Matterverse",
            description="Matter protocol device management server",
            version="1.0.0",
            lifespan=lifespan
        )

        # Mount API routes
        app.mount("", self.api.get_app())

        return app

    async def startup(self):
        """Application startup sequence."""
        try:
            self.logger.info("Starting Matterverse application...")

            # Start chip tool
            await self.chip_tool.start()

            # Connect MQTT
            if not self.mqtt.connect():
                raise RuntimeError("Failed to connect to MQTT broker")

            # Publish Homie devices
            self.mqtt.publish_homie_devices()

            # Start subscriptions (temporarily disabled)
            # subscription_task = asyncio.create_task(
            #     self.subscription_manager.subscribe_all_devices()
            # )
            # self._background_tasks.append(subscription_task)

            # Start polling subscriptions (new approach)
            polling_task = asyncio.create_task(
                self.polling_manager.start_polling_all_devices()
            )
            self._background_tasks.append(polling_task)

            # Setup signal handlers
            self._setup_signal_handlers()

            self.logger.info("Matterverse application started successfully")

        except Exception as e:
            self.logger.error(f"Error during startup: {e}")
            raise

    async def shutdown(self):
        """Application shutdown sequence."""
        if self._shutdown_in_progress:
            self.logger.info("Shutdown already in progress, skipping duplicate shutdown")
            return

        self._shutdown_in_progress = True

        try:
            self.logger.info("Shutting down Matterverse application...")

            # Set shutdown event
            self._shutdown_event.set()

            # Stop subscriptions (legacy)
            if self.subscription_manager:
                try:
                    await self.subscription_manager.stop_all_subscriptions()
                except Exception as e:
                    self.logger.error(f"Error stopping subscriptions: {e}")

            # Stop polling (new)
            if self.polling_manager:
                try:
                    await self.polling_manager.stop_polling()
                except Exception as e:
                    self.logger.error(f"Error stopping polling: {e}")

            # Cancel background tasks
            try:
                for task in self._background_tasks:
                    if not task.done():
                        task.cancel()

                if self._background_tasks:
                    await asyncio.gather(*self._background_tasks, return_exceptions=True)
            except Exception as e:
                self.logger.error(f"Error cancelling background tasks: {e}")

            # Disconnect MQTT
            if self.mqtt:
                try:
                    self.mqtt.disconnect()
                except Exception as e:
                    self.logger.error(f"Error disconnecting MQTT: {e}")

            # Stop chip tool
            if self.chip_tool:
                try:
                    await self.chip_tool.stop()
                except Exception as e:
                    self.logger.error(f"Error stopping chip tool: {e}")

            # Cleanup WebSocket connections
            if self.websocket:
                try:
                    await self.websocket.cleanup()
                except Exception as e:
                    self.logger.error(f"Error cleaning up WebSocket: {e}")

            # Close database
            if self.database:
                try:
                    self.database.close()
                except Exception as e:
                    self.logger.error(f"Error closing database: {e}")

            self.logger.info("Matterverse application shut down successfully")

        except Exception as e:
            import traceback
            self.logger.error(f"Error during shutdown: {e}")
            self.logger.error(f"Shutdown error traceback: {traceback.format_exc()}")

    def _setup_signal_handlers(self):
        """Setup signal handlers for graceful shutdown."""
        def signal_handler(signum, frame):
            if self._shutdown_in_progress:
                self.logger.info(f"Shutdown already in progress, ignoring signal {signum}")
                return

            self.logger.info(f"Received signal {signum}, initiating shutdown...")
            sys.exit(0)
            asyncio.create_task(self.shutdown())

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

    def get_app(self) -> FastAPI:
        """Get FastAPI application instance."""
        return self.app


# Global application instance
app_instance = None


async def create_application() -> FastAPI:
    """
    Create and initialize Matterverse application.

    Returns:
        FastAPI application instance
    """
    global app_instance

    if app_instance is None:
        app_instance = MatterverseApplication()
        await app_instance.initialize()

    return app_instance.get_app()


# For uvicorn
app = None

async def get_app():
    """Get application instance for uvicorn."""
    global app
    if app is None:
        app = await create_application()
    return app


if __name__ == "__main__":
    import uvicorn

    async def main():
        """Main entry point."""
        app = await create_application()
        config = uvicorn.Config(
            app,
            host="0.0.0.0",
            port=8000,
            log_level="info",
            reload=False
        )
        server = uvicorn.Server(config)
        await server.serve()

    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("Application stopped by user")
    except Exception as e:
        print(f"Application error: {e}")
        sys.exit(1)
