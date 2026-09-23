#!/usr/bin/env python3

import argparse
import json
import os
import sys
import time

import paho.mqtt.client as mqtt


def parse_arguments():
    """Read configurable workout values from the command line."""
    parser = argparse.ArgumentParser(
        description="Run a progressive ramped cycling workout."
    )

    parser.add_argument(
        "--start-resistance",
        type=int,
        default=20,
        help="Starting resistance level from 0 to 100. Default: 20",
    )

    parser.add_argument(
        "--increment",
        type=int,
        default=5,
        help="Resistance increase after each interval. Default: 5",
    )

    parser.add_argument(
        "--interval-duration",
        type=int,
        default=180,
        help="Length of each interval in seconds. Default: 180",
    )

    parser.add_argument(
        "--intervals",
        type=int,
        default=6,
        help="Number of ramp intervals. Default: 6",
    )

    parser.add_argument(
        "--recovery-resistance",
        type=int,
        default=10,
        help="Resistance applied when the workout finishes. Default: 10",
    )

    return parser.parse_args()


def validate_arguments(args):
    """Check that all workout arguments are safe and valid."""
    if not 0 <= args.start_resistance <= 100:
        raise ValueError("Start resistance must be between 0 and 100.")

    if args.increment <= 0:
        raise ValueError("Increment must be greater than 0.")

    if args.interval_duration <= 0:
        raise ValueError("Interval duration must be greater than 0 seconds.")

    if args.intervals <= 0:
        raise ValueError("Number of intervals must be greater than 0.")

    if not 0 <= args.recovery_resistance <= 100:
        raise ValueError("Recovery resistance must be between 0 and 100.")

    final_resistance = (
        args.start_resistance
        + (args.intervals - 1) * args.increment
    )

    if final_resistance > 100:
        raise ValueError(
            f"The workout would reach resistance {final_resistance}. "
            "Reduce the start resistance, increment, or number of intervals."
        )


def create_mqtt_client():
    """Create an MQTT client compatible with different Paho versions."""
    try:
        return mqtt.Client(
            callback_api_version=mqtt.CallbackAPIVersion.VERSION2
        )
    except AttributeError:
        return mqtt.Client()


def publish_resistance(client, topic, resistance):
    """Publish a resistance command to the SmartBike controller."""
    payload = json.dumps({"resistance": resistance})

    result = client.publish(topic, payload)
    result.wait_for_publish()

    if result.rc != mqtt.MQTT_ERR_SUCCESS:
        raise RuntimeError(
            f"Failed to publish resistance command. MQTT code: {result.rc}"
        )

    print(f"Resistance set to {resistance}")


def run_workout(client, topic, args):
    """Run each interval and progressively increase resistance."""
    print("\nStarting ramped workout")
    print(f"Intervals: {args.intervals}")
    print(f"Interval duration: {args.interval_duration} seconds")
    print(f"Starting resistance: {args.start_resistance}")
    print(f"Resistance increment: {args.increment}\n")

    for interval_number in range(1, args.intervals + 1):
        resistance = (
            args.start_resistance
            + (interval_number - 1) * args.increment
        )

        print(
            f"Interval {interval_number}/{args.intervals}: "
            f"resistance {resistance}"
        )

        publish_resistance(client, topic, resistance)
        time.sleep(args.interval_duration)

    print("\nRamped workout completed.")


def main():
    args = parse_arguments()

    try:
        validate_arguments(args)
    except ValueError as error:
        print(f"Invalid workout configuration: {error}")
        sys.exit(1)

    device_id = os.getenv("DEVICE_ID")
    broker_address = os.getenv("MQTT_HOSTNAME")
    username = os.getenv("MQTT_USERNAME")
    password = os.getenv("MQTT_PASSWORD")

    try:
        broker_port = int(os.getenv("MQTT_PORT", "1883"))
    except ValueError:
        print("MQTT_PORT must contain a valid integer.")
        sys.exit(1)

    if not device_id:
        print("Missing DEVICE_ID environment variable.")
        sys.exit(1)

    if not broker_address:
        print("Missing MQTT_HOSTNAME environment variable.")
        sys.exit(1)

    resistance_topic = f"bike/{device_id}/resistance/control"

    client = create_mqtt_client()

    if username:
        client.username_pw_set(username, password)

    try:
        print(f"Connecting to MQTT broker: {broker_address}:{broker_port}")
        client.connect(broker_address, broker_port, 60)
        client.loop_start()

        # Allow the MQTT client time to establish its connection.
        time.sleep(1)

        run_workout(client, resistance_topic, args)

    except KeyboardInterrupt:
        print("\nWorkout stopped by the user.")

    except Exception as error:
        print(f"\nWorkout failed: {error}")
        sys.exit(1)

    finally:
        try:
            print(
                f"Setting recovery resistance to "
                f"{args.recovery_resistance}"
            )
            publish_resistance(
                client,
                resistance_topic,
                args.recovery_resistance,
            )
            time.sleep(1)
        except Exception as error:
            print(f"Could not set recovery resistance: {error}")

        client.loop_stop()
        client.disconnect()
        print("Disconnected from MQTT broker.")


if __name__ == "__main__":
    main()