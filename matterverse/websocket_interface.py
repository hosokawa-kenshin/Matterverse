"""
WebSocket interface for Matterverse application.
Handles WebSocket connections and real-time communication.
"""
import asyncio
import json
from typing import Set, Optional, Any
from fastapi import WebSocket, WebSocketDisconnect

from logger import get_ws_logger


class WebSocketInterface:
    """WebSocket interface for real-time communication."""

    def __init__(self):
        """Initialize WebSocket interface."""
        self.logger = get_ws_logger()
        self._connected_clients: Set[WebSocket] = set()
        self._connection_lock = asyncio.Lock()

    @property
    def connected_clients_count(self) -> int:
        """Get number of connected clients."""
        return len(self._connected_clients)

    async def connect_client(self, websocket: WebSocket):
        """
        Connect a new WebSocket client.

        Args:
            websocket: WebSocket connection
        """
        await websocket.accept()
        async with self._connection_lock:
            self._connected_clients.add(websocket)

        self.logger.info(f"Client connected. Total clients: {self.connected_clients_count}")

    async def disconnect_client(self, websocket: WebSocket):
        """
        Disconnect a WebSocket client.

        Args:
            websocket: WebSocket connection
        """
        async with self._connection_lock:
            self._connected_clients.discard(websocket)

        self.logger.info(f"Client disconnected. Total clients: {self.connected_clients_count}")

    async def handle_client_connection(self, websocket: WebSocket) -> None:
        """
        Handle WebSocket client connection lifecycle.

        Args:
            websocket: WebSocket connection
        """
        await self.connect_client(websocket)

        try:
            while True:
                # Keep connection alive and handle incoming messages
                data = await websocket.receive_text()
                await self._handle_client_message(websocket, data)

        except WebSocketDisconnect:
            await self.disconnect_client(websocket)
        except Exception as e:
            self.logger.error(f"Error handling WebSocket connection: {e}")
            await self.disconnect_client(websocket)

    async def _handle_client_message(self, websocket: WebSocket, message: str):
        """
        Handle incoming message from client.

        Args:
            websocket: WebSocket connection
            message: Received message
        """
        try:
            # Parse JSON message
            data = json.loads(message)
            message_type = data.get("type")

            if message_type == "ping":
                await self._send_to_client(websocket, {"type": "pong"})
            elif message_type == "command":
                # Handle command request
                command = data.get("command")
                if command:
                    # TODO: Forward to command handler
                    await self._send_to_client(websocket, {
                        "type": "command_received",
                        "command": command
                    })
            else:
                self.logger.warning(f"Unknown message type: {message_type}")

        except json.JSONDecodeError:
            self.logger.error(f"Invalid JSON received: {message}")
            await self._send_to_client(websocket, {
                "type": "error",
                "message": "Invalid JSON format"
            })
        except Exception as e:
            self.logger.error(f"Error handling client message: {e}")

    async def _send_to_client(self, websocket: WebSocket, data: dict) -> bool:
        """
        Send data to specific client.

        Args:
            websocket: WebSocket connection
            data: Data to send

        Returns:
            True if successful, False otherwise
        """
        try:
            await websocket.send_text(json.dumps(data))
            return True
        except Exception as e:
            self.logger.error(f"Error sending to client: {e}")
            # Remove disconnected client
            await self.disconnect_client(websocket)
            return False

    async def broadcast_to_all_clients(self, data: Any) -> int:
        """
        Broadcast data to all connected clients.

        Args:
            data: Data to broadcast (will be JSON serialized if not string)

        Returns:
            Number of clients that received the message
        """
        if not self._connected_clients:
            return 0

        # Convert data to JSON string if needed
        if isinstance(data, str):
            message = data
        else:
            message = json.dumps(data)

        successful_sends = 0
        disconnected_clients = set()

        async with self._connection_lock:
            clients_copy = self._connected_clients.copy()

        for websocket in clients_copy:
            try:
                await websocket.send_text(message)
                successful_sends += 1
            except Exception as e:
                self.logger.error(f"Error broadcasting to client: {e}")
                disconnected_clients.add(websocket)

        # Remove disconnected clients
        if disconnected_clients:
            async with self._connection_lock:
                self._connected_clients -= disconnected_clients

        self.logger.info(f"Broadcasted message to {successful_sends} clients")
        return successful_sends

    async def send_parsed_data(self, parsed_json: str) -> int:
        """
        Send parsed data to all connected clients.

        Args:
            parsed_json: Parsed JSON data

        Returns:
            Number of clients that received the message
        """
        try:
            # Validate JSON
            json.loads(parsed_json)
            return await self.broadcast_to_all_clients(parsed_json)
        except json.JSONDecodeError as e:
            self.logger.error(f"Invalid JSON for broadcasting: {e}")
            return 0

    async def send_command_response(self, command: str, response: str) -> int:
        """
        Send command response to all connected clients.

        Args:
            command: Original command
            response: Command response

        Returns:
            Number of clients that received the message
        """
        data = {
            "type": "command_response",
            "command": command,
            "response": response,
            "timestamp": asyncio.get_event_loop().time()
        }

        return await self.broadcast_to_all_clients(data)

    async def send_error(self, error_message: str) -> int:
        """
        Send error message to all connected clients.

        Args:
            error_message: Error message

        Returns:
            Number of clients that received the message
        """
        data = {
            "type": "error",
            "message": error_message,
            "timestamp": asyncio.get_event_loop().time()
        }

        return await self.broadcast_to_all_clients(data)

    async def send_device_status(self, device_info: dict) -> int:
        """
        Send device status update to all connected clients.

        Args:
            device_info: Device information

        Returns:
            Number of clients that received the message
        """
        data = {
            "type": "device_status",
            "device": device_info,
            "timestamp": asyncio.get_event_loop().time()
        }

        return await self.broadcast_to_all_clients(data)

    async def cleanup(self):
        """Cleanup all WebSocket connections."""
        async with self._connection_lock:
            clients_copy = self._connected_clients.copy()
            self._connected_clients.clear()

        # Close all connections
        for websocket in clients_copy:
            try:
                await websocket.close()
            except Exception as e:
                self.logger.error(f"Error closing WebSocket: {e}")

        self.logger.info("All WebSocket connections closed")
