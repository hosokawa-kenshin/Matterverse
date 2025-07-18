import os
import re
import xml.etree.ElementTree as ET

def create_devicetypes_dict(devicetypes):
    devicetypes_dict = []
    for device_type in devicetypes:
        devicetypes_dict.append(create_devicetype_dict(device_type))
    return devicetypes_dict

def create_devicetype_dict(devicetype):
    name = devicetype.get('name', 'Unknown Device Type')
    device_id = devicetype.get('id', 'Unknown ID').lower()
    clusters = devicetype.get('clusters', [])
    data = {
        "id": device_id,
        "name": name,
        "clusters": clusters
    }
    return data

def create_clusters_dict(clusters):
    clusters_dict = []
    for cluster in clusters:
        clusters_dict.append(create_cluster_dict(cluster))
    return clusters_dict

def create_cluster_dict(cluster):
    name = cluster.get('name', 'Unknown Cluster')
    cluster_id = cluster.get('id', 'Unknown ID').lower()
    attributes = cluster.get('attributes', [])
    commands = cluster.get('commands', [])
    bitmaps = cluster.get('bitmaps', [])
    data = {
        "id": cluster_id,
        "name": name,
        "attributes": attributes,
        "enums": [],
        "bitmaps": bitmaps,
        "commands": commands
    }
    return data

def filter_clusters(clusters_dict):
    filtered_clusters = []
    for cluster in clusters_dict:
        attributes = cluster.get('attributes', 'Unknown Type')
        filtered_attributes = []
        for attr in attributes:
            attribute_type = attr.get('type')
            optional = attr.get('optional', 'false')
            if optional == 'true':
                continue
            if not "Enum" in attribute_type and not "enum" in attribute_type and not "int" in attribute_type and not "bool" in attribute_type and not "string" in attribute_type:
                continue
            filtered_attributes.append(attr)
        if not filtered_attributes:
            continue
        cluster_name = cluster.get('name', 'Unknown Cluster')
        cluster_id = cluster.get('id', 'Unknown ID').lower()
        cluster_enums = cluster.get('enums', [])
        commands = cluster.get('commands', [])
        bitmaps = cluster.get('bitmaps', [])
        filtered_cluster = {
            "id": cluster_id,
            "name": cluster_name,
            "attributes": filtered_attributes,
            "enums": cluster_enums,
            "bitmaps": bitmaps,
            "commands": commands
        }
        filtered_clusters.append(filtered_cluster)

    return filtered_clusters

def filter_devicetypes(devicetypes_dict, clusters_dict):
    filtered_devicetypes = []
    for devicetype in devicetypes_dict:
        filtered_clusters = []
        clusters = devicetype.get('clusters', [])
        for cluster in clusters:
            if not any(item.get("name") == cluster for item in clusters_dict):
                continue
            filtered_clusters.append(cluster)
        if not filtered_clusters:
            continue
        devicetype_id = devicetype.get('id', 'Unknown ID')
        devicetype_name = devicetype.get('name', 'Unknown Device Type')
        filtered_devicetypes.append({
            "id": devicetype_id,
            "name": devicetype_name,
            "clusters": filtered_clusters
        })
    return filtered_devicetypes

def parse_device_type_info(xml_file):
    global all_clusters
    global all_devicetypes
    tree = ET.parse(xml_file)
    root = tree.getroot()

    results = []

    for device_type in root.findall('deviceType'):
        device_info = {}
        device_id = device_type.find('deviceId')
        if device_id is not None:
            device_info['id'] = device_id.text.lower()

        name = device_type.find('name')
        if name is not None:
            device_info['name'] = name.text

        clusters = device_type.find('clusters')
        if clusters is not None:
            cluster_list = []
            for include in clusters.findall('include'):
                cluster = include.get('cluster') if include.get('serverLocked') == 'true' else None
                if cluster:
                    cluster_list.append(cluster)
            device_info['clusters'] = cluster_list

        results.append(device_info)
        temp_devicetypes = create_devicetypes_dict(results)
        all_devicetypes = filter_devicetypes(temp_devicetypes, all_clusters)
    return all_devicetypes

def convert_to_camel_case(snake_str):
    components = snake_str.split('_')
    return ''.join(x.title() for x in components)

def parse_enum(enum_elem):
    enum_data = {
        "name": enum_elem.get("name"),
        "type": enum_elem.get("type"),
        "clusters": [],
        "items": [],
    }

    for cluster in enum_elem.findall("cluster"):
        enum_data["clusters"].append({
            "id": cluster.get("code").lower(),
        })

    for item in enum_elem.findall("item"):
        enum_data["items"].append({
            "name": item.get("name"),
            "value": int(item.get("value"), 16) if item.get("value").startswith("0x") else int(item.get("value")),
        })
    return enum_data

def parse_bitmap(bitmap_elem):
    bitmap_data = {
        "name": bitmap_elem.get("name"),
        "type": bitmap_elem.get("type"),
        "fields": [],
    }
    for field in bitmap_elem.findall("field"):
        bitmap_data["fields"].append({
            "name": field.get("name"),
            "mask": int(field.get("mask"), 16) if field.get("mask").startswith("0x") else int(field.get("mask")),
        })
    return bitmap_data

def parse_cluster_info(cluster_elem):
    cluster = {
        "name": cluster_elem.findtext("name"),
        "id": cluster_elem.findtext("code").lower(),
        "attributes": [],
        "enums": [],
        "bitmaps": [],
        "commands": [],
        "events": [],
    }

    for attr in cluster_elem.findall("attribute"):
        cluster["attributes"].append({
            "code": attr.get("code").lower(),
            "name": convert_to_camel_case(attr.get("define")) if attr.get("define") else None,
            "type": attr.get("type") if attr.get("type") else None,
            "define": attr.get("define"),
            "writable": attr.get("writable") if attr.get("writable") else "false",
            "optional": attr.get("optional") if attr.get("optional") else "false",
            "side": attr.get("side"),
        })

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

def parse_clusters_info(xml_dir):
    global all_clusters

    clusters = []
    enums = []

    for filename in os.listdir(xml_dir):
        if filename.endswith(".xml"):
            path = os.path.join(xml_dir, filename)
            tree = ET.parse(path)
            root = tree.getroot()
            for cluster_elem in root.findall("cluster"):
                bitmaps = []
                cluster = parse_cluster_info(cluster_elem)
                for enum in root.findall("enum"):
                    enums.append(parse_enum(enum))
                for bitmap in root.findall("bitmap"):
                    bitmaps.append(parse_bitmap(bitmap))
                cluster["bitmaps"] = bitmaps
                clusters.append(cluster)
    temp_clusters = create_clusters_dict(clusters)
    all_clusters = filter_clusters(temp_clusters)
    for enum in enums:
        include_clusters = enum.get("clusters", [])
        for include_cluster in include_clusters:
            for all_cluster in all_clusters:
                if include_cluster.get("id") == all_cluster.get("id"):
                    all_cluster["enums"].append(enum)

    return all_clusters