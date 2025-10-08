import 'package:flutter/foundation.dart';
import 'package:logger/logger.dart';
import '../models/device_model.dart';
import '../services/api_client.dart';
import '../services/websocket_service.dart';
import 'dart:async';

class DeviceProvider with ChangeNotifier {
  final ApiClient _apiClient = ApiClient();
  final WebSocketService _webSocketService = WebSocketManager.instance;
  final Logger _logger = Logger();

  // State variables
  List<Device> _devices = [];
  List<MatterCluster> _matterClusters = [];
  List<MatterDeviceType> _matterDeviceTypes = [];
  bool _isLoading = false;
  String? _error;
  WebSocketConnectionState _connectionState = WebSocketConnectionState.disconnected;

  // Stream subscriptions
  StreamSubscription<StatusReport>? _statusReportSubscription;
  StreamSubscription<RegisterReport>? _registerReportSubscription;
  StreamSubscription<DeleteReport>? _deleteReportSubscription;
  StreamSubscription<WebSocketConnectionState>? _connectionStateSubscription;

  // Getters
  List<Device> get devices => List.unmodifiable(_devices);
  List<MatterCluster> get matterClusters => List.unmodifiable(_matterClusters);
  List<MatterDeviceType> get matterDeviceTypes => List.unmodifiable(_matterDeviceTypes);
  bool get isLoading => _isLoading;
  String? get error => _error;
  WebSocketConnectionState get connectionState => _connectionState;
  bool get isConnected => _connectionState == WebSocketConnectionState.connected;

  // Filtered devices by type
  List<Device> get plugDevices => _devices
      .where((device) => device.deviceType.contains('Plug'))
      .toList();

  List<Device> get sensorDevices => _devices
      .where((device) => device.deviceType.contains('Sensor'))
      .toList();

  List<Device> get onlineDevices => _devices.where((device) => device.isOn == true).toList();
  List<Device> get offlineDevices => _devices.where((device) => device.isOn == false).toList();

  // Statistics
  int get totalDevices => _devices.length;
  int get activeDevices => onlineDevices.length;
  double get totalPowerConsumption => _devices
      .map((device) => device.activePower ?? 0)
      .fold(0, (sum, power) => sum + power) / 1000.0; // Convert to watts

  DeviceProvider() {
    _initializeWebSocketListeners();
    _logger.i('DeviceProvider initialized');
  }

  void _initializeWebSocketListeners() {
    // Listen to status reports (device attribute changes)
    _statusReportSubscription = _webSocketService.statusReports.listen(
      _handleStatusReport,
      onError: (error) => _logger.e('Status report stream error: $error'),
    );

    // Listen to register reports (new device additions)
    _registerReportSubscription = _webSocketService.registerReports.listen(
      _handleRegisterReport,
      onError: (error) => _logger.e('Register report stream error: $error'),
    );

    // Listen to delete reports (device removals)
    _deleteReportSubscription = _webSocketService.deleteReports.listen(
      _handleDeleteReport,
      onError: (error) => _logger.e('Delete report stream error: $error'),
    );

    // Listen to connection state changes
    _connectionStateSubscription = _webSocketService.connectionState.listen(
      (state) {
        _connectionState = state;
        notifyListeners();
      },
      onError: (error) => _logger.e('Connection state stream error: $error'),
    );
  }

  // Initialize data - called on app startup
  Future<void> initialize() async {
    _logger.i('Initializing device provider');
    await loadMatterDataModel();
    await loadDevices();
    await connectWebSocket();
  }

  // Load Matter data model (clusters and device types)
  Future<void> loadMatterDataModel() async {
    try {
      _logger.i('Loading Matter data model');

      // Load in parallel
      final futures = await Future.wait([
        _apiClient.getMatterClusters(),
        _apiClient.getMatterDeviceTypes(),
      ]);

      _matterClusters = futures[0] as List<MatterCluster>;
      _matterDeviceTypes = futures[1] as List<MatterDeviceType>;

      _logger.i('Loaded ${_matterClusters.length} clusters and ${_matterDeviceTypes.length} device types');
      notifyListeners();
    } catch (e) {
      _logger.e('Failed to load Matter data model: $e');
      // Don't set error state, as this is non-critical for basic functionality
    }
  }

  // Load devices from API
  Future<void> loadDevices() async {
    if (_isLoading) return;

    _setLoading(true);
    _clearError();

    try {
      _logger.i('Loading devices from API');
      final devices = await _apiClient.getDevices();

      _devices = devices;
      _logger.i('Successfully loaded ${devices.length} devices');

      notifyListeners();
    } catch (e) {
      _logger.e('Failed to load devices: $e');
      _setError('Failed to load devices: ${e.toString()}');
    } finally {
      _setLoading(false);
    }
  }

  // Connect WebSocket
  Future<void> connectWebSocket() async {
    try {
      await _webSocketService.connect();
    } catch (e) {
      _logger.e('Failed to connect WebSocket: $e');
      // Don't treat this as a critical error
    }
  }

