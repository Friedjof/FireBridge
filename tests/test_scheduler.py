import unittest
from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from firebridge.config import AppConfig
from firebridge.scheduler import WorkflowScheduler
from firebridge.yaml_endpoints import load_endpoints


class FakeRunner:
    def __init__(self, stdout: str = "", connected: bool = True):
        self.stdout = stdout
        self.connected = connected
        self.commands = []

    def run(self, command):
        self.commands.append(command.argv)
        if "get-state" in command.argv:
            if not self.connected:
                return SimpleNamespace(returncode=1, stdout="", stderr="error: no devices/emulators found")
            return SimpleNamespace(returncode=0, stdout="device\n", stderr="")
        return SimpleNamespace(returncode=0, stdout=self.stdout, stderr="")


class SchedulerTests(unittest.TestCase):
    def test_battery_example_has_cron_schedule(self):
        endpoint = next(
            endpoint
            for endpoint in load_endpoints("examples")
            if endpoint.id == "example_battery_sensor"
        )

        self.assertEqual(endpoint.schedule.cron, "* * * * *")
        self.assertTrue(endpoint.schedule.run_on_start)
        self.assertEqual(endpoint.schedule.payload, "READ")

    def test_run_on_start_executes_scheduled_endpoint_once(self):
        endpoint = next(
            endpoint
            for endpoint in load_endpoints("examples")
            if endpoint.id == "example_battery_sensor"
        )
        publishes = []
        now = datetime(2026, 5, 6, 10, 0, tzinfo=ZoneInfo("UTC"))
        scheduler = WorkflowScheduler(
            AppConfig(mqtt_base_topic="firebridge/fire-hd8", timezone="UTC"),
            [endpoint],
            FakeRunner(stdout="  level: 83\n"),
            publisher=lambda topic, payload, retain: publishes.append(
                (topic, payload, retain)
            ),
            now=lambda: now,
        )

        first_results = scheduler.run_due()
        second_results = scheduler.run_due()

        self.assertEqual(len(first_results), 1)
        self.assertEqual(first_results[0].return_value, 83)
        self.assertEqual(second_results, [])
        self.assertIn(("firebridge/fire-hd8/examples/battery/state", "83", True), publishes)

    def test_disconnected_run_skips_scheduled_workflow_without_publishing(self):
        endpoint = next(
            endpoint
            for endpoint in load_endpoints("examples")
            if endpoint.id == "example_battery_sensor"
        )
        publishes = []
        now = datetime(2026, 5, 6, 10, 0, tzinfo=ZoneInfo("UTC"))
        runner = FakeRunner(stdout="  level: 83\n", connected=False)
        scheduler = WorkflowScheduler(
            AppConfig(mqtt_base_topic="firebridge/fire-hd8", timezone="UTC"),
            [endpoint],
            runner,
            publisher=lambda topic, payload, retain: publishes.append(
                (topic, payload, retain)
            ),
            now=lambda: now,
        )

        results = scheduler.run_due()

        # Skipped run produces no caller-visible result and no publishes.
        self.assertEqual(results, [])
        self.assertEqual(publishes, [])
        # Only the connectivity probe ran, the dumpsys call was suppressed.
        argvs = [argv for argv in runner.commands]
        self.assertEqual(argvs, [["adb", "get-state"]])


if __name__ == "__main__":
    unittest.main()
