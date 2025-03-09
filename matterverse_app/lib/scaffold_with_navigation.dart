import 'package:flutter/material.dart';
import 'package:matterverse_app/main.dart';
import 'package:matterverse_app/scaffold_with_navigation.dart';
import 'package:matterverse_app/navigation_app_bar.dart';
import 'package:matterverse_app/navigation_item.dart';
import 'package:matterverse_app/theme_mode_button.dart';
import 'package:go_router/go_router.dart';
import 'package:responsive_framework/responsive_framework.dart';

class ScaffoldWithNavigation extends StatelessWidget {
  const ScaffoldWithNavigation({
    super.key,
    required this.navigationShell,
  });

  final StatefulNavigationShell navigationShell;

  @override
  Widget build(BuildContext context) {
    final breakpoint = ResponsiveBreakpoints.of(context).breakpoint;
    return switch (breakpoint.name) {
      MOBILE || TABLET => _ScaffoldWithDrawer(navigationShell),
      (_) => _ScaffoldWithNavigationRail(navigationShell),
    };
  }
}

class _ScaffoldWithNavigationRail extends StatelessWidget {
  const _ScaffoldWithNavigationRail(this.navigationShell);

  final StatefulNavigationShell navigationShell;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final colorScheme = theme.colorScheme;
    return Scaffold(
      appBar: const NavigationAppBar(),
      body: Row(
        children: [
          Column(
            children: [
              Expanded(
                child: _NavigationRail(
                  navigationShell: navigationShell,
                  expand: false,
                ),
              ),
              const Padding(
                padding: EdgeInsets.all(16),
                child: ThemeModeButton.icon(),
              ),
            ],
          ),
          VerticalDivider(
            thickness: 1,
            width: 1,
            color: colorScheme.primary.withOpacity(0.2),
          ),
          Expanded(child: navigationShell),
        ],
      ),
    );
  }
}

class _ScaffoldWithDrawer extends StatelessWidget {
  const _ScaffoldWithDrawer(this.navigationShell);

  final StatefulNavigationShell navigationShell;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return Scaffold(
      appBar: const NavigationAppBar(),
      body: navigationShell,
      drawer: Drawer(
        child: Column(
          children: [
            DrawerHeader(
              decoration: const BoxDecoration(border: Border()),
              margin: EdgeInsets.zero,
              child: Center(
                child: Text(
                  MyApp.title,
                  style: theme.textTheme.bodyMedium!
                      .copyWith(fontWeight: FontWeight.w600),
                ),
              ),
            ),
            Expanded(
              child: _NavigationRail(
                navigationShell: navigationShell,
                expand: true,
              ),
            ),
            const Padding(
              padding: EdgeInsets.all(16),
              child: ThemeModeButton.outlined(),
            ),
          ],
        ),
      ),
    );
  }
}

class _NavigationRail extends StatelessWidget {
  const _NavigationRail({required this.navigationShell, required this.expand});

  final StatefulNavigationShell navigationShell;
  final bool expand;

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return NavigationRail(
      extended: expand,
      selectedIndex: navigationShell.currentIndex,
      unselectedLabelTextStyle: theme.textTheme.bodyMedium,
      selectedLabelTextStyle: theme.textTheme.bodyMedium!.copyWith(
        fontWeight: FontWeight.bold,
      ),
      onDestinationSelected: (index) {
        navigationShell.goBranch(
          index,
          initialLocation: index == navigationShell.currentIndex,
        );
      },
      destinations: [
        for (final item in NavigationItem.values)
          NavigationRailDestination(
            icon: Icon(item.iconData),
            label: Text(item.label),
          ),
      ],
    );
  }
}
