# Matterverse
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE) [![Python](https://img.shields.io/badge/Python-3.10+-brightgreen.svg)](https://python.org) [![Matter](https://img.shields.io/badge/Matter-SDK-orange.svg)](https://github.com/project-chip/connectedhomeip)

**Matterverse** is a democratization initiative for IoT systems that traditionally rely on vendor-specific protocols. By applying the Matter standard to industrial IoT systems, this project aims to enhance interoperability between devices and enable integration of systems from different vendors.

The name "Matterverse" combines "Matter" (the communication protocol) and "Universe" (representing a world of connected devices).

## Project Overview

Currently, the project focuses on replacing the communication protocol of BLE RSSI-based positioning systems with Matter, creating a more interoperable and vendor-neutral solution. Device exposure from Matter to MQTT has been implemented. Future development will explore representing MQTT devices as Matter devices to enable bidirectional protocol bridging.

## Architecture

The Matterverse ecosystem consists of several components:

- **Matterverse**: Central application managing Matter devices, MQTT communication, and data processing
- **ESP32 Examples**: Hardware implementations for beacon aggregation and mediation
- **Client Application**: Flutter-based mobile app for system interaction
- **Matter SDK**: Extended Matter/Thread/Zigbee connectivity solution with industrial-specific device types based on connectedhomeip

## Quick Start

### Prerequisites

- Python 3.10+
- Docker & Docker Compose
- ESP-IDF v4.4.4 (for ESP32 examples)
- Flutter 3.x (for client app)

### Using Docker (Recommended)

1. **Clone the repository**
   ```bash
   git clone https://github.com/hosokawa-kenshin/Matterverse.git
   cd Matterverse
   ```
2. **Configure environment variables**
   ```bash
   cd matterverse
   cp config/.env.docker.example /config/.env
   vim config/.env
   # Edit .env file with your specific configuration
   MQTT_BROKER_URL=mqtt://example.com  # Update with your MQTT broker

2. **Start with Docker Compose**
   ```bash
   docker-compose up --build
   ```

3. **Access the application**
   - Matterverse API: http://localhost:8000
   - MQTT Broker: localhost:1883
   - MQTT WebSocket: localhost:9001

### Manual Installation
1. **Install prerequisite packages**
   ```bash
   sudo apt-get install git gcc g++ pkg-config libssl-dev libdbus-1-dev \
   libglib2.0-dev libavahi-client-dev ninja-build python3-venv python3-dev \
   python3-pip unzip libgirepository1.0-dev libcairo2-dev libreadline-dev default-jre
   ```

2. **Clone Matterverse repository**
   ```bash
   git clone https://github.com/hosokawa-kenshin/Matterverse.git --recursive
   ```
   *This may take some time. Ensure stable network connection for proper submodule cloning*
   ```bash
   export TOPDIR=$HOME/Matterverse
   ```

3. **Setup connectedhomeip SDK**
   ```bash
   cd $TOPDIR/sdk
   source scripts/bootstrap.sh
   echo "source $TOPDIR/sdk/scripts/activate.sh" >> ~/.bashrc
   ```

4. **Build chip-tool**
   ```bash
   cd $TOPDIR/sdk/examples/chip-tool/
   gn gen build
   ninja -C build
   ```

5. **Download PAA certificates (for commercial devices)**
   ```bash
   cd $TOPDIR/sdk/credentials
   python fetch_paa_certs_from_dcl.py --use-main-net-http
   ```
   *Success if `$TOPDIR/sdk/credentials/paa-root-certs/` directory is created*

6. **Configure Matterverse**
   ```bash
   cd $TOPDIR/matterverse
   cp config/.env.local.example .env
   # Edit .env file with your configuration
   ```

   Key settings in `.env`:
   ```bash
   MQTT_BROKER_URL=mqtt://example.com  # Update with your MQTT broker
   ```

7. **Install Python dependencies**
   ```bash
   pip install -r requirements.txt
   ```

8. **Run the server**
   ```bash
   python3 main.py
   ```

9. **Access the application**
   - API Documentation: http://localhost:8000/docs
   - Health Check: http://localhost:8000/health
   - WebSocket: ws://localhost:8000/ws

## Project Structure

```
Matterverse/
├── matterverse/           # Main server application
│   ├── api_interface.py   # FastAPI REST endpoints
│   ├── mqtt_interface.py  # MQTT broker integration
│   ├── chip_tool_manager.py # Matter device management
│   ├── websocket_interface.py # Real-time communication
│   └── database_manager.py # SQLite database operations
├── examples/              # ESP32 hardware implementations
│   ├── beacon_aggregator/ # Matter-enabled beacon aggregator
│   └── beacon_mediator/   # BLE-to-Matter bridge device
├── matterverse_client/    # Flutter application
├── sdk/                   # Matter SDK integration
└── docs/                  # Documentation
```

## Components

### Matterverse

A FastAPI-based application that serves as the central hub for:
- Matter device commissioning and control
- MQTT message broker integration
- Real-time WebSocket communication
- SQLite database management
- RESTful API endpoints

**Key Features:**
- Asynchronous device management
- Matter cluster attribute monitoring
- MQTT-Matter protocol bridging
- WebSocket real-time updates

### ESP32 Examples

#### Beacon Aggregator
ESP32-based device that:
- Receives beacon information via Matter protocol
- Estimates beacon positions using RSSI data
- Supports commissioning via button press

#### Beacon Mediator
ESP32-based device that:
- Scans for BLE iBeacon advertisements
- Estimates distance based on RSSI measurements
- Transmits data via Matter protocol to aggregators

### Client Application

Flutter-based application for:
- System monitoring and control
- Device status visualization
- Configuration management

## Documentation

- [Matterverse Setup Guide](matterverse/README-Docker.md)
- [API Documentation](docs/api.md) (generated from FastAPI)
- [ESP32 Setup - Beacon Aggregator](examples/beacon_aggregator/README.md)
- [ESP32 Setup - Beacon Mediator](examples/beacon_mediator/README.md)

## API Endpoints

- `GET /health` - Health check
- `GET /device` - List all Matter devices
- `POST /device/{node_id}/command` - Send commands to devices
- `WebSocket /ws` - Real-time device updates

## Docker Support

Full Docker containerization with:
- Multi-stage builds for optimized images
- Development and production configurations
- Integrated MQTT broker
- Health monitoring
- Volume persistence for data

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- [Matter/Thread Group](https://csa-iot.org/all-solutions/matter/) for the Matter protocol
- [ESP-Matter](https://github.com/espressif/esp-matter) for ESP32 integration
- [Project CHIP](https://github.com/project-chip/connectedhomeip) for the core Matter SDK