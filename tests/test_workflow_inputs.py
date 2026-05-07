import unittest

from firebridge.workflow_inputs import _coerce_days, resolve_inputs
from firebridge.yaml_endpoints import EndpointConfig, InputSpec


def _endpoint(inputs: dict[str, dict]) -> EndpointConfig:
    return EndpointConfig(
        id="t",
        kind="action",
        name="t",
        mqtt={},
        ha={},
        inputs={name: InputSpec.from_dict(name, spec) for name, spec in inputs.items()},
        steps=[],
    )


class CoerceDaysTests(unittest.TestCase):
    def test_named_groups(self):
        self.assertEqual(_coerce_days("daily"), "1,2,3,4,5,6,7")
        self.assertEqual(_coerce_days("weekdays"), "2,3,4,5,6")
        self.assertEqual(_coerce_days("workdays"), "2,3,4,5,6")
        self.assertEqual(_coerce_days("weekend"), "7,1")

    def test_german_short(self):
        self.assertEqual(_coerce_days("mo,di,fr"), "2,3,6")
        self.assertEqual(_coerce_days("so,sa"), "1,7")

    def test_english_short_and_long(self):
        self.assertEqual(_coerce_days("mon,wed,fri"), "2,4,6")
        self.assertEqual(_coerce_days("monday,Friday"), "2,6")

    def test_numeric_passthrough_and_dedup(self):
        self.assertEqual(_coerce_days("2,3,6"), "2,3,6")
        self.assertEqual(_coerce_days("mo,Mo,2"), "2")

    def test_list_input(self):
        self.assertEqual(_coerce_days([2, 3, 6]), "2,3,6")
        self.assertEqual(_coerce_days(["mo", "fr"]), "2,6")

    def test_empty_returns_empty(self):
        self.assertEqual(_coerce_days(""), "")
        self.assertEqual(_coerce_days("   "), "")

    def test_invalid_token_raises(self):
        with self.assertRaises(ValueError):
            _coerce_days("never")
        with self.assertRaises(ValueError):
            _coerce_days("0")
        with self.assertRaises(ValueError):
            _coerce_days("8")


class MultiInputPayloadRoutingTests(unittest.TestCase):
    def test_plain_text_payload_routes_to_first_from_payload_input(self):
        endpoint = _endpoint(
            {
                "time": {"type": "text", "from_payload": True, "payload_key": "time", "required": True},
                "days": {"type": "days", "from_payload": True, "payload_key": "days", "default": ""},
            }
        )

        variables, _ = resolve_inputs(endpoint, "07:30")

        self.assertEqual(variables["time"], "07:30")
        self.assertEqual(variables["days"], "")

    def test_json_payload_distributes_to_named_inputs(self):
        endpoint = _endpoint(
            {
                "time": {"type": "text", "from_payload": True, "payload_key": "time", "required": True},
                "days": {"type": "days", "from_payload": True, "payload_key": "days"},
            }
        )

        variables, _ = resolve_inputs(endpoint, '{"time":"06:15","days":"mo,fr"}')

        self.assertEqual(variables["time"], "06:15")
        self.assertEqual(variables["days"], "2,6")

    def test_single_from_payload_input_still_receives_plain_text(self):
        endpoint = _endpoint(
            {
                "view": {"type": "text", "from_payload": True, "required": True},
            }
        )

        variables, _ = resolve_inputs(endpoint, "kitchen")

        self.assertEqual(variables["view"], "kitchen")


if __name__ == "__main__":
    unittest.main()
