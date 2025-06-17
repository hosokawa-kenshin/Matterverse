def get_enums_by_cluster_name(cluster):
    from matter_xml_parser import all_clusters
    cluster_info = next((item for item in all_clusters if item.get("name") == cluster), None)
    if cluster_info:
        enums = cluster_info.get("enums", [])
        return enums
    return []

def get_attributes_by_cluster_name(cluster):
    from matter_xml_parser import all_clusters
    cluster_info = next((item for item in all_clusters if item.get("name") == cluster), None)
    if cluster_info:
        attributes = cluster_info.get("attributes", [])
        return attributes
    return []

def get_cluster_name_by_code(cluster_code):
    from matter_xml_parser import all_clusters
    for cluster in all_clusters:
        if cluster.get("id") == cluster_code:
            return cluster.get("name")
    return None

def get_attribute_name_by_code(cluster_code, attribute_code):
    from matter_xml_parser import all_clusters
    for cluster in all_clusters:
        if cluster.get("id") == cluster_code:
            for attribute in cluster.get("attributes", []):
                if attribute.get("code") == attribute_code:
                    return attribute.get("name")
    return None

def get_cluster_by_device_type(device_type):
    from matter_xml_parser import all_devicetypes
    matched_item = next((item for item in all_devicetypes if item.get("id") == device_type), None)
    return matched_item.get("clusters", []) if matched_item else []
