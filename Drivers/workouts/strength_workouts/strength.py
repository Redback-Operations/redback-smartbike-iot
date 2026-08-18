#!/usr/bin/env python3

 

import argparse

import json

import os

import sys

import time

 

import paho.mqtt.client as mqtt

 

 

def parse_arguments():

    """Read endurance workout settings from command-line arguments."""

    parser = argparse.ArgumentParser(

        description="Run a steady FTP-based endurance cycling workout."

    )

 

    parser.add_argument(

        "--duration",

        type=int,

        default=1800,

        help="Duration of the main endurance stage in seconds. Default: 1800",

    )

 

    parser.add_argument(

        "--intensity-percent",

        type=float,

        default=70.0,

        help="Endurance intensity as a percentage of FTP. Default: 70",

    )

 

    parser.add_argument(

        "--endurance-resistance",

        type=int,

        default=35,

        help="Resistance during the endurance stage, from 0 to 100. Default: 35",

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

        "--recovery-percent",

        type=float,

        default=50.0,

        help="Warm-up and cool-down intensity as FTP percentage. Default: 50",

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

    """Validate workout duration, intensity and resistance values."""

    if args.duration <= 0:

        raise ValueError("Endurance duration must be greater than zero.")

 

    if args.warmup_duration < 0:

        raise ValueError("Warm-up duration cannot be negative.")

 

    if args.cooldown_duration < 0:

        raise ValueError("Cool-down duration cannot be negative.")

 

    if not 55 <= args.intensity_percent <= 85:

        raise ValueError(

            "Endurance intensity should be between 55% and 85% of FTP."

        )

 

    if not 0 < args.recovery_percent < args.intensity_percent:

        raise ValueError(

            "Recovery percentage must be greater than zero and "

            "lower than the endurance intensity."

        )

 

    resistance_values = {

        "endurance resistance": args.endurance_resistance,

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

    stage,

    dry_run=False,

):

    """Publish a SmartBike resistance command with workout metadata."""

    payload_data = {

        "resistance": resistance,

        "target_power_watts": round(target_power, 1),

        "ftp_percent": ftp_percent,

        "workout": "endurance",

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

        f"({ftp_percent:.1f}% FTP)"

    )

 

 

def wait_for_stage(duration, dry_run):

    """Wait for a workout stage to finish."""

    if dry_run:

        print(f"[DRY RUN] Would wait {duration} seconds.")

    else:

        time.sleep(duration)

 

 

def run_workout(client, topic, args, ftp):

    """Run the endurance warm-up, main stage and cool-down."""

    endurance_power = ftp * (args.intensity_percent / 100)

    recovery_power = ftp * (args.recovery_percent / 100)

 

    print("\nStarting endurance workout")

    print(f"FTP: {ftp:.1f} W")

    print(

        f"Endurance target: {endurance_power:.1f} W "

        f"({args.intensity_percent:.1f}% FTP)"

    )

    print(f"Main duration: {args.duration} seconds\n")

 

    if args.warmup_duration > 0:

        print("Warm-up")

 

        publish_resistance(

            client,

            topic,

            args.warmup_resistance,

            recovery_power,

            args.recovery_percent,

            "warmup",

            args.dry_run,

        )

 

        wait_for_stage(args.warmup_duration, args.dry_run)

 

    print("\nEndurance stage")

 

    publish_resistance(

        client,

        topic,

        args.endurance_resistance,

        endurance_power,

        args.intensity_percent,

        "endurance",

        args.dry_run,

    )

 

    wait_for_stage(args.duration, args.dry_run)

 

    if args.cooldown_duration > 0:

        print("\nCool-down")

 

        publish_resistance(

            client,

            topic,

            args.warmup_resistance,

            recovery_power,

            args.recovery_percent,

            "cooldown",

            args.dry_run,

        )

 

        wait_for_stage(args.cooldown_duration, args.dry_run)

 

    print("\nEndurance workout completed.")

 

 

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

        print("\nEndurance workout stopped by the user.")

 

    except Exception as error:

        print(f"\nEndurance workout failed: {error}")

        sys.exit(1)

 

    finally:

        try:

            recovery_power = ftp * (args.recovery_percent / 100)

 

            publish_resistance(

                client,

                resistance_topic,

                args.warmup_resistance,

                recovery_power,

                args.recovery_percent,

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
