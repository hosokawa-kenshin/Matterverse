import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'dart:convert';
import 'package:matterverse_app/config/post_config.dart';
import 'package:matterverse_app/widget/page_header.dart';
import 'package:animated_sidebar/animated_sidebar.dart';

class Screen extends StatefulWidget {
  const Screen({super.key});
  @override
  State<Screen> createState() => _ScreenState();
}

class _ScreenState extends State<Screen> {
  int activeTab = 0;

  final List<SidebarItem> items = [
    SidebarItem(icon: Icons.home_outlined, text: 'Home'),
    SidebarItem(icon: Icons.lightbulb_outline, text: 'Devices'),
    SidebarItem(icon: Icons.settings_outlined, text: 'Settings'),
  ];

  Future<void> sendCommand(command, node, endpoint) async {
    final response = await http.post(
      Uri.parse(PostConfig.sendCommandUri),
      headers: {'Content-Type': 'application/json'},
      body: json.encode({'command': '${command} ${node} ${endpoint}'}),
    );

    if (response.statusCode == 200) {
      var data = json.decode(response.body);
      print(data);
    } else {
      print('Failed to post data');
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
        body: Container(
      color: Color.fromARGB(255, 255, 255, 255),
      child: Row(crossAxisAlignment: CrossAxisAlignment.start, children: [
        AnimatedSidebar(
          margin: const EdgeInsets.fromLTRB(16, 24, 0, 24),
          expanded: MediaQuery.of(context).size.width > 600,
          items: items,
          selectedIndex: activeTab,
          autoSelectedIndex: false,
          onItemSelected: (index) => setState(() => activeTab = index),
          duration: const Duration(milliseconds: 100),
          frameDecoration: const BoxDecoration(
            color: Color.fromARGB(255, 48, 54, 87),
            borderRadius: BorderRadius.all(Radius.circular(10)),
          ),
          minSize: 90,
          maxSize: 250,
          itemIconSize: 26,
          itemIconColor: Colors.white,
          itemHoverColor: Colors.grey.withOpacity(0.3),
          itemSelectedColor: Colors.grey.withOpacity(0.3),
          itemTextStyle: const TextStyle(color: Colors.white, fontSize: 20),
          itemSelectedBorder: const BorderRadius.all(
            Radius.circular(5),
          ),
          itemMargin: 16,
          itemSpaceBetween: 10,
          headerIcon: Icons.device_hub_outlined,
          headerIconSize: 30,
          headerIconColor: Colors.amberAccent,
          headerTextStyle: const TextStyle(
              fontSize: 24, fontWeight: FontWeight.w600, color: Colors.white),
          headerText: 'Matterverse',
        ),
        Expanded(
          child: _buildPage(activeTab),
        ),
      ]),
    ));
  }

  List<Map<String, String>> deviceList = [
    {"name": "Tapo Smart Plug"},
  ];

  bool _isChecked = true;
  Widget _buildPage(int idx) {
    switch (idx) {
      case 0:
        return Text("Home"); //_buildHome();
      case 1:
        return Wrap(children: <Widget>[
          PageHeader(title: "Devices", description: "description"),
          SwitchListTile(
            title: Text(deviceList[0]["name"] ?? ''),
            value: _isChecked,
            onChanged: (bool value) {
              sendCommand("onoff toggle", 100, 1);
              setState(() {
                _isChecked = value;
              });
            },
          )
        ]); //_buildDevices();
      case 2:
        return Text("Setting"); //_buildSettings();
      default:
        return Text("Error");
    }
  }
}
