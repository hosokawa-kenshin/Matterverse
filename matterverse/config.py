"""
Configuration management for Matterverse application.
"""
import os
from typing import Optional
from dotenv import load_dotenv


class Config:
    """Configuration manager for environment variables and settings."""

    def __init__(self, env_file: Optional[str] = None):
        """
        Initialize configuration manager.

        Args:
            env_file: Path to .env file. If None, uses default .env
        """
        if env_file:
            load_dotenv(env_file)
        else:
            load_dotenv()

    @property
    def chip_tool_path(self) -> str:
        """Get chip-tool executable path."""
        return os.getenv('CHIP_TOOL_PATH', './chip-tool')

    @property
    def commissioning_dir(self) -> str:
        """Get commissioning directory path."""
        return os.getenv('COMMISSIONING_DIR', './commissioning_dir')

    @property
    def mqtt_broker_url(self) -> str:
        """Get MQTT broker URL."""
        return os.getenv('MQTT_BROKER_URL', 'localhost')

    @property
    def mqtt_broker_port(self) -> int:
        """Get MQTT broker port."""
        return int(os.getenv('MQTT_BROKER_PORT', '9001'))

    @property
    def cluster_xml_dir(self) -> str:
        """Get cluster XML directory path."""
        return os.getenv('CLUSTER_XML_DIR', '../sdk/src/app/zap-templates/zcl/data-model/chip/')

    @property
    def device_type_xml_file(self) -> str:
        """Get device type XML file path."""
        return os.getenv('DEVICETYPE_XML_FILE', '../sdk/src/app/zap-templates/zcl/data-model/chip/matter-device-types.xml')

    @property
    def paa_cert_dir_path(self) -> str:
        """Get PAA certificate directory path."""
        return os.getenv('PAA_CERT_DIR_PATH', '../sdk/credentials/paa_root_cert')

    @property
    def database_path(self) -> str:
        """Get SQLite database file path."""
        return os.getenv('DATABASE_PATH', './db/matterverse.db')

    @property
    def log_level(self) -> str:
        """Get log level."""
        return os.getenv('LOG_LEVEL', 'INFO')

    @property
    def enable_colored_logs(self) -> bool:
        """Get whether to enable colored logs."""
        return os.getenv('ENABLE_COLORED_LOGS', 'true').lower() == 'true'
