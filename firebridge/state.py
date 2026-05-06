from __future__ import annotations

import re
from typing import Any

from tools.adb import AdbRunner, adb_command, adb_shell
from tools.models import ToolContext


BATTERY_STATUS = {
    "1": "Unknown",
    "2": "Charging",
    "3": "Discharging",
    "4": "Not charging",
    "5": "Full",
}


def parse_battery(text: str) -> dict[str, Any]:
    level = None
    status = None
    for line in text.splitlines():
        stripped = line.strip()
        if stripped.startswith("level:"):
            level = int(stripped.split(":", 1)[1].strip())
        if stripped.startswith("status:"):
            raw_status = stripped.split(":", 1)[1].strip()
            status = BATTERY_STATUS.get(raw_status, raw_status)
    return {"battery_level": level, "battery_status": status}


def parse_power(text: str) -> dict[str, Any]:
    screen_on_patterns = [
        r"Display Power: state=ON",
        r"mWakefulness=Awake",
        r"mInteractive=true",
        r"screenState=ON",
    ]
    screen_off_patterns = [
        r"Display Power: state=OFF",
        r"mWakefulness=Asleep",
        r"mInteractive=false",
        r"screenState=OFF",
    ]

    if any(re.search(pattern, text) for pattern in screen_on_patterns):
        return {"screen_on": True}
    if any(re.search(pattern, text) for pattern in screen_off_patterns):
        return {"screen_on": False}
    return {"screen_on": None}


def _run_text(runner: AdbRunner, command) -> str:
    completed = runner.run(command)
    if completed.returncode != 0:
        return ""
    return completed.stdout.strip()


def read_device_state(context: ToolContext, runner: AdbRunner) -> dict[str, Any]:
    state: dict[str, Any] = {
        "connected": False,
        "adb_state": "unknown",
        "serial": context.adb_serial or None,
        "model": None,
        "device": None,
        "android": None,
        "battery_level": None,
        "battery_status": None,
        "screen_on": None,
        "locked": None,
        "foreground_app": None,
        "wifi_ip": None,
    }

    try:
        adb_state = runner.run(adb_command(context, "get-state", description="Read ADB state"))
    except OSError as exc:
        state["adb_state"] = "error"
        state["error"] = str(exc)
        return state

    state["adb_state"] = adb_state.stdout.strip() or "unknown"
    state["connected"] = adb_state.returncode == 0 and state["adb_state"] == "device"
    if not state["connected"]:
        state["error"] = adb_state.stderr.strip() or None
        return state

    state["model"] = _run_text(
        runner,
        adb_shell(context, "getprop", "ro.product.model", description="Read model"),
    ) or None
    state["device"] = _run_text(
        runner,
        adb_shell(context, "getprop", "ro.product.device", description="Read device"),
    ) or None
    state["android"] = _run_text(
        runner,
        adb_shell(
            context,
            "getprop",
            "ro.build.version.release",
            description="Read Android version",
        ),
    ) or None

    battery = _run_text(
        runner,
        adb_shell(context, "dumpsys", "battery", description="Read battery"),
    )
    power = _run_text(
        runner,
        adb_shell(context, "dumpsys", "power", description="Read power state"),
    )
    state.update(parse_battery(battery))
    state.update(parse_power(power))

    return state
