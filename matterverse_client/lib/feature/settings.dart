import 'package:flutter/material.dart';
import 'package:gap/gap.dart';
import 'package:adaptive_theme/adaptive_theme.dart';
import 'package:provider/provider.dart';
import 'package:go_router/go_router.dart';
import 'package:matterverse_app/widget/page_header.dart';
import 'package:matterverse_app/widget/content_view.dart';
import '../providers/device_provider.dart';
import '../providers/auth_provider.dart';
import '../services/api_client.dart';
import '../services/websocket_service.dart';

class SettingsPage extends StatefulWidget {
  const SettingsPage({super.key});

  @override
  State<SettingsPage> createState() => _SettingsPageState();
}

class _SettingsPageState extends State<SettingsPage> {
  final _serverUrlController = TextEditingController();
  bool _isTestingConnection = false;
  String? _connectionTestResult;

  @override
  void initState() {
    super.initState();
    _serverUrlController.text = ApiConfig.baseUrl;
  }

  @override
  void dispose() {
    _serverUrlController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return ContentView(
      child: SingleChildScrollView(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const PageHeader(
              title: '設定',
              description: 'アプリケーションの設定を管理',
            ),
            const Gap(24),

            // User information
            _buildUserInformation(),
            const Gap(24),

            // Server settings
            _buildServerSettings(),
            const Gap(24),

            // Theme settings
            _buildThemeSettings(),
            const Gap(24),

            // Data settings
            _buildDataSettings(),
            const Gap(24),

            // App information
            _buildAppInformation(),
          ],
        ),
      ),
    );
  }

  Widget _buildServerSettings() {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const Icon(Icons.dns, color: Colors.blue),
                const Gap(8),
                Text(
                  'サーバー設定',
                  style: Theme.of(context).textTheme.titleMedium?.copyWith(
                        fontWeight: FontWeight.bold,
                      ),
                ),
              ],
            ),
            const Gap(16),

            // Server URL input
            TextField(
              controller: _serverUrlController,
              decoration: InputDecoration(
                labelText: 'サーバーURL',
                hintText: 'http://localhost:8080',
                prefixIcon: const Icon(Icons.link),
                border: const OutlineInputBorder(),
                suffixIcon: IconButton(
                  icon: const Icon(Icons.science),
                  onPressed: _isTestingConnection ? null : _testConnection,
                  tooltip: '接続テスト',
                ),
              ),
              keyboardType: TextInputType.url,
            ),
            const Gap(12),

            // Connection test result
            if (_connectionTestResult != null) ...[
              Container(
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: _connectionTestResult!.contains('成功')
                      ? Colors.green.withOpacity(0.1)
                      : Colors.red.withOpacity(0.1),
                  borderRadius: BorderRadius.circular(8),
                  border: Border.all(
                    color: _connectionTestResult!.contains('成功')
                        ? Colors.green
                        : Colors.red,
                  ),
                ),
                child: Row(
                  children: [
                    Icon(
                      _connectionTestResult!.contains('成功')
                          ? Icons.check_circle
                          : Icons.error,
                      color: _connectionTestResult!.contains('成功')
                          ? Colors.green
                          : Colors.red,
                    ),
                    const Gap(8),
                    Expanded(child: Text(_connectionTestResult!)),
                  ],
                ),
              ),
              const Gap(12),
            ],

            // Save button
            SizedBox(
              width: double.infinity,
              child: ElevatedButton.icon(
                onPressed: _saveServerSettings,
                icon: const Icon(Icons.save),
                label: const Text('設定を保存'),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildThemeSettings() {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const Icon(Icons.palette, color: Colors.purple),
                const Gap(8),
                Text(
                  'テーマ設定',
                  style: Theme.of(context).textTheme.titleMedium?.copyWith(
                        fontWeight: FontWeight.bold,
                      ),
                ),
              ],
            ),
            const Gap(16),

            // Theme toggle buttons
            Row(
              children: [
                Expanded(
                  child: OutlinedButton.icon(
                    onPressed: () => AdaptiveTheme.of(context).setLight(),
                    icon: const Icon(Icons.light_mode),
                    label: const Text('ライト'),
                  ),
                ),
                const Gap(8),
                Expanded(
                  child: OutlinedButton.icon(
                    onPressed: () => AdaptiveTheme.of(context).setDark(),
                    icon: const Icon(Icons.dark_mode),
                    label: const Text('ダーク'),
                  ),
                ),
                const Gap(8),
                Expanded(
                  child: OutlinedButton.icon(
                    onPressed: () => AdaptiveTheme.of(context).setSystem(),
                    icon: const Icon(Icons.brightness_auto),
                    label: const Text('自動'),
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildDataSettings() {
    return Consumer<DeviceProvider>(
      builder: (context, deviceProvider, child) {
        return Card(
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    const Icon(Icons.storage, color: Colors.orange),
                    const Gap(8),
                    Text(
                      'データ管理',
                      style: Theme.of(context).textTheme.titleMedium?.copyWith(
                            fontWeight: FontWeight.bold,
                          ),
                    ),
                  ],
                ),
                const Gap(16),

                // Data statistics
                _buildDataStatistic(
                    '総デバイス数', '${deviceProvider.totalDevices}台'),
                _buildDataStatistic(
                    'アクティブデバイス', '${deviceProvider.activeDevices}台'),
                _buildDataStatistic(
                    '接続状態', deviceProvider.connectionState.displayName),

                const Gap(16),

                // Data management buttons
                Row(
                  children: [
                    Expanded(
                      child: OutlinedButton.icon(
                        onPressed: () => deviceProvider.refresh(),
                        icon: const Icon(Icons.refresh),
                        label: const Text('データ更新'),
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
        );
      },
    );
  }

  Widget _buildDataStatistic(String label, String value) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(label),
          Text(
            value,
            style: const TextStyle(fontWeight: FontWeight.w500),
          ),
        ],
      ),
    );
  }

  Widget _buildAppInformation() {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const Icon(Icons.info, color: Colors.teal),
                const Gap(8),
                Text(
                  'アプリケーション情報',
                  style: Theme.of(context).textTheme.titleMedium?.copyWith(
                        fontWeight: FontWeight.bold,
                      ),
                ),
              ],
            ),
            const Gap(16),

            _buildInfoRow('アプリ名', 'Matterverse'),
            _buildInfoRow('バージョン', '1.0.0'),

            const Gap(16),

            // About button
            SizedBox(
              width: double.infinity,
              child: OutlinedButton.icon(
                onPressed: _showAboutDialog,
                icon: const Icon(Icons.info_outline),
                label: const Text('このアプリについて'),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildInfoRow(String label, String value) {
    return Padding(
      padding: const EdgeInsets.symmetric(vertical: 4),
      child: Row(
        mainAxisAlignment: MainAxisAlignment.spaceBetween,
        children: [
          Text(label),
          Text(
            value,
            style: const TextStyle(fontWeight: FontWeight.w500),
          ),
        ],
      ),
    );
  }

  Future<void> _testConnection() async {
    setState(() {
      _isTestingConnection = true;
      _connectionTestResult = null;
    });

    try {
      final tempApiClient = ApiClient();
      tempApiClient.updateBaseUrl(_serverUrlController.text.trim());

      final isHealthy = await tempApiClient.checkHealth();

      setState(() {
        _connectionTestResult = isHealthy ? '✓ 接続に成功しました' : '✗ サーバーに接続できませんでした';
      });

      tempApiClient.dispose();
    } catch (e) {
      setState(() {
        _connectionTestResult = '✗ 接続エラー: ${e.toString()}';
      });
    } finally {
      setState(() {
        _isTestingConnection = false;
      });
    }
  }

  Future<void> _saveServerSettings() async {
    final newUrl = _serverUrlController.text.trim();
    if (newUrl.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('サーバーURLを入力してください')),
      );
      return;
    }

    // Show loading indicator
    showDialog(
      context: context,
      barrierDismissible: false,
      builder: (context) => const AlertDialog(
        content: Row(
          children: [
            CircularProgressIndicator(),
            SizedBox(width: 16),
            Text('サーバーに再接続中...'),
          ],
        ),
      ),
    );

    try {
      // Update server URL and reconnect
      await context.read<DeviceProvider>().updateServerUrl(newUrl);

      // Test connection after saving
      await _testConnection();

      if (mounted) {
        context.pop(); // Close loading dialog
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Row(
              children: [
                const Icon(Icons.check_circle, color: Colors.white),
                const SizedBox(width: 8),
                Text('サーバー設定を保存し、再接続しました'),
              ],
            ),
            backgroundColor: Colors.green,
          ),
        );
      }
    } catch (e) {
      if (mounted) {
        context.pop(); // Close loading dialog
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Row(
              children: [
                const Icon(Icons.error, color: Colors.white),
                const SizedBox(width: 8),
                Expanded(child: Text('サーバー設定の更新に失敗しました: $e')),
              ],
            ),
            backgroundColor: Colors.red,
            duration: const Duration(seconds: 5),
          ),
        );
      }
    }
  }

  void _showAboutDialog() {
    showAboutDialog(
      context: context,
      applicationName: 'Matterverse',
      applicationVersion: '1.0.0',
      applicationIcon: const Icon(Icons.home, size: 64),
      children: [
        const Gap(16),
        const Text(
          'Matterverseは、Matterプロトコル対応のスマートホームデバイスを'
          '統合管理するクロスプラットフォームアプリケーションです。',
        ),
        const Gap(16),
        const Text(
          '特徴:\n'
          '• リアルタイムデバイス監視\n'
          '• 電力使用量分析\n'
          '• 動的UI生成\n'
          '• クロスプラットフォーム対応',
        ),
      ],
    );
  }

  Widget _buildUserInformation() {
    return Consumer<AuthProvider>(
      builder: (context, authProvider, child) {
        return Card(
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    const Icon(Icons.person, color: Colors.green),
                    const Gap(8),
                    Text(
                      'ユーザー情報',
                      style: Theme.of(context).textTheme.titleMedium?.copyWith(
                            fontWeight: FontWeight.bold,
                          ),
                    ),
                  ],
                ),
                const Gap(16),
                ListTile(
                  leading: Icon(
                    authProvider.isAuthenticated
                        ? Icons.account_circle
                        : Icons.account_circle_outlined,
                  ),
                  title: const Text('ユーザー名'),
                  subtitle: Text(
                    authProvider.isAuthenticated
                        ? authProvider.username ?? '未設定'
                        : 'ゲスト（未ログイン）',
                  ),
                  contentPadding: EdgeInsets.zero,
                ),
                const Gap(16),
                SizedBox(
                  width: double.infinity,
                  child: authProvider.isAuthenticated
                      ? ElevatedButton.icon(
                          onPressed: authProvider.isLoading
                              ? null
                              : () => _showLogoutDialog(authProvider),
                          icon: authProvider.isLoading
                              ? const SizedBox(
                                  width: 16,
                                  height: 16,
                                  child:
                                      CircularProgressIndicator(strokeWidth: 2),
                                )
                              : const Icon(Icons.logout),
                          label: const Text('ログアウト'),
                          style: ElevatedButton.styleFrom(
                            foregroundColor:
                                Theme.of(context).colorScheme.error,
                          ),
                        )
                      : ElevatedButton.icon(
                          onPressed: () => _navigateToLogin(),
                          icon: const Icon(Icons.login),
                          label: const Text('ログイン'),
                          style: ElevatedButton.styleFrom(
                            foregroundColor:
                                Theme.of(context).colorScheme.primary,
                          ),
                        ),
                ),
              ],
            ),
          ),
        );
      },
    );
  }

  void _showLogoutDialog(AuthProvider authProvider) {
    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('ログアウト'),
        content: const Text('ログアウトしますか？'),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('キャンセル'),
          ),
          FilledButton(
            onPressed: () async {
              Navigator.of(context).pop();
              await authProvider.logout();
            },
            child: const Text('ログアウト'),
          ),
        ],
      ),
    );
  }

  void _navigateToLogin() {
    context.go('/login');
  }
}
