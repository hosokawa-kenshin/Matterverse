"""
ChipTool manager for Matterverse application.
Handles Matter CLI tool execution with process separation approach.
Each command request runs in a separate chip-tool process for complete isolation.
"""
import asyncio
import json
import re
import time
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


class ProcessBasedChipToolManager:
    """
    Process-separation based ChipTool manager.
    Each command runs in a separate chip-tool process for complete isolation.
    """

    def __init__(self, chip_tool_path: str, commissioning_dir: str, paa_cert_path: str,
                 max_concurrent_processes: int = 10, database: Optional[Any] = None,
                 data_model: Optional[Any] = None):
        """
        Initialize ProcessBased ChipTool manager.

        Args:
            chip_tool_path: Path to chip-tool executable
            commissioning_dir: Path to commissioning directory
            paa_cert_path: Path to PAA certificate directory
            max_concurrent_processes: Maximum number of concurrent processes
            database: Database reference
            data_model: Data model reference
        """
        self.chip_tool_path = chip_tool_path
        self.commissioning_dir = commissioning_dir
        self.paa_cert_path = paa_cert_path
        self.logger = get_chip_logger()
        self.database = database
        self.data_model = data_model

        # Process management
        self.max_concurrent = max_concurrent_processes
        self.active_processes: Dict[str, asyncio.subprocess.Process] = {}
        self.semaphore = asyncio.Semaphore(max_concurrent_processes)
        self.process_sequence = 0

        # Parser for output processing
        self.parser = ChipToolParser()

    async def start(self):
        """
        Start manager (no persistent process needed in separation approach).
        """
        self.logger.info("ProcessBasedChipToolManager started - no persistent process required")

    async def stop(self):
        """
        Stop manager and cleanup any remaining processes.
        """
        # Terminate any remaining active processes
        for process_id, process in list(self.active_processes.items()):
            try:
                if process.returncode is None:  # Process still running
                    process.terminate()
                    await asyncio.wait_for(process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                process.kill()
                await process.wait()
            except Exception as e:
                self.logger.warning(f"Error stopping process {process_id}: {e}")
            finally:
                self.active_processes.pop(process_id, None)

        self.logger.info("ProcessBasedChipToolManager stopped")

    def set_parsed_data_callback(self, callback: Callable):
        """Set callback for parsed data (compatibility)."""
        # Note: In process separation approach, callback is called per command
        self._on_parsed_data = callback

    async def execute_command(self, command: str, timeout: float = 30.0) -> ChipToolResponse:
        """
        Execute command in a new chip-tool process.

        Args:
            command: Command to execute
            timeout: Command timeout in seconds

        Returns:
            ChipToolResponse with parsed data
        """
        self.logger.info(f"Executing command in new process: {command}")

        # Acquire semaphore to limit concurrent processes
        async with self.semaphore:
            return await self._execute_in_new_process(command, timeout)

    async def _execute_in_new_process(self, command: str, timeout: float) -> ChipToolResponse:
        """
        Execute command in a new chip-tool process.

        Args:
            command: Command to execute
            timeout: Process timeout in seconds

        Returns:
            ChipToolResponse with result
        """
        self.process_sequence += 1
        process_id = f"proc_{self.process_sequence}_{int(time.time() * 1000000)}"

        try:
            # Parse command arguments
            cmd_args = command.strip().split()

            # Build chip-tool command with required arguments
            chip_tool_cmd = [
                self.chip_tool_path,
                *cmd_args,
                "--paa-trust-store-path", self.paa_cert_path,
                "--storage-directory", self.commissioning_dir
            ]

            self.logger.debug(f"[{process_id}] Starting process: {' '.join(chip_tool_cmd)}")

            # Start new chip-tool process
            process = await asyncio.create_subprocess_exec(
                *chip_tool_cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            # Register active process
            self.active_processes[process_id] = process

            # Wait for process completion with timeout
            try:
                stdout, stderr = await asyncio.wait_for(
                    process.communicate(), timeout=timeout
                )

                self.logger.debug(f"[{process_id}] Process completed with return code: {process.returncode}")

                # Parse output and generate response
                response = await self._parse_process_output(stdout, stderr, command, process_id)
                # Check for "Resource is busy" and retry if needed
                if response.error_message and "Resource is busy" in response.error_message:
                    self.logger.warning(f"[{process_id}] Resource busy detected")
                    max_retries = 3
                    retry_delay = 1.0

                    for retry_count in range(max_retries):
                        self.logger.warning(f"[{process_id}] Resource busy detected, retrying in {retry_delay}s (attempt {retry_count + 1}/{max_retries})")
                        await asyncio.sleep(retry_delay)

                        # Retry the command with a new process
                        try:
                            retry_process = await asyncio.create_subprocess_exec(
                                *chip_tool_cmd,
                                stdout=asyncio.subprocess.PIPE,
                                stderr=asyncio.subprocess.PIPE
                            )

                            retry_stdout, retry_stderr = await asyncio.wait_for(
                                retry_process.communicate(), timeout=timeout
                            )

                            retry_response = await self._parse_process_output(retry_stdout, retry_stderr, command, f"{process_id}_retry_{retry_count + 1}")

                            # If retry succeeded, use the retry response
                            if not (retry_response.error_message and "Resource is busy" in retry_response.error_message):
                                self.logger.info(f"[{process_id}] Retry succeeded after {retry_count + 1} attempts")
                                response = retry_response
                                break

                            # Increase delay for next retry
                            retry_delay *= 2

                        except asyncio.TimeoutError:
                            self.logger.error(f"[{process_id}] Retry timeout after {timeout} seconds")
                            continue
                        except Exception as retry_error:
                            self.logger.error(f"[{process_id}] Retry failed: {retry_error}")
                            continue
                    else:
                        self.logger.error(f"[{process_id}] All retries failed due to resource busy")
                # Update database if available
                if self.database and response.data:
                    try:
                        self.database.update_attribute(json.dumps(response.data))
                    except Exception as e:
                        self.logger.warning(f"Database update failed: {e}")

                return response

            except asyncio.TimeoutError:
                self.logger.error(f"[{process_id}] Process timeout after {timeout} seconds")
                process.terminate()
                try:
                    await asyncio.wait_for(process.wait(), timeout=5.0)
                except asyncio.TimeoutError:
                    process.kill()
                    await process.wait()

                return ChipToolResponse(
                    status="timeout",
                    command=command,
                    error_message=f"Process timed out after {timeout} seconds"
                )

        except Exception as e:
            self.logger.error(f"[{process_id}] Process execution failed: {e}")
            return ChipToolResponse(
                status="error",
                command=command,
                error_message=str(e)
            )

        finally:
            # Cleanup process from active list
            self.active_processes.pop(process_id, None)

    async def _parse_process_output(self, stdout: bytes, stderr: bytes,
                                  command: str, process_id: str) -> ChipToolResponse:
        """
        Parse chip-tool process output and generate response.

        Args:
            stdout: Standard output from process
            stderr: Standard error from process
            command: Original command
            process_id: Process identifier

        Returns:
            ChipToolResponse with parsed data
        """
        try:
            # Decode output
            stdout_str = stdout.decode('utf-8', errors='replace')
            stderr_str = stderr.decode('utf-8', errors='replace')

            self.logger.debug(f"[{process_id}] Raw stdout: {stdout_str[:500]}...")
            if stderr_str:
                self.logger.debug(f"[{process_id}] Raw stderr: {stderr_str[:500]}...")

            # Check for obvious errors in stderr
            if stderr_str and any(error in stderr_str.lower() for error in
                                ['error', 'failed', 'exception', 'segmentation fault']):
                return ChipToolResponse(
                    status="error",
                    command=command,
                    error_message=stderr_str.strip()
                )

            # Process stdout with parser
            if stdout_str:
                cleaned_output = self.parser.delete_garbage_from_output(stdout_str)
                if cleaned_output:
                    blocks = self.parser.extract_named_blocks(cleaned_output)

                    for block in blocks:
                        try:
                            parsed_data = self.parser.parse_chip_data(block)
                            if parsed_data:
                                # Format parsed data for response
                                formatted_data = self._format_parsed_data(parsed_data)

                                self.logger.info(f"[{process_id}] Successfully parsed data: {json.dumps(parsed_data, indent=2)}")

                                return ChipToolResponse(
                                    status="success",
                                    command=command,
                                    data=formatted_data
                                )

                        except Exception as parse_error:
                            self.logger.warning(f"[{process_id}] Parse error for block: {parse_error}")
                            continue

            # If no parseable data found, return raw output
            return ChipToolResponse(
                status="success",
                command=command,
                data={
                    "raw_output": stdout_str.strip(),
                    "note": "No structured data found, returning raw output"
                }
            )

        except Exception as e:
            self.logger.error(f"[{process_id}] Output parsing failed: {e}")
            return ChipToolResponse(
                status="error",
                command=command,
                error_message=f"Output parsing failed: {str(e)}"
            )

    def _format_parsed_data(self, parsed_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Format parsed data to the standard response format.

        Args:
            parsed_data: Raw parsed data from chip-tool

        Returns:
            Formatted data in standard format
        """
        try:
            if "InvokeResponseMessage" in parsed_data:
                invoke_response_data = parsed_data["InvokeResponseMessage"]
                invoke_response_ibs = invoke_response_data.get("InvokeResponseIBs", [])

                if invoke_response_ibs:
                    invoke_response_ib = invoke_response_ibs[0].get("InvokeResponseIB", {})
                    command_status_ib = invoke_response_ib.get("CommandStatusIB", {})
                    command_path_ib = command_status_ib.get("CommandPathIB", {})
                    status_ib = command_status_ib.get("StatusIB", {})

                    node_id = command_path_ib.get("NodeID")
                    endpoint = command_path_ib.get("EndpointId")
                    cluster_id = command_path_ib.get("ClusterId")
                    command_id = command_path_ib.get("CommandId")

                    cluster_name = None
                    command_name = None

                    if self.data_model:
                        try:
                            cluster_name = self.data_model.get_cluster_name_by_id(f"0x{int(cluster_id):04x}")
                            command_name = self.data_model.get_command_name_by_code(f"0x{int(cluster_id):04x}", f"0x{int(command_id):02x}")
                        except Exception as e:
                            self.logger.warning(f"Error getting cluster/command names: {e}")

                    return {
                        "node": node_id,
                        "endpoint": endpoint,
                        "cluster": cluster_name or f"Cluster_{cluster_id}",
                        "command": command_name or f"Command_{command_id}",
                    }

            if "ReportDataMessage" in parsed_data:
                report_data = parsed_data["ReportDataMessage"]
                attr_reports = report_data.get("AttributeReportIBs", [])

                if attr_reports:
                    attr_report = attr_reports[0].get("AttributeReportIB", {})
                    attr_data = attr_report.get("AttributeDataIB", {})
                    attr_path = attr_data.get("AttributePathIB", {})

                    node_id = attr_path.get("NodeID")
                    endpoint = attr_path.get("Endpoint")
                    cluster_id = attr_path.get("Cluster")
                    attribute_id = attr_path.get("Attribute")
                    value = attr_data.get("Data")

                    cluster_name = None
                    attribute_name = None

                    if self.data_model:
                        try:
                            cluster_name = self.data_model.get_cluster_name_by_id(f"0x{int(cluster_id):04x}")
                            attribute_name = self.data_model.get_attribute_name_by_code(f"0x{int(cluster_id):04x}", f"0x{int(attribute_id):04x}")
                        except Exception as e:
                            self.logger.warning(f"Error getting cluster/attribute names: {e}")

                    return {
                        "node": node_id,
                        "endpoint": endpoint,
                        "cluster": cluster_name or f"Cluster_{cluster_id}",
                        "attribute": attribute_name or f"Attribute_{attribute_id}",
                        "value": value
                    }

            # If not standard format, try to extract what we can
            return self._extract_basic_info(parsed_data)

        except Exception as e:
            self.logger.warning(f"Error formatting parsed data: {e}")
            # Return original data if formatting fails
            return parsed_data

    def _extract_basic_info(self, parsed_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract basic information from non-standard parsed data.

        Args:
            parsed_data: Raw parsed data

        Returns:
            Basic extracted information
        """
        # This is a fallback for data that doesn't match the standard ReportDataMessage format
        return {
            "raw_data": parsed_data
        }

    # Utility methods for common operations
    async def get_cluster_list(self, node_id: str) -> ChipToolResponse:
        """Get list of clusters for a node."""
        command = f"any read-by-id 0x001D 0 {node_id}"
        return await self.execute_command(command)

    async def get_attribute_list(self, node_id: str, endpoint: str, cluster: str) -> ChipToolResponse:
        """Get list of attributes for a cluster."""
        command = f"any read-by-id {cluster} {endpoint} {node_id}"
        return await self.execute_command(command)

    async def read_attribute(self, node_id: str, endpoint: str, cluster: str, attribute: str) -> ChipToolResponse:
        """Read specific attribute."""
        command = f"any read-by-id {cluster} {attribute} {endpoint} {node_id}"
        return await self.execute_command(command)

    async def write_attribute(self, node_id: str, endpoint: str, cluster: str, attribute: str, value: Any) -> ChipToolResponse:
        """Write specific attribute."""
        command = f"any write-by-id {cluster} {attribute} {endpoint} {node_id} {value}"
        return await self.execute_command(command)

    async def invoke_command(self, node_id: str, endpoint: str, cluster: str, command_id: str, *args) -> ChipToolResponse:
        """Invoke specific command."""
        command = f"any command-by-id {cluster} {command_id} {endpoint} {node_id}"
        if args:
            command += " " + " ".join(str(arg) for arg in args)
        return await self.execute_command(command)


# Legacy REPL-based class (deprecated - keeping for compatibility)
class ChipToolManager:

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

        self._command_sequence += 1
        command_id = f"cmd_{self._command_sequence}_{int(asyncio.get_event_loop().time() * 1000)}"

        future = asyncio.get_event_loop().create_future()

        self._pending_commands[command_id] = {
            "command": command,
            "future": future,
            "timestamp": asyncio.get_event_loop().time(),
            "timeout": timeout
        }

        try:
            await self._request_queue.put((command_id, command, future))

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
                    command_line = f"{command}\n"
                    self._process.stdin.write(command_line.encode())
                    await self._process.stdin.drain()

                    self._current_command_id = command_id
                    self._current_command = command

                    self.logger.info(f"[COMMAND_SENT] ID: {command_id}, Command: {command}")

                    await asyncio.sleep(0.1)

            except asyncio.CancelledError:
                break
            except Exception as e:
                self.logger.error(f"Error processing request: {e}")

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
                                        # Extract structured data and format it
                                        formatted_data = self._format_parsed_data(parsed_data)

                                        matching_command_id = self._find_matching_command(parsed_data, buf)

                                        if matching_command_id and matching_command_id in self._pending_commands:
                                            command_info = self._pending_commands[matching_command_id]

                                            response = ChipToolResponse(
                                                status="success",
                                                command=command_info["command"],
                                                data=formatted_data,
                                            )

                                            future = command_info["future"]
                                            if not future.done():
                                                future.set_result(response)
                                        else:
                                            fallback_cmd_id = self._get_oldest_pending_command()
                                            if fallback_cmd_id and fallback_cmd_id in self._pending_commands:
                                                command_info = self._pending_commands[fallback_cmd_id]

                                                response = ChipToolResponse(
                                                    status="success",
                                                    command=command_info["command"],
                                                    data=formatted_data,
                                                )

                                                future = command_info["future"]
                                                if not future.done():
                                                    future.set_result(response)
                                                    self.logger.warning(f"[FALLBACK] Assigned response to oldest command: {fallback_cmd_id}")

                                        parsed_json_str = json.dumps(parsed_data, indent=4)
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

                candidates = []
                current_time = asyncio.get_event_loop().time()

                for cmd_id, cmd_info in self._pending_commands.items():
                    if cmd_info["future"].done():
                        continue

                    if current_time - cmd_info["timestamp"] > cmd_info["timeout"]:
                        timeout_response = ChipToolResponse(
                            status="timeout",
                            command=cmd_info["command"],
                            error_message=f"Command timed out after {cmd_info['timeout']} seconds"
                        )
                        cmd_info["future"].set_result(timeout_response)
                        self.logger.warning(f"[TIMEOUT] Command {cmd_id}: {cmd_info['command']}")
                        continue

                    command = cmd_info["command"]
                    if self._command_matches_data(command, node_id, endpoint, cluster, attribute):
                        candidates.append((cmd_info["timestamp"], cmd_id))
                        self.logger.debug(f"[MATCH_CANDIDATE] {cmd_id}: {command}")

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

    def _format_parsed_data(self, parsed_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Format parsed data to the standard response format.

        Args:
            parsed_data: Raw parsed data from chip-tool

        Returns:
            Formatted data in standard format
        """
        try:
            if "InvokeResponseMessage" in parsed_data:
                invoke_response_data = parsed_data["InvokeResponseMessage"]
                invoke_response_ibs = invoke_response_data.get("InvokeResponseIBs", [])

                if invoke_response_ibs:
                    invoke_response_ib = invoke_response_ibs[0].get("InvokeResponseIB", {})
                    command_status_ib = invoke_response_ib.get("CommandStatusIB", {})
                    command_path_ib = command_status_ib.get("CommandPathIB", {})
                    status_ib = command_status_ib.get("StatusIB", {})

                    node_id = command_path_ib.get("NodeID")
                    endpoint = command_path_ib.get("EndpointId")
                    cluster_id = command_path_ib.get("ClusterId")
                    command_id = command_path_ib.get("CommandId")

                    cluster_name = None
                    command_name = None

                    if self.data_model:
                        try:
                            cluster_name = self.data_model.get_cluster_name_by_id(f"0x{int(cluster_id):04x}")
                            command_name = self.data_model.get_command_name_by_code(f"0x{int(cluster_id):04x}", f"0x{int(command_id):02x}")
                        except Exception as e:
                            self.logger.warning(f"Error getting cluster/command names: {e}")

                    return {
                        "node": node_id,
                        "endpoint": endpoint,
                        "cluster": cluster_name or f"Cluster_{cluster_id}",
                        "command": command_name or f"Command_{command_id}",
                    }

            if "ReportDataMessage" in parsed_data:
                report_data = parsed_data["ReportDataMessage"]
                attr_reports = report_data.get("AttributeReportIBs", [])

                if attr_reports:
                    attr_report = attr_reports[0].get("AttributeReportIB", {})
                    attr_data = attr_report.get("AttributeDataIB", {})
                    attr_path = attr_data.get("AttributePathIB", {})

                    node_id = attr_path.get("NodeID")
                    endpoint = attr_path.get("Endpoint")
                    cluster_id = attr_path.get("Cluster")
                    attribute_id = attr_path.get("Attribute")
                    value = attr_data.get("Data")

                    cluster_name = None
                    attribute_name = None

                    if self.data_model:
                        try:
                            cluster_name = self.data_model.get_cluster_name_by_id(f"0x{int(cluster_id):04x}")
                            attribute_name = self.data_model.get_attribute_name_by_code(f"0x{int(cluster_id):04x}", f"0x{int(attribute_id):04x}")
                        except Exception as e:
                            self.logger.warning(f"Error getting cluster/attribute names: {e}")

                    return {
                        "node": node_id,
                        "endpoint": endpoint,
                        "cluster": cluster_name or f"Cluster_{cluster_id}",
                        "attribute": attribute_name or f"Attribute_{attribute_id}",
                        "value": value
                    }

            # If not standard format, try to extract what we can
            return self._extract_basic_info(parsed_data)

        except Exception as e:
            self.logger.warning(f"Error formatting parsed data: {e}")
            # Return original data if formatting fails
            return parsed_data

    def _extract_basic_info(self, parsed_data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Extract basic information from non-standard parsed data.

        Args:
            parsed_data: Raw parsed data

        Returns:
            Basic extracted information
        """
        # This is a fallback for data that doesn't match the standard ReportDataMessage format
        return {
            "raw_data": parsed_data
        }

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
            parts = command.split()
            self.logger.debug(f"[COMMAND_MATCH] Checking command: {command}")
            self.logger.debug(f"[COMMAND_MATCH] Parts: {parts}")

            if len(parts) >= 4:
                cmd_node_id = int(parts[-2]) if parts[-2].isdigit() else None
                cmd_endpoint = int(parts[-1]) if parts[-1].isdigit() else None

                self.logger.debug(f"[COMMAND_MATCH] Command params: NodeID={cmd_node_id}, Endpoint={cmd_endpoint}")
                self.logger.debug(f"[COMMAND_MATCH] Response params: NodeID={node_id}, Endpoint={endpoint}")

                if cmd_node_id == node_id and cmd_endpoint == endpoint:
                    cluster_name = parts[0].lower() if parts else ""

                    if cluster_name == "onoff" and cluster == 6:
                        self.logger.debug(f"[COMMAND_MATCH] OnOff cluster match")
                        return True

                    elif cluster_name == "levelcontrol" and cluster == 8:
                        self.logger.debug(f"[COMMAND_MATCH] LevelControl cluster match")
                        return True

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
                await asyncio.sleep(1.0)
                current_time = asyncio.get_event_loop().time()
                expired_commands = []

                for cmd_id, cmd_info in self._pending_commands.items():
                    if cmd_info["future"].done():
                        continue

                    if current_time - cmd_info["timestamp"] > cmd_info["timeout"]:
                        expired_commands.append(cmd_id)

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
