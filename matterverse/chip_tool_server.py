import json
import sys
import re
import subprocess
from lark import Lark, Transformer
from dotenv import load_dotenv
import os
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
import asyncio
from contextlib import asynccontextmanager
from pydantic import BaseModel
from fastapi.middleware.cors import CORSMiddleware
import signal
from mqtt import mqtt_client, publish_to_mqtt_broker, create_homie_devices, disconnect_mqtt
from matter_xml_parser import parse_clusters_info
from database import insert_device_to_database, close_database_connection, insert_unique_id_to_database, get_endpoints_by_node_id, get_new_node_id_from_database
from subscribe import subscribe_devices
import hashlib

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

class CommandRequest(BaseModel):
    command: str

async def handle_shutdown():
    global chip_process
    chip_process.kill()
    print("\033[1;34mCHIP\033[0m:     chip-tool REPL stopped.")
    disconnect_mqtt(mqtt_client)
    close_database_connection()
    exit(0)

def shutdown_handler():
    asyncio.create_task(handle_shutdown())

loop = asyncio.get_event_loop()
loop.add_signal_handler(signal.SIGINT, shutdown_handler)
loop.add_signal_handler(signal.SIGTERM, shutdown_handler)

async def parse_subscribe_chip_tool_output():
    global chip_tool_output
    global connected_clients
    print("\033[1;34mCHIP\033[0m:     Start parsing chip-tool output")
    while True:
        if "[TOO] Endpoint: " in chip_tool_output or "Received Command Response Status" in chip_tool_output or "Refresh LivenessCheckTime for" in chip_tool_output or "Subscription established with SubscriptionID" in chip_tool_output:
            lines = chip_tool_output.splitlines()
            chip_tool_output = ""
            current_output = []
            for line in lines:
                if "Received Command Response Status" in line or "[TOO] Endpoint:" in line or "Refresh LivenessCheckTime for" in line or "Subscription established with SubscriptionID" in line:
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
                                except Exception as e:
                                    print(f"\033[1;34mCHIP\033[0m:     Error parsing data: {e}")
                                    continue
                                if "ReportDataMessage" in parsed_json and "AttributeReportIBs" in parsed_json:
                                    await publish_to_all_websocket_clients(parsed_json)
                                    publish_to_mqtt_broker(mqtt_client, parsed_json)
                                await response_queue.put(parsed_json)
                            break
                else:
                    current_output.append(line + '\n')
            current_output = []
            await asyncio.sleep(0.1)
        else:
            await asyncio.sleep(2)

async def parse_chip_tool_output():
    global chip_tool_output
    while True:
        if "Received Command Response Status" in chip_tool_output or "[TOO] Endpoint:" in chip_tool_output or "SubscribeResponse is received" in chip_tool_output:
            lines = chip_tool_output.splitlines()
            chip_tool_output = ""
            current_output = []
            for line in lines:
                if "Received Command Response Status" in line or "[TOO] Endpoint:" in line:
                    if current_output:
                        log = ''.join(current_output)
                        data = delete_garbage(log)
                        if data and data.strip():
                            tree = parse_chip_data(data)
                            parsed_json = TreeToJson().transform(tree)
                            print("\033[1;34mCHIP\033[0m:     Received data: ", parsed_json)
                            return parsed_json
                else:
                    current_output.append(line + '\n')
            break
        else:
            await asyncio.sleep(0.1)

async def read_repl_output():
    global chip_tool_output
    while True:
        line = await chip_process.stdout.readline()
        chip_tool_output += line.decode()

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

        except Exception as e:
            print(f"\033[1;34mCHIP\033[0m:     Error processing command: {command}")
            print(e)

        except asyncio.exceptions.CancelledError:
            break

def generate_hash(node_id, unique_id, endpoint):
    combined = f"{node_id}-{unique_id}-{endpoint}"
    return hashlib.sha256(combined.encode()).hexdigest()

async def get_basic_info_over_matter(node_id, attribute):
    command = f"basicinformation read {attribute} {node_id} 0"
    await run_chip_tool_command(command)
    while True:
        json_str = await response_queue.get()
        json_data = json.loads(json_str)
        node = json_data["ReportDataMessage"]["AttributeReportIBs"][0]["AttributeReportIB"]["AttributeDataIB"]["AttributePathIB"]["NodeID"]

        if node_id == node:
            value = json_data["ReportDataMessage"]["AttributeReportIBs"][0]["AttributeReportIB"]["AttributeDataIB"]["Data"]
            break
        else:
            continue
    return value

