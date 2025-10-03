"""
Polling-based subscription manager for Matterverse application.
Handles device attribute polling and monitoring with chip-tool read commands.
"""
import asyncio
import json
import re
from datetime import datetime
from typing import List, Dict, Any, Optional, Callable, Tuple
from dataclasses import dataclass

from logger import get_chip_logger


@dataclass
class PollingConfig:
    """Configuration for polling subscription manager."""
    polling_interval: int = 5      # 全属性統一ポーリング間隔（秒）
    max_concurrent_devices: int = 5 # 最大並行デバイス数
    command_timeout: int = 10       # コマンドタイムアウト（秒）
    device_error_stop: bool = True  # エラー時デバイス停止
    enable_error_logging: bool = True # エラーログ記録有効
    auto_discovery_interval: int = 300  # 新デバイス自動検出間隔（秒、0で無効）


class PollingState:
    """Memory-based state management for polling operations."""

    def __init__(self):
        self.device_locks: Dict[Tuple[int, int], asyncio.Lock] = {}  # デバイス単位ロック
        self.polling_enabled: Dict[Tuple[int, int], bool] = {}       # デバイス別有効状態
        self.error_counts: Dict[Tuple[int, int], int] = {}           # デバイス別エラー回数
        self.last_poll_time: Dict[str, datetime] = {}                # 属性別最終ポーリング時刻

    def get_device_lock(self, node_id: int, endpoint: int) -> asyncio.Lock:
        """Get or create lock for device (NodeID + Endpoint)."""
        device_key = (node_id, endpoint)
        if device_key not in self.device_locks:
            self.device_locks[device_key] = asyncio.Lock()
        return self.device_locks[device_key]

    def is_device_enabled(self, node_id: int, endpoint: int) -> bool:
        """Check if polling is enabled for device."""
        device_key = (node_id, endpoint)
        return self.polling_enabled.get(device_key, True)

    def disable_device(self, node_id: int, endpoint: int):
        """Disable polling for device."""
        device_key = (node_id, endpoint)
        self.polling_enabled[device_key] = False

    def enable_device(self, node_id: int, endpoint: int):
        """Enable polling for device."""
        device_key = (node_id, endpoint)
        self.polling_enabled[device_key] = True
        self.error_counts[device_key] = 0

    def increment_error_count(self, node_id: int, endpoint: int) -> int:
        """Increment error count for device and return new count."""
        device_key = (node_id, endpoint)
        self.error_counts[device_key] = self.error_counts.get(device_key, 0) + 1
        return self.error_counts[device_key]


