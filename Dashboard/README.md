# Redback SmartBike Dashboard

The Dashboard is the web interface for monitoring and controlling the SmartBike. It receives live data through MQTT and provides controls for the trainer, climb, fan, workouts, steering, and brakes.

## Requirements

- Python 3.9 or newer
- A running MQTT broker
- SmartBike device services publishing data to MQTT

## Install


On Linux or Raspberry Pi, use:

```bash
cd Dashboard
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
```

## Configure MQTT

Create a `.env` file in the repository root, or set these values in the environment:

```dotenv
MQTT_HOSTNAME=
MQTT_PORT=1883
MQTT_USERNAME=
MQTT_PASSWORD=
MQTT_USE_TLS=false
DEVICE_ID=000001
```

Use port `8883` and `MQTT_USE_TLS=true` when the broker requires TLS. Keep passwords out of Git.

## Run

From the repository root:

```bash
python Dashboard/run.py --host 0.0.0.0 --port 8080
```

Open `http://localhost:8080`. From another device, use `http://<PI_IP>:8080`.



To use a different broker or bike:

```bash
python Dashboard/run.py --broker 192.168.1.100 --broker_port 1883 --device 000002
```

## Basic Check

Run the dashboard's MQTT parsing check from the repository root:

```bash
python Dashboard/tests/test_dashboard.py
```

The dashboard is live-device only. It needs a reachable MQTT broker and active SmartBike services to display telemetry.
