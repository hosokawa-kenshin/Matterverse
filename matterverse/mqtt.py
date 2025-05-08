import paho.mqtt.client as mqtt

def on_connect(client, userdata, flags, rc):
    print("\033[1;35mMQTT:\033[0m     Connected with result code " + str(rc))
    client.subscribe("cmd/matter/+/+/onoff/toggle")

import asyncio

def on_message(client, userdata, msg):
    print(f"\033[1;35mMQTT:\033[0m     Message received: {msg.topic} {msg.payload}")
    if msg.topic.startswith("cmd/matter/"):
        parts = msg.topic.split("/")
        if len(parts) == 6:
            from chip_tool_server import run_chip_tool_command, loop
            node_id = parts[2]
            endpoint_id = parts[3]
            cluster = parts[4]
            command = parts[5]

            asyncio.run_coroutine_threadsafe(run_chip_tool_command(f"{cluster} {command} {node_id} {endpoint_id}"), loop)
            print(f"\033[1;35mMQTT:\033[0m     Processing toggle command for device {node_id} with command {endpoint_id}")

def publish_to_mqtt_broker(client, json):
    #TODO generate topic from json
    topic = "dt/matter/1/1/onoff/toggle"
    result = client.publish(topic, json)
    if result.rc == mqtt.MQTT_ERR_SUCCESS:
        print("\033[1;35mMQTT:\033[0m     MQTT publish successful.")
    else:
        print("\033[1;31mMQTT:\033[0m     MQTT publish failed with result code:", result.rc)

mqtt_client = mqtt.Client(transport="websockets")
mqtt_client.on_connect = on_connect
mqtt_client.on_message = on_message