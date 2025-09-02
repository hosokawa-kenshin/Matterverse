# Matterverse
[![License](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE) [![Python](https://img.shields.io/badge/Python-3.10+-brightgreen.svg)](https://python.org) [![Matter](https://img.shields.io/badge/Matter-SDK-orange.svg)](https://github.com/project-chip/connectedhomeip)

**Matterverse** is a democratization initiative for IoT systems that traditionally rely on vendor-specific protocols. By applying the Matter standard to industrial IoT systems, this project aims to enhance interoperability between devices and enable integration of systems from different vendors.

The name "Matterverse" combines "Matter" (the communication protocol) and "Universe" (representing a world of connected devices).

## Project Overview

Currently, the project focuses on replacing the communication protocol of BLE RSSI-based positioning systems with Matter, creating a more interoperable and vendor-neutral solution.

## Architecture

The Matterverse ecosystem consists of several components:

- **Matterverse**: Central application managing Matter devices, MQTT communication, and data processing
- **ESP32 Examples**: Hardware implementations for beacon aggregation and mediation
- **Client Application**: Flutter-based mobile app for system interaction
- **Matter SDK**: Integrated Matter/Thread/Zigbee connectivity solution

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

2. **Start with Docker Compose**
   ```bash
   cd matterverse
   docker-compose up --build
   ```

3. **Access the application**
   - Matterverse API: http://localhost:8000
   - MQTT Broker: localhost:1883
   - MQTT WebSocket: localhost:9001

### Manual Installation

1. **Install dependencies**
   ```bash
   cd matterverse
   pip install -r requirements.txt
   ```

2. **Configure environment**
   ```bash
   cp config/.env.example config/.env
   # Edit .env with your configuration
   ```

3. **Run the application**
   ```bash
   python main.py
   ```

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
├── matterverse_client/    # Flutter mobile application
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

Flutter-based mobile application for:
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

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Add tests if applicable
5. Submit a pull request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Acknowledgments

- [Matter/Thread Group](https://csa-iot.org/all-solutions/matter/) for the Matter protocol
- [ESP-Matter](https://github.com/espressif/esp-matter) for ESP32 integration
- [Project CHIP](https://github.com/project-chip/connectedhomeip) for the core Matter SDK

## Support

For questions and support, please open an issue in this repository.
