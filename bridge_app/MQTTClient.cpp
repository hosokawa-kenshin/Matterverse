#include "MQTTClient.h"
#include <chrono>
#include <lib/support/logging/CHIPLogging.h>
#include <platform/CHIPDeviceLayer.h>
#include <regex>
#include <sstream>

using namespace chip::DeviceLayer;

namespace mqtt {

// Implementation of HomieMessage::ParseTopic
bool HomieMessage::ParseTopic(const std::string & topic)
{
    // Expected format: homie/TopicID/ClusterName/AttributeName[/PropertyType]
    std::regex pattern(R"(^homie/([^/]+)(?:/([^/]+))?(?:/([^/]+))?(?:/(\$[^/]+))?$)");
    std::smatch matches;

    if (std::regex_match(topic, matches, pattern))
    {
        device_id = matches[1].str();

        if (matches[2].matched)
        {
            cluster_name = matches[2].str();
        }

        if (matches[3].matched)
        {
            attribute_name = matches[3].str();
        }

        if (matches[4].matched)
        {
            property_type = matches[4].str();
        }
        else if (!cluster_name.empty() && attribute_name.empty())
        {
            // This is likely a cluster property like $name, $properties
            property_type = cluster_name;
            cluster_name  = "";
        }
        else if (!attribute_name.empty() && attribute_name[0] == '$')
        {
            // This is a device-level property
            property_type  = attribute_name;
            attribute_name = "";
        }

        return true;
    }

    return false;
}

MQTTClient::MQTTClient(const Config & config) : m_config(config), m_mosq(nullptr), m_running(false), m_db(nullptr)
{
    // Mosquitto library initialization
    mosquitto_lib_init();

    // Initialize SQLite database
    if (!InitializeDatabase())
    {
        ChipLogError(DeviceLayer, "Failed to initialize SQLite database");
    }

    // Create mosquitto client
    m_mosq = mosquitto_new(m_config.client_id.c_str(), m_config.clean_session, this);
    if (!m_mosq)
    {
        ChipLogError(DeviceLayer, "Failed to create mosquitto client");
        return;
    }

    // Set callbacks
    mosquitto_connect_callback_set(m_mosq, OnConnect);
    mosquitto_disconnect_callback_set(m_mosq, OnDisconnect);
    mosquitto_message_callback_set(m_mosq, OnMessage);

    // Set username/password if provided
    if (!m_config.username.empty())
    {
        mosquitto_username_pw_set(m_mosq, m_config.username.c_str(),
                                  m_config.password.empty() ? nullptr : m_config.password.c_str());
    }

    ChipLogProgress(DeviceLayer, "MQTT Client created with ID: %s", m_config.client_id.c_str());
}

MQTTClient::~MQTTClient()
{
    StopAsync();

    if (m_mosq)
    {
        mosquitto_destroy(m_mosq);
    }
    mosquitto_lib_cleanup();

    if (m_db)
    {
        sqlite3_close(m_db);
    }
}

bool MQTTClient::Connect()
{
    if (!m_mosq)
    {
        ChipLogError(DeviceLayer, "MQTT client not initialized");
        return false;
    }

    int result = mosquitto_connect(m_mosq, m_config.broker_host.c_str(), m_config.broker_port, m_config.keepalive);
    if (result != MOSQ_ERR_SUCCESS)
    {
        ChipLogError(DeviceLayer, "Failed to connect to MQTT broker: %s", mosquitto_strerror(result));
        return false;
    }

    ChipLogProgress(DeviceLayer, "Connecting to MQTT broker at %s:%d", m_config.broker_host.c_str(), m_config.broker_port);
    return true;
}

bool MQTTClient::Disconnect()
{
    if (!m_mosq)
    {
        return false;
    }

    int result = mosquitto_disconnect(m_mosq);
    if (result != MOSQ_ERR_SUCCESS)
    {
        ChipLogError(DeviceLayer, "Failed to disconnect from MQTT broker: %s", mosquitto_strerror(result));
        return false;
    }

    ChipLogProgress(DeviceLayer, "Disconnected from MQTT broker");
    return true;
}

bool MQTTClient::IsConnected() const
{
    // Note: This is a simple check, in practice you might want to track connection state
    return m_mosq != nullptr;
}

bool MQTTClient::Subscribe(const std::string & topic, int qos)
{
    if (!m_mosq)
    {
        ChipLogError(DeviceLayer, "MQTT client not initialized");
        return false;
    }

    int result = mosquitto_subscribe(m_mosq, nullptr, topic.c_str(), qos);
    if (result != MOSQ_ERR_SUCCESS)
    {
        ChipLogError(DeviceLayer, "Failed to subscribe to topic '%s': %s", topic.c_str(), mosquitto_strerror(result));
        return false;
    }

    ChipLogProgress(DeviceLayer, "Subscribed to MQTT topic: %s", topic.c_str());
    return true;
}

bool MQTTClient::Unsubscribe(const std::string & topic)
{
    if (!m_mosq)
    {
        ChipLogError(DeviceLayer, "MQTT client not initialized");
        return false;
    }

    int result = mosquitto_unsubscribe(m_mosq, nullptr, topic.c_str());
    if (result != MOSQ_ERR_SUCCESS)
    {
        ChipLogError(DeviceLayer, "Failed to unsubscribe from topic '%s': %s", topic.c_str(), mosquitto_strerror(result));
        return false;
    }

    ChipLogProgress(DeviceLayer, "Unsubscribed from MQTT topic: %s", topic.c_str());
    return true;
}

bool MQTTClient::Publish(const std::string & topic, const std::string & payload, int qos, bool retain)
{
    if (!m_mosq)
    {
        ChipLogError(DeviceLayer, "MQTT client not initialized");
        return false;
    }

    int result =
        mosquitto_publish(m_mosq, nullptr, topic.c_str(), static_cast<int>(payload.length()), payload.c_str(), qos, retain);
    if (result != MOSQ_ERR_SUCCESS)
    {
        ChipLogError(DeviceLayer, "Failed to publish to topic '%s': %s", topic.c_str(), mosquitto_strerror(result));
        return false;
    }

    ChipLogProgress(DeviceLayer, "Published to MQTT topic '%s': %s", topic.c_str(), payload.c_str());
    return true;
}
void MQTTClient::SetMessageCallback(MessageCallback callback)
{
    m_message_callback = callback;
}

void MQTTClient::SetConnectionCallback(ConnectionCallback callback)
{
    m_connection_callback = callback;
}

void MQTTClient::StartAsync()
{
    if (m_running)
    {
        ChipLogProgress(DeviceLayer, "MQTT client loop already running");
        return;
    }

    m_running     = true;
    m_loop_thread = std::thread(&MQTTClient::RunLoop, this);
    ChipLogProgress(DeviceLayer, "MQTT client async loop started");
}

void MQTTClient::StopAsync()
{
    if (!m_running)
    {
        return;
    }

    m_running = false;

    if (m_loop_thread.joinable())
    {
        m_loop_thread.join();
    }

    ChipLogProgress(DeviceLayer, "MQTT client async loop stopped");
}

void MQTTClient::RunLoop()
{
    while (m_running)
    {
        if (m_mosq)
        {
            int result = mosquitto_loop(m_mosq, 100, 1); // 100ms timeout
            if (result != MOSQ_ERR_SUCCESS && result != MOSQ_ERR_NO_CONN)
            {
                ChipLogError(DeviceLayer, "MQTT loop error: %s", mosquitto_strerror(result));
                std::this_thread::sleep_for(std::chrono::milliseconds(1000)); // Wait before retry
            }
        }
        else
        {
            std::this_thread::sleep_for(std::chrono::milliseconds(100));
        }
    }
}

// Static callback functions
void MQTTClient::OnConnect(struct mosquitto * mosq, void * userdata, int result)
{
    MQTTClient * client = static_cast<MQTTClient *>(userdata);

    if (result == 0)
    {
        ChipLogProgress(DeviceLayer, "MQTT client connected successfully");
        if (client->m_connection_callback)
        {
            client->m_connection_callback(true);
        }
    }
    else
    {
        ChipLogError(DeviceLayer, "MQTT connection failed: %s", mosquitto_connack_string(result));
        if (client->m_connection_callback)
        {
            client->m_connection_callback(false);
        }
    }
}

void MQTTClient::OnDisconnect(struct mosquitto * mosq, void * userdata, int result)
{
    MQTTClient * client = static_cast<MQTTClient *>(userdata);

    if (result == 0)
    {
        ChipLogProgress(DeviceLayer, "MQTT client disconnected cleanly");
    }
    else
    {
        ChipLogError(DeviceLayer, "MQTT client disconnected unexpectedly");
    }

    if (client->m_connection_callback)
    {
        client->m_connection_callback(false);
    }
}

void MQTTClient::OnMessage(struct mosquitto * mosq, void * userdata, const struct mosquitto_message * message)
{
    MQTTClient * client = static_cast<MQTTClient *>(userdata);

    if (message->payloadlen > 0 && client->m_message_callback)
    {
        std::string topic(message->topic);
        std::string payload(static_cast<const char *>(message->payload), static_cast<size_t>(message->payloadlen));

        // ChipLogProgress(DeviceLayer, "MQTT message received - Topic: %s, Payload: %s", topic.c_str(), payload.c_str());

        // Process Homie message and store to database
        client->ProcessHomieMessage(topic, payload);

        client->m_message_callback(topic, payload);
    }
}

// SQLite Database Implementation
bool MQTTClient::InitializeDatabase()
{
    int rc = sqlite3_open(m_config.database_path.c_str(), &m_db);
    if (rc)
    {
        ChipLogError(DeviceLayer, "Can't open database: %s", sqlite3_errmsg(m_db));
        return false;
    }

    ChipLogProgress(DeviceLayer, "SQLite database opened: %s", m_config.database_path.c_str());

    return CreateTables();
}

bool MQTTClient::CreateTables()
{
    const char * create_devices_table = R"(
        CREATE TABLE IF NOT EXISTS devices (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            topic_id TEXT UNIQUE NOT NULL,
            device_name TEXT,
            state TEXT,
            homie_version TEXT,
            nodes TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP
        );
    )";

