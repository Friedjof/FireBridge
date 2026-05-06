from __future__ import annotations

import re
from typing import Any


TEMPLATE_RE = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*)\}")


def resolve_variable(name: str, variables: dict[str, Any]) -> Any:
    value: Any = variables
    for part in name.split("."):
        if isinstance(value, dict) and part in value:
            value = value[part]
        else:
            raise KeyError(f"Unknown variable: {name}")
    return value


def render_template(
    value: Any,
    variables: dict[str, Any],
    secrets: set[str] | None = None,
) -> Any:
    if not isinstance(value, str):
        return value

    secrets = secrets or set()
    full_match = TEMPLATE_RE.fullmatch(value)
    if full_match:
        name = full_match.group(1)
        return "<redacted>" if name in secrets else resolve_variable(name, variables)

    def replace(match: re.Match[str]) -> str:
        name = match.group(1)
        if name in secrets:
            return "<redacted>"
        return str(resolve_variable(name, variables))

    return TEMPLATE_RE.sub(replace, value)


def render_nested(
    value: Any,
    variables: dict[str, Any],
    secrets: set[str] | None = None,
) -> Any:
    if isinstance(value, dict):
        return {key: render_nested(item, variables, secrets) for key, item in value.items()}
    if isinstance(value, list):
        return [render_nested(item, variables, secrets) for item in value]
    return render_template(value, variables, secrets)
