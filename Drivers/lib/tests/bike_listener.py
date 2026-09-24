#!/usr/bin/env python3
"""
Reference listener demonstrating error-code based error raising.

Usage:
    python3 bike_listener.py --device_id 000001 --mqtt_host localhost -v
    python3 bike_listener.py --device_id 000001 --mqtt_host localhost --clamp
"""

import argparse
import json
import logging
import os
import signal
import sys

import paho.mqtt.client as mqtt

from error_codes import Code, validate_value, is_success
from bike_status import (publish_status, publish_device_status,
                         register_last_will, status_topic)

log = logging.getLogger("bike_listener")

NUMERIC_CONTROLS = ("incline", "resistance", "fan")
WORKOUT_CONTROL = "workout"

#: Domain configuration rather than an error concept - belongs in
#: lib/constants.py alongside the value ranges when integrated.
WORKOUTS = ("ramped", "ftp", "stop")


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        description="Bike command listener with error-code status reporting",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    p.add_argument("--device_id", default=os.getenv("DEVICE_ID", "000001"))
    p.add_argument("--mqtt_host", default=os.getenv("MQTT_HOST", "localhost"))
    p.add_argument("--mqtt_port", type=int,
                   default=int(os.getenv("MQTT_PORT", "1883")))
    p.add_argument("--mqtt_user", default=os.getenv("MQTT_USER"))
    p.add_argument("--mqtt_password", default=os.getenv("MQTT_PASSWORD"))
    p.add_argument("--clamp", action="store_true",
                   help="Adjust out-of-range values to the nearest permitted "
                        "bound and report VALUE_CLAMPED, instead of rejecting "
                        "them with VALUE_OUT_OF_RANGE")
    p.add_argument("-v", "--verbose", action="store_true")
    return p.parse_args(argv)


def make_client(client_id=None):
    """Works on both paho-mqtt 1.x and 2.x."""
    try:
        from paho.mqtt.enums import CallbackAPIVersion
        return mqtt.Client(CallbackAPIVersion.VERSION2, client_id=client_id)
    except ImportError:
        return mqtt.Client(client_id=client_id)


class BikeListener:
    def __init__(self, args):
        self.args = args
        self.device_id = args.device_id
        self.base = f"bike/{self.device_id}"
        self.command_topics = [f"{self.base}/{c}"
                               for c in NUMERIC_CONTROLS + (WORKOUT_CONTROL,)]
        self._shutting_down = False

        self.client = make_client(client_id=f"bike-listener-{self.device_id}")
        if args.mqtt_user:
            self.client.username_pw_set(args.mqtt_user, args.mqtt_password)

        # Must be registered BEFORE connect().
        register_last_will(self.client, self.device_id)

        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message

    # -- callbacks ---------------------------------------------------------
    def on_connect(self, client, userdata, flags, rc, properties=None):
        if rc != 0:
            log.error("Connection refused (%s)", rc)
            return
        log.info("Connected to %s:%s", self.args.mqtt_host, self.args.mqtt_port)
        for topic in self.command_topics:
            client.subscribe(topic, qos=1)
            log.info("Subscribed to %s  ->  %s", topic, status_topic(topic))
        log.info("Out-of-range values will be %s",
                 "clamped" if self.args.clamp else "rejected")

        publish_device_status(client, self.device_id, Code.OK,
                              "Bike online and accepting commands")
        log.info("Published OK to %s/status (retained)", self.base)

    def on_message(self, client, userdata, msg):
        topic = msg.topic
        control = topic.rsplit("/", 1)[-1]
        raw = msg.payload.decode("utf-8", errors="replace").strip()
        log.debug("RX %s  %r", topic, raw)

        if control == WORKOUT_CONTROL:
            self.handle_workout(topic, raw)
        elif control in NUMERIC_CONTROLS:
            self.handle_numeric(topic, control, raw)
        else:
            self.reply(topic, Code.CONTROL_NOT_CONFIGURED)

    # -- handlers ----------------------------------------------------------
    def handle_workout(self, topic, raw):
        value = raw
        if raw.startswith("{"):
            try:
                value = json.loads(raw).get("value", "")
            except json.JSONDecodeError:
                return self.reply(topic, Code.MALFORMED_PAYLOAD)

        value = str(value).lower()
        if not value:
            return self.reply(topic, Code.MISSING_FIELD)
        if value not in WORKOUTS:
            return self.reply(
                topic, Code.UNKNOWN_COMMAND,
                f"Unknown workout '{value}'. Valid: {', '.join(WORKOUTS)}",
                value=value)

        self.reply(topic, Code.OK, f"Workout '{value}' accepted", value=value)

    def handle_numeric(self, topic, control, raw):
        # Accept {"value": n}, the legacy {"<control>": n}, or a bare number.
        if raw.startswith("{"):
            try:
                data = json.loads(raw)
            except json.JSONDecodeError:
                return self.reply(topic, Code.MALFORMED_PAYLOAD)
            if "value" in data:
                value = data["value"]
            elif control in data:
                value = data[control]
            else:
                return self.reply(
                    topic, Code.MISSING_FIELD,
                    f"Payload must contain 'value' (or '{control}')")
        elif not raw:
            return self.reply(topic, Code.MISSING_FIELD, "Empty payload")
        else:
            value = raw

        code, message, applied = validate_value(control, value,
                                                clamp=self.args.clamp)
        self.reply(topic, code, message,
                   value=applied if applied is not None else value)

    def reply(self, topic, code, message=None, value=None):
        payload = publish_status(self.client, topic, code, message, value)
        (log.info if is_success(code) else log.error)(
            "%s -> %s %s (%s)", topic, payload["code"], payload["name"],
            payload["message"])

    # -- lifecycle ---------------------------------------------------------
    def run(self):
        try:
            self.client.connect(self.args.mqtt_host, self.args.mqtt_port, 60)
        except Exception as exc:
            log.error("Could not connect: %s", exc)
            return 1
        try:
            self.client.loop_forever()
        except KeyboardInterrupt:
            log.info("Interrupted.")
            self.shutdown()
        return 0

    def shutdown(self):
            # wait=True matters here: publishing is asynchronous, and without
            # it the message can still be queued when disconnect() runs. The
            # broker would then fire the Last Will and report a crash instead.
            publish_device_status(self.client, self.device_id,
                                  Code.BIKE_SHUTDOWN, "Bike shut down cleanly",
                                  wait=True)
            self.client.disconnect()


def main(argv=None):
    args = parse_args(argv)
    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s", datefmt="%H:%M:%S")

    listener = BikeListener(args)

    def _handle_signal(*_):
        listener.shutdown()
        sys.exit(0)

    signal.signal(signal.SIGINT, _handle_signal)
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, _handle_signal)

    return listener.run()


if __name__ == "__main__":
    sys.exit(main())