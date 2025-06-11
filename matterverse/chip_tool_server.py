import json
import re
from dotenv import load_dotenv
import os
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
import asyncio
from contextlib import asynccontextmanager
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
from mqtt import mqtt_client, publish_to_mqtt_broker, publish_homie_devices, disconnect_mqtt
from matter_xml_parser import parse_clusters_info, parse_device_type_info
from database import insert_device_to_database, close_database_connection, insert_unique_id_to_database, get_endpoints_by_node_id, get_new_node_id_from_database
from subscribe import subscribe_alldevices, subscribe_device
import hashlib
from chip_tool_parser import delete_garbage, extract_named_blocks, parse_chip_data, TreeToJson

load_dotenv()
CHIP_TOOL_PATH = os.getenv('CHIP_TOOL_PATH', './chip-tool')
COMMISSIONING_DIR = os.getenv('COMMISSIONING_DIR', './commitioning_dir')
MQTT_BROKER_URL = os.getenv('MQTT_BROKER_URL', 'localhost')

cluster_xml = os.getenv('CLUSTER_XML_DIR', '../sdk/src/app/zap-templates/zcl/data-model/chip/matter-clusters.xml')
device_type_xml = os.getenv('DEVICETYPE_XML_FILE', '../sdk/src/app/zap-templates/zcl/data-model/chip/matter-device-types.xml')
paa_root_cert = os.getenv('PAA_CERT_DIR_PATH', '../sdk/credentials/paa_root_cert')

connected_clients = set()
request_queue = asyncio.Queue()
response_queue = asyncio.Queue()
parsed_queue = asyncio.Queue()

class CommandRequest(BaseModel):
    command: str

async def publish_parsed_data():
    global connected_clients
    while True:
        parsed_json = await parsed_queue.get()
        if "ReportDataMessage" in parsed_json and "AttributeReportIBs" in parsed_json:
            await publish_to_all_websocket_clients(parsed_json)
            publish_to_mqtt_broker(mqtt_client, parsed_json) # TODO
        elif "InvokeResponseMessage" in parsed_json:
            json_data = json.loads(parsed_json)
            if "CommandStatusIB" in parsed_json:
                cluster_id = json_data["InvokeResponseMessage"]["InvokeResponseIBs"][0]["InvokeResponseIB"]["CommandStatusIB"]["CommandPathIB"]["ClusterId"]
                command_id = json_data["InvokeResponseMessage"]["InvokeResponseIBs"][0]["InvokeResponseIB"]["CommandStatusIB"]["CommandPathIB"]["CommandId"]
            else:
                cluster_id = json_data["InvokeResponseMessage"]["InvokeResponseIBs"][0]["InvokeResponseIB"]["CommandDataIB"]["CommandPathIB"]["ClusterId"]
                command_id = json_data["InvokeResponseMessage"]["InvokeResponseIBs"][0]["InvokeResponseIB"]["CommandDataIB"]["CommandPathIB"]["CommandId"]
            if cluster_id == 48 and command_id == 5:
                result = json_data["InvokeResponseMessage"]["InvokeResponseIBs"][0]["InvokeResponseIB"]["CommandDataIB"]["CommandFields"]["0x0"]
                if result == "0":
                    node_id = json_data["InvokeResponseMessage"]["InvokeResponseIBs"][0]["InvokeResponseIB"]["CommandDataIB"]["CommandPathIB"]["NodeID"]
                    await register_device_to_database()
                    print("\033[1;34mCHIP\033[0m:     Device registration successful.")
                    await subscribe_device(node_id)
        await asyncio.sleep(0.1)

