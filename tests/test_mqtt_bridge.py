import unittest

from firebridge.config import AppConfig
from firebridge.mqtt_bridge import action_from_message, should_ignore_mqtt_message
from firebridge.yaml_endpoints import load_endpoints


class MqttBridgeTests(unittest.TestCase):
    def test_screen_on_topic_maps_to_pin_unlock_tool(self):
        config = AppConfig(unlock_method="pin", unlock_pin="1234")

        action = action_from_message(config, config.screen_command_topic, "ON")

        self.assertIsNotNone(action)
        self.assertEqual(action.kind, "tool")
        self.assertEqual(action.result.tool, "screen.on")
        self.assertEqual(
            action.result.to_dict()["commands"][2]["argv"],
            ["adb", "shell", "input", "text", "<redacted>"],
        )

    def test_url_topic_accepts_json_payload(self):
        config = AppConfig()

        action = action_from_message(
            config,
            config.url_command_topic,
            '{"url":"https://example.org/dashboard"}',
        )

        self.assertEqual(action.result.tool, "url.open")
        self.assertEqual(action.result.state["url"], "https://example.org/dashboard")

    def test_brightness_topic_maps_to_brightness_tool(self):
        config = AppConfig()

        action = action_from_message(config, config.brightness_command_topic, "120")

        self.assertEqual(action.result.tool, "brightness.set")
        self.assertEqual(action.result.state["brightness"], 120)

    def test_reconnect_topic_maps_to_reconnect_action(self):
        config = AppConfig()

        action = action_from_message(config, config.reconnect_command_topic, "1")

        self.assertEqual(action.kind, "reconnect")
        self.assertIsNone(action.result)

    def test_yaml_endpoint_topic_maps_to_workflow_action(self):
        config = AppConfig(mqtt_base_topic="firebridge/fire-hd8")
        endpoints = load_endpoints("config/endpoints")

        action = action_from_message(
            config,
            "firebridge/fire-hd8/display/set",
            "ON",
            endpoints,
        )

        self.assertEqual(action.kind, "workflow")
        self.assertEqual(action.endpoint.id, "display")
        self.assertEqual(action.payload, "ON")

    def test_retained_command_messages_are_ignored_by_default(self):
        self.assertTrue(should_ignore_mqtt_message(AppConfig(), retained=True))
        self.assertFalse(should_ignore_mqtt_message(AppConfig(), retained=False))

    def test_retained_command_messages_can_be_allowed(self):
        config = AppConfig(mqtt_ignore_retained_commands=False)

        self.assertFalse(should_ignore_mqtt_message(config, retained=True))


if __name__ == "__main__":
    unittest.main()
