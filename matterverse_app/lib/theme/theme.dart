import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

class AppTheme {
  AppTheme._();

  static ThemeData get light => _themeData(Brightness.light);
  static ThemeData get dark => _themeData(Brightness.dark);

  static ThemeData _themeData(Brightness brightness) {
    final themeData = ThemeData.from(
      useMaterial3: true,
      colorScheme: ColorScheme.fromSeed(
        seedColor: Colors.deepPurple,
        brightness: brightness,
      ),
    );

    return themeData.copyWith(
      textTheme: themeData.textTheme.apply(
        fontFamily: GoogleFonts.poppins().fontFamily,
      ),
      appBarTheme: const AppBarTheme(scrolledUnderElevation: 0),
      dividerTheme: const DividerThemeData(space: 0),
      bottomNavigationBarTheme: const BottomNavigationBarThemeData(
        selectedLabelStyle: TextStyle(
          fontWeight: FontWeight.w600,
          fontSize: 12,
        ),
      ),
    );
  }
}