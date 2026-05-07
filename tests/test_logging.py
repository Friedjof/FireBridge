import io
import json
import logging
import os
import unittest
from unittest.mock import patch

import firebridge.logging as fb_logging
from firebridge.logging import JsonFormatter, TextFormatter, get_logger, setup_logging


def _capture(level: int, format_name: str, color: str = "never") -> str:
    fb_logging._LOGGING_CONFIGURED = False
    env = {
        "LOG_LEVEL": logging.getLevelName(level),
        "LOG_FORMAT": format_name,
        "LOG_COLOR": color,
    }
    with patch.dict(os.environ, env, clear=False):
        setup_logging()
    buffer = io.StringIO()
    handler = logging.StreamHandler(buffer)
    handler.setFormatter(
        JsonFormatter() if format_name == "json" else TextFormatter(use_color=False)
    )
    root = logging.getLogger()
    for existing in list(root.handlers):
        root.removeHandler(existing)
    root.addHandler(handler)
    try:
        log = get_logger("firebridge.test")
        log.debug("debug-line", extra={"channel": "x"})
        log.info("info-line", extra={"step": 1})
        log.warning("warn-line", extra={"reason": "spaces here"})
    finally:
        root.removeHandler(handler)
    return buffer.getvalue()


class LoggingTests(unittest.TestCase):
    def setUp(self) -> None:
        fb_logging._LOGGING_CONFIGURED = False

    def tearDown(self) -> None:
        fb_logging._LOGGING_CONFIGURED = False

    def test_log_level_filters_out_lower_levels(self):
        output = _capture(logging.INFO, "text")
        self.assertNotIn("debug-line", output)
        self.assertIn("info-line", output)
        self.assertIn("warn-line", output)

    def test_debug_level_emits_debug_records(self):
        output = _capture(logging.DEBUG, "text")
        self.assertIn("debug-line", output)
        self.assertIn("step=1", output)

    def test_text_format_quotes_values_with_spaces(self):
        output = _capture(logging.WARNING, "text")
        self.assertIn('reason="spaces here"', output)

    def test_json_format_emits_one_record_per_line(self):
        output = _capture(logging.INFO, "json")
        lines = [line for line in output.strip().splitlines() if line]
        self.assertTrue(lines, "expected at least one JSON line")
        for line in lines:
            record = json.loads(line)
            self.assertIn("ts", record)
            self.assertIn("level", record)
            self.assertEqual(record["logger"], "firebridge.test")
        info_record = json.loads(lines[0])
        self.assertEqual(info_record["message"], "info-line")
        self.assertEqual(info_record["step"], 1)

    def test_unknown_log_level_falls_back_to_info(self):
        fb_logging._LOGGING_CONFIGURED = False
        with patch.dict(os.environ, {"LOG_LEVEL": "verbose"}, clear=False):
            setup_logging()
        self.assertEqual(logging.getLogger().level, logging.INFO)

    def test_unknown_log_format_falls_back_to_text(self):
        fb_logging._LOGGING_CONFIGURED = False
        with patch.dict(
            os.environ,
            {"LOG_LEVEL": "INFO", "LOG_FORMAT": "yaml", "LOG_COLOR": "never"},
            clear=False,
        ):
            setup_logging()
        handlers = logging.getLogger().handlers
        self.assertTrue(handlers)
        self.assertIsInstance(handlers[0].formatter, TextFormatter)


if __name__ == "__main__":
    unittest.main()
