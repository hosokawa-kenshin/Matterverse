import 'package:flutter/material.dart';
import 'package:http/http.dart' as http;
import 'dart:convert';

class Screen extends StatefulWidget {
  const Screen({super.key});
  @override
  State<Screen> createState() => _ScreenState();
}

class _ScreenState extends State<Screen> {
  bool _isChecked = true;

  Future<void> postData() async {
    final response = await http.post(
      Uri.parse('https://localhost:8000/send_command'),
      headers: {'Content-Type': 'application/json'},
      body: json.encode({'command': 'onoff toggle 100 1'}),
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
      appBar: AppBar(
        backgroundColor: Colors.indigoAccent,
        title: Text("Matterverse"),
      ),
      body:
          Column(mainAxisAlignment: MainAxisAlignment.start, children: <Widget>[
        Row(
          mainAxisAlignment: MainAxisAlignment.spaceAround,
          crossAxisAlignment: CrossAxisAlignment.center,
          mainAxisSize: MainAxisSize.max,
          children: <Widget>[
            const Icon(Icons.outlet_outlined),
            Switch(
                value: _isChecked,
                onChanged: (value) {
                  postData();
                  setState(() {
                    _isChecked = value;
                  });
                })
          ],
        ),
      ]),
      drawer: Drawer(
        child: ListView(
          children: [
            DrawerHeader(
              child: Text(
                'Matterverse',
                style: TextStyle(
                  fontSize: 24,
                  color: Colors.white,
                ),
              ),
              decoration: BoxDecoration(
                color: Colors.indigoAccent,
              ),
            ),
            ListTile(
              leading: const Icon(Icons.space_dashboard_outlined),
              title: const Text("ダッシュボード"),
              onTap: () {},
            ),
            ListTile(
              leading: const Icon(Icons.login),
              title: const Text("メニュー2"),
              onTap: () {},
            ),
            ListTile(
              leading: const Icon(Icons.favorite),
              title: const Text("メニュー3"),
              onTap: () {},
            )
          ],
        ),
      ),
    );
  }
}
