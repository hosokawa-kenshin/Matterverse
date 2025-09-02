"""
Configuration management for Matterverse application.
"""
import os
from typing import Optional
from dotenv import load_dotenv


class Config:
    """Configuration manager for environment variables and settings."""

    def __init__(self, env_file: Optional[str] = None):
        """
        Initialize configuration manager.

        Args:
            env_file: Path to .env file. If None, uses default .env
        """
        if env_file:
            load_dotenv(env_file)
        else:
            load_dotenv("./config/.env")

    @property
    def chip_tool_path(self) -> str:
        """Get chip-tool executable path."""
        return os.getenv('CHIP_TOOL_PATH', './chip-tool')

    @property
    def commissioning_dir(self) -> str:
        """Get commissioning directory path."""
        return os.getenv('COMMISSIONING_DIR', './commissioning_dir')

    @property
    def mqtt_broker_url(self) -> str:
        """Get MQTT broker URL."""
        return os.getenv('MQTT_BROKER_URL', 'localhost')

    @property
    def mqtt_broker_port(self) -> int:
        """Get MQTT broker port."""
        return int(os.getenv('MQTT_BROKER_PORT', '9001'))

    @property
    def cluster_xml_dir(self) -> str:
        """Get cluster XML directory path."""
        return os.getenv('CLUSTER_XML_DIR', '../sdk/src/app/zap-templates/zcl/data-model/chip/')

    @property
    def device_type_xml_file(self) -> str:
        """Get device type XML file path."""
        return os.getenv('DEVICETYPE_XML_FILE', '../sdk/src/app/zap-templates/zcl/data-model/chip/matter-device-types.xml')

    @property
    def paa_cert_dir_path(self) -> str:
        """Get PAA certificate directory path."""
        return os.getenv('PAA_CERT_DIR_PATH', '../sdk/credentials/paa_root_cert')

    @property
    def database_path(self) -> str:
        """Get SQLite database file path."""
        return os.getenv('DATABASE_PATH', './db/matterverse.db')

    @property
    def log_level(self) -> str:
        """Get log level."""
        return os.getenv('LOG_LEVEL', 'INFO')

    @property
    def enable_colored_logs(self) -> bool:
        """Get whether to enable colored logs."""
        return os.getenv('ENABLE_COLORED_LOGS', 'true').lower() == 'true'

    # Polling configuration
    @property
    def polling_interval(self) -> int:
        """Get polling interval in seconds."""
        return int(os.getenv('POLLING_INTERVAL', '30'))

    @property
    def max_concurrent_devices(self) -> int:
        """Get maximum concurrent devices for polling."""
        return int(os.getenv('MAX_CONCURRENT_DEVICES', '5'))

    @property
    def command_timeout(self) -> int:
        """Get command timeout in seconds."""
        return int(os.getenv('COMMAND_TIMEOUT', '30'))

    @property
    def device_error_stop(self) -> bool:
        """Get whether to stop device polling on error."""
        return os.getenv('DEVICE_ERROR_STOP', 'true').lower() == 'true'

    @property
    def auto_discovery_interval(self) -> int:
        """Get auto-discovery interval in seconds (0 to disable)."""
        return int(os.getenv('AUTO_DISCOVERY_INTERVAL', '300'))

    def get(self, key: str, default=None):
        """Get configuration value by key with fallback to property."""
        # Map common keys to properties
        property_map = {
            'polling_interval': self.polling_interval,
            'max_concurrent_devices': self.max_concurrent_devices,
            'command_timeout': self.command_timeout,
            'device_error_stop': self.device_error_stop,
            'auto_discovery_interval': self.auto_discovery_interval
        }

        return property_map.get(key, default)