    const char * create_clusters_table = R"(
        CREATE TABLE IF NOT EXISTS clusters (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id TEXT NOT NULL,
            cluster_name TEXT NOT NULL,
            cluster_properties TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(device_id, cluster_name),
            FOREIGN KEY(device_id) REFERENCES devices(topic_id)
        );
    )";

    const char * create_attributes_table = R"(
        CREATE TABLE IF NOT EXISTS attributes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id TEXT NOT NULL,
            cluster_name TEXT NOT NULL,
            attribute_name TEXT NOT NULL,
            attribute_value TEXT,
            datatype TEXT,
            settable BOOLEAN DEFAULT FALSE,
            format_info TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(device_id, cluster_name, attribute_name),
            FOREIGN KEY(device_id) REFERENCES devices(topic_id)
        );
    )";

    const char * create_device_properties_table = R"(
        CREATE TABLE IF NOT EXISTS device_properties (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            device_id TEXT NOT NULL,
            property_name TEXT NOT NULL,
            property_value TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(device_id, property_name),
            FOREIGN KEY(device_id) REFERENCES devices(topic_id)
        );
    )";

    char * err_msg = nullptr;

    // Create devices table
    int rc = sqlite3_exec(m_db, create_devices_table, nullptr, nullptr, &err_msg);
    if (rc != SQLITE_OK)
    {
        ChipLogError(DeviceLayer, "SQL error creating devices table: %s", err_msg);
        sqlite3_free(err_msg);
        return false;
    }

    // Create clusters table
    rc = sqlite3_exec(m_db, create_clusters_table, nullptr, nullptr, &err_msg);
    if (rc != SQLITE_OK)
    {
        ChipLogError(DeviceLayer, "SQL error creating clusters table: %s", err_msg);
        sqlite3_free(err_msg);
        return false;
    }

    // Create attributes table
    rc = sqlite3_exec(m_db, create_attributes_table, nullptr, nullptr, &err_msg);
    if (rc != SQLITE_OK)
    {
        ChipLogError(DeviceLayer, "SQL error creating attributes table: %s", err_msg);
        sqlite3_free(err_msg);
        return false;
    }

    // Create device properties table
    rc = sqlite3_exec(m_db, create_device_properties_table, nullptr, nullptr, &err_msg);
    if (rc != SQLITE_OK)
    {
        ChipLogError(DeviceLayer, "SQL error creating device_properties table: %s", err_msg);
        sqlite3_free(err_msg);
        return false;
    }

    ChipLogProgress(DeviceLayer, "Database tables created successfully");
    return true;
}

