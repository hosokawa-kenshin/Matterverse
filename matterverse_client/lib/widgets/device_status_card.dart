import 'package:flutter/material.dart';
import 'package:gap/gap.dart';
import '../models/device_model.dart';
import '../services/websocket_service.dart';

class DeviceStatusCard extends StatelessWidget {
  final Device device;
  final VoidCallback? onToggle;
  final VoidCallback? onTap;

  const DeviceStatusCard({
    super.key,
    required this.device,
    this.onToggle,
    this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    final isOnOffDevice = device.getCluster('On/Off') != null;
    final isPowerMeasurement = device.getCluster('Electrical Power Measurement') != null;

    return Card(
      elevation: 2,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(12),
        child: Padding(
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // Header row with device type and status
              Row(
                children: [
                  _buildDeviceIcon(),
                  const Gap(8),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          _getDeviceDisplayName(),
                          style: Theme.of(context).textTheme.titleSmall?.copyWith(
                            fontWeight: FontWeight.bold,
                          ),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                        ),
                        Text(
                          '${device.node}:${device.endpoint}',
                          style: Theme.of(context).textTheme.bodySmall?.copyWith(
                            color: Theme.of(context).colorScheme.onSurface.withOpacity(0.6),
                          ),
                        ),
                      ],
                    ),
                  ),
                  if (isOnOffDevice) _buildStatusIndicator(),
                ],
              ),
              const Gap(12),

              // Device information
              if (isPowerMeasurement) ...[
                _buildPowerInfo(),
                const Gap(8),
              ],

              // Control button
              if (isOnOffDevice) ...[
                const Gap(8),
                SizedBox(
                  width: double.infinity,
                  child: ElevatedButton.icon(
                    onPressed: onToggle,
                    icon: Icon(device.isOn == true ? Icons.power_off : Icons.power),
                    label: Text(device.isOn == true ? 'オフ' : 'オン'),
                    style: ElevatedButton.styleFrom(
                      backgroundColor: device.isOn == true
                          ? Theme.of(context).colorScheme.secondary
                          : Theme.of(context).colorScheme.primary,
                      foregroundColor: device.isOn == true
                          ? Theme.of(context).colorScheme.onSecondary
                          : Theme.of(context).colorScheme.onPrimary,
                    ),
                  ),
                ),
              ],
            ],
          ),
        ),
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

    return Icon(iconData, color: iconColor, size: 28);
  }

  Widget _buildStatusIndicator() {
    final isOn = device.isOn;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: isOn == true ? Colors.green.withOpacity(0.2) : Colors.grey.withOpacity(0.2),
        borderRadius: BorderRadius.circular(12),
      ),
      child: Text(
        isOn == true ? 'オン' : isOn == false ? 'オフ' : '不明',
        style: TextStyle(
          color: isOn == true ? Colors.green.shade700 : Colors.grey.shade600,
          fontSize: 12,
          fontWeight: FontWeight.w500,
        ),
      ),
    );
  }

  Widget _buildPowerInfo() {
    final activePower = device.activePower;
    final rmsVoltage = device.rmsVoltage;
    final rmsCurrent = device.rmsCurrent;

    return Column(
      children: [
        if (activePower != null) ...[
          Row(
            children: [
              const Icon(Icons.flash_on, size: 16, color: Colors.orange),
              const Gap(4),
              Text(
                '${(activePower / 1000).toStringAsFixed(1)} W',
                style: const TextStyle(fontWeight: FontWeight.w500),
              ),
            ],
          ),
          const Gap(4),
        ],
        Row(
          children: [
            if (rmsVoltage != null) ...[
              const Icon(Icons.electrical_services, size: 14, color: Colors.blue),
              const Gap(2),
              Text(
                '${(rmsVoltage / 1000).toStringAsFixed(1)}V',
                style: const TextStyle(fontSize: 12),
              ),
              const Gap(8),
            ],
            if (rmsCurrent != null) ...[
              const Icon(Icons.timeline, size: 14, color: Colors.red),
              const Gap(2),
              Text(
                '${(rmsCurrent / 1000).toStringAsFixed(2)}A',
                style: const TextStyle(fontSize: 12),
              ),
            ],
          ],
        ),
      ],
    );
  }

  String _getDeviceDisplayName() {
    // Extract meaningful name from device type
    final deviceType = device.deviceType;
    if (deviceType.contains('Matter On/Off Plug-in Unit')) {
      return 'スマートプラグ';
    } else if (deviceType.contains('Matter Electrical Sensor')) {
      return '電力センサー';
    } else if (deviceType.contains('Matter Dimmable Plug-in Unit')) {
      return '調光プラグ';
    } else {
      return deviceType.replaceAll('Matter ', '');
    }
  }
}
