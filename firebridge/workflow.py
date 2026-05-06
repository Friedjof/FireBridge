from __future__ import annotations

import re
import shlex
import time
from dataclasses import dataclass, field
from typing import Any, Callable

from tools.adb import AdbRunner, adb_command
from tools.models import ToolCommand, ToolContext

from .config import AppConfig
from .workflow_inputs import resolve_inputs
from .workflow_template import render_nested, render_template, resolve_variable
from .yaml_endpoints import EndpointConfig, endpoint_variables


Publisher = Callable[[str, str, bool], None]
Sleeper = Callable[[float], None]


class WorkflowError(RuntimeError):
    pass


@dataclass
class WorkflowCommandReport:
    argv: list[str]
    description: str
    returncode: int | None = None
    stdout: str = ""
    stderr: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "argv": self.argv,
            "description": self.description,
            "returncode": self.returncode,
            "stdout": self.stdout,
            "stderr": self.stderr,
        }


@dataclass
class WorkflowPublishReport:
    topic: str
    payload: str
    retain: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {"topic": self.topic, "payload": self.payload, "retain": self.retain}


@dataclass
class WorkflowResult:
    endpoint_id: str
    kind: str
    status: str = "ok"
    return_value: Any = None
    variables: dict[str, Any] = field(default_factory=dict)
    commands: list[WorkflowCommandReport] = field(default_factory=list)
    publishes: list[WorkflowPublishReport] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "endpoint_id": self.endpoint_id,
            "kind": self.kind,
            "status": self.status,
            "return_value": self.return_value,
            "variables": self.variables,
            "commands": [command.to_dict() for command in self.commands],
            "publishes": [publish.to_dict() for publish in self.publishes],
        }


