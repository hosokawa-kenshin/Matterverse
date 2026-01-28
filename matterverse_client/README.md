# Matterverse Client

[![Flutter](https://img.shields.io/badge/Flutter-3.x-blue.svg)](https://flutter.dev)
[![Dart](https://img.shields.io/badge/Dart-3.x-blue.svg)](https://dart.dev)

## Overview

**Matterverse Client** is a Flutter-based client application designed to visualize, monitor, and interact with the Matterverse Server. It provides a cross-platform user interface for real-time IoT data, aggregated distance information, and Matter device states.

The client communicates with the Matterverse Server via REST APIs and WebSocket connections, enabling responsive dashboards and real-time updates.

## Getting Started

### Prerequisites

* Flutter SDK (3.x or later)
* Dart SDK (included with Flutter)
* A running **Matterverse** instance

## Installation

```bash
git clone https://github.com/hosokawa-kenshin/Matterverse
cd matterverse_client
flutter pub get
```

## Running the Client

### Mobile / Desktop

```bash
flutter run
```

### Web

```bash
flutter run -d chrome
```

---

## Configuration

Edit the server endpoint configuration to match your environment:

```dart
const String serverBaseUrl = "http://<server-address>:8000";
```

WebSocket endpoints are derived automatically from the base URL.

## License

This project is licensed under the MIT License. See the [LICENSE](../LICENSE) file for details.

## Related Projects

* **Matterverse** – Backend server for Matter device management

## Acknowledgments

* [Flutter](https://flutter.dev) for the cross-platform framework
* [FastAPI](https://fastapi.tiangolo.com) for the backend integration
* [Project CHIP](https://github.com/project-chip/connectedhomeip) for the Matter ecosystem
