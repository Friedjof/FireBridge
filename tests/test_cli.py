import json
import os
import subprocess
import sys
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class CliTests(unittest.TestCase):
    def run_cli(
        self,
        *args: str,
        env: dict[str, str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        process_env = os.environ.copy()
        if env:
            process_env.update(env)
        return subprocess.run(
            [sys.executable, "main.py", *args],
            cwd=PROJECT_ROOT,
            check=False,
            text=True,
            capture_output=True,
            env=process_env,
        )

    def test_tools_list_outputs_tool_names(self):
        result = self.run_cli("tools", "list")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("screen.on", result.stdout)
        self.assertIn("url.open", result.stdout)

    def test_dry_run_outputs_json_plan(self):
        result = self.run_cli("tools", "run", "screen.off", "--dry-run")

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)

        self.assertEqual(payload["tool"], "screen.off")
        self.assertEqual(
            payload["commands"][0]["argv"],
            ["adb", "shell", "input", "keyevent", "KEYCODE_SLEEP"],
        )

    def test_url_tool_requires_url(self):
        result = self.run_cli("tools", "run", "url.open", "--dry-run")

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("url.open requires --url", result.stderr)

    def test_pin_dry_run_redacts_pin(self):
        result = self.run_cli(
            "tools",
            "run",
            "screen.on",
            "--dry-run",
            env={"UNLOCK_METHOD": "pin", "UNLOCK_PIN": "1234"},
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("<redacted>", result.stdout)
        self.assertNotIn("1234", result.stdout)

    def test_serve_dry_run_discovery_outputs_json(self):
        result = self.run_cli("serve", "--dry-run-discovery")

        self.assertEqual(result.returncode, 0, result.stderr)
        payload = json.loads(result.stdout)
        objects = {(item["component"], item["object_id"]) for item in payload}
        self.assertIn(("switch", "display"), objects)
        self.assertIn(("sensor", "battery"), objects)

    def test_workflows_list_outputs_yaml_endpoints(self):
        result = self.run_cli("workflows", "list")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("display\taction\tfirebridge/tablet/display/set", result.stdout)

    def test_workflows_run_dry_run_redacts_pin(self):
        result = self.run_cli(
            "workflows",
            "run",
            "display",
            "--payload",
            "ON",
            "--dry-run",
            env={"UNLOCK_PIN": "1234"},
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("<redacted>", result.stdout)
        self.assertNotIn("1234", result.stdout)


if __name__ == "__main__":
    unittest.main()
