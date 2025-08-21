import 'package:flutter/material.dart';
import 'package:gap/gap.dart';

class DeviceSummaryCards extends StatelessWidget {
  final int totalDevices;
  final int activeDevices;
  final double totalPowerConsumption;

  const DeviceSummaryCards({
    super.key,
    required this.totalDevices,
    required this.activeDevices,
    required this.totalPowerConsumption,
  });

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        // 画面幅に応じてレイアウトを決定
        if (constraints.maxWidth > 600) {
          // 横並びレイアウト
          return Row(
            children: [
              Expanded(child: _buildTotalDevicesCard(context)),
              const Gap(16),
              Expanded(child: _buildActiveDevicesCard(context)),
              const Gap(16),
              Expanded(child: _buildPowerConsumptionCard(context)),
            ],
          );
        } else {
          // 縦並びレイアウト（狭い画面）
          return Column(
            children: [
              _buildTotalDevicesCard(context),
              const Gap(12),
              _buildActiveDevicesCard(context),
              const Gap(12),
              _buildPowerConsumptionCard(context),
            ],
          );
        }
      },
    );
  }

  Widget _buildTotalDevicesCard(BuildContext context) {
    return _SummaryCard(
      icon: Icons.devices,
      iconColor: Colors.blue,
      title: 'デバイス総数',
      value: totalDevices.toString(),
      subtitle: '台',
      backgroundColor: Colors.blue.withOpacity(0.1),
    );
  }

  Widget _buildActiveDevicesCard(BuildContext context) {
    return _SummaryCard(
      icon: Icons.power,
      iconColor: Colors.green,
      title: 'アクティブ',
      value: activeDevices.toString(),
      subtitle: '台 / $totalDevices台',
      backgroundColor: Colors.green.withOpacity(0.1),
    );
  }

  Widget _buildPowerConsumptionCard(BuildContext context) {
    return _SummaryCard(
      icon: Icons.flash_on,
      iconColor: Colors.orange,
      title: '総電力使用量',
      value: totalPowerConsumption.toStringAsFixed(1),
      subtitle: 'W',
      backgroundColor: Colors.orange.withOpacity(0.1),
    );
  }
}

class _SummaryCard extends StatelessWidget {
  final IconData icon;
  final Color iconColor;
  final String title;
  final String value;
  final String subtitle;
  final Color backgroundColor;

  const _SummaryCard({
    required this.icon,
    required this.iconColor,
    required this.title,
    required this.value,
    required this.subtitle,
    required this.backgroundColor,
  });

  @override
  Widget build(BuildContext context) {
    return Card(
      elevation: 1,
      child: Container(
        width: double.infinity,
        decoration: BoxDecoration(
          color: backgroundColor,
          borderRadius: BorderRadius.circular(12),
        ),
        child: Padding(
          padding: const EdgeInsets.all(20),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Container(
                    padding: const EdgeInsets.all(8),
                    decoration: BoxDecoration(
                      color: iconColor.withOpacity(0.2),
                      borderRadius: BorderRadius.circular(8),
                    ),
                    child: Icon(
                      icon,
                      color: iconColor,
                      size: 24,
                    ),
                  ),
                  const Gap(8),
                  Expanded(
                    child: Text(
                      title,
                      style: Theme.of(context).textTheme.titleSmall?.copyWith(
                        color: Theme.of(context).colorScheme.onSurface.withOpacity(0.8),
                        fontWeight: FontWeight.w500,
                      ),
                    ),
                  ),
                ],
              ),
              const Gap(12),
              Row(
                crossAxisAlignment: CrossAxisAlignment.end,
                children: [
                  Text(
                    value,
                    style: Theme.of(context).textTheme.headlineMedium?.copyWith(
                      fontWeight: FontWeight.bold,
                      color: iconColor,
                    ),
                  ),
                  const Gap(4),
                  Padding(
                    padding: const EdgeInsets.only(bottom: 4),
                    child: Text(
                      subtitle,
                      style: Theme.of(context).textTheme.bodySmall?.copyWith(
                        color: Theme.of(context).colorScheme.onSurface.withOpacity(0.6),
                      ),
                    ),
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }
}
