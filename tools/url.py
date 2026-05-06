from __future__ import annotations

from urllib.parse import urlparse

from .adb import adb_shell
from .models import ToolCommand, ToolContext, ToolResult


def build_open_url_commands(context: ToolContext, url: str) -> list[ToolCommand]:
    parsed = urlparse(url)
    if not parsed.scheme or not parsed.netloc:
        raise ValueError("URL must include scheme and host, for example https://example.org")

    args = [
        "am",
        "start",
        "-a",
        "android.intent.action.VIEW",
        "-d",
        url,
    ]
    if context.browser_package:
        args.extend(["-p", context.browser_package])

    return [
        adb_shell(
            context,
            *args,
            description="Open URL on the Android device",
        )
    ]


def open_url(context: ToolContext, url: str | None = None) -> ToolResult:
    target_url = url or context.default_url
    if not target_url:
        raise ValueError("url.open requires --url or DEFAULT_URL")

    return ToolResult(
        tool="url.open",
        description="Open a URL through Android intent handling",
        commands=build_open_url_commands(context, target_url),
        state={"url": target_url},
    )