  // Refresh all data
  Future<void> refresh() async {
    _logger.i('Refreshing all data');

    try {
      await loadDevices();
    } catch (e) {
      _logger.e('Error during refresh: $e');
      // Don't rethrow to allow RefreshIndicator to complete
    }

    if (!isConnected) {
      try {
        await connectWebSocket();
      } catch (e) {
        _logger.e('Error connecting WebSocket during refresh: $e');
        // Don't rethrow to allow RefreshIndicator to complete
      }
    }
  }

  // Add new device using manual pairing code
  Future<bool> addDevice(String manualPairingCode) async {
    _logger.i('Adding device with manual pairing code: $manualPairingCode');

    try {
      _setLoading(true);
      _clearError();

      final success = await _apiClient.addDevice(manualPairingCode);

      if (success) {
        _logger.i('Device added successfully, refreshing device list');
        // Refresh the device list to include the new device
        await loadDevices();
      } else {
        _logger.w('Failed to add device');
        _setError('デバイスの追加に失敗しました');
      }

      return success;
    } catch (e) {
      _logger.e('Error adding device: $e');
      _setError('デバイス追加エラー: $e');
      return false;
    } finally {
      _setLoading(false);
    }
  }

  // Execute device command
  Future<CommandResponse> executeDeviceCommand(
    Device device,
    String cluster,
    String command, {
    Map<String, dynamic>? args,
  }) async {
    try {
      _logger.i('Executing command $command on device ${device.node}:${device.endpoint}');

      final response = await _apiClient.executeCommand(
        device.node,
        device.endpoint,
        cluster,
        command,
        args: args,
      );

      if (response.isSuccess) {
        _logger.i('Command executed successfully');
        // The WebSocket will notify us of the state change
      } else {
        _logger.w('Command execution failed: ${response.error}');
      }

      return response;
    } catch (e) {
      _logger.e('Error executing device command: $e');
      rethrow;
    }
  }

  // Convenience methods for common operations
  Future<CommandResponse> toggleDevice(Device device) =>
      _apiClient.toggleDevice(device);

  Future<CommandResponse> setDeviceLevel(Device device, int level) =>
      _apiClient.setDeviceLevel(device, level);

  Future<CommandResponse> turnOnDevice(Device device) =>
      _apiClient.turnOnDevice(device);

  Future<CommandResponse> turnOffDevice(Device device) =>
      _apiClient.turnOffDevice(device);

  Future<CommandResponse> identifyDevice(Device device) =>
      _apiClient.identifyDevice(device);

  Future<bool> removeDevice(Device device) async {
    try {
      _logger.i('Removing device: ${device.node}:${device.endpoint}');

      final success = await _apiClient.removeDevice(device.node, device.endpoint);

      if (success) {
        // Remove device from local list
        _devices.removeWhere(
          (d) => d.node == device.node && d.endpoint == device.endpoint,
        );
        notifyListeners();
        _logger.i('Device removed successfully');
      } else {
        _logger.w('Failed to remove device from server');
      }

      return success;
    } catch (e) {
      _logger.e('Error removing device: $e');
      rethrow;
    }
  }

  // Forget device (alias for removeDevice)
  Future<bool> forgetDevice(Device device) async {
    return removeDevice(device);
  }

  // Update device name
  Future<bool> updateDeviceName(Device device, String newName) async {
    try {
      _logger.i('Updating device name: ${device.node}:${device.endpoint} to "$newName"');

      final success = await _apiClient.updateDeviceName(
        node: device.node,
        endpoint: device.endpoint,
        name: newName,
      );

      if (success) {
        // Update the device in the local list
        final deviceIndex = _devices.indexWhere(
          (d) => d.node == device.node && d.endpoint == device.endpoint,
        );

        if (deviceIndex != -1) {
          final updatedDevice = Device(
            node: device.node,
            endpoint: device.endpoint,
            name: newName, // Update the name
            deviceType: device.deviceType,
            topicId: device.topicId,
            clusters: device.clusters,
          );

          _devices[deviceIndex] = updatedDevice;
          notifyListeners();
          _logger.i('Updated device name locally: ${device.node}:${device.endpoint}');
        }
      }

      return success;
    } catch (e) {
      _logger.e('Error updating device name: $e');
      rethrow;
    }
  }

