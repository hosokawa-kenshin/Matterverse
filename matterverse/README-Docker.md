# Matterverse Docker Setup

This document provides instructions for running Matterverse using Docker containers.

## Prerequisites

- Docker Engine 20.10+
- Docker Compose 2.0+
- Git

## Quick Start

1. **Clone the repository**
   ```bash
   git clone <repository-url>
   cd Matterberse/matterverse
   ```

2. **Configure environment variables**
   ```bash
   cp config/.env.docker.example /config/.env
   vim config/.env
   # Edit .env file with your specific configuration
   ```

3. **Build and run**
   ```bash
   docker compose up --build
   ```

The application will be available at:
- Matterverse API: http://localhost:8000
- MQTT Broker: localhost:1883
- MQTT WebSocket: localhost:9001

### Volume Mounts

The following directories are mounted as volumes for persistence:

- `./db` - SQLite database storage
- `./commissioning_dir` - storage directory used to persist pairing information, certificates, and session data for Matter device management

## Development Mode

For development with hot reload:

```bash
# Use development override
docker compose -f docker compose.yml -f docker compose.override.yml up --build
```

This will:
- Mount source code for live editing
- Enable auto-reload on file changes
- Install test dependencies
- Provide Adminer database interface at http://localhost:8080

## Production Deployment

For production deployment without development overrides:

```bash
# Disable override file
docker compose -f docker compose.yml up -d --build
```

## Services

### Matterverse Application
- **Container**: `matterverse-app`
- **Ports**: 8000
- **Health Check**: Available at `/health`

## Network Configuration

The application uses host networking mode to enable Matter device discovery on the local network. If this causes issues, you can modify `docker compose.yml` to use bridge networking:

```yaml
services:
  matterverse:
    # Remove network_mode: host
    networks:
      - matterverse-network
```

## Matter Device Integration

### chip-tool Installation
The Dockerfile automatically builds and installs chip-tool from the Matter SDK. The tool is available at `/opt/chip-tool/chip-tool` within the container.

### Device Discovery
For proper Matter device discovery, ensure:
1. Host networking is enabled (default configuration)
2. Multicast traffic is allowed on your network
3. The container has access to the local network interface

## Troubleshooting

### Common Issues

1. **Permission denied on database**
   ```bash
   # Fix ownership of mounted volumes
   sudo chmod 777 -R db commissioning_dir
   ```

2. **chip-tool not found**
   ```bash
   # Rebuild with no cache
   docker compose build --no-cache
   ```

3. **Device discovery issues**
   ```bash
   # Ensure host networking
   docker compose exec matterverse ip addr show
   ```

### Logs

View application logs:
```bash
docker compose logs
```

### Database Access

Access SQLite database:
```bash
# Via container
docker compose exec matterverse sqlite3 /app/db/matterverse.db

# Via Adminer (development mode)
# Open http://localhost:8080
```

## Building Custom Images

Build with custom Matter SDK version:
```bash
# Edit Dockerfile - change git branch/tag
ARG MATTER_VERSION=v1.3.0.0
git clone --depth 1 --branch ${MATTER_VERSION} ...

# Rebuild
docker compose build --no-cache
```

## Health Monitoring

Health check endpoint:
```bash
curl http://localhost:8000/health
```

Container health status:
```bash
docker compose ps
```

## Stopping Services

```bash
# Stop all services
docker compose down

# Stop and remove volumes
docker compose down -v

# Stop and remove images
docker compose down --rmi all
```
