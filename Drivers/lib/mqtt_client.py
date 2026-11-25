#!/usr/bin/env python3

import os
import sys
import time
import paho.mqtt.client as paho
from paho import mqtt
import logging

# setup logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

logger_formatter = logging.Formatter('%(levelname)s:%(name)s:%(message)s')

logger_file_handler = logging.FileHandler('mqtt.log') # TODO: setup a logging folder and write all logging files to that folder
logger_file_handler.setFormatter(logger_formatter)

logger_stream_handler = logging.StreamHandler() # this will print all logs to the terminal also

logger.addHandler(logger_file_handler)
logger.addHandler(logger_stream_handler)

# log unhandled exceptions
def handle_exception(exc_type, exc_value, exc_traceback):
    if issubclass(exc_type, KeyboardInterrupt):
        sys.__excepthook__(exc_type, exc_value, exc_traceback)
        return

    logger.critical("Uncaught exception", exc_info=(exc_type, exc_value, exc_traceback))

sys.excepthook = handle_exception

# this is a MQTT client that is able to publish to and subscribe from MQTT topics
def _env(*names, default=None):
    """Return the first non-empty environment variable from names."""
    for name in names:
        value = os.getenv(name)
        if value:
            return value
    return default


def load_mqtt_config():
    """Read broker settings from the environment (.env).

    Primary names: MQTT_HOSTNAME, MQTT_PORT, MQTT_USERNAME, MQTT_PASSWORD, MQTT_USE_TLS.
    Legacy aliases MQTT_HOST, MQTT_USER, MQTT_PASS are still accepted.
    """
    host = _env("MQTT_HOSTNAME", "MQTT_HOST")
    port = int(_env("MQTT_PORT", default="1883"))
    username = _env("MQTT_USERNAME", "MQTT_USER")
    password = _env("MQTT_PASSWORD", "MQTT_PASS")
    use_tls = _env("MQTT_USE_TLS", default="").lower() in ("true", "1", "yes") or port == 8883
    return {"host": host, "port": port, "username": username,
            "password": password, "use_tls": use_tls}


# this is a MQTT client that is able to publish to and subscribe from MQTT topics
class MQTTClient:
    def __init__(self, broker_address=None, username=None, password=None, port=None, use_tls=None):
        # Anything not passed in falls back to the environment, so callers never hard-code broker details
        config = load_mqtt_config()
        self.broker_address = broker_address or config["host"]
        self.username = username or config["username"]
        self.password = password or config["password"]
        self.port = int(port) if port else config["port"]
        self.use_tls = config["use_tls"] if use_tls is None else use_tls
        self.client = None

        if not self.broker_address:
            raise ValueError("MQTT broker host not set. Set MQTT_HOSTNAME in .env or pass --broker_address.")

    @classmethod
    def from_env(cls):
        return cls()

    def get_client(self):
        return self.client

    def setup_mqtt_client(self):
        # using MQTT version 5 here, for 3.1.1: MQTTv311, 3.1: MQTTv31
        # userdata is user defined data of any type, updated by user_data_set()
        # client_id is the given name of the client
        self.client = paho.Client(client_id="", userdata=None, protocol=paho.MQTTv5)
        self.client.on_connect = self.on_connect

        # enable TLS only when configured (MQTT_USE_TLS=true or port 8883)
        if self.use_tls:
            self.client.tls_set(tls_version=paho.ssl.PROTOCOL_TLS)
        # only send a login if one is configured
        if self.username:
            self.client.username_pw_set(self.username, self.password)
        logger.info(f"Connecting to MQTT broker {self.broker_address}:{self.port} (TLS={self.use_tls})")
        self.client.connect(self.broker_address, self.port)

        # setting callbacks, use separate functions like above for better visibility
        self.client.on_subscribe = self.on_subscribe
        self.client.on_message = self.on_message
        self.client.on_publish = self.on_publish
        self.client.on_disconnect = self.on_disconnect

    def subscribe(self, topic_name):
        # subscribe to all topics of encyclopedia by using the wildcard "#"
        self.client.subscribe(topic_name, qos=1)

    def publish(self, topic_name, payload):
        # a single publish, this can also be done in loops, etc.
        self.client.publish(topic_name, payload=payload, qos=1)

    def loop_forever(self):
        # loop_forever for simplicity, here you need to stop the loop manually
        # you can also use loop_start and loop_stop
        self.client.loop_forever()

    def loop_start(self):
        # this method will starts a new thread for MQTT communication
        self.client.loop_start()

    # setting callbacks for different events to see if it works, print the message etc.
    def on_connect(self, client, userdata, flags, rc, properties=None):
        logger.info("CONNACK received with code %s." % rc)

    # with this callback you can see if your publish was successful
    def on_publish(self, client, userdata, mid, properties=None):
        logger.debug("[MQTT message published] mid: " + str(mid))

    # print which topic was subscribed to
    def on_subscribe(self, client, userdata, mid, granted_qos, properties=None):
        logger.debug("Subscribed: " + str(mid) + " " + str(granted_qos))

    # print message, useful for checking if it was successful
    def on_message(self, client, userdata, msg):
        logger.debug(msg.topic + " " + str(msg.qos) + " " + str(msg.payload))
    
    def on_disconnect(self, client, userdata, rc, properties):
        logger.info(f"Disconnected result code: {str(rc)}")
        if rc == 0:
            self.client.loop_stop()
        elif rc > 0:
            self.client.reconnect()

if __name__ == '__main__':
    # quick connection test using the values in .env
    client = MQTTClient.from_env()
    client.setup_mqtt_client()
    client.loop_forever()
