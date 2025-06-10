from lark import Lark, Transformer
import json
import re

grammar = """
    statement: key "=" brackets
    brackets: "{" elements "}"
    array: "[" elements "]"
    elements: (element | array | brackets)*
    element: key "=" value | number | string | quotedstr
    value: number | string | brackets | array | quotedstr
    key: /[a-zA-Z_][a-zA-Z0-9_]*/ | /0x[0-9a-fA-F_]+/
    number: /0x[0-9a-fA-F_]+/ | /\d+/
    string: /[a-zA-Z0-9]+/ | /[a-zA-Z0-9_]+/
    quotedstr: /"[^"]*"/
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
    node_id = ""
    for line in row_lines:
        line = line.strip()
        columns = line.split()
        if len(columns) >= 4 and any(columns[3:]):
            lines.append(line)

    for line in lines:
        columns = line.split()
        if "Received Command Response Status" in line or "Subscription established with SubscriptionID" in line or "Received Command Response Data" in line:
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
                if node_id:
                    node_id_str = "NodeID = " + node_id
                else:
                    node_id_str = "NodeID = UNKNOWN"
                formatted_lines.append(node_id_str.strip())
            formatted_lines.append(' '.join(columns[3:]))
    formatted_string = ' '.join(formatted_lines)
    formatted_string = re.sub(r'\(.*?\)', '', formatted_string)
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

    def quotedstr(self, items):
        return str(items[0][1:-1])

    def brackets(self, items):
        if len(items) == 1 and isinstance(items[0], dict):
            return dict(items[0])
        return items

    def array(self, items):
        if len(items) == 1 and isinstance(items[0], list):
            return items[0]
        return items

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

        if all(isinstance(item, tuple) and item[1] == None for item in items):
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