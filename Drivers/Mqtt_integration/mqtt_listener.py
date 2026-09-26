#!/usr/bin/env python3
"""
MQTT Listener for Workout Control - Smart Bike VR (Redback Operations)

Subscribes to bike/<device_id>/workout and launches the matching workout
script. Publishes the outcome of every command to bike/<device_id>/workout/status
so the calling application (game / mobile app) knows whether it succeeded.

Usage:
    python listener.py --device_id 000001 --mqtt_host localhost --dry-run -v

Requires:
    pip install paho-mqtt
"""

import argparse
import json
import logging
import os
import signal
import subprocess
import sys
import threading
import time

import paho.mqtt.client as mqtt


# --------------------------------------------------------------------------
# Error codes published to the status topic.
# Agree these with the game / mobile teams before they are treated as final.
# --------------------------------------------------------------------------
CODE_OK = "0000"
CODE_UNKNOWN_WORKOUT = "E1001"
CODE_EMPTY_COMMAND = "E1002"
CODE_SCRIPT_NOT_FOUND = "E1003"
CODE_LAUNCH_FAILED = "E1004"
CODE_STOP_FAILED = "E1005"
CODE_NOTHING_RUNNING = "E1006"

# Workout name -> script path, relative to --root_dir.
# Add new workouts here; no other code needs to change.
WORKOUTS = {
    "ramped": os.path.join("Driver", "start_ramped_workout.py"),
    "ftp": os.path.join("Driver", "start_ftp_workout.py"),
}

log = logging.getLogger("workout_listener")


# --------------------------------------------------------------------------
# Argument parsing
# --------------------------------------------------------------------------
def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description="MQTT Listener for Workout Control",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    parser.add_argument("--device_id", type=str, default=os.getenv("DEVICE_ID"),
                        help="Unique ID of the bike, used to form MQTT topics")
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
    parser.add_argument("--root_dir", type=str, default=os.getenv("ROOT_DIR", "/home/pi"),
                        help="Root directory where workout scripts are located")
    parser.add_argument("--qos", type=int, choices=[0, 1, 2], default=1,
                        help="QoS level for subscribe and status publishes")
    parser.add_argument("--dry-run", action="store_true",
                        help="Log what would be launched without starting any process. "
                             "Useful for testing off the Raspberry Pi.")
    parser.add_argument("-v", "--verbose", action="store_true",
                        help="Enable DEBUG logging (per-message detail)")
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


