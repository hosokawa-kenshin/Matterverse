"""
Device manager for Matterverse application.
Handles device registration, management, and operations.
"""
import hashlib
import re
from typing import Dict, Any, List, Optional

from logger import get_device_logger


class DeviceManager:
    """Manager for device registration and operations."""

    def __init__(self, chip_tool_manager, database, data_model):
        """
        Initialize device manager.

        Args:
            chip_tool_manager: ChipTool manager instance
            database: Database manager instance
            data_model: Data model dictionary instance
        """
        self.chip_tool = chip_tool_manager
        self.database = database
        self.data_model = data_model
        self.logger = get_device_logger()

    def generate_topic_id(self, node_id: int, unique_id: str, endpoint: int) -> str:
        """
        Generate topic ID for device.

        Args:
            node_id: Node ID
            unique_id: Device unique ID
            endpoint: Endpoint ID

        Returns:
            Generated topic ID
        """
        combined = f"{node_id}-{endpoint}-{unique_id}"
        hash_value = hashlib.sha256(combined.encode()).hexdigest()
        return hash_value

    async def register_new_device(self) -> bool:
        """
        Register a new device to the database.

        Returns:
            True if successful, False otherwise
        """
        try:
            self.logger.info("Starting device registration...")

            # Get next available node ID
            node_id = self.database.get_new_node_id()

            # Get basic device information
            unique_id = await self._get_device_basic_info(node_id, "unique-id")
            if not unique_id:
                self.logger.error("Failed to get device unique ID")
                return False

            vendor_name = await self._get_device_basic_info(node_id, "vendor-name")
            if not vendor_name:
                vendor_name = "Unknown"

            product_name = await self._get_device_basic_info(node_id, "product-name")
            if not product_name:
                product_name = "Device"

            # Clean names for topic generation
            vendor_clean = re.sub(r'[ -]', '', vendor_name)
            product_clean = re.sub(r'[ -]', '', product_name)
            device_name = f"{vendor_clean}_{product_clean}"

            # Register unique ID
            if not self.database.insert_unique_id(node_id, device_name, unique_id):
                self.logger.error("Failed to insert unique ID to database")
                return False

            # Get endpoint list
            endpoints = await self._get_device_endpoints(node_id)
            if not endpoints:
                self.logger.error("Failed to get device endpoints")
                return False

            # Register each endpoint
            for endpoint in endpoints:
                topic_id = self.generate_topic_id(node_id, unique_id, endpoint)
                topic_id = f"{device_name}_{topic_id}"

                # Get device types for this endpoint
                device_types = await self._get_endpoint_device_types(node_id, endpoint)
                if device_types:
                    # Use first device type
                    device_type = int(device_types.get("0x0", 0))

                    if not self.database.insert_device(node_id, endpoint, device_type, topic_id):
                        self.logger.error(f"Failed to insert device: NodeID={node_id}, Endpoint={endpoint}")
                        continue

                    self.logger.info(f"Registered device: NodeID={node_id}, Endpoint={endpoint}, "
                                   f"DeviceType=0x{device_type:04x}, TopicID={topic_id}")
                else:
                    self.logger.warning(f"No device types found for endpoint {endpoint}")

            self.logger.info(f"Device registration completed for NodeID: {node_id}")
            return True

        except Exception as e:
            self.logger.error(f"Error during device registration: {e}")
            return False

    async def _get_device_basic_info(self, node_id: int, attribute: str) -> Optional[str]:
        """
        Get basic information attribute from device.

        Args:
            node_id: Node ID
            attribute: Attribute name (e.g., "unique-id", "vendor-name", "product-name")

        Returns:
            Attribute value or None
        """
        try:
            value = await self.chip_tool.get_basic_info(node_id, attribute)
            if value:
                self.logger.info(f"Got {attribute} for NodeID {node_id}: {value}")
                return value
            else:
                self.logger.warning(f"Failed to get {attribute} for NodeID {node_id}")
                return None
        except Exception as e:
            self.logger.error(f"Error getting {attribute} for NodeID {node_id}: {e}")
            return None

    async def _get_device_endpoints(self, node_id: int) -> List[int]:
        """
        Get endpoint list from device.

        Args:
            node_id: Node ID

        Returns:
            List of endpoint IDs
        """
        try:
            endpoints = await self.chip_tool.get_endpoint_list(node_id)
            if endpoints:
                self.logger.info(f"Got endpoints for NodeID {node_id}: {endpoints}")
                return endpoints
            else:
                self.logger.warning(f"No endpoints found for NodeID {node_id}")
                return []
        except Exception as e:
            self.logger.error(f"Error getting endpoints for NodeID {node_id}: {e}")
            return []

    async def _get_endpoint_device_types(self, node_id: int, endpoint: int) -> Dict[str, Any]:
        """
        Get device types for specific endpoint.

        Args:
            node_id: Node ID
            endpoint: Endpoint ID

        Returns:
            Device types dictionary
        """
        try:
            device_types = await self.chip_tool.get_device_types(node_id, endpoint)
            if device_types:
                self.logger.info(f"Got device types for NodeID {node_id}, Endpoint {endpoint}: {device_types}")
                return device_types
            else:
                self.logger.warning(f"No device types found for NodeID {node_id}, Endpoint {endpoint}")
                return {}
        except Exception as e:
            self.logger.error(f"Error getting device types for NodeID {node_id}, Endpoint {endpoint}: {e}")
            return {}

    def get_all_devices(self) -> List[Dict[str, Any]]:
        """
        Get all devices from database.

        Returns:
            List of device dictionaries
        """
        return self.database.get_all_devices()

    def get_device_by_node_id(self, node_id: int) -> List[Dict[str, Any]]:
        """
        Get all devices for a specific node ID.

        Args:
            node_id: Node ID

        Returns:
            List of device dictionaries
        """
        return self.database.get_devices_by_node_id(node_id)

    def get_device_by_topic_id(self, topic_id: str) -> Optional[Dict[str, Any]]:
        """
        Get device by topic ID.

        Args:
            topic_id: Topic ID

        Returns:
            Device dictionary or None
        """
        return self.database.get_device_by_topic_id(topic_id)

    def get_device_by_node_id_endpoint(self, node_id: int, endpoint: int) -> Optional[Dict[str, Any]]:
        """
        Get device by node ID and endpoint.

        Args:
            node_id: Node ID
            endpoint: Endpoint ID

        Returns:
            Device dictionary or None
        """
        return self.database.get_device_by_node_id_endpoint(node_id, endpoint)

    def delete_device(self, node_id: int, endpoint: int) -> bool:
        """
        Delete device from database.

        Args:
            node_id: Node ID
            endpoint: Endpoint ID

        Returns:
            True if successful, False otherwise
        """
        success = self.database.delete_device(node_id, endpoint)
        if success:
            self.logger.info(f"Deleted device: NodeID={node_id}, Endpoint={endpoint}")
        else:
            self.logger.error(f"Failed to delete device: NodeID={node_id}, Endpoint={endpoint}")
        return success

    def get_device_clusters(self, device: Dict[str, Any]) -> List[str]:
        """
        Get cluster names for a device.

        Args:
            device: Device dictionary

        Returns:
            List of cluster names
        """
        device_type = device.get("DeviceType")
        if device_type is None:
            return []

        device_type_hex = f"0x{int(device_type):04x}"
        return self.data_model.get_clusters_by_device_type(device_type_hex)

    def get_device_attributes(self, device: Dict[str, Any], cluster_name: str) -> List[Dict[str, Any]]:
        """
        Get attributes for a device cluster.

        Args:
            device: Device dictionary
            cluster_name: Cluster name

        Returns:
            List of attribute dictionaries
        """
        clusters = self.get_device_clusters(device)
        if cluster_name not in clusters:
            return []

        return self.data_model.get_attributes_by_cluster_name(cluster_name)

    async def send_command_to_device(self, device: Dict[str, Any],
                                   cluster_name: str, command: str, *args) -> bool:
        """
        Send command to device.

        Args:
            device: Device dictionary
            cluster_name: Cluster name
            command: Command name
            *args: Command arguments

        Returns:
            True if successful, False otherwise
        """
        node_id = device.get("NodeID")
        endpoint = device.get("Endpoint")

        if node_id is None or endpoint is None:
            self.logger.error("Invalid device data for command")
            return False

        # Format cluster name for chip-tool
        cluster_formatted = cluster_name.lower().replace("/", "").replace(" ", "")

        # Build command
        chip_command = f"{cluster_formatted} {command}"
        if args:
            chip_command += " " + " ".join(str(arg) for arg in args)
        chip_command += f" {node_id} {endpoint}"

        try:
            response = await self.chip_tool.execute_command(chip_command)
            self.logger.info(f"Command sent to device: {chip_command}")
            return True
        except Exception as e:
            self.logger.error(f"Error sending command to device: {e}")
            return False

    async def read_device_attribute(self, device: Dict[str, Any],
                                  cluster_name: str, attribute_name: str) -> Optional[Any]:
        """
        Read attribute from device.

        Args:
            device: Device dictionary
            cluster_name: Cluster name
            attribute_name: Attribute name

        Returns:
            Attribute value or None
        """
        node_id = device.get("NodeID")
        endpoint = device.get("Endpoint")

        if node_id is None or endpoint is None:
            self.logger.error("Invalid device data for attribute read")
            return None

        # Format names for chip-tool
        cluster_formatted = cluster_name.lower().replace("/", "").replace(" ", "")
        attribute_formatted = re.sub(r'(?<!^)(?<![A-Z])(?=[A-Z])', '-', attribute_name).lower()

        # Build command
        chip_command = f"{cluster_formatted} read {attribute_formatted} {node_id} {endpoint}"

        try:
            response = await self.chip_tool.execute_command(chip_command)
            # TODO: Parse response to extract attribute value
            self.logger.info(f"Read attribute from device: {chip_command}")
            return response
        except Exception as e:
            self.logger.error(f"Error reading attribute from device: {e}")
            return None

    async def write_device_attribute(self, device: Dict[str, Any],
                                   cluster_name: str, attribute_name: str, value: Any) -> bool:
        """
        Write attribute to device.

        Args:
            device: Device dictionary
            cluster_name: Cluster name
            attribute_name: Attribute name
            value: Value to write

        Returns:
            True if successful, False otherwise
        """
        node_id = device.get("NodeID")
        endpoint = device.get("Endpoint")

        if node_id is None or endpoint is None:
            self.logger.error("Invalid device data for attribute write")
            return False

        # Format names for chip-tool
        cluster_formatted = cluster_name.lower().replace("/", "").replace(" ", "")
        attribute_formatted = re.sub(r'(?<!^)(?<![A-Z])(?=[A-Z])', '-', attribute_name).lower()

        # Build command
        chip_command = f"{cluster_formatted} write {attribute_formatted} {value} {node_id} {endpoint}"

        try:
            response = await self.chip_tool.execute_command(chip_command)
            self.logger.info(f"Wrote attribute to device: {chip_command}")
            return True
        except Exception as e:
            self.logger.error(f"Error writing attribute to device: {e}")
            return False
