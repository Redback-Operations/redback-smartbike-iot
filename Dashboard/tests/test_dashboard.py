import sys
import os
import json
import time

repo_root = os.path.abspath(os.getcwd())
sys.path.insert(0, os.path.join(repo_root, "Dashboard"))

import server

print("Testing MQTT topic parsing...")

# 1. Speed
server.parse_mqtt_topic_and_payload("bike/000001/speed/report", json.dumps({"value": 7.5, "unitName": "m/s"}))
assert server.current_state["speed_ms"] == 7.5, f"Speed ms failed: {server.current_state['speed_ms']}"
assert server.current_state["speed"] == 27.0, f"Speed kmh failed: {server.current_state['speed']}"

# 2. Cadence
server.parse_mqtt_topic_and_payload("bike/000001/cadence/report", json.dumps({"value": 90, "unitName": "RPM"}))
assert server.current_state["cadence"] == 90, f"Cadence failed: {server.current_state['cadence']}"

# 3. Power
server.parse_mqtt_topic_and_payload("bike/000001/power/report", json.dumps({"value": 225, "unitName": "W"}))
assert server.current_state["power"] == 225, f"Power failed: {server.current_state['power']}"

# 4. Heart Rate
server.parse_mqtt_topic_and_payload("bike/000001/heartrate", json.dumps({"value": 148, "unitName": "BPM"}))
assert server.current_state["heart_rate"] == 148, f"Heart rate failed: {server.current_state['heart_rate']}"

# 5. Incline
server.parse_mqtt_topic_and_payload("bike/000001/incline/report", json.dumps({"incline": 4.5}))
assert server.current_state["climb_grade"] == 4.5, f"Incline failed: {server.current_state['climb_grade']}"

# 6. Resistance & Workout
server.parse_mqtt_topic_and_payload("bike/000001/resistance/report", json.dumps({
    "resistance": 40,
    "target_power_watts": 160.0,
    "ftp_percent": 70.0,
    "workout": "endurance",
    "stage": "active"
}))
assert server.current_state["resistance"] == 40, f"Resistance failed: {server.current_state['resistance']}"
assert server.current_state["workout_name"] == "Endurance", f"Workout name failed: {server.current_state['workout_name']}"
assert server.current_state["workout_stage"] == "active", f"Workout stage failed: {server.current_state['workout_stage']}"
assert server.current_state["target_power"] == 160, f"Target power failed: {server.current_state['target_power']}"

# 7. Fan Status
server.parse_mqtt_topic_and_payload("bike/000001/fan/status", json.dumps({"value": 60, "unitName": "percentage"}))
assert server.current_state["fan_speed"] == 60, f"Fan speed failed: {server.current_state['fan_speed']}"
assert server.current_state["fan_level"] == 3, f"Fan level failed: {server.current_state['fan_level']}"

# 8. Button & Steering / Brake
server.parse_mqtt_topic_and_payload("bike/000001/button/report", json.dumps({"button": "LEFT", "state": 1}))
assert server.current_state["steering"] == "LEFT", f"Steering LEFT failed: {server.current_state['steering']}"

server.parse_mqtt_topic_and_payload("bike/000001/button/report", json.dumps({"button": "LEFT", "state": 0}))
assert server.current_state["steering"] == "CENTER", f"Steering CENTER failed: {server.current_state['steering']}"

server.parse_mqtt_topic_and_payload("bike/000001/button/report", json.dumps({"button": "BREAK", "state": 1}))
assert server.current_state["brake"] == True, f"Brake engaged failed: {server.current_state['brake']}"
assert server.current_state["brake_front"] == 100, f"Brake front failed: {server.current_state['brake_front']}"

# 9. Deltas detection
deltas = server.detect_deltas(server.current_state, {"speed": 0.0, "power": 0, "cadence": 0, "brake": False})
assert len(deltas) > 0, "Expected deltas detected"

print("All MQTT topic parsing and delta tests passed with 100% success!")
