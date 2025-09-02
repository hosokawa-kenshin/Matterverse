# Matterverse

[![Python](https://img.shields.io/badge/Python-3.10+-brightgreen.svg)](https://python.org) [![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-blue.svg)](https://fastapi.tiangolo.com) [![Matter](https://img.shields.io/badge/Matter-SDK-orange.svg)](https://github.com/project-chip/connectedhomeip)

The **Matterverse** is a FastAPI-based application that serves as the central hub for Matter device management, MQTT communication, and IoT system integration. It bridges Matter protocol devices with traditional IoT systems through MQTT and provides real-time WebSocket communication.

## Quick Start
### Prerequisites

- Python 3.10 or higher
- Matter SDK (connectedhomeip)
- chip-tool (connectedhomeip)
- MQTT Broker (Eclipse Mosquitto)
- SQLite 3

### Installation

1. **Install dependencies**
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure environment**
   ```bash
   cp .env.example .env
   # Edit .env with your specific configuration
   ```

3. **Run the server**
   ```bash
   python main.py
   ```

4. **Access the API**
   - API Documentation: http://localhost:8000/docs
   - Health Check: http://localhost:8000/health
   - WebSocket: ws://localhost:8000/ws

### Docker Deployment

For containerized deployment, see [Docker Setup Guide](README-Docker.md).

## Configuration
### Environment Variables

Create a `.env` file in the `config/` directory:

```bash
# Application Settings
LOG_LEVEL=INFO
ENABLE_COLORED_LOGS=true

# Database
DATABASE_PATH=db/matterverse.db

# Matter/chip-tool
CHIP_TOOL_PATH=/usr/local/bin/chip-tool
COMMISSIONING_DIR=commissioning_dir
PAA_CERT_DIR_PATH=paa-root-certs

# MQTT Broker
MQTT_BROKER_URL=localhost
MQTT_BROKER_PORT=1883

# XML Data Models
DEVICETYPE_XML_FILE=data_model/matter-devices.xml
CLUSTER_XML_DIR=data_model

# Polling Configuration
POLLING_INTERVAL=30
MAX_CONCURRENT_DEVICES=5
COMMAND_TIMEOUT=30
AUTO_DISCOVERY_INTERVAL=300
```

### Data Model Files

The server requires Matter XML data model files:

```bash
data_model/
├── matter-devices.xml      # Device type definitions
└── chip/                   # Cluster definitions
    ├── access-control-cluster.xml
    ├── basic-information-cluster.xml
    └── ... (other cluster files)
```

## Development

### Project Structure

```
matterverse/
├── main.py                          # Application entry point
├── matterverse_app.py              # Main application class
├── config.py                       # Configuration management
├── logger.py                       # Logging setup
│
├── api_interface.py                # FastAPI REST endpoints
├── websocket_interface.py          # WebSocket communication
│
├── chip_tool_manager.py            # Matter device management
├── device_manager.py               # Device state management
├── data_model_dictionary.py        # XML data model parsing
│
├── mqtt_interface.py               # MQTT broker integration
├── database_manager.py             # SQLite database operations
│
├── polling_subscription_manager.py # Modern polling system
│
├── requirements.txt                # Python dependencies
├── Dockerfile                      # Container image
├── docker-compose.yml              # Container orchestration
└── README-Docker.md                # Docker documentation
```

## API Usage


## Docker Support

Full containerization support with:

- Multi-stage builds for optimized images
- Development and production configurations
- Integrated MQTT broker (Mosquitto)
- Health monitoring and auto-restart
- Persistent volumes for data storage

See [Docker Setup Guide](README-Docker.md) for detailed instructions.

## License

This project is licensed under the MIT License - see the [LICENSE](../LICENSE) file for details.

## Acknowledgments

- [Project CHIP](https://github.com/project-chip/connectedhomeip) for the Matter SDK
- [FastAPI](https://fastapi.tiangolo.com) for the excellent web framework
- [Eclipse Mosquitto](https://mosquitto.org) for MQTT broker
- [Homie Convention](https://homieiot.github.io) for MQTT device representation
