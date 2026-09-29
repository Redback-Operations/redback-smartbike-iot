#!/usr/bin/env python3

import argparse
import json
import os
import sys
import time

import paho.mqtt.client as mqtt

# Load variables from a .env file when python-dotenv is available.



def parse_arguments():
    """Read threshold workout settings from command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Run an FTP-based threshold cycling workout."
    )

    parser.add_argument(
        "--intervals",
        type=int,
        default=3,
        help="Number of threshold intervals. Default: 3",
    )

    parser.add_argument(
        "--work-duration",
        type=int,
        default=480,
        help="Length of each threshold interval in seconds. Default: 480",
    )

    parser.add_argument(
        "--recovery-duration",
        type=int,
        default=240,
        help="Length of each recovery period in seconds. Default: 240",
    )

    parser.add_argument(
        "--intensity-percent",
        type=float,
        default=95.0,
        help="Threshold intensity as a percentage of FTP. Default: 95",
    )

    parser.add_argument(
        "--recovery-percent",
        type=float,
        default=55.0,
        help="Recovery intensity as a percentage of FTP. Default: 55",
    )

    parser.add_argument(
        "--work-resistance",
        type=int,
        default=50,
        help="Bike resistance during threshold intervals, from 0 to 100. Default: 50",
    )

    parser.add_argument(
        "--recovery-resistance",
        type=int,
        default=20,
        help="Bike resistance during recovery, from 0 to 100. Default: 20",
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
        "--ftp",
        type=float,
        default=None,
        help="Optional FTP override in watts. Otherwise the FTP environment variable is used.",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Display the workout without connecting to MQTT.",
    )

    return parser.parse_args()


def get_ftp(cli_ftp):
    """Read FTP from the command line or Raspberry Pi environment."""
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
    """Validate workout durations, intensities and resistance values."""
    if args.intervals <= 0:
        raise ValueError("Intervals must be greater than zero.")

    if args.work_duration <= 0:
        raise ValueError("Work duration must be greater than zero.")

    if args.recovery_duration < 0:
        raise ValueError("Recovery duration cannot be negative.")

    if args.warmup_duration < 0 or args.cooldown_duration < 0:
        raise ValueError("Warm-up and cool-down durations cannot be negative.")

    if not 80 <= args.intensity_percent <= 110:
        raise ValueError(
            "Threshold intensity should be between 80% and 110% of FTP."
        )

    if not 0 < args.recovery_percent < args.intensity_percent:
        raise ValueError(
            "Recovery percentage must be greater than zero and "
            "lower than the threshold intensity."
        )

    resistance_values = {
        "work resistance": args.work_resistance,
        "recovery resistance": args.recovery_resistance,
        "warm-up resistance": args.warmup_resistance,
    }

    for name, value in resistance_values.items():
        if not 0 <= value <= 100:
            raise ValueError(f"{name.capitalize()} must be between 0 and 100.")


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
    dry_run=False,
):
    """Publish a SmartBike resistance command with FTP metadata."""
    payload_data = {
        "resistance": resistance,
        "target_power_watts": round(target_power, 1),
        "ftp_percent": ftp_percent,
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
    """Run warm-up, threshold intervals, recoveries and cool-down."""
    threshold_power = ftp * (args.intensity_percent / 100)
    recovery_power = ftp * (args.recovery_percent / 100)

    print("\nStarting threshold workout")
    print(f"FTP: {ftp:.1f} W")
    print(
        f"Threshold target: {threshold_power:.1f} W "
        f"({args.intensity_percent:.1f}% FTP)"
    )
    print(
        f"Recovery target: {recovery_power:.1f} W "
        f"({args.recovery_percent:.1f}% FTP)"
    )
    print(f"Intervals: {args.intervals}\n")

    if args.warmup_duration > 0:
        print("Warm-up")
        publish_resistance(
            client,
            topic,
            args.warmup_resistance,
            recovery_power,
            args.recovery_percent,
            args.dry_run,
        )
        wait_for_stage(args.warmup_duration, args.dry_run)

    for interval_number in range(1, args.intervals + 1):
        print(f"\nThreshold interval {interval_number}/{args.intervals}")

        publish_resistance(
            client,
            topic,
            args.work_resistance,
            threshold_power,
            args.intensity_percent,
            args.dry_run,
        )
        wait_for_stage(args.work_duration, args.dry_run)

        if interval_number < args.intervals and args.recovery_duration > 0:
            print(f"Recovery {interval_number}/{args.intervals - 1}")

            publish_resistance(
                client,
                topic,
                args.recovery_resistance,
                recovery_power,
                args.recovery_percent,
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
            args.dry_run,
        )
        wait_for_stage(args.cooldown_duration, args.dry_run)

    print("\nThreshold workout completed.")


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

    # Enable TLS for secure HiveMQ connections on port 8883.
    if broker_port == 8883:
        client.tls_set()
        print("HiveMQ TLS enabled")

    try:
        print(f"Connecting to MQTT broker: {broker_address}:{broker_port}")
        client.connect(broker_address, broker_port, 60)
        client.loop_start()
        time.sleep(1)

        run_workout(client, resistance_topic, args, ftp)

    except KeyboardInterrupt:
        print("\nThreshold workout stopped by the user.")

    except Exception as error:
        print(f"\nThreshold workout failed: {error}")
        sys.exit(1)

    finally:
        try:
            publish_resistance(
                client,
                resistance_topic,
                args.recovery_resistance,
                ftp * (args.recovery_percent / 100),
                args.recovery_percent,
            )
            time.sleep(1)
        except Exception as error:
            print(f"Could not apply recovery resistance: {error}")

        client.loop_stop()
        client.disconnect()
        print("Disconnected from MQTT broker.")


if __name__ == "__main__":
    main()