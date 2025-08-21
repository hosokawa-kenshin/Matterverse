import 'package:flutter/material.dart';
import 'package:gap/gap.dart';
import 'package:responsive_framework/responsive_framework.dart';
import 'package:matterverse_app/widget/page_header.dart';
import 'package:matterverse_app/widget/content_view.dart';
import 'package:provider/provider.dart';
import 'package:intl/intl.dart';
import '../providers/device_provider.dart';
import '../models/device_model.dart';
import '../widgets/device_status_card.dart';
import '../widgets/connection_status_indicator.dart';
import '../widgets/power_consumption_chart.dart';
import '../widgets/device_summary_cards.dart';

class DashBoardPage extends StatefulWidget {
  const DashBoardPage({super.key});

  @override
  State<DashBoardPage> createState() => _DashBoardPageState();
}

class _DashBoardPageState extends State<DashBoardPage> {
  @override
  void initState() {
    super.initState();
    // Initialize data when dashboard loads
    WidgetsBinding.instance.addPostFrameCallback((_) {
      context.read<DeviceProvider>().initialize();
    });
  }

  @override
  Widget build(BuildContext context) {
    return Consumer<DeviceProvider>(
      builder: (context, deviceProvider, child) {
        return ContentView(
          child: RefreshIndicator(
            onRefresh: () => deviceProvider.refresh(),
            child: SingleChildScrollView(
              physics: const AlwaysScrollableScrollPhysics(),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  // Header with connection status
                  Row(
                    children: [
                      const Expanded(
                        child: PageHeader(
                          title: 'Dashboard',
                          description: 'デバイスのステータス、電力使用量のモニタリング',
                        ),
                      ),
                      const Gap(16),
                      _buildLastUpdateTime(deviceProvider),
                      const Gap(8),
                      ConnectionStatusIndicator(
                        connectionState: deviceProvider.connectionState,
                      ),
                    ],
                  ),
                  const Gap(24),

                  // Summary cards
                  DeviceSummaryCards(
                    totalDevices: deviceProvider.totalDevices,
                    activeDevices: deviceProvider.activeDevices,
                    totalPowerConsumption: deviceProvider.totalPowerConsumption,
                  ),
                  const Gap(24),

                  // Power consumption chart
                  if (deviceProvider.getPowerData().isNotEmpty) ...[
                    _buildSectionHeader('電力使用量'),
                    const Gap(16),
                    PowerConsumptionChart(
                      powerData: deviceProvider.getPowerData(),
                    ),
                    const Gap(24),
                  ],

                  // Device status cards
                  _buildSectionHeader('デバイス状況'),
                  const Gap(16),
                  _buildDeviceStatusSection(deviceProvider),

                  // Error handling
                  if (deviceProvider.error != null) ...[
                    const Gap(24),
                    _buildErrorCard(deviceProvider.error!),
                  ],

                  // Add some bottom padding for better scrolling
                  const Gap(32),
                ],
              ),
            ),
          ),
        );
      },
    );
  }

  Widget _buildSectionHeader(String title) {
    return Text(
      title,
      style: Theme.of(context).textTheme.titleLarge?.copyWith(
        fontWeight: FontWeight.bold,
      ),
    );
  }

  Widget _buildLastUpdateTime(DeviceProvider deviceProvider) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.end,
      children: [
        Text(
          '最終更新',
          style: Theme.of(context).textTheme.bodySmall?.copyWith(
            color: Theme.of(context).colorScheme.onSurface.withOpacity(0.7),
          ),
        ),
        Text(
          DateFormat('HH:mm:ss').format(DateTime.now()),
          style: Theme.of(context).textTheme.bodySmall?.copyWith(
            fontWeight: FontWeight.w500,
          ),
        ),
      ],
    );
  }

  Widget _buildDeviceStatusSection(DeviceProvider deviceProvider) {
    if (deviceProvider.isLoading && deviceProvider.devices.isEmpty) {
      return const Center(
        child: Padding(
          padding: EdgeInsets.all(32.0),
          child: CircularProgressIndicator(),
        ),
      );
    }

    if (deviceProvider.devices.isEmpty) {
      return _buildEmptyState();
    }

    // Determine grid layout based on screen size
    int crossAxisCount;
    double childAspectRatio;
    
    if (MediaQuery.of(context).size.width > 1200) {
      crossAxisCount = 4;
      childAspectRatio = 1.2;
    } else if (MediaQuery.of(context).size.width > 800) {
      crossAxisCount = 2;
      childAspectRatio = 1.1;
    } else {
      crossAxisCount = 1;
      childAspectRatio = 2.5;
    }

    return GridView.builder(
      shrinkWrap: true,
      physics: const NeverScrollableScrollPhysics(),
      gridDelegate: SliverGridDelegateWithFixedCrossAxisCount(
        crossAxisCount: crossAxisCount,
        childAspectRatio: childAspectRatio,
        crossAxisSpacing: 16,
        mainAxisSpacing: 16,
      ),
      itemCount: deviceProvider.devices.length,
      itemBuilder: (context, index) {
        final device = deviceProvider.devices[index];
        return DeviceStatusCard(
          device: device,
          onToggle: () => _toggleDevice(deviceProvider, device),
          onTap: () => _navigateToDeviceDetail(context, device),
        );
      },
    );
  }

  Widget _buildEmptyState() {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32.0),
        child: Column(
          children: [
            Icon(
              Icons.devices_other,
              size: 64,
              color: Theme.of(context).colorScheme.onSurface.withOpacity(0.5),
            ),
            const Gap(16),
            Text(
              'デバイスが見つかりません',
              style: Theme.of(context).textTheme.titleMedium?.copyWith(
                color: Theme.of(context).colorScheme.onSurface.withOpacity(0.7),
              ),
            ),
            const Gap(8),
            Text(
              'サーバーの設定を確認するか、デバイスを追加してください。',
              style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                color: Theme.of(context).colorScheme.onSurface.withOpacity(0.5),
              ),
              textAlign: TextAlign.center,
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildErrorCard(String error) {
    return Card(
      color: Theme.of(context).colorScheme.errorContainer,
      child: Padding(
        padding: const EdgeInsets.all(16.0),
        child: Row(
          children: [
            Icon(
              Icons.error,
              color: Theme.of(context).colorScheme.onErrorContainer,
            ),
            const Gap(12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    'エラーが発生しました',
                    style: Theme.of(context).textTheme.titleSmall?.copyWith(
                      color: Theme.of(context).colorScheme.onErrorContainer,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                  const Gap(4),
                  Text(
                    error,
                    style: Theme.of(context).textTheme.bodySmall?.copyWith(
                      color: Theme.of(context).colorScheme.onErrorContainer,
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _toggleDevice(DeviceProvider deviceProvider, Device device) async {
    try {
      final response = await deviceProvider.toggleDevice(device);
      if (!response.isSuccess) {
        _showErrorSnackBar('デバイスの制御に失敗しました: ${response.error}');
      }
    } catch (e) {
      _showErrorSnackBar('デバイスの制御に失敗しました: $e');
    }
  }

  void _navigateToDeviceDetail(BuildContext context, Device device) {
    // Navigate to device detail page (to be implemented)
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text('${device.deviceType} (${device.node}:${device.endpoint})'),
        duration: const Duration(seconds: 2),
      ),
    );
  }

  void _showErrorSnackBar(String message) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(message),
        backgroundColor: Theme.of(context).colorScheme.error,
        duration: const Duration(seconds: 4),
      ),
    );
  }
}
