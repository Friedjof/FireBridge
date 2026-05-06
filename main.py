from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import replace

from tools.adb import AdbRunner
from tools.models import ToolContext, ToolResult
from tools.registry import available_tools, build_tool_result


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="firebridge")
    subparsers = parser.add_subparsers(dest="command")

    serve_parser = subparsers.add_parser("serve", help="Run the MQTT bridge service")
    serve_parser.add_argument(
        "--dry-run-discovery",
        action="store_true",
        help="Print Home Assistant discovery payloads and exit",
    )
    serve_parser.add_argument("--config-dir", help="Endpoint YAML directory")

    workflows_parser = subparsers.add_parser("workflows", help="Run YAML workflows")
    workflows_subparsers = workflows_parser.add_subparsers(dest="workflows_command")

    workflows_list_parser = workflows_subparsers.add_parser(
        "list",
        help="List YAML workflow endpoints",
    )
    workflows_list_parser.add_argument("--config-dir", help="Endpoint YAML directory")

    workflows_run_parser = workflows_subparsers.add_parser(
        "run",
        help="Build or execute a YAML workflow endpoint",
    )
    workflows_run_parser.add_argument("id")
    workflows_run_parser.add_argument("--payload", default="", help="MQTT payload to use")
    workflows_run_parser.add_argument("--dry-run", action="store_true", help="Only print the plan")
    workflows_run_parser.add_argument("--config-dir", help="Endpoint YAML directory")

    tools_parser = subparsers.add_parser("tools", help="Run endpoint-style tools")
    tools_subparsers = tools_parser.add_subparsers(dest="tools_command")

    tools_subparsers.add_parser("list", help="List available tools")

    run_parser = tools_subparsers.add_parser("run", help="Build or execute a tool plan")
    run_parser.add_argument("name", choices=available_tools())
    run_parser.add_argument("--dry-run", action="store_true", help="Only print the plan")
    run_parser.add_argument("--url", help="URL for url.open")
    run_parser.add_argument("--value", type=int, help="Numeric value for tools like brightness.set")

    return parser


def _print_tool_result(result: ToolResult) -> None:
    print(json.dumps(result.to_dict(), indent=2, sort_keys=True))


def _execute_tool_result(result: ToolResult) -> int:
    runner = AdbRunner(timeout=int(os.environ.get("ADB_COMMAND_TIMEOUT", "10")))
    executed = []
    exit_code = 0

    for command in result.commands:
        completed = runner.run(command)
        executed.append(
            {
                "argv": command.to_dict()["argv"],
                "returncode": completed.returncode,
                "stdout": completed.stdout,
                "stderr": completed.stderr,
            }
        )
        if completed.returncode != 0:
            exit_code = completed.returncode
            break

    print(
        json.dumps(
            {
                **result.to_dict(),
                "executed": executed,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return exit_code


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command is None:
        parser.print_help()
        return 0

    if args.command == "serve":
        from firebridge.config import AppConfig
        from firebridge.discovery import build_discovery_payloads
        from firebridge.mqtt_bridge import MqttBridge
        from firebridge.yaml_endpoints import load_endpoints

        config = AppConfig.from_env()
        if args.config_dir:
            config = replace(config, config_dir=args.config_dir)
        endpoints = load_endpoints(config.config_dir)
        if args.dry_run_discovery:
            print(
                json.dumps(
                    [
                        payload.to_dict()
                        for payload in build_discovery_payloads(
                            config,
                            endpoints if endpoints else None,
                        )
                    ],
                    indent=2,
                    sort_keys=True,
                )
            )
            return 0

        return MqttBridge(config).run_forever()

    if args.command == "workflows":
        from firebridge.config import AppConfig
        from firebridge.workflow import WorkflowRunner
        from firebridge.yaml_endpoints import load_endpoints

        config = AppConfig.from_env()
        if args.config_dir:
            config = replace(config, config_dir=args.config_dir)
        endpoints = load_endpoints(config.config_dir)

        if args.workflows_command == "list":
            for endpoint in endpoints:
                print(f"{endpoint.id}\t{endpoint.kind}\t{endpoint.command_topic(config)}")
            return 0

        if args.workflows_command == "run":
            endpoint = next((item for item in endpoints if item.id == args.id), None)
            if endpoint is None:
                print(f"Unknown workflow endpoint: {args.id}", file=sys.stderr)
                return 2
            try:
                workflow = WorkflowRunner(
                    config,
                    AdbRunner(timeout=config.adb_command_timeout),
                    sleeper=(lambda seconds: None) if args.dry_run else time.sleep,
                )
                result = workflow.run(endpoint, args.payload, dry_run=args.dry_run)
            except Exception as exc:
                print(str(exc), file=sys.stderr)
                return 2
            print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
            return 0

    if args.command == "tools" and args.tools_command == "list":
        for name in available_tools():
            print(name)
        return 0

    if args.command == "tools" and args.tools_command == "run":
        try:
            result = build_tool_result(
                args.name,
                ToolContext.from_env(),
                url=args.url,
                value=args.value,
            )
        except ValueError as exc:
            print(str(exc), file=sys.stderr)
            return 2

        if args.dry_run:
            _print_tool_result(result)
            return 0

        return _execute_tool_result(result)

    parser.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
