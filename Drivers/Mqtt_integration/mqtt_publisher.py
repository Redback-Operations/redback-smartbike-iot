import paho.mqtt.client as mqtt
import logging

# Configure logging
logging.basicConfig(filename='mqtt_publisher.log', level=logging.INFO,
                    format='%(asctime)s - %(levelname)s - %(message)s')

# MQTT settings
MQTT_BROKER = "broker_host"
MQTT_PORT = 1883
MQTT_TOPIC = "bike/000001/workout"

def on_connect(client, userdata, flags, rc):
    """Callback when the client connects to the MQTT broker."""
    logging.info(f"Connected to MQTT Broker with result code {rc}")

def publish_workout_command(command):
    """Publish a workout command to the MQTT broker."""
    client = mqtt.Client()
    client.on_connect = on_connect
    try:
        client.connect(MQTT_BROKER, MQTT_PORT, 60)
        client.loop_start()
        logging.info(f"Publishing command: {command}")
        result = client.publish(MQTT_TOPIC, command)
        result.wait_for_publish()
        logging.info(f"Command published successfully: {command}")
    except Exception as e:
        logging.error(f"Failed to publish command: {e}")
    finally:
        client.loop_stop()
        client.disconnect()

if __name__ == "__main__":
    # Example usage
    # Replace with actual command or integrate with app's button press event
    publish_workout_command("Ramped")
