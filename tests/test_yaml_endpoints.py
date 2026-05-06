import tempfile
import unittest
from pathlib import Path

from firebridge.config import AppConfig
from firebridge.yaml_endpoints import load_endpoint_file, load_endpoints


class YamlEndpointTests(unittest.TestCase):
    def test_load_single_endpoint_file(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "sleep.yaml"
            path.write_text(
                """
version: 1
id: sleep
kind: action
name: Sleep
mqtt:
  command_topic: ${base_topic}/sleep/set
steps:
  - adb: shell input keyevent KEYCODE_SLEEP
""".strip(),
                encoding="utf-8",
            )

            endpoints = load_endpoint_file(path)

        self.assertEqual(len(endpoints), 1)
        self.assertEqual(endpoints[0].id, "sleep")
        self.assertEqual(
            endpoints[0].command_topic(AppConfig(mqtt_base_topic="firebridge/test")),
            "firebridge/test/sleep/set",
        )

    def test_load_bundled_example_endpoints(self):
        endpoints = load_endpoints("config/endpoints")
        ids = {endpoint.id for endpoint in endpoints}

        self.assertEqual(ids, {"battery", "brightness", "display", "open_url"})

    def test_load_documentation_examples(self):
        endpoints = load_endpoints("examples")
        ids = {endpoint.id for endpoint in endpoints}

        self.assertIn("example_display_pin", ids)
        self.assertIn("example_immersive_mode", ids)
        self.assertIn("example_app_selector", ids)
        self.assertIn("example_current_app", ids)
        self.assertIn("example_set_fully_device_owner", ids)
        self.assertIn("example_verify_codename", ids)


if __name__ == "__main__":
    unittest.main()
