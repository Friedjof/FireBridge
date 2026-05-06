import unittest
from datetime import datetime
from zoneinfo import ZoneInfo

from firebridge.cron import parse_cron_expression


class CronTests(unittest.TestCase):
    def test_next_after_supports_steps(self):
        cron = parse_cron_expression("*/5 * * * *")
        current = datetime(2026, 5, 6, 10, 1, tzinfo=ZoneInfo("UTC"))

        self.assertEqual(
            cron.next_after(current),
            datetime(2026, 5, 6, 10, 5, tzinfo=ZoneInfo("UTC")),
        )

    def test_rejects_non_five_field_cron(self):
        with self.assertRaises(ValueError):
            parse_cron_expression("*/10 * * * * *")

    def test_supports_lists_and_ranges(self):
        cron = parse_cron_expression("0 8-10,12 * * 1-5")

        self.assertTrue(cron.matches(datetime(2026, 5, 6, 8, 0)))
        self.assertFalse(cron.matches(datetime(2026, 5, 6, 11, 0)))


if __name__ == "__main__":
    unittest.main()
