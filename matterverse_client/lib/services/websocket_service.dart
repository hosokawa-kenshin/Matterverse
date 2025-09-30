import 'dart:async';
import 'dart:convert';
import 'package:web_socket_channel/web_socket_channel.dart';
import 'package:web_socket_channel/status.dart' as status;
import 'package:logger/logger.dart';
import '../models/device_model.dart';
import 'api_client.dart';

enum WebSocketConnectionState {
  disconnected,
  connecting,
  connected,
  reconnecting,
  error,
}

class WebSocketService {
  WebSocketChannel? _channel;
  WebSocketConnectionState _connectionState = WebSocketConnectionState.disconnected;
  final Logger _logger = Logger();

  // Stream controllers for broadcasting messages
  final _statusReportController = StreamController<StatusReport>.broadcast();
  final _registerReportController = StreamController<RegisterReport>.broadcast();
  final _deleteReportController = StreamController<DeleteReport>.broadcast();
  final _connectionStateController = StreamController<WebSocketConnectionState>.broadcast();

  // Reconnection parameters
  static const int _maxReconnectAttempts = 5;
  static const Duration _initialReconnectDelay = Duration(seconds: 2);
  int _reconnectAttempts = 0;
  Timer? _reconnectTimer;
  Timer? _heartbeatTimer;

  // Public streams
  Stream<StatusReport> get statusReports => _statusReportController.stream;
  Stream<RegisterReport> get registerReports => _registerReportController.stream;
  Stream<DeleteReport> get deleteReports => _deleteReportController.stream;
  Stream<WebSocketConnectionState> get connectionState => _connectionStateController.stream;

  WebSocketConnectionState get currentConnectionState => _connectionState;
  bool get isConnected => _connectionState == WebSocketConnectionState.connected;

  // Connect to WebSocket
  Future<void> connect() async {
    if (_connectionState == WebSocketConnectionState.connected ||
        _connectionState == WebSocketConnectionState.connecting) {
      _logger.w('WebSocket already connected or connecting');
      return;
    }

    await _connect();
  }

  Future<void> _connect() async {
    try {
      _updateConnectionState(WebSocketConnectionState.connecting);
      _logger.i('Connecting to WebSocket: ${ApiConfig.webSocketEndpoint}');

      _channel = WebSocketChannel.connect(Uri.parse(ApiConfig.webSocketEndpoint));

      // Listen to messages
      _channel!.stream.listen(
        _handleMessage,
        onError: _handleError,
        onDone: _handleConnectionClosed,
        cancelOnError: false,
      );

      // Wait for connection to be established
      await _channel!.ready;

      _updateConnectionState(WebSocketConnectionState.connected);
      _reconnectAttempts = 0;
      _logger.i('WebSocket connected successfully');

      // Start heartbeat to monitor connection
      _startHeartbeat();

    } catch (e) {
      _logger.e('Failed to connect to WebSocket: $e');
      _updateConnectionState(WebSocketConnectionState.error);
      _scheduleReconnect();
    }
  }

  void _handleMessage(dynamic message) {
    try {
      final jsonData = jsonDecode(message as String);
      final wsMessage = WebSocketMessage.fromJson(jsonData);

      _logger.d('Received WebSocket message: ${wsMessage.type}');

      if (wsMessage is StatusReport) {
        _statusReportController.add(wsMessage);
        _logger.d('Status report: ${wsMessage.cluster}.${wsMessage.attribute} = ${wsMessage.value}');
      } else if (wsMessage is RegisterReport) {
        _registerReportController.add(wsMessage);
        _logger.i('New device registered: ${wsMessage.deviceType} (${wsMessage.node}:${wsMessage.endpoint})');
      } else if (wsMessage is DeleteReport) {
        _deleteReportController.add(wsMessage);
        _logger.d('Received delete report message');
      }
    } catch (e) {
      _logger.e('Error parsing WebSocket message: $e');
      _logger.d('Raw message: $message');
    }
  }

  void _handleError(error) {
    _logger.e('WebSocket error: $error');
    _updateConnectionState(WebSocketConnectionState.error);
    _scheduleReconnect();
  }

  void _handleConnectionClosed() {
    _logger.w('WebSocket connection closed');
    _stopHeartbeat();

    if (_connectionState != WebSocketConnectionState.disconnected) {
      _updateConnectionState(WebSocketConnectionState.disconnected);
      _scheduleReconnect();
    }
  }

