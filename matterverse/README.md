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
   export TOPDIR=path/to/Matterverse
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

### Docker Deployment

For containerized deployment, see [Docker Setup Guide](README-Docker.md).


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
