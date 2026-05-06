from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from tools.adb import AdbRunner
from tools.models import ToolResult


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
        completed = runner.run(command)
        executed.append(
            ExecutedCommand(
                argv=command.to_dict()["argv"],
                returncode=completed.returncode,
                stdout=completed.stdout,
                stderr=completed.stderr,
            )
        )
        if completed.returncode != 0:
            exit_code = completed.returncode
            break

    return ExecutionReport(result=result, executed=executed, exit_code=exit_code)
