import 'package:flutter/material.dart';
import 'package:gap/gap.dart';
import 'package:responsive_framework/responsive_framework.dart';
import 'package:matterverse_app/widget/page_header.dart';
import 'package:matterverse_app/widget/content_view.dart';
import 'package:matterverse_app/protocol/post.dart';
import 'package:web_socket_channel/web_socket_channel.dart';

List<Map<String, dynamic>> deviceList = [
  {"name": "Tapo Smart Plug", "isChecked": false},
];

class DevicesPage extends StatefulWidget {
  const DevicesPage({super.key});

  @override
  State<DevicesPage> createState() => _DevicesPageState();
}

class _DevicesPageState extends State<DevicesPage> {
  late WebSocketChannel channel;

  @override

  void initState() {
    super.initState();
    connectToWebSocket();
  }

  void connectToWebSocket() {
    channel = WebSocketChannel.connect(
      Uri.parse('ws://localhost:8000/ws'),
    );
    List<String> messages = [];
    channel.stream.listen(
          (dynamic message) {
        setState(() {
          try {
            messages.add(message.toString());
          } catch (e) {
            messages.add('Error decoding message: $message');
          }
        });
      },
      onError: (error) {
        debugPrint('WebSocket Error: $error');
      },
      onDone: () {
        debugPrint('WebSocket Connection Closed');
      },
    );
  }

  void sendCommand(command, node, endpoint){
    try {
      channel.sink.add("$command $node $endpoint");
    } catch (e){
      debugPrint('Error sending message: $e');
    }
  }

  Widget build(BuildContext context) {
    final responsive = ResponsiveBreakpoints.of(context);

    return ContentView(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const PageHeader(
            title: 'Devices',
            description: 'デバイスの管理と制御',
          ),
          const Gap(16),
          SwitchListTile(
            title: Text(deviceList[0]["name"] ?? ''),
            value: deviceList[0]["isChecked"] ?? false,
            onChanged: (bool value) {
              sendCommand("onoff toggle", 100, 1);
              setState(() {
                deviceList[0]["isChecked"] = value;
              });
            },
          )
        ],
      ),
    );
  }
}
