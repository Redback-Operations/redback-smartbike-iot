#!/usr/bin/env python3

import os
import argparse
import sys
import subprocess

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from lib.mqtt_client import MQTTClient  # noqa: E402

# Set up argument parser to handle environment variables
parser = argparse.ArgumentParser(description="MQTT Listener for Workout Control")
parser.add_argument("--device_id", type=str, default=os.getenv('DEVICE_ID'),
                    help="The unique ID of the bike, used to form MQTT topics")
parser.add_argument("--mqtt_host", type=str, default=os.getenv('MQTT_HOSTNAME') or os.getenv('MQTT_HOST'),
                    help="MQTT broker host address")
parser.add_argument("--mqtt_port", type=int, default=int(os.getenv('MQTT_PORT', '1883')),
                    help="MQTT broker port")
parser.add_argument("--mqtt_user", type=str, default=os.getenv('MQTT_USERNAME') or os.getenv('MQTT_USER'),
                    help="MQTT username")
parser.add_argument("--mqtt_password", type=str, default=os.getenv('MQTT_PASSWORD') or os.getenv('MQTT_PASS'),
                    help="MQTT password")
parser.add_argument("--root_dir", type=str, default=os.getenv('ROOT_DIR', '/home/pi'),
                    help="Root directory where workout scripts are located")

args = parser.parse_args()

# MQTT topic
workout_topic = f"bike/{args.device_id}/workout"

# State tracking for ongoing workouts
current_workout = None

# MQTT Callbacks
def on_connect(client, userdata, flags, rc, properties=None):
    print(f"Connected with result code {rc}")
    client.subscribe(workout_topic)

def on_message(client, userdata, msg):
    global current_workout
    workout_type = msg.payload.decode().lower()  # Make workout selector case insensitive
    print(f"Message received: {msg.topic} {workout_type}")

    if current_workout:
        print(f"Workout already started: {current_workout}")
        # Terminate the current workout if a new one is triggered
        print("Terminating current workout...")
        subprocess.run(["pkill", "-f", current_workout])  # Kills the current workout process
        current_workout = None

    # Start a new workout based on the message
    if workout_type == "ramped":
        current_workout = os.path.join(args.root_dir, "Driver/start_ramped_workout.py")
    elif workout_type == "ftp":
        current_workout = os.path.join(args.root_dir, "Driver/start_ftp_workout.py")
    else:
        print("Unknown workout type")
        return
    
    # Start the selected workout
    print(f"Starting workout: {workout_type}")
    subprocess.run([current_workout])
    
# Setup MQTT Client (host, port, login and TLS from args / .env)
mqtt_client = MQTTClient(args.mqtt_host, args.mqtt_user, args.mqtt_password, port=args.mqtt_port)
mqtt_client.on_connect = on_connect
mqtt_client.on_message = on_message
mqtt_client.setup_mqtt_client()
client = mqtt_client.get_client()

# Blocking call to process network traffic and dispatch callbacks
client.loop_forever()
