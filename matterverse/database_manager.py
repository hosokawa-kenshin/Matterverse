"""
Database management for Matterverse application.
"""
import sqlite3
import json
from typing import List, Optional, Dict, Any
from contextlib import contextmanager

from logger import get_sql_logger


class Database:
    """Database manager for Matterverse SQLite operations."""

    def __init__(self, db_path: str, data_model: Optional[Any] = None):
        """
        Initialize database manager.

        Args:
            db_path: Path to SQLite database file
        """
        self.db_path = db_path
        self.logger = get_sql_logger()
        self._connection = None
        self._initialize_tables()
        self.data_model = data_model

    def _initialize_tables(self):
        """Create database tables if they don't exist."""
        with self.get_connection() as conn:
            cursor = conn.cursor()

            # Create Device table
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS Device (
                NodeID INTEGER,
                Endpoint INTEGER,
                DeviceType INTEGER,
                TopicID TEXT,
                PRIMARY KEY (NodeID, Endpoint)
            )
            ''')

            # Create UniqueID table
            cursor.execute('''
            CREATE TABLE IF NOT EXISTS UniqueID (
                NodeID INTEGER,
                Name TEXT,
                UniqueID TEXT,
                PRIMARY KEY (NodeID)
            )
            ''')

            cursor.execute('''
            CREATE TABLE IF NOT EXISTS Attribute (
                NodeID INTEGER,
                Endpoint INTEGER,
                Cluster TEXT,
                Attribute TEXT,
                Type TEXT,
                Value TEXT,
                PRIMARY KEY (NodeID, Endpoint, Cluster, Attribute)
            )
            ''')

            conn.commit()
            self.logger.info("Database initialized")

    @contextmanager
    def get_connection(self):
        """
        Get database connection with automatic cleanup.

        Yields:
            sqlite3.Connection: Database connection
        """
        conn = None
        try:
            conn = sqlite3.connect(self.db_path, check_same_thread=False)
            conn.row_factory = sqlite3.Row  # Enable column access by name
            yield conn
        except sqlite3.Error as e:
            if conn:
                conn.rollback()
            self.logger.error(f"Database error: {e}")
            raise
        finally:
            if conn:
                conn.close()

    def get_all_devices(self) -> List[Dict[str, Any]]:
        """
        Get all devices with comprehensive information.

        Returns:
            List of device dictionaries with clusters, attributes, and commands
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                # Get all devices
                cursor.execute("""
                SELECT DISTINCT NodeID, Endpoint, DeviceType, TopicID FROM Device
                """)
                device_rows = cursor.fetchall()

                devices = []
                for device_row in device_rows:
                    node_id = device_row['NodeID']
                    endpoint = device_row['Endpoint']
                    device_type_name = str(device_row['DeviceType'])
                    topic_id = device_row['TopicID']

                    # Get clusters for this device
                    clusters = self._get_device_clusters(node_id, endpoint)

                    device = {
                        "node": node_id,
                        "endpoint": endpoint,
                        "device_type": device_type_name or f"Unknown Device Type",
                        "topic_id": topic_id,
                        "clusters": clusters
                    }
                    devices.append(device)

                return devices

        except sqlite3.Error as e:
            self.logger.error(f"Query error: {e}")
            return []

    def _get_device_clusters(self, node_id: int, endpoint: int) -> List[Dict[str, Any]]:
        """Get clusters with attributes and commands for a device."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                # Get all attributes for this device grouped by cluster
                cursor.execute("""
                SELECT DISTINCT Cluster FROM Attribute
                WHERE NodeID = ? AND Endpoint = ?
                ORDER BY Cluster
                """, (node_id, endpoint))

                cluster_rows = cursor.fetchall()
                clusters = []

                for cluster_row in cluster_rows:
                    cluster_name = cluster_row['Cluster']

                    # Get attributes for this cluster
                    attributes = self._get_cluster_attributes(node_id, endpoint, cluster_name)

                    # Get commands for this cluster from data model
                    commands = self._get_cluster_commands(cluster_name)

                    cluster = {
                        "name": cluster_name,
                        "attributes": attributes,
                        "commands": commands
                    }
                    clusters.append(cluster)

                return clusters

        except sqlite3.Error as e:
            self.logger.error(f"Error getting device clusters: {e}")
            return []

    def _get_cluster_attributes(self, node_id: int, endpoint: int, cluster_name: str) -> List[Dict[str, Any]]:
        """Get attributes for a specific cluster."""
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                cursor.execute("""
                SELECT Attribute, Type, Value FROM Attribute
                WHERE NodeID = ? AND Endpoint = ? AND Cluster = ?
                ORDER BY Attribute
                """, (node_id, endpoint, cluster_name))

                attr_rows = cursor.fetchall()
                attributes = []

                for attr_row in attr_rows:
                    attribute_name = attr_row['Attribute']
                    attribute_type = attr_row['Type']
                    value_str = attr_row['Value']

                    # Try to parse value as appropriate type
                    parsed_value = self._parse_attribute_value(value_str)

                    attribute = {
                        "name": attribute_name,
                        "type": attribute_type,
                        "value": parsed_value
                    }
                    attributes.append(attribute)

                return attributes

        except sqlite3.Error as e:
            self.logger.error(f"Error getting cluster attributes: {e}")
            return []

    def _get_cluster_commands(self, cluster_name: str) -> List[Dict[str, Any]]:
        """Get commands for a cluster from data model."""
        commands = []
        if not self.data_model:
            return []

        # # Use the new method from data_model if available
        # if hasattr(self.data_model, 'get_command_names_by_cluster_name'):
        #     return self.data_model.get_command_names_by_cluster_name(cluster_name)

        # Fallback to original implementation
        cluster = self.data_model.get_cluster_by_name(cluster_name)
        if not cluster:
            return []

        commands_data = cluster.get("commands", [])
        if not commands_data:
            self.logger.warning(f"No commands found for cluster: {cluster_name}")
            return []

        for command in commands_data:
            if isinstance(command, dict) and "name" in command:
                command_info = {
                    "name": command["name"],
                    "args": command.get("args", [])
            }
            commands.append(command_info)
        return commands

    def _parse_attribute_value(self, value_str: str) -> Any:
        """Parse attribute value to appropriate Python type."""
        if not value_str:
            return None

        # Try to parse as JSON first
        try:
            import json
            return json.loads(value_str)
        except (json.JSONDecodeError, ValueError):
            pass

        # Try to parse as boolean
        if value_str.lower() in ('true', 'false'):
            return value_str.lower() == 'true'

        # Try to parse as integer
        try:
            return int(value_str)
        except ValueError:
            pass

        # Try to parse as float
        try:
            return float(value_str)
        except ValueError:
            pass

        # Return as string
        return value_str

    def get_all_attributes(self) -> List[Dict[str, Any]]:
        """
        Get all attributes from database.

        Returns:
            List of attribute dictionaries
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                SELECT NodeID, Endpoint, Cluster, Attribute, Value FROM Attribute
                """)
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
        except sqlite3.Error as e:
            self.logger.error(f"Query error: {e}")
            return []

    def update_attribute(self, parsed_json_str: str) -> bool:
        """
        Update or insert attribute from parsed JSON string.

        Args:
            parsed_json_str: Parsed JSON string containing NodeID, Endpoint, Cluster, Attribute, Value

        Returns:
            True if successful, False otherwise
        """
        try:
            json_data = json.loads(parsed_json_str)

                # Check if this is a ReportDataMessage
            if ("ReportDataMessage" not in json_data or
                "AttributeReportIBs" not in json_data["ReportDataMessage"]):
                return False

            # Extract attribute path information
            report_data = json_data["ReportDataMessage"]
            attr_reports = report_data.get("AttributeReportIBs", [])
            if not attr_reports:
                return False

            attr_report = attr_reports[0].get("AttributeReportIB", {})
            attr_data = attr_report.get("AttributeDataIB", {})
            attr_path = attr_data.get("AttributePathIB", {})
            response_node_id = attr_path.get("NodeID")
            if response_node_id == "UNKNOWN":
                self.logger.warning("Received UNKNOWN NodeID, skipping update")
                return False
            response_endpoint = attr_path.get("Endpoint")
            response_cluster_id = attr_path.get("Cluster")
            response_cluster = self.data_model.get_cluster_name_by_id(f"0x{int(response_cluster_id):04x}")
            response_attribute_id = attr_path.get("Attribute")
            response_attribute = self.data_model.get_attribute_name_by_code(f"0x{int(response_cluster_id):04x}",f"0x{int(response_attribute_id):04x}")
            response_value = attr_data.get("Data", None)

            with self.get_connection() as conn:
                cursor = conn.cursor()

                # Check if attribute already exists to preserve Type field
                cursor.execute("""
                SELECT Type FROM Attribute
                WHERE NodeID = ? AND Endpoint = ? AND Cluster = ? AND Attribute = ?
                """, (response_node_id, response_endpoint, response_cluster, response_attribute))

                existing_row = cursor.fetchone()

                if existing_row:
                    # Update existing record, preserve Type field
                    existing_type = existing_row['Type']
                    cursor.execute("""
                    UPDATE Attribute SET Value = ?
                    WHERE NodeID = ? AND Endpoint = ? AND Cluster = ? AND Attribute = ?
                    """, (response_value, response_node_id, response_endpoint, response_cluster, response_attribute))
                    self.logger.info(f"Updated attribute: NodeID={response_node_id}, Endpoint={response_endpoint}, "
                                   f"Cluster={response_cluster}, Attribute={response_attribute}, "
                                   f"Type={existing_type} (preserved), Value={response_value}")
                else:
                    return True

                conn.commit()
                return True
        except sqlite3.Error as e:
            self.logger.error(f"Update error: {e}")
            return False


    def get_device_by_topic_id(self, topic_id: str) -> Optional[Dict[str, Any]]:
        """
        Get device by topic ID.

        Args:
            topic_id: Topic ID to search for

        Returns:
            Device dictionary or None if not found
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                SELECT NodeID, Endpoint, DeviceType, TopicID
                FROM Device WHERE TopicID = ?
                """, (topic_id,))
                row = cursor.fetchone()
                return dict(row) if row else None
        except sqlite3.Error as e:
            self.logger.error(f"Query error: {e}")
            return None

    def get_devices_by_node_id(self, node_id: int) -> List[Dict[str, Any]]:
        """
        Get all devices for a specific node ID.

        Args:
            node_id: Node ID to search for

        Returns:
            List of device dictionaries
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                SELECT NodeID, Endpoint, DeviceType, TopicID
                FROM Device WHERE NodeID = ?
                """, (node_id,))
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
        except sqlite3.Error as e:
            self.logger.error(f"Query error: {e}")
            return []

    def get_device_by_node_id_endpoint(self, node_id: Optional[int],
                                     endpoint: Optional[int]) -> Optional[Dict[str, Any]]:
        """
        Get device by node ID and endpoint.

        Args:
            node_id: Node ID
            endpoint: Endpoint ID

        Returns:
            Device dictionary or None if not found
        """
        if node_id is None or endpoint is None:
            self.logger.warning("NodeID or Endpoint is None")
            return None

        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                SELECT NodeID, Endpoint, DeviceType, TopicID
                FROM Device WHERE NodeID = ? AND Endpoint = ?
                """, (node_id, endpoint))
                row = cursor.fetchone()
                return dict(row) if row else None
        except sqlite3.Error as e:
            self.logger.error(f"Query error: {e}")
            return None

    def get_endpoints_by_node_id(self, node_id: int) -> List[int]:
        """
        Get all endpoints for a specific node ID.

        Args:
            node_id: Node ID to search for

        Returns:
            List of endpoint IDs
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                SELECT Endpoint FROM Device WHERE NodeID = ?
                """, (node_id,))
                return [row[0] for row in cursor.fetchall()]
        except sqlite3.Error as e:
            self.logger.error(f"Query error: {e}")
            return []

    def get_clusters_by_node_id_endpoint(self, node_id: int, endpoint: int) -> List[str]:
        """
        Get all clusters for a specific node ID and endpoint.

        Args:
            node_id: Node ID to search for
            endpoint: Endpoint ID to search for

        Returns:
            List of cluster names
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                SELECT Cluster FROM Attribute WHERE NodeID = ? AND Endpoint = ?
                """, (node_id, endpoint))
                return [row[0] for row in cursor.fetchall()]
        except sqlite3.Error as e:
            self.logger.error(f"Query error: {e}")
            return []

    def get_attributenames_by_node_id_endpoint_cluster_name(self, node_id: int, endpoint: int, cluster_name: str) -> List[str]:
        """
        Get all attribute names for a specific node ID, endpoint, and cluster name.

        Args:
            node_id: Node ID to search for
            endpoint: Endpoint ID to search for

        Returns:
            List of attribute names
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                SELECT Attribute FROM Attribute WHERE NodeID = ? AND Endpoint = ? AND Cluster = ?
                """, (node_id, endpoint, cluster_name))
                return [row[0] for row in cursor.fetchall()]
        except sqlite3.Error as e:
            self.logger.error(f"Query error: {e}")
            return []

    def insert_unique_id(self, node_id: int, device_name: str, unique_id: str) -> bool:
        """
        Insert unique ID information.

        Args:
            node_id: Node ID
            device_name: Device name
            unique_id: Unique ID

        Returns:
            True if successful, False otherwise
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                INSERT INTO UniqueID (NodeID, Name, UniqueID)
                VALUES (?, ?, ?)
                """, (node_id, device_name, unique_id))
                conn.commit()
                self.logger.info(f"Inserted unique ID info: NodeID={node_id}, Name={device_name}, UniqueID={unique_id}")
                return True
        except sqlite3.IntegrityError as e:
            self.logger.error(f"Insert error: {e}")
            return False

    def get_new_node_id(self) -> int:
        """
        Get next available node ID.

        Returns:
            Next node ID (max existing + 1, or 1 if no devices exist)
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT MAX(NodeID) FROM Device")
                result = cursor.fetchone()[0]
                return (result + 1) if result is not None else 1
        except sqlite3.Error as e:
            self.logger.error(f"Query error: {e}")
            return 1

    def insert_device(self, node_id: int, endpoint: int, device_type: int, topic_id: str) -> bool:
        """
        Insert device information.

        Args:
            node_id: Node ID
            endpoint: Endpoint ID
            device_type: Device type
            topic_id: Topic ID

        Returns:
            True if successful, False otherwise
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                INSERT INTO Device (NodeID, Endpoint, DeviceType, TopicID)
                VALUES (?, ?, ?, ?)
                """, (node_id, endpoint, device_type, topic_id))
                conn.commit()
                self.logger.info(f"Inserted device: NodeID={node_id}, Endpoint={endpoint}, DeviceType={device_type}, TopicID={topic_id}")
                return True
        except sqlite3.IntegrityError as e:
            self.logger.error(f"Insert error: {e}")
            return False

    def create_attribute_entry(self, node_id: int, endpoint: int, cluster: str, attribute: str) -> bool:
        """
        Create or update attribute entry.

        Args:
            node_id: Node ID
            endpoint: Endpoint ID
            cluster: Cluster name
            attribute: Attribute name
            value: Attribute value
        Returns:
            True if successful, False otherwise
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()

                # Check if attribute already exists
                cursor.execute("""
                SELECT Type, Value FROM Attribute
                WHERE NodeID = ? AND Endpoint = ? AND Cluster = ? AND Attribute = ?
                """, (node_id, endpoint, cluster, attribute))

                existing_row = cursor.fetchone()

                if existing_row:
                    # Attribute already exists - preserve everything
                    self.logger.debug(f"Attribute already exists: NodeID={node_id}, Endpoint={endpoint}, "
                                    f"Cluster={cluster}, Attribute={attribute} - skipping")
                    return True
                else:
                    # New attribute - insert with Type from data_model
                    value = None
                    attr_type = self.data_model.get_attribute_type_by_name(cluster, attribute) if self.data_model else "unknown"

                    cursor.execute("""
                    INSERT INTO Attribute (NodeID, Endpoint, Cluster, Attribute, Type, Value)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """, (node_id, endpoint, cluster, attribute, attr_type, value))
                    conn.commit()

                    self.logger.info(f"Inserted new attribute: NodeID={node_id}, Endpoint={endpoint}, "
                                   f"Cluster={cluster}, Attribute={attribute}, Type={attr_type}, Value={value}")
                    return True

        except sqlite3.Error as e:
            self.logger.error(f"Insert/Update error: {e}")
            return False

    def delete_device(self, node_id: int, endpoint: int) -> bool:
        """
        Delete device by node ID and endpoint.

        Args:
            node_id: Node ID
            endpoint: Endpoint ID

        Returns:
            True if successful, False otherwise
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                DELETE FROM Device WHERE NodeID = ? AND Endpoint = ?
                """, (node_id, endpoint))
                conn.commit()
                self.logger.info(f"Deleted device: NodeID={node_id}, Endpoint={endpoint}")
                return True
        except sqlite3.Error as e:
            self.logger.error(f"Delete error: {e}")
            return False

    def close(self):
        """Close database connection if open."""
        if self._connection:
            self._connection.close()
            self._connection = None
            self.logger.info("Database connection closed")
