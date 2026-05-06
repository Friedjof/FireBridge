import os
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from firebridge.config import AppConfig
from firebridge.workflow import WorkflowRunner
from firebridge.yaml_endpoints import load_endpoints


class FakeRunner:
    def __init__(self, stdout: str = ""):
        self.stdout = stdout
        self.commands = []

    def run(self, command):
        self.commands.append(command.argv)
        return SimpleNamespace(returncode=0, stdout=self.stdout, stderr="")


class WorkflowTests(unittest.TestCase):
    def endpoint(self, endpoint_id: str):
        endpoints = load_endpoints("config/endpoints")
        return next(endpoint for endpoint in endpoints if endpoint.id == endpoint_id)

    def example_endpoint(self, endpoint_id: str):
        endpoints = load_endpoints("examples")
        return next(endpoint for endpoint in endpoints if endpoint.id == endpoint_id)

    def test_display_on_dry_run_redacts_pin_and_publishes_state(self):
        config = AppConfig(mqtt_base_topic="firebridge/fire-hd8")
        endpoint = self.endpoint("display")

        with patch.dict(os.environ, {"UNLOCK_PIN": "1234"}):
            result = WorkflowRunner(config, FakeRunner()).run(
                endpoint,
                "ON",
                dry_run=True,
            )

        self.assertEqual(result.return_value, "ON")
        self.assertIn(
            ["adb", "shell", "input", "text", "<redacted>"],
            [command.argv for command in result.commands],
        )
        self.assertEqual(result.variables["pin"], "<redacted>")
        self.assertEqual(result.publishes[0].topic, "firebridge/fire-hd8/display/state")
        self.assertEqual(result.publishes[0].payload, "ON")

    def test_display_discovery_payload_uses_string_payloads(self):
        from firebridge.discovery import build_discovery_payloads

        config = AppConfig(mqtt_base_topic="firebridge/fire-hd8")
        endpoint = self.endpoint("display")

        payload = build_discovery_payloads(config, [endpoint])[0].payload

        self.assertEqual(payload["payload_on"], "ON")
        self.assertEqual(payload["payload_off"], "OFF")

    def test_display_off_branch_uses_sleep_command(self):
        config = AppConfig(mqtt_base_topic="firebridge/fire-hd8")
        endpoint = self.endpoint("display")

        with patch.dict(os.environ, {"UNLOCK_PIN": "1234"}):
            result = WorkflowRunner(config, FakeRunner()).run(
                endpoint,
                "OFF",
                dry_run=True,
            )

        self.assertEqual(result.return_value, "OFF")
        self.assertEqual(
            result.commands[0].argv,
            ["adb", "shell", "input", "keyevent", "KEYCODE_SLEEP"],
        )

    def test_battery_sensor_captures_and_returns_regex_value(self):
        config = AppConfig(mqtt_base_topic="firebridge/fire-hd8")
        endpoint = self.endpoint("battery")
        publishes = []

        runner = WorkflowRunner(
            config,
            FakeRunner(stdout="  level: 83\n  status: 2\n"),
            publisher=lambda topic, payload, retain: publishes.append(
                (topic, payload, retain)
            ),
        )
        result = runner.run(endpoint)

        self.assertEqual(result.return_value, 83)
        self.assertEqual(publishes, [("firebridge/fire-hd8/battery/state", "83", True)])

    def test_app_selector_uses_selected_package(self):
        config = AppConfig(mqtt_base_topic="firebridge/fire-hd8")
        endpoint = self.example_endpoint("example_app_selector")

        result = WorkflowRunner(config, FakeRunner()).run(
            endpoint,
            "Home Assistant",
            dry_run=True,
        )

        self.assertEqual(
            result.commands[0].argv,
            [
                "adb",
                "shell",
                "monkey",
                "-p",
                "io.homeassistant.companion.android.minimal",
                "1",
            ],
        )
        self.assertEqual(result.return_value, "Home Assistant")
        self.assertEqual(
            result.variables["package"],
            "io.homeassistant.companion.android.minimal",
        )
        self.assertEqual(result.variables["package_choice"]["name"], "Home Assistant")
        self.assertEqual(result.publishes[0].payload, "Home Assistant")

        package_result = WorkflowRunner(config, FakeRunner()).run(
            endpoint,
            "com.android.settings",
            dry_run=True,
        )
        self.assertEqual(
            package_result.commands[0].argv,
            ["adb", "shell", "monkey", "-p", "com.android.settings", "1"],
        )
        self.assertEqual(package_result.return_value, "Settings")


if __name__ == "__main__":
    unittest.main()
