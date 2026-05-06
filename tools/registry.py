from __future__ import annotations

from collections.abc import Callable
from typing import Any

from .brightness import set_brightness
from .models import ToolContext, ToolResult
from .screen import screen_off, screen_on, screen_toggle
from .status import read_status
from .url import open_url


ToolFactory = Callable[..., ToolResult]

_TOOLS: dict[str, ToolFactory] = {
    "brightness.set": set_brightness,
    "screen.off": screen_off,
    "screen.on": screen_on,
    "screen.toggle": screen_toggle,
    "status.read": read_status,
    "url.open": open_url,
}


def available_tools() -> list[str]:
    return sorted(_TOOLS)


def build_tool_result(name: str, context: ToolContext, **kwargs: Any) -> ToolResult:
    try:
        factory = _TOOLS[name]
    except KeyError as exc:
        raise ValueError(f"Unknown tool: {name}") from exc

    if name == "url.open":
        return factory(context, kwargs.get("url"))
    if name == "brightness.set":
        value = kwargs.get("value")
        if value is None:
            raise ValueError("brightness.set requires --value")
        return factory(context, int(value))

    return factory(context)
