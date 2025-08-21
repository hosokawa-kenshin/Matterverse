// Device data models based on the requirements specification

class Device {
  final int node;
  final int endpoint;
  final String deviceType;
  final String topicId;
  final List<Cluster> clusters;

  Device({
    required this.node,
    required this.endpoint,
    required this.deviceType,
    required this.topicId,
    required this.clusters,
  });

  factory Device.fromJson(Map<String, dynamic> json) {
    return Device(
      node: json['node'] as int,
      endpoint: json['endpoint'] as int,
      deviceType: json['device_type'] as String,
      topicId: json['topic_id'] as String,
      clusters: (json['clusters'] as List)
          .map((cluster) => Cluster.fromJson(cluster))
          .toList(),
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'node': node,
      'endpoint': endpoint,
      'device_type': deviceType,
      'topic_id': topicId,
      'clusters': clusters.map((cluster) => cluster.toJson()).toList(),
    };
  }

  // Get specific cluster by name
  Cluster? getCluster(String clusterName) {
    try {
      return clusters.firstWhere((cluster) => cluster.name == clusterName);
    } catch (e) {
      return null;
    }
  }

  // Get specific attribute value
  dynamic getAttributeValue(String clusterName, String attributeName) {
    final cluster = getCluster(clusterName);
    if (cluster != null) {
      final attribute = cluster.getAttribute(attributeName);
      return attribute?.value;
    }
    return null;
  }

  // Check if device is currently on (for On/Off devices)
  bool? get isOn {
    return getAttributeValue('On/Off', 'OnOff') as bool?;
  }

  // Get active power (for Electrical Power Measurement devices)
  int? get activePower {
    return getAttributeValue('Electrical Power Measurement', 'ActivePower') as int?;
  }

  // Get RMS voltage (for Electrical Power Measurement devices)
  int? get rmsVoltage {
    return getAttributeValue('Electrical Power Measurement', 'RMSVoltage') as int?;
  }

  // Get RMS current (for Electrical Power Measurement devices)
  int? get rmsCurrent {
    return getAttributeValue('Electrical Power Measurement', 'RMSCurrent') as int?;
  }

  @override
  String toString() {
    return 'Device(node: $node, endpoint: $endpoint, deviceType: $deviceType, topicId: $topicId)';
  }

  @override
  bool operator ==(Object other) {
    if (identical(this, other)) return true;
    return other is Device &&
        other.node == node &&
        other.endpoint == endpoint;
  }

  @override
  int get hashCode => Object.hash(node, endpoint);
}

class Cluster {
  final String name;
  final List<Attribute> attributes;
  final List<Command> commands;

  Cluster({
    required this.name,
    required this.attributes,
    required this.commands,
  });

  factory Cluster.fromJson(Map<String, dynamic> json) {
    return Cluster(
      name: json['name'] as String,
      attributes: (json['attributes'] as List)
          .map((attr) => Attribute.fromJson(attr))
          .toList(),
      commands: (json['commands'] as List)
          .map((cmd) => Command.fromJson(cmd))
          .toList(),
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'name': name,
      'attributes': attributes.map((attr) => attr.toJson()).toList(),
      'commands': commands.map((cmd) => cmd.toJson()).toList(),
    };
  }

  // Get specific attribute by name
  Attribute? getAttribute(String attributeName) {
    try {
      return attributes.firstWhere((attr) => attr.name == attributeName);
    } catch (e) {
      return null;
    }
  }

  // Get specific command by name
  Command? getCommand(String commandName) {
    try {
      return commands.firstWhere((cmd) => cmd.name == commandName);
    } catch (e) {
      return null;
    }
  }

  @override
  String toString() {
    return 'Cluster(name: $name, attributes: ${attributes.length}, commands: ${commands.length})';
  }
}

class Attribute {
  final String name;
  final String type;
  final dynamic value;

  Attribute({
    required this.name,
    required this.type,
    required this.value,
  });

  factory Attribute.fromJson(Map<String, dynamic> json) {
    return Attribute(
      name: json['name'] as String,
      type: json['type'] as String,
      value: json['value'],
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'name': name,
      'type': type,
      'value': value,
    };
  }

  // Check if this attribute is writable (based on common patterns)
  bool get isWritable {
    // This would typically come from Matter data model,
    // but for now we use simple heuristics
    switch (name) {
      case 'OnOff':
      case 'IdentifyTime':
        return true;
      default:
        return false;
    }
  }