# --------------------------------------------------------------------------
# Listener
# --------------------------------------------------------------------------
class WorkoutListener:
    def __init__(self, args):
        self.args = args
        self.workout_topic = f"bike/{args.device_id}/workout"
        self.status_topic = f"bike/{args.device_id}/workout/status"

        self.current_workout = None      # name, e.g. "ramped"
        self.current_proc = None         # subprocess.Popen handle
        self._lock = threading.Lock()    # on_message may be re-entered
        self._stopping = False

        self.client = make_client(client_id=f"workout-listener-{args.device_id}")
        if args.mqtt_user:
            self.client.username_pw_set(args.mqtt_user, args.mqtt_password)
        self.client.on_connect = self.on_connect
        self.client.on_disconnect = self.on_disconnect
        self.client.on_message = self.on_message

    # -- status reporting --------------------------------------------------
    def publish_status(self, code, message, workout=None):
        payload = {
            "code": code,
            "message": message,
            "workout": workout,
            "timestamp": time.time(),
        }
        log_fn = log.info if code == CODE_OK else log.error
        log_fn("%s: %s", code, message)
        try:
            self.client.publish(self.status_topic, json.dumps(payload), qos=self.args.qos)
        except Exception as exc:  # never let status reporting kill the listener
            log.error("Failed to publish status: %s", exc)

    # -- MQTT callbacks ----------------------------------------------------
    # Signature covers both paho 1.x (client, userdata, flags, rc) and
    # 2.x (client, userdata, flags, reason_code, properties).
    def on_connect(self, client, userdata, flags, rc, properties=None):
        if rc != 0:
            log.error("Connection to broker refused (code %s: %s). "
                      "Check host, port and credentials.", rc, rc_text(rc))
            return
        log.info("Connected to broker at %s:%s", self.args.mqtt_host, self.args.mqtt_port)
        client.subscribe(self.workout_topic, qos=self.args.qos)
        log.info("Subscribed to %s", self.workout_topic)
        log.info("Publishing status to %s", self.status_topic)
        log.info("Known workouts: %s, stop", ", ".join(sorted(WORKOUTS)))

    # 1.x passes (client, userdata, rc); 2.x passes
    # (client, userdata, flags, reason_code, properties).
    def on_disconnect(self, client, userdata, rc_or_flags, reason_code=None, properties=None):
        rc = reason_code if reason_code is not None else rc_or_flags
        if rc != 0 and not self._stopping:
            log.warning("Unexpected disconnect (code %s). Reconnecting...", rc)

    def on_message(self, client, userdata, msg):
        try:
            command = msg.payload.decode("utf-8", errors="replace").strip().lower()
        except Exception as exc:
            self.publish_status(CODE_EMPTY_COMMAND, f"Could not decode payload: {exc}")
            return

        log.debug("Message received on %s: %r", msg.topic, command)

        if not command:
            self.publish_status(CODE_EMPTY_COMMAND, "Received an empty command")
            return

        with self._lock:
            if command == "stop":
                self.handle_stop()
            elif command in WORKOUTS:
                self.handle_start(command)
            else:
                self.publish_status(
                    CODE_UNKNOWN_WORKOUT,
                    f"Unknown workout type '{command}'. "
                    f"Valid values: {', '.join(sorted(WORKOUTS))}, stop",
                    workout=command,
                )

    # -- workout control ---------------------------------------------------
    def workout_is_running(self):
        if self.args.dry_run:
            # No real process in dry-run mode, so track state by name only.
            return self.current_workout is not None
        return self.current_proc is not None and self.current_proc.poll() is None

    def terminate_current(self):
        """Stop the running workout. Returns True if something was stopped."""
        if self.args.dry_run:
            if self.current_workout:
                log.info("[dry-run] Would terminate workout: %s", self.current_workout)
            self.current_workout = None
            self.current_proc = None
            return True

        if not self.workout_is_running():
            self.current_proc = None
            self.current_workout = None
            return True

        name = self.current_workout
        log.info("Terminating current workout: %s", name)
        try:
            self.current_proc.terminate()
            try:
                self.current_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                log.warning("Workout '%s' did not exit in time; killing it.", name)
                self.current_proc.kill()
                self.current_proc.wait(timeout=5)
        except Exception as exc:
            self.publish_status(CODE_STOP_FAILED,
                                f"Failed to stop workout '{name}': {exc}", workout=name)
            return False
        finally:
            self.current_proc = None
            self.current_workout = None
        return True

    def handle_stop(self):
        if not self.workout_is_running():
            self.publish_status(CODE_NOTHING_RUNNING, "No workout is currently running")
            return
        name = self.current_workout
        if self.terminate_current():
            self.publish_status(CODE_OK, f"Workout '{name}' stopped", workout=name)

    def handle_start(self, workout_type):
        if self.workout_is_running():
            log.info("Workout already running: %s", self.current_workout)
            if not self.terminate_current():
                return

        script_path = os.path.join(self.args.root_dir, WORKOUTS[workout_type])

        if self.args.dry_run:
            self.current_workout = workout_type
            self.current_proc = None
            self.publish_status(CODE_OK,
                                f"[dry-run] Would start '{workout_type}' -> {script_path}",
                                workout=workout_type)
            return

        if not os.path.isfile(script_path):
            self.publish_status(CODE_SCRIPT_NOT_FOUND,
                                f"Workout script not found: {script_path}",
                                workout=workout_type)
            return

        try:
            # sys.executable avoids relying on the script being chmod +x with a shebang.
            self.current_proc = subprocess.Popen([sys.executable, script_path])
            self.current_workout = workout_type
        except Exception as exc:
            self.current_proc = None
            self.current_workout = None
            self.publish_status(CODE_LAUNCH_FAILED,
                                f"Failed to launch '{workout_type}': {exc}",
                                workout=workout_type)
            return

        self.publish_status(CODE_OK,
                            f"Workout '{workout_type}' started (pid {self.current_proc.pid})",
                            workout=workout_type)

    # -- lifecycle ---------------------------------------------------------
    def run(self):
        try:
            self.client.connect(self.args.mqtt_host, self.args.mqtt_port, keepalive=60)
        except Exception as exc:
            log.error("Could not connect to broker at %s:%s - %s",
                      self.args.mqtt_host, self.args.mqtt_port, exc)
            return 1

        try:
            self.client.loop_forever()
        except KeyboardInterrupt:
            log.info("Interrupted by user.")
        finally:
            self.shutdown()
        return 0

    def shutdown(self, *_):
        if self._stopping:
            return
        self._stopping = True
        log.info("Shutting down...")
        with self._lock:
            self.terminate_current()
        try:
            self.client.disconnect()
        except Exception:
            pass


# --------------------------------------------------------------------------
def main(argv=None):
    args = parse_args(argv)
    configure_logging(args.verbose)

    if not args.device_id:
        log.error("device_id is required. Pass --device_id or set the DEVICE_ID "
                  "environment variable.")
        return 2

    listener = WorkoutListener(args)
    signal.signal(signal.SIGINT, lambda *a: listener.shutdown())
    if hasattr(signal, "SIGTERM"):
        signal.signal(signal.SIGTERM, lambda *a: listener.shutdown())

    return listener.run()


if __name__ == "__main__":
    sys.exit(main())
