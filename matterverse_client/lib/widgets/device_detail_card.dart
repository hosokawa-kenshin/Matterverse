import 'package:flutter/material.dart';
import 'package:gap/gap.dart';
import '../models/device_model.dart';

typedef CommandCallback = Future<void> Function(
  Device device,
  String cluster,
  String command,
  Map<String, dynamic>? args,
);

class DeviceDetailCard extends StatelessWidget {
  final Device device;
  final CommandCallback onCommand;

  const DeviceDetailCard({
    super.key,
    required this.device,
    required this.onCommand,
  });

  @override
  Widget build(BuildContext context) {
    return Card(
      elevation: 2,
      child: ExpansionTile(
        leading: _buildDeviceIcon(),
        title: Text(
          device.displayName,
          style: Theme.of(context).textTheme.titleMedium?.copyWith(
            fontWeight: FontWeight.bold,
          ),
        ),
        subtitle: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text('Node: ${device.node}, Endpoint: ${device.endpoint}'),
            const Gap(4),
            _buildStatusChips(context),
          ],
        ),
        children: [
          Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                // Device information
                _buildDeviceInfo(context),
                const Gap(16),

                // Clusters
                ...device.clusters.map((cluster) =>
                    _buildClusterSection(context, cluster)),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildDeviceIcon() {
    IconData iconData;
    Color? iconColor;

    if (device.deviceType.contains('Plug')) {
      iconData = Icons.electrical_services;
      iconColor = device.isOn == true ? Colors.green : Colors.grey;
    } else if (device.deviceType.contains('Sensor')) {
      iconData = Icons.sensors;
      iconColor = Colors.blue;
    } else if (device.deviceType.contains('Light')) {
      iconData = Icons.lightbulb;
      iconColor = device.isOn == true ? Colors.amber : Colors.grey;
    } else {
      iconData = Icons.device_unknown;
      iconColor = Colors.grey;
    }

    return Container(
      padding: const EdgeInsets.all(8),
      decoration: BoxDecoration(
        color: iconColor?.withOpacity(0.1),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Icon(iconData, color: iconColor, size: 32),
    );
  }

  Widget _buildStatusChips(BuildContext context) {
    return Wrap(
      spacing: 8,
      children: [
        // On/Off status
        if (device.isOn != null)
          Chip(
            label: Text(device.isOn! ? 'オン' : 'オフ'),
            backgroundColor: device.isOn!
                ? Colors.green.withOpacity(0.2)
                : Colors.grey.withOpacity(0.2),
            side: BorderSide(
              color: device.isOn! ? Colors.green : Colors.grey,
            ),
          ),

        // Power measurement
        if (device.activePower != null)
          Chip(
            label: Text('${(device.activePower! / 1000).toStringAsFixed(1)}W'),
            backgroundColor: Colors.orange.withOpacity(0.2),
            side: const BorderSide(color: Colors.orange),
          ),
      ],
    );
  }

  Widget _buildDeviceInfo(BuildContext context) {
    return Card(
      color: Theme.of(context).colorScheme.surfaceVariant.withOpacity(0.5),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              'デバイス情報',
              style: Theme.of(context).textTheme.titleSmall?.copyWith(
                fontWeight: FontWeight.bold,
              ),
            ),
            const Gap(8),
            _buildInfoRow('Node', device.node.toString()),
            _buildInfoRow('Endpoint', device.endpoint.toString()),
            _buildInfoRow('DeviceType', device.deviceType),
            _buildInfoRow('Topic ID', device.topicId)
          ],
        ),
      ),
    );
  }

  Widget _buildInfoRow(String label, String value) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 2),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 100,
            child: Text(
              '$label:',
              style: const TextStyle(fontWeight: FontWeight.w500),
            ),
          ),
          Expanded(
            child: Text(
              value,
              style: const TextStyle(fontFamily: 'monospace'),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildClusterSection(BuildContext context, Cluster cluster) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 16),
      child: Card(
        child: ExpansionTile(
          title: Row(
            children: [
              Icon(
                _getClusterIcon(cluster.name),
                size: 20,
                color: _getClusterColor(cluster.name),
              ),
              const Gap(8),
              Text(
                cluster.name,
                style: Theme.of(context).textTheme.titleSmall?.copyWith(
                  fontWeight: FontWeight.w600,
                ),
              ),
            ],
          ),
          subtitle: Text(
            '${cluster.attributes.length} 属性, ${cluster.commands.length} コマンド',
            style: Theme.of(context).textTheme.bodySmall?.copyWith(
              color: Theme.of(context).colorScheme.onSurface.withOpacity(0.6),
            ),
          ),
          children: [
            Padding(
              padding: const EdgeInsets.all(16),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  // Attributes section
                  if (cluster.attributes.isNotEmpty) ...[
                    Text(
                      '属性',
                      style: Theme.of(context).textTheme.titleSmall?.copyWith(
                        fontWeight: FontWeight.bold,
                        color: Theme.of(context).colorScheme.primary,
                      ),
                    ),
                    const Gap(8),
                    ...cluster.attributes.map((attribute) =>
                        _buildAttributeRow(context, cluster, attribute)),
                    const Gap(16),
                  ],

                  // Commands section
                  if (cluster.commands.isNotEmpty) ...[
                    Text(
                      'コマンド',
                      style: Theme.of(context).textTheme.titleSmall?.copyWith(
                        fontWeight: FontWeight.bold,
                        color: Theme.of(context).colorScheme.secondary,
                      ),
                    ),
                    const Gap(8),
                    Wrap(
                      spacing: 8,
                      runSpacing: 8,
                      children: cluster.commands.map((command) =>
                          _buildCommandButton(context, cluster, command)).toList(),
                    ),
                  ],
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildAttributeRow(BuildContext context, Cluster cluster, Attribute attribute) {
    return Container(
      margin: const EdgeInsets.only(bottom: 8),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: Theme.of(context).colorScheme.surface,
        borderRadius: BorderRadius.circular(8),
        border: Border.all(
          color: Theme.of(context).colorScheme.outline.withOpacity(0.2),
        ),
      ),
      child: Row(
        children: [
          Expanded(
            flex: 2,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  attribute.name,
                  style: const TextStyle(fontWeight: FontWeight.w500),
                ),
                Text(
                  attribute.type,
                  style: Theme.of(context).textTheme.bodySmall?.copyWith(
                    color: Theme.of(context).colorScheme.onSurface.withOpacity(0.6),
                  ),
                ),
              ],
            ),
          ),
          Expanded(
            flex: 2,
            child: _buildAttributeValue(context, attribute),
          ),
          if (attribute.isWritable)
            Icon(
              Icons.edit,
              size: 16,
              color: Theme.of(context).colorScheme.primary,
            ),
        ],
      ),
    );
  }

  Widget _buildAttributeValue(BuildContext context, Attribute attribute) {
    final value = attribute.value;

    if (value == null) {
      return const Text('null', style: TextStyle(fontStyle: FontStyle.italic));
    }

    switch (attribute.uiType) {
      case AttributeUIType.switch_:
        return Switch(
          value: value as bool? ?? false,
          onChanged: attribute.isWritable ? (newValue) {
            // Handle attribute change
          } : null,
        );

      case AttributeUIType.meter:
        final numValue = value is num ? value.toDouble() : 0.0;
        String displayValue = numValue.toString();

        if (attribute.name.contains('Power')) {
          displayValue = '${(numValue / 1000).toStringAsFixed(1)}W';
        } else if (attribute.name.contains('Voltage')) {
          displayValue = '${(numValue / 1000).toStringAsFixed(1)}V';
        } else if (attribute.name.contains('Current')) {
          displayValue = '${(numValue / 1000).toStringAsFixed(3)}A';
        }

        return Text(
          displayValue,
          style: const TextStyle(fontWeight: FontWeight.w500),
        );

      case AttributeUIType.number:
        return Text(
          value.toString(),
          style: const TextStyle(fontFamily: 'monospace'),
        );

      default:
        return Text(
          value.toString(),
          style: const TextStyle(fontFamily: 'monospace'),
          maxLines: 2,
          overflow: TextOverflow.ellipsis,
        );
    }
  }

  Widget _buildCommandButton(BuildContext context, Cluster cluster, Command command) {
    final hasArgs = command.hasArguments;

    return ElevatedButton.icon(
      onPressed: () => _executeCommand(context, cluster, command),
      icon: Icon(_getCommandIcon(command.name), size: 16),
      label: Text(
        _getCommandDisplayName(command.name),
        style: const TextStyle(fontSize: 12),
      ),
      style: ElevatedButton.styleFrom(
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
        backgroundColor: hasArgs
            ? Theme.of(context).colorScheme.secondaryContainer
            : Theme.of(context).colorScheme.primaryContainer,
      ),
    );
  }

  Future<void> _executeCommand(BuildContext context, Cluster cluster, Command command) async {
    if (command.hasArguments) {
      // Show dialog for command arguments
      await _showCommandArgumentsDialog(context, cluster, command);
    } else {
      // Execute command directly
      await onCommand(device, cluster.name, command.name, null);
    }
  }

  Future<void> _showCommandArgumentsDialog(BuildContext context, Cluster cluster, Command command) async {
    final args = <String, dynamic>{};

    return showDialog(
      context: context,
      builder: (context) => AlertDialog(
        title: Text('${command.name} コマンド'),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          children: command.args.map((arg) =>
              TextFormField(
                decoration: InputDecoration(
                  labelText: '${arg.name} (${arg.type})',
                  hintText: arg.required ? '必須' : '任意',
                ),
                onChanged: (value) {
                  // Parse value based on type
                  if (arg.type.contains('int')) {
                    args[arg.name] = int.tryParse(value) ?? 0;
                  } else if (arg.type.contains('bool')) {
                    args[arg.name] = value.toLowerCase() == 'true';
                  } else {
                    args[arg.name] = value;
                  }
                },
              ),
          ).toList(),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('キャンセル'),
          ),
          ElevatedButton(
            onPressed: () async {
              Navigator.of(context).pop();
              await onCommand(device, cluster.name, command.name, args);
            },
            child: const Text('実行'),
          ),
        ],
      ),
    );
  }

  IconData _getClusterIcon(String clusterName) {
    switch (clusterName) {
      case 'On/Off': return Icons.power_settings_new;
      case 'Identify': return Icons.visibility;
      case 'Groups': return Icons.group;
      case 'Electrical Power Measurement': return Icons.flash_on;
      case 'Electrical Energy Measurement': return Icons.battery_charging_full;
      case 'Descriptor': return Icons.info;
      default: return Icons.settings;
    }
  }

  Color _getClusterColor(String clusterName) {
    switch (clusterName) {
      case 'On/Off': return Colors.green;
      case 'Identify': return Colors.blue;
      case 'Groups': return Colors.purple;
      case 'Electrical Power Measurement': return Colors.orange;
      case 'Electrical Energy Measurement': return Colors.amber;
      case 'Descriptor': return Colors.grey;
      default: return Colors.grey;
    }
  }

  IconData _getCommandIcon(String commandName) {
    switch (commandName.toLowerCase()) {
      case 'on': return Icons.power;
      case 'off': return Icons.power_off;
      case 'toggle': return Icons.power_settings_new;
      case 'identify': return Icons.visibility;
      default: return Icons.play_arrow;
    }
  }

  String _getCommandDisplayName(String commandName) {
    switch (commandName) {
      case 'On': return 'オン';
      case 'Off': return 'オフ';
      case 'Toggle': return 'トグル';
      case 'Identify': return '識別';
      default: return commandName;
    }
  }

}
