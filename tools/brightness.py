from __future__ import annotations

from .adb import adb_shell
from .models import ToolContext, ToolResult


def set_brightness(context: ToolContext, value: int) -> ToolResult:
    if value < 0 or value > 255:
        raise ValueError("brightness.set requires a value between 0 and 255")

    return ToolResult(
        tool="brightness.set",
        description="Set Android screen brightness",
        commands=[
            adb_shell(
                context,
                "settings",
                "put",
                "system",
                "screen_brightness",
                str(value),
                description="Set screen brightness",
            )
        ],
        state={"brightness": value},
    )