async def get_endpoint_list_over_matter(node_id):
    command = f"descriptor read parts-list {node_id} 0"
    await run_chip_tool_command(command)
    while True:
        json_str = await response_queue.get()
        json_data = json.loads(json_str)
        node = json_data["ReportDataMessage"]["AttributeReportIBs"][0]["AttributeReportIB"]["AttributeDataIB"]["AttributePathIB"]["NodeID"]

        if node_id == node:
            endpoints = json_data["ReportDataMessage"]["AttributeReportIBs"][0]["AttributeReportIB"]["AttributeDataIB"]["Data"]
            break
        else:
            continue
    return endpoints

async def get_devicetypes_over_matter(node_id, endpoint):
    command = f"descriptor read device-type-list {node_id} {endpoint}"
    await run_chip_tool_command(command)
    while True:
        json_str = await response_queue.get()
        json_data = json.loads(json_str)

        node = json_data["ReportDataMessage"]["AttributeReportIBs"][0]["AttributeReportIB"]["AttributeDataIB"]["AttributePathIB"]["NodeID"]
        if node_id == node:
            devicetypes = json_data["ReportDataMessage"]["AttributeReportIBs"][0]["AttributeReportIB"]["AttributeDataIB"]["Data"][0]
            break
        else:
            continue
    return devicetypes

async def register_device_to_database():
    print("\033[1;34mCHIP\033[0m:     Registering device to database...")
    node_id = get_new_node_id_from_database()
    unique_id = await get_basic_info_over_matter(node_id, "unique-id")
    print(f"\033[1;34mCHIP\033[0m:     Registering device to database: {node_id}, {unique_id}")
    vendor_name = await get_basic_info_over_matter(node_id, "vendor-name")
    print(f"\033[1;34mCHIP\033[0m:     Registering device to database: {node_id}, {unique_id}, {vendor_name}")
    # product_name = await get_basic_info_over_matter(node_id, "product-name")
    # device_name = f"{vendor_name}-{product_name}"
    insert_unique_id_to_database(node_id, vendor_name, unique_id)
    endpoints = await get_endpoint_list_over_matter(node_id)

    for endpoint in endpoints:
        topic_id = generate_hash(node_id, unique_id, endpoint)
        devicetypes = await get_devicetypes_over_matter(node_id, endpoint)
        print(devicetypes)
        devicetype = int(devicetypes.get("0x0"))
        insert_device_to_database(node_id, endpoint, devicetype, topic_id)

async def lifespan(app: FastAPI):
    print("\033[1;34mCHIP\033[0m:     Starting chip-tool REPL...")
    global chip_process
    global chip_tool_output
    global tasks

    parse_clusters_info(cluster_xml)
    from matter_xml_parser import all_clusters
    chip_tool_output = ""
    chip_process = await run_chip_tool()

    mqtt_client.connect(MQTT_BROKER_URL, port=9001, keepalive=60)
    mqtt_client.loop_start()

    create_homie_devices(mqtt_client)

    tasks = [
        asyncio.create_task(process_requests()),
        asyncio.create_task(read_repl_output()),
        asyncio.create_task(parse_subscribe_chip_tool_output())
    ]

    await subscribe_devices()
    print("\033[1;34mCHIP\033[0m:     chip-tool REPL started.")

    yield

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
    if "pairing" in request.command:
        request.command = request.command + f" --paa-trust-store-path {paa_root_cert}"
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

