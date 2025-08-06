"""
Data model dictionary management for Matterverse application.
Handles XML parsing and data model management for Matter clusters and device types.
"""
import os
import re
from typing import Dict, List, Any, Optional
import xml.etree.ElementTree as ET

from logger import get_api_logger


class DataModelDictionary:
    """Manager for Matter data model information from XML files."""

    def __init__(self):
        """Initialize data model dictionary."""
        self.logger = get_api_logger()
        self._clusters: List[Dict[str, Any]] = []
        self._device_types: List[Dict[str, Any]] = []
        self._enums: List[Dict[str, Any]] = []

    @property
    def clusters(self) -> List[Dict[str, Any]]:
        """Get all clusters."""
        return self._clusters

    @property
    def device_types(self) -> List[Dict[str, Any]]:
        """Get all device types."""
        return self._device_types

    @property
    def enums(self) -> List[Dict[str, Any]]:
        """Get all enums."""
        return self._enums

    def parse_clusters_from_directory(self, xml_dir: str) -> bool:
        """
        Parse cluster information from XML directory.

        Args:
            xml_dir: Directory containing cluster XML files

        Returns:
            True if successful, False otherwise
        """
        try:
            clusters = []
            enums = []
            bitmaps = []
            structs = []

            for filename in os.listdir(xml_dir):
                if filename.endswith(".xml"):
                    path = os.path.join(xml_dir, filename)
                    file_clusters, file_enums, file_structs, file_bitmaps = self._parse_cluster_file(path)
                    clusters.extend(file_clusters)
                    enums.extend(file_enums)
                    structs.extend(file_structs)
                    bitmaps.extend(file_bitmaps)

            # Process and filter clusters
            # self._clusters = self._filter_clusters(clusters)
            self._clusters = clusters
            self._enums = enums
            self._structs = structs
            self._bitmaps = bitmaps

            # Associate enums with clusters
            self._associate_enums_with_clusters()

            self.logger.info(f"Parsed {len(self._clusters)} clusters from {xml_dir}")
            return True

        except Exception as e:
            self.logger.error(f"Error parsing clusters: {e}")
            return False

    def parse_device_types_from_file(self, xml_file: str) -> bool:
        """
        Parse device type information from XML file.

        Args:
            xml_file: Path to device types XML file

        Returns:
            True if successful, False otherwise
        """
        try:
            tree = ET.parse(xml_file)
            root = tree.getroot()

            device_types = []
            for device_type_elem in root.findall('deviceType'):
                device_type = self._parse_device_type(device_type_elem)
                if device_type:
                    device_types.append(device_type)

            # Filter device types based on available clusters
            # self._device_types = self._filter_device_types(device_types)
            self._device_types = device_types

            self.logger.info(f"Parsed {len(self._device_types)} device types from {xml_file}")
            return True

        except Exception as e:
            self.logger.error(f"Error parsing device types: {e}")
            return False

    def _parse_cluster_file(self, xml_file: str) -> tuple[List[Dict], List[Dict]]:
        """Parse clusters and enums from a single XML file."""
        tree = ET.parse(xml_file)
        root = tree.getroot()

        clusters = []
        enums = []
        bitmaps = []
        structs = []

        for cluster_elem in root.findall("cluster"):
            cluster = self._parse_cluster(cluster_elem)
            if cluster:
                clusters.append(cluster)

        for enum_elem in root.findall("enum"):
            enum = self._parse_enum(enum_elem)
            if enum:
                enums.append(enum)

        for struct_elem in root.findall("struct"):
            struct = self._parse_struct(struct_elem)
            if struct:
                structs.append(struct)

        for bitmap_elem in root.findall("bitmap"):
            bitmap = self._parse_bitmap(bitmap_elem)
            if bitmap:
                bitmaps.append(bitmap)

        return clusters, enums, structs, bitmaps

    def _parse_cluster(self, cluster_elem) -> Optional[Dict[str, Any]]:
        """Parse cluster information from XML element."""
        cluster = {
            "name": cluster_elem.findtext("name"),
            "id": cluster_elem.findtext("code", "").lower(),
            "attributes": [],
            "enums": [],
            "bitmaps": [],
            "commands": [],
            "events": [],
        }

        # Parse attributes
        for attr in cluster_elem.findall("attribute"):
            cluster["attributes"].append({
                "code": attr.get("code", "").lower(),
                "name": self._convert_to_camel_case(attr.get("define")) if attr.get("define") else None,
                "type": attr.get("type"),
                "define": attr.get("define"),
                "writable": attr.get("writable", "false"),
                "optional": attr.get("optional", "false"),
                "side": attr.get("side"),
            })

        # Parse commands
        for cmd in cluster_elem.findall("command"):
            command = {
                "code": cmd.get("code"),
                "name": cmd.get("name"),
                "source": cmd.get("source"),
                "args": [],
            }
            for arg in cmd.findall("arg"):
                command["args"].append({
                    "name": arg.get("name"),
                    "type": arg.get("type"),
                })
            cluster["commands"].append(command)

        return cluster

    def _parse_enum(self, enum_elem) -> Optional[Dict[str, Any]]:
        """Parse enum information from XML element."""
        enum_data = {
            "name": enum_elem.get("name"),
            "type": enum_elem.get("type"),
            "clusters": [],
            "items": [],
        }

        # Parse cluster associations
        for cluster in enum_elem.findall("cluster"):
            enum_data["clusters"].append({
                "id": cluster.get("code", "").lower(),
            })

        # Parse enum items
        for item in enum_elem.findall("item"):
            value_str = item.get("value", "0")
            if value_str.startswith("0x"):
                value = int(value_str, 16)
            else:
                value = int(value_str)

            enum_data["items"].append({
                "name": item.get("name"),
                "value": value,
            })

        return enum_data

    def _parse_struct(self, struct_elem) -> Optional[Dict[str, Any]]:
        """Parse struct information from XML element."""
        struct_data = {
            "name": struct_elem.get("name"),
            "api_maturity": struct_elem.get("apiMaturity"),
            "clusters": [],
            "fields": []
        }

        for cluster in struct_elem.findall("cluster"):
            struct_data["clusters"].append({
                "id": cluster.get("code", "").lower(),
            })

        for item in struct_elem.findall("item"):
            field_data = self._parse_struct_field(item)
            if field_data:
                struct_data["fields"].append(field_data)

        return struct_data if struct_data["name"] else None

    def _parse_struct_field(self, item_elem) -> Optional[Dict[str, Any]]:
        """Parse struct field information from XML element."""
        field_data = {
            "field_id": self._parse_int_value(item_elem.get("fieldId", "0")),
            "name": item_elem.get("name"),
            "type": item_elem.get("type"),
            "optional": item_elem.get("optional") == "true",
            "nullable": item_elem.get("isNullable") == "true",
            "default": item_elem.get("default"),
            "min": self._parse_int_value(item_elem.get("min")) if item_elem.get("min") else None,
            "max": self._parse_int_value(item_elem.get("max")) if item_elem.get("max") else None,
            "length": self._parse_int_value(item_elem.get("length")) if item_elem.get("length") else None
        }

        field_data = {k: v for k, v in field_data.items() if v is not None and v != ""}

        return field_data if field_data.get("name") else None

    def _parse_int_value(self, value_str: str) -> Optional[int]:
        """Parse integer value from string (supports hex)."""
        if not value_str:
            return None

        try:
            if value_str.startswith("0x"):
                return int(value_str, 16)
            else:
                return int(value_str)
        except ValueError:
            return None

    def _parse_bitmap(self, bitmap_elem) -> Optional[Dict[str, Any]]:
        """Parse bitmap information from XML element."""
        bitmap_data = {
            "name": bitmap_elem.get("name"),
            "clusters": [],
            "type": bitmap_elem.get("type"),
            "fields": [],
        }

        for cluster in bitmap_elem.findall("cluster"):
            bitmap_data["clusters"].append({
                "id": cluster.get("code", "").lower(),
            })

        for field in bitmap_elem.findall("field"):
            mask_str = field.get("mask", "0")
            if mask_str.startswith("0x"):
                mask = int(mask_str, 16)
            else:
                mask = int(mask_str)

            bitmap_data["fields"].append({
                "name": field.get("name"),
                "mask": mask,
            })

        return bitmap_data

    def _parse_device_type(self, device_type_elem) -> Optional[Dict[str, Any]]:
        """Parse device type information from XML element."""
        device_info = {}

        device_id_elem = device_type_elem.find('deviceId')
        if device_id_elem is not None:
            device_info['id'] = device_id_elem.text.lower()

        name_elem = device_type_elem.find('typeName')
        if name_elem is not None:
            device_info['name'] = name_elem.text

        clusters_elem = device_type_elem.find('clusters')
        if clusters_elem is not None:
            cluster_list = []
            for include in clusters_elem.findall('include'):
                cluster = include.get('cluster')
                server_locked = include.get('serverLocked') == 'true'
                if cluster and server_locked:
                    cluster_list.append(cluster)
            device_info['clusters'] = cluster_list

        return device_info if device_info else None

    def _filter_clusters(self, clusters: List[Dict]) -> List[Dict]:
        """Filter clusters based on supported attribute types."""
        filtered_clusters = []

        for cluster in clusters:
            attributes = cluster.get('attributes', [])
            filtered_attributes = []

            for attr in attributes:
                attribute_type = attr.get('type', '')

                # Filter by supported types
                supported_types = ['int', 'bool', 'string', 'Bitmap', 'Enum', 'array','Struct']
                if 'Struct' in attribute_type:
                    print(f"Skipping struct type attribute: {attr.get('name')}")
                if any(t in attribute_type for t in supported_types):
                    filtered_attributes.append(attr)

            # Skip clusters with no supported attributes
            if not filtered_attributes:
                continue

            filtered_cluster = {
                "id": cluster.get('id', '').lower(),
                "name": cluster.get('name', 'Unknown Cluster'),
                "attributes": filtered_attributes,
                "enums": cluster.get('enums', []),
                "bitmaps": cluster.get('bitmaps', []),
                "structs": cluster.get('structs', []),
                "commands": cluster.get('commands', [])
            }
            filtered_clusters.append(filtered_cluster)

        return filtered_clusters

    def _filter_device_types(self, device_types: List[Dict]) -> List[Dict]:
        """Filter device types based on available clusters."""
        filtered_device_types = []
        available_cluster_names = {cluster.get("name") for cluster in self._clusters}

        for device_type in device_types:
            clusters = device_type.get('clusters', [])
            filtered_clusters = [
                cluster for cluster in clusters
                if cluster in available_cluster_names
            ]

            if filtered_clusters:
                filtered_device_types.append({
                    "id": device_type.get('id', 'Unknown ID'),
                    "name": device_type.get('name', 'Unknown Device Type'),
                    "clusters": filtered_clusters
                })

        return filtered_device_types

    def _associate_enums_with_clusters(self):
        """Associate enums with their corresponding clusters."""
        for enum in self._enums:
            include_clusters = enum.get("clusters", [])
            for include_cluster in include_clusters:
                for cluster in self._clusters:
                    if include_cluster.get("id") == cluster.get("id"):
                        cluster["enums"].append(enum)
        for bitmap in self._bitmaps:
            include_clusters = bitmap.get("clusters", [])
            for include_cluster in include_clusters:
                for cluster in self._clusters:
                    if include_cluster.get("id") == cluster.get("id"):
                        cluster.setdefault("bitmaps", []).append(bitmap)
        for struct in self._structs:
            include_clusters = struct.get("clusters", [])
            for include_cluster in include_clusters:
                for cluster in self._clusters:
                    if include_cluster.get("id") == cluster.get("id"):
                        cluster.setdefault("structs", []).append(struct)

    def _convert_to_camel_case(self, snake_str: str) -> str:
        """Convert snake_case to CamelCase."""
        components = snake_str.split('_')
        return ''.join(x.title() for x in components)

    # Utility methods for data access
    def get_cluster_by_name(self, name: str) -> Optional[Dict[str, Any]]:
        """Get cluster by name."""
        return next((cluster for cluster in self._clusters if cluster.get("name") == name), None)

    def get_cluster_by_id(self, cluster_id: str) -> Optional[Dict[str, Any]]:
        """Get cluster by ID."""
        return next((cluster for cluster in self._clusters if cluster.get("id") == cluster_id), None)

    def get_cluster_id_by_name(self, name: str) -> Optional[str]:
        """Get cluster ID by name."""
        cluster = self.get_cluster_by_name(name)
        return cluster.get("id") if cluster else None

    def get_device_type_by_id(self, device_type_id: str) -> Optional[Dict[str, Any]]:
        """Get device type by ID."""
        return next((dt for dt in self._device_types if dt.get("id") == device_type_id), None)

    def get_clusters_by_device_type(self, device_type_id: str) -> List[str]:
        """Get cluster names for a device type."""
        device_type = self.get_device_type_by_id(device_type_id)
        return device_type.get("clusters", []) if device_type else []

    def get_attributes_by_cluster_name(self, cluster_name: str) -> List[Dict[str, Any]]:
        """Get attributes for a cluster."""
        cluster = self.get_cluster_by_name(cluster_name)
        return cluster.get("attributes", []) if cluster else []

    def get_enums_by_cluster_name(self, cluster_name: str) -> List[Dict[str, Any]]:
        """Get enums for a cluster."""
        cluster = self.get_cluster_by_name(cluster_name)
        return cluster.get("enums", []) if cluster else []

    def get_cluster_name_by_id(self, cluster_id: str) -> Optional[str]:
        """Get cluster name by ID."""
        cluster = self.get_cluster_by_id(cluster_id)
        return cluster.get("name") if cluster else None

    def get_attribute_name_by_code(self, cluster_id: str, attribute_code: str) -> Optional[str]:
        """Get attribute name by cluster ID and attribute code."""
        cluster = self.get_cluster_by_id(cluster_id)
        if cluster:
            for attribute in cluster.get("attributes", []):
                if attribute.get("code") == attribute_code:
                    return attribute.get("name")
        return None

    def get_attribute_code_by_name(self, cluster_id: str, attribute_name: str) -> Optional[str]:
        """Get attribute code by cluster ID and attribute name."""
        cluster = self.get_cluster_by_id(cluster_id)
        if cluster:
            for attribute in cluster.get("attributes", []):
                if attribute.get("name") == attribute_name:
                    return attribute.get("code")
        return None

    def get_command_name_by_code(self, cluster_id: str, command_code: str) -> Optional[str]:
        """
        Get command name by cluster ID and command code.

        Args:
            cluster_id: Cluster ID (e.g., "0x0202")
            command_code: Command code (e.g., "0x00")

        Returns:
            Command name or None if not found
        """
        try:
            # Normalize IDs to lowercase for comparison
            cluster_id = cluster_id.lower()
            command_code = command_code.lower()

            # Search through all clusters
            for cluster in self._clusters:
                if cluster.get("id", "").lower() == cluster_id:
                    # Search through commands in this cluster
                    commands = cluster.get("commands", [])
                    for command in commands:
                        if command.get("code", "").lower() == command_code:
                            return command.get("name")

            for cluster in self.clusters:
                if cluster.get("id", "").lower() == cluster_id:
                    commands = cluster.get("commands", [])
                    for command in commands:
                        if command.get("code", "").lower() == command_code:
                            return command.get("name")

            return None

        except Exception as e:
            self.logger.error(f"Error getting command name: {e}")
            return None