  // Handle WebSocket status reports
  void _handleStatusReport(StatusReport report) {
    _logger.d('Processing status report: ${report.cluster}.${report.attribute} = ${report.value}');

    // Find the device and update its attribute
    final deviceIndex = _devices.indexWhere(
      (device) => device.node == report.node && device.endpoint == report.endpoint,
    );

    if (deviceIndex != -1) {
      final device = _devices[deviceIndex];
      final cluster = device.getCluster(report.cluster);

      if (cluster != null) {
        final attribute = cluster.getAttribute(report.attribute);
        if (attribute != null) {
          // Create updated attribute
          final updatedAttribute = Attribute(
            name: attribute.name,
            type: attribute.type,
            value: report.value,
          );

          // Create updated cluster
          final updatedAttributes = cluster.attributes.map((attr) {
            return attr.name == report.attribute ? updatedAttribute : attr;
          }).toList();

          final updatedCluster = Cluster(
            name: cluster.name,
            attributes: updatedAttributes,
            commands: cluster.commands,
          );

          // Create updated device
          final updatedClusters = device.clusters.map((clstr) {
            return clstr.name == report.cluster ? updatedCluster : clstr;
          }).toList();

          final updatedDevice = Device(
            node: device.node,
            endpoint: device.endpoint,
            name: device.name,
            deviceType: device.deviceType,
            topicId: device.topicId,
            clusters: updatedClusters,
          );

          _devices[deviceIndex] = updatedDevice;
          notifyListeners();

          _logger.d('Updated device ${device.node}:${device.endpoint} attribute ${report.attribute}');
        }
      }
    } else {
      _logger.w('Received status report for unknown device: ${report.node}:${report.endpoint}');
    }
  }

  // Handle WebSocket register reports
  void _handleRegisterReport(RegisterReport report) {
    _logger.i('Processing register report for new device: ${report.deviceType} (${report.node}:${report.endpoint})');

    // Check if device already exists
    final existingDevice = _devices.any(
      (device) => device.node == report.node && device.endpoint == report.endpoint,
    );

    if (!existingDevice) {
      // For now, just refresh devices list
      // In a more sophisticated implementation, we could create a basic device
      // and wait for full details via API
      loadDevices();
    }
  }

  // Handle WebSocket delete reports
  void _handleDeleteReport(DeleteReport report) {
    _logger.i('Processing delete report for device: ${report.node}:${report.endpoint}');

    // Remove device from local list if it exists
    final existingDeviceIndex = _devices.indexWhere(
      (device) => device.node == report.node && device.endpoint == report.endpoint,
    );

    if (existingDeviceIndex != -1) {
      _devices.removeAt(existingDeviceIndex);
      notifyListeners();
      _logger.i('Device removed from local list: ${report.node}:${report.endpoint}');
    } else {
      // Device not found in local list, refresh the entire list to sync with server
      _logger.w('Device to delete not found in local list, refreshing devices');
      loadDevices();
    }
  }

  // Get device by node and endpoint
  Device? getDevice(int node, int endpoint) {
    try {
      return _devices.firstWhere(
        (device) => device.node == node && device.endpoint == endpoint,
      );
    } catch (e) {
      return null;
    }
  }

  // Get devices by type
  List<Device> getDevicesByType(String deviceType) {
    return _devices.where((device) => device.deviceType.contains(deviceType)).toList();
  }

  // Search devices
  List<Device> searchDevices(String query) {
    final lowercaseQuery = query.toLowerCase();
    return _devices.where((device) {
      return device.deviceType.toLowerCase().contains(lowercaseQuery) ||
          device.topicId.toLowerCase().contains(lowercaseQuery) ||
          device.node.toString().contains(lowercaseQuery) ||
          device.endpoint.toString().contains(lowercaseQuery);
    }).toList();
  }

  // Get power data for all electrical sensors
  List<PowerData> getPowerData() {
    return _devices
        .where((device) => device.activePower != null)
        .map((device) => PowerData.fromDevice(device))
        .toList();
  }

  // Update server URL
  Future<void> updateServerUrl(String newUrl) async {
    _logger.i('Updating server URL to: $newUrl');

    // Update global config and save to preferences
    await ApiConfig.updateBaseUrl(newUrl);

    // Update API client
    _apiClient.updateBaseUrl(newUrl);

    // Disconnect WebSocket
    await _webSocketService.disconnect();

    // Clear existing data
    _devices.clear();
    _error = null;
    notifyListeners();

    // Reload data with new URL
    try {
      await loadDevices();
      await connectWebSocket();
      _logger.i('Successfully reconnected to new server');
    } catch (e) {
      _logger.e('Failed to connect to new server: $e');
      _setError('新しいサーバーへの接続に失敗しました: $e');
    }
  }  void _setLoading(bool loading) {
    if (_isLoading != loading) {
      _isLoading = loading;
      notifyListeners();
    }
  }

  void _setError(String error) {
    _error = error;
    notifyListeners();
  }

  void _clearError() {
    if (_error != null) {
      _error = null;
      notifyListeners();
    }
  }

  @override
  void dispose() {
    _logger.i('Disposing DeviceProvider');
    _statusReportSubscription?.cancel();
    _registerReportSubscription?.cancel();
    _deleteReportSubscription?.cancel();
    _connectionStateSubscription?.cancel();
    _webSocketService.dispose();
    _apiClient.dispose();
    super.dispose();
  }
}
