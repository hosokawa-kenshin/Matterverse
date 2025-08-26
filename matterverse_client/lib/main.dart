import 'package:flutter/material.dart';
import 'package:flutter/foundation.dart';
import 'package:flutter_web_plugins/url_strategy.dart';
import 'package:adaptive_theme/adaptive_theme.dart';
import 'package:matterverse_app/theme/theme.dart';
import 'package:responsive_framework/responsive_framework.dart';
import 'package:matterverse_app/router.dart';
import 'package:provider/provider.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'providers/device_provider.dart';
import 'providers/auth_provider.dart';

void main() {
  // ハッシュルーティングを無効化してクリーンなURLを使用
  if (kIsWeb) {
    usePathUrlStrategy();
  }

  runApp(MyApp());
}

class MyApp extends StatelessWidget {
  const MyApp({super.key});
  static const title = 'Matterverse';

  @override
  Widget build(BuildContext context) {
    return MultiProvider(
      providers: [
        ChangeNotifierProvider(create: (_) => AuthProvider()),
        ChangeNotifierProvider(create: (_) => DeviceProvider()),
      ],
      child: Consumer<AuthProvider>(
        builder: (context, authProvider, child) {
          final router = createRouter(authProvider);

          return AdaptiveTheme(
            light: AppTheme.light,
            dark: AppTheme.dark,
            initial: AdaptiveThemeMode.system,
            builder: (theme, darkTheme) => ResponsiveBreakpoints.builder(
              breakpoints: [
                const Breakpoint(start: 0, end: 450, name: MOBILE),
                const Breakpoint(start: 451, end: 960, name: TABLET),
                const Breakpoint(
                    start: 961, end: double.infinity, name: DESKTOP),
              ],
              child: MaterialApp.router(
                title: title,
                routerConfig: router,
                theme: theme,
                darkTheme: darkTheme,
                // Add internationalization support
                localizationsDelegates: const [
                  GlobalMaterialLocalizations.delegate,
                  GlobalWidgetsLocalizations.delegate,
                  GlobalCupertinoLocalizations.delegate,
                ],
                supportedLocales: const [
                  Locale('en', 'US'),
                  Locale('ja', 'JP'),
                ],
                // Set default locale
                locale: const Locale('ja', 'JP'),
                debugShowCheckedModeBanner: false,
              ),
            ),
          );
        },
      ),
    );
  }
}
