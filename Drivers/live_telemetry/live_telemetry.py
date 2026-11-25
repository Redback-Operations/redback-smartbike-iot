
"""
Live Speed and Cadence Telemetry Integration

Converts standard SmartBike MQTT telemetry into a format
compatible with the legacy Unity telemetry interface.
"""

import json
import math


SUPPORTED_MEASUREMENTS = ("speed", "cadence")


def convert_telemetry(topic, payload):
    """
    Validate and convert a SmartBike telemetry message.

    Returns:
        tuple: Converted MQTT topic and JSON payload.

    Raises:
        ValueError: If the topic or measurement is invalid.
    """

    parts = topic.split("/")

    if len(parts) != 3 or parts[0] != "bike":
        raise ValueError("Invalid bike telemetry topic")

    device_id = parts[1]
    measurement = parts[2]

    if not device_id:
        raise ValueError("Missing bike device ID")

    if measurement not in SUPPORTED_MEASUREMENTS:
        raise ValueError("Unsupported telemetry measurement")

    data = json.loads(payload)

    if not isinstance(data, dict):
        raise ValueError("Telemetry payload must be a JSON object")

    value = data.get("value")
    timestamp = data.get("timestamp")

    if type(value) not in (int, float):
        raise ValueError("Measurement must be numeric")

    if not math.isfinite(value) or value < 0:
        raise ValueError("Invalid measurement value")

    if type(timestamp) not in (int, float):
        raise ValueError("Timestamp must be numeric")

    if not math.isfinite(timestamp) or timestamp <= 0:
        raise ValueError("Invalid timestamp")

    converted_topic = f"/bike/{device_id}/{measurement}"

    converted_payload = json.dumps({
        "ts": int(timestamp),
        measurement: value
    })

    return converted_topic, converted_payload


if __name__ == "__main__":
    sample_topic = "bike/01/speed"

    sample_payload = json.dumps({
        "value": 5.4,
        "unitName": "m/s",
        "timestamp": 1795580000.123,
        "metadata": {
            "deviceName": "test-bike"
        }
    })

    topic, payload = convert_telemetry(
        sample_topic,
        sample_payload
    )

    print("Converted topic:", topic)
    print("Converted payload:", payload)
