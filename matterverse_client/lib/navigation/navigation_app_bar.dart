import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:gap/gap.dart';
import 'package:go_router/go_router.dart';

import 'package:matterverse_app/navigation/navigation_title.dart';
import '../providers/auth_provider.dart';

class NavigationAppBar extends StatelessWidget implements PreferredSizeWidget {
  const NavigationAppBar({super.key});

  @override
  Widget build(BuildContext context) {
    return AppBar(
      title: const NavigationTitle(),
      centerTitle: false,
      elevation: 4,
      actions: [
        Consumer<AuthProvider>(
          builder: (context, authProvider, child) {
            if (authProvider.isLoading) {
              return const Padding(
                padding: EdgeInsets.all(16.0),
                child: SizedBox(
                  width: 20,
                  height: 20,
                  child: CircularProgressIndicator(strokeWidth: 2),
                ),
              );
            }

            return Padding(
              padding:
                  const EdgeInsets.symmetric(horizontal: 16.0, vertical: 8.0),
              child: Row(
                mainAxisSize: MainAxisSize.min,
                children: [
                  Icon(
                    authProvider.isAuthenticated
                        ? Icons.account_circle
                        : Icons.account_circle_outlined,
                    color: authProvider.isAuthenticated
                        ? Theme.of(context).colorScheme.primary
                        : Theme.of(context).colorScheme.onSurfaceVariant,
                    size: 24,
                  ),
                  const Gap(8),
                  Column(
                    mainAxisAlignment: MainAxisAlignment.center,
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        authProvider.username ?? 'ゲスト',
                        style: Theme.of(context).textTheme.bodyMedium?.copyWith(
                              fontWeight: FontWeight.w600,
                              color: Theme.of(context).colorScheme.onSurface,
                            ),
                      ),
                      Text(
                        authProvider.isAuthenticated ? 'ログイン済み' : '未ログイン',
                        style: Theme.of(context).textTheme.bodySmall?.copyWith(
                              color: authProvider.isAuthenticated
                                  ? Theme.of(context).colorScheme.primary
                                  : Theme.of(context)
                                      .colorScheme
                                      .onSurfaceVariant,
                              fontSize: 11,
                            ),
                      ),
                    ],
                  ),
                  const Gap(12),
                  if (authProvider.isAuthenticated)
                    IconButton(
                      onPressed: authProvider.isLoading
                          ? null
                          : () => _showLogoutDialog(context, authProvider),
                      icon: const Icon(Icons.logout),
                      tooltip: 'ログアウト',
                      style: IconButton.styleFrom(
                        foregroundColor: Theme.of(context).colorScheme.error,
                      ),
                    )
                  else
                    IconButton(
                      onPressed: () => _navigateToLogin(context),
                      icon: const Icon(Icons.login),
                      tooltip: 'ログイン',
                      style: IconButton.styleFrom(
                        foregroundColor: Theme.of(context).colorScheme.primary,
                      ),
                    ),
                ],
              ),
            );
          },
        ),
      ],
    );
  }

  @override
  Size get preferredSize => const Size.fromHeight(kToolbarHeight);

  void _showLogoutDialog(BuildContext context, AuthProvider authProvider) {
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

  void _navigateToLogin(BuildContext context) {
    context.go('/login');
  }
}
