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

load_dotenv()
CHIP_TOOL_PATH = os.getenv('CHIP_TOOL_PATH', './chip-tool')
COMMISSIONING_DIR = os.getenv('COMMISSIONING_DIR', './commitioning_dir')

request_queue = asyncio.Queue()

import signal
class CommandRequest(BaseModel):
    command: str

async def handle_shutdown():
    print("Shutdown signal received. Stopping tasks...")
    for task in asyncio.all_tasks():
        task.cancel()
    await asyncio.sleep(1)
    print("All tasks cancelled. Exiting.")

def shutdown_handler():
    asyncio.create_task(handle_shutdown())

loop = asyncio.get_event_loop()
loop.add_signal_handler(signal.SIGINT, shutdown_handler)
loop.add_signal_handler(signal.SIGTERM, shutdown_handler)

async def parse_subscribe_chip_tool_output():
    global chip_tool_output
    while True:
        if "Refresh LivenessCheckTime for" in chip_tool_output:
            lines = chip_tool_output.splitlines()
            chip_tool_output = ""
            current_output = []
            for line in lines:
                if "Refresh LivenessCheckTime for" in line:
                    if current_output:
                        log = ''.join(current_output)
                        data = delete_garbage(log)
                        if data and data.strip():
                            tree = parse_chip_data(data)
                            parsed_json = TreeToJson().transform(tree)
                            print("Received data: ", parsed_json)
                            return parsed_json
                else:
                    current_output.append(line + '\n')
            current_output = []
            await asyncio.sleep(0.1)
        else:
            await asyncio.sleep(0.1)

async def parse_chip_tool_output():
    global chip_tool_output
    while True:
        if "Received Command Response Status" in chip_tool_output:
            lines = chip_tool_output.splitlines()
            chip_tool_output = ""
            current_output = []
            for line in lines:
                if "Received Command Response Status" in line:
                    if current_output:
                        log = ''.join(current_output)
                        data = delete_garbage(log)
                        if data and data.strip():
                            tree = parse_chip_data(data)
                            parsed_json = TreeToJson().transform(tree)
                            print("Received data: ", parsed_json)
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
            websocket, command = await request_queue.get()
            print(f"Processing command: {command}")
            chip_process.stdin.write(command.encode() + b'\n')
            await chip_process.stdin.drain()
            parsed_json = await parse_chip_tool_output()
            if websocket:
                await websocket.send_text(json.dumps(parsed_json))

        except Exception as e:
            print(f"Error processing command: {command}")
            print(e)

        except asyncio.exceptions.CancelledError:
            break

async def lifespan(app: FastAPI):
    print("Starting chip-tool REPL...")
    global chip_process
    global chip_tool_output
    chip_process = await run_chip_tool()
    chip_tool_output = ""

    tasks = [
        asyncio.create_task(process_requests()),
        asyncio.create_task(read_repl_output()),
        asyncio.create_task(parse_subscribe_chip_tool_output())
    ]
    print("chip-tool REPL started.")

    yield

    print("Stopping chip-tool REPL...")
    for task in tasks:
        task.cancel()
    chip_process.terminate()
    await asyncio.sleep(1)
    if chip_process.poll() is None:
        chip_process.kill()
    print("chip-tool REPL stopped.")

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.websocket("/ws")
async def run_chip_tool_command(websocket: WebSocket):
    await websocket.accept()
    try:
        while True:
            command = await websocket.receive_text()
            print(f"Received command: {command}")
            await request_queue.put((websocket, command))
    except WebSocketDisconnect:
        print("WebSocket disconnected")

@app.post("/command")
async def run_chip_tool_command(request: CommandRequest):
    print(f"received command: {request.command}")
    await request_queue.put((None, request.command))
    return {"status": "success"}

async def run_chip_tool():
    process = await asyncio.create_subprocess_exec(
        CHIP_TOOL_PATH, "interactive", "start", "--storage-directory", COMMISSIONING_DIR,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE
    )
    return process

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
    for line in row_lines:
        line = line.strip()
        columns = line.split()
        if len(columns) >= 4 and any(columns[3:]):
            lines.append(line)

    for line in lines:
        columns = line.split()
        if "Received Command Response Status" in line:
            continue
        if (len(columns) >= 3 and columns[2] == '[DMG]' and (columns[3] == '[' or columns[3] == ']' or '{' in line or '}' in line or '=' in line or '(' in line or ')' in line)):
            formatted_lines.append(columns[3:])

    formatted_string = ' '.join([' '.join(line) for line in formatted_lines])
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