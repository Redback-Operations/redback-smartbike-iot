# Ramped Workout

The ramped workout gradually increases the SmartBike resistance over a configurable number of intervals.

## Requirements

The following environment variables must be configured:

- `DEVICE_ID` – SmartBike device identifier
- `MQTT_HOSTNAME` – MQTT broker address
- `MQTT_PORT` – MQTT broker port
- `MQTT_USERNAME` – MQTT username, if required
- `MQTT_PASSWORD` – MQTT password, if required

Resistance commands are published to:

```text
bike/{DEVICE_ID}/resistance/control