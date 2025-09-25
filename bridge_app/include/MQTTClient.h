/*
 * Copyright (c) 2025 Project CHIP Authors
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

#pragma once

#include <atomic>
#include <functional>
#include <map>
#include <mosquitto.h>
#include <sqlite3.h>
#include <string>
#include <thread>

namespace mqtt {

// Matter Device Information Structure
struct MatterDeviceInfo
{
    std::string topic_id;                                               // Device ID extracted from topic
    std::string device_name;                                            // Device friendly name
    std::string state;                                                  // Device state (ready, init, etc.)
    std::string homie_version;                                          // Homie protocol version
    std::string nodes;                                                  // Comma-separated list of nodes
    std::map<std::string, std::map<std::string, std::string>> clusters; // cluster_name -> {attribute_name -> value}
};

// Homie Message Structure
struct HomieMessage
{
    std::string device_id;
    std::string cluster_name;
    std::string attribute_name;
    std::string property_type; // $name, $datatype, $settable, etc.
    std::string value;

    bool ParseTopic(const std::string & topic);
};

class MQTTClient
{
public:
    struct Config
    {
        std::string broker_host   = "localhost";
        int broker_port           = 1883;
        std::string client_id     = "matter_bridge_mqtt";
        int keepalive             = 60;
        bool clean_session        = true;
        std::string username      = "";
        std::string password      = "";
        std::string database_path = "matter_devices.db";
    };

    using MessageCallback    = std::function<void(const std::string & topic, const std::string & payload)>;
    using ConnectionCallback = std::function<void(bool connected)>;

    MQTTClient(const Config & config);
    ~MQTTClient();

    // 接続管理
    bool Connect();
    bool Disconnect();
    bool IsConnected() const;

    // メッセージング
    bool Subscribe(const std::string & topic, int qos = 0);
    bool Unsubscribe(const std::string & topic);
    bool Publish(const std::string & topic, const std::string & payload, int qos = 0, bool retain = false);

    // コールバック設定
    void SetMessageCallback(MessageCallback callback);
    void SetConnectionCallback(ConnectionCallback callback);

    // 非同期処理開始/停止
    void StartAsync();
    void StopAsync();

    // SQLite Database functions
    bool InitializeDatabase();
    bool SaveDeviceInfo(const MatterDeviceInfo & deviceInfo);
    bool SaveAttributeValue(const std::string & deviceId, const std::string & clusterName, const std::string & attributeName,
                            const std::string & value);
    std::vector<MatterDeviceInfo> GetAllDevices();

private:
    Config m_config;
    struct mosquitto * m_mosq;
    MessageCallback m_message_callback;
    ConnectionCallback m_connection_callback;
    std::atomic<bool> m_running;
    std::thread m_loop_thread;
    sqlite3 * m_db;
    std::map<std::string, MatterDeviceInfo> m_devices; // Cache for device information

    // Mosquitto callbacks
    static void OnConnect(struct mosquitto * mosq, void * userdata, int result);
    static void OnDisconnect(struct mosquitto * mosq, void * userdata, int result);
    static void OnMessage(struct mosquitto * mosq, void * userdata, const struct mosquitto_message * message);

    void RunLoop();

    // Database helper functions
    bool CreateTables();
    void ProcessHomieMessage(const std::string & topic, const std::string & payload);
    void UpdateDeviceCache(const HomieMessage & message, const std::string & payload);
};

} // namespace mqtt
