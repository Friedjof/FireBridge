from __future__ import annotations

from dataclasses import dataclass, field
from os import environ
from typing import Any


@dataclass(frozen=True)
class ToolContext:
    adb_serial: str = ""
    default_url: str = ""
    browser_package: str = ""
    screen_off_timeout_ms: int = 2_147_483_647
    unlock_method: str = "none"
    unlock_pin: str = ""

    @classmethod
    def from_env(cls) -> "ToolContext":
        adb_target = environ.get("ADB_TARGET", "")
        return cls(
            adb_serial=environ.get("ADB_SERIAL", "") or adb_target,
            default_url=environ.get("DEFAULT_URL", ""),
            browser_package=environ.get("BROWSER_PACKAGE", ""),
            screen_off_timeout_ms=int(
                environ.get("SCREEN_OFF_TIMEOUT_MS", "2147483647")
            ),
            unlock_method=environ.get("UNLOCK_METHOD", "none"),
            unlock_pin=environ.get("UNLOCK_PIN", ""),
        )


@dataclass(frozen=True)
class ToolCommand:
    argv: list[str]
    description: str
    redacted_argv: list[str] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "argv": self.redacted_argv or self.argv,
            "description": self.description,
        }


@dataclass(frozen=True)
class ToolResult:
    tool: str
    description: str
    commands: list[ToolCommand] = field(default_factory=list)
    state: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool": self.tool,
            "description": self.description,
            "commands": [command.to_dict() for command in self.commands],
            "state": self.state,
        }
