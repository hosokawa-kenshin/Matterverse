import 'dart:async';
import 'dart:convert';
import 'package:dio/dio.dart';
import 'package:logger/logger.dart';
import '../models/device_model.dart';

class ApiConfig {
  static String baseUrl = 'http://localhost:8000'; // Default value, should be configurable
  static const Duration connectTimeout = Duration(seconds: 30);
  static const Duration receiveTimeout = Duration(seconds: 30);

  // API endpoints
  static String get deviceEndpoint => '$baseUrl/device';
  static String get dataModelClusterEndpoint => '$baseUrl/datamodel/cluster';
  static String get dataModelDeviceTypeEndpoint => '$baseUrl/datamodel/devicetype';
  static String deviceCommandEndpoint(int node, int endpoint, String cluster, String command) =>
      '$baseUrl/device/$node/$endpoint/$cluster/$command';
  static String get webSocketEndpoint => baseUrl.replaceFirst('http', 'ws') + '/ws';
}

class ApiClient {
  late final Dio _dio;
  final Logger _logger = Logger();

  ApiClient() {
    _dio = Dio(BaseOptions(
      connectTimeout: ApiConfig.connectTimeout,
      receiveTimeout: ApiConfig.receiveTimeout,
      headers: {
        'Content-Type': 'application/json',
        'Accept': 'application/json',
      },
    ));

    // Add interceptors for logging and error handling
    _dio.interceptors.add(LogInterceptor(
      requestBody: true,
      responseBody: true,
      logPrint: (obj) => _logger.d(obj),
    ));

    _dio.interceptors.add(InterceptorsWrapper(
      onError: (error, handler) {
        _logger.e('API Error: ${error.message}');
        return handler.next(error);
      },
    ));
  }

  // Update base URL (for settings)
  void updateBaseUrl(String newBaseUrl) {
    ApiConfig.baseUrl = newBaseUrl;
    _dio.options.baseUrl = newBaseUrl;
    _logger.i('API base URL updated to: $newBaseUrl');
  }

  // Get all devices
  Future<List<Device>> getDevices() async {
    try {
      _logger.i('Fetching devices from ${ApiConfig.deviceEndpoint}');
      final response = await _dio.get(ApiConfig.deviceEndpoint);

      if (response.statusCode == 200) {
        final data = response.data as Map<String, dynamic>;
        final devicesList = data['devices'] as List;

        final devices = devicesList
            .map((deviceJson) => Device.fromJson(deviceJson))
            .toList();

        _logger.i('Successfully fetched ${devices.length} devices');
        return devices;
      } else {
        throw ApiException('Failed to fetch devices: ${response.statusCode}');
      }
    } on DioException catch (e) {
      _logger.e('Network error fetching devices: ${e.message}');
      throw ApiException('Network error: ${_getDioErrorMessage(e)}');
    } catch (e) {
      _logger.e('Unexpected error fetching devices: $e');
      throw ApiException('Unexpected error: $e');
    }
  }

  // Execute device command
  Future<CommandResponse> executeCommand(
    int node,
    int endpoint,
    String cluster,
    String command, {
    Map<String, dynamic>? args,
  }) async {
    try {
      final url = ApiConfig.deviceCommandEndpoint(node, endpoint, cluster, command);
      final requestBody = {'args': args ?? {}};

      _logger.i('Executing command: $command on device $node:$endpoint, cluster: $cluster');
      _logger.d('Request body: $requestBody');

      final response = await _dio.post(url, data: requestBody);

      if (response.statusCode == 200) {
        final commandResponse = CommandResponse.fromJson(response.data);
        _logger.i('Command executed successfully: ${commandResponse.status}');
        return commandResponse;
      } else {
        throw ApiException('Command execution failed: ${response.statusCode}');
      }
    } on DioException catch (e) {
      _logger.e('Network error executing command: ${e.message}');
      throw ApiException('Network error: ${_getDioErrorMessage(e)}');
    } catch (e) {
      _logger.e('Unexpected error executing command: $e');
      throw ApiException('Unexpected error: $e');
    }
  }

  // Update device endpoint name
  Future<bool> updateDeviceName({
    required int node,
    required int endpoint,
    required String name,
  }) async {
    try {
      final url = '${ApiConfig.baseUrl}/device/$node/$endpoint/name';
      _logger.i('Updating device name: $url');

      final requestBody = {
        'name': name,
      };

      final response = await _dio.post(url, data: requestBody);

      if (response.statusCode == 200) {
        final responseData = response.data;
        _logger.i('Device name updated successfully: ${responseData['name']}');
        return responseData['status'] == 'success';
      } else {
        throw ApiException('Device name update failed: ${response.statusCode}');
      }
    } on DioException catch (e) {
      _logger.e('Network error updating device name: ${e.message}');
      throw ApiException('Network error: ${_getDioErrorMessage(e)}');
    } catch (e) {
      _logger.e('Unexpected error updating device name: $e');
      throw ApiException('Unexpected error: $e');
    }
  }

