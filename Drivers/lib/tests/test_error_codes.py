#!/usr/bin/env python3
"""
End-to-end test: publishes commands to a running bike_listener.py and checks
the status reply carries the expected code.

    # terminal 1
    python3 bike_listener.py --device_id 000001 --mqtt_host localhost
    # terminal 2
    python3 test_error_codes.py --device_id 000001 --mqtt_host localhost
"""

import argparse
import json
import os
import sys
import threading
import time

import paho.mqtt.client as mqtt

from error_codes import Code

#: (description, control topic suffix, payload, expected code)
CASES = [
    ("Valid incline",              "incline",    '{"value": 5}',      Code.OK),
    ("Valid resistance",           "resistance", '{"value": 40}',     Code.OK),
    ("Legacy incline key",         "incline",    '{"incline": 7}',    Code.OK),
    ("Bare numeric value",         "fan",        '50',                Code.OK),
    ("Incline above maximum",      "incline",    '{"value": 100}',    Code.VALUE_OUT_OF_RANGE),
    ("Resistance below minimum",   "resistance", '{"value": -5}',     Code.VALUE_OUT_OF_RANGE),
    ("Non-numeric value",          "incline",    '{"value": "high"}', Code.VALUE_WRONG_TYPE),
    ("Malformed JSON",             "incline",    '{"value": ',        Code.MALFORMED_PAYLOAD),
    ("Missing field",              "resistance", '{"amount": 30}',    Code.MISSING_FIELD),
    ("Valid workout",              "workout",    'ramped',            Code.OK),
    ("Valid workout (mixed case)", "workout",    'FTP',               Code.OK),
    ("Unknown workout",            "workout",    'sprint',            Code.UNKNOWN_COMMAND),
]


def make_client(client_id=None):
    try:
        from paho.mqtt.enums import CallbackAPIVersion
        return mqtt.Client(CallbackAPIVersion.VERSION2, client_id=client_id)
    except ImportError:
        return mqtt.Client(client_id=client_id)


def parse_args(argv=None):
    p = argparse.ArgumentParser(description="Test the bike error code scheme")
    p.add_argument("--device_id", default=os.getenv("DEVICE_ID", "000001"))
    p.add_argument("--mqtt_host", default=os.getenv("MQTT_HOST", "localhost"))
    p.add_argument("--mqtt_port", type=int,
                   default=int(os.getenv("MQTT_PORT", "1883")))
    p.add_argument("--mqtt_user", default=os.getenv("MQTT_USER"))
    p.add_argument("--mqtt_password", default=os.getenv("MQTT_PASSWORD"))
    p.add_argument("--clamp", action="store_true",
                   help="Expect VALUE_CLAMPED instead of VALUE_OUT_OF_RANGE "
                        "(use when the listener is running with --clamp)")
    p.add_argument("--timeout", type=float, default=5.0)
    return p.parse_args(argv)


class Tester:
    def __init__(self, args):
        self.args = args
        self.base = f"bike/{args.device_id}"
        self.connected = threading.Event()
        self.reply = None
        self.reply_ready = threading.Event()

        self.client = make_client(client_id=f"errcode-test-{args.device_id}")
        if args.mqtt_user:
            self.client.username_pw_set(args.mqtt_user, args.mqtt_password)
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message

    def _on_connect(self, client, userdata, flags, rc, properties=None):
        if rc == 0:
            client.subscribe(f"{self.base}/+/status", qos=1)
        self.connected.set()

    def _on_message(self, client, userdata, msg):
        try:
            self.reply = json.loads(msg.payload.decode())
        except json.JSONDecodeError:
            self.reply = {"code": None, "message": msg.payload.decode()}
        self.reply_ready.set()

    def connect(self):
        self.client.connect(self.args.mqtt_host, self.args.mqtt_port, 60)
        self.client.loop_start()
        return self.connected.wait(timeout=self.args.timeout)

    def run_case(self, control, payload):
        self.reply = None
        self.reply_ready.clear()
        self.client.publish(f"{self.base}/{control}", payload, qos=1)
        if not self.reply_ready.wait(timeout=self.args.timeout):
            return None
        return self.reply

    def close(self):
        self.client.loop_stop()
        self.client.disconnect()


def main(argv=None):
    args = parse_args(argv)
    tester = Tester(args)

    if not tester.connect():
        print(f"Could not connect to broker at "
              f"{args.mqtt_host}:{args.mqtt_port}")
        return 1

    print(f"\nTesting against {tester.base}"
          f"{'  (expecting clamped values)' if args.clamp else ''}\n")
    print(f"{'Scenario':<30}{'Expected':<10}{'Actual':<10}{'Result'}")
    print("-" * 62)

    passed = failed = 0
    for description, control, payload, expected in CASES:
        if args.clamp and expected == Code.VALUE_OUT_OF_RANGE:
            expected = Code.VALUE_CLAMPED
        time.sleep(0.15)
        reply = tester.run_case(control, payload)
        actual = reply["code"] if reply else "no reply"
        ok = reply is not None and actual == int(expected)
        print(f"{description:<30}{int(expected):<10}{str(actual):<10}"
              f"{'PASS' if ok else 'FAIL'}")
        passed, failed = (passed + 1, failed) if ok else (passed, failed + 1)

    print("-" * 62)
    print(f"{passed} passed, {failed} failed\n")

    tester.close()
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())