async def parse_chip_tool_output():
    global chip_tool_output
    print("\033[1;34mCHIP\033[0m:     Start parsing chip-tool output")
    while True:

        if "[TOO] Endpoint: " in chip_tool_output or "Received Command Response Status" in chip_tool_output or "Refresh LivenessCheckTime for" in chip_tool_output or "Subscription established with SubscriptionID" in chip_tool_output or "Received CommissioningComplete response" in chip_tool_output:
            lines = chip_tool_output.splitlines()
            chip_tool_output = ""
            current_output = []
            for line in lines:
                if "Received CommissioningComplete response" in line or "Received Command Response Status" in line or "[TOO] Endpoint:" in line or "Refresh LivenessCheckTime for" in line or "Subscription established with SubscriptionID" in line:
                    if current_output:
                        log = ''.join(current_output)
                        data = delete_garbage(log)
                        if data and data.strip():
                            blocks = extract_named_blocks(data)
                            for block in blocks:
                                try:
                                    tree = parse_chip_data(block)
                                    parsed_json = json.dumps(TreeToJson().transform(tree))
                                    print("\033[1;34mCHIP\033[0m:     Received data: ", parsed_json)
                                    await parsed_queue.put(parsed_json)
                                    await response_queue.put(parsed_json)
                                except Exception as e:
                                    print(f"\033[1;34mCHIP\033[0m:     Error parsing data: {e}")
                                    continue
                            break
                else:
                    current_output.append(line + '\n')
            current_output = []
            await asyncio.sleep(0.1)
        else:
            await asyncio.sleep(2)

async def read_repl_output():
    global chip_tool_output
    while True:
        line = await chip_process.stdout.readline()
        chip_tool_output += line.decode()
        await asyncio.sleep(0.01)

async def process_requests():
    while True:
        parsed_json = ""

        try:
            websocket, command, future = await request_queue.get()
            print(f"\033[1;34mCHIP\033[0m:     Processing command: {command}")
            chip_process.stdin.write(command.encode() + b'\n')
            await chip_process.stdin.drain()
            # parsed_json = await parse_chip_tool_output()
            if websocket:
                # await websocket.send_text(json.dumps(parsed_json))
                await websocket.send_text({"command": command, "status": "success"})
            elif future:
                future.set_result({"command": command, "status": "success"})
                # future.set_result(parsed_json)
            await asyncio.sleep(0.1)

        except Exception as e:
            print(f"\033[1;34mCHIP\033[0m:     Error processing command: {command}")
            print(e)

        except asyncio.exceptions.CancelledError:
            break

def generate_hash(node_id, unique_id, endpoint):
    combined = f"{node_id}-{endpoint}-{unique_id}"
    return hashlib.sha256(combined.encode()).hexdigest()

async def get_basic_info_over_matter(node_id, attribute):
    basicinforamation_id = 40
    command = f"basicinformation read {attribute} {node_id} 0"
    await run_chip_tool_command(command)
    while True:
        json_str = await response_queue.get()
        json_data = json.loads(json_str)
        if "ReportDataMessage" in json_str and "AttributeReportIBs" in json_str:
            node = json_data["ReportDataMessage"]["AttributeReportIBs"][0]["AttributeReportIB"]["AttributeDataIB"]["AttributePathIB"]["NodeID"]
            cluster = json_data["ReportDataMessage"]["AttributeReportIBs"][0]["AttributeReportIB"]["AttributeDataIB"]["AttributePathIB"]["Cluster"]
            if node_id == node and cluster == basicinforamation_id:
                value = json_data["ReportDataMessage"]["AttributeReportIBs"][0]["AttributeReportIB"]["AttributeDataIB"]["Data"]
                break
            else:
                continue
    return value

async def get_endpoint_list_over_matter(node_id):
    descriptor_id = 29
    command = f"descriptor read parts-list {node_id} 0"
    await run_chip_tool_command(command)
    while True:
        json_str = await response_queue.get()
        json_data = json.loads(json_str)
        if "ReportDataMessage" in json_str and "AttributeReportIBs" in json_str:
            node = json_data["ReportDataMessage"]["AttributeReportIBs"][0]["AttributeReportIB"]["AttributeDataIB"]["AttributePathIB"]["NodeID"]
            cluster = json_data["ReportDataMessage"]["AttributeReportIBs"][0]["AttributeReportIB"]["AttributeDataIB"]["AttributePathIB"]["Cluster"]
            if node_id == node and cluster == descriptor_id:
                endpoints = json_data["ReportDataMessage"]["AttributeReportIBs"][0]["AttributeReportIB"]["AttributeDataIB"]["Data"]
                break
            else:
                continue
    return endpoints

