import unittest

from tools.brightness import set_brightness
from tools.models import ToolContext
from tools.registry import available_tools, build_tool_result
from tools.screen import screen_off, screen_on
from tools.url import open_url


class ToolTests(unittest.TestCase):
    def test_available_tools_contains_endpoint_actions(self):
        self.assertEqual(
            available_tools(),
            [
                "brightness.set",
                "screen.off",
                "screen.on",
                "screen.toggle",
                "status.read",
                "url.open",
            ],
        )

    def test_screen_on_builds_ordered_adb_plan(self):
        context = ToolContext(default_url="http://homeassistant.local:8123/dashboard")

        result = screen_on(context)

        self.assertEqual(result.tool, "screen.on")
        self.assertEqual(
            [command.argv for command in result.commands],
            [
                ["adb", "shell", "input", "keyevent", "KEYCODE_WAKEUP"],
                [
                    "adb",
                    "shell",
                    "settings",
                    "put",
                    "system",
                    "screen_off_timeout",
                    "2147483647",
                ],
                [
                    "adb",
                    "shell",
                    "am",
                    "start",
                    "-a",
                    "android.intent.action.VIEW",
                    "-d",
                    "http://homeassistant.local:8123/dashboard",
                ],
            ],
        )

    def test_screen_on_can_optionally_swipe_unlock_without_pin(self):
        result = screen_on(ToolContext(unlock_method="swipe"))

        self.assertEqual(
            [command.argv for command in result.commands[:3]],
            [
                ["adb", "shell", "input", "keyevent", "KEYCODE_WAKEUP"],
                ["adb", "shell", "wm", "dismiss-keyguard"],
                ["adb", "shell", "input", "swipe", "400", "700", "400", "200"],
            ],
        )

    def test_screen_on_can_enter_pin_without_exposing_it_in_json(self):
        result = screen_on(ToolContext(unlock_method="pin", unlock_pin="1234"))

        self.assertEqual(
            [command.argv for command in result.commands[:4]],
            [
                ["adb", "shell", "input", "keyevent", "KEYCODE_WAKEUP"],
                ["adb", "shell", "input", "swipe", "400", "700", "400", "200"],
                ["adb", "shell", "input", "text", "1234"],
                ["adb", "shell", "input", "keyevent", "KEYCODE_ENTER"],
            ],
        )
        self.assertEqual(
            result.to_dict()["commands"][2]["argv"],
            ["adb", "shell", "input", "text", "<redacted>"],
        )

    def test_screen_on_rejects_pin_without_pin_value(self):
        with self.assertRaises(ValueError):
            screen_on(ToolContext(unlock_method="pin"))

    def test_screen_off_builds_sleep_command(self):
        result = screen_off(ToolContext(adb_serial="G090"))

        self.assertEqual(
            result.commands[0].argv,
            ["adb", "-s", "G090", "shell", "input", "keyevent", "KEYCODE_SLEEP"],
        )

    def test_open_url_rejects_url_without_scheme(self):
        with self.assertRaises(ValueError):
            open_url(ToolContext(), "homeassistant.local:8123")

    def test_open_url_supports_browser_package(self):
        result = open_url(
            ToolContext(browser_package="org.mozilla.firefox"),
            "https://example.org/dashboard",
        )

        self.assertEqual(
            result.commands[0].argv,
            [
                "adb",
                "shell",
                "am",
                "start",
                "-a",
                "android.intent.action.VIEW",
                "-d",
                "https://example.org/dashboard",
                "-p",
                "org.mozilla.firefox",
            ],
        )

    def test_brightness_value_is_validated(self):
        with self.assertRaises(ValueError):
            set_brightness(ToolContext(), 300)

    def test_registry_builds_url_tool(self):
        result = build_tool_result(
            "url.open",
            ToolContext(),
            url="https://example.org",
        )

        self.assertEqual(result.tool, "url.open")
        self.assertEqual(result.state["url"], "https://example.org")


if __name__ == "__main__":
    unittest.main()
