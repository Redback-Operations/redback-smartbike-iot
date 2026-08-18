#!/usr/bin/env python3

 

import argparse

import json

import os

import sys

import time

 

import paho.mqtt.client as mqtt

 

 

def parse_arguments():

    """Read strength workout settings from command-line arguments."""

    parser = argparse.ArgumentParser(

        description="Run a high-resistance FTP-based cycling strength workout."

    )

 

    parser.add_argument(

        "--intervals",

        type=int,

        default=6,

        help="Number of strength intervals. Default: 6",

    )

 

    parser.add_argument(

        "--work-duration",

        type=int,

        default=120,

        help="Length of each strength interval in seconds. Default: 120",

    )

 

    parser.add_argument(

        "--recovery-duration",

        type=int,

        default=180,

        help="Length of each recovery period in seconds. Default: 180",

    )

 

    parser.add_argument(

        "--intensity-percent",

        type=float,

        default=85.0,

        help="Strength interval intensity as FTP percentage. Default: 85",

    )

 

    parser.add_argument(

        "--recovery-percent",

        type=float,

        default=50.0,

        help="Recovery intensity as FTP percentage. Default: 50",

    )

 

    parser.add_argument(

        "--work-resistance",

        type=int,

        default=70,

        help="Resistance during strength intervals, from 0 to 100. Default: 70",

    )

 

    parser.add_argument(

        "--recovery-resistance",

        type=int,

        default=20,

        help="Resistance during recovery periods, from 0 to 100. Default: 20",

    )

 

    parser.add_argument(

        "--warmup-duration",

        type=int,

        default=300,

        help="Warm-up duration in seconds. Default: 300",

    )

 

    parser.add_argument(

        "--cooldown-duration",

        type=int,

        default=300,

        help="Cool-down duration in seconds. Default: 300",

    )

 

    parser.add_argument(

        "--warmup-resistance",

        type=int,

        default=15,

        help="Resistance during warm-up and cool-down. Default: 15",

    )

 

    parser.add_argument(

        "--target-cadence",

        type=int,

        default=60,

        help="Suggested cadence during strength intervals in RPM. Default: 60",

    )

 

    parser.add_argument(

        "--ftp",

        type=float,

        default=None,

        help="Optional FTP override in watts. Otherwise FTP is read from the environment.",

    )

 

    parser.add_argument(

        "--dry-run",

        action="store_true",

        help="Display the workout without connecting to MQTT.",

    )

 

    return parser.parse_args()

 

 

def get_ftp(cli_ftp):

    """Read FTP from the command line or environment."""

    if cli_ftp is not None:

        ftp = cli_ftp

    else:

        ftp_value = os.getenv("FTP")

 

        if not ftp_value:

            raise ValueError(

                "FTP was not provided. Add FTP to the Pi .env file "

                "or use --ftp."

            )

 

        try:

            ftp = float(ftp_value)

        except ValueError as error:

            raise ValueError("FTP must be a valid number.") from error

 

    if ftp <= 0:

        raise ValueError("FTP must be greater than zero.")

 

    return ftp

 

 

def validate_arguments(args):

    """Validate strength workout settings."""

    if args.intervals <= 0:

        raise ValueError("Intervals must be greater than zero.")

 

    if args.work_duration <= 0:

        raise ValueError("Work duration must be greater than zero.")

 

    if args.recovery_duration < 0:

        raise ValueError("Recovery duration cannot be negative.")

 

    if args.warmup_duration < 0:

        raise ValueError("Warm-up duration cannot be negative.")

 

    if args.cooldown_duration < 0:

        raise ValueError("Cool-down duration cannot be negative.")

 

    if not 60 <= args.intensity_percent <= 110:

        raise ValueError(

            "Strength intensity should be between 60% and 110% of FTP."

        )

 

    if not 0 < args.recovery_percent < args.intensity_percent:

        raise ValueError(

            "Recovery percentage must be greater than zero and "

            "lower than the strength intensity."

        )

 

    if not 30 <= args.target_cadence <= 120:

        raise ValueError(

            "Target cadence must be between 30 and 120 RPM."

        )

 

    resistance_values = {

        "work resistance": args.work_resistance,

        "recovery resistance": args.recovery_resistance,

        "warm-up resistance": args.warmup_resistance,

    }

 

    for name, value in resistance_values.items():

        if not 0 <= value <= 100:

            raise ValueError(

                f"{name.capitalize()} must be between 0 and 100."

            )

 

 

def create_mqtt_client():

    """Create an MQTT client compatible with different Paho versions."""

    try:

        return mqtt.Client(

            callback_api_version=mqtt.CallbackAPIVersion.VERSION2

        )

    except (AttributeError, TypeError):

        return mqtt.Client()

 

 

