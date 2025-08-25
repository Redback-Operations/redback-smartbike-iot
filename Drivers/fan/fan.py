#!/usr/bin/env python3
import gatt
import sys
import struct
from mqtt_client import MQTTClient
import os
import json
import time
import platform

# MQTT message handler - now listens to 'bike/{DEVICE_ID}/fan/control'
def message(client, userdata, msg):
    payload = msg.payload.decode("utf-8")
    print("Received", msg.topic, msg.qos, msg.payload)

    try:
        data = json.loads(payload)
        fan_level = int(data.get("level", -1))
    except (json.JSONDecodeError, ValueError):
        print("Invalid payload format")
        return

    if fan_level < 0 or fan_level > 5:
        print("Invalid level value")
        return

    # Map 0–5 to 0–100 percentage scale
    speed = fan_level * 20
    print(f"Setting fan to {speed}% based on level {fan_level}")
    device.set_speed(speed)

def publish(client, userdata, mid, properties=None):
    pass

class AnyDeviceManager(gatt.DeviceManager):
    def device_discovered(self, dev):
        alias = dev.alias()
        if alias and self.prefix and alias.startswith(self.prefix):
            dev = AnyDevice(mac_address=dev.mac_address, manager=self)
            dev.enableCount = 0
            dev.startCount = 0
            dev.sendCount = 0
            dev.speed = 0
            dev.zeroCount = 0
            dev.zero_limit = 10
            dev.connect()
            self.stop_discovery()
            global device
            device = dev

class AnyDevice(gatt.Device):
    def __del__(self):
        self.stop_measurements()

    def connect_succeeded(self):
        super().connect_succeeded()
        print(f"[{self.mac_address}] Connected")

    def connect_failed(self, error):
        super().connect_failed(error)
        print(f"[{self.mac_address}] Connection failed: {error}")
        self.manager.start_discovery()

    def disconnect_succeeded(self):
        super().disconnect_succeeded()

    def set_speed(self, new_speed):
        if not (0 <= new_speed <= 100):
            print(f"Invalid speed {new_speed}")
            return
        self.speed = new_speed
        self.sendCount = 0
        if self.enableCount < 3:
            value = bytes([0x20, 0xee, 0xfc])
            self.enable_characteristic.write_value(value)
        elif self.startCount < 3:
            value = bytes([0x04, 0x04])
            self.fan_characteristic.write_value(value)
        else:
            value = bytes([0x02, self.speed])
            self.fan_characteristic.write_value(value)

    def services_resolved(self):
        super().services_resolved()
        self.manager.stop_discovery()
        self.enable_service = next(s for s in self.services if s.uuid[4:8] == 'ee01')
        self.enable_characteristic = next(c for c in self.enable_service.characteristics if c.uuid[4:8] == 'e002')
        self.fan_service = next(s for s in self.services if s.uuid[4:8] == 'ee0c')
        self.fan_characteristic = next(c for c in self.fan_service.characteristics if c.uuid[4:8] == 'e038')
        self.enable_characteristic.enable_notifications()
        self.fan_characteristic.enable_notifications()
        if self.enableCount < 3:
            value = bytes([0x20, 0xee, 0xfc])
            self.enable_characteristic.write_value(value)

    def stop_measurements(self):
        self.enable_characteristic.enable_notifications(False)
        self.fan_characteristic.enable_notifications(False)

    def characteristic_write_value_succeeded(self, characteristic):
        if characteristic == self.enable_characteristic and self.enableCount < 3:
            self.enable_characteristic.write_value(bytes([0x20, 0xee, 0xfc]))
            self.enableCount += 1
        elif characteristic == self.fan_characteristic:
            if self.startCount < 3:
                self.fan_characteristic.write_value(bytes([0x04, 0x04]))
                self.startCount += 1
            elif self.sendCount < 3:
                self.fan_characteristic.write_value(bytes([0x02, self.speed]))
                self.sendCount += 1
                if self.sendCount == 3:
                    print(f"Speed set to {self.speed}")

    def characteristic_write_value_failed(self, error):
        print("Write failed")

    def characteristic_enable_notifications_succeeded(self, characteristic):
        print("Notifications enabled")

    def characteristic_enable_notifications_failed(self, characteristic, error):
        print("Notifications failed")

    def characteristic_value_updated(self, characteristic, value):
        if characteristic == self.fan_characteristic:
            if len(value) == 4 and value[0] == 0xFD and value[1] == 0x01 and value[3] == 0x04:
                if not (value[2] == 0x00 and self.zeroCount >= self.zero_limit):
                    self.zeroCount = 0 if value[2] != 0 else self.zeroCount + 1
                    reported_speed = value[2]
                    topic = f"bike/{deviceId}/fan/status"
                    payload = json.dumps({
                        "value": reported_speed,
                        "unitName": "percentage",
                        "timestamp": time.time(),
                        "metadata": {"deviceName": platform.node()}
                    })
                    mqtt_client.publish(topic, payload)
                    print(f"Published speed: {reported_speed}")

def main():
    try:
        adapter_name = os.getenv('FAN_ADAPTER_NAME')
        alias_prefix = os.getenv('FAN_ALIAS_PREFIX')

        global mqtt_client, deviceId
        mqtt_client = MQTTClient(
            os.getenv('MQTT_HOSTNAME'),
            os.getenv('MQTT_USERNAME'),
            os.getenv('MQTT_PASSWORD')
        )
        mqtt_client.setup_mqtt_client()
        deviceId = os.getenv('DEVICE_ID')

        topic = f"bike/{deviceId}/fan/control"
        mqtt_client.subscribe(topic)
        mqtt_client.get_client().on_message = message
        mqtt_client.get_client().on_publish = publish
        mqtt_client.get_client().loop_start()

        global manager
        manager = AnyDeviceManager(adapter_name=adapter_name)
        manager.prefix = alias_prefix
        manager.start_discovery()
        manager.run()

    except KeyboardInterrupt:
        pass
    mqtt_client.get_client().loop_stop()

if __name__ == "__main__":
    main()