class WorkflowRunner:
    def __init__(
        self,
        config: AppConfig,
        runner: AdbRunner,
        publisher: Publisher | None = None,
        sleeper: Sleeper = time.sleep,
    ) -> None:
        self.config = config
        self.runner = runner
        self.publisher = publisher
        self.sleeper = sleeper

    def run(
        self,
        endpoint: EndpointConfig,
        payload: str = "",
        dry_run: bool = False,
    ) -> WorkflowResult:
        input_variables, secrets = resolve_inputs(endpoint, payload)
        variables = {
            **endpoint_variables(self.config, endpoint),
            **input_variables,
        }
        result = WorkflowResult(endpoint_id=endpoint.id, kind=endpoint.kind)
        steps = endpoint.steps
        labels = {
            str(step["id"]): index
            for index, step in enumerate(steps)
            if isinstance(step, dict) and "id" in step
        }

        index = 0
        executed_steps = 0
        while index < len(steps):
            if executed_steps >= 200:
                raise WorkflowError(f"Endpoint {endpoint.id} exceeded maximum step count")
            executed_steps += 1

            step = steps[index]
            next_label = self._execute_step(endpoint, step, variables, secrets, result, dry_run)
            if result.status == "returned":
                result.status = "ok"
                break

            if next_label:
                if next_label not in labels:
                    raise WorkflowError(f"Unknown step label: {next_label}")
                index = labels[next_label]
                continue

            index += 1

        result.variables = self._redacted_variables(variables, secrets)
        return result

    def _execute_step(
        self,
        endpoint: EndpointConfig,
        step: dict[str, Any],
        variables: dict[str, Any],
        secrets: set[str],
        result: WorkflowResult,
        dry_run: bool,
    ) -> str | None:
        if "if" in step:
            return self._execute_if(step["if"], variables, secrets)
        if "jump" in step:
            return str(render_template(step["jump"], variables, secrets))
        if "sleep" in step:
            milliseconds = float(render_template(step["sleep"], variables, secrets))
            if not dry_run:
                self.sleeper(milliseconds / 1000)
            return step.get("next")
        if "set" in step:
            self._execute_set(step["set"], variables, secrets)
            return step.get("next")
        if "adb" in step:
            self._execute_adb(endpoint, step, variables, secrets, result, dry_run)
            return step.get("next")
        if "publish" in step:
            self._execute_publish(step["publish"], variables, secrets, result, dry_run)
            return step.get("next")
        if "return" in step:
            result.return_value = render_template(step["return"], variables, secrets)
            result.status = "returned"
            return None
        if "fail" in step:
            message = render_template(step["fail"], variables, secrets)
            raise WorkflowError(str(message))
        return step.get("next")

    def _execute_adb(
        self,
        endpoint: EndpointConfig,
        step: dict[str, Any],
        variables: dict[str, Any],
        secrets: set[str],
        result: WorkflowResult,
        dry_run: bool,
    ) -> None:
        args = self._adb_args(step["adb"], variables, secrets, redacted=False)
        redacted_args = self._adb_args(step["adb"], variables, secrets, redacted=True)
        context = self.config.tool_context()
        command = adb_command(
            context,
            *args,
            description=str(step.get("description", f"Run {endpoint.id} ADB step")),
            redacted_args=tuple(redacted_args) if redacted_args != args else None,
        )
        report = WorkflowCommandReport(
            argv=command.to_dict()["argv"],
            description=command.description,
        )

        if not dry_run:
            completed = self.runner.run(command)
            report.returncode = completed.returncode
            report.stdout = completed.stdout
            report.stderr = completed.stderr
            if completed.returncode != 0:
                result.commands.append(report)
                raise WorkflowError(
                    f"ADB step failed in {endpoint.id}: {completed.stderr.strip()}"
                )
            if capture := step.get("capture"):
                variables[str(capture)] = completed.stdout
        result.commands.append(report)

    def _adb_args(
        self,
        spec: Any,
        variables: dict[str, Any],
        secrets: set[str],
        redacted: bool,
    ) -> list[str]:
        rendered = render_nested(spec, variables, secrets if redacted else set())
        if isinstance(rendered, str):
            return shlex.split(rendered)
        if isinstance(rendered, dict) and "args" in rendered:
            return [str(item) for item in rendered["args"]]
        if isinstance(rendered, list):
            return [str(item) for item in rendered]
        raise WorkflowError("adb step must be a string, list, or mapping with args")

    def _execute_set(
        self,
        assignments: dict[str, Any],
        variables: dict[str, Any],
        secrets: set[str],
    ) -> None:
        for name, value in assignments.items():
            if isinstance(value, dict) and "regex" in value:
                variables[name] = self._regex_value(value["regex"], variables, secrets)
            else:
                variables[name] = render_nested(value, variables, secrets)

    def _regex_value(
        self,
        spec: dict[str, Any],
        variables: dict[str, Any],
        secrets: set[str],
    ) -> Any:
        source_spec = spec.get("source", "")
        if isinstance(source_spec, str) and "${" not in source_spec:
            source = variables.get(source_spec, "")
        else:
            source = render_template(source_spec, variables, secrets)
        match = re.search(str(spec["pattern"]), str(source), re.MULTILINE)
        if not match:
            if "default" in spec:
                return spec["default"]
            raise WorkflowError(f"Regex did not match: {spec['pattern']}")
        value = match.group(int(spec.get("group", 1)))
        value_type = spec.get("type", "text")
        if value_type == "int":
            return int(value)
        if value_type == "float":
            return float(value)
        return value

    def _execute_if(
        self,
        spec: dict[str, Any],
        variables: dict[str, Any],
        secrets: set[str],
    ) -> str | None:
        if "equals" in spec:
            condition = spec["equals"]
            matched = render_template(condition["left"], variables, secrets) == render_template(
                condition["right"], variables, secrets
            )
        elif "exists" in spec:
            value = spec["exists"]
            if isinstance(value, str) and value.startswith("${") and value.endswith("}"):
                value = render_template(value, variables, secrets)
            elif isinstance(value, str):
                value = variables.get(value)
            matched = bool(value)
        elif "matches" in spec:
            condition = spec["matches"]
            value = render_template(condition["value"], variables, secrets)
            matched = re.search(str(condition["pattern"]), str(value)) is not None
        else:
            raise WorkflowError("if step requires equals, exists, or matches")

        target = spec.get("then") if matched else spec.get("else")
        return str(render_template(target, variables, secrets)) if target else None

    def _execute_publish(
        self,
        spec: dict[str, Any],
        variables: dict[str, Any],
        secrets: set[str],
        result: WorkflowResult,
        dry_run: bool,
    ) -> None:
        topic = str(render_template(spec["topic"], variables, secrets))
        payload = str(render_template(spec.get("payload", ""), variables, secrets))
        retain = bool(spec.get("retain", True))
        result.publishes.append(WorkflowPublishReport(topic=topic, payload=payload, retain=retain))
        if self.publisher and not dry_run:
            self.publisher(topic, payload, retain)

    def _redacted_variables(
        self,
        variables: dict[str, Any],
        secrets: set[str],
    ) -> dict[str, Any]:
        return {
            key: "<redacted>" if key in secrets else value
            for key, value in variables.items()
            if key not in {"endpoint", "mqtt"}
        }
