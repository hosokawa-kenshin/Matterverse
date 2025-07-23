"""
ChipTool manager for Matterverse application.
Handles Matter CLI tool REPL process and command execution.
"""
import asyncio
import json
import re
from typing import Optional, Dict, Any, Callable
from lark import Lark, Transformer

from logger import get_chip_logger


class ChipToolParser:
    """Parser for chip-tool output."""
    
    GRAMMAR = """
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
    
    def __init__(self):
        """Initialize parser."""
        self.parser = Lark(self.GRAMMAR, start='statement', parser='lalr')
        self.transformer = TreeToJsonTransformer()
    
    def clean_log_output(self, log: str) -> str:
        """Clean and format chip-tool log output."""
        # Remove ANSI color codes
        log = re.sub(r'\x1b\[[0-9;]*m', '', log)
        log = re.sub(r',', '', log)
        
        row_lines = log.splitlines()
        lines = []
        formatted_lines = []
        node_id = ""
        
        # Filter meaningful lines
        for line in row_lines:
            line = line.strip()
            columns = line.split()
            if len(columns) >= 4 and any(columns[3:]):
                lines.append(line)
        
        # Process lines
        for line in lines:
            columns = line.split()
            
            # Skip certain message types
            skip_patterns = [
                "Received Command Response Status",
                "Subscription established with SubscriptionID", 
                "Received Command Response Data"
            ]
            if any(pattern in line for pattern in skip_patterns):
                continue
            
            # Extract node ID from IM messages
            if "IM:ReportData" in line or "IM:InvokeCommandResponse" in line:
                match = re.search(r'from\s+\d+:(\w{16})', line)
                if match:
                    node_id = match.group(1)
                    if node_id and not node_id.startswith("0x"):
                        node_id = "0x" + node_id.lstrip("0")
            
            # Format DMG messages
            dmg_indicators = ['[', ']', '{', '}', '=', '(', ')']
            if (len(columns) >= 3 and columns[2] == '[DMG]' and 
                any(indicator in line for indicator in dmg_indicators)):
                
                if "Endpoint =" in line or "EndpointId =" in line:
                    node_id_str = f"NodeID = {node_id}" if node_id else "NodeID = UNKNOWN"
                    formatted_lines.append(node_id_str.strip())
                
                formatted_lines.append(' '.join(columns[3:]))
        
        formatted_string = ' '.join(formatted_lines)
        # Remove content in parentheses
        formatted_string = re.sub(r'\(.*?\)', '', formatted_string)
        return formatted_string
    
    def extract_named_blocks(self, text: str) -> list:
        """Extract named blocks from text."""
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
    
    def parse_chip_data(self, data: str) -> Optional[Dict]:
        """Parse chip-tool data using grammar."""
        try:
            tree = self.parser.parse(data)
            return self.transformer.transform(tree)
        except Exception as e:
            return None


class TreeToJsonTransformer(Transformer):
    """Transformer to convert parse tree to JSON."""
    
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
        
        if len(items) == 1 and isinstance(items[0], dict):
            return items[0]
        
        if all(isinstance(item, tuple) and item[1] is None for item in items):
            result = []
            result.extend(item[0] for item in items)
            return result
        
        result = {}
        if all(isinstance(item, tuple) for item in items):
            for item in items:
                result[item[0]] = item[1]
            return result
        
        for key, value in items:
            result[key] = value
        return result


class ChipToolManager:
    """Manager for chip-tool REPL process and command execution."""
    
    def __init__(self, chip_tool_path: str, commissioning_dir: str, paa_cert_path: str):
        """
        Initialize ChipTool manager.
        
        Args:
            chip_tool_path: Path to chip-tool executable
            commissioning_dir: Path to commissioning directory
            paa_cert_path: Path to PAA certificate directory
        """
        self.chip_tool_path = chip_tool_path
        self.commissioning_dir = commissioning_dir
        self.paa_cert_path = paa_cert_path
        self.logger = get_chip_logger()
        
        self._process: Optional[asyncio.subprocess.Process] = None
        self._output_buffer = ""
        self._request_queue = asyncio.Queue()
        self._response_queue = asyncio.Queue()
        self._parsed_queue = asyncio.Queue()
        
        self.parser = ChipToolParser()
        self._tasks = []
        
        # Callbacks
        self._on_parsed_data: Optional[Callable] = None
    
    async def start(self):
        """Start chip-tool REPL process and background tasks."""
        try:
            self.logger.info("Starting chip-tool REPL...")
            
            self._process = await asyncio.create_subprocess_exec(
                self.chip_tool_path, "interactive", "start",
                "--paa-trust-store-path", self.paa_cert_path,
                "--storage-directory", self.commissioning_dir,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            # Start background tasks
            self._tasks = [
                asyncio.create_task(self._read_output()),
                asyncio.create_task(self._process_requests()),
                asyncio.create_task(self._parse_output()),
                asyncio.create_task(self._handle_parsed_data())
            ]
            
            self.logger.info("chip-tool REPL started")
            
        except Exception as e:
            self.logger.error(f"Failed to start chip-tool: {e}")
            raise
    
    async def stop(self):
        """Stop chip-tool process and cleanup."""
        if self._process:
            self._process.kill()
            await self._process.wait()
            self._process = None
        
        # Cancel background tasks
        for task in self._tasks:
            task.cancel()
        
        # Wait for tasks to complete
        await asyncio.gather(*self._tasks, return_exceptions=True)
        self._tasks.clear()
        
        self.logger.info("chip-tool REPL stopped")
    
    def set_parsed_data_callback(self, callback: Callable):
        """Set callback for parsed data."""
        self._on_parsed_data = callback
    
    async def execute_command(self, command: str) -> str:
        """
        Execute command and wait for response.
        
        Args:
            command: Command to execute
            
        Returns:
            Response from chip-tool
        """
        self.logger.info(f"Executing command: {command}")
        
        future = asyncio.get_event_loop().create_future()
        await self._request_queue.put((None, command, future))
        result = await future
        return result
    
    async def _read_output(self):
        """Read output from chip-tool process."""
        if not self._process:
            return
            
        while True:
            try:
                line = await self._process.stdout.readline()
                if not line:
                    break
                
                self._output_buffer += line.decode()
                await asyncio.sleep(0.01)
                
            except Exception as e:
                self.logger.error(f"Error reading output: {e}")
                break
    
    async def _process_requests(self):
        """Process command requests."""
        while True:
            try:
                websocket, command, future = await self._request_queue.get()
                
                if self._process and self._process.stdin:
                    command_line = f"{command}\n"
                    self._process.stdin.write(command_line.encode())
                    await self._process.stdin.drain()
                
                # Wait for response and set future result
                response = await self._response_queue.get()
                if future:
                    future.set_result(response)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error processing request: {e}")
    
    async def _parse_output(self):
        """Parse chip-tool output."""
        self.logger.info("Start parsing chip-tool output")
        
        while True:
            try:
                await asyncio.sleep(0.1)
                
                if not self._output_buffer:
                    continue
                
                # Check for specific output patterns
                skip_patterns = [
                    "[TOO] Endpoint: ",
                    "Received Command Response Status",
                    "Refresh LivenessCheckTime for",
                    "Subscription established with SubscriptionID",
                    "Received CommissioningComplete response"
                ]
                
                if any(pattern in self._output_buffer for pattern in skip_patterns):
                    self._output_buffer = ""
                    continue
                
                # Clean and parse output
                cleaned_output = self.parser.clean_log_output(self._output_buffer)
                if cleaned_output:
                    blocks = self.parser.extract_named_blocks(cleaned_output)
                    
                    for block in blocks:
                        parsed_data = self.parser.parse_chip_data(block)
                        if parsed_data:
                            parsed_json = json.dumps(parsed_data, indent=4)
                            await self._response_queue.put(parsed_json)
                            await self._parsed_queue.put(parsed_json)
                
                self._output_buffer = ""
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error parsing output: {e}")
    
    async def _handle_parsed_data(self):
        """Handle parsed data from chip-tool."""
        while True:
            try:
                parsed_json = await self._parsed_queue.get()
                
                if self._on_parsed_data:
                    await self._on_parsed_data(parsed_json)
                
            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error handling parsed data: {e}")
    
    async def get_basic_info(self, node_id: int, attribute: str) -> Optional[str]:
        """
        Get basic information attribute from device.
        
        Args:
            node_id: Node ID
            attribute: Attribute name
            
        Returns:
            Attribute value or None
        """
        command = f"basicinformation read {attribute} {node_id} 0"
        await self.execute_command(command)
        
        while True:
            json_str = await self._response_queue.get()
            json_data = json.loads(json_str)
            
            if ("ReportDataMessage" in json_str and 
                "AttributeReportIBs" in json_str):
                
                report_data = json_data.get("ReportDataMessage", {})
                attr_reports = report_data.get("AttributeReportIBs", [])
                
                if attr_reports:
                    attr_report = attr_reports[0].get("AttributeReportIB", {})
                    attr_data = attr_report.get("AttributeDataIB", {})
                    return str(attr_data.get("Data", ""))
            
            break
        
        return None
    
    async def get_endpoint_list(self, node_id: int) -> list:
        """
        Get endpoint list from device.
        
        Args:
            node_id: Node ID
            
        Returns:
            List of endpoints
        """
        command = f"descriptor read parts-list {node_id} 0"
        await self.execute_command(command)
        
        while True:
            json_str = await self._response_queue.get()
            json_data = json.loads(json_str)
            
            if ("ReportDataMessage" in json_str and 
                "AttributeReportIBs" in json_str):
                
                report_data = json_data.get("ReportDataMessage", {})
                attr_reports = report_data.get("AttributeReportIBs", [])
                
                if attr_reports:
                    attr_report = attr_reports[0].get("AttributeReportIB", {})
                    attr_data = attr_report.get("AttributeDataIB", {})
                    data = attr_data.get("Data", [])
                    return [int(endpoint) for endpoint in data]
            
            break
        
        return []
    
    async def get_device_types(self, node_id: int, endpoint: int) -> dict:
        """
        Get device types from endpoint.
        
        Args:
            node_id: Node ID
            endpoint: Endpoint ID
            
        Returns:
            Device types dictionary
        """
        command = f"descriptor read device-type-list {node_id} {endpoint}"
        await self.execute_command(command)
        
        while True:
            json_str = await self._response_queue.get()
            json_data = json.loads(json_str)
            
            if ("ReportDataMessage" in json_str and 
                "AttributeReportIBs" in json_str):
                
                report_data = json_data.get("ReportDataMessage", {})
                attr_reports = report_data.get("AttributeReportIBs", [])
                
                if attr_reports:
                    attr_report = attr_reports[0].get("AttributeReportIB", {})
                    attr_data = attr_report.get("AttributeDataIB", {})
                    return attr_data.get("Data", {})
            
            break
        
        return {}
