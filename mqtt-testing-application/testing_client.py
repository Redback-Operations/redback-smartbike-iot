import sys
import os
import time
import json

root_folder = os.path.abspath(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(root_folder)

from Drivers.lib.constants import *
from Drivers.lib.mqtt_client import *
from app_config import MQTT, TOPICS # Configure topics and MQTT credentials here
import logging

"""
To use:
    - Define topics you want to subscribe to on SUBSCRIBED_TOPICS
      *This will clog up the control interface but it will still work
    - Add/modify any control methods for control topics that are not already present
    - Add the MQTT credentials
    - Run
    - Enter the corrosponding numbers to select control methods
    - Input values to send to control topics
"""

# ========= USER SETTINGS =========

# MQTT credentials
MQTT_HOST = MQTT['HOST']
MQTT_USER = MQTT['USER']
MQTT_PASS = MQTT['PASSWORD']

# ===============================
def message(client, userdata, message): # Callback for when a message is received
    print(f"Received {message.topic} {str(message.payload)}")


class MQTT_Controller:
    def __init__(self):
        self.logger = logging.getLogger(__name__)
        self.client = MQTTClient(broker_address=MQTT_HOST,username=MQTT_USER,password=MQTT_PASS, port=MQTT['PORT'])
        self.client.setup_mqtt_client()
        for topics in TOPICS:
            self.client.subscribe(TOPICS[topics])
            logger.info(f"Subscribed to {TOPICS[topics]}")
        self.client.get_client().on_message = message
        self.client.get_client().loop_start()


    def publish(self, topic, val):
        payload = json.dumps({"value": val, "timestamp": time.time()})
        self.client.publish(topic, payload)
        self.logger.debug(f"Published {payload} to {topic}")


    def _control_input(self):
        time.sleep(0.8)
        try:
            command = int(input('=====Select Topic=====\n\t1. Incline\n\t2. Resistance\n\t3. Fan\n\t4. Workout Selector\n\t5. Speed\n\t6. Cadence\n\t7. Power\n\t8. Button\nINPUT = '))
        except ValueError:
            print("Invalid input. Please enter a number.")
            self._control_input()
            return
        topic_map = {
            1: TOPICS["BIKE_INCLINE_REPORT"],
            2: TOPICS["BIKE_RESISTANCE_REPORT"],
            3: TOPICS["FAN_CONTROL"],
            4: TOPICS["WORKOUT_SELECTOR_TOPIC"],
            5: TOPICS["BIKE_SPEED_REPORT"],
            6: TOPICS["BIKE_CADENCE_REPORT"],
            7: TOPICS["BIKE_POWER_REPORT"],
            8: TOPICS["BIKE_BUTTON_REPORT"]
        }
        if command in topic_map:
            val = input('Value: ').strip()
            self.publish(topic_map[command], val)
        else:
            self._control_input()
        time.sleep(0.5)

    def _control_loop(self):
        try:
            while True:
                self._control_input()
        except KeyboardInterrupt:
            print('\nControl Loop Terminated.')
            self.client.get_client().loop_stop()


def main():
    controller = MQTT_Controller()
    controller._control_loop()


if __name__ == '__main__':
    main()