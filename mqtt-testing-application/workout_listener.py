#!/usr/bin/env python3
"""Safe MQTT listener for validating Unity workout commands.

Unlike the production Raspberry Pi listener, this script only prints received
commands and never starts or stops workout processes.
"""

import argparse
import sys

import paho.mqtt.client as mqtt


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Listen for SmartBike workout commands without controlling hardware."
    )
    parser.add_argument("--host", default="test.mosquitto.org")
    parser.add_argument("--port", type=int, default=1883)
    parser.add_argument("--device-id", default="000001")
    parser.add_argument("--username", default="")
    parser.add_argument("--password", default="")
    return parser.parse_args()


def main() -> int:
    args = parse_arguments()
    topic = f"bike/{args.device_id}/workout"

    def on_connect(client, userdata, flags, reason_code, properties):
        if reason_code != 0:
            print(f"Connection rejected: {reason_code}", flush=True)
            return
        client.subscribe(topic, qos=1)
        print(f"CONNECTED: {args.host}:{args.port}", flush=True)
        print(f"LISTENING: {topic}", flush=True)
        print("Return to Unity and send Ramped or FTP. Press Ctrl+C to stop.", flush=True)

    def on_message(client, userdata, message):
        payload = message.payload.decode("utf-8", errors="replace")
        valid = payload.lower() in {"ramped", "ftp"}
        result = "VALID" if valid else "UNKNOWN"
        print(
            f"RECEIVED [{result}] topic={message.topic} payload={payload}",
            flush=True,
        )

    client = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    if args.username:
        client.username_pw_set(args.username, args.password)
    client.on_connect = on_connect
    client.on_message = on_message

    try:
        client.connect(args.host, args.port, keepalive=60)
        client.loop_forever()
    except KeyboardInterrupt:
        print("\nListener stopped.")
        return 0
    except Exception as exception:
        print(f"ERROR: {exception}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
