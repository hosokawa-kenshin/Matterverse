import 'package:flutter/material.dart';
import 'package:gap/gap.dart';

import 'package:matterverse_app/navigation/navigation_title.dart';

class NavigationAppBar extends StatelessWidget implements PreferredSizeWidget {
  const NavigationAppBar({super.key});

  @override
  Widget build(BuildContext context) {
    return AppBar(
      title: const NavigationTitle(),
      centerTitle: false,
      elevation: 4,
    );
  }

  @override
  Size get preferredSize => AppBar().preferredSize;
}
