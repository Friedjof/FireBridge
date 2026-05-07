import time
import unittest

from firebridge.config import AppConfig
from firebridge.mqtt_bridge import MqttBridge, action_from_message, should_ignore_mqtt_message
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


class _FakeMqttClient:
    def __init__(self) -> None:
        self.published: list[tuple[str, str, bool]] = []
        self.unsubscribed: list[str] = []

    def publish(self, topic: str, payload: str = "", retain: bool = False) -> None:
        self.published.append((topic, payload, retain))

    def unsubscribe(self, topic: str) -> None:
        self.unsubscribed.append(topic)


class DiscoveryReconciliationTests(unittest.TestCase):
    def _bridge(self) -> MqttBridge:
        config = AppConfig(
            device_id="fire_hd8",
            mqtt_discovery_prefix="homeassistant",
            mqtt_discovery_cleanup=True,
            mqtt_discovery_cleanup_delay=0.0,
        )
        return MqttBridge(config)

    def test_owned_discovery_topic_recognises_device_scope(self):
        bridge = self._bridge()

        self.assertTrue(
            bridge._is_owned_discovery_topic(
                "homeassistant/switch/fire_hd8/display/config"
            )
        )
        # different device must not match
        self.assertFalse(
            bridge._is_owned_discovery_topic(
                "homeassistant/switch/other_device/display/config"
            )
        )
        # not a discovery config topic
        self.assertFalse(
            bridge._is_owned_discovery_topic("firebridge/tablet/display/state")
        )

    def test_discovery_wildcard_targets_only_this_device(self):
        bridge = self._bridge()

        self.assertEqual(
            bridge._discovery_wildcard(),
            "homeassistant/+/fire_hd8/+/config",
        )

    def test_reconcile_publishes_empty_payload_for_stale_topics(self):
        bridge = self._bridge()
        bridge._discovery_current = {
            "homeassistant/switch/fire_hd8/display/config",
            "homeassistant/button/fire_hd8/reconnect_adb/config",
        }
        bridge._discovery_observed = {
            "homeassistant/switch/fire_hd8/display/config",  # current
            "homeassistant/sensor/fire_hd8/old_battery/config",  # stale
            "homeassistant/select/fire_hd8/old_app_selector/config",  # stale
        }
        bridge._discovery_reconciled = False
        bridge._discovery_reconcile_at = time.monotonic() - 1.0
        client = _FakeMqttClient()

        bridge._maybe_reconcile_discovery(client)

        topics = sorted(topic for topic, _, _ in client.published)
        self.assertEqual(
            topics,
            [
                "homeassistant/select/fire_hd8/old_app_selector/config",
                "homeassistant/sensor/fire_hd8/old_battery/config",
            ],
        )
        for _, payload, retain in client.published:
            self.assertEqual(payload, "")
            self.assertTrue(retain)
        self.assertEqual(
            client.unsubscribed,
            ["homeassistant/+/fire_hd8/+/config"],
        )
        self.assertTrue(bridge._discovery_reconciled)

    def test_reconcile_skips_when_no_stale_topics(self):
        bridge = self._bridge()
        bridge._discovery_current = {"homeassistant/switch/fire_hd8/display/config"}
        bridge._discovery_observed = {"homeassistant/switch/fire_hd8/display/config"}
        bridge._discovery_reconciled = False
        bridge._discovery_reconcile_at = time.monotonic() - 1.0
        client = _FakeMqttClient()

        bridge._maybe_reconcile_discovery(client)

        self.assertEqual(client.published, [])
        self.assertEqual(
            client.unsubscribed,
            ["homeassistant/+/fire_hd8/+/config"],
        )
        self.assertTrue(bridge._discovery_reconciled)

    def test_reconcile_waits_until_delay_has_elapsed(self):
        bridge = self._bridge()
        bridge._discovery_current = set()
        bridge._discovery_observed = {"homeassistant/switch/fire_hd8/old/config"}
        bridge._discovery_reconciled = False
        bridge._discovery_reconcile_at = time.monotonic() + 60.0
        client = _FakeMqttClient()

        bridge._maybe_reconcile_discovery(client)

        self.assertEqual(client.published, [])
        self.assertEqual(client.unsubscribed, [])
        self.assertFalse(bridge._discovery_reconciled)


if __name__ == "__main__":
    unittest.main()
