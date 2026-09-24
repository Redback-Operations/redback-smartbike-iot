#!/usr/bin/env python3
"""
MQTT Publisher for Workout Control - Smart Bike VR (Redback Operations)

Publishes a workout command to bike/<device_id>/workout and optionally waits
for the listener's reply on bike/<device_id>/workout/status.

Usage:
    python mqtt_publisher.py ramped --device_id 000001 --mqtt_host localhost --wait -v
    python mqtt_publisher.py stop   --device_id 000001

Requires:
    pip install paho-mqtt
"""

import argparse
import json
import logging
import os
import sys
import threading

import paho.mqtt.client as mqtt


# Must stay in sync with WORKOUTS in listener.py
VALID_COMMANDS = ["ramped", "ftp", "stop"]

log = logging.getLogger("workout_publisher")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="Publish a workout command to the Smart Bike MQTT broker",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("command", nargs="?", default="ramped",
                        help=f"Workout command to send. One of: {', '.join(VALID_COMMANDS)}")
    parser.add_argument("--device_id", type=str, default=os.getenv("DEVICE_ID", "000001"),
                        help="Unique ID of the bike")
    parser.add_argument("--mqtt_host", type=str,
                        default=os.getenv("MQTT_HOST", "localhost"),
                        help="MQTT broker host address")
    parser.add_argument("--mqtt_port", type=int,
                        default=int(os.getenv("MQTT_PORT", "1883")),
                        help="MQTT broker port")
    parser.add_argument("--mqtt_user", type=str, default=os.getenv("MQTT_USER"),
                        help="MQTT username (omit if the broker is open)")
    parser.add_argument("--mqtt_password", type=str, default=os.getenv("MQTT_PASSWORD"),
                        help="MQTT password")
    parser.add_argument("--qos", type=int, choices=[0, 1, 2], default=1,
                        help="QoS level for the publish")
    parser.add_argument("--wait", action="store_true",
                        help="Wait for the listener's reply on the status topic")
    parser.add_argument("--timeout", type=float, default=10.0,
                        help="Seconds to wait for connection and for the status reply")
    parser.add_argument("--force", action="store_true",
                        help="Send the command even if it is not in VALID_COMMANDS "
                             "(useful for testing the listener's error handling)")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Enable DEBUG logging")
    return parser.parse_args(argv)


def configure_logging(verbose):
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )


def make_client(client_id=None):
    """Create an MQTT client that works on both paho-mqtt 1.x and 2.x."""
    try:
        from paho.mqtt.enums import CallbackAPIVersion  # paho-mqtt >= 2.0
        return mqtt.Client(CallbackAPIVersion.VERSION2, client_id=client_id)
    except ImportError:
        return mqtt.Client(client_id=client_id)  # paho-mqtt 1.x


def rc_text(rc):
    """Human-readable connect result, for both int (1.x) and ReasonCode (2.x)."""
    try:
        return mqtt.connack_string(rc)
    except Exception:
        return str(rc)


class WorkoutPublisher:
    """Holds one connection so repeated publishes do not reconnect every time."""

    def __init__(self, args):
        self.args = args
        self.workout_topic = f"bike/{args.device_id}/workout"
        self.status_topic = f"bike/{args.device_id}/workout/status"

        self._connected = threading.Event()
        self._status_received = threading.Event()
        self._connect_rc = None

        self.client = make_client(client_id=f"workout-publisher-{args.device_id}")
        if args.mqtt_user:
            self.client.username_pw_set(args.mqtt_user, args.mqtt_password)
        self.client.on_connect = self._on_connect
        self.client.on_message = self._on_message

    # Signature covers both paho 1.x (client, userdata, flags, rc) and
    # 2.x (client, userdata, flags, reason_code, properties).
    def _on_connect(self, client, userdata, flags, rc, properties=None):
        self._connect_rc = rc
        if rc == 0:
            log.info("Connected to broker at %s:%s",
                     self.args.mqtt_host, self.args.mqtt_port)
            if self.args.wait:
                client.subscribe(self.status_topic, qos=self.args.qos)
                log.debug("Subscribed to %s", self.status_topic)
        else:
            log.error("Connection refused (code %s: %s)", rc, rc_text(rc))
        self._connected.set()

    def _on_message(self, client, userdata, msg):
        raw = msg.payload.decode("utf-8", errors="replace")
        try:
            data = json.loads(raw)
            code = data.get("code", "?")
            message = data.get("message", "")
            if code == "0000":
                log.info("Listener replied OK: %s", message)
            else:
                log.error("Listener replied with error %s: %s", code, message)
        except json.JSONDecodeError:
            log.info("Listener replied: %s", raw)
        self._status_received.set()

    def connect(self):
        """Connect and block until CONNACK. Returns True on success."""
        try:
            self.client.connect(self.args.mqtt_host, self.args.mqtt_port, keepalive=60)
        except Exception as exc:
            log.error("Could not reach broker at %s:%s - %s",
                      self.args.mqtt_host, self.args.mqtt_port, exc)
            return False

        self.client.loop_start()
        if not self._connected.wait(timeout=self.args.timeout):
            log.error("Timed out waiting for the broker to acknowledge the connection.")
            return False
        return self._connect_rc == 0

    def publish(self, command):
        """Publish one command. Returns True if the broker acknowledged it."""
        log.info("Publishing '%s' to %s", command, self.workout_topic)
        try:
            result = self.client.publish(self.workout_topic, command, qos=self.args.qos)
            # At QoS 0 this returns as soon as the bytes hit the socket, which is
            # why QoS 1 is the default here - it waits for a real broker ack.
            result.wait_for_publish(timeout=self.args.timeout)
        except Exception as exc:
            log.error("Failed to publish command: %s", exc)
            return False

        if result.rc != mqtt.MQTT_ERR_SUCCESS:
            log.error("Publish failed with code %s", result.rc)
            return False

        log.info("Command published successfully: %s", command)
        return True

    def wait_for_status(self):
        """Wait for the listener to reply on the status topic."""
        log.debug("Waiting up to %.1fs for a reply on %s",
                  self.args.timeout, self.status_topic)
        if not self._status_received.wait(timeout=self.args.timeout):
            log.warning("No reply received on %s. Is the listener running?",
                        self.status_topic)
            return False
        return True

    def close(self):
        try:
            self.client.loop_stop()
            self.client.disconnect()
        except Exception:
            pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()
        return False


def main(argv=None):
    args = parse_args(argv)
    configure_logging(args.verbose)

    command = args.command.strip().lower()
    if command not in VALID_COMMANDS and not args.force:
        log.error("Unknown command '%s'. Valid commands: %s (use --force to send anyway)",
                  command, ", ".join(VALID_COMMANDS))
        return 2

    with WorkoutPublisher(args) as publisher:
        if not publisher.connect():
            return 1
        if not publisher.publish(command):
            return 1
        if args.wait and not publisher.wait_for_status():
            return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
