import os
import re
import xml.etree.ElementTree as ET

def parse_device_type_info(xml_file):
    tree = ET.parse(xml_file)
    root = tree.getroot()

    results = []

    for device_type in root.findall('deviceType'):
        device_info = {}
        device_id = device_type.find('deviceId')
        if device_id is not None:
            device_info['id'] = device_id.text

        name = device_type.find('name')
        if name is not None:
            device_info['name'] = name.text

        clusters = device_type.find('clusters')
        if clusters is not None:
            cluster_list = []
            for include in clusters.findall('include'):
                cluster = include.get('cluster')
                if cluster:
                    cluster_list.append(cluster)
            device_info['clusters'] = cluster_list

        results.append(device_info)

    return results

def parse_cluster_info(cluster_elem):
    cluster = {
        "name": cluster_elem.findtext("name"),
        "id": cluster_elem.findtext("code"),
        "attributes": [],
        "commands": [],
        "events": [],
    }

    for attr in cluster_elem.findall("attribute"):
        cluster["attributes"].append({
            "code": attr.get("code"),
            "name": attr.text if attr.text else None,
            "type": attr.get("type").lower() if attr.get("type") else None,
            "define": attr.get("define"),
            "side": attr.get("side"),
        }) if attr.get("code").startswith("0x0") else None

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

    all_clusters = []
    for filename in os.listdir(xml_dir):
        if filename.endswith(".xml"):
            path = os.path.join(xml_dir, filename)
            tree = ET.parse(path)
            root = tree.getroot()
            for cluster_elem in root.findall("cluster"):
                cluster = parse_cluster_info(cluster_elem)
                all_clusters.append(cluster)

    return all_clusters