void MQTTClient::ProcessHomieMessage(const std::string & topic, const std::string & payload)
{
    HomieMessage msg;
    if (!msg.ParseTopic(topic))
    {
        ChipLogError(DeviceLayer, "Failed to parse Homie topic: %s", topic.c_str());
        return;
    }

    msg.value = payload;
    UpdateDeviceCache(msg, payload);

    // Handle different types of messages
    if (msg.property_type == "$homie")
    {
        // Device homie version - first ensure device exists, then update
        const char * insert_sql = R"(
            INSERT OR IGNORE INTO devices (topic_id, created_at, updated_at)
            VALUES (?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        )";
        sqlite3_stmt * insert_stmt;
        if (sqlite3_prepare_v2(m_db, insert_sql, -1, &insert_stmt, nullptr) == SQLITE_OK)
        {
            sqlite3_bind_text(insert_stmt, 1, msg.device_id.c_str(), -1, SQLITE_STATIC);
            int rc = sqlite3_step(insert_stmt);
            sqlite3_finalize(insert_stmt);

            if (rc != SQLITE_DONE)
            {
                ChipLogError(DeviceLayer, "Failed to insert device record for $homie: %s", sqlite3_errmsg(m_db));
            }
        }

        // Now update the homie version
        const char * update_sql = R"(
            UPDATE devices SET homie_version = ?, updated_at = CURRENT_TIMESTAMP
            WHERE topic_id = ?
        )";
        sqlite3_stmt * update_stmt;
        if (sqlite3_prepare_v2(m_db, update_sql, -1, &update_stmt, nullptr) == SQLITE_OK)
        {
            sqlite3_bind_text(update_stmt, 1, payload.c_str(), -1, SQLITE_STATIC);
            sqlite3_bind_text(update_stmt, 2, msg.device_id.c_str(), -1, SQLITE_STATIC);
            int rc = sqlite3_step(update_stmt);
            sqlite3_finalize(update_stmt);

            if (rc != SQLITE_DONE)
            {
                ChipLogError(DeviceLayer, "Failed to update homie version: %s", sqlite3_errmsg(m_db));
            }
            else
            {
                ChipLogProgress(DeviceLayer, "Updated homie version for device %s: %s", msg.device_id.c_str(), payload.c_str());
            }
        }
    }
    else if (msg.property_type == "$name")
    {
        if (msg.cluster_name.empty() && msg.attribute_name.empty())
        {
            // Device name - first ensure device exists, then update
            const char * insert_sql = R"(
                INSERT OR IGNORE INTO devices (topic_id, created_at, updated_at)
                VALUES (?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            )";
            sqlite3_stmt * insert_stmt;
            if (sqlite3_prepare_v2(m_db, insert_sql, -1, &insert_stmt, nullptr) == SQLITE_OK)
            {
                sqlite3_bind_text(insert_stmt, 1, msg.device_id.c_str(), -1, SQLITE_STATIC);
                sqlite3_step(insert_stmt);
                sqlite3_finalize(insert_stmt);
            }

            // Now update the device name
            const char * update_sql = R"(
                UPDATE devices SET device_name = ?, updated_at = CURRENT_TIMESTAMP
                WHERE topic_id = ?
            )";
            sqlite3_stmt * update_stmt;
            if (sqlite3_prepare_v2(m_db, update_sql, -1, &update_stmt, nullptr) == SQLITE_OK)
            {
                sqlite3_bind_text(update_stmt, 1, payload.c_str(), -1, SQLITE_STATIC);
                sqlite3_bind_text(update_stmt, 2, msg.device_id.c_str(), -1, SQLITE_STATIC);
                int rc = sqlite3_step(update_stmt);
                sqlite3_finalize(update_stmt);

                if (rc == SQLITE_DONE)
                {
                    ChipLogProgress(DeviceLayer, "Updated device name for %s: %s", msg.device_id.c_str(), payload.c_str());
                }
            }
        }
        else if (!msg.cluster_name.empty() && msg.attribute_name.empty())
        {
            // Cluster name
            const char * sql = R"(
                INSERT OR IGNORE INTO clusters (device_id, cluster_name, created_at, updated_at)
                VALUES (?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            )";
            sqlite3_stmt * stmt;
            if (sqlite3_prepare_v2(m_db, sql, -1, &stmt, nullptr) == SQLITE_OK)
            {
                sqlite3_bind_text(stmt, 1, msg.device_id.c_str(), -1, SQLITE_STATIC);
                sqlite3_bind_text(stmt, 2, msg.cluster_name.c_str(), -1, SQLITE_STATIC);
                int rc = sqlite3_step(stmt);
                sqlite3_finalize(stmt);

                if (rc == SQLITE_DONE)
                {
                    ChipLogProgress(DeviceLayer, "Inserted cluster %s for device %s", msg.cluster_name.c_str(),
                                    msg.device_id.c_str());
                }
            }
        }
        else if (!msg.cluster_name.empty() && !msg.attribute_name.empty())
        {
            // Attribute name - insert attribute if not exists
            const char * sql = R"(
                INSERT OR IGNORE INTO attributes (device_id, cluster_name, attribute_name, created_at, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
            )";
            sqlite3_stmt * stmt;
            if (sqlite3_prepare_v2(m_db, sql, -1, &stmt, nullptr) == SQLITE_OK)
            {
                sqlite3_bind_text(stmt, 1, msg.device_id.c_str(), -1, SQLITE_STATIC);
                sqlite3_bind_text(stmt, 2, msg.cluster_name.c_str(), -1, SQLITE_STATIC);
                sqlite3_bind_text(stmt, 3, msg.attribute_name.c_str(), -1, SQLITE_STATIC);
                int rc = sqlite3_step(stmt);
                sqlite3_finalize(stmt);

                if (rc == SQLITE_DONE)
                {
                    ChipLogProgress(DeviceLayer, "Inserted attribute %s.%s for device %s", msg.cluster_name.c_str(),
                                    msg.attribute_name.c_str(), msg.device_id.c_str());
                }
            }
        }
    }
    else if (msg.property_type == "$state")
    {
        // Device state - first ensure device exists, then update
        const char * insert_sql = R"(
            INSERT OR IGNORE INTO devices (topic_id, created_at, updated_at)
            VALUES (?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        )";
        sqlite3_stmt * insert_stmt;
        if (sqlite3_prepare_v2(m_db, insert_sql, -1, &insert_stmt, nullptr) == SQLITE_OK)
        {
            sqlite3_bind_text(insert_stmt, 1, msg.device_id.c_str(), -1, SQLITE_STATIC);
            sqlite3_step(insert_stmt);
            sqlite3_finalize(insert_stmt);
        }

        // Now update the state
        const char * update_sql = R"(
            UPDATE devices SET state = ?, updated_at = CURRENT_TIMESTAMP
            WHERE topic_id = ?
        )";
        sqlite3_stmt * update_stmt;
        if (sqlite3_prepare_v2(m_db, update_sql, -1, &update_stmt, nullptr) == SQLITE_OK)
        {
            sqlite3_bind_text(update_stmt, 1, payload.c_str(), -1, SQLITE_STATIC);
            sqlite3_bind_text(update_stmt, 2, msg.device_id.c_str(), -1, SQLITE_STATIC);
            int rc = sqlite3_step(update_stmt);
            sqlite3_finalize(update_stmt);

            if (rc == SQLITE_DONE)
            {
                ChipLogProgress(DeviceLayer, "Updated device state for %s: %s", msg.device_id.c_str(), payload.c_str());
            }
        }
    }
    else if (msg.property_type == "$nodes")
    {
        // Device nodes - first ensure device exists, then update
        const char * insert_sql = R"(
            INSERT OR IGNORE INTO devices (topic_id, created_at, updated_at)
            VALUES (?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        )";
        sqlite3_stmt * insert_stmt;
        if (sqlite3_prepare_v2(m_db, insert_sql, -1, &insert_stmt, nullptr) == SQLITE_OK)
        {
            sqlite3_bind_text(insert_stmt, 1, msg.device_id.c_str(), -1, SQLITE_STATIC);
            sqlite3_step(insert_stmt);
            sqlite3_finalize(insert_stmt);
        }

        // Now update the nodes
        const char * update_sql = R"(
            UPDATE devices SET nodes = ?, updated_at = CURRENT_TIMESTAMP
            WHERE topic_id = ?
        )";
        sqlite3_stmt * update_stmt;
        if (sqlite3_prepare_v2(m_db, update_sql, -1, &update_stmt, nullptr) == SQLITE_OK)
        {
            sqlite3_bind_text(update_stmt, 1, payload.c_str(), -1, SQLITE_STATIC);
            sqlite3_bind_text(update_stmt, 2, msg.device_id.c_str(), -1, SQLITE_STATIC);
            int rc = sqlite3_step(update_stmt);
            sqlite3_finalize(update_stmt);

            if (rc == SQLITE_DONE)
            {
                ChipLogProgress(DeviceLayer, "Updated device nodes for %s: %s", msg.device_id.c_str(), payload.c_str());
            }
        }
    }
    else if (msg.property_type == "$properties")
    {
        // Cluster properties - first ensure cluster exists, then update
        const char * insert_sql = R"(
            INSERT OR IGNORE INTO clusters (device_id, cluster_name, created_at, updated_at)
            VALUES (?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        )";
        sqlite3_stmt * insert_stmt;
        if (sqlite3_prepare_v2(m_db, insert_sql, -1, &insert_stmt, nullptr) == SQLITE_OK)
        {
            sqlite3_bind_text(insert_stmt, 1, msg.device_id.c_str(), -1, SQLITE_STATIC);
            sqlite3_bind_text(insert_stmt, 2, msg.cluster_name.c_str(), -1, SQLITE_STATIC);
            sqlite3_step(insert_stmt);
            sqlite3_finalize(insert_stmt);
        }

        // Now update the cluster properties
        const char * update_sql = R"(
            UPDATE clusters SET cluster_properties = ?, updated_at = CURRENT_TIMESTAMP
            WHERE device_id = ? AND cluster_name = ?
        )";
        sqlite3_stmt * update_stmt;
        if (sqlite3_prepare_v2(m_db, update_sql, -1, &update_stmt, nullptr) == SQLITE_OK)
        {
            sqlite3_bind_text(update_stmt, 1, payload.c_str(), -1, SQLITE_STATIC);
            sqlite3_bind_text(update_stmt, 2, msg.device_id.c_str(), -1, SQLITE_STATIC);
            sqlite3_bind_text(update_stmt, 3, msg.cluster_name.c_str(), -1, SQLITE_STATIC);
            int rc = sqlite3_step(update_stmt);
            sqlite3_finalize(update_stmt);

            if (rc == SQLITE_DONE)
            {
                ChipLogProgress(DeviceLayer, "Updated cluster properties for %s.%s: %s", msg.device_id.c_str(),
                                msg.cluster_name.c_str(), payload.c_str());
            }
        }
    }
    else if (msg.property_type == "$datatype")
    {
        // Attribute datatype - first ensure the attribute record exists
        const char * insert_sql = R"(
            INSERT OR IGNORE INTO attributes (device_id, cluster_name, attribute_name, created_at, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        )";
        sqlite3_stmt * insert_stmt;
        if (sqlite3_prepare_v2(m_db, insert_sql, -1, &insert_stmt, nullptr) == SQLITE_OK)
        {
            sqlite3_bind_text(insert_stmt, 1, msg.device_id.c_str(), -1, SQLITE_STATIC);
            sqlite3_bind_text(insert_stmt, 2, msg.cluster_name.c_str(), -1, SQLITE_STATIC);
            sqlite3_bind_text(insert_stmt, 3, msg.attribute_name.c_str(), -1, SQLITE_STATIC);
            sqlite3_step(insert_stmt);
            sqlite3_finalize(insert_stmt);
        }

        // Now update the datatype
        const char * update_sql = R"(
            UPDATE attributes SET datatype = ?, updated_at = CURRENT_TIMESTAMP
            WHERE device_id = ? AND cluster_name = ? AND attribute_name = ?
        )";
        sqlite3_stmt * update_stmt;
        if (sqlite3_prepare_v2(m_db, update_sql, -1, &update_stmt, nullptr) == SQLITE_OK)
        {
            sqlite3_bind_text(update_stmt, 1, payload.c_str(), -1, SQLITE_STATIC);
            sqlite3_bind_text(update_stmt, 2, msg.device_id.c_str(), -1, SQLITE_STATIC);
            sqlite3_bind_text(update_stmt, 3, msg.cluster_name.c_str(), -1, SQLITE_STATIC);
            sqlite3_bind_text(update_stmt, 4, msg.attribute_name.c_str(), -1, SQLITE_STATIC);
            sqlite3_step(update_stmt);
            sqlite3_finalize(update_stmt);
        }
    }
    else if (msg.property_type == "$settable")
    {
        // Attribute settable property - first ensure the attribute record exists
        const char * insert_sql = R"(
            INSERT OR IGNORE INTO attributes (device_id, cluster_name, attribute_name, created_at, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        )";
        sqlite3_stmt * insert_stmt;
        if (sqlite3_prepare_v2(m_db, insert_sql, -1, &insert_stmt, nullptr) == SQLITE_OK)
        {
            sqlite3_bind_text(insert_stmt, 1, msg.device_id.c_str(), -1, SQLITE_STATIC);
            sqlite3_bind_text(insert_stmt, 2, msg.cluster_name.c_str(), -1, SQLITE_STATIC);
            sqlite3_bind_text(insert_stmt, 3, msg.attribute_name.c_str(), -1, SQLITE_STATIC);
            sqlite3_step(insert_stmt);
            sqlite3_finalize(insert_stmt);
        }

        // Now update the settable property
        bool settable           = (payload == "true");
        const char * update_sql = R"(
            UPDATE attributes SET settable = ?, updated_at = CURRENT_TIMESTAMP
            WHERE device_id = ? AND cluster_name = ? AND attribute_name = ?
        )";
        sqlite3_stmt * update_stmt;
        if (sqlite3_prepare_v2(m_db, update_sql, -1, &update_stmt, nullptr) == SQLITE_OK)
        {
            sqlite3_bind_int(update_stmt, 1, settable ? 1 : 0);
            sqlite3_bind_text(update_stmt, 2, msg.device_id.c_str(), -1, SQLITE_STATIC);
            sqlite3_bind_text(update_stmt, 3, msg.cluster_name.c_str(), -1, SQLITE_STATIC);
            sqlite3_bind_text(update_stmt, 4, msg.attribute_name.c_str(), -1, SQLITE_STATIC);
            sqlite3_step(update_stmt);
            sqlite3_finalize(update_stmt);
        }
    }
    else if (msg.property_type == "$format")
    {
        // Attribute format - first ensure the attribute record exists
        const char * insert_sql = R"(
            INSERT OR IGNORE INTO attributes (device_id, cluster_name, attribute_name, created_at, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP)
        )";
        sqlite3_stmt * insert_stmt;
        if (sqlite3_prepare_v2(m_db, insert_sql, -1, &insert_stmt, nullptr) == SQLITE_OK)
        {
            sqlite3_bind_text(insert_stmt, 1, msg.device_id.c_str(), -1, SQLITE_STATIC);
            sqlite3_bind_text(insert_stmt, 2, msg.cluster_name.c_str(), -1, SQLITE_STATIC);
            sqlite3_bind_text(insert_stmt, 3, msg.attribute_name.c_str(), -1, SQLITE_STATIC);
            sqlite3_step(insert_stmt);
            sqlite3_finalize(insert_stmt);
        }

        // Now update the format info
        const char * update_sql = R"(
            UPDATE attributes SET format_info = ?, updated_at = CURRENT_TIMESTAMP
            WHERE device_id = ? AND cluster_name = ? AND attribute_name = ?
        )";
        sqlite3_stmt * update_stmt;
        if (sqlite3_prepare_v2(m_db, update_sql, -1, &update_stmt, nullptr) == SQLITE_OK)
        {
            sqlite3_bind_text(update_stmt, 1, payload.c_str(), -1, SQLITE_STATIC);
            sqlite3_bind_text(update_stmt, 2, msg.device_id.c_str(), -1, SQLITE_STATIC);
            sqlite3_bind_text(update_stmt, 3, msg.cluster_name.c_str(), -1, SQLITE_STATIC);
            sqlite3_bind_text(update_stmt, 4, msg.attribute_name.c_str(), -1, SQLITE_STATIC);
            sqlite3_step(update_stmt);
            sqlite3_finalize(update_stmt);
        }
    }
    else if (msg.property_type.empty() && !msg.cluster_name.empty() && !msg.attribute_name.empty())
    {
        // This is an actual attribute value (no property type means it's the value)
        SaveAttributeValue(msg.device_id, msg.cluster_name, msg.attribute_name, payload);
    }

    ChipLogProgress(DeviceLayer, "Processed Homie message - Device: %s, Cluster: %s, Attribute: %s, Property: %s",
                    msg.device_id.c_str(), msg.cluster_name.c_str(), msg.attribute_name.c_str(), msg.property_type.c_str());
}

