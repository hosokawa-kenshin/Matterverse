"""
API interface for Matterverse application.
Handles REST API endpoints and request processing.
"""
from fastapi import FastAPI, WebSocket, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, Any, List, Optional

from logger import get_api_logger


class CommandRequest(BaseModel):
    """Request model for command execution."""
    command: str
    node: int
    endpoint: int
    cluster: str
    args: Dict[str, Any] = {}


class DeviceRequest(BaseModel):
    """Request model for device operations."""
    node_id: int
    endpoint: Optional[int] = None


class CommissioningRequest(BaseModel):
    """Request model for device commissioning."""
    manual_pairing_code: Optional[str] = None


class CommissioningWindowRequest(BaseModel):
    """Request model for commissioning window."""
    duration: int = 300
    discriminator: int = 3840


class AttributeWriteRequest(BaseModel):
    """Request model for attribute write operations."""
    value: Any


class AttributeRequest(BaseModel):
    """Request model for attribute operations."""
    node_id: int
    endpoint: int
    cluster_name: str
    attribute_name: str
    value: Optional[Any] = None


class DeviceNameRequest(BaseModel):
    """Request model for device name update."""
    name: str


class APIInterface:
    """API interface for REST endpoints."""

    def __init__(self, device_manager, websocket_interface, chip_tool_manager, data_model, mqtt, polling_manager=None):
        """
        Initialize API interface.

        Args:
            device_manager: Device manager instance
            websocket_interface: WebSocket interface instance
            chip_tool_manager: ChipTool manager instance
            data_model: Data model dictionary instance
            mqtt: MQTT interface instance
            polling_manager: Polling subscription manager instance (optional)
        """
        self.device_manager = device_manager
        self.websocket = websocket_interface
        self.chip_tool = chip_tool_manager
        self.database = device_manager.database
        self.data_model = data_model
        self.mqtt = mqtt
        self.polling_manager = polling_manager
        self.logger = get_api_logger()

        self.app = FastAPI(title="Matterverse API", version="1.0.0")
        self._setup_middleware()
        self._setup_routes()

    def set_device_commissioned_callback(self, callback):
        """
        Set callback function to be called when a device is commissioned.

        Args:
            callback: Async function to call after successful device commissioning
        """
        self._device_commissioned_callback = callback

    def _setup_middleware(self):
        """Setup FastAPI middleware."""
        self.app.add_middleware(
            CORSMiddleware,
            allow_origins=["*"],
            allow_credentials=True,
            allow_methods=["*"],
            allow_headers=["*"],
        )

    def _setup_routes(self):
        """Setup API routes."""

        @self.app.get("/")
        async def root():
            """Root endpoint."""
            return {"message": "Matterverse API", "version": "1.0.0"}

        @self.app.get("/health")
        async def health_check():
            """Health check endpoint for Docker and monitoring."""
            try:
                # Check database connection
                db_status = "healthy"
                try:
                    _ = self.device_manager.get_all_devices()
                except Exception:
                    db_status = "unhealthy"

                # Check chip-tool availability
                chip_tool_status = "healthy"
                try:
                    import os
                    chip_tool_path = os.getenv('CHIP_TOOL_PATH', '/opt/chip-tool/chip-tool')
                    if not os.path.exists(chip_tool_path):
                        chip_tool_status = "chip-tool not found"
                except Exception:
                    chip_tool_status = "unknown"

                # Check polling status
                polling_status = {}
                if self.polling_manager:
                    polling_status = {
                        "is_paused": self.polling_manager.is_polling_paused(),
                        "command_in_progress": self.polling_manager.is_command_in_progress()
                    }

                response = {
                    "status": "healthy" if db_status == "healthy" else "unhealthy",
                    "websocket_clients": self.websocket.connected_clients_count,
                    "database": db_status,
                    "chip_tool": chip_tool_status,
                    "version": "1.0.0"
                }

                if polling_status:
                    response["polling"] = polling_status

                return response
            except Exception as e:
                return {
                    "status": "unhealthy",
                    "error": str(e),
                    "version": "1.0.0"
                }

        @self.app.post("/command")
        async def execute_command(request: CommandRequest):
            """
            Execute chip-tool command.

            Args:
                request: Command request

            Returns:
                Command execution result
            """
            try:
                args = ""
                self.logger.info(f"Received command: {request.command}")

                # Pause polling if polling manager is available
                if self.polling_manager:
                    await self.polling_manager.pause_polling_for_command()

                try:
                    cluster_name = request.cluster.lower().replace("/", "").replace(" ", "")
                    if request.args == {}:
                        args = ""
                        command = f'{cluster_name} {request.command} {args} {request.node} {request.endpoint}'
                    else:
                        args = ' '.join([str(v) for v in request.args.values()])
                        command = f'{cluster_name} {request.command} {args} {request.node} {request.endpoint}'
                    response = await self.chip_tool.execute_command(command)

                    # Format response according to API design
                    if response.status == "success" and response.data:
                        formatted_response = self._format_command_response(response)
                        return {
                            "status": "success",
                            "command": request.command,
                            "data": formatted_response
                        }
                    else:
                        return {
                            "status": response.status,
                            "command": request.command,
                            "response": response.to_dict()
                        }

                finally:
                    if self.polling_manager:
                        if request.cluster == "On/Off" and request.command in ["on", "off", "toggle"]:
                          current_value = await self.database.get_value_by_attribute(
                            request.node, request.endpoint, "On/Off", "OnOff"
                          )
                          await self.polling_manager.poll_single_attribute(request.node, request.endpoint, "On/Off", "OnOff", current_value)
                        await self.polling_manager.resume_polling_after_command()

            except Exception as e:
                # Ensure polling is resumed even if there's an error
                if self.polling_manager:
                    await self.polling_manager.resume_polling_after_command()

                self.logger.error(f"Error executing command: {e}")
                await self.websocket.send_error(f"Command execution failed: {str(e)}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.get("/device")
        async def get_devices(
            node: Optional[int] = Query(None, description="Filter by Node ID"),
            endpoint: Optional[int] = Query(None, description="Filter by Endpoint ID"),
            device_type: Optional[str] = Query(None, description="Filter by Device Type"),
            name: Optional[str] = Query(None, description="Filter by Device Name"),
            cluster: Optional[str] = Query(None, description="Filter by Cluster name"),
            attribute: Optional[str] = Query(None, description="Filter by Attribute name"),
            command: Optional[str] = Query(None, description="Filter by Command name")
        ):
            """
            Get devices with optional filtering.

            Query Parameters:
                node: Filter by Node ID
                endpoint: Filter by Endpoint ID
                device_type: Filter by Device Type
                name: Filter by Device Name
                cluster: Filter by Cluster name
                attribute: Filter by Attribute name
                command: Filter by Command name

            Returns:
                Filtered list of devices
            """
            try:
                all_devices = self.device_manager.get_all_devices()

                filtered_devices = self._filter_devices(
                    all_devices, node, endpoint, device_type, name, cluster, attribute, command
                )

                return {"devices": filtered_devices}
            except Exception as e:
                self.logger.error(f"Error getting devices: {e}")
                raise HTTPException(status_code=500, detail=str(e))


        @self.app.post("/device")
        async def commissioning(request: Optional[CommissioningRequest] = None):
            """
            Commissioning endpoint.

            Args:
                request: Optional commissioning request with manual pairing code

            Returns:
                Test commissioning result
            """
            try:
                if request and request.manual_pairing_code:
                   response = await self.device_manager.commissioning_device(request.manual_pairing_code)
                if response:
                    self.mqtt.publish_homie_devices()
                    await self.websocket.broadcast_device_addition(response)
                    return {"status": "success", "devices": response}
                else:
                    return {"status": "error", "detail": "No devices commissioned"}
            except HTTPException:
                raise
            except Exception as e:
                self.logger.error(f"Error in test commissioning: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.post("/demo")
        async def demo_commissioning(request: Optional[CommissioningRequest] = None):
            """
            Demo commissioning endpoint.
            Adds demo device and attribute data to the database.

            Returns:
                Demo commissioning result
            """
            try:
                # Demo data definition
                demo_node_id = 1
                demo_endpoint = 1
                demo_device_type = "Matter Extended Color Light"
                demo_device_name = "Matter Light"
                demo_topic_id = "demo_matter_light"
                demo_unique_id = "demo_unique_id_1"

                # First, delete existing demo device if exists
                existing_device = self.database.get_device_by_node_id_endpoint(demo_node_id, demo_endpoint)
                if existing_device:
                    self.logger.info(f"Deleting existing demo device: NodeID={demo_node_id}, Endpoint={demo_endpoint}")
                    self.database.delete_device(demo_node_id, demo_endpoint)

                # Insert unique ID
                if not self.database.insert_unique_id(demo_node_id, "demo_device", demo_unique_id):
                    self.logger.warning("Failed to insert demo unique ID (may already exist)")

                # Insert demo device
                if not self.database.insert_device(demo_node_id, demo_endpoint, demo_device_type, demo_device_name, demo_topic_id):
                    self.logger.error("Failed to insert demo device")
                    raise HTTPException(status_code=500, detail="Failed to create demo device")

                # Demo clusters and attributes
                demo_clusters = [
                    {
                        "name": "Descriptor",
                        "attributes": [
                            {"name": "ClientList", "type": "array", "value": "[]"},
                            {"name": "DeviceTypeList", "type": "array", "value": "[{'0x0': '266', '0x1': '1'}]"},
                            {"name": "PartsList", "type": "array", "value": "[]"},
                            {"name": "ServerList", "type": "array", "value": "['3', '4', '6', '29']"}
                        ]
                    },
                    {
                        "name": "Groups",
                        "attributes": [
                            {"name": "NameSupport", "type": "NameSupportBitmap", "value": "128"}
                        ]
                    },
                    {
                        "name": "Identify",
                        "attributes": [
                            {"name": "IdentifyTime", "type": "int16u", "value": "0"},
                            {"name": "IdentifyType", "type": "IdentifyTypeEnum", "value": "2"}
                        ]
                    },
                    {
                        "name": "On/Off",
                        "attributes": [
                            {"name": "OnOff", "type": "boolean", "value": "true"}
                        ]
                    }
                ]

                # Insert attributes into database
                for cluster in demo_clusters:
                    cluster_name = cluster["name"]
                    for attr in cluster["attributes"]:
                        attr_name = attr["name"]
                        attr_type = attr["type"]
                        attr_value = attr["value"]

                        # Create attribute entry
                        if self.database.create_attribute_entry(demo_node_id, demo_endpoint, cluster_name, attr_name):
                            # Update the value if creation was successful
                            self.database.update_attribute_value(demo_node_id, demo_endpoint, cluster_name, attr_name, attr_value)
                            self.logger.info(f"Created demo attribute: {cluster_name}.{attr_name} = {attr_value}")
                        else:
                            self.logger.warning(f"Failed to create demo attribute: {cluster_name}.{attr_name}")

                # Return success response with the created device data
                created_device = self.database.get_device_by_node_id_endpoint(demo_node_id, demo_endpoint)
                if not created_device:
                    raise HTTPException(status_code=500, detail="Failed to retrieve created demo device")

                devices = self.database.get_devices_by_node_id(demo_node_id)
                await self.websocket.broadcast_device_addition(devices)
                self.logger.info(f"Sent WebSocket register_report for demo device: NodeID={demo_node_id}, Endpoint={demo_endpoint}")

                return {
                    "status": "success",
                    "devices": devices
                }

            except HTTPException:
                raise
            except Exception as e:
                self.logger.error(f"Error in demo commissioning: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.post("/device/{node_id}/window")
        async def open_commissioning_window(node_id: int, request: CommissioningWindowRequest):
            """
            Open commissioning window for device.

            Args:
                node_id: Node ID
                request: Commissioning window parameters

            Returns:
                Commissioning window result
            """
            try:
                return {
                    "status": "success",
                    "node": node_id,
                    "endpoint": 1,
                    "manual_pairing_code": "56789123456",
                    "duration": request.duration
                }
            except Exception as e:
                self.logger.error(f"Error opening commissioning window: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.delete("/device/{node_id}/{endpoint}")
        async def delete_device(node_id: int, endpoint: int):
            """
            Delete device.

            Args:
                node_id: Node ID
                endpoint: Endpoint ID

            Returns:
                Deletion result
            """
            try:
                success = self.device_manager.delete_device(node_id, endpoint)
                if success:
                    await self.websocket.broadcast_device_deletion(node_id, endpoint)
                    return {"status": "success", "message": "Device deleted successfully"}
                else:
                    raise HTTPException(status_code=400, detail="Device deletion failed")
            except HTTPException:
                raise
            except Exception as e:
                self.logger.error(f"Error deleting device: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.post("/device/{node_id}/{endpoint}/name")
        async def update_device_name(node_id: int, endpoint: int, request: DeviceNameRequest):
            """
            Update device name.

            Args:
                node_id: Node ID
                endpoint: Endpoint ID
                request: Request body with new device name

            Returns:
                Update result
            """
            try:
                # Check if device exists
                device = self.device_manager.get_device_by_node_id_endpoint(node_id, endpoint)
                if not device:
                    raise HTTPException(status_code=404, detail="Device not found")

                # Update device name
                success = self.device_manager.update_device_name(node_id, endpoint, request.name)
                if success:
                    return {
                        "status": "success",
                        "node": node_id,
                        "endpoint": endpoint,
                        "name": request.name
                    }
                else:
                    raise HTTPException(status_code=400, detail="Device name update failed")
            except HTTPException:
                raise
            except Exception as e:
                self.logger.error(f"Error updating device name: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.post("/device/{node_id}/{endpoint}/{cluster_name}/{attribute_name}")
        async def write_attribute_direct(node_id: int, endpoint: int, cluster_name: str, attribute_name: str, request: AttributeWriteRequest):
            """
            Write attribute to device using direct path.

            Args:
                node_id: Node ID
                endpoint: Endpoint ID
                cluster_name: Cluster name
                attribute_name: Attribute name
                request: Request body with value

            Returns:
                Write result
            """
            try:
                device = self.device_manager.get_device_by_node_id_endpoint(node_id, endpoint)
                if not device:
                    raise HTTPException(status_code=404, detail="Device not found")

                success = await self.device_manager.write_device_attribute(
                    device, cluster_name, attribute_name, request.value
                )

                if success:
                    return {
                        "node": node_id,
                        "endpoint": endpoint,
                        "cluster": cluster_name,
                        "attribute": attribute_name,
                        "value": request.value
                    }
                else:
                    raise HTTPException(status_code=400, detail="Attribute write failed")
            except HTTPException:
                raise
            except Exception as e:
                self.logger.error(f"Error writing attribute: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.get("/datamodel/cluster")
        async def get_clusters():
            """
            Get cluster information.

            Returns:
                Cluster information
            """
            try:
                cluster_info = self.data_model.clusters
                return {"clusters": cluster_info}
            except Exception as e:
                self.logger.error(f"Error getting cluster information: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.get("/datamodel/devicetype")
        async def get_device_types():
            """
            Get device type information.

            Returns:
                Device type information
            """
            try:
                device_types = self.data_model.device_types
                return {"device_types": device_types}
            except Exception as e:
                self.logger.error(f"Error getting device types: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.websocket("/ws")
        async def websocket_endpoint(websocket: WebSocket):
            """WebSocket endpoint for real-time communication."""
            await self.websocket.handle_client_connection(websocket)

    def get_app(self) -> FastAPI:
        """Get FastAPI application instance."""
        return self.app

    def _format_command_response(self, response) -> Dict[str, Any]:
        """
        Format chip-tool command response to API standard format.

        Args:
            response: ChipToolResponse object

        Returns:
            Formatted response data
        """
        try:
            if not response.data:
                return {}

            # Extract data from ReportDataMessage format
            if "ReportDataMessage" in response.data:
                report_data = response.data["ReportDataMessage"]
                attr_reports = report_data.get("AttributeReportIBs", [])

                if attr_reports:
                    attr_report = attr_reports[0].get("AttributeReportIB", {})
                    attr_data = attr_report.get("AttributeDataIB", {})
                    attr_path = attr_data.get("AttributePathIB", {})

                    # Map cluster ID to name
                    cluster_id = attr_path.get("Cluster")
                    cluster_name = self._get_cluster_name_by_id(cluster_id)

                    # Map attribute ID to name
                    attribute_id = attr_path.get("Attribute")
                    attribute_name = self._get_attribute_name_by_id(cluster_id, attribute_id)

                    return {
                        "node": attr_path.get("NodeID"),
                        "endpoint": attr_path.get("Endpoint"),
                        "cluster": cluster_name or f"Cluster_{cluster_id}",
                        "attribute": attribute_name or f"Attribute_{attribute_id}",
                        "value": attr_data.get("Data")
                    }

            # If not standard format, return as-is
            return response.data

        except Exception as e:
            self.logger.warning(f"Error formatting command response: {e}")
            return response.data or {}

    def _get_cluster_name_by_id(self, cluster_id: int) -> Optional[str]:
        """Get cluster name by cluster ID."""
        cluster_name = self.data_model.get_cluster_name_by_id(f"0x{int(cluster_id):04x}")
        return cluster_name

    def _get_attribute_name_by_id(self, cluster_id: int, attribute_id: int) -> Optional[str]:
        """Get attribute name by cluster and attribute ID."""
        attribute_name = self.data_model.get_attribute_name_by_code(f"0x{int(cluster_id):04x}", f"0x{int(attribute_id):04x}")
        return attribute_name

    def _filter_devices(self, devices: List[Dict[str, Any]], node: Optional[int],
                       endpoint: Optional[int], device_type: Optional[str], name: Optional[str],
                       cluster: Optional[str], attribute: Optional[str], command: Optional[str]) -> List[Dict[str, Any]]:
        """
        Filter devices based on query parameters.

        Args:
            devices: List of devices to filter
            node: Filter by node ID
            endpoint: Filter by endpoint ID
            device_type: Filter by device type
            name: Filter by device name
            cluster: Filter by cluster name
            attribute: Filter by attribute name
            command: Filter by command name

        Returns:
            Filtered list of devices
        """
        filtered_devices = []

        for device in devices:
            # Apply node filter
            if node is not None and device.get("node") != node:
                continue

            # Apply endpoint filter
            if endpoint is not None and device.get("endpoint") != endpoint:
                continue

            # Apply device_type filter
            if device_type is not None and device_type not in device.get("device_type", ""):
                continue

            # Apply name filter
            if name is not None and name not in device.get("name", ""):
                continue

            # Create a copy of the device to potentially modify clusters
            filtered_device = device.copy()

            # Apply cluster, attribute, and command filters
            if cluster is not None or attribute is not None or command is not None:
                original_clusters = device.get("clusters", [])
                filtered_clusters = []

                for cluster_data in original_clusters:
                    cluster_name = cluster_data.get("name", "")

                    # Apply cluster filter
                    if cluster is not None and cluster_name != cluster:
                        continue

                    # Create a copy of the cluster to potentially modify attributes and commands
                    filtered_cluster = cluster_data.copy()
                    cluster_modified = False

                    # Apply attribute filter
                    if attribute is not None:
                        original_attributes = cluster_data.get("attributes", [])
                        filtered_attributes = []

                        for attr in original_attributes:
                            if attr.get("name") == attribute:
                                filtered_attributes.append(attr)

                        # Update cluster with filtered attributes
                        if filtered_attributes:
                            filtered_cluster["attributes"] = filtered_attributes
                            cluster_modified = True
                        else:
                            # Skip this cluster if no matching attributes found
                            continue

                    # Apply command filter
                    if command is not None:
                        original_commands = cluster_data.get("commands", [])
                        filtered_commands = []

                        for cmd in original_commands:
                            cmd_name = cmd.get("name") if isinstance(cmd, dict) else str(cmd)
                            if cmd_name == command:
                                filtered_commands.append(cmd)

                        # Update cluster with filtered commands
                        if filtered_commands:
                            filtered_cluster["commands"] = filtered_commands
                            cluster_modified = True
                        else:
                            # Skip this cluster if no matching commands found
                            continue

                    # Include cluster if it matches filters or if no specific filters applied
                    if attribute is None and command is None:
                        # No attribute/command filters - include cluster as is
                        filtered_clusters.append(filtered_cluster)
                    elif cluster_modified:
                        # Cluster was modified by attribute/command filters
                        filtered_clusters.append(filtered_cluster)

                # Update device with filtered clusters
                filtered_device["clusters"] = filtered_clusters

                # Only include device if it has matching clusters
                if filtered_clusters:
                    filtered_devices.append(filtered_device)
            else:
                # No cluster/attribute/command filters - include device as is
                filtered_devices.append(filtered_device)

        return filtered_devices
