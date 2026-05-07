from __future__ import annotations

import logging
import subprocess

from .models import ToolCommand, ToolContext

log = logging.getLogger("firebridge.adb")


def adb_command(
    context: ToolContext,
    *args: str,
    description: str,
    redacted_args: tuple[str, ...] | None = None,
) -> ToolCommand:
    argv = ["adb"]
    redacted_argv = ["adb"] if redacted_args else None
    if context.adb_serial:
        argv.extend(["-s", context.adb_serial])
        if redacted_argv is not None:
            redacted_argv.extend(["-s", context.adb_serial])
    argv.extend(args)
    if redacted_argv is not None:
        redacted_argv.extend(redacted_args)
    return ToolCommand(argv=argv, description=description, redacted_argv=redacted_argv)


def adb_shell(
    context: ToolContext,
    *args: str,
    description: str,
    redacted_args: tuple[str, ...] | None = None,
) -> ToolCommand:
    redacted_shell_args = ("shell", *redacted_args) if redacted_args else None
    return adb_command(
        context,
        "shell",
        *args,
        description=description,
        redacted_args=redacted_shell_args,
    )


class AdbRunner:
    def __init__(self, timeout: int = 10) -> None:
        self.timeout = timeout

    def connect(self, target: str) -> subprocess.CompletedProcess[str]:
        log.debug("adb connect", extra={"target": target, "timeout": self.timeout})
        return subprocess.run(
            ["adb", "connect", target],
            check=False,
            text=True,
            capture_output=True,
            timeout=self.timeout,
        )

    def run(self, command: ToolCommand) -> subprocess.CompletedProcess[str]:
        argv = command.argv
        log.log(
            5,  # below DEBUG: only visible if explicitly enabled
            "adb run",
            extra={"argv": argv, "description": command.description},
        )
        return subprocess.run(
            argv,
            check=False,
            text=True,
            capture_output=True,
            timeout=self.timeout,
        )
