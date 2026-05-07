from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from tools.adb import AdbRunner
from tools.models import ToolResult

from .logging import get_logger, truncate

log = get_logger("firebridge.executor")


@dataclass(frozen=True)
class ExecutedCommand:
    argv: list[str]
    returncode: int
    stdout: str
    stderr: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "argv": self.argv,
            "returncode": self.returncode,
            "stdout": self.stdout,
            "stderr": self.stderr,
        }


@dataclass(frozen=True)
class ExecutionReport:
    result: ToolResult
    executed: list[ExecutedCommand]
    exit_code: int

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.result.to_dict(),
            "executed": [command.to_dict() for command in self.executed],
        }


def execute_tool_result(result: ToolResult, runner: AdbRunner) -> ExecutionReport:
    executed: list[ExecutedCommand] = []
    exit_code = 0

    for command in result.commands:
        argv = command.to_dict()["argv"]
        started = time.monotonic()
        completed = runner.run(command)
        duration_ms = int((time.monotonic() - started) * 1000)
        executed.append(
            ExecutedCommand(
                argv=argv,
                returncode=completed.returncode,
                stdout=completed.stdout,
                stderr=completed.stderr,
            )
        )
        if completed.returncode != 0:
            exit_code = completed.returncode
            log.warning(
                "Tool command failed",
                extra={
                    "tool": result.tool,
                    "argv": argv,
                    "rc": completed.returncode,
                    "stderr": truncate(completed.stderr.strip(), 300),
                    "duration_ms": duration_ms,
                },
            )
            break
        log.debug(
            "Tool command ok",
            extra={
                "tool": result.tool,
                "argv": argv,
                "duration_ms": duration_ms,
            },
        )

    return ExecutionReport(result=result, executed=executed, exit_code=exit_code)
