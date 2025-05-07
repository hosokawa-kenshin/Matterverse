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

from mqtt import mqtt_client, publish_to_mqtt_broker

load_dotenv()
CHIP_TOOL_PATH = os.getenv('CHIP_TOOL_PATH', './chip-tool')
COMMISSIONING_DIR = os.getenv('COMMISSIONING_DIR', './commitioning_dir')

connected_clients = set()
request_queue = asyncio.Queue()


class CommandRequest(BaseModel):
    command: str

async def handle_shutdown():
    print("\033[1;34mCHIP:\033[0m     Shutdown signal received. Stopping tasks...")
    for task in asyncio.all_tasks():
        task.cancel()
    await asyncio.sleep(1)
    print("\033[1;34mCHIP:\033[0m     All tasks cancelled. Exiting.")

def shutdown_handler():
    asyncio.create_task(handle_shutdown())

loop = asyncio.get_event_loop()
loop.add_signal_handler(signal.SIGINT, shutdown_handler)
loop.add_signal_handler(signal.SIGTERM, shutdown_handler)

async def parse_subscribe_chip_tool_output():
    global chip_tool_output
    global connected_clients
    while True:
        if "Refresh LivenessCheckTime for" in chip_tool_output or "Subscription established with SubscriptionID" in chip_tool_output:
            lines = chip_tool_output.splitlines()
            chip_tool_output = ""
            current_output = []
            for line in lines:
                if "Refresh LivenessCheckTime for" in line or "Subscription established with SubscriptionID" in chip_tool_output:
                    if current_output:
                        log = ''.join(current_output)
                        data = delete_garbage(log)
                        if data and data.strip():
                            tree = parse_chip_data(data)
                            parsed_json = json.dumps(TreeToJson().transform(tree))
                            print("\033[1;34mCHIP:\033[0m     Received data: ", parsed_json)
                            await publish_to_all_websocket_clients(parsed_json)
                            publish_to_mqtt_broker(mqtt_client, "dt/matter/1/1/onoff/toggle", parsed_json)
                            break
                else:
                    current_output.append(line + '\n')
            current_output = []
            await asyncio.sleep(0.1)
        else:
            await asyncio.sleep(0.1)

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
                            print("\033[1;34mCHIP:\033[0m     Received data: ", parsed_json)
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
            print(f"\033[1;34mCHIP:\033[0m     Processing command: {command}")
            chip_process.stdin.write(command.encode() + b'\n')
            await chip_process.stdin.drain()
            parsed_json = await parse_chip_tool_output()
            if websocket:
                await websocket.send_text(json.dumps(parsed_json))
            elif future:
                future.set_result(parsed_json)

        except Exception as e:
            print(f"\033[1;34mCHIP:\033[0m     Error processing command: {command}")
            print(e)

        except asyncio.exceptions.CancelledError:
            break

async def lifespan(app: FastAPI):
    print("\033[1;34mCHIP:\033[0m     Starting chip-tool REPL...")
    global chip_process
    global chip_tool_output
    chip_tool_output = ""
    chip_process = await run_chip_tool()

    mqtt_client.connect("172.23.81.17", port=9001, keepalive=60)
    mqtt_client.loop_start()

    tasks = [
        asyncio.create_task(process_requests()),
        asyncio.create_task(read_repl_output()),
        asyncio.create_task(parse_subscribe_chip_tool_output())
    ]

    await run_chip_tool_subscribe_command("onoff subscribe on-off 10 100 1 1")

    print("\033[1;34mCHIP:\033[0m     chip-tool REPL started.")

    yield

    print("\033[1;34mCHIP:\033[0m     Stopping chip-tool REPL...")
    for task in tasks:
        task.cancel()
    chip_process.terminate()
    await asyncio.sleep(1)
    if chip_process.poll() is None:
        chip_process.kill()
    print("\033[1;34mCHIP:\033[0m     chip-tool REPL stopped.")
    mqtt_client.loop_stop()
    mqtt_client.disconnect()

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
async def run_chip_tool_command(websocket: WebSocket):
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
async def run_chip_tool_command(request: CommandRequest):
    print(f"\033[1;34mCHIP:\033[0m     received command: {request.command}")
    future = asyncio.get_event_loop().create_future()
    await request_queue.put((None, request.command, future))
    result = await future
    return result

async def run_chip_tool_subscribe_command(command):
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

grammar = """
    statement: key "=" brackets
    brackets: "{" elements "}"
    array: "[" elements "]"
    elements: (element | array | brackets)*
    element: key "=" value | number code
    value: number | string | brackets | array | number code
    code: "(" string ")"
    key: /[a-zA-Z_][a-zA-Z0-9_]*/
    number: /0x[0-9a-fA-F_]+/ | /\d+/
    string: /[a-zA-Z]+/
    %ignore " "
    %ignore /\t/
    %ignore /\\r?\\n/
"""

def delete_garbage(log):
    log = re.sub(r'\x1b\[[0-9;]*m', '', log)
    log = re.sub(r',', '', log)
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

        if (len(columns) >= 3 and columns[2] == '[DMG]' and (columns[3] == '[' or columns[3] == ']' or '{' in line or '}' in line or '=' in line or '(' in line or ')' in line)):
            if "Endpoint =" in line:
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

    def elements(self, items):
        if len(items) == 1 and isinstance(items[0], list):
            return items[0]

        if all(isinstance(item, tuple) and isinstance(item[0], int) and item[1] == "unsigned" for item in items):
            result = []
            result.extend(item[0] for item in items)
            return result

        result = {}
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