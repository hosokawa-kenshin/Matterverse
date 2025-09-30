import 'package:flutter/material.dart';
import 'package:gap/gap.dart';
import 'package:matterverse_app/widget/page_header.dart';
import 'package:matterverse_app/widget/content_view.dart';
import 'package:provider/provider.dart';
import '../providers/device_provider.dart';
import '../models/device_model.dart';
import '../widgets/device_detail_card.dart';
import '../widgets/connection_status_indicator.dart';
import '../widgets/device_summary_cards.dart';

class DevicesPage extends StatefulWidget {
  const DevicesPage({super.key});

  @override
  State<DevicesPage> createState() => _DevicesPageState();
}

class _DevicesPageState extends State<DevicesPage> {
  String _searchQuery = '';
  String _selectedDeviceType = 'All';

  @override
  Widget build(BuildContext context) {
    return Consumer<DeviceProvider>(
      builder: (context, deviceProvider, child) {
        final filteredDevices = _filterDevices(deviceProvider.devices);

        return Scaffold(
          body: ContentView(
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
                            title: 'デバイス管理',
                            description: 'デバイスの詳細制御と監視',
                          ),
                        ),
                        ConnectionStatusIndicator(
                          connectionState: deviceProvider.connectionState,
                        ),
                      ],
                    ),
                    const Gap(24),

                    // Search and filter controls
                    _buildSearchAndFilters(deviceProvider),
                    const Gap(24),

                    // Device statistics
                    _buildDeviceStatistics(deviceProvider),
                    const Gap(24),

                    // Device list
                    _buildDeviceList(filteredDevices, deviceProvider),

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
          ),
          floatingActionButton: FloatingActionButton(
            onPressed: () => _showAddDeviceDialog(context, deviceProvider),
            tooltip: 'デバイスを追加',
            child: const Icon(Icons.add),
          ),
        );
      },
    );
  }

  Widget _buildSearchAndFilters(DeviceProvider deviceProvider) {
    final deviceTypes = ['All', 'Plug', 'Sensor', 'Light'].where((type) {
      if (type == 'All') return true;
      return deviceProvider.devices.any((device) =>
          device.deviceType.toLowerCase().contains(type.toLowerCase()));
    }).toList();

    return Column(
      children: [
        // Search bar
        TextField(
          decoration: InputDecoration(
            hintText: 'デバイスを検索...',
            prefixIcon: const Icon(Icons.search),
            border: OutlineInputBorder(
              borderRadius: BorderRadius.circular(12),
            ),
            filled: true,
            fillColor: Theme.of(context).colorScheme.surface,
          ),
          onChanged: (value) {
            setState(() {
              _searchQuery = value;
            });
          },
        ),
        const Gap(16),

        // Filter chips
        SingleChildScrollView(
          scrollDirection: Axis.horizontal,
          child: Row(
            children: deviceTypes.map((type) {
              final isSelected = _selectedDeviceType == type;
              return Padding(
                padding: const EdgeInsets.only(right: 8),
                child: FilterChip(
                  label: Text(_getDeviceTypeDisplayName(type)),
                  selected: isSelected,
                  onSelected: (selected) {
                    setState(() {
                      _selectedDeviceType = selected ? type : 'All';
                    });
                  },
                  backgroundColor: Theme.of(context).colorScheme.surface,
                  selectedColor: Theme.of(context).colorScheme.primaryContainer,
                ),
              );
            }).toList(),
          ),
        ),
      ],
    );
  }

  Widget _buildDeviceStatistics(DeviceProvider deviceProvider) {
    return DeviceSummaryCards(
      totalDevices: deviceProvider.totalDevices,
      activeDevices: deviceProvider.activeDevices,
      totalPowerConsumption: deviceProvider.totalPowerConsumption,
    );
  }

  Widget _buildDeviceList(List<Device> devices, DeviceProvider deviceProvider) {
    if (deviceProvider.isLoading && devices.isEmpty) {
      return const Center(
        child: Padding(
          padding: EdgeInsets.all(32.0),
          child: CircularProgressIndicator(),
        ),
      );
    }

    if (devices.isEmpty) {
      return _buildEmptyState();
    }

    return _buildListLayout(devices, deviceProvider);
  }

  Widget _buildListLayout(List<Device> devices, DeviceProvider deviceProvider) {
    return Column(
      children: devices
          .map((device) => Padding(
                padding: const EdgeInsets.only(bottom: 16),
                child: ConstrainedBox(
                  constraints: const BoxConstraints(),
                  child: DeviceDetailCard(
                    device: device,
                    onCommand: (device, cluster, command, args) =>
                        _executeCommand(
                            deviceProvider, device, cluster, command, args),
                  ),
                ),
              ))
          .toList(),
    );
  }

  Widget _buildEmptyState() {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(32.0),
        child: Column(
          children: [
            Icon(
              Icons.search_off,
              size: 64,
              color: Theme.of(context).colorScheme.onSurface.withOpacity(0.5),
            ),
            const Gap(16),
            Text(
              _searchQuery.isNotEmpty ? '検索結果が見つかりません' : 'デバイスが見つかりません',
              style: Theme.of(context).textTheme.titleMedium?.copyWith(
                    color: Theme.of(context)
                        .colorScheme
                        .onSurface
                        .withOpacity(0.7),
                  ),
            ),
            const Gap(8),
            Text(
              _searchQuery.isNotEmpty
                  ? '別のキーワードで検索してください。'
                  : 'サーバーの設定を確認するか、デバイスを追加してください。',
              style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                    color: Theme.of(context)
                        .colorScheme
                        .onSurface
                        .withOpacity(0.5),
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

  List<Device> _filterDevices(List<Device> devices) {
    var filtered = devices;

    // Filter by search query
    if (_searchQuery.isNotEmpty) {
      filtered = deviceProvider.searchDevices(_searchQuery);
    }

    // Filter by device type
    if (_selectedDeviceType != 'All') {
      filtered = filtered
          .where((device) => device.deviceType
              .toLowerCase()
              .contains(_selectedDeviceType.toLowerCase()))
          .toList();
    }

    return filtered;
  }

  String _getDeviceTypeDisplayName(String type) {
    switch (type) {
      case 'All':
        return '全て';
      case 'Plug':
        return 'プラグ';
      case 'Sensor':
        return 'センサー';
      case 'Light':
        return '照明';
      default:
        return type;
    }
  }

  Future<void> _executeCommand(
    DeviceProvider deviceProvider,
    Device device,
    String cluster,
    String command,
    Map<String, dynamic>? args,
  ) async {
    try {
      final response = await deviceProvider.executeDeviceCommand(
        device,
        cluster,
        command,
        args: args,
      );

      if (!response.isSuccess) {
        _showErrorSnackBar('コマンド実行に失敗しました: ${response.error}');
      }
    } catch (e) {
      _showErrorSnackBar('コマンド実行に失敗しました: $e');
    }
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

  void _showSuccessSnackBar(String message) {
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(message),
        backgroundColor: Theme.of(context).colorScheme.primary,
        duration: const Duration(seconds: 3),
      ),
    );
  }

  void _showAddDeviceDialog(BuildContext context, DeviceProvider deviceProvider) {
    final pairingCodeController = TextEditingController();

    showDialog(
      context: context,
      builder: (BuildContext context) {
        bool isLoading = false;

        return StatefulBuilder(
          builder: (context, setState) {
            return AlertDialog(
              title: const Text('デバイスの追加'),
              content: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text('マニュアルペアリングコードを入力してください'),
                  const Gap(16),
                  TextField(
                    controller: pairingCodeController,
                    decoration: InputDecoration(
                      labelText: 'マニュアルペアリングコード(11桁)',
                      hintText: '例: 34970112332',
                      border: OutlineInputBorder(
                        borderRadius: BorderRadius.circular(8),
                      ),
                      prefixIcon: const Icon(Icons.qr_code),
                    ),
                    keyboardType: TextInputType.number,
                    enabled: !isLoading,
                  ),
                  if (isLoading) ...[
                    const Gap(16),
                    const Row(
                      children: [
                        SizedBox(
                          width: 20,
                          height: 20,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        ),
                        Gap(12),
                        Text('デバイスを追加中...'),
                      ],
                    ),
                  ],
                ],
              ),
              actions: [
                TextButton(
                  onPressed: isLoading ? null : () => Navigator.of(context).pop(),
                  child: const Text('キャンセル'),
                ),
                ElevatedButton(
                  onPressed: isLoading
                      ? null
                      : () async {
                          await _addDevice(
                            context,
                            deviceProvider,
                            pairingCodeController.text.trim(),
                            () => setState(() => isLoading = true),
                            () => setState(() => isLoading = false),
                          );
                        },
                  child: const Text('追加'),
                ),
              ],
            );
          },
        );
      },
    );
  }

  Future<void> _addDevice(
    BuildContext context,
    DeviceProvider deviceProvider,
    String pairingCode,
    VoidCallback setLoadingTrue,
    VoidCallback setLoadingFalse,
  ) async {
    if (pairingCode.isEmpty) {
      _showErrorSnackBar('ペアリングコードを入力してください');
      return;
    }

    setLoadingTrue();

    try {
      final success = await deviceProvider.addDevice(pairingCode);

      if (success) {
        Navigator.of(context).pop();
        _showSuccessSnackBar('デバイスが正常に追加されました');
        // デバイスリストを更新
        await deviceProvider.refresh();
      } else {
        _showErrorSnackBar('デバイスの追加に失敗しました');
      }
    } catch (e) {
      _showErrorSnackBar('エラーが発生しました: $e');
    } finally {
      setLoadingFalse();
    }
  }

  DeviceProvider get deviceProvider => context.read<DeviceProvider>();
}
