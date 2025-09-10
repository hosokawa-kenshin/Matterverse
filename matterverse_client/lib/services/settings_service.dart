import 'package:shared_preferences/shared_preferences.dart';
import 'package:logger/logger.dart';

class SettingsService {
  static const String _serverUrlKey = 'server_url';
  static const String _defaultServerUrl = 'http://localhost:8000';

  static final Logger _logger = Logger();
  static SettingsService? _instance;
  static SharedPreferences? _prefs;

  SettingsService._();

  static Future<SettingsService> getInstance() async {
    if (_instance == null) {
      _instance = SettingsService._();
      _prefs = await SharedPreferences.getInstance();
      _logger.i('SettingsService initialized');
    }
    return _instance!;
  }

  // Server URL settings
  Future<String> getServerUrl() async {
    final url = _prefs?.getString(_serverUrlKey) ?? _defaultServerUrl;
    _logger.d('Retrieved server URL: $url');
    return url;
  }

  Future<void> setServerUrl(String url) async {
    await _prefs?.setString(_serverUrlKey, url);
    _logger.i('Saved server URL: $url');
  }

  // Get all settings as a map for debugging
  Map<String, dynamic> getAllSettings() {
    return {
      'serverUrl': _prefs?.getString(_serverUrlKey) ?? _defaultServerUrl,
    };
  }

  // Clear all settings
  Future<void> clearAllSettings() async {
    await _prefs?.clear();
    _logger.i('Cleared all settings');
  }

  // Reset to default values
  Future<void> resetToDefaults() async {
    await setServerUrl(_defaultServerUrl);
    _logger.i('Reset settings to defaults');
  }
}