  // Get appropriate UI widget type based on attribute type
  AttributeUIType get uiType {
    if (type == 'boolean') return AttributeUIType.switch_;
    if (type == 'int16u' || type == 'int8u' || type.contains('int')) {
      return AttributeUIType.number;
    }
    if (type.contains('Enum')) return AttributeUIType.dropdown;
    if (type == 'array') return AttributeUIType.list;
    if (type.contains('power') || type.contains('voltage') || type.contains('amperage')) {
      return AttributeUIType.meter;
    }
    return AttributeUIType.text;
  }

  @override
  String toString() {
    return 'Attribute(name: $name, type: $type, value: $value)';
  }
}

class Command {
  final String name;
  final List<CommandArgument> args;

  Command({
    required this.name,
    required this.args,
  });

  factory Command.fromJson(Map<String, dynamic> json) {
    return Command(
      name: json['name'] as String,
      args: (json['args'] as List? ?? [])
          .map((arg) => CommandArgument.fromJson(arg))
          .toList(),
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'name': name,
      'args': args.map((arg) => arg.toJson()).toList(),
    };
  }

  bool get hasArguments => args.isNotEmpty;

  @override
  String toString() {
    return 'Command(name: $name, args: ${args.length})';
  }
}

class CommandArgument {
  final String name;
  final String type;
  final bool required;

  CommandArgument({
    required this.name,
    required this.type,
    this.required = false,
  });

  factory CommandArgument.fromJson(Map<String, dynamic> json) {
    return CommandArgument(
      name: json['name'] as String,
      type: json['type'] as String,
      required: json['required'] as bool? ?? false,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'name': name,
      'type': type,
      'required': required,
    };
  }

  @override
  String toString() {
    return 'CommandArgument(name: $name, type: $type, required: $required)';
  }
}

// Matter standard cluster information
class MatterCluster {
  final String name;
  final String id;
  final List<MatterAttribute> attributes;

  MatterCluster({
    required this.name,
    required this.id,
    required this.attributes,
  });

  factory MatterCluster.fromJson(Map<String, dynamic> json) {
    return MatterCluster(
      name: json['name'] as String,
      id: json['id'] as String,
      attributes: (json['attributes'] as List? ?? [])
          .map((attr) => MatterAttribute.fromJson(attr))
          .toList(),
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'name': name,
      'id': id,
      'attributes': attributes.map((attr) => attr.toJson()).toList(),
    };
  }
}

class MatterAttribute {
  final String code;
  final String name;
  final String type;
  final String define;
  final bool writable;
  final bool optional;
  final String side;

  MatterAttribute({
    required this.code,
    required this.name,
    required this.type,
    required this.define,
    required this.writable,
    required this.optional,
    required this.side,
  });

  factory MatterAttribute.fromJson(Map<String, dynamic> json) {
    return MatterAttribute(
      code: json['code'] as String,
      name: json['name'] as String,
      type: json['type'] as String,
      define: json['define'] as String,
      writable: json['writable'].toString().toLowerCase() == 'true',
      optional: json['optional'].toString().toLowerCase() == 'true',
      side: json['side'] as String,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'code': code,
      'name': name,
      'type': type,
      'define': define,
      'writable': writable,
      'optional': optional,
      'side': side,
    };
  }
}

// Matter standard device type information
class MatterDeviceType {
  final String id;
  final String name;
  final List<String> clusters;

  MatterDeviceType({
    required this.id,
    required this.name,
    required this.clusters,
  });

  factory MatterDeviceType.fromJson(Map<String, dynamic> json) {
    return MatterDeviceType(
      id: json['id'] as String,
      name: json['name'] as String,
      clusters: (json['clusters'] as List).cast<String>(),
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'name': name,
      'clusters': clusters,
    };
  }
}

// Command execution response
class CommandResponse {
  final String status;
  final int node;
  final int endpoint;
  final String cluster;
  final String command;
  final Map<String, dynamic>? result;
  final String? error;

  CommandResponse({
    required this.status,
    required this.node,
    required this.endpoint,
    required this.cluster,
    required this.command,
    this.result,
    this.error,
  });

  factory CommandResponse.fromJson(Map<String, dynamic> json) {
    return CommandResponse(
      status: json['status'] as String,
      node: json['node'] as int,
      endpoint: json['endpoint'] as int,
      cluster: json['cluster'] as String,
      command: json['command'] as String,
      result: json['result'] as Map<String, dynamic>?,
      error: json['error'] as String?,
    );
  }

  bool get isSuccess => status == 'success';
  bool get isError => status == 'error';

