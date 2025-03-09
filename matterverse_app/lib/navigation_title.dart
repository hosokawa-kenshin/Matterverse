import 'package:flutter/material.dart';
import 'package:matterverse_app/router.dart';
import 'package:responsive_framework/responsive_framework.dart';

class NavigationTitle extends StatelessWidget {
  const NavigationTitle({super.key});

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    return SelectionContainer.disabled(
      child: MouseRegion(
        cursor: SystemMouseCursors.click,
        child: Visibility(
          visible: ResponsiveBreakpoints.of(context).largerThan(MOBILE),
          child: GestureDetector(
            onTap: () => const DashboardRoute().go(context),
            child: Text(
              'Matterverse',
              style: theme.textTheme.bodyLarge!.copyWith(
                fontWeight: FontWeight.w700,
              ),
            ),
          ),
        ),
      ),
    );
  }
}
