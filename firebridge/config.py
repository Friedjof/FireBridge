from __future__ import annotations

from dataclasses import dataclass
from os import environ

from tools.models import ToolContext


def _bool_from_env(name: str, default: bool) -> bool:
    value = environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class AppConfig:
    adb_target: str = ""
    adb_serial: str = ""
    adb_connect_on_start: bool = True
    adb_command_timeout: int = 10

    mqtt_host: str = ""
    mqtt_port: int = 1883
    mqtt_username: str = ""
    mqtt_password: str = ""
    mqtt_client_id: str = "firebridge"
    mqtt_base_topic: str = "firebridge/tablet"
    mqtt_discovery_enabled: bool = True
    mqtt_discovery_prefix: str = "homeassistant"
    mqtt_state_interval: int = 30
    mqtt_ignore_retained_commands: bool = True

    config_dir: str = "config/endpoints"
    timezone: str = "UTC"

    device_id: str = "firebridge_tablet"
    device_name: str = "FireBridge Tablet"
    default_url: str = ""
    browser_package: str = ""
    screen_off_timeout_ms: int = 2_147_483_647
    unlock_method: str = "none"
    unlock_pin: str = ""

    @classmethod
    def from_env(cls) -> "AppConfig":
        return cls(
            adb_target=environ.get("ADB_TARGET", ""),
            adb_serial=environ.get("ADB_SERIAL", ""),
            adb_connect_on_start=_bool_from_env("ADB_CONNECT_ON_START", True),
            adb_command_timeout=int(environ.get("ADB_COMMAND_TIMEOUT", "10")),
            mqtt_host=environ.get("MQTT_HOST", ""),
            mqtt_port=int(environ.get("MQTT_PORT", "1883")),
            mqtt_username=environ.get("MQTT_USERNAME", ""),
            mqtt_password=environ.get("MQTT_PASSWORD", ""),
            mqtt_client_id=environ.get("MQTT_CLIENT_ID", "firebridge"),
            mqtt_base_topic=environ.get("MQTT_BASE_TOPIC", "firebridge/tablet"),
            mqtt_discovery_enabled=_bool_from_env("MQTT_DISCOVERY_ENABLED", True),
            mqtt_discovery_prefix=environ.get("MQTT_DISCOVERY_PREFIX", "homeassistant"),
            mqtt_state_interval=int(environ.get("MQTT_STATE_INTERVAL", "30")),
            mqtt_ignore_retained_commands=_bool_from_env(
                "MQTT_IGNORE_RETAINED_COMMANDS",
                True,
            ),
            config_dir=environ.get("CONFIG_DIR", "config/endpoints"),
            timezone=environ.get("TZ", "UTC"),
            device_id=environ.get("DEVICE_ID", "firebridge_tablet"),
            device_name=environ.get("DEVICE_NAME", "FireBridge Tablet"),
            default_url=environ.get("DEFAULT_URL", ""),
            browser_package=environ.get("BROWSER_PACKAGE", ""),
            screen_off_timeout_ms=int(
                environ.get("SCREEN_OFF_TIMEOUT_MS", "2147483647")
            ),
            unlock_method=environ.get("UNLOCK_METHOD", "none"),
            unlock_pin=environ.get("UNLOCK_PIN", ""),
        )

    @property
    def base_topic(self) -> str:
        return self.mqtt_base_topic.strip("/")

    @property
    def availability_topic(self) -> str:
        return f"{self.base_topic}/availability"

    @property
    def state_topic(self) -> str:
        return f"{self.base_topic}/state"

    @property
    def screen_state_topic(self) -> str:
        return f"{self.base_topic}/screen/state"

    @property
    def screen_command_topic(self) -> str:
        return f"{self.base_topic}/screen/set"

    @property
    def url_command_topic(self) -> str:
        return f"{self.base_topic}/url/set"

    @property
    def default_url_command_topic(self) -> str:
        return f"{self.base_topic}/default_url/open"

    @property
    def brightness_state_topic(self) -> str:
        return f"{self.base_topic}/brightness/state"

    @property
    def brightness_command_topic(self) -> str:
        return f"{self.base_topic}/brightness/set"

    @property
    def reconnect_command_topic(self) -> str:
        return f"{self.base_topic}/command/reconnect"

    def tool_context(self) -> ToolContext:
        return ToolContext(
            adb_serial=self.adb_serial or self.adb_target,
            default_url=self.default_url,
            browser_package=self.browser_package,
            screen_off_timeout_ms=self.screen_off_timeout_ms,
            unlock_method=self.unlock_method,
            unlock_pin=self.unlock_pin,
        )