def publish_resistance(

    client,

    topic,

    resistance,

    target_power,

    ftp_percent,

    target_cadence,

    stage,

    dry_run=False,

):

    """Publish a SmartBike resistance command with strength metadata."""

    payload_data = {

        "resistance": resistance,

        "target_power_watts": round(target_power, 1),

        "ftp_percent": ftp_percent,

        "target_cadence_rpm": target_cadence,

        "workout": "strength",

        "stage": stage,

    }

 

    payload = json.dumps(payload_data)

 

    if dry_run:

        print(f"[DRY RUN] Topic: {topic}")

        print(f"[DRY RUN] Payload: {payload}")

        return

 

    result = client.publish(topic, payload)

    result.wait_for_publish()

 

    if result.rc != mqtt.MQTT_ERR_SUCCESS:

        raise RuntimeError(

            f"Failed to publish resistance command. MQTT code: {result.rc}"

        )

 

    print(

        f"Resistance: {resistance} | "

        f"Target power: {target_power:.1f} W "

        f"({ftp_percent:.1f}% FTP) | "

        f"Target cadence: {target_cadence} RPM"

    )

 

 

def wait_for_stage(duration, dry_run):

    """Wait for a workout stage to finish."""

    if dry_run:

        print(f"[DRY RUN] Would wait {duration} seconds.")

    else:

        time.sleep(duration)

 

 

def run_workout(client, topic, args, ftp):

    """Run warm-up, strength intervals, recoveries and cool-down."""

    strength_power = ftp * (args.intensity_percent / 100)

    recovery_power = ftp * (args.recovery_percent / 100)

 

    print("\nStarting strength workout")

    print(f"FTP: {ftp:.1f} W")

    print(

        f"Strength target: {strength_power:.1f} W "

        f"({args.intensity_percent:.1f}% FTP)"

    )

    print(f"Target cadence: {args.target_cadence} RPM")

    print(f"Intervals: {args.intervals}\n")

 

    if args.warmup_duration > 0:

        print("Warm-up")

 

        publish_resistance(

            client,

            topic,

            args.warmup_resistance,

            recovery_power,

            args.recovery_percent,

            80,

            "warmup",

            args.dry_run,

        )

 

        wait_for_stage(args.warmup_duration, args.dry_run)

 

    for interval_number in range(1, args.intervals + 1):

        print(

            f"\nStrength interval "

            f"{interval_number}/{args.intervals}"

        )

 

        publish_resistance(

            client,

            topic,

            args.work_resistance,

            strength_power,

            args.intensity_percent,

            args.target_cadence,

            "strength",

            args.dry_run,

        )

 

        wait_for_stage(args.work_duration, args.dry_run)

 

        if interval_number < args.intervals and args.recovery_duration > 0:

            print(

                f"Recovery "

                f"{interval_number}/{args.intervals - 1}"

            )

 

            publish_resistance(

                client,

                topic,

                args.recovery_resistance,

                recovery_power,

                args.recovery_percent,

                80,

                "recovery",

                args.dry_run,

            )

 

            wait_for_stage(args.recovery_duration, args.dry_run)

 

    if args.cooldown_duration > 0:

        print("\nCool-down")

 

        publish_resistance(

            client,

            topic,

            args.warmup_resistance,

            recovery_power,

            args.recovery_percent,

            80,

            "cooldown",

            args.dry_run,

        )

 

        wait_for_stage(args.cooldown_duration, args.dry_run)

 

    print("\nStrength workout completed.")

 

 

def main():

    args = parse_arguments()

 

    try:

        validate_arguments(args)

        ftp = get_ftp(args.ftp)

    except ValueError as error:

        print(f"Invalid workout configuration: {error}")

        sys.exit(1)

 

    device_id = os.getenv("DEVICE_ID", "000001")

    resistance_topic = f"bike/{device_id}/resistance/control"

 

    if args.dry_run:

        run_workout(None, resistance_topic, args, ftp)

        return

 

    broker_address = os.getenv("MQTT_HOSTNAME")

    username = os.getenv("MQTT_USERNAME")

    password = os.getenv("MQTT_PASSWORD")

 

    try:

        broker_port = int(os.getenv("MQTT_PORT", "1883"))

    except ValueError:

        print("MQTT_PORT must contain a valid integer.")

        sys.exit(1)

 

    if not broker_address:

        print("Missing MQTT_HOSTNAME environment variable.")

        sys.exit(1)

 

    client = create_mqtt_client()

 

    if username:

        client.username_pw_set(username, password)

 

    try:

        print(f"Connecting to MQTT broker: {broker_address}:{broker_port}")

        client.connect(broker_address, broker_port, 60)

        client.loop_start()

        time.sleep(1)

 

        run_workout(client, resistance_topic, args, ftp)

 

    except KeyboardInterrupt:

        print("\nStrength workout stopped by the user.")

 

    except Exception as error:

        print(f"\nStrength workout failed: {error}")

        sys.exit(1)

 

    finally:

        try:

            recovery_power = ftp * (args.recovery_percent / 100)

 

            publish_resistance(

                client,

                resistance_topic,

                args.recovery_resistance,

                recovery_power,

                args.recovery_percent,

                80,

                "recovery",

            )

 

            time.sleep(1)

 

        except Exception as error:

            print(f"Could not apply recovery resistance: {error}")

 

        client.loop_stop()

        client.disconnect()

        print("Disconnected from MQTT broker.")

 

 

if __name__ == "__main__":

    main()