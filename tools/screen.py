from __future__ import annotations

from .adb import adb_shell
from .models import ToolCommand, ToolContext, ToolResult
from .url import build_open_url_commands


def _unlock_commands(context: ToolContext) -> list[ToolCommand]:
    if context.unlock_method == "none":
        return []
    if context.unlock_method == "swipe":
        return [
            adb_shell(
                context,
                "wm",
                "dismiss-keyguard",
                description="Dismiss a non-secure Android keyguard",
            ),
            adb_shell(
                context,
                "input",
                "swipe",
                "400",
                "700",
                "400",
                "200",
                description="Swipe to unlock the keyguard",
            )
        ]
    if context.unlock_method == "pin":
        if not context.unlock_pin:
            raise ValueError("UNLOCK_METHOD=pin requires UNLOCK_PIN")
        return [
            adb_shell(
                context,
                "input",
                "swipe",
                "400",
                "700",
                "400",
                "200",
                description="Open the PIN entry screen",
            ),
            adb_shell(
                context,
                "input",
                "text",
                context.unlock_pin,
                description="Enter unlock PIN",
                redacted_args=("input", "text", "<redacted>"),
            ),
            adb_shell(
                context,
                "input",
                "keyevent",
                "KEYCODE_ENTER",
                description="Submit unlock PIN",
            ),
        ]

    raise ValueError(
        f"Unsupported unlock method: {context.unlock_method}. "
        "Supported methods are: none, swipe, pin."
    )


def screen_on(context: ToolContext) -> ToolResult:
    commands = [
        adb_shell(
            context,
            "input",
            "keyevent",
            "KEYCODE_WAKEUP",
            description="Wake the display",
        ),
        *_unlock_commands(context),
        adb_shell(
            context,
            "settings",
            "put",
            "system",
            "screen_off_timeout",
            str(context.screen_off_timeout_ms),
            description="Set a long screen-off timeout",
        ),
    ]

    if context.default_url:
        commands.extend(build_open_url_commands(context, context.default_url))

    return ToolResult(
        tool="screen.on",
        description="Wake and keep the display awake",
        commands=commands,
        state={"screen": "ON"},
    )


def screen_off(context: ToolContext) -> ToolResult:
    return ToolResult(
        tool="screen.off",
        description="Put the display to sleep",
        commands=[
            adb_shell(
                context,
                "input",
                "keyevent",
                "KEYCODE_SLEEP",
                description="Sleep the display",
            )
        ],
        state={"screen": "OFF"},
    )


def screen_toggle(context: ToolContext) -> ToolResult:
    return ToolResult(
        tool="screen.toggle",
        description="Toggle the display power state",
        commands=[
            adb_shell(
                context,
                "input",
                "keyevent",
                "26",
                description="Toggle display power",
            )
        ],
        state={"screen": "TOGGLE"},
    )
