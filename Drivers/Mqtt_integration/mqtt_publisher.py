import os
import sys
import logging

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from lib.mqtt_client import MQTTClient  # noqa: E402

# Configure logging
logging.basicConfig(filename='mqtt_publisher.log', level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')

# Broker host/port/login come from .env (MQTT_HOSTNAME, MQTT_PORT, MQTT_USERNAME, MQTT_PASSWORD)
MQTT_TOPIC = f"bike/{os.getenv('DEVICE_ID', '000001')}/workout"

def publish_workout_command(command):
    """Publish a workout command to the MQTT broker."""
    mqtt_client = MQTTClient.from_env()
    client = None
    try:
        mqtt_client.setup_mqtt_client()
        client = mqtt_client.get_client()
        client.loop_start()
        logging.info(f"Publishing command: {command}")
        result = client.publish(MQTT_TOPIC, command, qos=1)
        result.wait_for_publish()
        logging.info(f"Command published successfully: {command}")
    except Exception as e:
        logging.error(f"Failed to publish command: {e}")
    finally:
        if client:
            client.loop_stop()
            client.disconnect()

if __name__ == "__main__":
    # Example usage
    # Replace with actual command or integrate with app's button press event
    publish_workout_command("Ramped")
