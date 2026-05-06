import unittest
from datetime import datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from firebridge.config import AppConfig
from firebridge.scheduler import WorkflowScheduler
from firebridge.yaml_endpoints import load_endpoints


class FakeRunner:
    def __init__(self, stdout: str = ""):
        self.stdout = stdout
        self.commands = []

    def run(self, command):
        self.commands.append(command.argv)
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


if __name__ == "__main__":
    unittest.main()