class PollingSubscriptionManager:
    """Manager for polling-based device attribute monitoring."""

    def __init__(self, chip_tool_manager, data_model, database, config: Optional[PollingConfig] = None):
        """
        Initialize polling subscription manager.

        Args:
            chip_tool_manager: ProcessBasedChipTool manager instance
            data_model: Data model dictionary instance
            database: Database manager instance
            config: Polling configuration
        """
        self.chip_tool = chip_tool_manager
        self.data_model = data_model
        self.database = database
        self.config = config or PollingConfig()
        self.logger = get_chip_logger()

        self.state = PollingState()
        self._polling_tasks: List[asyncio.Task] = []
        self._notification_callback: Optional[Callable] = None
        self._running = False
        self._semaphore = asyncio.Semaphore(self.config.max_concurrent_devices)

        # Auto-discovery task
        self._discovery_task: Optional[asyncio.Task] = None

        # Command execution control
        self._command_in_progress = False
        self._paused_for_command = False
        self._command_lock = asyncio.Lock()

    def set_notification_callback(self, callback: Callable):
        """Set callback for value change notifications."""
        self._notification_callback = callback

    async def pause_polling_for_command(self):
        """Pause all polling operations for command execution."""
        async with self._command_lock:
            if not self._running:
                return

            self.logger.info("Pausing polling for command execution...")
            self._paused_for_command = True
            self._command_in_progress = True

    async def resume_polling_after_command(self):
        """Resume polling operations after command execution."""
        async with self._command_lock:
            if not self._running:
                return

            self.logger.info("Resuming polling after command execution...")
            self._command_in_progress = False
            self._paused_for_command = False

    def is_polling_paused(self) -> bool:
        """Check if polling is currently paused for command execution."""
        return self._paused_for_command

    def is_command_in_progress(self) -> bool:
        """Check if a command is currently being executed."""
        return self._command_in_progress

    async def start_polling_all_devices(self):
        """Start polling for all devices in database."""
        if self._running:
            self.logger.warning("Polling already running")
            return

        self.logger.info("Starting polling for all devices...")
        self._running = True

        # Get all unique devices (NodeID + Endpoint combinations) from Attribute table
        devices = self._get_unique_devices()
        if not devices:
            self.logger.warning("No devices found in Attribute table")
            return

        # Start polling task for each device
        for device in devices:
            node_id = device["NodeID"]
            endpoint = device["Endpoint"]

            if not self._is_device_already_polling(node_id, endpoint):
                task = asyncio.create_task(
                    self._device_polling_loop(node_id, endpoint)
                )
                self._polling_tasks.append(task)

        self.logger.info(f"Started polling for {len(devices)} devices")

        # Start auto-discovery if enabled
        if self.config.auto_discovery_interval > 0:
            self._discovery_task = asyncio.create_task(self._auto_discovery_loop())
            self.logger.info(f"Started auto-discovery with {self.config.auto_discovery_interval}s interval")

    async def add_new_device_polling(self, node_id: int, endpoint: int):
        """Add polling for a new device that was added during runtime."""
        if not self._running:
            self.logger.warning("Polling is not running. Cannot add new device.")
            return False

        if self._is_device_already_polling(node_id, endpoint):
            self.logger.info(f"Device NodeID={node_id}, Endpoint={endpoint} is already being polled")
            return True

        # Check if device has attributes in database
        attributes = self._get_device_attributes(node_id, endpoint)
        if not attributes:
            self.logger.warning(f"No attributes found for new device NodeID={node_id}, Endpoint={endpoint}")
            return False

        self.logger.info(f"Adding polling for new device NodeID={node_id}, Endpoint={endpoint}")

        # Enable device and start polling task
        self.state.enable_device(node_id, endpoint)

        task = asyncio.create_task(
            self._device_polling_loop(node_id, endpoint)
        )
        self._polling_tasks.append(task)

        return True

    async def rescan_and_add_new_devices(self):
        """Rescan Attribute table and add polling for any new devices."""
        if not self._running:
            self.logger.warning("Polling is not running. Cannot rescan for new devices.")
            return

        self.logger.info("Rescanning for new devices...")

        # Get current devices from database
        current_devices = self._get_unique_devices()
        added_count = 0

        for device in current_devices:
            node_id = device["NodeID"]
            endpoint = device["Endpoint"]

            if not self._is_device_already_polling(node_id, endpoint):
                success = await self.add_new_device_polling(node_id, endpoint)
                if success:
                    added_count += 1

        self.logger.info(f"Rescan completed. Added polling for {added_count} new devices")
        return added_count

    def _is_device_already_polling(self, node_id: int, endpoint: int) -> bool:
        """Check if a device is already being polled."""
        # Check if device has an active polling task
        for task in self._polling_tasks:
            if task.done():
                continue
            # Check task name or state to determine if it's for this device
            # Since we can't easily get task parameters, we'll check the state
            device_key = (node_id, endpoint)
            if device_key in self.state.device_locks:
                return True
        return False

    async def _auto_discovery_loop(self):
        """Automatic discovery loop for new devices."""
        self.logger.info("Starting auto-discovery loop")

        while self._running:
            try:
                await asyncio.sleep(self.config.auto_discovery_interval)

                if not self._running:
                    break

                self.logger.debug("Running auto-discovery scan...")
                added_count = await self.rescan_and_add_new_devices()

                if added_count > 0:
                    self.logger.info(f"Auto-discovery: Added {added_count} new devices")

            except asyncio.CancelledError:
                self.logger.info("Auto-discovery cancelled")
                break
            except Exception as e:
                self.logger.error(f"Error in auto-discovery loop: {e}")
                # Continue the loop even if there's an error

        self.logger.info("Auto-discovery loop ended")

    async def stop_polling(self):
        """Stop all polling operations."""
        self.logger.info("Stopping polling...")
        self._running = False

        # Stop auto-discovery
        if self._discovery_task and not self._discovery_task.done():
            self._discovery_task.cancel()
            try:
                await self._discovery_task
            except asyncio.CancelledError:
                pass

        # Cancel all polling tasks
        for task in self._polling_tasks:
            if not task.done():
                task.cancel()

        # Wait for tasks to complete
        if self._polling_tasks:
            await asyncio.gather(*self._polling_tasks, return_exceptions=True)

        self._polling_tasks.clear()
        self.logger.info("All polling stopped")

    async def restart_device_polling(self, node_id: int, endpoint: int):
        """Restart polling for a specific device."""
        self.logger.info(f"Restarting polling for device NodeID={node_id}, Endpoint={endpoint}")

        # Enable device and start new polling task
        self.state.enable_device(node_id, endpoint)

        task = asyncio.create_task(
            self._device_polling_loop(node_id, endpoint)
        )
        self._polling_tasks.append(task)

    def _get_unique_devices(self) -> List[Dict[str, Any]]:
        """Get unique device combinations (NodeID + Endpoint) from Attribute table."""
        try:
            all_attributes = self.database.get_all_attributes()

            # Extract unique device combinations
            device_set = set()
            for attr in all_attributes:
                device_key = (attr["NodeID"], attr["Endpoint"])
                device_set.add(device_key)

            # Convert to list of dictionaries
            devices = []
            for node_id, endpoint in device_set:
                devices.append({
                    "NodeID": node_id,
                    "Endpoint": endpoint
                })

            return devices

        except Exception as e:
            self.logger.error(f"Error getting unique devices: {e}")
            return []

    async def _device_polling_loop(self, node_id: int, endpoint: int):
        """Main polling loop for a single device."""
        self.logger.info(f"Starting polling loop for device NodeID={node_id}, Endpoint={endpoint}")

        while self._running and self.state.is_device_enabled(node_id, endpoint):
            try:
                # Check if polling is paused for command execution
                if self._paused_for_command:
                    await asyncio.sleep(0.5)  # Short sleep while paused
                    continue

                async with self._semaphore:  # Limit concurrent devices
                    await self._poll_device_attributes(node_id, endpoint)

                # Wait for next polling interval
                await asyncio.sleep(self.config.polling_interval)

            except asyncio.CancelledError:
                self.logger.info(f"Polling cancelled for device NodeID={node_id}, Endpoint={endpoint}")
                break
            except Exception as e:
                self.logger.error(f"Error in polling loop for device NodeID={node_id}, Endpoint={endpoint}: {e}")

                # Handle device error
                error_count = self.state.increment_error_count(node_id, endpoint)
                if self.config.device_error_stop:
                    self.logger.error(f"Stopping polling for device NodeID={node_id}, Endpoint={endpoint} due to error")
                    self.state.disable_device(node_id, endpoint)
                    break
                else:
                    # Wait before retry
                    await asyncio.sleep(self.config.polling_interval)

        self.logger.info(f"Polling loop ended for device NodeID={node_id}, Endpoint={endpoint}")

    async def _poll_device_attributes(self, node_id: int, endpoint: int):
        """Poll all attributes for a single device sequentially."""
        device_lock = self.state.get_device_lock(node_id, endpoint)

        async with device_lock:  # Ensure sequential execution within device
            # Check if polling is paused for command execution
            if self._paused_for_command:
                return

            # Get all attributes for this device
            attributes = self._get_device_attributes(node_id, endpoint)

            if not attributes:
                self.logger.debug(f"No attributes found for device NodeID={node_id}, Endpoint={endpoint}")
                return

            self.logger.debug(f"Polling {len(attributes)} attributes for device NodeID={node_id}, Endpoint={endpoint}")

            # Poll each attribute sequentially
            for attr in attributes:
                if not self._running or not self.state.is_device_enabled(node_id, endpoint):
                    break

                # Check if polling is paused for command execution
                if self._paused_for_command:
                    break

                try:
                    await self.poll_single_attribute(
                        node_id, endpoint, attr["Cluster"], attr["Attribute"], attr["Value"]
                    )

                    # Small delay between attributes to avoid overwhelming device
                    await asyncio.sleep(0.1)

                except Exception as e:
                    self.logger.error(f"Error polling attribute {attr['Cluster']}.{attr['Attribute']} "
                                    f"for device NodeID={node_id}, Endpoint={endpoint}: {e}")

    def _get_device_attributes(self, node_id: int, endpoint: int) -> List[Dict[str, Any]]:
        """Get all attributes for a specific device."""
        try:
            all_attributes = self.database.get_all_attributes()

            # Filter attributes for this device
            device_attributes = []
            for attr in all_attributes:
                if attr["NodeID"] == node_id and attr["Endpoint"] == endpoint:
                    device_attributes.append(attr)

            return device_attributes

        except Exception as e:
            self.logger.error(f"Error getting device attributes: {e}")
            return []

    async def poll_single_attribute(self, node_id: int, endpoint: int,
                                   cluster_name: str, attribute_name: str, current_value: str):
        """Poll a single attribute and handle value changes."""
        try:
            # Convert attribute name to chip-tool format
            attribute_name_formatted = re.sub(r'(?<!^)(?<![A-Z])(?=[A-Z])', '-', attribute_name).lower()

            # Convert cluster name to chip-tool format
            cluster_name_formatted = cluster_name.lower().replace("/", "").replace(" ", "")

            # Create read command: {cluster} read {attribute} {node_id} {endpoint}
            command = f"{cluster_name_formatted} read {attribute_name_formatted} {node_id} {endpoint}"

            self.logger.debug(f"Executing: {command}")

            # Execute read command
            response = await asyncio.wait_for(
                self.chip_tool.execute_command(command),
                timeout=self.config.command_timeout
            )

            self.logger.warning(f"Response for {command}: {response}")
            if response.status != "success":
                self.logger.error(f"Failed to read attribute {cluster_name}.{attribute_name}: {response.error_message}")
                return

            # Extract value from response
            new_value = self._extract_attribute_value(response.data)
            if new_value is None:
                self.logger.warning(f"Could not extract value from response for {cluster_name}.{attribute_name}")
                return

            # Convert to string for comparison
            new_value_str = str(new_value)

            # Check if value changed
            if current_value != new_value_str:
                self.logger.info(f"Value changed for {cluster_name}.{attribute_name} "
                               f"on NodeID={node_id}, Endpoint={endpoint}: {current_value} -> {new_value_str}")

                # Update database
                await self._update_attribute_value(node_id, endpoint, cluster_name, attribute_name, new_value_str)

                # Send notification
                await self._send_value_change_notification(
                    node_id, endpoint, cluster_name, attribute_name, new_value
                )

            # Update last poll time
            attr_key = f"{node_id}.{endpoint}.{cluster_name}.{attribute_name}"
            self.state.last_poll_time[attr_key] = datetime.now()

        except asyncio.TimeoutError:
            self.logger.error(f"Timeout reading attribute {cluster_name}.{attribute_name} "
                            f"for NodeID={node_id}, Endpoint={endpoint}")
            raise
        except Exception as e:
            self.logger.error(f"Error polling attribute {cluster_name}.{attribute_name}: {e}")
            raise

    def _extract_attribute_value(self, response_data: Dict[str, Any]) -> Any:
        """Extract attribute value from chip-tool response."""
        try:
            if not response_data:
                return None

            # For ProcessBasedChipToolManager formatted responses
            if "value" in response_data:
                return response_data["value"]

            # For raw ReportDataMessage responses
            if "ReportDataMessage" in response_data:
                report_data = response_data["ReportDataMessage"]
                attr_reports = report_data.get("AttributeReportIBs", [])

                if attr_reports:
                    attr_report = attr_reports[0].get("AttributeReportIB", {})
                    attr_data = attr_report.get("AttributeDataIB", {})
                    return attr_data.get("Data")

            return None

        except Exception as e:
            self.logger.error(f"Error extracting attribute value: {e}")
            return None

    async def _update_attribute_value(self, node_id: int, endpoint: int,
                                    cluster_name: str, attribute_name: str, new_value: str):
        """Update attribute value in database."""
        try:
            # Create a mock JSON response for the existing update_attribute method
            mock_response = {
                "ReportDataMessage": {
                    "AttributeReportIBs": [{
                        "AttributeReportIB": {
                            "AttributeDataIB": {
                                "AttributePathIB": {
                                    "NodeID": node_id,
                                    "Endpoint": endpoint,
                                    "Cluster": self._get_cluster_id(cluster_name),
                                    "Attribute": self._get_attribute_id(cluster_name, attribute_name)
                                },
                                "Data": new_value
                            }
                        }
                    }]
                }
            }

            # Use existing database update method
            success = self.database.update_attribute(json.dumps(mock_response))
            if not success:
                self.logger.error(f"Failed to update attribute in database: {cluster_name}.{attribute_name}")

        except Exception as e:
            self.logger.error(f"Error updating attribute value: {e}")

    def _get_cluster_id(self, cluster_name: str) -> int:
        """Get cluster ID from cluster name."""
        try:
            cluster_info = self.data_model.get_cluster_by_name(cluster_name)
            if cluster_info:
                cluster_id_str = cluster_info.get("id", "0x0000")
                # Remove '0x' prefix and convert to int
                return int(cluster_id_str.replace("0x", ""), 16)
            return 0
        except Exception:
            return 0

    def _get_attribute_id(self, cluster_name: str, attribute_name: str) -> int:
        """Get attribute ID from cluster and attribute names."""
        try:
            cluster_info = self.data_model.get_cluster_by_name(cluster_name)
            if cluster_info:
                cluster_id = cluster_info.get("id")
                attribute_code = self.data_model.get_attribute_code_by_name(cluster_id, attribute_name)
                if attribute_code:
                    # Remove '0x' prefix and convert to int
                    return int(attribute_code.replace("0x", ""), 16)
            return 0
        except Exception:
            return 0

    async def _send_value_change_notification(self, node_id: int, endpoint: int,
                                            cluster_name: str, attribute_name: str, value: Any):
        """Send notification for value change."""
        try:
            # Create notification data according to specification
            notification_data = {
                "type": "status_report",
                "device": {
                    "node": node_id,
                    "endpoint": endpoint,
                },
                "data": {
                    "cluster": cluster_name,
                    "attribute": attribute_name,
                    "type": self.data_model.get_attribute_type_by_name(cluster_name, attribute_name),
                    "value": value
                }
            }

            # Call notification callback if set
            if self._notification_callback:
                try:
                    await self._notification_callback(json.dumps(notification_data))
                except Exception as callback_error:
                    self.logger.error(f"Error in notification callback: {callback_error}")
            else:
                self.logger.warning("No notification callback set - notification not sent")

        except Exception as e:
            self.logger.error(f"Error sending value change notification: {e}")

    def get_polling_status(self) -> Dict[str, Any]:
        """Get current polling status."""
        # Clean up completed tasks
        self._cleanup_completed_tasks()

        enabled_devices = sum(1 for enabled in self.state.polling_enabled.values() if enabled)
        disabled_devices = sum(1 for enabled in self.state.polling_enabled.values() if not enabled)

        return {
            "running": self._running,
            "total_devices": len(self.state.polling_enabled),
            "enabled_devices": enabled_devices,
            "disabled_devices": disabled_devices,
            "active_tasks": len([task for task in self._polling_tasks if not task.done()]),
            "completed_tasks": len([task for task in self._polling_tasks if task.done()]),
            "auto_discovery_enabled": self.config.auto_discovery_interval > 0,
            "auto_discovery_running": self._discovery_task and not self._discovery_task.done(),
            "error_counts": dict(self.state.error_counts),
            "config": {
                "polling_interval": self.config.polling_interval,
                "max_concurrent_devices": self.config.max_concurrent_devices,
                "command_timeout": self.config.command_timeout,
                "device_error_stop": self.config.device_error_stop,
                "auto_discovery_interval": self.config.auto_discovery_interval
            }
        }

    def _cleanup_completed_tasks(self):
        """Remove completed tasks from the task list."""
        active_tasks = [task for task in self._polling_tasks if not task.done()]
        completed_count = len(self._polling_tasks) - len(active_tasks)

        if completed_count > 0:
            self.logger.debug(f"Cleaned up {completed_count} completed tasks")
            self._polling_tasks = active_tasks

    async def get_device_status(self, node_id: int, endpoint: int) -> Dict[str, Any]:
        """Get status for a specific device."""
        device_key = (node_id, endpoint)
        attr_key_prefix = f"{node_id}.{endpoint}."

        # Get last poll times for this device
        device_poll_times = {
            key.replace(attr_key_prefix, ""): time
            for key, time in self.state.last_poll_time.items()
            if key.startswith(attr_key_prefix)
        }

        return {
            "node": node_id,
            "endpoint": endpoint,
            "enabled": self.state.is_device_enabled(node_id, endpoint),
            "error_count": self.state.error_counts.get(device_key, 0),
            "last_poll_times": {
                attr: time.isoformat() if time else None
                for attr, time in device_poll_times.items()
            }
        }
