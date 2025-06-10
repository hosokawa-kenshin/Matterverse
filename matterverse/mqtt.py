import paho.mqtt.client as mqtt
import json
import re
import asyncio
import threading
from database import get_devices_from_database
from matter_utils import get_cluster_by_device_type, get_attributes_by_cluster_name

def on_connect(client, userdata, flags, rc):
    print("\033[1;35mMQTT\033[0m:     Connected with result code " + str(rc))
    client.subscribe("homie/+/+/+/set")
    client.subscribe("cmd/matter/+/+/onoff/toggle")

def on_message(client, userdata, msg):
    print(f"\033[1;35mMQTT\033[0m:     Message received: {msg.topic} {msg.payload}")

    if msg.topic.endswith("/set"):
        match = re.match(r"homie/(\w+)/(\w+)/(\w+)/set", msg.topic)
        if match:
            topic_id, cluster_name, attribute_name = match.groups()
            attribute_name = re.sub(r'(?<!^)(?<![A-Z])(?=[A-Z])', '-', attribute_name).lower()
            payload = msg.payload.decode()
            from database import get_device_by_topic_id
            device = get_device_by_topic_id(topic_id)
            if not device:
                print("\033[1;31mMQTT\033[0m:     Device not found in database.")
                return
            node_id = device.get("NodeID")
            endpoint_id = device.get("Endpoint")
            from chip_tool_server import run_chip_tool_command

            if cluster_name == "onoff":
                command = "on" if payload == "true" else "off"
                chip_command = f"{cluster_name} {command} {node_id} {endpoint_id}"
            else:
                chip_command = f"{cluster_name} write {attribute_name} {payload} {node_id} {endpoint_id}"
            def run_in_thread():
                asyncio.run(run_chip_tool_command(chip_command))

            thread = threading.Thread(target=run_in_thread)
            thread.start()

def disconnect_mqtt(client):
    if client.is_connected():
        devices = get_devices_from_database()
        for device in devices:
            topic_id = device.get("TopicID")
            base = f"homie/{topic_id}"
            client.publish(f"{base}/$state", "disconnected", retain=True)
            print(f"\033[1;35mMQTT\033[0m:     Publishing disconnect state for device {topic_id}...")
        client.loop_stop()
        client.disconnect()
        print("\033[1;35mMQTT\033[0m:     MQTT disconnected.")
    else:
        print("\033[1;35mMQTT\033[0m:     MQTT already disconnected.")

def publish_homie_devices(client):
    devices = get_devices_from_database()
    if not devices:
        print("\033[1;35mMQTT\033[0m:     No devices found in the database.")
        return

    for device in devices:
        publish_homie_device(client, device)

def publish_homie_device(client, device):
    name = "Test Device"
    topic_id = device.get("TopicID")
    device_type = f"0x{int(device.get('DeviceType', 0)):04x}"
    clusters = get_cluster_by_device_type(device_type)

    base = f"homie/{topic_id}"

    client.will_set(f"{base}/$state", "lost", retain=True)
    client.publish(f"{base}/$homie", "3.0.1", retain=True)
    client.publish(f"{base}/$name", name, retain=True)
    client.publish(f"{base}/$state", "init", retain=True)

    cluster_names = []
    attribute_names = []

    for cluster in clusters:
        cluster_nm = cluster.lower().replace("/", "")
        cluster_nm = re.sub(r' ', '', cluster_nm)
        cluster_names.append(cluster_nm)

    client.publish(f"{base}/$nodes", ",".join(cluster_names), retain=True)

    for cluster in clusters:
        attributes = get_attributes_by_cluster_name(cluster)
        cluster_name = cluster.lower().replace("/", "")
        cluster_name = re.sub(r' ', '', cluster_name)
        client.publish(f"{base}/{cluster_name}/$name", cluster, retain=True)
        attribute_names = [attr["name"] for attr in attributes]
        client.publish(f"{base}/{cluster_name}/$properties", ",".join(attribute_names), retain=True)
        for attr in attributes:
            attribute_name = attr["name"]
            client.publish(f"{base}/{cluster_name}/{attribute_name}/$name", attr["name"], retain=True)
            if "int" in attr["type"]:
                client.publish(f"{base}/{cluster_name}/{attribute_name}/$datatype", "integer", retain=True)
            elif "bool" in attr["type"]:
                client.publish(f"{base}/{cluster_name}/{attribute_name}/$datatype", "boolean", retain=True)
                client.publish(f"{base}/{cluster_name}/{attribute_name}", "false", retain=True)
            else:
                client.publish(f"{base}/{cluster_name}/{attribute_name}/$datatype", attr["type"], retain=True)
            if attr['writable'] == "true":
                client.publish(f"{base}/{cluster_name}/{attribute_name}/$settable", "true", retain=True)
            else:
                client.publish(f"{base}/{cluster_name}/{attribute_name}/$settable", "false", retain=True)
            print(f"{base}/{cluster_name}/{attribute_name}")
    client.publish(f"{base}/$state", "ready", retain=True)
    print(f"\033[1;35mMQTT\033[0m:     Homie device created: {base}")


def publish_to_mqtt_broker(client, json_str):
    from matter_utils import get_cluster_name_by_code, get_attribute_name_by_code
    print("\033[1;35mMQTT\033[0m:     Publishing to MQTT broker...")
    json_data = json.loads(json_str)

    report_data = json_data.get("ReportDataMessage", {})
    attribute_report = report_data.get("AttributeReportIBs", [{}])[0].get("AttributeReportIB", {})
    attribute_data = attribute_report.get("AttributeDataIB", {})
    attribute_path = attribute_data.get("AttributePathIB", {})

    node_id = attribute_path.get("NodeID")
    endpoint_id = attribute_path.get("Endpoint")

    from database import get_device_by_node_id_endpoint
    if node_id > 9223372036854775807 or node_id < -9223372036854775808:
        print("\033[1;31mMQTT\033[0m:     NodeID exceeds SQLite integer range, setting NodeID to NULL.")
        node_id = None

    device = get_device_by_node_id_endpoint(node_id, endpoint_id)
    if not device:
        print("\033[1;31mMQTT\033[0m:     Device not found in database.")
        return
    devicetype = device.get("DeviceType")
    devicetype = f"0x{int(devicetype):04x}"

    clusters = get_cluster_by_device_type(devicetype)
    cluster_code = attribute_path.get("Cluster")
    cluster_code = f"0x{int(cluster_code):04x}"
    attribute_code = attribute_path.get("Attribute")
    payload = attribute_data.get("Data")

    if not isinstance(payload, str):
        payload = str(payload)
    cluster_name = get_cluster_name_by_code(cluster_code)

    if cluster_name not in clusters:
        print("\033[1;31mMQTT\033[0m:     Cluster not found in device's clusters, skipping MQTT publish.")
        return
    else:
        attribute_code = f"0x{int(attribute_code):04x}"

    cluster_name = cluster_name.lower().replace("/", "")
    attribute_name = get_attribute_name_by_code(cluster_code, attribute_code)
    topic_id = device.get("TopicID")
    topic = f"homie/{topic_id}/{cluster_name}/{attribute_name}"
    result = client.publish(topic, payload, retain=True)

    if result.rc == mqtt.MQTT_ERR_SUCCESS:
        print("\033[1;35mMQTT\033[0m:     MQTT publish successful.")
    else:
        print("\033[1;31mMQTT\033[0m:     MQTT publish failed with result code:", result.rc)

mqtt_client = mqtt.Client(transport="websockets")
mqtt_client.on_connect = on_connect
mqtt_client.on_message = on_message
