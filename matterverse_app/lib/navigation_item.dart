import 'package:flutter/material.dart';
import 'package:recase/recase.dart';

enum NavigationItem {
  dashboard(iconData: Icons.dashboard_outlined),
  devices(iconData: Icons.lightbulb_outline),
  settings(iconData: Icons.settings_outlined);

  const NavigationItem({required this.iconData});
  final IconData iconData;
  String get label => name.pascalCase;
}