void MQTTClient::UpdateDeviceCache(const HomieMessage & message, const std::string & payload)
{
    // Update in-memory cache for faster access
    auto & device   = m_devices[message.device_id];
    device.topic_id = message.device_id;

    if (message.property_type == "$name" && message.cluster_name.empty())
    {
        device.device_name = payload;
    }
    else if (message.property_type == "$state")
    {
        device.state = payload;
    }
    else if (message.property_type == "$homie")
    {
        device.homie_version = payload;
    }
    else if (message.property_type == "$nodes")
    {
        device.nodes = payload;
    }
}

bool MQTTClient::SaveDeviceInfo(const MatterDeviceInfo & deviceInfo)
{
    const char * sql = R"(
        INSERT OR REPLACE INTO devices
        (topic_id, device_name, state, homie_version, nodes, updated_at)
        VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
    )";

    sqlite3_stmt * stmt;
    if (sqlite3_prepare_v2(m_db, sql, -1, &stmt, nullptr) != SQLITE_OK)
    {
        ChipLogError(DeviceLayer, "Failed to prepare statement: %s", sqlite3_errmsg(m_db));
        return false;
    }

    sqlite3_bind_text(stmt, 1, deviceInfo.topic_id.c_str(), -1, SQLITE_STATIC);
    sqlite3_bind_text(stmt, 2, deviceInfo.device_name.c_str(), -1, SQLITE_STATIC);
    sqlite3_bind_text(stmt, 3, deviceInfo.state.c_str(), -1, SQLITE_STATIC);
    sqlite3_bind_text(stmt, 4, deviceInfo.homie_version.c_str(), -1, SQLITE_STATIC);
    sqlite3_bind_text(stmt, 5, deviceInfo.nodes.c_str(), -1, SQLITE_STATIC);

    int result = sqlite3_step(stmt);
    sqlite3_finalize(stmt);

    if (result != SQLITE_DONE)
    {
        ChipLogError(DeviceLayer, "Failed to save device info: %s", sqlite3_errmsg(m_db));
        return false;
    }

    ChipLogProgress(DeviceLayer, "Saved device info for: %s", deviceInfo.topic_id.c_str());
    return true;
}

