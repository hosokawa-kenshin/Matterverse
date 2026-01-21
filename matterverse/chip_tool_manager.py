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
from typing import List, Optional, Dict, Any, Callable
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
                "data version filters provided",
                "SubscribeResponse is received",
                "Refresh LivenessCheckTime for"
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


class InteractiveSubscriptionParser:
    """
    既存 ChipToolParser を活用したストリーミング対応パーサー

    chip-tool の interactive モード出力をリアルタイムでパース
    """

    def __init__(self, data_model=None):
        """
        Initialize parser.

        Args:
            data_model: データモデル（クラスタ・属性名の解決用）
        """
        self.chip_parser = ChipToolParser()  # 既存パーサーを活用
        self.data_model = data_model
        self.logger = get_chip_logger()

        # ストリーミング処理用バッファ
        self._buffer = ""
        self._max_buffer_size = 5000000  # 約5MB
        self.has_revision = False


    def extract_attribute_data_ib_blocks(self, text: str) -> List[str]:
        results = []

        key = "AttributeDataIB = {"
        i = 0
        n = len(text)

        while i < n:
            start = text.find(key, i)
            if start == -1:
                break

            brace_count = 0
            j = start

            while j < n:
                if text[j] == "{":
                    brace_count += 1
                elif text[j] == "}":
                    brace_count -= 1
                    if brace_count == 0:
                        # AttributeDataIB 全体を取得
                        block = text[start : j + 1]
                        results.append(block.strip())
                        i = j + 1
                        break
                j += 1
            else:
                break

        return results

    def parse_line(self, line: str) -> Optional[list[Dict[str, Any]]]:
        """
        1行ずつ受け取ってバッファに蓄積し、完成したレポートをパース

        Args:
            line: chip-tool からの1行の出力

        Returns:
            属性データのリスト（レポート完成時）、または None
        """
        # 生の行をバッファに追加
        self._buffer += line + "\n"
        with open("chiptool_stream.log", "a", encoding="utf-8") as f:
          f.write(line + "\n")
          f.flush()

        # バッファサイズ制限
        if len(self._buffer) > self._max_buffer_size:
            # 後半を保持（前半を削除）
            self._buffer = self._buffer[-25000:]
            self.logger.debug("Buffer trimmed to prevent memory overflow")

        # ReportDataMessage の終了を検出
        # InteractionModelRevision があり、かつその後に } がある必要がある
        if not self.has_revision:
            self.has_revision = 'InteractionModelRevision' in line
        has_closing_brace = self.has_revision and '}' in line

        if not has_closing_brace:
            return None

        try:
            self.has_revision = False
            self.logger.debug(f"Processing complete report, buffer size: {len(self._buffer)} bytes")
            tmp_buffer = self._buffer
            self._buffer = ""

            formatted = self.chip_parser.delete_garbage_from_output(tmp_buffer)
            if not formatted:
                self.logger.debug("No valid data after formatting")
                self._buffer = ""
                return None

            self.logger.debug(f"Formatted output ({len(formatted)} bytes): {formatted[:200]}...")

            blocks = self.extract_attribute_data_ib_blocks(formatted)

            self.logger.debug(f"Extracted {len(blocks)} blocks")

            results = []
            for block in blocks:
                self.logger.debug(f"Processing block ({len(block)} bytes): {block[:100]}...")
                # AttributeDataIB ブロックを処理
                if 'AttributeDataIB' in block:
                    self.logger.debug("Block contains AttributeDataIB, extracting...")
                    attr_data = self._extract_attribute_data(block)
                    if attr_data:
                        results.append(attr_data)
                        self.logger.debug(f"Successfully extracted: {attr_data}")
                    else:
                        self.logger.warning("Failed to extract attribute data from block")
                else:
                    self.logger.debug("Block does not contain AttributeDataIB, skipping")

            if results:
                self.logger.info(f"Parsed {len(results)} attribute reports")
                return results
            else:
                self.logger.debug("No results extracted from blocks")

        except Exception as e:
            self.logger.error(f"Parse error: {e}", exc_info=True)
            self._buffer = ""  # エラー時もクリア

        return None

    def _extract_attribute_data(self, block: str) -> Optional[Dict[str, Any]]:
        """
        ブロックから属性データを抽出

        Args:
            block: AttributeDataIB ブロックの文字列

        Returns:
            属性データ辞書、または None
        """
        data = {}

        # NodeID（delete_garbage_from_output が挿入済み）
        match = re.search(r'NodeID\s*=\s*(0x[0-9a-fA-F]+)', block)
        if match:
            data['node_id'] = int(match.group(1), 16)
        else:
            self.logger.warning("NodeID not found in block")
            return None  # NodeID 必須

        # Endpoint（16進数）
        match = re.search(r'Endpoint\s*=\s*0x([0-9a-fA-F]+)', block)
        if match:
            data['endpoint'] = int(match.group(1), 16)
        else:
            # 10進数も試す（後方互換性）
            match = re.search(r'Endpoint\s*=\s*(\d+)', block)
            if match:
                data['endpoint'] = int(match.group(1))

        # Cluster（16進数）
        match = re.search(r'Cluster\s*=\s*0x([0-9a-fA-F]+)', block)
        if match:
            cluster_id = int(match.group(1), 16)
            data['cluster'] = cluster_id

            cluster_id_str = f"0x{cluster_id:04X}"
            # クラスター名を取得
            if self.data_model:
                data['cluster_name'] = self.data_model.get_cluster_name_by_id(cluster_id_str)
            else:
                data['cluster_name'] = f"0x{cluster_id:04X}"

        # Attribute（16進数、アンダースコア付き対応）
        match = re.search(r'Attribute\s*=\s*0x([0-9a-fA-F_]+)', block)
        if match:
            attr_hex = match.group(1).replace('_', '')
            attribute_id = int(attr_hex, 16)
            data['attribute'] = attribute_id
            attribute_id_str = f"0x{attribute_id:04X}"

            # 属性名を取得
            if self.data_model and 'cluster' in data:
                data['attribute_name'] = self.data_model.get_attribute_name_by_code(
                    cluster_id_str, attribute_id_str
                )
            else:
                data['attribute_name'] = f"0x{attribute_id:04X}"

        # DataVersion
        match = re.search(r'DataVersion\s*=\s*0x([0-9a-fA-F]+)', block)
        if match:
            data['data_version'] = int(match.group(1), 16)

        # Data 値（型判定）
        # 注意: delete_garbage_from_output で "(unsigned)" などが削除される

        # Bool 型: Data = true / Data = false

        match = re.search(r'Data\s*=\s*(true|false)', block, re.IGNORECASE)
        if match:
            data['value'] = match.group(1).lower()
            data['value_type'] = 'bool'
        else:
            # 数値型: Data = 123 または Data = -5
            match = re.search(r'Data\s*=\s*(-?\d+)', block)
            if match:
                data['value'] = int(match.group(1))
                data['value_type'] = 'int'
            else:
                # 文字列型: Data = "text"
                match = re.search(r'Data\s*=\s*"([^"]*)"', block)
                if match:
                    data['value'] = match.group(1)
                    data['value_type'] = 'string'
                else:
                    match = re.search(r'Data\s*=\s*\[\s*\{(.*?)\}\s*\]',block,re.DOTALL)
                    if match:
                        content = match.group(1).strip()
                        data['value'] = '{ ' + content + ' }'
                        data['value_type'] = 'struct'
                    else:
                        match = re.search(r'Data\s*=\s*\[\s*(.*?)\s*\]',block,re.DOTALL)
                        if match:
                            content = match.group(1).strip()
                            items = [item.strip() for item in content.split(',')]
                            data['value'] = items
                            data['value_type'] = 'array'
                        else:
                    # その他（配列、構造体など）
                    # より詳細な解析が必要な場合は拡張
                            self.logger.warning(f"Could not extract value from block: {block}")
                            data['value'] = None
                            data['value_type'] = 'unknown'

        # 必須フィールドチェック
        required_fields = ['node_id', 'endpoint', 'cluster', 'attribute']
        if all(k in data for k in required_fields):
            self.logger.debug(
                f"Extracted: NodeID={data['node_id']}, "
                f"Endpoint={data['endpoint']}, "
                f"Cluster=0x{data['cluster']:04X}, "
                f"Attribute=0x{data['attribute']:04X}, "
                f"Value={data.get('value')}"
            )
            return data
        else:
            missing = [f for f in required_fields if f not in data]
            self.logger.warning(f"Missing required fields: {missing}")

        return None


