import os
import sys
import subprocess

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from Drivers.lib.mqtt_client import MQTTClient  # noqa: E402

BIKE_ID = os.getenv("DEVICE_ID") or os.getenv("BIKEID", "000001")
MQTT_TOPIC = f"bike/{BIKE_ID}/startWorkout"

WORKOUT_SCRIPTS = {
    "Ramped": "start_ramped_workout.py",
    "Interval": "start_interval_workout.py",
    "Steady": "start_steady_workout.py"
}

def on_connect(client, userdata, flags, rc, properties=None):
    """Callback for when the client connects to the broker."""
    if rc == 0:
        print("Connected to MQTT broker")
        client.subscribe(MQTT_TOPIC)
        print(f"Subscribed to topic: {MQTT_TOPIC}")
    else:
        print(f"Connection failed with code {rc}")

def on_message(client, userdata, msg):
    """Callback for when a message is received."""
    payload = msg.payload.decode()
    print(f"Message received: {payload}")

    if payload in WORKOUT_SCRIPTS:
        script = WORKOUT_SCRIPTS[payload]
        try:
            print(f"Starting workout script: {script}")
            subprocess.run(["python3", script], check=True)
        except Exception as e:
            print(f"Error running script {script}: {e}")
    else:
        print(f"Unrecognized payload: {payload}")

def main():
    # Broker host/port/login come from .env (MQTT_HOSTNAME, MQTT_PORT, ...)
    mqtt_client = MQTTClient.from_env()
    mqtt_client.on_connect = on_connect
    mqtt_client.on_message = on_message

    try:
        mqtt_client.setup_mqtt_client()
        client = mqtt_client.get_client()
    except Exception as e:
        print(f"Failed to connect to MQTT broker: {e}")
        return
    
    client.loop_forever()

if __name__ == "__main__":
    main()
