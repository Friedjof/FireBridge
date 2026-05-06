from __future__ import annotations

from .adb import adb_command, adb_shell
from .models import ToolContext, ToolResult


def read_status(context: ToolContext) -> ToolResult:
    return ToolResult(
        tool="status.read",
        description="Read device status probes",
        commands=[
            adb_command(context, "get-state", description="Read ADB connection state"),
            adb_shell(
                context,
                "getprop",
                "ro.product.model",
                description="Read device model",
            ),
            adb_shell(
                context,
                "getprop",
                "ro.product.device",
                description="Read device codename",
            ),
            adb_shell(
                context,
                "getprop",
                "ro.build.version.release",
                description="Read Android version",
            ),
            adb_shell(context, "dumpsys", "battery", description="Read battery state"),
            adb_shell(context, "dumpsys", "power", description="Read display power state"),
        ],
        state={},
    )