async def run_chip_tool():
    process = await asyncio.create_subprocess_exec(
        CHIP_TOOL_PATH, "interactive", "start", "--storage-directory", COMMISSIONING_DIR,
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

grammar = """
    statement: key "=" brackets
    brackets: "{" elements "}"
    array: "[" elements "]"
    elements: (element | array | brackets)*
    element: key "=" value | number code
    value: number | string | brackets | array | number code | string code
    code: "(" string ")" | "(" description ")"
    key: /[a-zA-Z_][a-zA-Z0-9_]*/ | /0x[0-9a-fA-F_]+/
    number: /0x[0-9a-fA-F_]+/ | /\d+/
    string: /[a-zA-Z0-9]+/
    description: /([a-zA-Z0-9]+[ ]+)+[a-zA-Z0-9]+/
    %ignore " "
    %ignore /\t/
    %ignore /\\r?\\n/
"""

def delete_garbage(log):
    log = re.sub(r'\x1b\[[0-9;]*m', '', log)
    log = re.sub(r',', '', log)
    log = re.sub(r'"', '', log)
    row_lines = log.splitlines()
    lines = []
    formatted_lines = []
    parsed_json = ""
    node_id = ""
    for line in row_lines:
        line = line.strip()
        columns = line.split()
        if len(columns) >= 4 and any(columns[3:]):
            lines.append(line)

    for line in lines:
        columns = line.split()
        if "Received Command Response Status" in line or "Subscription established with SubscriptionID" in line:
            continue

        if "IM:ReportData" in line:
            match = re.search(r'from\s+\d+:(\w{16})', line)
            if match:
                node_id = match.group(1)
                if node_id and not node_id.startswith("0x"):
                    node_id = "0x" + node_id.lstrip("0")

        if "IM:InvokeCommandResponse" in line:
            match = re.search(r'from\s+\d+:(\w{16})', line)
            if match:
                node_id = match.group(1)
                if node_id and not node_id.startswith("0x"):
                    node_id = "0x" + node_id.lstrip("0")

        if (len(columns) >= 3 and columns[2] == '[DMG]' and (columns[3] == '[' or columns[3] == ']' or '{' in line or '}' in line or '=' in line or '(' in line or ')' in line)):
            if "Endpoint =" in line or "EndpointId =" in line:
                node_id_str = "NodeID = " + node_id
                formatted_lines.append(node_id_str.strip())
            formatted_lines.append(' '.join(columns[3:]))
    formatted_string = ' '.join(formatted_lines)
    return formatted_string

class TreeToJson(Transformer):
    def start(self, items):
        return {"start": items}

    def statement(self, items):
        return {items[0]: items[1]}

    def key(self, items):
        return str(items[0])

    def value(self, items):
        return items[0]

    def number(self, items):
        if items[0].startswith('0x'):
            return int(items[0], 16)
        else:
            return int(items[0])

    def string(self, items):
        return str(items[0])

    def brackets(self, items):
        if len(items) == 1 and isinstance(items[0], dict):
            return dict(items[0])
        return items

    def array(self, items):
        if len(items) == 1 and isinstance(items[0], list):
            return items[0]
        return items

    def code(self, items):
        return items[0]

    def element(self, items):
        key = items[0]
        value = items[1] if len(items) > 1 else None
        return key, value

    def description(self, items):
        return str(items[0])

    def elements(self, items):

        if len(items) == 1 and isinstance(items[0], list):
            return items[0]

        if len(items) == 1 and isinstance(items[0],dict):
            return items[0]

        if all(isinstance(item, tuple) and isinstance(item[0], int) and item[1] == "unsigned" for item in items):
            result = []
            result.extend(item[0] for item in items)
            return result

        result = {}
        if all(isinstance(item, tuple)for item in items):
            for item in items:
                result[item[0]] = item[1]
            return result

        for key, value in items:
            result[key] = value
        return result

def parse_chip_data(data):
    parser = Lark(grammar, start='statement', parser='lalr')
    tree = parser.parse(data)
    return tree

def print_tree_json(tree):
    parsed_json = json.dumps(TreeToJson().transform(tree), indent=4)
    print(parsed_json)

def extract_named_blocks(text):
    blocks = []
    stack = []
    current_block = ""
    recording = False
    key_start = None

    for i, char in enumerate(text):
        if char == '{':
            if not stack:
                key_match = re.search(r'(\w+)\s*=\s*$', text[:i].strip().splitlines()[-1])
                if key_match:
                    key_start = text.rfind(key_match.group(1), 0, i)
                    current_block = text[key_start:i]
                    recording = True
            stack.append('{')
            if recording:
                current_block += '{'
        elif char == '}':
            stack.pop()
            if recording:
                current_block += '}'
            if not stack and recording:
                blocks.append(current_block.strip())
                current_block = ""
                recording = False
        else:
            if recording:
                current_block += char
    return blocks