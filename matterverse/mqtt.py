import paho.mqtt.client as mqtt
import json
import re

def on_connect(client, userdata, flags, rc):
    print("\033[1;35mMQTT\033[0m:     Connected with result code " + str(rc))
    client.subscribe("homie/+/+/+/set")
    client.subscribe("cmd/matter/+/+/onoff/toggle")

import asyncio

def on_message(client, userdata, msg):
    print(f"\033[1;35mMQTT\033[0m:     Message received: {msg.topic} {msg.payload}")
    if msg.topic.startswith("cmd/matter/"):
        parts = msg.topic.split("/")
        if len(parts) == 6:
            from chip_tool_server import run_chip_tool_command, loop
            node_id = parts[2]
            endpoint_id = parts[3]
            cluster_code = parts[4]
            command = parts[5]

            asyncio.run_coroutine_threadsafe(run_chip_tool_command(f"{cluster_code} {command} {node_id} {endpoint_id}"), loop)
            print(f"\033[1;35mMQTT\033[0m:     Processing toggle command for device {node_id} with command {endpoint_id}...")

    elif msg.topic.endswith("/set"):
        match = re.match(r"homie/(\d+)/(\d+)/(\w+)/set", msg.topic)
        if match:
            node_id, endpoint_id, cluster_name = match.groups()
            value = msg.payload.decode().lower()
            if cluster_name == "onoff":
                command = "on" if value == "true" else "off"
                asyncio.run_coroutine_threadsafe(
                    run_chip_tool_command(f"{cluster_name} {command} {node_id} {endpoint_id}"), loop
                )
            else:
                asyncio.run_coroutine_threadsafe(
                    run_chip_tool_command(f"{cluster_name} write {node_id} {endpoint_id}"), loop
                )
            print(f"\033[1;35mMQTT\033[0m:     Homie set received: {command} on {node_id}:{endpoint_id}")

def publish_to_mqtt_broker(client, json_str):
    from chip_tool_server import all_clusters
    global all_clusters
    # json_data = json.loads(json_str)

    # report_data = json_data.get("ReportDataMessage", {})
    # attribute_report = report_data.get("AttributeReportIBs", [{}])[0].get("AttributeReportIB", {})
    # attribute_data = attribute_report.get("AttributeDataIB", {})
    # attribute_path = attribute_data.get("AttributePathIB", {})

    # node_id = attribute_path.get("NodeID")
    # endpoint = attribute_path.get("Endpoint")
    # cluster_code = attribute_path.get("Cluster")
    # cluster_code = f"0x{int(cluster_code):04X}"
    # attribute_code = attribute_path.get("Attribute")
    # attribute_code = f"0x{int(attribute_code):04X}"

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

    # topic = f"dt/matter/{node_id}/{endpoint}/{cluster_name}/{attribute_name}"
    # print(f"\033[1;35mMQTT\033[0m:     Publishing to MQTT broker with topic: {topic}")
    # result = client.publish(topic, json_str)
    # if result.rc == mqtt.MQTT_ERR_SUCCESS:
    print("\033[1;35mMQTT\033[0m:     MQTT publish successful.")
    # else:
    #     print("\033[1;31mMQTT\033[0m:     MQTT publish failed with result code:", result.rc)

mqtt_client = mqtt.Client(transport="websockets")
mqtt_client.on_connect = on_connect
mqtt_client.on_message = on_message
