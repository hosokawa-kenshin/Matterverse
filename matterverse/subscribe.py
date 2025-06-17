import os
import re
import asyncio
from database import get_devices_from_database, get_devices_by_node_id
from matter_utils import get_cluster_by_device_type
import json

async def subscribe_device(node_id):
    devices = get_devices_by_node_id(node_id)
    if devices is None or len(devices) == 0:
        return
    await subscribe_devices(devices)

async def subscribe_alldevices():
    print("\033[1;34mCHIP\033[0m:     Subscribing to all devices...")
    devices = get_devices_from_database()
    await subscribe_devices(devices)

async def subscribe_devices(devices):
    for device in devices:
        node = device.get("NodeID")
        endpoint = device.get("Endpoint")
        device_type = device.get("DeviceType")
        device_type = f"0x{int(device_type):04x}"
        clusters = get_cluster_by_device_type(device_type)
        from matter_xml_parser import all_clusters
        for cluster in clusters:
            cluster_info = next((item for item in all_clusters if item.get("name") == cluster), None)
            if cluster_info:
                attributes = cluster_info.get("attributes", [])
                for attribute in attributes:
                    attribute_name = attribute.get("name")
                    if attribute_name != '':
                        attribute_name = re.sub(r'(?<!^)(?<![A-Z])(?=[A-Z])', '-', attribute_name).lower()
                        cluster_name = cluster.lower().replace("/", "")
                        cluster_name = cluster_name.replace(" ", "")
                        command = f"{cluster_name} subscribe {attribute_name} 1 100 {node} {endpoint}"
                        from chip_tool_server import run_chip_tool_command
                        from chip_tool_server import response_queue
                        await run_chip_tool_command(command)
                        while True:
                            print(f"\033[1;34mCHIP\033[0m:     Waiting for response for NodeID: {node}, Endpoint: {endpoint}, Cluster: {cluster_name}, Attribute: {attribute_name}")
                            try:
                                json_str = await asyncio.wait_for(response_queue.get(), timeout=5)
                            except asyncio.TimeoutError:
                                print(f"\033[1;31mCHIP\033[0m:     Timeout waiting for response for NodeID: {node}, Endpoint: {endpoint}, Cluster: {cluster_name}, Attribute: {attribute_name}")
                                break
                            json_data = json.loads(json_str)
                            if "ReportDataMessage" not in json_data or "AttributeReportIBs" not in json_data["ReportDataMessage"]:
                                break
                            node_id = json_data["ReportDataMessage"]["AttributeReportIBs"][0]["AttributeReportIB"]["AttributeDataIB"]["AttributePathIB"]["NodeID"]
                            endpoint_id = json_data["ReportDataMessage"]["AttributeReportIBs"][0]["AttributeReportIB"]["AttributeDataIB"]["AttributePathIB"]["Endpoint"]
                            cluster_code = json_data["ReportDataMessage"]["AttributeReportIBs"][0]["AttributeReportIB"]["AttributeDataIB"]["AttributePathIB"]["Cluster"]
                            attribute_code = json_data["ReportDataMessage"]["AttributeReportIBs"][0]["AttributeReportIB"]["AttributeDataIB"]["AttributePathIB"]["Attribute"]
                            cluster_code = f"0x{int(cluster_code):04x}"
                            attribute_code = f"0x{int(attribute_code):04x}"
                            if node == node_id and endpoint == endpoint_id and cluster_info.get("id") == cluster_code and attribute.get("code") == attribute_code:
                                print(f"\033[1;34mCHIP\033[0m:     Subscribe executed for NodeID: {node}, Endpoint: {endpoint}, Cluster: {cluster_name}, Attribute: {attribute_name}")
                                await asyncio.sleep(0.1)
                                break
        print(f"\033[1;34mCHIP\033[0m:     Subscribed to all attributes for NodeID: {node}, Endpoint: {endpoint}, DeviceType: {device_type}")