from __future__ import annotations

import json
import time
from dataclasses import dataclass
from threading import RLock

from tools.adb import AdbRunner
from tools.models import ToolResult
from tools.registry import build_tool_result

from .config import AppConfig
from .discovery import build_discovery_payloads
from .executor import execute_tool_result
from .logging import get_logger, truncate
from .scheduler import WorkflowScheduler
from .state import read_device_state
from .workflow import WorkflowResult, WorkflowRunner
from .yaml_endpoints import EndpointConfig, load_endpoints

log = get_logger("firebridge.mqtt")


def _reason_code_value(reason_code) -> int | None:
    if reason_code is None:
        return None
    value = getattr(reason_code, "value", reason_code)
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True)
class MqttAction:
    kind: str
    result: ToolResult | None = None
    endpoint: EndpointConfig | None = None
    payload: str = ""


def action_from_message(
    config: AppConfig,
    topic: str,
    payload: str,
    endpoints: list[EndpointConfig] | None = None,
) -> MqttAction | None:
    stripped_payload = payload.strip()
    context = config.tool_context()

    if endpoints is not None:
        for endpoint in endpoints:
            if endpoint.command_topic(config) == topic:
                return MqttAction("workflow", endpoint=endpoint, payload=payload)

        if topic == config.reconnect_command_topic:
            return MqttAction("reconnect")

        return None

    if topic == config.screen_command_topic:
        requested_state = stripped_payload.upper()
        if requested_state == "ON":
            return MqttAction("tool", build_tool_result("screen.on", context))
        if requested_state == "OFF":
            return MqttAction("tool", build_tool_result("screen.off", context))
        if requested_state == "TOGGLE":
            return MqttAction("tool", build_tool_result("screen.toggle", context))
        raise ValueError("screen/set payload must be ON, OFF, or TOGGLE")

    if topic == config.url_command_topic:
        url = stripped_payload
        if stripped_payload.startswith("{"):
            data = json.loads(stripped_payload)
            url = str(data.get("url", ""))
        return MqttAction("tool", build_tool_result("url.open", context, url=url))

    if topic == config.default_url_command_topic:
        return MqttAction("tool", build_tool_result("url.open", context))

    if topic == config.brightness_command_topic:
        return MqttAction(
            "tool",
            build_tool_result("brightness.set", context, value=int(stripped_payload)),
        )

    if topic == config.reconnect_command_topic:
        return MqttAction("reconnect")

    return None


def should_ignore_mqtt_message(config: AppConfig, retained: bool) -> bool:
    return config.mqtt_ignore_retained_commands and retained


