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
    - Add the MQTT credentials
    - Run
    - Enter the corresponding numbers to select control methods
    - Input values to send to control topics
"""

# ========= USER SETTINGS =========

# MQTT credentials
MQTT_HOST = ''
MQTT_USER = ''
MQTT_PASS = ''

# Smartbike ID
DEVICE_ID = '000001'

# Testing Controls
SUBSCRIBED_TOPICS = []  # use '#' for all topics

# ===============================

# Write topics dynamically for future flexibility
TOPICS = {
    "INCLINE": f'bike/{DEVICE_ID}/incline/control',
    "RESISTANCE": f'bike/{DEVICE_ID}/resistance/control',
    "FAN": f'bike/{DEVICE_ID}/fan/control',
    "WORKOUT_SELECTOR": f'bike/{DEVICE_ID}/workout',
}

# Read topics dynamically for future flexibility
READ_TOPICS = {
    "INCLINE_REPORT": f'bike/{DEVICE_ID}/incline/control',
    "RESISTANCE_REPORT": f'bike/{DEVICE_ID}/resistance/report',
    "SPEED_REPORT": f'bike/{DEVICE_ID}/speed',
    "CADENCE_REPORT": f'bike/{DEVICE_ID}/cadence',
    "POWER_REPORT": f'bike/{DEVICE_ID}/power',
    "BUTTON_REPORT": f'bike/{DEVICE_ID}/button/report',
}

class MQTT_Controller:
    def __init__(self):
        self.client = MQTTClient(broker_address=MQTT_HOST, username=MQTT_USER, password=MQTT_PASS)
        self.client.setup_mqtt_client()
        self.feedback()
        self._control_loop()

    def publish_message(self, topic, value):
        payload = json.dumps({"value": value, "timestamp": self.get_timestamp()})
        self.client.publish(topic, payload)

    def get_timestamp(self):
        return time.time()

    def publish_incline(self, val):
        self.publish_message(TOPICS["INCLINE"], val)

    def publish_resistance(self, val):
        self.publish_message(TOPICS["RESISTANCE"], val)

    def publish_fan(self, val):
        self.publish_message(TOPICS["FAN"], val)

    def publish_workout_selector(self, val):
        self.client.publish(TOPICS["WORKOUT_SELECTOR"], val)

    def _control_input(self):
        time.sleep(0.8)
        command = self.get_valid_input(
            '=====Select Topic=====\n\t1. Incline\n\t2. Resistance\n\t3. Fan\n\t4. Workout Selector\nINPUT = ',
            [1, 2, 3, 4]
        )
        if command == 1:
            val = self.get_valid_input('Incline Value: ', is_float=True)
            self.publish_incline(val)
        elif command == 2:
            val = self.get_valid_input('Resistance Value: ', is_float=True)
            self.publish_resistance(val)
        elif command == 3:
            val = self.get_valid_input('Fan Value: ', is_float=True)
            self.publish_fan(val)
        elif command == 4:
            val = input('Workout Selector Value: ')
            self.publish_workout_selector(val)
        time.sleep(0.5)

    def get_valid_input(self, prompt, valid_values=None, is_float=False):
        while True:
            try:
                user_input = input(prompt)
                if is_float:
                    value = float(user_input)
                else:
                    value = int(user_input)
                if valid_values and value not in valid_values:
                    print(f"Invalid input! Please enter one of the following: {valid_values}")
                    continue
                return value
            except ValueError:
                print("Invalid input! Please enter a valid number.")

    def _control_loop(self):
        try:
            while True:
                self.client.loop_start()
                self._control_input()
        except KeyboardInterrupt:
            print('\nControl Loop Terminated.')

    def feedback(self):
        for topic in SUBSCRIBED_TOPICS:
            self.client.subscribe(topic)

def main():
    controller = MQTT_Controller()

if __name__ == '__main__':
    main()