bool MQTTClient::SaveAttributeValue(const std::string & deviceId, const std::string & clusterName,
                                    const std::string & attributeName, const std::string & value)
{
    const char * sql = R"(
        INSERT OR IGNORE INTO attributes (device_id, cluster_name, attribute_name, created_at, updated_at)
        VALUES (?, ?, ?, CURRENT_TIMESTAMP, CURRENT_TIMESTAMP);
        UPDATE attributes SET attribute_value = ?, updated_at = CURRENT_TIMESTAMP
        WHERE device_id = ? AND cluster_name = ? AND attribute_name = ?;
    )";

    sqlite3_stmt * stmt;
    if (sqlite3_prepare_v2(m_db, sql, -1, &stmt, nullptr) != SQLITE_OK)
    {
        ChipLogError(DeviceLayer, "Failed to prepare statement: %s", sqlite3_errmsg(m_db));
        return false;
    }

    sqlite3_bind_text(stmt, 1, deviceId.c_str(), -1, SQLITE_STATIC);
    sqlite3_bind_text(stmt, 2, clusterName.c_str(), -1, SQLITE_STATIC);
    sqlite3_bind_text(stmt, 3, attributeName.c_str(), -1, SQLITE_STATIC);
    sqlite3_bind_text(stmt, 4, value.c_str(), -1, SQLITE_STATIC);
    sqlite3_bind_text(stmt, 5, deviceId.c_str(), -1, SQLITE_STATIC);
    sqlite3_bind_text(stmt, 6, clusterName.c_str(), -1, SQLITE_STATIC);
    sqlite3_bind_text(stmt, 7, attributeName.c_str(), -1, SQLITE_STATIC);

    int result = sqlite3_step(stmt);
    sqlite3_finalize(stmt);

    if (result != SQLITE_DONE)
    {
        ChipLogError(DeviceLayer, "Failed to save attribute value: %s", sqlite3_errmsg(m_db));
        return false;
    }

    ChipLogProgress(DeviceLayer, "Saved attribute value - Device: %s, Cluster: %s, Attribute: %s, Value: %s", deviceId.c_str(),
                    clusterName.c_str(), attributeName.c_str(), value.c_str());
    return true;
}

