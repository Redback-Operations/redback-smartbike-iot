#!/usr/bin/env python3
# Thin wrapper: use the shared client in Drivers/lib so broker host, port,
# login and TLS all come from .env (MQTT_HOSTNAME, MQTT_PORT, ...).
import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from lib.mqtt_client import MQTTClient, load_mqtt_config  # noqa: E402,F401
