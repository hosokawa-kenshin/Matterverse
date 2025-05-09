import os
import re
import xml.etree.ElementTree as ET

def parse_cluster(cluster_elem):
    cluster = {
        "name": cluster_elem.findtext("name"),
        "domain": cluster_elem.findtext("domain"),
        "code": cluster_elem.findtext("code"),
        "define": cluster_elem.findtext("define"),
        "description": cluster_elem.findtext("description"),
        "attributes": [],
        "commands": [],
        "events": [],
    }

    for attr in cluster_elem.findall("attribute"):
        cluster["attributes"].append({
            "code": attr.get("code"),
            "name": attr.text.strip() if attr.text else None,
            "type": attr.get("type"),
            "define": attr.get("define"),
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

def parse_clusters_from_directory(xml_dir):
    clusters = {}

    for filename in os.listdir(xml_dir):
        if filename.endswith(".xml"):
            path = os.path.join(xml_dir, filename)
            tree = ET.parse(path)
            root = tree.getroot()
            for cluster_elem in root.findall("cluster"):
                cluster = parse_cluster(cluster_elem)
                clusters[cluster["code"]] = cluster

    return clusters