std::vector<MatterDeviceInfo> MQTTClient::GetAllDevices()
{
    std::vector<MatterDeviceInfo> devices;

    const char * sql = R"(
        SELECT topic_id, device_name, state, homie_version, nodes
        FROM devices
        ORDER BY topic_id
    )";

    sqlite3_stmt * stmt;
    if (sqlite3_prepare_v2(m_db, sql, -1, &stmt, nullptr) != SQLITE_OK)
    {
        ChipLogError(DeviceLayer, "Failed to prepare query: %s", sqlite3_errmsg(m_db));
        return devices;
    }

    while (sqlite3_step(stmt) == SQLITE_ROW)
    {
        MatterDeviceInfo device;
        device.topic_id = reinterpret_cast<const char *>(sqlite3_column_text(stmt, 0));

        const char * name = reinterpret_cast<const char *>(sqlite3_column_text(stmt, 1));
        if (name)
            device.device_name = name;

        const char * state = reinterpret_cast<const char *>(sqlite3_column_text(stmt, 2));
        if (state)
            device.state = state;

        const char * homie = reinterpret_cast<const char *>(sqlite3_column_text(stmt, 3));
        if (homie)
            device.homie_version = homie;

        const char * nodes = reinterpret_cast<const char *>(sqlite3_column_text(stmt, 4));
        if (nodes)
            device.nodes = nodes;

        devices.push_back(device);
    }

    sqlite3_finalize(stmt);

    ChipLogProgress(DeviceLayer, "Retrieved %zu devices from database", devices.size());
    return devices;
}
} // namespace mqtt
