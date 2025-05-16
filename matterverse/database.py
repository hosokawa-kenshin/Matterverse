import sqlite3

_conn = None
_cursor = None

def get_database_connection():
    global _conn, _cursor
    if _conn is None or _cursor is None:
        _conn = sqlite3.connect('./db/matterverse.db')
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
            UniqueID TEXT,
            PRIMARY KEY (NodeID)
        )
        ''')

        _conn.commit()

        print("\033[1;36mSQL \033[0m:     Database initialized")
    return _conn, _cursor

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

def insert_unique_id_to_database(node_id, unique_id):
    conn, cursor = get_database_connection()
    try:
        cursor.execute("""
        INSERT INTO UniqueID (NodeID, UniqueID)
        VALUES (?, ?)
        """, (node_id, unique_id))
        conn.commit()
        print(f"\033[1;36mSQL \033[0m:     Insert unique id infomation to database",(node_id, unique_id))
    except sqlite3.IntegrityError as e:
        print(f"\033[1;36mSQL \033[0m:     Insert Error:", e)

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
