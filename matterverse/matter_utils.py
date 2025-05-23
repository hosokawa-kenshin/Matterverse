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
    cluster_mapping = {
        "0x0016": [
            "Access Control", "Basic Information", "General Commissioning",
            "Power Source Configuration", "Time Synchronization", "Group Key Management",
            "Network Commissioning", "Administrator Commissioning", "Operational Credentials",
            "Localization Configuration", "Time Format Localization", "Unit Localization",
            "General Diagnostics", "Diagnostic Logs", "Software Diagnostics",
            "Ethernet Network Diagnostics", "Wi-Fi Network Diagnostics", "Thread Network Diagnostics",
            "ICD Management",
        ],
        "0x0011": ["Power Source"],
        "0x0510": [
            "Power Topology", "Electrical Energy Measurement", "Electrical Power Measurement",
        ],
        "0x0012": [
            "OTA Software Update Requestor", "OTA Software Update Provider",
        ],
        "0x0014": [
            "OTA Software Update Provider", "OTA Software Update Requestor",
        ],
        "0x000e": ["Actions"],
        "0x0013": [
            "Bridged Device Basic Information", "Power Source Configuration", "Power Source",
        ],
        "0x0100": ["On/Off"],
        "0x0101": ["On/Off", "Level Control"],
        "0x010C": ["On/Off", "Level Control", "Color Control"],
        "0x010D": ["On/Off", "Level Control", "Color Control"],
        "0x010A": ["On/Off"],
        "0x010B": ["On/Off", "Level Control"],
        "0x0303": [
            "On/Off", "Pump Configuration and Control", "Level Control", "Temperature Measurement",
            "Pressure Measurement", "Flow Measurement", "Occupancy Sensing",
        ],
        "0x0103": ["On/Off"],
        "0x0104": ["On/Off", "Level Control"],
        "0x0105": ["On/Off", "Level Control", "Color Control"],
        "0x0840": [
            "On/Off", "Level Control", "Color Control", "Illuminance Measurement", "Occupancy Sensing",
        ],
        "0x0304": [
            "On/Off", "Pump Configuration and Control", "Level Control", "Temperature Measurement",
            "Pressure Measurement", "Flow Measurement",
        ],
        "0x000f": ["Switch"],
        "0x0015": ["Boolean State"],
        "0x0106": ["Illuminance Measurement"],
        "0x0107": ["Occupancy Sensing"],
        "0x0302": ["Temperature Measurement"],
        "0x0305": ["Pressure Measurement"],
        "0x0306": ["Flow Measurement"],
        "0x0307": ["Relative Humidity Measurement"],
        "0x0850": ["On/Off"],
        "0x000A": ["Door Lock"],
        "0x000B": ["Door Lock"],
        "0x0202": ["Window Covering"],
        "0x0203": ["Window Covering"],
        "0x0300": ["Thermostat", "On/Off", "Level Control"],
        "0x0301": [
            "Thermostat", "Thermostat User Interface Configuration", "Fan Control",
            "Temperature Measurement", "Occupancy Sensing", "Relative Humidity Measurement",
        ],
        "0x002B": ["Fan Control"],
        "0x0023": [
            "Media Playback", "Keypad Input", "Application Launcher", "Media Input", "On/Off",
            "Channel", "Audio Output", "Low Power", "Wake on LAN", "Target Navigator",
            "Account Login", "Content Launcher",
        ],
        "0x0028": [
            "Media Playback", "Keypad Input", "Media Input", "On/Off", "Channel",
            "Audio Output", "Low Power", "Wake on LAN", "Target Navigator",
        ],
        "0x0029": [
            "Media Playback", "Content Launcher", "Keypad Input",
            "Account Login", "On/Off", "Level Control", "Wake on LAN", "Channel", "Target Navigator",
            "Media Input", "Low Power", "Audio Output", "Application Launcher", "Application Basic",
        ],
        "0x002A": [
            "Media Playback", "Content Launcher", "Keypad Input",
            "Account Login", "On/Off", "Level Control", "Wake on LAN", "Channel", "Target Navigator",
            "Media Input", "Low Power", "Audio Output", "Application Launcher",
        ],
        "0x0022": ["On/Off", "Level Control"],
        "0x0024": [
            "Application Basic", "Keypad Input", "Application Launcher",
            "Account Login", "Content Launcher", "Media Playback", "Target Navigator", "Channel",
        ],
        "0x0027": ["Mode Select"],
        "0x0072": [
            "On/Off", "Groups", "Scenes Management", "Thermostat",
            "Thermostat User Interface Configuration", "Fan Control", "Temperature Measurement",
            "Relative Humidity Measurement",
        ],
        "0x0076": [
            "Groups", "Smoke CO Alarm", "Relative Humidity Measurement",
            "Temperature Measurement", "Carbon Monoxide Concentration Measurement", "Power Source",
                    ],
        "0x002D": [
            "Groups", "Fan Control", "HEPA Filter Monitoring",
            "Activated Carbon Filter Monitoring",
        ],
        "0x002C": [
            "Air Quality", "Temperature Measurement",
            "Relative Humidity Measurement", "Carbon Monoxide Concentration Measurement",
            "Carbon Dioxide Concentration Measurement", "Nitrogen Dioxide Concentration Measurement",
            "Ozone Concentration Measurement", "Formaldehyde Concentration Measurement",
            "PM1 Concentration Measurement", "PM2.5 Concentration Measurement",
            "PM10 Concentration Measurement", "Radon Concentration Measurement",
            "Total Volatile Organic Compounds Concentration Measurement",
        ],
        "0x0075": [
            "On/Off", "Temperature Control", "Dishwasher Mode",
            "Dishwasher Alarm", "Operational State",
        ],
        "0x007B": [],
        "0x0079": [
            "Fan Control", "Microwave Oven Mode", "Microwave Oven Control",
            "Operational State",
        ],
        "0x0070": [
            "Refrigerator And Temperature Controlled Cabinet Mode",
            "Refrigerator Alarm",
        ],
        "0x0073": [
            "On/Off", "Laundry Washer Mode", "Laundry Washer Controls",
            "Temperature Control", "Operational State",
        ],
        "0x007C": [
            "On/Off", "Laundry Washer Mode", "Laundry Dryer Controls",
            "Temperature Control", "Operational State",
        ],
        "0x007A": [
            "HEPA Filter Monitoring", "Activated Carbon Filter Monitoring",
            "Fan Control",
        ],
        "0x0074": [
            "RVC Run Mode", "RVC Clean Mode", "RVC Operational State",
            "Service Area",
        ],
        "0x0071": [
            "Temperature Control", "Temperature Measurement",
            "Refrigerator And Temperature Controlled Cabinet Mode", "Oven Mode",
            "Oven Cavity Operational State",
        ],
        "0x0041": ["Boolean State", "Boolean State Configuration"],
        "0x0042": ["Valve Configuration and Control"],
        "0x0043": ["Boolean State", "Boolean State Configuration"],
        "0x0044": ["Boolean State", "Boolean State Configuration"],
        "0x0090": [
            "Thread Network Directory", "Wi-Fi Network Management",
            "Thread Border Router Management",
        ],
        "0x0091": ["Thread Network Diagnostics", "Thread Border Router Management"],
        "0xFFF10003": [
            "Color Control", "Door Lock", "Groups",
            "Level Control", "On/Off", "Scenes Management", "Temperature Measurement",
        ],
        "0x0019": [
            "Network Commissioning", "Ethernet Network Diagnostics",
            "Wi-Fi Network Diagnostics", "Thread Network Diagnostics",
        ],
        "0x0078": ["On/Off"],
        "0x0077": ["On/Off", "Temperature Control", "Temperature Measurement"],
        "0x050C": [
            "Energy EVSE", "Energy EVSE Mode", "Temperature Measurement",
        ],
    }
    return cluster_mapping.get(device_type, "unknown")