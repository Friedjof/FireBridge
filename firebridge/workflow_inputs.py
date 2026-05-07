from __future__ import annotations

import json
from os import environ
from typing import Any

from .yaml_endpoints import EndpointConfig, InputSpec


_DAY_TOKENS = {
    # English short
    "sun": 1, "mon": 2, "tue": 3, "wed": 4, "thu": 5, "fri": 6, "sat": 7,
    # English long
    "sunday": 1, "monday": 2, "tuesday": 3, "wednesday": 4,
    "thursday": 5, "friday": 6, "saturday": 7,
    # German short
    "so": 1, "mo": 2, "di": 3, "mi": 4, "do": 5, "fr": 6, "sa": 7,
}

_DAY_GROUPS = {
    "daily": [1, 2, 3, 4, 5, 6, 7],
    "all": [1, 2, 3, 4, 5, 6, 7],
    "every": [1, 2, 3, 4, 5, 6, 7],
    "weekdays": [2, 3, 4, 5, 6],
    "workdays": [2, 3, 4, 5, 6],
    "weekend": [7, 1],
    "weekends": [7, 1],
}


def _parse_payload(payload: str) -> Any:
    stripped = payload.strip()
    if not stripped:
        return ""
    if stripped.startswith("{") or stripped.startswith("["):
        return json.loads(stripped)
    return stripped


def _coerce_bool(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    lowered = str(value).strip().lower()
    if lowered in {"1", "true", "yes", "on"}:
        return True
    if lowered in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"Cannot parse boolean value: {value}")


def _coerce_number(value: Any) -> int | float:
    if isinstance(value, int | float):
        return value
    text = str(value).strip()
    return float(text) if "." in text else int(text)


def _coerce_days(value: Any) -> str:
    """Map an Android AlarmClock days specifier to a comma-separated 1-7 list.

    Accepts named groups (`daily`, `weekdays`, `weekend`), German/English day
    abbreviations (`mo`, `di`, `mon`, `tue`, ...), full names (`monday`),
    raw integers (`2,3,6`), or a Python list. Empty input returns "".
    """
    if isinstance(value, list):
        tokens: list[str] = [str(item).strip() for item in value if str(item).strip()]
    else:
        text = str(value).strip().lower()
        if not text:
            return ""
        if text in _DAY_GROUPS:
            return ",".join(str(d) for d in _DAY_GROUPS[text])
        tokens = [tok.strip() for tok in text.split(",") if tok.strip()]

    days: list[int] = []
    for raw in tokens:
        token = raw.lower()
        if token.isdigit():
            number = int(token)
            if not 1 <= number <= 7:
                raise ValueError(f"Day number must be between 1 and 7, got {number}")
            days.append(number)
            continue
        if token in _DAY_TOKENS:
            days.append(_DAY_TOKENS[token])
            continue
        raise ValueError(f"Unknown day token: {raw}")

    seen: set[int] = set()
    ordered: list[int] = []
    for day in days:
        if day in seen:
            continue
        seen.add(day)
        ordered.append(day)
    return ",".join(str(d) for d in ordered)


def _coerce_choice(spec: InputSpec, value: Any) -> tuple[Any, dict[str, str] | None]:
    if value is None or value == "":
        if spec.required:
            raise ValueError(f"Input {spec.name} is required")
        return value, None

    choice = spec.choice_for_payload(value)
    if choice is None:
        allowed = spec.choice_names()
        raise ValueError(f"Input {spec.name} must be one of: {', '.join(allowed)}")
    return choice.value, {
        "key": choice.key,
        "name": choice.name,
        "value": choice.value,
    }


def _coerce_value(spec: InputSpec, value: Any) -> Any:
    if value is None or value == "":
        if spec.required:
            raise ValueError(f"Input {spec.name} is required")
        return value

    if spec.type == "text":
        return str(value)
    if spec.type == "number":
        number = _coerce_number(value)
        if spec.min is not None and number < spec.min:
            raise ValueError(f"Input {spec.name} must be >= {spec.min}")
        if spec.max is not None and number > spec.max:
            raise ValueError(f"Input {spec.name} must be <= {spec.max}")
        return number
    if spec.type == "bool":
        return _coerce_bool(value)
    if spec.type == "choice":
        return _coerce_choice(spec, value)[0]
    if spec.type == "json":
        return json.loads(value) if isinstance(value, str) else value
    if spec.type == "days":
        return _coerce_days(value)

    raise ValueError(f"Unsupported input type for {spec.name}: {spec.type}")


def resolve_inputs(endpoint: EndpointConfig, payload: str) -> tuple[dict[str, Any], set[str]]:
    parsed_payload = _parse_payload(payload)
    payload_input_names = [
        name for name, spec in endpoint.inputs.items() if spec.from_payload
    ]
    variables: dict[str, Any] = {}
    secrets: set[str] = set()

    for name, spec in endpoint.inputs.items():
        value = None
        has_value = False

        if spec.env:
            env_value = environ.get(spec.env)
            if env_value is not None:
                value = env_value
                has_value = True

        if spec.from_payload:
            key = spec.payload_key or name
            if isinstance(parsed_payload, dict) and key in parsed_payload:
                value = parsed_payload[key]
                has_value = True
            elif not isinstance(parsed_payload, dict) and (
                len(payload_input_names) == 1 or name == payload_input_names[0]
            ):
                # Non-dict payload routes to the first from-payload input;
                # any further from-payload inputs fall through to env/default.
                value = parsed_payload
                has_value = True

        if not has_value and spec.default is not None:
            value = spec.default
            has_value = True

        if not has_value:
            if spec.required:
                raise ValueError(f"Input {name} is required")
            value = None

        if spec.type == "choice":
            variables[name], choice_context = _coerce_choice(spec, value)
            if choice_context is not None:
                variables[f"{name}_choice"] = choice_context
        else:
            variables[name] = _coerce_value(spec, value)
        if spec.secret:
            secrets.add(name)

    return variables, secrets
