import paho.mqtt.client as mqtt
import json
import re
import asyncio
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
            payload = msg.payload.decode()
            from database import get_device_by_topic_id
            device = get_device_by_topic_id(topic_id)
            if not device:
                print("\033[1;31mMQTT\033[0m:     Device not found in database.")
                return
            node_id = device.get("NodeID")
            endpoint_id = device.get("Endpoint")
            if cluster_name == "onoff":
                command = "on" if payload == "true" else "off"
                asyncio.run_coroutine_threadsafe(
                    run_chip_tool_command(f"{cluster_name} {command} {node_id} {endpoint_id}"), loop
                )
            else:
                asyncio.run_coroutine_threadsafe(
                    run_chip_tool_command(f"{cluster_name} write {attribute_name} {payload} {node_id} {endpoint_id}"), loop
                )
            print(f"\033[1;35mMQTT\033[0m:     Homie set received: {payload} on {node_id}:{cluster_name}:{attribute_name}")

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

def create_homie_devices(client):
    devices = get_devices_from_database()
    if not devices:
        print("\033[1;35mMQTT\033[0m:     No devices found in the database.")
        return

    for device in devices:
        publish_homie_device(client, device)

def publish_homie_device(client, device):
    from matter_xml_parser import all_clusters

    name = "Test Device"
    topic_id = device.get("TopicID")
    device_type = f"0x{int(device.get('DeviceType', 0)):04X}"
    clusters = get_cluster_by_device_type(device_type)

    base = f"homie/{topic_id}"

    client.will_set(f"{base}/$state", "lost", retain=True)
    client.publish(f"{base}/$homie", "3.0.1", retain=True)
    client.publish(f"{base}/$name", name, retain=True)
    client.publish(f"{base}/$state", "init", retain=True)

    cluster_names = []
    attribute_names = []

    for cluster in clusters:
        cluster_names.append(cluster.lower().replace("/", ""))

    client.publish(f"{base}/$nodes", ",".join(cluster_names), retain=True)

    for cluster in clusters:
        attributes = get_attributes_by_cluster_name(cluster)
        cluster_name = cluster.lower().replace("/", "")
        client.publish(f"{base}/{cluster_name}/$name", cluster, retain=True)
        attribute_names = [re.sub(r'(?<!^)(?<![A-Z])(?=[A-Z])', '-', attr["name"]).lower() for attr in attributes]
        client.publish(f"{base}/{cluster_name}/$properties", ",".join(attribute_names), retain=True)
        for attr in attributes:
            attribute_name = attr["name"]
            if attribute_name != '':
                attribute_name = re.sub(r'(?<!^)(?<![A-Z])(?=[A-Z])', '-', attribute_name).lower()
                client.publish(f"{base}/{cluster_name}/{attribute_name}/$name", attr["name"], retain=True)
                if "int" in attr["type"]:
                    client.publish(f"{base}/{cluster_name}/{attribute_name}/$datatype", "integer", retain=True)
                elif "bool" in attr["type"]:
                    client.publish(f"{base}/{cluster_name}/{attribute_name}/$datatype", "boolean", retain=True)
                    client.publish(f"{base}/{cluster_name}/{attribute_name}/$format", "OFF,ON", retain=True)
                    client.publish(f"{base}/{cluster_name}/{attribute_name}", "false", retain=True)
                else:
                    client.publish(f"{base}/{cluster_name}/{attribute_name}/$datatype", attr["type"], retain=True)
                client.publish(f"{base}/{cluster_name}/{attribute_name}/$settable", "true", retain=True)
                print(f"{base}/{cluster_name}/{attribute_name}")
    client.publish(f"{base}/$state", "ready", retain=True)
    print(f"\033[1;35mMQTT\033[0m:     Homie device created: {base}")


def publish_to_mqtt_broker(client, json_str):
    from matter_utils import get_cluster_name_by_code, get_attribute_name_by_code
    json_data = json.loads(json_str)

    report_data = json_data.get("ReportDataMessage", {})
    attribute_report = report_data.get("AttributeReportIBs", [{}])[0].get("AttributeReportIB", {})
    attribute_data = attribute_report.get("AttributeDataIB", {})
    attribute_path = attribute_data.get("AttributePathIB", {})

    node_id = attribute_path.get("NodeID")
    endpoint_id = attribute_path.get("Endpoint")
    cluster_code = attribute_path.get("Cluster")
    cluster_code = f"0x{int(cluster_code):04X}"
    attribute_code = attribute_path.get("Attribute")
    attribute_code = f"0x{int(attribute_code):04X}"

    payload = attribute_data.get("Data")

    cluster_name = get_cluster_name_by_code(cluster_code)
    cluster_name = cluster_name.lower().replace("/", "")
    attribute_name = get_attribute_name_by_code(cluster_code, attribute_code)
    attribute_name = re.sub(r'(?<!^)(?<![A-Z])(?=[A-Z])', '-', attribute_name).lower()

    from database import get_device_by_node_id_endpoint
    device = get_device_by_node_id_endpoint(node_id, endpoint_id)
    if not device:
        print("\033[1;31mMQTT\033[0m:     Device not found in database.")
        return

    topic_id = device.get("TopicID")
    topic = f"homie/{topic_id}/{cluster_name}/{attribute_name}"
    result = client.publish(topic, payload, retain=True)

    # cluster = all_clusters.get(cluster_code, {})
    # cluster_name = cluster.get("name")
    # if cluster_name:
    #     cluster_name = cluster_name.lower().replace("/", "")

    # attribute_name = None
    # for attr in cluster.get("attributes", []):
    #     if attr["code"] == attribute_code:
    #         attribute_name = attr["name"]
    #         break
    # if attribute_name:
    #     attribute_name = re.sub(r'(?<!^)(?<![A-Z])(?=[A-Z])', '-', attribute_name).lower()

    # print(f"\033[1;35mMQTT\033[0m:     Publishing to MQTT broker with topic: {topic}")
    # result = client.publish(topic, json_str)
    if result.rc == mqtt.MQTT_ERR_SUCCESS:
        print("\033[1;35mMQTT\033[0m:     MQTT publish successful.")
    else:
        print("\033[1;31mMQTT\033[0m:     MQTT publish failed with result code:", result.rc)

mqtt_client = mqtt.Client(transport="websockets")
mqtt_client.on_connect = on_connect
mqtt_client.on_message = on_message
