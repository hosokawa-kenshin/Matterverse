"""
Logging utilities for Matterverse application.
"""
import logging
from typing import Optional


class ColoredFormatter(logging.Formatter):
    """Custom formatter to add colors to log messages."""
    
    # ANSI color codes
    COLORS = {
        'DEBUG': '\033[0;36m',      # Cyan
        'INFO': '\033[0;32m',       # Green  
        'WARNING': '\033[0;33m',    # Yellow
        'ERROR': '\033[0;31m',      # Red
        'CRITICAL': '\033[1;31m',   # Bold Red
        'RESET': '\033[0m'          # Reset
    }
    
    COMPONENT_COLORS = {
        'CHIP': '\033[1;34m',       # Bold Blue
        'SQL': '\033[1;36m',        # Bold Cyan
        'MQTT': '\033[1;35m',       # Bold Magenta
        'WS': '\033[1;31m',         # Bold Red
        'API': '\033[1;32m',        # Bold Green
        'DEV': '\033[1;33m',        # Bold Yellow
    }
    
    def format(self, record):
        """Format log record with colors."""
        if hasattr(record, 'component'):
            component = record.component
            color = self.COMPONENT_COLORS.get(component, '')
            reset = self.COLORS['RESET']
            record.component = f"{color}{component:<4}{reset}"
        
        log_color = self.COLORS.get(record.levelname, '')
        reset = self.COLORS['RESET']
        
        # Apply color to the entire message
        formatted = super().format(record)
        return f"{log_color}{formatted}{reset}"


class Logger:
    """Centralized logger for Matterverse components."""
    
    _loggers = {}
    _colored_enabled = True
    
    @classmethod
    def setup(cls, level: str = 'INFO', enable_colors: bool = True):
        """
        Setup logging configuration.
        
        Args:
            level: Log level (DEBUG, INFO, WARNING, ERROR, CRITICAL)
            enable_colors: Whether to enable colored output
        """
        cls._colored_enabled = enable_colors
        
        # Configure root logger
        root_logger = logging.getLogger()
        root_logger.setLevel(getattr(logging, level.upper()))
        
        # Remove existing handlers
        for handler in root_logger.handlers[:]:
            root_logger.removeHandler(handler)
        
        # Create console handler
        console_handler = logging.StreamHandler()
        
        if enable_colors:
            formatter = ColoredFormatter(
                '%(component)s:     %(message)s'
            )
        else:
            formatter = logging.Formatter(
                '%(component)s:     %(message)s'
            )
        
        console_handler.setFormatter(formatter)
        root_logger.addHandler(console_handler)
    
    @classmethod
    def get_logger(cls, component: str) -> logging.LoggerAdapter:
        """
        Get logger for specific component.
        
        Args:
            component: Component name (CHIP, SQL, MQTT, etc.)
            
        Returns:
            Logger adapter with component context
        """
        if component not in cls._loggers:
            logger = logging.getLogger(f"matterverse.{component.lower()}")
            adapter = logging.LoggerAdapter(logger, {'component': component})
            cls._loggers[component] = adapter
        
        return cls._loggers[component]


# Convenience functions for getting component loggers
def get_chip_logger():
    """Get logger for CHIP tool operations."""
    return Logger.get_logger('CHIP')

def get_sql_logger():
    """Get logger for database operations.""" 
    return Logger.get_logger('SQL')

def get_mqtt_logger():
    """Get logger for MQTT operations."""
    return Logger.get_logger('MQTT')

def get_ws_logger():
    """Get logger for WebSocket operations."""
    return Logger.get_logger('WS')

def get_api_logger():
    """Get logger for API operations."""
    return Logger.get_logger('API')

def get_device_logger():
    """Get logger for device operations."""
    return Logger.get_logger('DEV')
