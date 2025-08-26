import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:go_router/go_router.dart';
import 'package:matterverse_app/navigation/scaffold_with_navigation.dart';
import 'package:matterverse_app/feature/dashboard.dart';
import 'package:matterverse_app/feature/devices.dart';
import 'package:matterverse_app/feature/settings.dart';
import 'package:matterverse_app/feature/login.dart';
import 'package:matterverse_app/providers/auth_provider.dart';

part 'router.g.dart';

final _rootNavigatorKey = GlobalKey<NavigatorState>(debugLabel: 'root');

// AuthProviderを受け取るファクトリー関数
GoRouter createRouter(AuthProvider authProvider) {
  return GoRouter(
    routes: $appRoutes,
    debugLogDiagnostics: kDebugMode,
    navigatorKey: _rootNavigatorKey,
    redirect: (context, state) {
      final isLoading = authProvider.isLoading;
      final isAuthenticated = authProvider.isAuthenticated;
      final isLoginPage = state.matchedLocation == '/login';
      final isDevicesPage = state.matchedLocation == '/devices';
      final isSettingsPage = state.matchedLocation == '/settings';

      if (isLoading) return null;

      if (!isAuthenticated) {
        if (isDevicesPage) {
          return '/login';
        }
        return null;
      }

      if (isAuthenticated && isLoginPage) {
        return '/';
      }

      return null;
    },
    refreshListenable: authProvider,
  );
}

@TypedGoRoute<LoginRoute>(
  path: '/login',
)
class LoginRoute extends GoRouteData {
  const LoginRoute();

  @override
  Widget build(BuildContext context, GoRouterState state) {
    return const LoginPage();
  }
}

@TypedStatefulShellRoute<ShellRouteData>(
  branches: [
    TypedStatefulShellBranch(
      routes: [
        TypedGoRoute<DashboardRoute>(
          path: '/',
        ),
      ],
    ),
    TypedStatefulShellBranch(
      routes: [
        TypedGoRoute<DevicesPageRoute>(
          path: '/devices',
        ),
      ],
    ),
    TypedStatefulShellBranch(
      routes: [
        TypedGoRoute<SettingsPageRoute>(
          path: '/settings',
        ),
      ],
    ),
  ],
)
class ShellRouteData extends StatefulShellRouteData {
  const ShellRouteData();

  @override
  Widget builder(
    BuildContext context,
    GoRouterState state,
    StatefulNavigationShell navigationShell,
  ) {
    return SelectionArea(
      child: ScaffoldWithNavigation(
        navigationShell: navigationShell,
      ),
    );
  }
}

class DashboardRoute extends GoRouteData {
  const DashboardRoute();

  @override
  Widget build(BuildContext context, GoRouterState state) {
    return const DashBoardPage();
  }
}

class DevicesPageRoute extends GoRouteData {
  const DevicesPageRoute();

  @override
  Widget build(BuildContext context, GoRouterState state) {
    return DevicesPage();
  }
}

class SettingsPageRoute extends GoRouteData {
  const SettingsPageRoute();

  @override
  Widget build(BuildContext context, GoRouterState state) {
    return SettingsPage();
  }
}
