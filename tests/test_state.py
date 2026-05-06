import unittest
from types import SimpleNamespace

from firebridge.state import parse_battery, parse_power, read_device_state
from tools.models import ToolContext


class FakeRunner:
    def __init__(self, outputs):
        self.outputs = outputs

    def run(self, command):
        return self.outputs.get(
            tuple(command.argv),
            SimpleNamespace(returncode=1, stdout="", stderr="missing fake output"),
        )


class StateTests(unittest.TestCase):
    def test_parse_battery(self):
        parsed = parse_battery("  level: 83\n  status: 2\n")

        self.assertEqual(parsed["battery_level"], 83)
        self.assertEqual(parsed["battery_status"], "Charging")

    def test_parse_power(self):
        self.assertEqual(parse_power("Display Power: state=ON"), {"screen_on": True})
        self.assertEqual(parse_power("mInteractive=false"), {"screen_on": False})

    def test_read_device_state_uses_adb_outputs(self):
        runner = FakeRunner(
            {
                ("adb", "get-state"): SimpleNamespace(
                    returncode=0,
                    stdout="device\n",
                    stderr="",
                ),
                ("adb", "shell", "getprop", "ro.product.model"): SimpleNamespace(
                    returncode=0,
                    stdout="KFMEWI\n",
                    stderr="",
                ),
                ("adb", "shell", "getprop", "ro.product.device"): SimpleNamespace(
                    returncode=0,
                    stdout="thebes\n",
                    stderr="",
                ),
                (
                    "adb",
                    "shell",
                    "getprop",
                    "ro.build.version.release",
                ): SimpleNamespace(returncode=0, stdout="7.1.2\n", stderr=""),
                ("adb", "shell", "dumpsys", "battery"): SimpleNamespace(
                    returncode=0,
                    stdout="  level: 83\n  status: 2\n",
                    stderr="",
                ),
                ("adb", "shell", "dumpsys", "power"): SimpleNamespace(
                    returncode=0,
                    stdout="Display Power: state=ON\n",
                    stderr="",
                ),
            }
        )

        state = read_device_state(ToolContext(), runner)

        self.assertTrue(state["connected"])
        self.assertEqual(state["model"], "KFMEWI")
        self.assertEqual(state["device"], "thebes")
        self.assertEqual(state["battery_level"], 83)
        self.assertTrue(state["screen_on"])


if __name__ == "__main__":
    unittest.main()
