import 'package:flutter/material.dart';
import 'package:gap/gap.dart';
import '../models/device_model.dart';
import '../services/websocket_service.dart';

class DeviceStatusCard extends StatefulWidget {
  final Device device;
  final VoidCallback? onToggle;
  final VoidCallback? onTap;
  final ValueChanged<int>? onChangeLevel;

  const DeviceStatusCard({
    super.key,
    required this.device,
    this.onToggle,
    this.onTap,
    this.onChangeLevel,
  });

  @override
  State<DeviceStatusCard> createState() => _DeviceStatusCardState();
}

class _DeviceStatusCardState extends State<DeviceStatusCard> {
  late double _currentLevel;

  @override
  void initState() {
    super.initState();
    _currentLevel = _convertLevelToPercent(widget.device.level);
  }

  @override
  void didUpdateWidget(DeviceStatusCard oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.device.level != widget.device.level) {
      _currentLevel = _convertLevelToPercent(widget.device.level);
    }
  }

  double _convertLevelToPercent(int? level) {
    if (level == null) return 0.0;
    return (level / 254.0 * 100.0).clamp(0.0, 100.0);
  }

  int _convertPercentToLevel(double percent) {
    return (percent / 100.0 * 254.0).round().clamp(0, 254);
  }

  @override
  Widget build(BuildContext context) {
    final isOnOffDevice = widget.device.getCluster('On/Off') != null;
    final isLevelControlDevice = widget.device.getCluster('Level Control') != null;
    final isPowerMeasurement = widget.device.getCluster('Electrical Power Measurement') != null;

    return Card(
      elevation: 2,
      child: InkWell(
        onTap: widget.onTap,
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
                          widget.device.displayName,
                          style: Theme.of(context).textTheme.titleSmall?.copyWith(
                            fontWeight: FontWeight.bold,
                          ),
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                        ),
                        Text(
                          '${widget.device.node}:${widget.device.endpoint}',
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
                    onPressed: widget.onToggle,
                    icon: Icon(widget.device.isOn == true ? Icons.power_off : Icons.power),
                    label: Text(widget.device.isOn == true ? 'オフ' : 'オン'),
                    style: ElevatedButton.styleFrom(
                      backgroundColor: widget.device.isOn == true
                          ? Theme.of(context).colorScheme.secondary
                          : Theme.of(context).colorScheme.primary,
                      foregroundColor: widget.device.isOn == true
                          ? Theme.of(context).colorScheme.onSecondary
                          : Theme.of(context).colorScheme.onPrimary,
                    ),
                  ),
                ),
              ],

              if (isLevelControlDevice) ...[
                const Gap(8),
                Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      '明るさ: ${_currentLevel.toInt() ?? 0}%',
                      style: Theme.of(context).textTheme.bodySmall,
                    ),
                    const Gap(4),
                    Slider(
                      value: (_currentLevel ?? 0).toDouble(),
                      min: 0,
                      max: 100,
                      divisions: 100,
                      onChanged: (value) {
                        // TODO: Implement level change logic
                        // current level range is 0 to 254
                        // levelcontrol move-to-level 128 10 0 0 3 1
                        setState(() {
                          _currentLevel = value;
                        });
                      },
                      onChangeEnd: (value) {
                        final level = _convertPercentToLevel(value);
                        widget.onChangeLevel?.call(level);
                      },
                    ),
                  ],
                )
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

    if (widget.device.deviceType.contains('Plug')) {
      iconData = Icons.electrical_services;
      iconColor = widget.device.isOn == true ? Colors.green : Colors.grey;
    } else if (widget.device.deviceType.contains('Sensor')) {
      iconData = Icons.sensors;
      iconColor = Colors.blue;
    } else if (widget.device.deviceType.contains('Light')) {
      iconData = Icons.lightbulb;
      iconColor = widget.device.isOn == true ? Colors.amber : Colors.grey;
    } else {
      iconData = Icons.device_unknown;
      iconColor = Colors.grey;
    }

    return Icon(iconData, color: iconColor, size: 28);
  }

  Widget _buildStatusIndicator() {
    final isOn = widget.device.isOn;
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
    final activePower = widget.device.activePower;
    final rmsVoltage = widget.device.rmsVoltage;
    final rmsCurrent = widget.device.rmsCurrent;

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
}
