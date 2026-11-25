import sys
import os
import time
import json

root_folder = os.path.abspath(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(root_folder)

from Drivers.lib.constants import *
from Drivers.lib.mqtt_client import *

"""
To use:
    - Define topics you want to subscribe to on SUBSCRIBED_TOPICS
      *This will clog up the control interface but it will still work
    - Add/modify any control methods for control topics that are not already present
    - Set the MQTT_* values in .env
    - Run
    - Enter the corrosponding numbers to select control methods
    - Input values to send to control topics
"""

# ========= USER SETTINGS =========

# MQTT credentials come from .env (MQTT_HOSTNAME, MQTT_PORT, MQTT_USERNAME, MQTT_PASSWORD)

# Smartbike ID
DEVICE_ID = os.getenv('DEVICE_ID', '000001')

# Testing Controls
SUBSCRIBED_TOPICS = [] # use '#' for all topics

# ===============================

# write topics
INCLINE_TOPIC = BIKE_01_INCLINE_COMMAND
RESISTANCE_TOPIC = BIKE_01_RESISTANCE_COMMAND
FAN_TOPIC = f'bike/{DEVICE_ID}/fan/control'

# read topics
BIKE_01_INCLINE_REPORT = 'bike/000001/incline/control'
BIKE_01_RESISTANCE_REPORT = 'bike/000001/resistance/report'
BIKE_01_SPEED_REPORT = 'bike/000001/speed'
BIKE_01_CADENCE_REPORT = 'bike/000001/cadence'
BIKE_01_POWER_REPORT = 'bike/000001/power'
BIKE_01_BUTTON_REPORT = 'bike/000001/button/report'

# Workout selector
WORKOUT_SELECTOR_TOPIC = "bike/000001/workout"

class MQTT_Controller:
    def __init__(self):
        self.client = MQTTClient.from_env()
        self.client.setup_mqtt_client()
        self.feedback()
        self._control_loop()

    def publish_incline(self,val):
        payload = json.dumps({"incline" : val, "timestamp": time.time()})
        self.client.publish(INCLINE_TOPIC,payload)

    def publish_resistance(self,val):
        payload = json.dumps({"resistance" : val, "timestamp": time.time()})
        self.client.publish(RESISTANCE_TOPIC,payload)

    def publish_fan(self,val):
        payload = json.dumps({"value" : val, "timestamp": time.time()})
        self.client.publish(FAN_TOPIC,payload)
    
    def publish_workout_selector(self,val):
        self.client.publish(WORKOUT_SELECTOR_TOPIC,val)

    def _control_input(self):
        time.sleep(0.8)
        command = int(input('=====Select Topic=====\n\t1. Incline\n\t2. Resistance\n\t3. Fan\n\t4. Workout Selector\nINPUT = '))
        match command:
            case 1: 
                val = float(input('Value: '))
                self.publish_incline(val)
            case 2:
                val = float(input('Value: '))
                self.publish_resistance(val)
            case 3:
                val = float(input('Value: '))
                self.publish_fan(val)
            case 4:
                val = input('Value: ')
                self.publish_workout_selector(val)
            case _:
                self._control_input()
        time.sleep(0.5)

    def _control_loop(self):
        try:
            while True:
                self.client.loop_start()
                self._control_input()
        except KeyboardInterrupt:
            print('\nControl Loop Terminated.')

    def feedback(self):
        subscribe_topics = SUBSCRIBED_TOPICS
        for topic in subscribe_topics:
            self.client.subscribe(topic)

def main():
    controller = MQTT_Controller()

if __name__ == '__main__':
    main()