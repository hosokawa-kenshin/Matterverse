import 'package:http/http.dart' as http;
import 'dart:convert';
import 'package:matterverse_app/config/post_config.dart';

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