  @override
  String toString() {
    return 'CommandResponse(status: $status, node: $node, endpoint: $endpoint, cluster: $cluster, command: $command)';
  }
}

// WebSocket message types
abstract class WebSocketMessage {
  final String type;
  final Map<String, dynamic> device;
  final Map<String, dynamic> data;

  WebSocketMessage({
    required this.type,
    required this.device,
    required this.data,
  });

  factory WebSocketMessage.fromJson(Map<String, dynamic> json) {
    final type = json['type'] as String;
    switch (type) {
      case 'status_report':
        return StatusReport.fromJson(json);
      case 'register_report':
        return RegisterReport.fromJson(json);
      default:
        throw ArgumentError('Unknown WebSocket message type: $type');
    }
  }
}

class StatusReport extends WebSocketMessage {
  StatusReport({
    required Map<String, dynamic> device,
    required Map<String, dynamic> data,
  }) : super(type: 'status_report', device: device, data: data);

  factory StatusReport.fromJson(Map<String, dynamic> json) {
    return StatusReport(
      device: json['device'] as Map<String, dynamic>,
      data: json['data'] as Map<String, dynamic>,
    );
  }

  int get node => device['node'] as int;
  int get endpoint => device['endpoint'] as int;
  String get cluster => data['cluster'] as String;
  String get attribute => data['attribute'] as String;
  dynamic get value => data['value'];

  @override
  String toString() {
    return 'StatusReport(node: $node, endpoint: $endpoint, cluster: $cluster, attribute: $attribute, value: $value)';
  }
}

class RegisterReport extends WebSocketMessage {
  RegisterReport({
    required Map<String, dynamic> device,
    required Map<String, dynamic> data,
  }) : super(type: 'register_report', device: device, data: data);

  factory RegisterReport.fromJson(Map<String, dynamic> json) {
    return RegisterReport(
      device: json['device'] as Map<String, dynamic>,
      data: json['data'] as Map<String, dynamic>,
    );
  }

  int get node => device['node'] as int;
  int get endpoint => device['endpoint'] as int;
  String get deviceType => data['device_type'] as String;
  String get topicId => data['topic_id'] as String;

  @override
  String toString() {
    return 'RegisterReport(node: $node, endpoint: $endpoint, deviceType: $deviceType, topicId: $topicId)';
  }
}

// Power data for electrical measurements
class PowerData {
  final int activePower; // mW
  final int rmsCurrent; // mA
  final int rmsVoltage; // mV
  final int cumulativeEnergyImported;
  final DateTime timestamp;

  PowerData({
    required this.activePower,
    required this.rmsCurrent,
    required this.rmsVoltage,
    required this.cumulativeEnergyImported,
    required this.timestamp,
  });

  factory PowerData.fromDevice(Device device) {
    return PowerData(
      activePower: device.activePower ?? 0,
      rmsCurrent: device.rmsCurrent ?? 0,
      rmsVoltage: device.rmsVoltage ?? 0,
      cumulativeEnergyImported: 0, // TODO: Extract from device
      timestamp: DateTime.now(),
    );
  }

  // Convert power from mW to W for display
  double get activePowerInWatts => activePower / 1000.0;

  // Convert voltage from mV to V for display
  double get rmsVoltageInVolts => rmsVoltage / 1000.0;

  // Convert current from mA to A for display
  double get rmsCurrentInAmps => rmsCurrent / 1000.0;

  Map<String, dynamic> toJson() {
    return {
      'activePower': activePower,
      'rmsCurrent': rmsCurrent,
      'rmsVoltage': rmsVoltage,
      'cumulativeEnergyImported': cumulativeEnergyImported,
      'timestamp': timestamp.toIso8601String(),
    };
  }

  factory PowerData.fromJson(Map<String, dynamic> json) {
    return PowerData(
      activePower: json['activePower'] as int,
      rmsCurrent: json['rmsCurrent'] as int,
      rmsVoltage: json['rmsVoltage'] as int,
      cumulativeEnergyImported: json['cumulativeEnergyImported'] as int,
      timestamp: DateTime.parse(json['timestamp'] as String),
    );
  }

  @override
  String toString() {
    return 'PowerData(${activePowerInWatts.toStringAsFixed(2)}W, ${rmsVoltageInVolts.toStringAsFixed(1)}V, ${rmsCurrentInAmps.toStringAsFixed(3)}A)';
  }
}

// UI type enumeration for attributes
enum AttributeUIType {
  switch_,
  number,
  dropdown,
  list,
  meter,
  text,
}
