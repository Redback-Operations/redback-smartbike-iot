import os
import sys
import asyncio
import json
import logging
import random
import time
import re
from typing import Dict, Any, Set, List, Optional
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query, Body, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
import paho.mqtt.client as paho_mqtt

# Load optional .env file if available
try:
    from dotenv import load_dotenv
    load_dotenv()
    root_env = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".env"))
    if os.path.exists(root_env):
        load_dotenv(root_env)
except ImportError:
    pass

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")

MQTT_HOST = os.getenv("MQTT_HOSTNAME") or os.getenv("MQTT_HOST") or "localhost"
MQTT_PORT = int(os.getenv("MQTT_PORT", "1883"))
MQTT_USER = os.getenv("MQTT_USERNAME") or os.getenv("MQTT_USER") or ""
MQTT_PASS = os.getenv("MQTT_PASSWORD") or os.getenv("MQTT_PASS") or ""
MQTT_USE_TLS = os.getenv("MQTT_USE_TLS", "").lower() in ("true", "1", "yes") or MQTT_PORT == 8883
DEFAULT_DEVICE_ID = os.getenv("DEVICE_ID") or os.getenv("BIKEID") or "000001"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
logger = logging.getLogger("DashboardServer")

app = FastAPI(
    title="Redback SmartBike IoT Platform",
    description="Diagnostic, Telemetry & Bidirectional Control Suite for Redback SmartBike IoT",
    version="2.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

active_connections: Set[WebSocket] = set()
mqtt_client_instance: Optional[paho_mqtt.Client] = None

current_state: Dict[str, Any] = {
    "device_id": DEFAULT_DEVICE_ID,
    "speed": 0.0,
    "speed_ms": 0.0,
    "cadence": 0,
    "power": 0,
    "heart_rate": 0,
    "climb_grade": 0.0,
    "resistance": 0,
    "fan_speed": 0,
    "fan_level": 0,
    "steering": "CENTER",
    "brake": False,
    "brake_front": 0,
    "brake_rear": 0,
    "workout_name": "None",
    "workout_stage": "idle",
    "target_power": 0,
    "ftp_percent": 0.0,
    "ftp_setting": 200,
    "mqtt_connected": False,
    "kickr_connected": False,
    "climb_connected": False,
    "heartrate_connected": False,
    "fan_connected": False,
    "button_connected": False,
    "last_update": time.time(),
}

device_last_seen: Dict[str, float] = {
    "kickr": 0,
    "climb": 0,
    "heartrate": 0,
    "fan": 0,
    "button": 0,
}

prev_logged_state: Dict[str, Any] = {}
simulation_active = False
mqtt_messages_buffer: List[Dict[str, Any]] = []
MAX_MQTT_BUFFER = 300

async def broadcast_payload(payload: dict):
    if not active_connections:
        return
    msg_str = json.dumps(payload)
    dead = set()
    for ws in list(active_connections):
        try:
            await ws.send_text(msg_str)
        except Exception:
            dead.add(ws)
    for ws in dead:
        if ws in active_connections:
            active_connections.remove(ws)

def detect_deltas(new_state: Dict[str, Any], old_state: Dict[str, Any]):
    deltas = []
    
    s_new = new_state.get("speed", 0.0)
    s_old = old_state.get("speed", 0.0)
    if abs(s_new - s_old) >= 0.5:
        deltas.append({"type": "speed", "msg": f"Speed: {s_old:.1f} -> {s_new:.1f} km/h", "val": s_new})

    c_new = new_state.get("cadence", 0)
    c_old = old_state.get("cadence", 0)
    if abs(c_new - c_old) >= 3:
        deltas.append({"type": "cadence", "msg": f"Cadence: {c_old} -> {c_new} RPM", "val": c_new})

    p_new = new_state.get("power", 0)
    p_old = old_state.get("power", 0)
    if abs(p_new - p_old) >= 10:
        deltas.append({"type": "power", "msg": f"Power: {p_old} W -> {p_new} W", "val": p_new})

    hr_new = new_state.get("heart_rate", 0)
    hr_old = old_state.get("heart_rate", 0)
    if hr_new > 0 and abs(hr_new - hr_old) >= 3:
        deltas.append({"type": "hr", "msg": f"Heart Rate: {hr_old} -> {hr_new} BPM", "val": hr_new})

    g_new = new_state.get("climb_grade", 0.0)
    g_old = old_state.get("climb_grade", 0.0)
    if abs(g_new - g_old) >= 0.5:
        deltas.append({"type": "climb", "msg": f"Climb Pitch: {g_old:+.1f}% -> {g_new:+.1f}%", "val": g_new})

    r_new = new_state.get("resistance", 0)
    r_old = old_state.get("resistance", 0)
    if abs(r_new - r_old) >= 2:
        deltas.append({"type": "resistance", "msg": f"Resistance: {r_old}% -> {r_new}%", "val": r_new})

    f_new = new_state.get("fan_speed", 0)
    f_old = old_state.get("fan_speed", 0)
    if abs(f_new - f_old) >= 5:
        deltas.append({"type": "fan", "msg": f"Fan Speed: {f_old}% -> {f_new}%", "val": f_new})

    b_new = new_state.get("brake", False)
    b_old = old_state.get("brake", False)
    if b_new != b_old:
        status_text = "ENGAGED" if b_new else "RELEASED"
        deltas.append({"type": "brake", "msg": f"Brake System: {status_text}", "val": b_new})

    st_new = new_state.get("steering", "CENTER")
    st_old = old_state.get("steering", "CENTER")
    if st_new != st_old:
        deltas.append({"type": "steering", "msg": f"Steering: {st_old} -> {st_new}", "val": st_new})

    wk_new = new_state.get("workout_stage", "idle")
    wk_old = old_state.get("workout_stage", "idle")
    if wk_new != wk_old and wk_new != "idle":
        deltas.append({"type": "workout", "msg": f"Workout [{new_state.get('workout_name', '')}] Stage: {wk_new.upper()} ({new_state.get('target_power', 0)}W)", "val": wk_new})

    return deltas

def check_heartbeats():
    now = time.time()
    current_state["kickr_connected"] = (now - device_last_seen["kickr"]) < 12
    current_state["climb_connected"] = (now - device_last_seen["climb"]) < 12
    current_state["heartrate_connected"] = (now - device_last_seen["heartrate"]) < 12
    current_state["fan_connected"] = (now - device_last_seen["fan"]) < 15
    current_state["button_connected"] = (now - device_last_seen["button"]) < 30

def parse_mqtt_topic_and_payload(topic: str, raw_payload: str):
    global current_state, device_last_seen
    current_state["last_update"] = time.time()
    
    data = None
    try:
        data = json.loads(raw_payload)
    except Exception:
        pass

    topic_parts = topic.split("/")
    if len(topic_parts) >= 2 and topic_parts[0] == "bike" and topic_parts[1] not in ("#", "+"):
        current_state["device_id"] = topic_parts[1]

    if "/speed" in topic:
        device_last_seen["kickr"] = time.time()
        current_state["kickr_connected"] = True
        if isinstance(data, dict):
            val = data.get("value") or data.get("speed") or 0.0
            unit = str(data.get("unitName", "m/s")).lower()
            try:
                val = float(val)
                if unit == "m/s":
                    current_state["speed_ms"] = round(val, 2)
                    current_state["speed"] = round(val * 3.6, 1)
                else:
                    current_state["speed"] = round(val, 1)
                    current_state["speed_ms"] = round(val / 3.6, 2)
            except (ValueError, TypeError):
                pass
        elif data is not None:
            try:
                val = float(data)
                current_state["speed"] = round(val, 1)
                current_state["speed_ms"] = round(val / 3.6, 2)
            except (ValueError, TypeError):
                pass

    elif "/cadence" in topic:
        device_last_seen["kickr"] = time.time()
        current_state["kickr_connected"] = True
        if isinstance(data, dict):
            val = data.get("value") or data.get("cadence") or 0
            try:
                current_state["cadence"] = int(round(float(val)))
            except (ValueError, TypeError):
                pass
        elif data is not None:
            try:
                current_state["cadence"] = int(round(float(data)))
            except (ValueError, TypeError):
                pass

    elif "/power" in topic:
        device_last_seen["kickr"] = time.time()
        current_state["kickr_connected"] = True
        if isinstance(data, dict):
            val = data.get("value") or data.get("power") or 0
            try:
                current_state["power"] = int(round(float(val)))
            except (ValueError, TypeError):
                pass
        elif data is not None:
            try:
                current_state["power"] = int(round(float(data)))
            except (ValueError, TypeError):
                pass

    elif "/heartrate" in topic or "/hr" in topic:
        device_last_seen["heartrate"] = time.time()
        current_state["heartrate_connected"] = True
        if isinstance(data, dict):
            val = data.get("value") or data.get("heartrate") or data.get("heart_rate") or 0
            try:
                current_state["heart_rate"] = int(round(float(val)))
            except (ValueError, TypeError):
                pass
        elif data is not None:
            try:
                current_state["heart_rate"] = int(round(float(data)))
            except (ValueError, TypeError):
                pass

    elif "/incline" in topic or "/climb" in topic:
        device_last_seen["climb"] = time.time()
        current_state["climb_connected"] = True
        if isinstance(data, dict):
            val = data.get("incline") if "incline" in data else data.get("value")
            if val is not None:
                try:
                    current_state["climb_grade"] = round(float(val), 1)
                except (ValueError, TypeError):
                    pass
        elif data is not None:
            try:
                current_state["climb_grade"] = round(float(data), 1)
            except (ValueError, TypeError):
                pass

    elif "/resistance" in topic:
        device_last_seen["kickr"] = time.time()
        current_state["kickr_connected"] = True
        if isinstance(data, dict):
            val = data.get("resistance") if "resistance" in data else data.get("value")
            if val is not None:
                try:
                    current_state["resistance"] = int(round(float(val)))
                except (ValueError, TypeError):
                    pass
            if "workout" in data:
                current_state["workout_name"] = str(data["workout"]).capitalize()
            if "stage" in data:
                current_state["workout_stage"] = str(data["stage"]).lower()
            if "target_power_watts" in data:
                try:
                    current_state["target_power"] = int(round(float(data["target_power_watts"])))
                except (ValueError, TypeError):
                    pass
            if "ftp_percent" in data:
                try:
                    current_state["ftp_percent"] = round(float(data["ftp_percent"]), 1)
                except (ValueError, TypeError):
                    pass
        elif data is not None:
            try:
                current_state["resistance"] = int(round(float(data)))
            except (ValueError, TypeError):
                pass

    elif "/fan" in topic:
        device_last_seen["fan"] = time.time()
        current_state["fan_connected"] = True
        if isinstance(data, dict):
            if "value" in data:
                try:
                    current_state["fan_speed"] = int(round(float(data["value"])))
                    current_state["fan_level"] = int(round(current_state["fan_speed"] / 20.0))
                except (ValueError, TypeError):
                    pass
            elif "level" in data:
                try:
                    lvl = int(data["level"])
                    current_state["fan_level"] = max(0, min(5, lvl))
                    current_state["fan_speed"] = current_state["fan_level"] * 20
                except (ValueError, TypeError):
                    pass
        elif data is not None:
            try:
                val = int(data)
                if val <= 5:
                    current_state["fan_level"] = val
                    current_state["fan_speed"] = val * 20
                else:
                    current_state["fan_speed"] = val
                    current_state["fan_level"] = int(round(val / 20.0))
            except (ValueError, TypeError):
                pass

    elif "/button" in topic or "Turn/" in topic:
        device_last_seen["button"] = time.time()
        current_state["button_connected"] = True
        
        if topic == "Turn/Left":
            msg_str = str(raw_payload).strip().upper()
            current_state["steering"] = "LEFT" if msg_str == "LEFT" else "CENTER"
        elif topic == "Turn/Right":
            msg_str = str(raw_payload).strip().upper()
            current_state["steering"] = "RIGHT" if msg_str == "RIGHT" else "CENTER"
        elif isinstance(data, dict):
            btn = str(data.get("button", "")).upper()
            st = int(data.get("state", 0))
            
            if btn == "LEFT":
                current_state["steering"] = "LEFT" if st == 1 else "CENTER"
            elif btn == "RIGHT":
                current_state["steering"] = "RIGHT" if st == 1 else "CENTER"
            elif btn in ("BREAK", "BRAKE"):
                current_state["brake"] = (st == 1)
                current_state["brake_front"] = 100 if st == 1 else 0
                current_state["brake_rear"] = 80 if st == 1 else 0

    elif isinstance(data, dict):
        for k in ["speed", "cadence", "power", "heart_rate", "climb_grade", "resistance", "fan_speed", "brake", "brake_front", "brake_rear", "steering", "device_id"]:
            if k in data:
                current_state[k] = data[k]
        if "incline" in data:
            current_state["climb_grade"] = float(data["incline"])

def publish_mqtt_message(topic: str, payload_data: Any, qos: int = 1) -> bool:
    global mqtt_client_instance
    if not mqtt_client_instance or not current_state["mqtt_connected"]:
        logger.warning(f"MQTT client not connected. Local fallback publish to {topic}: {payload_data}")
        if isinstance(payload_data, (dict, list)):
            payload_str = json.dumps(payload_data)
        else:
            payload_str = str(payload_data)
        parse_mqtt_topic_and_payload(topic, payload_str)
        return False

    try:
        if isinstance(payload_data, (dict, list)):
            payload_str = json.dumps(payload_data)
        else:
            payload_str = str(payload_data)
            
        res = mqtt_client_instance.publish(topic, payload=payload_str, qos=qos)
        logger.info(f"Published to {topic} (QoS {qos}): {payload_str}")
        return res.rc == 0
    except Exception as e:
        logger.error(f"Failed to publish to MQTT topic {topic}: {e}")
        return False

def on_connect(client, userdata, flags, rc, properties=None):
    if rc == 0:
        logger.info(f"Connected successfully to MQTT Broker at {MQTT_HOST}:{MQTT_PORT}!")
        current_state["mqtt_connected"] = True
        topics = [
            ("bike/#", 0),
            ("Turn/#", 0),
            ("$SYS/broker/uptime", 0)
        ]
        client.subscribe(topics)
        logger.info("Subscribed to wildcard topics: bike/#, Turn/#, $SYS/broker/uptime")
    else:
        logger.warning(f"MQTT connection failed with code: {rc}")
        current_state["mqtt_connected"] = False

def on_disconnect(client, userdata, rc, properties=None):
    logger.info(f"Disconnected from MQTT Broker (code: {rc})")
    current_state["mqtt_connected"] = False

def on_message(client, userdata, msg):
    global prev_logged_state
    try:
        raw_payload = msg.payload.decode(errors="ignore")
        timestamp = time.strftime("%H:%M:%S")
        
        mqtt_item = {
            "timestamp": timestamp,
            "topic": msg.topic,
            "payload": raw_payload,
            "qos": msg.qos,
            "size": len(msg.payload)
        }
        mqtt_messages_buffer.append(mqtt_item)
        if len(mqtt_messages_buffer) > MAX_MQTT_BUFFER:
            mqtt_messages_buffer.pop(0)

        parse_mqtt_topic_and_payload(msg.topic, raw_payload)
        check_heartbeats()

        deltas = detect_deltas(current_state, prev_logged_state)
        if deltas:
            prev_logged_state = dict(current_state)

        loop = getattr(app, "custom_loop", None)
        if loop and loop.is_running():
            asyncio.run_coroutine_threadsafe(
                broadcast_payload({
                    "type": "telemetry",
                    "state": current_state,
                    "deltas": deltas,
                    "mqtt_event": mqtt_item
                }),
                loop
            )
    except Exception as e:
        logger.error(f"Error handling MQTT message: {e}")

async def live_heartbeat_worker():
    while True:
        check_heartbeats()
        await broadcast_payload({
            "type": "telemetry",
            "state": current_state,
            "deltas": []
        })
        await asyncio.sleep(1)

async def simulation_worker():
    global simulation_active, prev_logged_state
    speed_kmh = 24.5
    cadence = 86
    power = 185
    hr = 136
    grade = 1.5
    resistance = 35
    fan_speed = 40
    
    sim_tick = 0
    
    while True:
        sim_tick += 1
        check_heartbeats()
        
        if simulation_active:
            speed_kmh = max(0.0, min(65.0, round(speed_kmh + random.uniform(-0.6, 0.7), 1)))
            speed_ms = round(speed_kmh / 3.6, 2)
            cadence = max(0, min(140, int(cadence + random.randint(-2, 2))))
            power = max(0, min(600, int(power + random.randint(-7, 8))))
            hr = max(60, min(195, int(hr + random.randint(-1, 1))))
            
            if random.random() < 0.05:
                grade = round(random.choice([-4.0, -2.0, 0.0, 1.5, 3.5, 6.0, 8.5, 12.0]), 1)
            
            if random.random() < 0.04:
                resistance = random.choice([15, 25, 35, 50, 70])

            fan_speed = min(100, max(0, int(power / 3.5)))
            fan_level = int(round(fan_speed / 20.0))

            steer = "CENTER"
            r_steer = random.random()
            if r_steer < 0.07:
                steer = "LEFT"
            elif r_steer < 0.14:
                steer = "RIGHT"

            brake = random.random() < 0.05
            brake_f = 85 if brake else 0
            brake_r = 70 if brake else 0

            stages = ["warmup", "active", "active", "cooldown", "recovery"]
            stage_idx = (sim_tick // 40) % len(stages)
            current_stage = stages[stage_idx]
            target_watts = int(200 * (0.5 if current_stage in ("warmup", "recovery") else 0.85))

            device_id = current_state.get("device_id", DEFAULT_DEVICE_ID)

            current_state.update({
                "speed": speed_kmh,
                "speed_ms": speed_ms,
                "cadence": cadence,
                "power": power,
                "heart_rate": hr,
                "climb_grade": grade,
                "resistance": resistance,
                "fan_speed": fan_speed,
                "fan_level": fan_level,
                "brake": brake,
                "brake_front": brake_f,
                "brake_rear": brake_r,
                "steering": steer,
                "workout_name": "Endurance",
                "workout_stage": current_stage,
                "target_power": target_watts,
                "ftp_percent": round((target_watts / current_state["ftp_setting"]) * 100, 1),
                "mqtt_connected": True,
                "kickr_connected": True,
                "climb_connected": True,
                "heartrate_connected": True,
                "fan_connected": True,
                "button_connected": True,
                "last_update": time.time(),
            })

            deltas = detect_deltas(current_state, prev_logged_state)
            if deltas:
                prev_logged_state = dict(current_state)

            timestamp = time.strftime("%H:%M:%S")
            subtopic = random.choice(["speed", "cadence", "power", "heartrate", "incline", "resistance", "fan", "button"])
            
            if subtopic == "speed":
                mock_topic = f"bike/{device_id}/speed/report"
                mock_payload = json.dumps({"value": speed_ms, "unitName": "m/s", "timestamp": time.time()})
            elif subtopic == "cadence":
                mock_topic = f"bike/{device_id}/cadence/report"
                mock_payload = json.dumps({"value": cadence, "unitName": "RPM", "timestamp": time.time()})
            elif subtopic == "power":
                mock_topic = f"bike/{device_id}/power/report"
                mock_payload = json.dumps({"value": power, "unitName": "W", "timestamp": time.time()})
            elif subtopic == "heartrate":
                mock_topic = f"bike/{device_id}/heartrate"
                mock_payload = json.dumps({"value": hr, "unitName": "BPM", "timestamp": time.time()})
            elif subtopic == "incline":
                mock_topic = f"bike/{device_id}/incline/report"
                mock_payload = json.dumps({"incline": grade, "timestamp": time.time()})
            elif subtopic == "resistance":
                mock_topic = f"bike/{device_id}/resistance/report"
                mock_payload = json.dumps({
                    "resistance": resistance,
                    "target_power_watts": target_watts,
                    "ftp_percent": round((target_watts / current_state["ftp_setting"]) * 100, 1),
                    "workout": "endurance",
                    "stage": current_stage,
                    "timestamp": time.time()
                })
            elif subtopic == "fan":
                mock_topic = f"bike/{device_id}/fan/status"
                mock_payload = json.dumps({"value": fan_speed, "unitName": "percentage", "timestamp": time.time()})
            else:
                mock_topic = f"bike/{device_id}/button/report"
                mock_payload = json.dumps({"button": steer if steer != "CENTER" else ("BREAK" if brake else "CENTER"), "state": 1 if (steer != "CENTER" or brake) else 0, "timestamp": time.time()})

            mock_mqtt = {
                "timestamp": timestamp,
                "topic": mock_topic,
                "payload": mock_payload,
                "qos": 0,
                "size": len(mock_payload)
            }
            mqtt_messages_buffer.append(mock_mqtt)
            if len(mqtt_messages_buffer) > MAX_MQTT_BUFFER:
                mqtt_messages_buffer.pop(0)

            await broadcast_payload({
                "type": "telemetry",
                "state": current_state,
                "deltas": deltas,
                "mqtt_event": mock_mqtt
            })
        await asyncio.sleep(0.5)

@app.on_event("startup")
async def startup_event():
    global mqtt_client_instance
    app.custom_loop = asyncio.get_running_loop()
    asyncio.create_task(live_heartbeat_worker())
    
    try:
        try:
            mqttc = paho_mqtt.Client(client_id=f"redback_dashboard_{random.randint(1000, 9999)}", protocol=paho_mqtt.MQTTv5)
        except Exception:
            mqttc = paho_mqtt.Client(client_id=f"redback_dashboard_{random.randint(1000, 9999)}")
            
        if MQTT_USER and MQTT_PASS:
            mqttc.username_pw_set(MQTT_USER, MQTT_PASS)
            
        if MQTT_USE_TLS:
            try:
                mqttc.tls_set(tls_version=paho_mqtt.ssl.PROTOCOL_TLS)
            except Exception as e:
                logger.warning(f"Could not configure TLS: {e}")
                
        mqttc.on_connect = on_connect
        mqttc.on_disconnect = on_disconnect
        mqttc.on_message = on_message
        
        logger.info(f"Connecting to MQTT Broker at {MQTT_HOST}:{MQTT_PORT}...")
        mqttc.connect_async(MQTT_HOST, MQTT_PORT, 60)
        mqttc.loop_start()
        mqtt_client_instance = mqttc
    except Exception as e:
        logger.warning(f"Could not connect to MQTT Broker ({e}). Dashboard is running in standalone mode.")

@app.on_event("shutdown")
async def shutdown_event():
    global mqtt_client_instance
    if mqtt_client_instance:
        try:
            mqtt_client_instance.loop_stop()
            mqtt_client_instance.disconnect()
        except Exception:
            pass

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    global current_state
    await websocket.accept()
    active_connections.add(websocket)
    
    await websocket.send_text(json.dumps({
        "type": "init",
        "state": current_state,
        "mqtt_buffer": mqtt_messages_buffer[-50:],
        "config": {
            "broker_host": MQTT_HOST,
            "broker_port": MQTT_PORT,
            "device_id": current_state["device_id"]
        }
    }))
    
    try:
        while True:
            raw = await websocket.receive_text()
            cmd = json.loads(raw)
            action = cmd.get("action")
            device_id = current_state.get("device_id", DEFAULT_DEVICE_ID)

            if action in ("set_climb", "set_incline"):
                new_grade = round(float(cmd.get("grade") if cmd.get("grade") is not None else cmd.get("incline", 0.0)), 1)
                new_grade = max(-10.0, min(19.0, new_grade))
                current_state["climb_grade"] = new_grade
                
                topic = f"bike/{device_id}/incline/control"
                payload = {"incline": new_grade, "timestamp": time.time()}
                publish_mqtt_message(topic, payload)
                
                delta_msg = f"Incline Command: {new_grade:+.1f}% sent to {topic}"
                await broadcast_payload({
                    "type": "telemetry",
                    "state": current_state,
                    "deltas": [{"type": "climb", "msg": delta_msg, "val": new_grade}],
                    "mqtt_event": {
                        "timestamp": time.strftime("%H:%M:%S"),
                        "topic": topic,
                        "payload": json.dumps(payload),
                        "qos": 1,
                        "size": len(json.dumps(payload))
                    }
                })

            elif action == "set_resistance":
                new_res = max(0, min(100, int(cmd.get("resistance", 0))))
                current_state["resistance"] = new_res
                
                topic = f"bike/{device_id}/resistance/control"
                payload = {
                    "resistance": new_res,
                    "target_power_watts": round(current_state["ftp_setting"] * (new_res / 100.0), 1),
                    "ftp_percent": new_res,
                    "stage": "manual",
                    "timestamp": time.time()
                }
                publish_mqtt_message(topic, payload)
                
                delta_msg = f"Resistance Command: {new_res}% sent to {topic}"
                await broadcast_payload({
                    "type": "telemetry",
                    "state": current_state,
                    "deltas": [{"type": "resistance", "msg": delta_msg, "val": new_res}],
                    "mqtt_event": {
                        "timestamp": time.strftime("%H:%M:%S"),
                        "topic": topic,
                        "payload": json.dumps(payload),
                        "qos": 1,
                        "size": len(json.dumps(payload))
                    }
                })

            elif action == "set_fan":
                level = cmd.get("level")
                speed = cmd.get("value") or cmd.get("speed")
                if level is not None:
                    level = max(0, min(5, int(level)))
                    speed = level * 20
                elif speed is not None:
                    speed = max(0, min(100, int(speed)))
                    level = int(round(speed / 20.0))
                else:
                    level = 0
                    speed = 0
                    
                current_state["fan_speed"] = speed
                current_state["fan_level"] = level
                
                topic = f"bike/{device_id}/fan/control"
                payload = {"level": level, "value": speed, "timestamp": time.time()}
                publish_mqtt_message(topic, payload)
                
                delta_msg = f"Headwind Fan Command: Level {level} ({speed}%) sent to {topic}"
                await broadcast_payload({
                    "type": "telemetry",
                    "state": current_state,
                    "deltas": [{"type": "fan", "msg": delta_msg, "val": speed}],
                    "mqtt_event": {
                        "timestamp": time.strftime("%H:%M:%S"),
                        "topic": topic,
                        "payload": json.dumps(payload),
                        "qos": 1,
                        "size": len(json.dumps(payload))
                    }
                })

            elif action == "set_workout":
                workout_name = cmd.get("workout", "Endurance")
                ftp = float(cmd.get("ftp", current_state["ftp_setting"]))
                subaction = cmd.get("workout_action", "start")
                
                current_state["workout_name"] = workout_name
                current_state["ftp_setting"] = ftp
                current_state["workout_stage"] = "warmup" if subaction == "start" else "idle"
                
                topic = f"bike/{device_id}/workout"
                payload = {"workout": workout_name.lower(), "ftp": ftp, "action": subaction, "timestamp": time.time()}
                publish_mqtt_message(topic, payload)
                
                delta_msg = f"Workout Command: {workout_name} ({subaction.upper()}) @ FTP {ftp:.0f}W"
                await broadcast_payload({
                    "type": "telemetry",
                    "state": current_state,
                    "deltas": [{"type": "workout", "msg": delta_msg, "val": workout_name}],
                })

            elif action == "switch_device":
                new_id = str(cmd.get("device_id", DEFAULT_DEVICE_ID)).strip()
                if new_id:
                    current_state["device_id"] = new_id
                    await broadcast_payload({
                        "type": "telemetry",
                        "state": current_state,
                        "deltas": [{"type": "system", "msg": f"Active Device ID switched to #{new_id}", "val": new_id}]
                    })

            elif action == "publish_mqtt":
                pub_topic = cmd.get("topic", f"bike/{device_id}/custom")
                pub_payload = cmd.get("payload", "{}")
                pub_qos = int(cmd.get("qos", 0))
                try:
                    payload_json = json.loads(pub_payload)
                    publish_mqtt_message(pub_topic, payload_json, pub_qos)
                except Exception:
                    publish_mqtt_message(pub_topic, pub_payload, pub_qos)

    except WebSocketDisconnect:
        if websocket in active_connections:
            active_connections.remove(websocket)

@app.get("/api/state")
async def get_state():
    return current_state

@app.get("/api/config")
async def get_config():
    return {
        "broker_host": MQTT_HOST,
        "broker_port": MQTT_PORT,
        "broker_user": MQTT_USER if MQTT_USER else None,
        "use_tls": MQTT_USE_TLS,
        "default_device_id": current_state["device_id"]
    }

@app.post("/api/control/incline")
async def api_set_incline(incline: float = Body(..., embed=True)):
    grade = max(-10.0, min(19.0, round(incline, 1)))
    current_state["climb_grade"] = grade
    topic = f"bike/{current_state['device_id']}/incline/control"
    payload = {"incline": grade, "timestamp": time.time()}
    publish_mqtt_message(topic, payload)
    return {"status": "ok", "incline": grade, "topic": topic}

@app.post("/api/control/resistance")
async def api_set_resistance(resistance: int = Body(..., embed=True)):
    res_val = max(0, min(100, int(resistance)))
    current_state["resistance"] = res_val
    topic = f"bike/{current_state['device_id']}/resistance/control"
    payload = {"resistance": res_val, "timestamp": time.time()}
    publish_mqtt_message(topic, payload)
    return {"status": "ok", "resistance": res_val, "topic": topic}

@app.post("/api/control/fan")
async def api_set_fan(speed: int = Body(..., embed=True)):
    fan_val = max(0, min(100, int(speed)))
    lvl = int(round(fan_val / 20.0))
    current_state["fan_speed"] = fan_val
    current_state["fan_level"] = lvl
    topic = f"bike/{current_state['device_id']}/fan/control"
    payload = {"level": lvl, "value": fan_val, "timestamp": time.time()}
    publish_mqtt_message(topic, payload)
    return {"status": "ok", "fan_speed": fan_val, "level": lvl, "topic": topic}

@app.post("/api/publish")
async def api_publish_raw(topic: str = Body(...), payload: str = Body(...), qos: int = Body(0)):
    try:
        p_data = json.loads(payload)
    except Exception:
        p_data = payload
    success = publish_mqtt_message(topic, p_data, qos)
    return {"status": "ok" if success else "sent_or_simulated", "topic": topic}

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

@app.get("/")
async def get_index():
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8080)