class InteractiveChipToolManager:
    """Interactive モードでの chip-tool 管理"""

    def __init__(self, chip_tool_path: str, commissioning_dir: str,
                 paa_cert_path: str, database, data_model, debug_file: str = None):
        self.chip_tool_path = chip_tool_path
        self.commissioning_dir = commissioning_dir
        self.paa_cert_path = paa_cert_path
        self.database = database
        self.data_model = data_model
        self.logger = get_chip_logger()

        self.process: Optional[asyncio.subprocess.Process] = None
        self.output_task: Optional[asyncio.Task] = None

        # ChipToolParser を転用したパーサー
        self.parser = InteractiveSubscriptionParser(data_model)

        self._running = False
        self._write_lock = asyncio.Lock()
        self._notification_callback = None

        # デバッグファイル出力
        self.debug_file = debug_file or "/tmp/interactive_chip_tool_debug.log"
        self._debug_enabled = True
        # ファイルをクリア
        if self._debug_enabled:
            try:
                with open(self.debug_file, 'w') as f:
                    f.write(f"=== Interactive ChipTool Debug Log ===\n")
                    f.write(f"Started at: {datetime.now().isoformat()}\n\n")
            except Exception as e:
                self.logger.warning(f"Failed to initialize debug file: {e}")
                self._debug_enabled = False

    def _write_debug(self, message: str):
        """デバッグメッセージをファイルに書き込み"""
        if not self._debug_enabled:
            return
        try:
            with open(self.debug_file, 'a') as f:
                f.write(f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] {message}\n")
        except Exception as e:
            self.logger.warning(f"Failed to write debug: {e}")

    async def start(self):
        """Interactive モードで chip-tool を起動"""
        if self._running:
            self.logger.warning("chip-tool is already running")
            return

        try:
            # chip-tool を interactive モードで起動
            # 重要: バッファリング問題を回避するための設定
            env = os.environ.copy()
            env['PYTHONUNBUFFERED'] = '1'  # Python のバッファリング無効化

            cmd = [
                self.chip_tool_path,
                "interactive",
                "start",
                "--storage-directory", self.commissioning_dir,
                "--paa-trust-store-path", self.paa_cert_path,
            ]

            self.logger.info(f"Starting chip-tool: {' '.join(cmd)}")

            self.process = await asyncio.create_subprocess_exec(
                *cmd,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
                cwd=os.path.dirname(self.chip_tool_path),
                env=env,
            )

            self._running = True

            # 出力監視タスクを起動
            self.output_task = asyncio.create_task(self._monitor_output())

            self.logger.info("chip-tool interactive mode started")

            # プロセス起動待機
            await asyncio.sleep(2.0)

        except Exception as e:
            self.logger.error(f"Failed to start chip-tool: {e}")
            raise

    async def stop(self):
        """chip-tool プロセスを停止"""
        if not self._running:
            return

        self._running = False

        # 出力監視タスクをキャンセル
        if self.output_task and not self.output_task.done():
            self.output_task.cancel()
            try:
                await self.output_task
            except asyncio.CancelledError:
                pass

        # プロセスを終了
        if self.process and self.process.returncode is None:
            try:
                # 終了コマンドを送信
                async with self._write_lock:
                    self.process.stdin.write(b"quit\n")
                    await self.process.stdin.drain()

                await asyncio.wait_for(self.process.wait(), timeout=5.0)
            except asyncio.TimeoutError:
                self.process.terminate()
                await asyncio.wait_for(self.process.wait(), timeout=3.0)
            except Exception as e:
                self.logger.error(f"Error stopping process: {e}")
                self.process.kill()

        self.logger.info("chip-tool stopped")

    async def send_command(self, command: str) -> bool:
        """
        Interactive モードの chip-tool にコマンドを送信

        Args:
            command: 実行するコマンド (例: "any subscribe-by-id 0x0006 0x0000 1 0 0 100 1000")

        Returns:
            送信成功可否
        """
        if not self._running or not self.process:
            self.logger.error("chip-tool is not running")
            return False

        try:
            async with self._write_lock:
                cmd_bytes = f"{command}\n".encode('utf-8')
                self._write_debug(f"[SEND_CMD] Command: {command}")
                self._write_debug(f"[SEND_CMD] Bytes: {cmd_bytes}")
                self.process.stdin.write(cmd_bytes)
                await self.process.stdin.drain()

            self.logger.debug(f"Command sent: {command}")
            return True

        except Exception as e:
            self.logger.error(f"Failed to send command: {e}")
            self._write_debug(f"[SEND_CMD] Error: {e}")
            return False

    async def _monitor_output(self):
        """stdout/stderr を監視してパース"""
        try:
            while self._running:
                # stdout と stderr を並行して読み取り
                tasks = []

                if self.process.stdout:
                    tasks.append(self._read_stream(self.process.stdout, 'stdout'))

                if self.process.stderr:
                    tasks.append(self._read_stream(self.process.stderr, 'stderr'))

                if not tasks:
                    break

                await asyncio.gather(*tasks, return_exceptions=True)

        except asyncio.CancelledError:
            self.logger.info("Output monitoring cancelled")
        except Exception as e:
            self.logger.error(f"Error in output monitoring: {e}")

    async def _read_stream(self, stream, stream_name: str):
        """
        ストリームから1行ずつ読み取り

        注意: 常時起動プロセスではバッファリングの問題で readline() が
        即座に返らない可能性があるため、以下の対策を実装：
        1. 環境変数 PYTHONUNBUFFERED=1 でバッファリング無効化
        2. タイムアウト付き read を使用
        """
        try:
            while self._running:
                # タイムアウト付きで readline を実行
                # 長時間ブロックを防ぐため 1 秒でタイムアウト
                try:
                    line = await asyncio.wait_for(
                        stream.readline(),
                        timeout=1.0
                    )
                except asyncio.TimeoutError:
                    # タイムアウトは正常（出力がない時）
                    continue

                if not line:
                    # ストリーム終了
                    self.logger.warning(f"{stream_name} closed")
                    break

                line_str = line.decode('utf-8', errors='replace').strip()

                if line_str:
                    # デバッグファイルに生ログを記録
                    self._write_debug(f"[{stream_name}] {line_str}")

                    # パーサーに渡す（複数の属性レポートが返る可能性あり）
                    parsed_data_list = self.parser.parse_line(line_str)

                    if parsed_data_list:
                        self._write_debug(f"[PARSED] Found {len(parsed_data_list)} attribute(s)")
                        # 複数の属性レポートを順次処理
                        for parsed_data in parsed_data_list:
                            self._write_debug(f"[PARSED] Data: {parsed_data}")
                            await self._handle_parsed_data(parsed_data)

        except asyncio.CancelledError:
            raise
        except Exception as e:
            self.logger.error(f"Error reading {stream_name}: {e}")

    async def _handle_parsed_data(self, parsed_data: Dict[str, Any]):
        """パースされたデータを処理（DB更新・通知）"""
        try:
            node_id = parsed_data['node_id']
            endpoint = parsed_data['endpoint']
            cluster = parsed_data.get('cluster_name', parsed_data['cluster'])
            attribute = parsed_data.get('attribute_name', parsed_data['attribute'])
            new_value = str(parsed_data['value'])  # Convert to string for database

            self._write_debug(f"[HANDLE] NodeID={node_id}, Endpoint={endpoint}, Cluster={cluster}, Attribute={attribute}, Value={new_value}")

            # データベースから現在値を取得
            current_value = self.database.get_attribute_value(
                node_id, endpoint, cluster, attribute
            )

            self._write_debug(f"[DB_GET] Current value: {current_value}")

            # 値が変更されているか、または初回（current_value が None）の場合に更新
            should_update = (current_value is None) or (current_value != new_value)

            if should_update:
                if current_value is None:
                    self._write_debug(f"[DB_UPDATE] Initial value: {new_value}")
                    self.logger.info(
                        f"Initial attribute value: NodeID={node_id}, Endpoint={endpoint}, "
                        f"Cluster={cluster}, Attribute={attribute}, "
                        f"Value={new_value}"
                    )
                else:
                    self._write_debug(f"[DB_UPDATE] Changed: {current_value} -> {new_value}")
                    self.logger.info(
                        f"Attribute changed: NodeID={node_id}, Endpoint={endpoint}, "
                        f"Cluster={cluster}, Attribute={attribute}, "
                        f"Old={current_value}, New={new_value}"
                    )

                # データベース更新
                success = self.database.update_attribute_value(
                    node_id=node_id,
                    endpoint=endpoint,
                    cluster=cluster,
                    attribute=attribute,
                    value=new_value
                )

                self._write_debug(f"[DB_UPDATE] Success: {success}")

                if not success:
                    self.logger.warning(
                        f"Failed to update attribute: NodeID={node_id}, Endpoint={endpoint}, "
                        f"Cluster={cluster}, Attribute={attribute}"
                    )
                    return

                if self._notification_callback:
                    self._write_debug(f"[NOTIFY] Sending notification")
                    await self._notification_callback({
                        'node_id': node_id,
                        'endpoint': endpoint,
                        'cluster': cluster,
                        'attribute': attribute,
                        'value': new_value,
                        'old_value': current_value
                    })
                else:
                    self._write_debug(f"[NOTIFY] Skipped (initial value or no callback)")
            else:
                self._write_debug(f"[SKIP] Value unchanged: {current_value}")

        except Exception as e:
            self.logger.error(f"Error handling parsed data: {e}")

    def set_notification_callback(self, callback: Callable):
        """通知コールバックを設定"""
        self._notification_callback = callback

    async def subscribe_all_devices(self):
        """全デバイスの全属性をサブスクライブ"""
        try:
            # データベースから全デバイス取得
            devices = self.database.get_all_devices()

            if not devices:
                self.logger.warning("No devices found in database")
                return

            self.logger.info(f"Subscribing to {len(devices)} devices")

            for device in devices:
                await self._subscribe_device(device)

                # デバイス間で少し間隔を空ける
                await asyncio.sleep(0.5)

            self.logger.info("All devices subscribed")

        except Exception as e:
            self.logger.error(f"Error subscribing to devices: {e}")

    async def _subscribe_device(self, device: Dict[str, Any]):
        """1つのデバイスの全属性をサブスクライブ"""
        node_id = device['node']  # Fixed: 'node' not 'node_id'
        endpoint = device['endpoint']

        # デバイスの全クラスター・属性を取得
        attributes = self.database.get_device_attributes(node_id, endpoint)

        if not attributes:
            self.logger.warning(f"No attributes for device {node_id}:{endpoint}")
            return

        # クラスターごとにグループ化
        clusters = {}
        for attr in attributes:
            cluster_name = attr['cluster']  # Fixed: 'cluster' not 'cluster_id'
            if cluster_name not in clusters:
                clusters[cluster_name] = []
            # 属性名を記録（実際にはワイルドカードを使うので使用しない）

        # 各クラスターの全属性をサブスクライブ
        for cluster_name in clusters.keys():
            # データモデルからクラスターIDを取得
            cluster_info = self.data_model.get_cluster_by_name(cluster_name)
            if not cluster_info:
                self.logger.warning(f"Cluster {cluster_name} not found in data model")
                continue

            cluster_id_raw = cluster_info.get('id', 0)

            # cluster_id を整数に変換（16進数文字列の場合もある）
            if isinstance(cluster_id_raw, str):
                cluster_id = int(cluster_id_raw, 16) if cluster_id_raw.startswith('0x') else int(cluster_id_raw)
            else:
                cluster_id = int(cluster_id_raw)

            # ワイルドカード属性でサブスクライブ
            # any subscribe-by-id cluster-ids attribute-ids min-interval max-interval destination-id endpoint-ids
            command = (
                f"any subscribe-by-id "
                f"0x{cluster_id:04X} "  # cluster-ids
                f"0xFFFFFFFF "  # attribute-ids (wildcard)
                f"0 "  # min-interval (seconds)
                f"100 "  # max-interval (seconds)
                f"{node_id} "  # destination-id (node-id)
                f"{endpoint}"  # endpoint-ids
            )

            self._write_debug(f"[SUBSCRIBE] Prepared command: {command}")

            success = await self.send_command(command)

            if success:
                self.logger.info(
                    f"Subscribed: NodeID={node_id}, Endpoint={endpoint}, "
                    f"Cluster={cluster_name} (0x{cluster_id:04X})"
                )
            else:
                self.logger.error(
                    f"Failed to subscribe: NodeID={node_id}, Endpoint={endpoint}, "
                    f"Cluster={cluster_name} (0x{cluster_id:04X})"
                )

            # クラスター間で間隔を空ける
            await asyncio.sleep(0.3)
