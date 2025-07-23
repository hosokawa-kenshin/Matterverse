"""
Subscription manager for Matterverse application.
Handles device attribute subscriptions and monitoring.
"""
import asyncio
import json
import re
from typing import List, Dict, Any, Optional, Callable

from logger import get_chip_logger


class SubscriptionManager:
    """Manager for device attribute subscriptions."""
    
    def __init__(self, chip_tool_manager, data_model, database):
        """
        Initialize subscription manager.
        
        Args:
            chip_tool_manager: ChipTool manager instance
            data_model: Data model dictionary instance  
            database: Database manager instance
        """
        self.chip_tool = chip_tool_manager
        self.data_model = data_model
        self.database = database
        self.logger = get_chip_logger()
        
        self._subscription_tasks = []
        self._subscription_callback: Optional[Callable] = None
    
    def set_subscription_callback(self, callback: Callable):
        """Set callback for subscription updates."""
        self._subscription_callback = callback
    
    async def subscribe_all_devices(self):
        """Subscribe to all devices in database."""
        self.logger.info("Subscribing to all devices...")
        
        devices = self.database.get_all_devices()
        if not devices:
            self.logger.warning("No devices found in database")
            return
        
        await self.subscribe_devices(devices)
    
    async def subscribe_device_by_node_id(self, node_id: int):
        """
        Subscribe to all endpoints for a specific node ID.
        
        Args:
            node_id: Node ID to subscribe to
        """
        devices = self.database.get_devices_by_node_id(node_id)
        if not devices:
            self.logger.warning(f"No devices found for NodeID: {node_id}")
            return
        
        await self.subscribe_devices(devices)
    
    async def subscribe_devices(self, devices: List[Dict[str, Any]]):
        """
        Subscribe to multiple devices.
        
        Args:
            devices: List of device dictionaries
        """
        for device in devices:
            task = asyncio.create_task(self._subscribe_device(device))
            self._subscription_tasks.append(task)
        
        # Wait for all subscriptions to complete
        if self._subscription_tasks:
            await asyncio.gather(*self._subscription_tasks, return_exceptions=True)
    
    async def _subscribe_device(self, device: Dict[str, Any]):
        """
        Subscribe to all attributes of a single device.
        
        Args:
            device: Device dictionary
        """
        node_id = device.get("NodeID")
        endpoint = device.get("Endpoint")
        device_type = device.get("DeviceType")
        
        if not all([node_id is not None, endpoint is not None, device_type is not None]):
            self.logger.error(f"Invalid device data: {device}")
            return
        
        device_type_hex = f"0x{int(device_type):04x}"
        clusters = self.data_model.get_clusters_by_device_type(device_type_hex)
        
        self.logger.info(f"Subscribing to device NodeID: {node_id}, Endpoint: {endpoint}, DeviceType: {device_type_hex}")
        
        for cluster_name in clusters:
            await self._subscribe_cluster_attributes(node_id, endpoint, cluster_name)
        
        self.logger.info(f"Completed subscriptions for NodeID: {node_id}, Endpoint: {endpoint}")
    
    async def _subscribe_cluster_attributes(self, node_id: int, endpoint: int, cluster_name: str):
        """
        Subscribe to all attributes in a cluster.
        
        Args:
            node_id: Node ID
            endpoint: Endpoint ID
            cluster_name: Cluster name
        """
        cluster_info = self.data_model.get_cluster_by_name(cluster_name)
        if not cluster_info:
            self.logger.warning(f"Cluster info not found for: {cluster_name}")
            return
        
        attributes = cluster_info.get("attributes", [])
        if not attributes:
            self.logger.warning(f"No attributes found for cluster: {cluster_name}")
            return
        
        for attribute in attributes:
            await self._subscribe_attribute(node_id, endpoint, cluster_name, attribute)
    
    async def _subscribe_attribute(self, node_id: int, endpoint: int, 
                                 cluster_name: str, attribute: Dict[str, Any]):
        """
        Subscribe to a specific attribute.
        
        Args:
            node_id: Node ID
            endpoint: Endpoint ID
            cluster_name: Cluster name
            attribute: Attribute dictionary
        """
        attribute_name = attribute.get("name")
        if not attribute_name:
            return
        
        # Convert attribute name to chip-tool format
        attribute_name_formatted = re.sub(r'(?<!^)(?<![A-Z])(?=[A-Z])', '-', attribute_name).lower()
        
        # Convert cluster name to chip-tool format
        cluster_name_formatted = cluster_name.lower().replace("/", "").replace(" ", "")
        
        # Create subscription command
        command = f"{cluster_name_formatted} subscribe {attribute_name_formatted} 1 100 {node_id} {endpoint}"
        
        self.logger.info(f"Subscribing to NodeID: {node_id}, Endpoint: {endpoint}, "
                        f"Cluster: {cluster_name_formatted}, Attribute: {attribute_name_formatted}")
        
        try:
            # Execute subscription command
            await self.chip_tool.execute_command(command)
            
            # Wait for subscription confirmation
            timeout_seconds = 5
            confirmed = await self._wait_for_subscription_confirmation(
                node_id, endpoint, cluster_name, attribute, timeout_seconds
            )
            
            if confirmed:
                self.logger.info(f"Subscription confirmed for NodeID: {node_id}, Endpoint: {endpoint}, "
                               f"Cluster: {cluster_name_formatted}, Attribute: {attribute_name_formatted}")
            else:
                self.logger.warning(f"Subscription timeout for NodeID: {node_id}, Endpoint: {endpoint}, "
                                  f"Cluster: {cluster_name_formatted}, Attribute: {attribute_name_formatted}")
            
            # Small delay between subscriptions
            await asyncio.sleep(0.1)
            
        except Exception as e:
            self.logger.error(f"Error subscribing to attribute {attribute_name}: {e}")
    
    async def _wait_for_subscription_confirmation(self, node_id: int, endpoint: int,
                                                cluster_name: str, attribute: Dict[str, Any],
                                                timeout_seconds: int = 5) -> bool:
        """
        Wait for subscription confirmation.
        
        Args:
            node_id: Node ID
            endpoint: Endpoint ID
            cluster_name: Cluster name
            attribute: Attribute dictionary
            timeout_seconds: Timeout in seconds
            
        Returns:
            True if confirmed, False if timeout
        """
        cluster_info = self.data_model.get_cluster_by_name(cluster_name)
        if not cluster_info:
            return False
        
        expected_cluster_id = cluster_info.get("id")
        expected_attribute_code = attribute.get("code")
        
        if not expected_cluster_id or not expected_attribute_code:
            return False
        
        start_time = asyncio.get_event_loop().time()
        
        while (asyncio.get_event_loop().time() - start_time) < timeout_seconds:
            try:
                # Check for response from chip tool
                json_str = await asyncio.wait_for(
                    self.chip_tool._response_queue.get(), 
                    timeout=1.0
                )
                
                json_data = json.loads(json_str)
                
                # Check if this is a ReportDataMessage
                if ("ReportDataMessage" not in json_data or 
                    "AttributeReportIBs" not in json_data["ReportDataMessage"]):
                    continue
                
                # Extract attribute path information
                report_data = json_data["ReportDataMessage"]
                attr_reports = report_data.get("AttributeReportIBs", [])
                
                if not attr_reports:
                    continue
                
                attr_report = attr_reports[0].get("AttributeReportIB", {})
                attr_data = attr_report.get("AttributeDataIB", {})
                attr_path = attr_data.get("AttributePathIB", {})
                
                response_node_id = attr_path.get("NodeID")
                response_endpoint = attr_path.get("Endpoint")
                response_cluster = attr_path.get("Cluster")
                response_attribute = attr_path.get("Attribute")
                
                # Format for comparison
                response_cluster_formatted = f"0x{int(response_cluster):04x}"
                response_attribute_formatted = f"0x{int(response_attribute):04x}"
                
                # Check if this matches our subscription
                if (node_id == response_node_id and 
                    endpoint == response_endpoint and
                    expected_cluster_id == response_cluster_formatted and
                    expected_attribute_code == response_attribute_formatted):
                    
                    # Notify callback if set
                    if self._subscription_callback:
                        await self._subscription_callback(json_str)
                    
                    return True
                
            except asyncio.TimeoutError:
                continue
            except Exception as e:
                self.logger.error(f"Error waiting for subscription confirmation: {e}")
                continue
        
        return False
    
    async def stop_all_subscriptions(self):
        """Stop all active subscriptions."""
        # Cancel all subscription tasks
        for task in self._subscription_tasks:
            if not task.done():
                task.cancel()
        
        # Wait for tasks to complete
        if self._subscription_tasks:
            await asyncio.gather(*self._subscription_tasks, return_exceptions=True)
        
        self._subscription_tasks.clear()
        self.logger.info("All subscriptions stopped")
    
    async def resubscribe_device(self, node_id: int, endpoint: int):
        """
        Resubscribe to a specific device.
        
        Args:
            node_id: Node ID
            endpoint: Endpoint ID
        """
        device = self.database.get_device_by_node_id_endpoint(node_id, endpoint)
        if device:
            await self._subscribe_device(device)
        else:
            self.logger.error(f"Device not found: NodeID={node_id}, Endpoint={endpoint}")
    
    async def subscribe_new_device(self, device_info: Dict[str, Any]):
        """
        Subscribe to a newly registered device.
        
        Args:
            device_info: Device information dictionary
        """
        self.logger.info(f"Subscribing to new device: {device_info}")
        await self._subscribe_device(device_info)
