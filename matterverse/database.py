import sqlite3

_conn = None
_cursor = None

def get_database_connection():
    global _conn, _cursor
    if _conn is None or _cursor is None:
        _conn = sqlite3.connect('./db/matterverse.db', check_same_thread=False)
        _cursor = _conn.cursor()

        _cursor.execute('''
        CREATE TABLE IF NOT EXISTS Device (
            NodeID INTEGER,
            Endpoint INTEGER,
            DeviceType INTEGER,
            TopicID TEXT,
            PRIMARY KEY (NodeID, Endpoint)
        )
        ''')

        _cursor.execute('''
        CREATE TABLE IF NOT EXISTS UniqueID (
            NodeID INTEGER,
            Name TEXT,
            UniqueID TEXT,
            PRIMARY KEY (NodeID)
        )
        ''')

        _conn.commit()

        print("\033[1;36mSQL \033[0m:     Database initialized")
    return _conn, _cursor

def get_devices_from_database():
    conn, cursor = get_database_connection()
    try:
        cursor.execute("""
        SELECT NodeID, Endpoint, DeviceType, TopicID FROM Device
        """)
        devices = cursor.fetchall()
        devices_list = []
        for device in devices:
            devices_list.append(
                {
                    "NodeID": device[0],
                    "Endpoint": device[1],
                    "DeviceType": device[2],
                    "TopicID": device[3],
                })
        return devices_list
    except sqlite3.Error as e:
        print(f"\033[1;36mSQL \033[0m:     Query Error:", e)
        return []

def get_device_by_topic_id(topic_id):
    conn, cursor = get_database_connection()
    try:
        cursor.execute("""
        SELECT NodeID, Endpoint, DeviceType FROM Device WHERE TopicID = ?
        """, (topic_id,))
        device = cursor.fetchone()
        if device:
            return {
                "NodeID": device[0],
                "Endpoint": device[1],
                "DeviceType": device[2],
                "TopicID": topic_id,
            }
        else:
            return None
    except sqlite3.Error as e:
        print(f"\033[1;36mSQL \033[0m:     Query Error:", e)
        return None

def get_device_by_node_id_endpoint(node_id, endpoint):
    conn, cursor = get_database_connection()
    try:
        cursor.execute("""
        SELECT NodeID, Endpoint, DeviceType, TopicID FROM Device WHERE NodeID = ? AND Endpoint = ?
        """, (node_id, endpoint))
        device = cursor.fetchone()
        if device:
            return {
                "NodeID": device[0],
                "Endpoint": device[1],
                "DeviceType": device[2],
                "TopicID": device[3],
            }
        else:
            return None
    except sqlite3.Error as e:
        print(f"\033[1;36mSQL \033[0m:     Query Error:", e)
        return None

def get_endpoints_by_node_id(node_id):
    conn, cursor = get_database_connection()
    try:
        cursor.execute("""
        SELECT Endpoint FROM Device WHERE NodeID = ?
        """, (node_id,))
        endpoints = [row[0] for row in cursor.fetchall()]
        return endpoints
    except sqlite3.Error as e:
        print(f"\033[1;36mSQL \033[0m:     Query Error:", e)
        return []

def insert_unique_id_to_database(node_id, device_name, unique_id):
    conn, cursor = get_database_connection()
    try:
        cursor.execute("""
        INSERT INTO UniqueID (NodeID, Name, UniqueID)
        VALUES (?, ?, ?)
        """, (node_id, device_name, unique_id))
        conn.commit()
        print(f"\033[1;36mSQL \033[0m:     Insert unique id infomation to database",(node_id, device_name, unique_id))
    except sqlite3.IntegrityError as e:
        print(f"\033[1;36mSQL \033[0m:     Insert Error:", e)

def get_new_node_id_from_database():
    conn, cursor = get_database_connection()
    try:
        cursor.execute("""
        SELECT NodeID FROM Device
        """)
        node_ids = [row[0] for row in cursor.fetchall()]
        if node_ids:
            return max(node_ids) + 1
        else:
            return 1
    except sqlite3.Error as e:
        print(f"\033[1;36mSQL \033[0m:     Query Error:", e)
        return None

def insert_device_to_database(node_id, endpoint, device_type, topic):
    conn, cursor = get_database_connection()
    try:
        cursor.execute("""
        INSERT INTO Device (NodeID, Endpoint, DeviceType, TopicID)
        VALUES (?, ?, ?, ?)
        """, (node_id, endpoint, device_type, topic))
        conn.commit()
        print(f"\033[1;36mSQL \033[0m:     Insert device infomation to database",(node_id, endpoint, device_type, topic))
    except sqlite3.IntegrityError as e:
        print(f"\033[1;36mSQL \033[0m:     Insert Error:", e)

def close_database_connection():
    global _conn, _cursor
    if _conn:
        _conn.close()
        _conn = None
        _cursor = None
        print("\033[1;36mSQL \033[0m:     Database connection closed")
    else:
        print("\033[1;36mSQL \033[0m:     No database connection to close")
