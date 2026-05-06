from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .config import AppConfig
from .yaml_endpoints import EndpointConfig


COMMAND_TOPIC_COMPONENTS = {
    "button",
    "number",
    "select",
    "switch",
    "text",
}

STATE_TOPIC_COMPONENTS = {
    "binary_sensor",
    "number",
    "select",
    "sensor",
    "switch",
    "text",
}

SENSOR_TRIGGER_COMPONENTS = {"binary_sensor", "sensor"}


@dataclass(frozen=True)
class DiscoveryPayload:
    component: str
    object_id: str
    topic: str
    payload: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "component": self.component,
            "object_id": self.object_id,
            "topic": self.topic,
            "payload": self.payload,
        }


def _device(config: AppConfig) -> dict[str, Any]:
    return {
        "identifiers": [config.device_id],
        "name": config.device_name,
        "manufacturer": "FireBridge",
        "model": "ADB controlled Android tablet",
    }


def _discovery_topic(config: AppConfig, component: str, object_id: str) -> str:
    prefix = config.mqtt_discovery_prefix.strip("/")
    return f"{prefix}/{component}/{config.device_id}/{object_id}/config"


def _payload(
    config: AppConfig,
    component: str,
    object_id: str,
    name: str,
    **values: Any,
) -> DiscoveryPayload:
    payload = {
        "name": name,
        "unique_id": f"{config.device_id}_{object_id}",
        "availability_topic": config.availability_topic,
        "payload_available": "online",
        "payload_not_available": "offline",
        "device": _device(config),
        **values,
    }
    return DiscoveryPayload(
        component=component,
        object_id=object_id,
        topic=_discovery_topic(config, component, object_id),
        payload=payload,
    )


def _select_options(endpoint: EndpointConfig) -> list[str]:
    for spec in endpoint.inputs.values():
        if spec.type == "choice" and spec.choices:
            return spec.choice_names()
    return []


def _endpoint_payload(config: AppConfig, endpoint: EndpointConfig) -> DiscoveryPayload | None:
    if not endpoint.ha or endpoint.ha.get("enabled", True) is False:
        return None

    component = str(endpoint.ha.get("component", "button"))
    object_id = str(endpoint.ha.get("object_id", endpoint.id))
    name = str(endpoint.ha.get("name", endpoint.name))
    values = {
        key: value
        for key, value in endpoint.ha.items()
        if key
        not in {
            "component",
            "object_id",
            "name",
            "enabled",
            "unit",
            "trigger_button",
            "trigger_button_name",
            "trigger_button_object_id",
            "trigger_payload",
        }
    }
    if "unit" in endpoint.ha and "unit_of_measurement" not in values:
        values["unit_of_measurement"] = endpoint.ha["unit"]

    command_topic = endpoint.command_topic(config)
    state_topic = endpoint.state_topic(config)
    values.pop("command_topic", None)
    values.pop("state_topic", None)

    if component in COMMAND_TOPIC_COMPONENTS and command_topic:
        values["command_topic"] = command_topic
    if component in STATE_TOPIC_COMPONENTS and state_topic:
        values["state_topic"] = state_topic
    if component == "select" and "options" not in values:
        options = _select_options(endpoint)
        if options:
            values["options"] = options

    return _payload(config, component, object_id, name, **values)


def _endpoint_trigger_button(
    config: AppConfig,
    endpoint: EndpointConfig,
) -> DiscoveryPayload | None:
    component = str(endpoint.ha.get("component", "button"))
    command_topic = endpoint.command_topic(config)
    if component not in SENSOR_TRIGGER_COMPONENTS or not command_topic:
        return None
    if endpoint.ha.get("trigger_button", True) is False:
        return None

    object_id = str(endpoint.ha.get("object_id", endpoint.id))
    name = str(endpoint.ha.get("name", endpoint.name))
    button_object_id = str(endpoint.ha.get("trigger_button_object_id", f"{object_id}_read"))
    button_name = str(endpoint.ha.get("trigger_button_name", f"Read {name}"))
    payload_press = str(endpoint.ha.get("trigger_payload", "READ"))

    return _payload(
        config,
        "button",
        button_object_id,
        button_name,
        command_topic=command_topic,
        payload_press=payload_press,
    )


def _endpoint_payloads(config: AppConfig, endpoint: EndpointConfig) -> list[DiscoveryPayload]:
    payloads = []
    primary = _endpoint_payload(config, endpoint)
    if primary is not None:
        payloads.append(primary)
    trigger_button = _endpoint_trigger_button(config, endpoint)
    if trigger_button is not None:
        payloads.append(trigger_button)
    return payloads


def build_discovery_payloads(
    config: AppConfig,
    endpoints: list[EndpointConfig] | None = None,
) -> list[DiscoveryPayload]:
    if endpoints is not None:
        payloads: list[DiscoveryPayload] = []
        for endpoint in endpoints:
            payloads.extend(_endpoint_payloads(config, endpoint))
        return payloads

    return [
        _payload(
            config,
            "switch",
            "display",
            "Display",
            command_topic=config.screen_command_topic,
            state_topic=config.screen_state_topic,
            payload_on="ON",
            payload_off="OFF",
        ),
        _payload(
            config,
            "button",
            "open_default_url",
            "Open Default URL",
            command_topic=config.default_url_command_topic,
        ),
        _payload(
            config,
            "button",
            "reconnect_adb",
            "Reconnect ADB",
            command_topic=config.reconnect_command_topic,
        ),
        _payload(
            config,
            "binary_sensor",
            "connected",
            "Connected",
            state_topic=config.state_topic,
            value_template="{{ 'ON' if value_json.connected else 'OFF' }}",
            payload_on="ON",
            payload_off="OFF",
            device_class="connectivity",
        ),
        _payload(
            config,
            "binary_sensor",
            "screen",
            "Screen",
            state_topic=config.screen_state_topic,
            payload_on="ON",
            payload_off="OFF",
        ),
        _payload(
            config,
            "sensor",
            "adb_state",
            "ADB State",
            state_topic=config.state_topic,
            value_template="{{ value_json.adb_state }}",
        ),
        _payload(
            config,
            "sensor",
            "battery",
            "Battery",
            state_topic=config.state_topic,
            value_template="{{ value_json.battery_level }}",
            unit_of_measurement="%",
            device_class="battery",
            state_class="measurement",
        ),
        _payload(
            config,
            "number",
            "brightness",
            "Brightness",
            command_topic=config.brightness_command_topic,
            state_topic=config.brightness_state_topic,
            min=0,
            max=255,
            step=1,
            mode="slider",
        ),
        _payload(
            config,
            "text",
            "open_url",
            "Open URL",
            command_topic=config.url_command_topic,
            mode="text",
        ),
    ]
