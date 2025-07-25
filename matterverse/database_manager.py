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
        Get all devices from database.

        Returns:
            List of device dictionaries
        """
        try:
            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                SELECT NodeID, Endpoint, DeviceType, TopicID FROM Device
                """)
                rows = cursor.fetchall()
                return [dict(row) for row in rows]
        except sqlite3.Error as e:
            self.logger.error(f"Query error: {e}")
            return []

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
            response_endpoint = attr_path.get("Endpoint")
            response_cluster_id = attr_path.get("Cluster")
            response_cluster = self.data_model.get_cluster_name_by_id(f"0x{int(response_cluster_id):04x}")
            response_attribute_id = attr_path.get("Attribute")
            response_attribute = self.data_model.get_attribute_name_by_code(f"0x{int(response_cluster_id):04x}",f"0x{int(response_attribute_id):04x}")
            response_value = attr_data.get("Data", None)
            print(response_value)

            with self.get_connection() as conn:
                cursor = conn.cursor()
                cursor.execute("""
                INSERT INTO Attribute (NodeID, Endpoint, Cluster, Attribute, Value)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(NodeID, Endpoint, Cluster, Attribute) DO UPDATE SET Value = ?
                """, (response_node_id, response_endpoint, response_cluster, response_attribute, response_value, response_value))
                conn.commit()
                self.logger.info(f"Updated attribute: {parsed_json_str}")
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
                value = None
                cursor.execute("""
                INSERT INTO Attribute (NodeID, Endpoint, Cluster, Attribute, Value)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(NodeID, Endpoint, Cluster, Attribute) DO UPDATE SET Value = ?
                """, (node_id, endpoint, cluster, attribute, value, value))
                conn.commit()
                self.logger.info(f"Inserted/Updated attribute: NodeID={node_id}, Endpoint={endpoint}, Cluster={cluster}, Attribute={attribute}, Value={value}")
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
