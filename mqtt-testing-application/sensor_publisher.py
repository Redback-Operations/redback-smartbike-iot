#!/usr/bin/env python3
"""Publish safe sample SmartBike telemetry for Unity Week 5 testing."""

import argparse
import json
import time

import paho.mqtt.client as mqtt


def arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Publish sample SmartBike sensor data.")
    parser.add_argument("--host", default="test.mosquitto.org")
    parser.add_argument("--port", type=int, default=1883)
    parser.add_argument("--device-id", default="000001")
    parser.add_argument("--speed", type=float, default=6.5, help="Metres per second")
    parser.add_argument("--cadence", type=float, default=82.0, help="Revolutions per minute")
    parser.add_argument("--distance", type=float, default=125.4, help="Metres")
    parser.add_argument("--username", default="")
    parser.add_argument("--password", default="")
    return parser.parse_args()


def payload(value: float, unit: str) -> str:
    return json.dumps(
        {
            "value": value,
            "unitName": unit,
            "timestamp": time.time(),
            "metadata": {"deviceName": "week5-test-publisher"},
        }
    )


def main() -> None:
    args = arguments()
    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    if args.username:
        client.username_pw_set(args.username, args.password)
    client.connect(args.host, args.port, keepalive=60)
    client.loop_start()

    messages = (
        (f"bike/{args.device_id}/speed", payload(args.speed, "m/s")),
        (f"bike/{args.device_id}/cadence", payload(args.cadence, "rpm")),
        (f"bike/{args.device_id}/distance", payload(args.distance, "m")),
    )
    try:
        for topic, message in messages:
            result = client.publish(topic, message, qos=1)
            result.wait_for_publish()
            print(f"PUBLISHED topic={topic} payload={message}", flush=True)
    finally:
        client.loop_stop()
        client.disconnect()


if __name__ == "__main__":
    main()
