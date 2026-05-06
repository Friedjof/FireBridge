from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .config import AppConfig
from .workflow_template import render_template


@dataclass(frozen=True)
class ChoiceSpec:
    key: str
    name: str
    value: str

    @classmethod
    def from_raw(cls, raw: Any) -> "ChoiceSpec":
        if isinstance(raw, dict):
            value = raw.get("value", raw.get("key", raw.get("name", "")))
            name = raw.get("name", raw.get("key", value))
            key = raw.get("key", name)
            return cls(key=str(key), name=str(name), value=str(value))

        text = str(raw)
        return cls(key=text, name=text, value=text)


@dataclass(frozen=True)
class InputSpec:
    name: str
    type: str = "text"
    required: bool = False
    from_payload: bool = False
    payload_key: str = ""
    env: str = ""
    default: Any = None
    choices: list[Any] = field(default_factory=list)
    min: float | None = None
    max: float | None = None
    secret: bool = False

    @classmethod
    def from_dict(cls, name: str, data: dict[str, Any]) -> "InputSpec":
        return cls(
            name=name,
            type=str(data.get("type", "text")),
            required=bool(data.get("required", False)),
            from_payload=bool(data.get("from_payload", False)),
            payload_key=str(data.get("payload_key", "")),
            env=str(data.get("env", "")),
            default=data.get("default"),
            choices=list(data.get("choices", [])),
            min=data.get("min"),
            max=data.get("max"),
            secret=bool(data.get("secret", False)),
        )

    def choice_specs(self) -> list[ChoiceSpec]:
        return [ChoiceSpec.from_raw(choice) for choice in self.choices]

    def choice_names(self) -> list[str]:
        return [choice.name for choice in self.choice_specs()]

    def choice_for_payload(self, value: Any) -> ChoiceSpec | None:
        text = str(value)
        choices = self.choice_specs()
        for choice in choices:
            if text == choice.name:
                return choice
        for choice in choices:
            if text == choice.key:
                return choice
        for choice in choices:
            if text == choice.value:
                return choice
        return None


@dataclass(frozen=True)
class ScheduleConfig:
    cron: str = ""
    run_on_start: bool = False
    timezone: str = ""
    payload: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> "ScheduleConfig | None":
        if not data:
            return None
        cron = str(data.get("cron", "")).strip()
        if not cron:
            return None
        return cls(
            cron=cron,
            run_on_start=bool(data.get("run_on_start", False)),
            timezone=str(data.get("timezone", "")).strip(),
            payload=str(data.get("payload", "")),
        )


@dataclass(frozen=True)
class EndpointConfig:
    id: str
    kind: str
    name: str
    mqtt: dict[str, Any]
    ha: dict[str, Any]
    inputs: dict[str, InputSpec]
    steps: list[dict[str, Any]]
    schedule: ScheduleConfig | None = None
    source: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any], source: str = "") -> "EndpointConfig":
        endpoint_id = str(data.get("id", "")).strip()
        if not endpoint_id:
            raise ValueError(f"Endpoint in {source or '<memory>'} is missing id")

        kind = str(data.get("kind", "action")).strip()
        if kind not in {"action", "sensor"}:
            raise ValueError(f"Endpoint {endpoint_id} has unsupported kind: {kind}")

        raw_inputs = data.get("inputs", {}) or {}
        if not isinstance(raw_inputs, dict):
            raise ValueError(f"Endpoint {endpoint_id} inputs must be a mapping")

        steps = data.get("steps", []) or []
        if not isinstance(steps, list):
            raise ValueError(f"Endpoint {endpoint_id} steps must be a list")

        return cls(
            id=endpoint_id,
            kind=kind,
            name=str(data.get("name", endpoint_id)),
            mqtt=dict(data.get("mqtt", {}) or {}),
            ha=dict(data.get("ha", {}) or {}),
            inputs={
                name: InputSpec.from_dict(name, dict(spec or {}))
                for name, spec in raw_inputs.items()
            },
            steps=[dict(step or {}) for step in steps],
            schedule=ScheduleConfig.from_dict(data.get("schedule")),
            source=source,
        )

    def command_topic(self, config: AppConfig) -> str:
        topic = self.mqtt.get("command_topic", "")
        return render_template(str(topic), endpoint_variables(config, self)) if topic else ""

    def state_topic(self, config: AppConfig) -> str:
        topic = self.mqtt.get("state_topic", "")
        return render_template(str(topic), endpoint_variables(config, self)) if topic else ""


def endpoint_variables(config: AppConfig, endpoint: EndpointConfig) -> dict[str, Any]:
    base_variables = {
        "base_topic": config.base_topic,
        "availability_topic": config.availability_topic,
        "device_id": config.device_id,
        "device_name": config.device_name,
    }
    return {
        **base_variables,
        "endpoint": {
            "id": endpoint.id,
            "kind": endpoint.kind,
            "name": endpoint.name,
        },
        "mqtt": {
            "command_topic": render_template(
                str(endpoint.mqtt.get("command_topic", "")),
                base_variables,
            ),
            "state_topic": render_template(
                str(endpoint.mqtt.get("state_topic", "")),
                base_variables,
            ),
        },
    }


def load_endpoint_file(path: Path) -> list[EndpointConfig]:
    raw = yaml.safe_load(path.read_text(encoding="utf-8"))
    if raw is None:
        return []
    if not isinstance(raw, dict):
        raise ValueError(f"Endpoint file {path} must contain a mapping")

    version = raw.get("version")
    if version != 1:
        raise ValueError(f"Endpoint file {path} must use version: 1")

    if "endpoints" in raw:
        endpoints = raw.get("endpoints") or []
        if not isinstance(endpoints, list):
            raise ValueError(f"Endpoint file {path} endpoints must be a list")
        return [EndpointConfig.from_dict(dict(item or {}), str(path)) for item in endpoints]

    data = dict(raw)
    data.pop("version", None)
    return [EndpointConfig.from_dict(data, str(path))]


def load_endpoints(config_dir: str) -> list[EndpointConfig]:
    path = Path(config_dir)
    if not path.exists():
        return []

    files = sorted([*path.rglob("*.yaml"), *path.rglob("*.yml")])
    endpoints: list[EndpointConfig] = []
    seen: set[str] = set()
    for file_path in files:
        for endpoint in load_endpoint_file(file_path):
            if endpoint.id in seen:
                raise ValueError(f"Duplicate endpoint id: {endpoint.id}")
            seen.add(endpoint.id)
            endpoints.append(endpoint)

    return endpoints
