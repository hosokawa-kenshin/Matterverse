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

class CommandRequest(BaseModel):
    command: str

request_queue = asyncio.Queue()

async def process_requests():
    global chip_process
    chip_process = run_chip_tool()
    while True:
        websocket, command = await request_queue.get()
        try:
            chip_process.stdin.write(command)
            chip_process.stdin.write('\n')
            chip_process.stdin.write('\n')
            chip_process.stdin.flush()
            output = []
            while True:
                line = chip_process.stdout.readline()
                if "Missing cluster or command set name" in line:
                    chip_process.stdout.flush()
                    break
                output.append(line)
            log = ''.join(output)
            data = delete_garbage(log)
            tree = parse_chip_data(data)
            parsed_json = TreeToJson().transform(tree)
            await websocket.send_text(json.dumps(parsed_json))
        except Exception as e:
            await websocket.send_text(json.dumps({"error": str(e)}))
        finally:
            request_queue.task_done()

async def lifespan(app: FastAPI):
    print("Starting chip-tool REPL...")
    asyncio.create_task(process_requests())
    yield
    chip_process.terminate()
    await asyncio.sleep(1)
    if chip_process.poll() is None:
        chip_process.kill()
    print ("Terminating chip-tool REPL...")

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

def run_chip_tool():
    process = subprocess.Popen(
        [CHIP_TOOL_PATH, "interactive", "start", "--storage-directory", COMMISSIONING_DIR],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
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

    formatted_string = '\n'.join([' '.join(line) for line in formatted_lines])
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

# def main():
#     process = run_chip_tool()
#     while True:
#         command = input("Enter command: ")
#         if command.lower() == 'exit':
#             break
#         log = run_chip_tool_command(process, command)
#         data = delete_garbage(log)
#         tree = parse_chip_data(data)
#         print_tree_json(tree)

# if __name__ == "__main__":
#     main()