  void _updateConnectionState(WebSocketConnectionState newState) {
    if (_connectionState != newState) {
      _connectionState = newState;
      _connectionStateController.add(newState);
      _logger.d('WebSocket connection state changed to: ${newState.name}');
    }
  }

  void _scheduleReconnect() {
    if (_reconnectAttempts >= _maxReconnectAttempts) {
      _logger.e('Max reconnection attempts reached. Giving up.');
      _updateConnectionState(WebSocketConnectionState.error);
      return;
    }

    if (_reconnectTimer?.isActive == true) return;

    final delay = _calculateReconnectDelay();
    _logger.i('Scheduling reconnect attempt ${_reconnectAttempts + 1}/$_maxReconnectAttempts in ${delay.inSeconds}s');

    _updateConnectionState(WebSocketConnectionState.reconnecting);
    _reconnectTimer = Timer(delay, () {
      _reconnectAttempts++;
      _connect();
    });
  }

  Duration _calculateReconnectDelay() {
    // Exponential backoff with jitter
    final baseDelay = _initialReconnectDelay.inMilliseconds * (1 << _reconnectAttempts);
    final jitter = (baseDelay * 0.1 * (DateTime.now().millisecond / 1000.0));
    return Duration(milliseconds: (baseDelay + jitter).round());
  }

  void _startHeartbeat() {
    _heartbeatTimer = Timer.periodic(const Duration(seconds: 30), (_) {
      if (isConnected) {
        try {
          // Send ping message to keep connection alive
          _channel?.sink.add(jsonEncode({'type': 'ping', 'timestamp': DateTime.now().toIso8601String()}));
        } catch (e) {
          _logger.w('Failed to send heartbeat: $e');
        }
      }
    });
  }

  void _stopHeartbeat() {
    _heartbeatTimer?.cancel();
    _heartbeatTimer = null;
  }

  // Disconnect from WebSocket
  Future<void> disconnect() async {
    _logger.i('Disconnecting WebSocket');

    _updateConnectionState(WebSocketConnectionState.disconnected);
    _reconnectTimer?.cancel();
    _stopHeartbeat();

    try {
      await _channel?.sink.close(status.normalClosure);
    } catch (e) {
      _logger.w('Error closing WebSocket: $e');
    }

    _channel = null;
    _reconnectAttempts = 0;
  }

  // Force reconnect
  Future<void> reconnect() async {
    _logger.i('Force reconnecting WebSocket');
    await disconnect();
    await Future.delayed(const Duration(milliseconds: 500));
    await connect();
  }

  // Send message to WebSocket (for future use)
  void sendMessage(Map<String, dynamic> message) {
    if (!isConnected) {
      _logger.w('Cannot send message: WebSocket not connected');
      return;
    }

    try {
      final jsonMessage = jsonEncode(message);
      _channel?.sink.add(jsonMessage);
      _logger.d('Sent WebSocket message: ${message['type']}');
    } catch (e) {
      _logger.e('Failed to send WebSocket message: $e');
    }
  }

  void dispose() {
    _logger.i('Disposing WebSocket service');
    disconnect();
    _statusReportController.close();
    _registerReportController.close();
    _connectionStateController.close();
  }
}

// Helper class for managing WebSocket connection lifecycle
class WebSocketManager {
  static WebSocketService? _instance;
  static WebSocketService get instance {
    _instance ??= WebSocketService();
    return _instance!;
  }

  static void dispose() {
    _instance?.dispose();
    _instance = null;
  }
}

// Extension for converting connection state to user-friendly string
extension WebSocketConnectionStateExtension on WebSocketConnectionState {
  String get displayName {
    switch (this) {
      case WebSocketConnectionState.disconnected:
        return 'Disconnected';
      case WebSocketConnectionState.connecting:
        return 'Connecting...';
      case WebSocketConnectionState.connected:
        return 'Connected';
      case WebSocketConnectionState.reconnecting:
        return 'Reconnecting...';
      case WebSocketConnectionState.error:
        return 'Connection Error';
    }
  }

  bool get isConnectedOrConnecting =>
      this == WebSocketConnectionState.connected ||
      this == WebSocketConnectionState.connecting;
}
