
#!/usr/bin/env python3

"""
Live Speed and Cadence MQTT Bridge

Receives standard SmartBike telemetry and converts it
into the legacy Unity-compatible MQTT format.
"""

import os
import sys
import logging
import argparse

root_folder = os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))
)

sys.path.append(root_folder)

from lib.mqtt_client import MQTTClient
from live_telemetry import convert_telemetry


logger = logging.getLogger(__name__)


class LiveTelemetryBridge(MQTTClient):

    def __init__(
        self,
        broker_address,
        username,
        password,
        device_id,
        port=8883,
        dry_run=True
    ):
        super().__init__(
            broker_address,
            username,
            password,
            port
        )

        self.device_id = device_id
        self.dry_run = dry_run

        self.speed_topic = f"bike/{device_id}/speed"
        self.cadence_topic = f"bike/{device_id}/cadence"

    def on_connect(
        self, client, userdata, flags, rc, properties=None
    ):
        if rc != 0:
            logger.error("MQTT connection failed: %s", rc)
            return

        logger.info("Connected to MQTT broker")

        self.subscribe(self.speed_topic)
        self.subscribe(self.cadence_topic)

        logger.info("Subscribed to %s", self.speed_topic)
        logger.info("Subscribed to %s", self.cadence_topic)

    def on_message(self, client, userdata, msg):

        if msg.topic not in (
            self.speed_topic,
            self.cadence_topic
        ):
            return

        try:
            topic, payload = convert_telemetry(
                msg.topic,
                msg.payload
            )

        except (ValueError, TypeError, OverflowError) as error:
            logger.warning(
                "Invalid telemetry received: %s",
                error
            )
            return

        if self.dry_run:
            logger.info(
                "[DRY RUN] %s: %s",
                topic,
                payload
            )
        else:
            self.publish(topic, payload)

            logger.info(
                "Telemetry published: %s: %s",
                topic,
                payload
            )


def main():

    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s:%(name)s:%(message)s"
    )

    parser = argparse.ArgumentParser(
        description="Live speed and cadence MQTT bridge"
    )

    parser.add_argument(
        "--broker",
        default=os.getenv("MQTT_HOSTNAME")
    )

    parser.add_argument(
        "--port",
        type=int,
        default=8883
    )

    parser.add_argument(
        "--device-id",
        default=os.getenv("DEVICE_ID")
    )

    parser.add_argument(
        "--publish",
        action="store_true",
        help="Enable publishing of converted telemetry"
    )

    args = parser.parse_args()

    if not args.broker or not args.device_id:
        parser.error("Broker and device ID are required")

    bridge = LiveTelemetryBridge(
        broker_address=args.broker,
        username=os.getenv("MQTT_USERNAME"),
        password=os.getenv("MQTT_PASSWORD"),
        device_id=args.device_id,
        port=args.port,
        dry_run=not args.publish
    )

    try:
        bridge.setup_mqtt_client()
        bridge.loop_forever()

    except KeyboardInterrupt:
        logger.info("Stopping telemetry bridge")

    finally:
        if bridge.get_client() is not None:
            bridge.get_client().disconnect()


if __name__ == "__main__":
    main()
