
import json
import unittest

from types import SimpleNamespace
from unittest.mock import patch

from mqtt_bridge import LiveTelemetryBridge


class TestMQTTBridge(unittest.TestCase):

    def setUp(self):
        self.bridge = LiveTelemetryBridge(
            broker_address="localhost",
            username=None,
            password=None,
            device_id="01",
            dry_run=True
        )

    def create_message(self, topic, value):
        return SimpleNamespace(
            topic=topic,
            payload=json.dumps({
                "value": value,
                "timestamp": 1795580000.123
            }).encode("utf-8")
        )

    def test_successful_connection(self):
        with patch.object(self.bridge, "subscribe") as subscribe:
            self.bridge.on_connect(None, None, {}, 0)

            self.assertEqual(subscribe.call_count, 2)

            subscribe.assert_any_call("bike/01/speed")
            subscribe.assert_any_call("bike/01/cadence")

    def test_failed_connection(self):
        with patch.object(self.bridge, "subscribe") as subscribe:
            self.bridge.on_connect(None, None, {}, 1)

            subscribe.assert_not_called()

    def test_dry_run(self):
        message = self.create_message(
            "bike/01/speed", 5.4
        )

        with patch.object(self.bridge, "publish") as publish:
            self.bridge.on_message(None, None, message)

            publish.assert_not_called()

    def test_speed_publishing(self):
        self.bridge.dry_run = False

        message = self.create_message(
            "bike/01/speed", 5.4
        )

        with patch.object(self.bridge, "publish") as publish:
            self.bridge.on_message(None, None, message)

            publish.assert_called_once()

            topic, payload = publish.call_args.args

            self.assertEqual(topic, "/bike/01/speed")
            self.assertEqual(json.loads(payload), {
                "ts": 1795580000,
                "speed": 5.4
            })

    def test_cadence_publishing(self):
        self.bridge.dry_run = False

        message = self.create_message(
            "bike/01/cadence", 85
        )

        with patch.object(self.bridge, "publish") as publish:
            self.bridge.on_message(None, None, message)

            publish.assert_called_once()

            topic, payload = publish.call_args.args

            self.assertEqual(topic, "/bike/01/cadence")
            self.assertEqual(json.loads(payload), {
                "ts": 1795580000,
                "cadence": 85
            })

    def test_invalid_measurement(self):
        self.bridge.dry_run = False

        message = self.create_message(
            "bike/01/speed", -5
        )

        with patch.object(self.bridge, "publish") as publish:
            self.bridge.on_message(None, None, message)

            publish.assert_not_called()

    def test_unrelated_topic(self):
        self.bridge.dry_run = False

        message = self.create_message(
            "bike/01/power", 150
        )

        with patch.object(self.bridge, "publish") as publish:
            self.bridge.on_message(None, None, message)

            publish.assert_not_called()

    def test_different_bike(self):
        self.bridge.dry_run = False

        message = self.create_message(
            "bike/02/speed", 5.4
        )

        with patch.object(self.bridge, "publish") as publish:
            self.bridge.on_message(None, None, message)

            publish.assert_not_called()


if __name__ == "__main__":
    unittest.main()
