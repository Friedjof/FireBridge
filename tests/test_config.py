import os
import unittest
from unittest.mock import patch

from firebridge.config import AppConfig


class ConfigTests(unittest.TestCase):
    def test_config_reads_environment(self):
        with patch.dict(
            os.environ,
            {
                "ADB_TARGET": "192.168.1.50:5555",
                "MQTT_HOST": "mqtt.local",
                "MQTT_PORT": "1884",
                "MQTT_BASE_TOPIC": "firebridge/fire-hd8/",
                "MQTT_IGNORE_RETAINED_COMMANDS": "false",
                "TZ": "Europe/Berlin",
                "DEVICE_ID": "fire_hd8",
                "UNLOCK_METHOD": "pin",
                "UNLOCK_PIN": "1234",
            },
            clear=True,
        ):
            config = AppConfig.from_env()

        self.assertEqual(config.adb_target, "192.168.1.50:5555")
        self.assertEqual(config.mqtt_host, "mqtt.local")
        self.assertEqual(config.mqtt_port, 1884)
        self.assertFalse(config.mqtt_ignore_retained_commands)
        self.assertEqual(config.timezone, "Europe/Berlin")
        self.assertEqual(config.base_topic, "firebridge/fire-hd8")
        self.assertEqual(config.screen_command_topic, "firebridge/fire-hd8/screen/set")
        self.assertEqual(config.tool_context().adb_serial, "192.168.1.50:5555")
        self.assertEqual(config.tool_context().unlock_pin, "1234")

    def test_retained_commands_are_ignored_by_default(self):
        with patch.dict(os.environ, {}, clear=True):
            config = AppConfig.from_env()

        self.assertTrue(config.mqtt_ignore_retained_commands)


if __name__ == "__main__":
    unittest.main()
