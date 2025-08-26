import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

class AuthProvider extends ChangeNotifier {
  String? _username;
  bool _isLoading = false;

  String? get username => _username;
  bool get isAuthenticated => _username != null;
  bool get isLoading => _isLoading;

  AuthProvider() {
    _loadUserFromStorage();
  }

  Future<void> _loadUserFromStorage() async {
    _isLoading = true;
    notifyListeners();

    try {
      final prefs = await SharedPreferences.getInstance();
      _username = prefs.getString('username');
    } catch (e) {
      debugPrint('ユーザー情報の読み込みに失敗: $e');
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  Future<bool> login(String username) async {
    if (username.trim().isEmpty) {
      return false;
    }

    _isLoading = true;
    notifyListeners();

    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString('username', username.trim());
      _username = username.trim();
      notifyListeners();
      return true;
    } catch (e) {
      debugPrint('ログインに失敗: $e');
      return false;
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }

  Future<void> logout() async {
    _isLoading = true;
    notifyListeners();

    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.remove('username');
      _username = null;
      notifyListeners();
    } catch (e) {
      debugPrint('ログアウトに失敗: $e');
    } finally {
      _isLoading = false;
      notifyListeners();
    }
  }
}
