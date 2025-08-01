"""
ChipTool manager for Matterverse application.
Handles Matter CLI tool REPL process and command execution.
"""
import asyncio
import json
import re
from typing import Optional, Dict, Any, Callable
from dataclasses import dataclass
from datetime import datetime
from lark import Lark, Transformer

from logger import get_chip_logger


@dataclass
class ChipToolResponse:
    """Response from chip-tool command execution."""
    status: str
    command: str
    data: Optional[Dict[str, Any]] = None
    error_message: Optional[str] = None
    timestamp: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary."""
        return {
            "status": self.status,
            "command": self.command,
            "data": self.data,
            "error_message": self.error_message,
            "timestamp": datetime.now().isoformat()
        }


class ChipToolParser:
    """Parser for chip-tool output."""

    GRAMMAR = r"""
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

    def delete_garbage_from_output(self, log: str) -> str:
        """Format chip-tool log output."""
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

            # Skip lines with insufficient columns
            if len(columns) < 3:
                continue

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

                if len(columns) > 3:
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
                    # Safely extract the last line before current position
                    text_before = text[:i].strip()
                    if text_before:
                        lines_before = text_before.splitlines()
                        if lines_before:
                            last_line = lines_before[-1]
                            key_match = re.search(r'(\w+)\s*=\s*$', last_line)
                            if key_match:
                                key_start = text.rfind(key_match.group(1), 0, i)
                                current_block = text[key_start:i]
                                recording = True
                stack.append('{')
                if recording:
                    current_block += '{'
            elif char == '}':
                if stack:  # Check if stack is not empty before popping
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

    def __init__(self, chip_tool_path: str, commissioning_dir: str, paa_cert_path: str, config=None, database: Optional[Any] = None):
        """
        Initialize ChipTool manager.

        Args:
            chip_tool_path: Path to chip-tool executable
            commissioning_dir: Path to commissioning directory
            paa_cert_path: Path to PAA certificate directory
            config: Configuration object
            database: Database reference
        """
        self.chip_tool_path = chip_tool_path
        self.commissioning_dir = commissioning_dir
        self.paa_cert_path = paa_cert_path
        self.config = config
        self.logger = get_chip_logger()
        self.database = database

        self._process: Optional[asyncio.subprocess.Process] = None
        self._output_buffer = ""
        self._request_queue = asyncio.Queue()
        self._response_queue = asyncio.Queue()
        self._parsed_queue = asyncio.Queue()

        # Improved command management
        self._pending_commands: Dict[str, Dict[str, Any]] = {}  # コマンド情報を保存
        self._command_sequence = 0  # シーケンス番号

        # Backward compatibility (deprecated)
        self._pending_requests: Dict[str, asyncio.Future] = {}
        self._command_timeouts: Dict[str, float] = {}
        self._current_command_id: Optional[str] = None
        self._current_command: Optional[str] = None

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
                asyncio.create_task(self._handle_parsed_data()),
                asyncio.create_task(self._timeout_monitor())
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

    async def execute_command(self, command: str, timeout: float = 30.0) -> ChipToolResponse:
        """
        Execute command and wait for parsed response.

        Args:
            command: Command to execute
            timeout: Command timeout in seconds

        Returns:
            ChipToolResponse with parsed data
        """
        self.logger.info(f"Executing command: {command}")

        # ユニークなコマンドIDを生成
        self._command_sequence += 1
        command_id = f"cmd_{self._command_sequence}_{int(asyncio.get_event_loop().time() * 1000)}"

        future = asyncio.get_event_loop().create_future()

        # コマンド情報を保存
        self._pending_commands[command_id] = {
            "command": command,
            "future": future,
            "timestamp": asyncio.get_event_loop().time(),
            "timeout": timeout
        }

        try:
            # Add command to queue
            await self._request_queue.put((command_id, command, future))

            # Wait for result with timeout
            result = await asyncio.wait_for(future, timeout=timeout)
            return result

        except asyncio.TimeoutError:
            # Handle timeout
            self.logger.error(f"Command timeout: {command}")
            return ChipToolResponse(
                status="timeout",
                command=command,
                error_message=f"Command timed out after {timeout} seconds"
            )
        finally:
            # Cleanup
            self._pending_commands.pop(command_id, None)
            self._pending_requests.pop(command_id, None)
            self._command_timeouts.pop(command_id, None)

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
        """Process command requests sequentially."""
        while True:
            try:
                command_id, command, future = await self._request_queue.get()

                if self._process and self._process.stdin:
                    # コマンドを逐次実行
                    command_line = f"{command}\n"
                    self._process.stdin.write(command_line.encode())
                    await self._process.stdin.drain()

                    # Store command ID for response matching
                    self._current_command_id = command_id
                    self._current_command = command

                    self.logger.info(f"[COMMAND_SENT] ID: {command_id}, Command: {command}")

                    # 短い遅延を追加して出力の分離を改善
                    await asyncio.sleep(0.1)

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error processing request: {e}")

                # エラー時の処理
                if command_id in self._pending_commands:
                    error_response = ChipToolResponse(
                        status="error",
                        command=command,
                        error_message=str(e)
                    )
                    future = self._pending_commands[command_id]["future"]
                    if not future.done():
                        future.set_result(error_response)

    async def _parse_output(self):
        """Parse chip-tool output and set future results."""
        self.logger.info("Start parsing chip-tool output")

        while True:
            try:
                await asyncio.sleep(0.001)

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
                    buf = self._output_buffer
                    self._output_buffer = ""

                    try:
                        cleaned_output = self.parser.delete_garbage_from_output(buf)
                        if cleaned_output:
                            blocks = self.parser.extract_named_blocks(cleaned_output)

                            for block in blocks:
                                try:
                                    parsed_data = self.parser.parse_chip_data(block)
                                    if parsed_data:
                                        matching_command_id = self._find_matching_command(parsed_data, buf)

                                        if matching_command_id and matching_command_id in self._pending_commands:
                                            command_info = self._pending_commands[matching_command_id]

                                            response = ChipToolResponse(
                                                status="success",
                                                command=command_info["command"],
                                                data=parsed_data,
                                            )

                                            future = command_info["future"]
                                            if not future.done():
                                                future.set_result(response)
                                        else:
                                            # フォールバック：最も古い待機中のコマンドに応答を割り当て
                                            fallback_cmd_id = self._get_oldest_pending_command()
                                            if fallback_cmd_id and fallback_cmd_id in self._pending_commands:
                                                command_info = self._pending_commands[fallback_cmd_id]

                                                response = ChipToolResponse(
                                                    status="success",
                                                    command=command_info["command"],
                                                    data=parsed_data,
                                                )

                                                future = command_info["future"]
                                                if not future.done():
                                                    future.set_result(response)
                                                    self.logger.warning(f"[FALLBACK] Assigned response to oldest command: {fallback_cmd_id}")

                                        # 既存の処理も継続
                                        parsed_json_str = json.dumps(parsed_data, indent=4)
                                        parsed_json = json.loads(parsed_json_str)
                                        await self._response_queue.put(parsed_json_str)
                                        await self._parsed_queue.put(parsed_json_str)

                                        if self.database:
                                            self.database.update_attribute(parsed_json_str)

                                        self.logger.info(f"Parsed data: {parsed_json_str}")

                                except Exception as parse_error:
                                    self.logger.warning(f"Error parsing block: {parse_error}")

                                    # Set error response for future
                                    command_id = self._current_command_id
                                    if command_id and command_id in self._pending_commands:
                                        command_info = self._pending_commands[command_id]
                                        error_response = ChipToolResponse(
                                            status="error",
                                            command=command_info["command"],
                                            error_message=f"Parse error: {parse_error}",
                                        )
                                        future = command_info["future"]
                                        if not future.done():
                                            future.set_result(error_response)
                                    continue

                    except Exception as clean_error:
                        self.logger.warning(f"Error cleaning output: {clean_error}")

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

    def _find_matching_command(self, parsed_data: Dict[str, Any], raw_output: str) -> Optional[str]:
        """
        Find the matching command for parsed data.

        Args:
            parsed_data: Parsed JSON data
            raw_output: Raw chip-tool output

        Returns:
            Matching command ID or None
        """
        # データからNodeID、Endpoint、Clusterを抽出
        try:
            report_data = parsed_data.get("ReportDataMessage", {})
            attr_reports = report_data.get("AttributeReportIBs", [])

            if attr_reports:
                attr_report = attr_reports[0].get("AttributeReportIB", {})
                attr_data = attr_report.get("AttributeDataIB", {})
                attr_path = attr_data.get("AttributePathIB", {})

                node_id = attr_path.get("NodeID")
                endpoint = attr_path.get("Endpoint")
                cluster = attr_path.get("Cluster")
                attribute = attr_path.get("Attribute")

                self.logger.debug(f"[MATCHING] Response data: NodeID={node_id}, Endpoint={endpoint}, Cluster={cluster}, Attribute={attribute}")

                # 最も古い待機中のコマンドから順にマッチング
                candidates = []
                current_time = asyncio.get_event_loop().time()

                for cmd_id, cmd_info in self._pending_commands.items():
                    if cmd_info["future"].done():
                        continue

                    # タイムアウトチェック
                    if current_time - cmd_info["timestamp"] > cmd_info["timeout"]:
                        # タイムアウトしたコマンドを処理
                        timeout_response = ChipToolResponse(
                            status="timeout",
                            command=cmd_info["command"],
                            error_message=f"Command timed out after {cmd_info['timeout']} seconds"
                        )
                        cmd_info["future"].set_result(timeout_response)
                        self.logger.warning(f"[TIMEOUT] Command {cmd_id}: {cmd_info['command']}")
                        continue

                    # コマンドと応答データのマッチング
                    command = cmd_info["command"]
                    if self._command_matches_data(command, node_id, endpoint, cluster, attribute):
                        candidates.append((cmd_info["timestamp"], cmd_id))
                        self.logger.debug(f"[MATCH_CANDIDATE] {cmd_id}: {command}")

                # 最も古いコマンドを選択
                if candidates:
                    candidates.sort(key=lambda x: x[0])
                    selected_cmd_id = candidates[0][1]
                    self.logger.info(f"[MATCH_SELECTED] {selected_cmd_id}: {self._pending_commands[selected_cmd_id]['command']}")
                    return selected_cmd_id
                else:
                    self.logger.warning(f"[NO_MATCH] No matching command found for response data")

        except Exception as e:
            self.logger.error(f"Error finding matching command: {e}")

        return None

    def _get_oldest_pending_command(self) -> Optional[str]:
        """
        Get the oldest pending command ID.

        Returns:
            Oldest pending command ID or None
        """
        oldest_cmd_id = None
        oldest_timestamp = float('inf')

        for cmd_id, cmd_info in self._pending_commands.items():
            if not cmd_info["future"].done() and cmd_info["timestamp"] < oldest_timestamp:
                oldest_timestamp = cmd_info["timestamp"]
                oldest_cmd_id = cmd_id

        return oldest_cmd_id

    def _command_matches_data(self, command: str, node_id: int, endpoint: int,
                            cluster: int, attribute: int) -> bool:
        """
        Check if command matches the response data.

        Args:
            command: Original command string
            node_id: Response node ID
            endpoint: Response endpoint
            cluster: Response cluster
            attribute: Response attribute

        Returns:
            True if command matches data
        """
        try:
            # コマンドからパラメータを抽出
            parts = command.split()
            self.logger.debug(f"[COMMAND_MATCH] Checking command: {command}")
            self.logger.debug(f"[COMMAND_MATCH] Parts: {parts}")

            # 基本的なマッチング：node_idとendpointをチェック
            if len(parts) >= 4:
                cmd_node_id = int(parts[-2]) if parts[-2].isdigit() else None
                cmd_endpoint = int(parts[-1]) if parts[-1].isdigit() else None

                self.logger.debug(f"[COMMAND_MATCH] Command params: NodeID={cmd_node_id}, Endpoint={cmd_endpoint}")
                self.logger.debug(f"[COMMAND_MATCH] Response params: NodeID={node_id}, Endpoint={endpoint}")

                if cmd_node_id == node_id and cmd_endpoint == endpoint:
                    # クラスターマッチング（追加チェック）
                    cluster_name = parts[0].lower() if parts else ""

                    # OnOffクラスター (cluster ID 6) の場合
                    if cluster_name == "onoff" and cluster == 6:
                        self.logger.debug(f"[COMMAND_MATCH] OnOff cluster match")
                        return True

                    # LevelControlクラスター (cluster ID 8) の場合
                    elif cluster_name == "levelcontrol" and cluster == 8:
                        self.logger.debug(f"[COMMAND_MATCH] LevelControl cluster match")
                        return True

                    # その他のクラスターも基本的にマッチとみなす
                    elif cmd_node_id == node_id and cmd_endpoint == endpoint:
                        self.logger.debug(f"[COMMAND_MATCH] Basic node/endpoint match")
                        return True

            self.logger.debug(f"[COMMAND_MATCH] No match for command: {command}")

        except Exception as e:
            self.logger.debug(f"Error matching command: {e}")

        return False

    async def _timeout_monitor(self):
        """Monitor and handle command timeouts."""
        while True:
            try:
                await asyncio.sleep(1.0)  # 1秒ごとにチェック

                current_time = asyncio.get_event_loop().time()
                expired_commands = []

                for cmd_id, cmd_info in self._pending_commands.items():
                    if cmd_info["future"].done():
                        continue

                    if current_time - cmd_info["timestamp"] > cmd_info["timeout"]:
                        expired_commands.append(cmd_id)

                # タイムアウトしたコマンドを処理
                for cmd_id in expired_commands:
                    if cmd_id in self._pending_commands:
                        cmd_info = self._pending_commands[cmd_id]
                        timeout_response = ChipToolResponse(
                            status="timeout",
                            command=cmd_info["command"],
                            error_message=f"Command timed out after {cmd_info['timeout']} seconds"
                        )

                        future = cmd_info["future"]
                        if not future.done():
                            future.set_result(timeout_response)

                        self.logger.warning(f"Command timed out: {cmd_id} - {cmd_info['command']}")

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error in timeout monitor: {e}")


    async def get_cluster_list(self, node_id: int, endpoint: int) -> list:
        """
        Get cluster list for a specific endpoint.

        Args:
            node_id: Node ID
            endpoint: Endpoint ID

        Returns:
            List of clusters
        """
        command = f"descriptor read server-list {node_id} {endpoint}"
        response = await self.execute_command(command)

        if response.status != "success":
            self.logger.error(f"Failed to get cluster list: {response.error_message}")
            return []

        # Extract data from response
        data = response.data
        if not data:
            return []

        try:
            # Navigate through the parsed data structure
            report_data = data.get("ReportDataMessage", {})
            attr_reports = report_data.get("AttributeReportIBs", [])

            if attr_reports:
                attr_report = attr_reports[0].get("AttributeReportIB", {})
                attr_data = attr_report.get("AttributeDataIB", {})
                attr_path = attr_data.get("AttributePathIB", {})

                response_node_id = attr_path.get("NodeID")
                response_endpoint = attr_path.get("Endpoint")

                if response_node_id == node_id and response_endpoint == endpoint:
                    clusters = []
                    for cluster in attr_data.get("Data", []):
                        clusters.append(int(cluster))
                    return clusters

        except Exception as e:
            self.logger.error(f"Error extracting cluster data: {e}")

        return []

    async def get_attribute_list(self, node_id: int, endpoint: int, cluster_name: str) -> list:
        """
        Get attribute list for a specific cluster.

        Args:
            node_id: Node ID
            endpoint: Endpoint ID
            cluster_name: Cluster name

        Returns:
            List of attributes
        """
        cluster_name = ''.join(cluster_name.split()).replace('/', '').lower()
        command = f"{cluster_name} read attribute-list {node_id} {endpoint}"
        response = await self.execute_command(command)

        if response.status != "success":
            self.logger.error(f"Failed to get attribute list: {response.error_message}")
            return []

        # Extract data from response
        data = response.data
        if not data:
            return []

        try:
            # Navigate through the parsed data structure
            report_data = data.get("ReportDataMessage", {})
            attr_reports = report_data.get("AttributeReportIBs", [])

            if attr_reports:
                attr_report = attr_reports[0].get("AttributeReportIB", {})
                attr_data = attr_report.get("AttributeDataIB", {})
                attr_path = attr_data.get("AttributePathIB", {})

                response_node_id = attr_path.get("NodeID")
                response_endpoint = attr_path.get("Endpoint")

                if response_node_id == node_id and response_endpoint == endpoint:
                    attributes = []
                    for attribute in attr_data.get("Data", []):
                        attributes.append(int(attribute))
                    return attributes

        except Exception as e:
            self.logger.error(f"Error extracting attribute data: {e}")

        return []


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
        response = await self.execute_command(command)

        if response.status != "success":
            self.logger.error(f"Failed to get basic info: {response.error_message}")
            return None

        # Extract data from response
        data = response.data
        if not data:
            return None

        try:
            # Navigate through the parsed data structure
            report_data = data.get("ReportDataMessage", {})
            attr_reports = report_data.get("AttributeReportIBs", [])

            if attr_reports:
                attr_report = attr_reports[0].get("AttributeReportIB", {})
                attr_data = attr_report.get("AttributeDataIB", {})
                attr_path = attr_data.get("AttributePathIB", {})

                if attr_path.get("NodeID") == node_id:
                    return str(attr_data.get("Data", ""))

        except Exception as e:
            self.logger.error(f"Error extracting basic info data: {e}")

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
        response = await self.execute_command(command)

        if response.status != "success":
            self.logger.error(f"Failed to get endpoint list: {response.error_message}")
            return []

        # Extract data from response
        data = response.data
        if not data:
            return []

        try:
            # Navigate through the parsed data structure
            report_data = data.get("ReportDataMessage", {})
            attr_reports = report_data.get("AttributeReportIBs", [])

            if attr_reports:
                attr_report = attr_reports[0].get("AttributeReportIB", {})
                attr_data = attr_report.get("AttributeDataIB", {})
                data_array = attr_data.get("Data", [])
                attr_path = attr_data.get("AttributePathIB", {})

                if attr_path.get("NodeID") == node_id:
                    return [int(endpoint) for endpoint in data_array]

        except Exception as e:
            self.logger.error(f"Error extracting endpoint data: {e}")

        return []

    async def get_device_types(self, node_id: int, endpoint: int) -> list:
        """
        Get device types from endpoint.

        Args:
            node_id: Node ID
            endpoint: Endpoint ID

        Returns:
            List of device types
        """
        command = f"descriptor read device-type-list {node_id} {endpoint}"
        response = await self.execute_command(command)

        if response.status != "success":
            self.logger.error(f"Failed to get device types: {response.error_message}")
            return []

        # Extract data from response
        data = response.data
        if not data:
            return []

        try:
            # Navigate through the parsed data structure
            report_data = data.get("ReportDataMessage", {})
            attr_reports = report_data.get("AttributeReportIBs", [])

            if attr_reports:
                attr_report = attr_reports[0].get("AttributeReportIB", {})
                attr_data = attr_report.get("AttributeDataIB", {})
                attr_path = attr_data.get("AttributePathIB", {})

                if attr_path.get("NodeID") == node_id:
                    return attr_data.get("Data", [])

        except Exception as e:
            self.logger.error(f"Error extracting device type data: {e}")

        return []
