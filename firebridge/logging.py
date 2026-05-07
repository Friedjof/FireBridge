from __future__ import annotations

import json
import logging
import os
import sys
import time
from typing import Any

VALID_LEVELS = {"DEBUG", "INFO", "WARNING", "WARN", "ERROR", "CRITICAL"}

_RESERVED_RECORD_KEYS = {
    "name",
    "msg",
    "args",
    "levelname",
    "levelno",
    "pathname",
    "filename",
    "module",
    "exc_info",
    "exc_text",
    "stack_info",
    "lineno",
    "funcName",
    "created",
    "msecs",
    "relativeCreated",
    "thread",
    "threadName",
    "processName",
    "process",
    "message",
    "taskName",
}

_ANSI_RESET = "\033[0m"
_ANSI_DIM = "\033[2m"
_ANSI_BOLD = "\033[1m"
_LEVEL_COLORS = {
    logging.DEBUG: "\033[2;37m",       # dim grey
    logging.INFO: "\033[36m",          # cyan
    logging.WARNING: "\033[33m",       # yellow
    logging.ERROR: "\033[31m",         # red
    logging.CRITICAL: "\033[1;41;97m",  # white on red, bold
}

_LOGGING_CONFIGURED = False


def _quote_value(value: Any) -> str:
    text = str(value)
    if text == "" or any(ch in text for ch in (" ", "\t", "=", '"')):
        escaped = text.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    return text


def _record_extras(record: logging.LogRecord) -> dict[str, Any]:
    return {
        key: value
        for key, value in record.__dict__.items()
        if key not in _RESERVED_RECORD_KEYS and not key.startswith("_")
    }


class TextFormatter(logging.Formatter):
    def __init__(self, use_color: bool) -> None:
        super().__init__()
        self.use_color = use_color

    def format(self, record: logging.LogRecord) -> str:
        local = time.localtime(record.created)
        timestamp = f"{time.strftime('%Y-%m-%d %H:%M:%S', local)}.{int(record.msecs):03d}"
        level = record.levelname.ljust(8)
        name = record.name
        message = record.getMessage()

        extras = _record_extras(record)
        extra_text = ""
        if extras:
            extra_text = " " + " ".join(
                f"{key}={_quote_value(value)}" for key, value in extras.items()
            )

        if self.use_color:
            color = _LEVEL_COLORS.get(record.levelno, "")
            line = (
                f"{_ANSI_DIM}{timestamp}{_ANSI_RESET} "
                f"{color}{level}{_ANSI_RESET} "
                f"{_ANSI_BOLD}{name}{_ANSI_RESET} "
                f"{message}"
                f"{_ANSI_DIM}{extra_text}{_ANSI_RESET}"
            )
        else:
            line = f"{timestamp} {level} {name} {message}{extra_text}"

        if record.exc_info:
            line += "\n" + self.formatException(record.exc_info)
        return line


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        utc = time.gmtime(record.created)
        timestamp = f"{time.strftime('%Y-%m-%dT%H:%M:%S', utc)}.{int(record.msecs):03d}Z"
        payload: dict[str, Any] = {
            "ts": timestamp,
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        for key, value in _record_extras(record).items():
            payload[key] = value
        if record.exc_info:
            payload["exc_info"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str, sort_keys=True)


def _resolve_level(name: str) -> int:
    candidate = name.strip().upper()
    if candidate == "WARN":
        candidate = "WARNING"
    if candidate not in VALID_LEVELS:
        return logging.INFO
    return getattr(logging, candidate)


def _resolve_color(setting: str, format_name: str) -> bool:
    value = setting.strip().lower()
    if value in {"always", "force", "true", "1", "on", "yes"}:
        return True
    if value in {"never", "off", "false", "0", "no"}:
        return False
    if format_name != "text":
        return False
    return sys.stderr.isatty()


def setup_logging() -> None:
    global _LOGGING_CONFIGURED
    if _LOGGING_CONFIGURED:
        return

    level = _resolve_level(os.environ.get("LOG_LEVEL", "INFO"))
    format_name = os.environ.get("LOG_FORMAT", "text").strip().lower()
    if format_name not in {"text", "json"}:
        format_name = "text"
    use_color = _resolve_color(os.environ.get("LOG_COLOR", "auto"), format_name)

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(
        JsonFormatter() if format_name == "json" else TextFormatter(use_color=use_color)
    )

    root = logging.getLogger()
    for existing in list(root.handlers):
        root.removeHandler(existing)
    root.addHandler(handler)
    root.setLevel(level)

    # Tame chatty third-party loggers; raise to DEBUG only when explicitly asked.
    for noisy in ("paho", "paho.mqtt", "urllib3"):
        logging.getLogger(noisy).setLevel(max(level, logging.INFO))

    _LOGGING_CONFIGURED = True


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)


def truncate(value: Any, limit: int = 200) -> str:
    text = str(value)
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"
