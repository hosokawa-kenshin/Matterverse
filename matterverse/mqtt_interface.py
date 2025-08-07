"""
MQTT interface for Matterverse application.
Handles MQTT broker connection, Homie device publishing, and command handling.
"""
import json
import re
import threading
import asyncio
from typing import Optional, Callable, Dict, Any, List
import paho.mqtt.client as mqtt

from logger import get_mqtt_logger


class MQTTInterface:
    """MQTT interface for device communication using Homie convention."""

    def __init__(self, broker_url: str, broker_port: int = 9001):
        """
        Initialize MQTT interface.

        Args:
            broker_url: MQTT broker URL
            broker_port: MQTT broker port
        """
        self.broker_url = broker_url
        self.broker_port = broker_port
        self.logger = get_mqtt_logger()

        self.client = mqtt.Client(transport="websockets")
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message

        self._connected = False
        self._command_callback: Optional[Callable] = None

        # Data model access
        self._data_model = None
        self._database = None

    def set_data_model(self, data_model):
        """Set data model dictionary reference."""
        self._data_model = data_model

    def set_database(self, database):
        """Set database reference."""
        self._database = database

    def set_command_callback(self, callback: Callable):
        """Set callback for handling MQTT commands."""
        self._command_callback = callback

    def connect(self) -> bool:
        """
        Connect to MQTT broker.

        Returns:
            True if connection successful, False otherwise
        """
        try:
            self.client.connect(self.broker_url, port=self.broker_port, keepalive=60)
            self.client.loop_start()
            return True
        except Exception as e:
            self.logger.error(f"Failed to connect to MQTT broker: {e}")
            return False

    def disconnect(self):
        """Disconnect from MQTT broker."""
        if self._connected and self._database:
            # Publish disconnect state for all devices
            devices = self._database.get_all_devices()
            for device in devices:
                topic_id = device.get("TopicID")
                if topic_id:
                    base = f"homie/{topic_id}"
                    self.client.publish(f"{base}/$state", "disconnected", retain=True)
                    self.logger.info(f"Publishing disconnect state for device {topic_id}")

        if self.client.is_connected():
            self.client.loop_stop()
            self.client.disconnect()
            self.logger.info("MQTT disconnected")
        else:
            self.logger.info("MQTT already disconnected")

    def _on_connect(self, client, userdata, flags, rc):
        """Handle MQTT connection."""
        if rc == 0:
            self._connected = True
            self.logger.info(f"Connected with result code {rc}")
            client.subscribe("homie/+/+/+/set")
        else:
            self.logger.error(f"Failed to connect with result code {rc}")

    def _on_message(self, client, userdata, msg):
        """Handle incoming MQTT messages."""
        self.logger.info(f"Message received: {msg.topic} {msg.payload}")

        if msg.topic.endswith("/set"):
            self._handle_command_message(msg)

    def _handle_command_message(self, msg):
        """Handle command messages from MQTT."""
        match = re.match(r"homie/(\w+)/(\w+)/(\w+)/set", msg.topic)
        if not match:
            return

        topic_id, cluster_name, attribute_name = match.groups()
        payload = msg.payload.decode()

        if not self._database:
            self.logger.error("Database not available")
            return

        device = self._database.get_device_by_topic_id(topic_id)
        if not device:
            self.logger.error("Device not found in database")
            return

        node_id = device.get("NodeID")
        endpoint_id = device.get("Endpoint")

        # Convert attribute name back to chip-tool format
        attribute_name = re.sub(r'(?<!^)(?<![A-Z])(?=[A-Z])', '-', attribute_name).lower()

        # Prepare chip-tool command
        if cluster_name == "onoff":
            command = "on" if payload == "true" else "off"
            chip_command = f"{cluster_name} {command} {node_id} {endpoint_id}"
        else:
            chip_command = f"{cluster_name} write {attribute_name} {payload} {node_id} {endpoint_id}"

        # Execute command via callback
        if self._command_callback:
            def run_in_thread():
                asyncio.run(self._command_callback(chip_command))

            thread = threading.Thread(target=run_in_thread)
            thread.start()

    def publish_homie_devices(self):
        """Publish all devices using Homie convention."""
        if not self._database:
            self.logger.error("Database not available")
            return

        devices = self._database.get_all_devices()
        if not devices:
            self.logger.error("No devices found in the database")
            return

        for device in devices:
            self.publish_homie_device(device)

    def publish_homie_device(self, device: Dict[str, Any]):
        """
        Publish single device using Homie convention.

        Args:
            device: Device dictionary
        """
        if not self._data_model:
            self.logger.error("Data model not available")
            return

        name = "Test Device"  # TODO: Get actual device name
        topic_id = device.get("TopicID")
        device_type = f"0x{int(device.get('DeviceType', 0)):04x}"
        clusters = self._data_model.get_clusters_by_device_type(device_type)

        base = f"homie/{topic_id}"

        # Publish device properties
        self.client.will_set(f"{base}/$state", "lost", retain=True)
        self.client.publish(f"{base}/$homie", "3.0.1", retain=True)
        self.client.publish(f"{base}/$name", name, retain=True)
        self.client.publish(f"{base}/$state", "init", retain=True)

        # Prepare cluster names
        cluster_names = []
        for cluster in clusters:
            cluster_nm = cluster.lower().replace("/", "").replace(" ", "")
            cluster_names.append(cluster_nm)

        self.client.publish(f"{base}/$nodes", ",".join(cluster_names), retain=True)

        # Publish cluster information
        for cluster in clusters:
            self._publish_cluster_info(base, cluster)

        self.client.publish(f"{base}/$state", "ready", retain=True)
        self.logger.info(f"Homie device created: {base}")

    def _publish_cluster_info(self, base: str, cluster: str):
        """Publish cluster information for a device."""
        if not self._data_model:
            return

        attributes = self._data_model.get_attributes_by_cluster_name(cluster)
        cluster_name = cluster.lower().replace("/", "").replace(" ", "")

        self.client.publish(f"{base}/{cluster_name}/$name", cluster, retain=True)

        attribute_names = [attr["name"] for attr in attributes]
        self.client.publish(f"{base}/{cluster_name}/$properties",
                          ",".join(attribute_names), retain=True)

        for attr in attributes:
            self._publish_attribute_info(base, cluster_name, cluster, attr)

    def _publish_attribute_info(self, base: str, cluster_name: str,
                               cluster: str, attr: Dict[str, Any]):
        """Publish attribute information."""
        if not self._data_model:
            return

        attribute_name = attr["name"]
        attr_type = attr.get("type", "")

        self.client.publish(f"{base}/{cluster_name}/{attribute_name}/$name",
                          attribute_name, retain=True)

        # Set data type based on attribute type
        if "Enum" in attr_type or attribute_name == "CurrentMode":
            self.client.publish(f"{base}/{cluster_name}/{attribute_name}/$datatype",
                              "enum", retain=True)

            enums = self._data_model.get_enums_by_cluster_name(cluster)
            for enum in enums:
                if enum.get("name", "").lower() in attr_type.lower():
                    enum_format = self._convert_items_to_homie_format(enum.get("items", []))
                    self.client.publish(f"{base}/{cluster_name}/{attribute_name}/$format",
                                      enum_format, retain=True)
                    break

        elif "int" in attr_type:
            self.client.publish(f"{base}/{cluster_name}/{attribute_name}/$datatype",
                              "integer", retain=True)

        elif "bool" in attr_type:
            self.client.publish(f"{base}/{cluster_name}/{attribute_name}/$datatype",
                              "boolean", retain=True)
            self.client.publish(f"{base}/{cluster_name}/{attribute_name}/$format",
                              "true,false", retain=True)

        elif "string" in attr_type:
            self.client.publish(f"{base}/{cluster_name}/{attribute_name}/$datatype",
                              "string", retain=True)

        # Set settable property
        if attr['writable'] == "true" or attr["name"] == "OnOff":
            self.client.publish(f"{base}/{cluster_name}/{attribute_name}/$settable",
                              "true", retain=True)
        else:
            self.client.publish(f"{base}/{cluster_name}/{attribute_name}/$settable",
                              "false", retain=True)

    def _convert_items_to_homie_format(self, items: List[Dict]) -> str:
        """Convert enum items to Homie format."""
        def escape_commas(value):
            return value.replace(",", ",,")

        return ",".join([f"{item['value']}:{escape_commas(item['name'])}"
                        for item in items])

    def publish_attribute_data(self, json_str: str) -> bool:
        """
        Publish attribute data to MQTT.

        Args:
            json_str: JSON string with attribute data

        Returns:
            True if successful, False otherwise
        """
        if not self._data_model or not self._database:
            self.logger.error("Data model or database not available")
            return False

        try:

            print(f"Received attribute data: {json_str}")
            json_data = json.loads(json_str)
            node_id = json_data.get("node")
            endpoint_id = json_data.get("endpoint")
            cluster_name = json_data.get("cluster")
            cluster_name = cluster_name.lower().replace("/", "").replace(" ", "")
            value = str(json_data.get("value"))

            attribute_name = json_data.get("attribute")

            sql_max_number = 9223372036854775807
            sql_min_number = -9223372036854775808

            # Validate node ID
            if node_id and (node_id > sql_max_number or node_id < sql_min_number):
                self.logger.error("NodeID exceeds SQLite integer range, setting NodeID to NULL")
                node_id = None
            if isinstance(node_id, str) and (node_id == "UNKNOWN" or not node_id.replace('0x', '').isalnum()):
                self.logger.error(f"Skipping MQTT publish for invalid NodeID: {node_id}")
                return False

            device = self._database.get_device_by_node_id_endpoint(node_id, endpoint_id)
            if not device:
                self.logger.error("Device not found in database")
                return False

            topic_id = device.get("TopicID")
            topic = f"homie/{topic_id}/{cluster_name}/{attribute_name}"

            result = self.client.publish(topic, value, retain=True)

            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                self.logger.info("MQTT publish successful")
                return True
            else:
                self.logger.error(f"MQTT publish failed with result code: {result.rc}")
                return False

        except Exception as e:
            self.logger.error(f"Error publishing attribute data: {e}")
            return False
