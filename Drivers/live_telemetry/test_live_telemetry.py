
import unittest
import json

from live_telemetry import convert_telemetry


class TestLiveTelemetry(unittest.TestCase):

    def create_payload(self, value):
        return json.dumps({
            "value": value,
            "timestamp": 1795580000.123
        })

    def test_speed_conversion(self):
        topic, payload = convert_telemetry(
            "bike/01/speed",
            self.create_payload(5.4)
        )

        self.assertEqual(topic, "/bike/01/speed")
        self.assertEqual(json.loads(payload), {
            "ts": 1795580000,
            "speed": 5.4
        })

    def test_cadence_conversion(self):
        topic, payload = convert_telemetry(
            "bike/01/cadence",
            self.create_payload(85)
        )

        self.assertEqual(topic, "/bike/01/cadence")
        self.assertEqual(json.loads(payload), {
            "ts": 1795580000,
            "cadence": 85
        })

    def test_zero_measurement(self):
        topic, payload = convert_telemetry(
            "bike/01/speed",
            self.create_payload(0)
        )

        self.assertEqual(json.loads(payload)["speed"], 0)

    def test_negative_measurement(self):
        with self.assertRaises(ValueError):
            convert_telemetry(
                "bike/01/speed",
                self.create_payload(-5)
            )

    def test_invalid_measurement(self):
        with self.assertRaises(ValueError):
            convert_telemetry(
                "bike/01/cadence",
                self.create_payload("invalid")
            )

    def test_unsupported_topic(self):
        with self.assertRaises(ValueError):
            convert_telemetry(
                "bike/01/power",
                self.create_payload(150)
            )

    def test_invalid_json(self):
        with self.assertRaises(ValueError):
            convert_telemetry(
                "bike/01/speed",
                "invalid json"
            )

    def test_missing_timestamp(self):
        with self.assertRaises(ValueError):
            convert_telemetry(
                "bike/01/speed",
                json.dumps({"value": 5.4})
            )


if __name__ == "__main__":
    unittest.main()