class MqttBridge:
    def __init__(self, config: AppConfig, runner: AdbRunner | None = None) -> None:
        self.config = config
        self.runner = runner or AdbRunner(timeout=config.adb_command_timeout)
        self.endpoints = load_endpoints(config.config_dir)
        self.adb_lock = RLock()
        self._discovery_current: set[str] = set()
        self._discovery_observed: set[str] = set()
        self._discovery_reconcile_at: float | None = None
        self._discovery_reconciled = True

    def run_forever(self) -> int:
        if not self.config.mqtt_host:
            log.error("MQTT_HOST is required for firebridge serve")
            return 2

        try:
            import paho.mqtt.client as mqtt
        except ImportError:
            log.error("paho-mqtt is not installed")
            return 2

        log.info(
            "Starting bridge",
            extra={
                "mqtt_host": self.config.mqtt_host,
                "mqtt_port": self.config.mqtt_port,
                "client_id": self.config.mqtt_client_id,
                "base_topic": self.config.base_topic,
                "config_dir": self.config.config_dir,
                "endpoints": len(self.endpoints),
                "adb_target": self.config.adb_target or "<usb>",
            },
        )

        if self.config.adb_target and self.config.adb_connect_on_start:
            log.info("Connecting ADB", extra={"target": self.config.adb_target})
            connect_result = self.runner.connect(self.config.adb_target)
            if connect_result.returncode == 0:
                log.info(
                    "ADB connect ok",
                    extra={"target": self.config.adb_target, "stdout": truncate(connect_result.stdout.strip(), 120)},
                )
            else:
                log.warning(
                    "ADB connect returned non-zero",
                    extra={
                        "target": self.config.adb_target,
                        "rc": connect_result.returncode,
                        "stderr": truncate(connect_result.stderr.strip(), 200),
                    },
                )

        client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=self.config.mqtt_client_id,
        )

        if self.config.mqtt_username:
            client.username_pw_set(
                self.config.mqtt_username,
                self.config.mqtt_password or None,
            )

        client.will_set(self.config.availability_topic, "offline", retain=True)
        scheduler = WorkflowScheduler(
            self.config,
            self.endpoints,
            self.runner,
            publisher=lambda topic, payload, retain: client.publish(
                topic,
                payload,
                retain=retain,
            ),
            adb_lock=self.adb_lock,
        )

        def on_connect(client, userdata, flags, reason_code, properties):
            rc_value = _reason_code_value(reason_code)
            log.info(
                "Connected to MQTT broker",
                extra={
                    "host": self.config.mqtt_host,
                    "port": self.config.mqtt_port,
                    "reason_code": rc_value,
                    "reason": str(reason_code),
                },
            )
            client.publish(self.config.availability_topic, "online", retain=True)
            topics = self._subscription_topics()
            for topic in topics:
                client.subscribe(topic)
            log.info(
                "Subscribed to command topics",
                extra={"count": len(topics), "base_topic": self.config.base_topic},
            )
            log.debug("Subscriptions", extra={"topics": topics})
            if self.config.mqtt_discovery_enabled:
                self._discovery_current = self._current_discovery_topics()
                published = self._publish_discovery(client)
                log.info(
                    "Published HA discovery payloads",
                    extra={"count": published, "prefix": self.config.mqtt_discovery_prefix},
                )
                if self.config.mqtt_discovery_cleanup:
                    wildcard = self._discovery_wildcard()
                    client.subscribe(wildcard)
                    self._discovery_observed.clear()
                    self._discovery_reconciled = False
                    self._discovery_reconcile_at = (
                        time.monotonic() + self.config.mqtt_discovery_cleanup_delay
                    )
                    log.info(
                        "Watching discovery wildcard for stale entities",
                        extra={
                            "pattern": wildcard,
                            "delay_s": self.config.mqtt_discovery_cleanup_delay,
                        },
                    )
            self._publish_state(client)

        def on_disconnect(client, userdata, disconnect_flags, reason_code, properties):
            rc_value = _reason_code_value(reason_code)
            level = log.warning if rc_value not in (0, None) else log.info
            level(
                "Disconnected from MQTT broker",
                extra={"reason_code": rc_value, "reason": str(reason_code)},
            )

        def on_message(client, userdata, message):
            if (
                self.config.mqtt_discovery_enabled
                and self.config.mqtt_discovery_cleanup
                and self._is_owned_discovery_topic(message.topic)
            ):
                if bool(message.retain) and message.topic not in self._discovery_current:
                    self._discovery_observed.add(message.topic)
                return

            if should_ignore_mqtt_message(self.config, bool(message.retain)):
                log.debug(
                    "Ignoring retained MQTT command",
                    extra={"topic": message.topic},
                )
                return

            payload = message.payload.decode("utf-8", errors="replace")
            log.info(
                "MQTT command received",
                extra={"topic": message.topic, "payload": truncate(payload, 200)},
            )
            try:
                action = action_from_message(
                    self.config,
                    message.topic,
                    payload,
                    self.endpoints if self.endpoints else None,
                )
                if action is None:
                    log.debug(
                        "No action mapped for topic",
                        extra={"topic": message.topic},
                    )
                    return
                if action.kind == "reconnect":
                    log.info(
                        "Handling reconnect request",
                        extra={"target": self.config.adb_target or "<usb>"},
                    )
                    if self.config.adb_target:
                        with self.adb_lock:
                            self.runner.connect(self.config.adb_target)
                    self._publish_state(client)
                    return
                if action.kind == "workflow" and action.endpoint is not None:
                    started = time.monotonic()
                    log.info(
                        "Running workflow",
                        extra={
                            "endpoint_id": action.endpoint.id,
                            "kind": action.endpoint.kind,
                            "payload": truncate(action.payload, 120),
                        },
                    )
                    with self.adb_lock:
                        workflow = WorkflowRunner(
                            self.config,
                            self.runner,
                            publisher=lambda topic, payload, retain: client.publish(
                                topic,
                                payload,
                                retain=retain,
                            ),
                        )
                        workflow_result = workflow.run(action.endpoint, action.payload)
                    duration_ms = int((time.monotonic() - started) * 1000)
                    log.info(
                        "Workflow finished",
                        extra={
                            "endpoint_id": action.endpoint.id,
                            "status": workflow_result.status,
                            "return_value": truncate(workflow_result.return_value, 120),
                            "commands": len(workflow_result.commands),
                            "publishes": len(workflow_result.publishes),
                            "duration_ms": duration_ms,
                        },
                    )
                    self._publish_workflow_return_state(
                        client,
                        action.endpoint,
                        workflow_result,
                    )
                    self._publish_state(client)
                    return
                if action.result is not None:
                    log.info(
                        "Running tool",
                        extra={
                            "tool": action.result.tool,
                            "commands": len(action.result.commands),
                        },
                    )
                    with self.adb_lock:
                        report = execute_tool_result(action.result, self.runner)
                    if report.exit_code != 0:
                        log.error(
                            "Tool execution failed",
                            extra={
                                "tool": action.result.tool,
                                "rc": report.exit_code,
                                "report": truncate(json.dumps(report.to_dict()), 400),
                            },
                        )
                    else:
                        log.debug(
                            "Tool execution ok",
                            extra={"tool": action.result.tool},
                        )
                    self._publish_action_state(client, action.result)
                    self._publish_state(client)
            except Exception as exc:  # MQTT callbacks should not crash the service.
                log.exception(
                    "Failed to handle MQTT message",
                    extra={"topic": message.topic, "error": str(exc)},
                )

        client.on_connect = on_connect
        client.on_disconnect = on_disconnect
        client.on_message = on_message
        client.connect(self.config.mqtt_host, self.config.mqtt_port, keepalive=60)

        try:
            client.loop_start()
            last_state_publish = time.monotonic()
            while True:
                time.sleep(1)
                self._maybe_reconcile_discovery(client)
                try:
                    scheduled_results = scheduler.run_due()
                    if scheduled_results:
                        self._publish_state(client)
                except Exception as exc:
                    log.exception(
                        "Scheduled workflow run failed",
                        extra={"error": str(exc)},
                    )

                if time.monotonic() - last_state_publish >= max(
                    1,
                    self.config.mqtt_state_interval,
                ):
                    self._publish_state(client)
                    last_state_publish = time.monotonic()
        except KeyboardInterrupt:
            log.info("Shutdown requested")
            client.publish(self.config.availability_topic, "offline", retain=True)
            client.disconnect()
            return 0
        finally:
            client.loop_stop()

        return 0

    def _subscription_topics(self) -> list[str]:
        if self.endpoints:
            topics = [
                topic
                for endpoint in self.endpoints
                if (topic := endpoint.command_topic(self.config))
            ]
            topics.append(self.config.reconnect_command_topic)
            return topics

        return [
            self.config.screen_command_topic,
            self.config.url_command_topic,
            self.config.default_url_command_topic,
            self.config.brightness_command_topic,
            self.config.reconnect_command_topic,
        ]

    def _publish_discovery(self, client) -> int:
        published = 0
        for discovery in build_discovery_payloads(
            self.config,
            self.endpoints if self.endpoints else None,
        ):
            client.publish(
                discovery.topic,
                json.dumps(discovery.payload, sort_keys=True),
                retain=True,
            )
            published += 1
        return published

    def _current_discovery_topics(self) -> set[str]:
        return {
            discovery.topic
            for discovery in build_discovery_payloads(
                self.config,
                self.endpoints if self.endpoints else None,
            )
        }

    def _discovery_wildcard(self) -> str:
        prefix = self.config.mqtt_discovery_prefix.strip("/")
        return f"{prefix}/+/{self.config.device_id}/+/config"

    def _is_owned_discovery_topic(self, topic: str) -> bool:
        prefix = self.config.mqtt_discovery_prefix.strip("/")
        parts = topic.split("/")
        return (
            len(parts) == 5
            and parts[0] == prefix
            and parts[2] == self.config.device_id
            and parts[4] == "config"
        )

    def _maybe_reconcile_discovery(self, client) -> None:
        if self._discovery_reconciled or self._discovery_reconcile_at is None:
            return
        if time.monotonic() < self._discovery_reconcile_at:
            return

        stale = sorted(self._discovery_observed - self._discovery_current)
        if stale:
            for topic in stale:
                client.publish(topic, payload="", retain=True)
            log.info(
                "Removed stale discovery entities",
                extra={"count": len(stale), "topics": stale},
            )
        else:
            log.debug("No stale discovery entities to remove")

        client.unsubscribe(self._discovery_wildcard())
        self._discovery_observed.clear()
        self._discovery_reconciled = True
        self._discovery_reconcile_at = None

    def _publish_action_state(self, client, result: ToolResult) -> None:
        if result.tool.startswith("screen.") and "screen" in result.state:
            client.publish(
                self.config.screen_state_topic,
                result.state["screen"],
                retain=True,
            )
        if result.tool == "brightness.set" and "brightness" in result.state:
            client.publish(
                self.config.brightness_state_topic,
                str(result.state["brightness"]),
                retain=True,
            )

    def _publish_workflow_return_state(
        self,
        client,
        endpoint: EndpointConfig,
        result: WorkflowResult,
    ) -> None:
        state_topic = endpoint.state_topic(self.config)
        if not state_topic or result.return_value is None:
            return

        already_published = any(publish.topic == state_topic for publish in result.publishes)
        if already_published:
            return

        client.publish(state_topic, str(result.return_value), retain=True)

    def _publish_state(self, client) -> None:
        with self.adb_lock:
            state = read_device_state(self.config.tool_context(), self.runner)
        client.publish(self.config.state_topic, json.dumps(state, sort_keys=True), retain=True)
        if state.get("screen_on") is not None:
            client.publish(
                self.config.screen_state_topic,
                "ON" if state["screen_on"] else "OFF",
                retain=True,
            )
