import unittest

from firebridge.config import AppConfig
from firebridge.discovery import build_discovery_payloads
from firebridge.yaml_endpoints import load_endpoints


class DiscoveryTests(unittest.TestCase):
    def test_builds_home_assistant_discovery_payloads(self):
        config = AppConfig(
            device_id="fire_hd8",
            device_name="Fire HD8",
            mqtt_base_topic="firebridge/fire-hd8",
        )

        payloads = build_discovery_payloads(config)
        by_object_id = {payload.object_id: payload for payload in payloads}

        self.assertIn("display", by_object_id)
        self.assertIn("battery", by_object_id)
        self.assertIn("open_url", by_object_id)
        self.assertEqual(
            by_object_id["display"].topic,
            "homeassistant/switch/fire_hd8/display/config",
        )
        self.assertEqual(
            by_object_id["display"].payload["command_topic"],
            "firebridge/fire-hd8/screen/set",
        )
        self.assertEqual(by_object_id["battery"].payload["device_class"], "battery")

    def test_core_connectivity_sensor_emitted_alongside_yaml_endpoints(self):
        config = AppConfig(
            device_id="fire_hd8",
            mqtt_base_topic="firebridge/fire-hd8",
        )
        endpoints = load_endpoints("config/endpoints")

        payloads = build_discovery_payloads(config, endpoints)
        by_object_id = {payload.object_id: payload for payload in payloads}

        # The connectivity / status sensors must show up even when the user
        # only loads YAML endpoints; otherwise HA loses sight of the device
        # the moment ADB drops.
        self.assertIn("connected", by_object_id)
        self.assertEqual(by_object_id["connected"].component, "binary_sensor")
        self.assertEqual(
            by_object_id["connected"].payload["device_class"], "connectivity"
        )
        self.assertEqual(
            by_object_id["connected"].payload["state_topic"],
            "firebridge/fire-hd8/state",
        )
        self.assertIn("adb_state", by_object_id)
        self.assertIn("battery", by_object_id)

    def test_sensor_command_topic_becomes_separate_button(self):
        config = AppConfig(
            device_id="fire_hd8",
            device_name="Fire HD8",
            mqtt_base_topic="firebridge/fire-hd8",
        )
        endpoints = load_endpoints("examples")

        payloads = build_discovery_payloads(config, endpoints)
        by_object_id = {payload.object_id: payload for payload in payloads}

        sensor = by_object_id["example_battery_sensor"]
        button = by_object_id["example_battery_sensor_read"]

        self.assertEqual(sensor.component, "sensor")
        self.assertIn("state_topic", sensor.payload)
        self.assertNotIn("command_topic", sensor.payload)
        self.assertEqual(button.component, "button")
        self.assertEqual(
            button.payload["command_topic"],
            "firebridge/fire-hd8/examples/battery/read",
        )
        self.assertNotIn("state_topic", button.payload)

        select = by_object_id["example_app_selector"]
        self.assertEqual(select.payload["options"][:3], ["Home Assistant", "Browser", "Settings"])
        self.assertNotIn(
            "io.homeassistant.companion.android.minimal",
            select.payload["options"],
        )

    def test_yaml_discovery_payloads_do_not_mix_invalid_command_and_state_fields(self):
        config = AppConfig(mqtt_base_topic="firebridge/fire-hd8")
        payloads = build_discovery_payloads(config, load_endpoints("examples"))

        for discovery in payloads:
            if discovery.component in {"sensor", "binary_sensor"}:
                self.assertNotIn("command_topic", discovery.payload, discovery.object_id)
            if discovery.component == "button":
                self.assertIn("command_topic", discovery.payload, discovery.object_id)
                self.assertNotIn("state_topic", discovery.payload, discovery.object_id)


if __name__ == "__main__":
    unittest.main()
