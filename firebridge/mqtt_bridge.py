from __future__ import annotations

import json
import sys
import time
from dataclasses import dataclass
from threading import RLock

from tools.adb import AdbRunner
from tools.models import ToolResult
from tools.registry import build_tool_result

from .config import AppConfig
from .discovery import build_discovery_payloads
from .executor import execute_tool_result
from .scheduler import WorkflowScheduler
from .state import read_device_state
from .workflow import WorkflowResult, WorkflowRunner
from .yaml_endpoints import EndpointConfig, load_endpoints


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

    def run_forever(self) -> int:
        if not self.config.mqtt_host:
            print("MQTT_HOST is required for firebridge serve", file=sys.stderr)
            return 2

        try:
            import paho.mqtt.client as mqtt
        except ImportError:
            print("paho-mqtt is not installed", file=sys.stderr)
            return 2

        if self.config.adb_target and self.config.adb_connect_on_start:
            self.runner.connect(self.config.adb_target)

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
            client.publish(self.config.availability_topic, "online", retain=True)
            for topic in self._subscription_topics():
                client.subscribe(topic)
            if self.config.mqtt_discovery_enabled:
                self._publish_discovery(client)
            self._publish_state(client)

        def on_message(client, userdata, message):
            if should_ignore_mqtt_message(self.config, bool(message.retain)):
                print(
                    f"Ignoring retained MQTT command on {message.topic}",
                    file=sys.stderr,
                )
                return

            payload = message.payload.decode("utf-8", errors="replace")
            try:
                action = action_from_message(
                    self.config,
                    message.topic,
                    payload,
                    self.endpoints if self.endpoints else None,
                )
                if action is None:
                    return
                if action.kind == "reconnect":
                    if self.config.adb_target:
                        with self.adb_lock:
                            self.runner.connect(self.config.adb_target)
                    self._publish_state(client)
                    return
                if action.kind == "workflow" and action.endpoint is not None:
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
                    self._publish_workflow_return_state(
                        client,
                        action.endpoint,
                        workflow_result,
                    )
                    self._publish_state(client)
                    return
                if action.result is not None:
                    with self.adb_lock:
                        report = execute_tool_result(action.result, self.runner)
                    if report.exit_code != 0:
                        print(json.dumps(report.to_dict()), file=sys.stderr)
                    self._publish_action_state(client, action.result)
                    self._publish_state(client)
            except Exception as exc:  # MQTT callbacks should not crash the service.
                print(f"Failed to handle MQTT message on {message.topic}: {exc}", file=sys.stderr)

        client.on_connect = on_connect
        client.on_message = on_message
        client.connect(self.config.mqtt_host, self.config.mqtt_port, keepalive=60)

        try:
            client.loop_start()
            last_state_publish = time.monotonic()
            while True:
                time.sleep(1)
                try:
                    scheduled_results = scheduler.run_due()
                    if scheduled_results:
                        self._publish_state(client)
                except Exception as exc:
                    print(f"Failed to run scheduled workflow: {exc}", file=sys.stderr)

                if time.monotonic() - last_state_publish >= max(
                    1,
                    self.config.mqtt_state_interval,
                ):
                    self._publish_state(client)
                    last_state_publish = time.monotonic()
        except KeyboardInterrupt:
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

    def _publish_discovery(self, client) -> None:
        for discovery in build_discovery_payloads(
            self.config,
            self.endpoints if self.endpoints else None,
        ):
            client.publish(
                discovery.topic,
                json.dumps(discovery.payload, sort_keys=True),
                retain=True,
            )

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
