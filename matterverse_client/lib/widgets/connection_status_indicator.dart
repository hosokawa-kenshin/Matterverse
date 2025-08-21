import 'package:flutter/material.dart';
import '../services/websocket_service.dart';

class ConnectionStatusIndicator extends StatelessWidget {
  final WebSocketConnectionState connectionState;

  const ConnectionStatusIndicator({
    super.key,
    required this.connectionState,
  });

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      decoration: BoxDecoration(
        color: _getBackgroundColor(context),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(
          color: _getBorderColor(context),
          width: 1,
        ),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          _buildStatusIcon(),
          const SizedBox(width: 6),
          Text(
            connectionState.displayName,
            style: Theme.of(context).textTheme.bodySmall?.copyWith(
              color: _getTextColor(context),
              fontWeight: FontWeight.w500,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildStatusIcon() {
    switch (connectionState) {
      case WebSocketConnectionState.connected:
        return const Icon(
          Icons.wifi,
          size: 16,
          color: Colors.green,
        );
      case WebSocketConnectionState.connecting:
      case WebSocketConnectionState.reconnecting:
        return SizedBox(
          width: 16,
          height: 16,
          child: CircularProgressIndicator(
            strokeWidth: 2,
            valueColor: AlwaysStoppedAnimation<Color>(
              Colors.orange.shade600,
            ),
          ),
        );
      case WebSocketConnectionState.error:
        return const Icon(
          Icons.error,
          size: 16,
          color: Colors.red,
        );
      case WebSocketConnectionState.disconnected:
      default:
        return const Icon(
          Icons.wifi_off,
          size: 16,
          color: Colors.grey,
        );
    }
  }

  Color _getBackgroundColor(BuildContext context) {
    switch (connectionState) {
      case WebSocketConnectionState.connected:
        return Colors.green.withOpacity(0.1);
      case WebSocketConnectionState.connecting:
      case WebSocketConnectionState.reconnecting:
        return Colors.orange.withOpacity(0.1);
      case WebSocketConnectionState.error:
        return Colors.red.withOpacity(0.1);
      case WebSocketConnectionState.disconnected:
      default:
        return Colors.grey.withOpacity(0.1);
    }
  }

  Color _getBorderColor(BuildContext context) {
    switch (connectionState) {
      case WebSocketConnectionState.connected:
        return Colors.green.withOpacity(0.3);
      case WebSocketConnectionState.connecting:
      case WebSocketConnectionState.reconnecting:
        return Colors.orange.withOpacity(0.3);
      case WebSocketConnectionState.error:
        return Colors.red.withOpacity(0.3);
      case WebSocketConnectionState.disconnected:
      default:
        return Colors.grey.withOpacity(0.3);
    }
  }

  Color _getTextColor(BuildContext context) {
    switch (connectionState) {
      case WebSocketConnectionState.connected:
        return Colors.green.shade700;
      case WebSocketConnectionState.connecting:
      case WebSocketConnectionState.reconnecting:
        return Colors.orange.shade700;
      case WebSocketConnectionState.error:
        return Colors.red.shade700;
      case WebSocketConnectionState.disconnected:
      default:
        return Colors.grey.shade600;
    }
  }
}
