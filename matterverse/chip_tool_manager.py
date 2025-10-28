"""
ChipTool manager for Matterverse application.
Handles Matter CLI tool execution with process separation approach.
Each command request runs in a separate chip-tool process for complete isolation.
"""
import asyncio
import json
import os
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
                "Received Command Response Data",
                "SendReadRequest ReadClient",
                "MoveToState ReadClient",
                "All ReadHandler-s are clean",
                "data version filters provided"
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
                 max_concurrent_processes: int = 100, database: Optional[Any] = None,
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

        # Callback for parsed data
        self._parsed_data_callback = None

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
        """
        Set callback for parsed data.

        Args:
            callback: Async function to call when command result is parsed
        """
        self._parsed_data_callback = callback

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
                if command.startswith("pairing code") or command.startswith("pairing code-pairverifier"):
                    response = await self._parse_commissioning_output(stdout, stderr, command, process_id)
                else:
                    response = await self._parse_process_output(stdout, stderr, command, process_id)

                if (response.data and
                    isinstance(response.data, dict) and
                    response.data.get('raw_output') and
                    "Resource is busy" in response.data.get('raw_output', '')):
                    self.logger.warning(f"[{process_id}] Resource busy detected")
                    max_retries = 3
                    retry_delay = 0.05

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
                            if not (retry_response.data and
                                   isinstance(retry_response.data, dict) and
                                   retry_response.data.get('raw_output') and
                                   "Resource is busy" in retry_response.data.get('raw_output', '')):
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

                config_ini_path = os.path.join(self.commissioning_dir, "chip_tool_config.ini")
                if os.path.exists(config_ini_path):
                    try:
                        os.remove(config_ini_path)
                        self.logger.info(f"[{process_id}] Deleted chip_tool_config.ini to reset session state")
                    except Exception as e:
                        self.logger.warning(f"[{process_id}] Failed to delete chip_tool_config.ini: {e}")

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

    async def _parse_commissioning_output(self, stdout: bytes, stderr: bytes, command: str, process_id: str) -> ChipToolResponse:
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
                    formatted_datas = []
                    for block in blocks:
                        try:
                            parsed_data = self.parser.parse_chip_data(block)
                            if parsed_data:
                                # Format parsed data for response
                                formatted_data = self._format_parsed_data(parsed_data)
                                formatted_datas.append(formatted_data)
                                # formatted_datas.append(parsed_data)
                        except Exception as parse_error:
                            self.logger.warning(f"[{process_id}] Parse error for block: {parse_error}")
                            continue
                    return ChipToolResponse(
                        status="success",
                        command=command,
                        data=formatted_datas
                    )

            # If no parseable data found, return raw output
            return ChipToolResponse(
                status="success",
                command=command,
                data={
                    "raw_output": formatted_data if 'formatted_data' in locals() else (parsed_data if 'parsed_data' in locals() else stdout_str.strip()),
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

                                # if self._parsed_data_callback:
                                #     try:
                                #         if asyncio.iscoroutinefunction(self._parsed_data_callback):
                                #             await self._parsed_data_callback(json.dumps(formatted_data))
                                #         else:
                                #             self._parsed_data_callback(json.dumps(formatted_data))
                                #     except Exception as callback_error:
                                #         self.logger.error(f"[{process_id}] Error in parsed data callback: {callback_error}")

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
                    "raw_output": formatted_data if 'formatted_data' in locals() else (parsed_data if 'parsed_data' in locals() else stdout_str.strip()),
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
                    command_data_ib = invoke_response_ib.get("CommandDataIB", {})
                    if not command_data_ib:
                        command_status_ib = invoke_response_ib.get("CommandStatusIB", {})
                        status_ib = command_status_ib.get("StatusIB", {})
                        command_path_ib = command_status_ib.get("CommandPathIB", {})

                        node_id = command_path_ib.get("NodeID")
                        endpoint = command_path_ib.get("EndpointId")
                        cluster_id = command_path_ib.get("ClusterId")
                        command_id = command_path_ib.get("CommandId")
                    else:
                        command_path_ib = command_data_ib.get("CommandPathIB", {})
                        command_fields = command_data_ib.get("CommandFields", {})

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

                    if command_data_ib:
                        return {
                            "node": node_id,
                            "endpoint": endpoint,
                            "cluster": cluster_name or f"Cluster_{cluster_id}",
                            "command": command_name or f"Command_{command_id}",
                            "command_fields": command_fields,
                        }
                    else:
                        return {
                            "node": node_id,
                            "endpoint": endpoint,
                            "cluster": cluster_name or f"Cluster_{cluster_id}",
                            "command": command_name or f"Command_{command_id}",
                            "status": status_ib,
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

    async def commissioning(self, pairing_code: str, node_id: Optional[int] = None) -> bool:
        """
        Commission a device using pairing code.

        Args:
            pairing_code: The pairing code (QR code payload or manual code)
            node_id: Target node ID (if None, will use next available)

        Returns:
            True if commissioning successful, False otherwise
        """
        try:
            if node_id is None:
                node_id = self.database.get_new_node_id() if hasattr(self, 'database') else 1

            command = f"pairing code {node_id} {pairing_code}"
            response = await self.execute_command(command, timeout=120.0)
            if response.data:
                for item in response.data:
                    if item['node'] == node_id:
                        if item['command_fields']['0x0'] == "0":
                            return True
                        continue

            return False

        except Exception as e:
            self.logger.error(f"Error during commissioning: {e}")
            return False

    # Utility methods for common operations
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

    # Advanced utility methods with detailed data extraction
    async def get_cluster_list(self, node_id: int, endpoint: int) -> list:
        """
        Get cluster list for a specific endpoint with detailed extraction.

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
            if data.get("value"):
                clusters = []
                for cluster in data.get("value", []):
                    clusters.append(int(cluster))
                return clusters

        except Exception as e:
            self.logger.error(f"Error extracting cluster data: {e}")

        return []

    async def get_attribute_list(self, node_id: int, endpoint: int, cluster_name: str) -> list:
        """
        Get attribute list for a specific cluster with detailed extraction.

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
            if data.get("value"):
                attributes = []
                for attribute in data.get("value", []):
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
            return str(data.get("value", ""))

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
            return [int(endpoint) for endpoint in data.get("value", [])]

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
            return data.get("value", [])

        except Exception as e:
            self.logger.error(f"Error extracting device type data: {e}")

        return []