async def get_devicetypes_over_matter(node_id, endpoint):
    descriptor_id = 29
    command = f"descriptor read device-type-list {node_id} {endpoint}"
    await run_chip_tool_command(command)
    while True:
        json_str = await response_queue.get()
        json_data = json.loads(json_str)
        if "ReportDataMessage" in json_str and "AttributeReportIBs" in json_str:
            node = json_data["ReportDataMessage"]["AttributeReportIBs"][0]["AttributeReportIB"]["AttributeDataIB"]["AttributePathIB"]["NodeID"]
            cluster = json_data["ReportDataMessage"]["AttributeReportIBs"][0]["AttributeReportIB"]["AttributeDataIB"]["AttributePathIB"]["Cluster"]
            if node_id == node and cluster == descriptor_id:
                devicetypes = json_data["ReportDataMessage"]["AttributeReportIBs"][0]["AttributeReportIB"]["AttributeDataIB"]["Data"][0]
                break
            else:
                continue
    return devicetypes

async def register_device_to_database():
    print("\033[1;34mCHIP\033[0m:     Registering device to database...")
    node_id = get_new_node_id_from_database()
    unique_id = await get_basic_info_over_matter(node_id, "unique-id")
    vendor_name = await get_basic_info_over_matter(node_id, "vendor-name")
    vendor_name = re.sub(r'[ -]', '', vendor_name)
    product_name = await get_basic_info_over_matter(node_id, "product-name")
    product_name = re.sub(r'[ -]', '', product_name)
    device_name = f"{vendor_name}_{product_name}"
    insert_unique_id_to_database(node_id, device_name, unique_id)
    endpoints = await get_endpoint_list_over_matter(node_id)

    for endpoint in endpoints:
        topic_id = generate_hash(node_id, unique_id, endpoint)
        topic_id = f"{device_name}_{topic_id}"
        devicetypes = await get_devicetypes_over_matter(node_id, endpoint)
        devicetype = int(devicetypes.get("0x0"))
        insert_device_to_database(node_id, endpoint, devicetype, topic_id)

async def lifespan(app: FastAPI):
    print("\033[1;34mCHIP\033[0m:     Starting chip-tool REPL...")
    global chip_process
    global chip_tool_output
    global tasks

    parse_clusters_info(cluster_xml)
    parse_device_type_info(device_type_xml)

    chip_tool_output = ""
    chip_process = await run_chip_tool_repl()

    mqtt_client.connect(MQTT_BROKER_URL, port=9001, keepalive=60)
    mqtt_client.loop_start()

    publish_homie_devices(mqtt_client)

    tasks = [
        asyncio.create_task(process_requests()),
        asyncio.create_task(read_repl_output()),
        asyncio.create_task(parse_chip_tool_output()),
        asyncio.create_task(publish_parsed_data())
    ]

    await subscribe_alldevices()
    print("\033[1;34mCHIP\033[0m:     chip-tool REPL started.")

    yield

    chip_process.kill()
    print("\033[1;34mCHIP\033[0m:     chip-tool REPL stopped.")

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.on_event("startup")
async def startup_event():
    global connected_clients
    connected_clients = set()

@app.websocket("/ws")
async def run_chip_tool_command_ws(websocket: WebSocket):
    await websocket.accept()
    global connected_clients
    connected_clients.add(websocket)
    try:
        while True:
            command = await websocket.receive_text()
            print(f"Received command: {command}")
            await request_queue.put((websocket, command, None))
    except WebSocketDisconnect:
        print("WebSocket disconnected")
        connected_clients.remove(websocket)

@app.post("/command")
async def run_chip_tool_command_post(request: CommandRequest):
    print(f"\033[1;34mCHIP\033[0m:     received command: {request.command}")
    if "test" in request.command:
        await register_device_to_database()
        return {"status": "success", "message": "Test command received."}
    future = asyncio.get_event_loop().create_future()
    await request_queue.put((None, request.command, future))
    result = await future
    return result

async def run_chip_tool_command(command):
    future = asyncio.get_event_loop().create_future()
    await request_queue.put((None, command, future))
    result = await future
    return result

async def run_chip_tool_repl():
    process = await asyncio.create_subprocess_exec(
        CHIP_TOOL_PATH, "interactive", "start","--paa-trust-store-path", paa_root_cert,"--storage-directory", COMMISSIONING_DIR,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    return process

async def publish_to_all_websocket_clients(message):
    global connected_clients
    for websocket in connected_clients:
        await websocket.send_text(message)
    print(f"\033[1;31mWS  \033[0m:     Published message to all connected clients.")
