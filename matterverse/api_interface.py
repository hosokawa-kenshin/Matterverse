"""
API interface for Matterverse application.
Handles REST API endpoints and request processing.
"""
from fastapi import FastAPI, WebSocket, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, Any, List, Optional

from logger import get_api_logger


class CommandRequest(BaseModel):
    """Request model for command execution."""
    command: str


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


class APIInterface:
    """API interface for REST endpoints."""

    def __init__(self, device_manager, websocket_interface, chip_tool_manager, data_model):
        """
        Initialize API interface.

        Args:
            device_manager: Device manager instance
            websocket_interface: WebSocket interface instance
            chip_tool_manager: ChipTool manager instance
            data_model: Data model dictionary instance
        """
        self.device_manager = device_manager
        self.websocket = websocket_interface
        self.chip_tool = chip_tool_manager
        self.data_model = data_model
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
            """Health check endpoint."""
            return {
                "status": "healthy",
                "websocket_clients": self.websocket.connected_clients_count
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
                self.logger.info(f"Received command: {request.command}")

                # Execute command via chip-tool
                response = await self.chip_tool.execute_command(request.command)

                # Format response according to API design
                if response.status == "success" and response.data:
                    # Extract structured data from response
                    formatted_response = self._format_command_response(response)
                    print(f"Formatted response: {formatted_response}")
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

            except Exception as e:
                self.logger.error(f"Error executing command: {e}")
                await self.websocket.send_error(f"Command execution failed: {str(e)}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.get("/attributes")
        async def get_all_attributes():
            """
            Get all attributes.

            Returns:
                List of all attributes
            """
            try:
                attributes = self.device_manager.get_all_attributes()
                return {"attributes": attributes}
            except Exception as e:
                self.logger.error(f"Error getting attributes: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.get("/device")
        async def get_all_devices():
            """
            Get all devices.

            Returns:
                List of all devices
            """
            try:
                devices = self.device_manager.get_all_devices()
                return {"devices": devices}
            except Exception as e:
                self.logger.error(f"Error getting devices: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.get("/device/{node_id}")
        async def get_device_by_node_id(node_id: int):
            """
            Get devices by node ID.

            Args:
                node_id: Node ID

            Returns:
                List of devices for the node
            """
            try:
                devices = self.device_manager.get_device_by_node_id(node_id)
                if not devices:
                    raise HTTPException(status_code=404, detail="No devices found for node ID")
                return {"devices": devices}
            except HTTPException:
                raise
            except Exception as e:
                self.logger.error(f"Error getting device by node ID: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.get("/device/{node_id}/{endpoint}")
        async def get_device_by_node_id_endpoint(node_id: int, endpoint: int):
            """
            Get device by node ID and endpoint.

            Args:
                node_id: Node ID
                endpoint: Endpoint ID

            Returns:
                Device information
            """
            try:
                device = self.device_manager.get_device_by_node_id_endpoint(node_id, endpoint)
                if not device:
                    raise HTTPException(status_code=404, detail="Device not found")
                return {"device": device}
            except HTTPException:
                raise
            except Exception as e:
                self.logger.error(f"Error getting device: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.post("/device")
        async def commission_device(request: Optional[CommissioningRequest] = None):
            """
            Commission a new device.

            Args:
                request: Optional commissioning request with manual pairing code

            Returns:
                Commissioning result
            """
            try:
                success = await self.device_manager.register_new_device()
                if success:
                    # デバイスコミッショニング成功後のコールバック実行
                    if hasattr(self, '_device_commissioned_callback'):
                        try:
                            await self._device_commissioned_callback()
                        except Exception as callback_error:
                            self.logger.error(f"Error in device commissioned callback: {callback_error}")
                            # コールバックエラーでもコミッショニング成功は返す

                    return {"status": "success", "message": "Device commissioned successfully"}
                else:
                    raise HTTPException(status_code=400, detail="Device commissioning failed")
            except HTTPException:
                raise
            except Exception as e:
                self.logger.error(f"Error commissioning device: {e}")
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
                # This would need to be implemented in device_manager
                # For now, return a placeholder response
                return {
                    "status": "success",
                    "node": node_id,
                    "endpoint": 1,  # Would need to be determined
                    "manual_pairing_code": "56789123456",  # Would be generated
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
                    return {"status": "success", "message": "Device deleted successfully"}
                else:
                    raise HTTPException(status_code=400, detail="Device deletion failed")
            except HTTPException:
                raise
            except Exception as e:
                self.logger.error(f"Error deleting device: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.get("/device/{node_id}/{endpoint}/clusters")
        async def get_device_clusters(node_id: int, endpoint: int):
            """
            Get clusters for a device.

            Args:
                node_id: Node ID
                endpoint: Endpoint ID

            Returns:
                List of clusters
            """
            try:
                device = self.device_manager.get_device_by_node_id_endpoint(node_id, endpoint)
                if not device:
                    raise HTTPException(status_code=404, detail="Device not found")

                clusters = self.device_manager.get_device_clusters(device)
                return {"clusters": clusters}
            except HTTPException:
                raise
            except Exception as e:
                self.logger.error(f"Error getting device clusters: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.get("/device/{node_id}/{endpoint}/{cluster_name}/attributes")
        async def get_cluster_attributes(node_id: int, endpoint: int, cluster_name: str):
            """
            Get attributes for a device cluster.

            Args:
                node_id: Node ID
                endpoint: Endpoint ID
                cluster_name: Cluster name

            Returns:
                List of attributes
            """
            try:
                device = self.device_manager.get_device_by_node_id_endpoint(node_id, endpoint)
                if not device:
                    raise HTTPException(status_code=404, detail="Device not found")

                attributes = self.device_manager.get_device_attributes(device, cluster_name)
                return {"attributes": attributes}
            except HTTPException:
                raise
            except Exception as e:
                self.logger.error(f"Error getting cluster attributes: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.get("/device/{node_id}/{endpoint}/{cluster_name}/{attribute_name}/read")
        async def read_attribute_direct(node_id: int, endpoint: int, cluster_name: str, attribute_name: str):
            """
            Read attribute from device using direct path.

            Args:
                node_id: Node ID
                endpoint: Endpoint ID
                cluster_name: Cluster name
                attribute_name: Attribute name

            Returns:
                Attribute value
            """
            try:
                device = self.device_manager.get_device_by_node_id_endpoint(node_id, endpoint)
                if not device:
                    raise HTTPException(status_code=404, detail="Device not found")

                value = await self.device_manager.read_device_attribute(
                    device, cluster_name, attribute_name
                )

                return {
                    "node": node_id,
                    "endpoint": endpoint,
                    "cluster": cluster_name,
                    "attribute": attribute_name,
                    "value": value
                }
            except HTTPException:
                raise
            except Exception as e:
                self.logger.error(f"Error reading attribute: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.post("/device/{node_id}/{endpoint}/{cluster_name}/{attribute_name}/write")
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

        @self.app.post("/devices/{node_id}/{endpoint}/attributes/read")
        async def read_attribute(node_id: int, endpoint: int, request: AttributeRequest):
            """
            Read attribute from device.

            Args:
                node_id: Node ID
                endpoint: Endpoint ID
                request: Attribute request

            Returns:
                Attribute value
            """
            try:
                device = self.device_manager.get_device_by_node_id_endpoint(node_id, endpoint)
                if not device:
                    raise HTTPException(status_code=404, detail="Device not found")

                value = await self.device_manager.read_device_attribute(
                    device, request.cluster_name, request.attribute_name
                )

                return {
                    "cluster": request.cluster_name,
                    "attribute": request.attribute_name,
                    "value": value
                }
            except HTTPException:
                raise
            except Exception as e:
                self.logger.error(f"Error reading attribute: {e}")
                raise HTTPException(status_code=500, detail=str(e))

        @self.app.post("/devices/{node_id}/{endpoint}/attributes/write")
        async def write_attribute(node_id: int, endpoint: int, request: AttributeRequest):
            """
            Write attribute to device.

            Args:
                node_id: Node ID
                endpoint: Endpoint ID
                request: Attribute request with value

            Returns:
                Write result
            """
            try:
                if request.value is None:
                    raise HTTPException(status_code=400, detail="Value is required for write operation")

                device = self.device_manager.get_device_by_node_id_endpoint(node_id, endpoint)
                if not device:
                    raise HTTPException(status_code=404, detail="Device not found")

                success = await self.device_manager.write_device_attribute(
                    device, request.cluster_name, request.attribute_name, request.value
                )

                if success:
                    return {"status": "success", "message": "Attribute written successfully"}
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
        cluster_map = {
            6: "On/Off",
            8: "LevelControl",
            3: "Identify",
            29: "Descriptor",
            40: "BasicInformation"
        }
        return cluster_map.get(cluster_id)

    def _get_attribute_name_by_id(self, cluster_id: int, attribute_id: int) -> Optional[str]:
        """Get attribute name by cluster and attribute ID."""
        attribute_map = {
            6: {0: "OnOff"},  # On/Off cluster
            8: {0: "CurrentLevel"},  # Level Control cluster
            3: {0: "IdentifyTime", 1: "IdentifyType"},  # Identify cluster
        }
        return attribute_map.get(cluster_id, {}).get(attribute_id)
