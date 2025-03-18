

import sys
import os
root_folder = os.path.abspath(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(root_folder)
from app_config import MQTT, TOPICS
from Drivers.lib.constants import *
from Drivers.lib.mqtt_client import *
import logging 

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = logging.StreamHandler(sys.stdout)
handler.setLevel(logging.INFO)
formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
handler.setFormatter(formatter)
logger.addHandler(handler)

def message(client, userdata, msg):
    logger.info("Received " + msg.topic + " " + str(msg.qos) + " " + str(msg.payload))

def main():
    try:
        mqtt_client = MQTTClient(broker_address=MQTT['HOST'], username=MQTT['USER'], password=MQTT['PASSWORD'], port=MQTT['PORT'])
        mqtt_client.setup_mqtt_client()
        for topics in TOPICS:
            mqtt_client.subscribe(TOPICS[topics])
            logger.info(f"Subscribed to {TOPICS[topics]}")
        mqtt_client.get_client().on_message = message
        mqtt_client.loop_forever()

    except KeyboardInterrupt:
        print("Exiting...")
        sys.exit(0)

if __name__ == '__main__':
    main()