  // Get Matter cluster information
  Future<List<MatterCluster>> getMatterClusters() async {
    try {
      _logger.i('Fetching Matter clusters from ${ApiConfig.dataModelClusterEndpoint}');
      final response = await _dio.get(ApiConfig.dataModelClusterEndpoint);

      if (response.statusCode == 200) {
        final data = response.data as Map<String, dynamic>;
        final clustersList = data['clusters'] as List;

        final clusters = clustersList
            .map((clusterJson) => MatterCluster.fromJson(clusterJson))
            .toList();

        _logger.i('Successfully fetched ${clusters.length} Matter clusters');
        return clusters;
      } else {
        throw ApiException('Failed to fetch Matter clusters: ${response.statusCode}');
      }
    } on DioException catch (e) {
      _logger.e('Network error fetching Matter clusters: ${e.message}');
      throw ApiException('Network error: ${_getDioErrorMessage(e)}');
    } catch (e) {
      _logger.e('Unexpected error fetching Matter clusters: $e');
      throw ApiException('Unexpected error: $e');
    }
  }

  // Get Matter device type information
  Future<List<MatterDeviceType>> getMatterDeviceTypes() async {
    try {
      _logger.i('Fetching Matter device types from ${ApiConfig.dataModelDeviceTypeEndpoint}');
      final response = await _dio.get(ApiConfig.dataModelDeviceTypeEndpoint);

      if (response.statusCode == 200) {
        final data = response.data as Map<String, dynamic>;
        final deviceTypesList = data['device_types'] as List;

        final deviceTypes = deviceTypesList
            .map((deviceTypeJson) => MatterDeviceType.fromJson(deviceTypeJson))
            .toList();

        _logger.i('Successfully fetched ${deviceTypes.length} Matter device types');
        return deviceTypes;
      } else {
        throw ApiException('Failed to fetch Matter device types: ${response.statusCode}');
      }
    } on DioException catch (e) {
      _logger.e('Network error fetching Matter device types: ${e.message}');
      throw ApiException('Network error: ${_getDioErrorMessage(e)}');
    } catch (e) {
      _logger.e('Unexpected error fetching Matter device types: $e');
      throw ApiException('Unexpected error: $e');
    }
  }

  // Health check
  Future<bool> checkHealth() async {
    try {
      final response = await _dio.get('${ApiConfig.baseUrl}/health',
          options: Options(receiveTimeout: const Duration(seconds: 5)));
      return response.statusCode == 200;
    } catch (e) {
      _logger.w('Health check failed: $e');
      return false;
    }
  }

  String _getDioErrorMessage(DioException e) {
    switch (e.type) {
      case DioExceptionType.connectionTimeout:
        return 'Connection timeout';
      case DioExceptionType.sendTimeout:
        return 'Send timeout';
      case DioExceptionType.receiveTimeout:
        return 'Receive timeout';
      case DioExceptionType.connectionError:
        return 'Connection error';
      case DioExceptionType.badResponse:
        return 'Bad response: ${e.response?.statusCode}';
      case DioExceptionType.cancel:
        return 'Request cancelled';
      default:
        return e.message ?? 'Unknown error';
    }
  }

  void dispose() {
    _dio.close();
  }
}

// Custom exception for API errors
class ApiException implements Exception {
  final String message;
  final int? statusCode;
  final dynamic response;

  ApiException(this.message, {this.statusCode, this.response});

  @override
  String toString() => 'ApiException: $message';
}

// Convenience methods for common device operations
extension DeviceCommands on ApiClient {
  // Toggle On/Off device
  Future<CommandResponse> toggleDevice(Device device) async {
    final onOffCluster = device.getCluster('On/Off');
    if (onOffCluster == null) {
      throw ApiException('Device does not support On/Off control');
    }

    final currentState = device.isOn;
    final command = currentState == true ? 'Off' : 'On';

    return executeCommand(
      device.node,
      device.endpoint,
      'On/Off',
      command,
    );
  }

  // Turn device on
  Future<CommandResponse> turnOnDevice(Device device) async {
    return executeCommand(
      device.node,
      device.endpoint,
      'On/Off',
      'On',
    );
  }

  // Turn device off
  Future<CommandResponse> turnOffDevice(Device device) async {
    return executeCommand(
      device.node,
      device.endpoint,
      'On/Off',
      'Off',
    );
  }

  // Identify device
  Future<CommandResponse> identifyDevice(Device device, {int seconds = 10}) async {
    return executeCommand(
      device.node,
      device.endpoint,
      'Identify',
      'Identify',
      args: {'IdentifyTime': seconds},
    );
  }
}
