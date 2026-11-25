#!/usr/bin/env python3

import re
import os
import sys
#import gatt # this version lacks descriptors
import platform
import json
import time
from argparse import ArgumentParser
import threading
import logging

root_folder = os.path.abspath(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.append(root_folder)

from lib.mqtt_client import MQTTClient
from lib.ble_helper import convert_incline_to_op_value, service_or_characteristic_found, service_or_characteristic_found_full_match, decode_int_bytes, covert_negative_value_to_valid_bytes
from lib.constants import RESISTANCE_MIN, RESISTANCE_MAX, INCLINE_MIN, INCLINE_MAX, FAN_MIN, FAN_MAX, FTMS_UUID, FTMS_CONTROL_POINT_UUID, FTMS_REQUEST_CONTROL, FTMS_RESET, FTMS_SET_TARGET_RESISTANCE_LEVEL, INCLINE_REQUEST_CONTROL, INCLINE_CONTROL_OP_CODE, INCLINE_CONTROL_SERVICE_UUID, INCLINE_CONTROL_CHARACTERISTIC_UUID, INDOOR_BIKE_DATA_UUID, DEVICE_UNIT_NAMES, FTMS_SET_TARGET_FAN_SPEED
import lib.gatt.gatt_linux as gatt

"""
TODO:
    - integrate climb, resistance and WahooData code into KICKRDevice code
    - make WahooDevice more general to be applied to Fan and TICKR drivers
    - add critical error logging code
    - move argparse, manager, and device connect code to main()
"""

# setup logging

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

logger_formatter = logging.Formatter('%(levelname)s:%(name)s:%(message)s')

logger_file_handler = logging.FileHandler('wahoo.log') # TODO: setup a logging folder and write all logging files to that folder
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

# define Control Point response type constants
WRITE_SUCCESS, WRITE_FAIL, NOTIFICATION_SUCCESS, NOTIFICATION_FAIL = range(4)

# ======== GATT Device Manager Class ========

# FIXME: make this compatible with all devices
# TODO: find a better method - maybe just note the MAC address (dah)
#       This method requires initialising the device inside the manager which seems to be an unintended use for the manager
#       Just create some MAC address discovery script instead and the MAC addresses can be hardcoded.
"""class WahooManager(gatt.DeviceManager):
    # Subclass gatt.DeviceManager to allow discovery only of HEADWIND devices
    # When the alias begins with the required prefix, connect to the device
    def device_discovered(self, device):
        alias = device.alias()
        if alias is not None and self.prefix is not None and len(alias) >= len(self.prefix) and alias[0:len(self.prefix)] == self.prefix:
            #print("[%s] Discovered, alias = %s" % (device.mac_address, device.alias()))
            device = AnyDevice(mac_address=device.mac_address, manager=self)
            device.connect()
            device.zero_limit = 10
            device.zeroCount = 0
            self.stop_discovery()"""

# extend on_message method to pass messages to device
class DeviceMQTTClient(MQTTClient):
    def __init__(self, broker_address, username, password, device, port=1883):
        super().__init__(broker_address, username, password, port=port)
        self.device = device

    def on_message(self, client, userdata, msg):
        super().on_message(client, userdata, msg)
        self.device.on_message(msg)

# ======== GATT Interface Class ========

class WahooDevice(gatt.Device):
    """This class should handle GATT functionality, including:
    * Connection
    * Response logging
    """

    def __init__(self, mac_address, manager, args, managed=True):
        super().__init__(mac_address, manager, managed)

        # CLI parser arguments
        self.args = args

        # MQTT client
        self.setup_mqtt_client()

    def set_service_or_characteristic(self, service_or_characteristic):
        """Match services and characteristics using their UUIDs
        
        virtual method to be implemented by subclass"""
        pass

    # ====== Log connection & characteristic update ======

    def connect_succeeded(self):
        super().connect_succeeded()
        logger.info("[%s] Connected" % (self.mac_address))

    def connect_failed(self, error):
        super().connect_failed(error)
        logger.debug("[%s] Connection failed: %s" % (self.mac_address, str(error)))
        sys.exit()

    def disconnect_succeeded(self):
        super().disconnect_succeeded()
        logger.info("[%s] Disconnected" % (self.mac_address))

    def characteristic_value_updated(self, characteristic, value):
        logger.debug(f"The updated value for {characteristic.uuid} is: {value}")

    # ====== Control Point Response Methods ======

    def control_point_response(self, characteristic, response_type: int, error = None):
        """Handle responses from indicated control points
        
        virutal method to be implemented by subclass"""
        pass

    def characteristic_write_value_succeeded(self, characteristic):
        logger.debug(f"A new value has been written to {characteristic.uuid}")
        self.control_point_response(characteristic,response_type=WRITE_SUCCESS)

    def characteristic_write_value_failed(self, characteristic, error):
        logger.debug(f"A new value has not been written to {characteristic.uuid} successfully: {str(error)}")
        self.control_point_response(characteristic,response_type=WRITE_FAIL,error=error)

    def characteristic_enable_notification_succeeded(self, characteristic):
        logger.debug(f"The {characteristic.uuid} has been enabled with notification!")
        self.control_point_response(characteristic,response_type=NOTIFICATION_SUCCESS)

    def characteristic_enable_notification_failed(self, characteristic, error):
        logger.debug(f"Cannot enable notification for {characteristic.uuid}: {str(error)}")
        self.control_point_response(characteristic,response_type=NOTIFICATION_FAIL,error=error)

    # ===== MQTT methods =====
    
    def setup_mqtt_client(self):
        self.mqtt_client = DeviceMQTTClient(self.args.broker_address, self.args.username, self.args.password, self, port=self.args.port)
        self.mqtt_client.setup_mqtt_client()

    def subscribe(self, topic: str, SubscribeOptions: int = 0):
        """Subscribe to a MQTT topic"""
        self.mqtt_client.subscribe([(topic, SubscribeOptions)])

    def publish(self, topic: str, payload):
        """Publish to a MQTT topic"""
        self.mqtt_client.publish(topic, payload)
    
    def mqtt_data_report_payload(self, device_type, value):
        """Create a standardised payload for MQTT publishing"""
        return json.dumps({"value": value, "unitName": DEVICE_UNIT_NAMES[device_type], "timestamp": time.time(), "metadata": { "deviceName": platform.node() } })
    
    # ====== Request & Resolve control point
    def services_resolved(self):
        super().services_resolved()

        print("[%s] Resolved services" % (self.mac_address))
        for service in self.services:
            print("[%s]\tService [%s]" % (self.mac_address, service.uuid))
            self.set_service_or_characteristic(service)

            for characteristic in service.characteristics:
                self.set_service_or_characteristic(characteristic)
                print("[%s]\t\tCharacteristic [%s]" % (self.mac_address, characteristic.uuid))
                if characteristic.read_value() != None:
                    print("The characteristic value is: ", characteristic.read_value())
        
        # start looping MQTT messages
        self.mqtt_client.loop_start()

# ======== Wahoo Controller Class ========

class KICKRDevice(WahooDevice):
    """This sub-class should extend the GATTInterface class to also handle:
    * MQTT [or any alternative networking protocols]
    * Individual Wahoo devices
    * Pulling data from devices"""

    def __init__(self, mac_address, manager, args, managed=True):
        super().__init__(mac_address, manager, args, managed)

        # Fitness Machine Service device & control point
        self.ftms = None
        self.ftms_control_point = None

        # bike data characteristic
        self.indoor_bike_data = None

        # Wahoo sub-devices
        self.climber = Climber(self,args)
        self.resistance = Resistance(self,args)

        self.devices = [self.climber, self.resistance]

        # Wahoo data handler
        self.wahoo_data = WahooData(self,args)

    # ===== MQTT method for device ======

    def on_message(self, msg):
        """Run when a subscribed MQTT topic publishes"""
        for device in self.devices:
            device.on_message(msg)

    # ===== GATT for devices =====

    def set_service_or_characteristic(self, service_or_characteristic):
        super().set_service_or_characteristic(service_or_characteristic)

        # find services & characteristics of the KICKR trainer
        if service_or_characteristic_found(FTMS_UUID, service_or_characteristic.uuid):
            self.ftms = service_or_characteristic
            logger.info('FTMS service found')
        elif service_or_characteristic_found(FTMS_CONTROL_POINT_UUID, service_or_characteristic.uuid):
            self.ftms_control_point = service_or_characteristic
            self.ftms_control_point.write_value(bytearray([FTMS_REQUEST_CONTROL])) # request control point
            logger.info('CONTROL POINT characteristic found')
        elif service_or_characteristic_found(INDOOR_BIKE_DATA_UUID, service_or_characteristic.uuid):
            self.indoor_bike_data = service_or_characteristic
            logger.info('INDOOR BIKE DATA characteristic found')
            self.indoor_bike_data.enable_notifications()

        for device in self.devices:
            device.set_control_point(service_or_characteristic)

    def characteristic_value_updated(self, characteristic, value):
        super().characteristic_value_updated(characteristic,value)

        if characteristic == self.indoor_bike_data:
            self.wahoo_data.process_data(value)

    def control_point_response(self, characteristic, response_type: int, error = None):
        """forward responses and their types to devices"""

        # TODO: handle responses from own control point
        
        # forward responses
        for device in self.devices:
            device.control_point_response(characteristic, response_type, error)

# ======== KICKR sub-device Classes ========

class SubDevice:
    """Class for sub-device functionality like the KICKR Climb's incline control, KICKR smart trainer's resistance control"""

    def __init__(self, name: str, controller: KICKRDevice, command_topic: str, report_topic: str):
        """
        Create a Wahoo Device

        Parameters
        ----------
        name : str 
            Name of the device for logging. Will be automatically converted to all upper case.
        controller : WahooController 
            The WahooController object which will handle the device.
        command_topic : str
            MQTT topic used to control device. Should be passed using ArgumentParser.
        report_topic : str
            MQTT topic used for device to report current status. Should be passed using ArgumentParser.
        """

        # device controller
        self.controller = controller

        # device name for logging
        self._name = name.upper()

        # command topic
        self.command_topic = command_topic
        self.controller.subscribe(self.command_topic)

        # report topic
        self.report_topic = report_topic

        # device control point service & characteristic
        self.control_point_service = None
        self.control_point = None

        # hold value while writing
        self._internal_value = None # internal device value for tracking physical device value
        self._new_internal_value = None # human readable value for logging
        self._new_write_value = None # byte array value to be written to control point

        # threading variables
        self._TIMEOUT = 10
        self.terminate_write = False
        self.write_timeout_count = 0
        self.write_thread = None

        # log device status & info
        logger.info(f'{self._name} initialised')
        logger.debug(f'{self._name} command topic is {self.command_topic}')

    def set_control_point(self, service_or_characteristic):
        """Set UUID of passed service/characteristic if it is a required control point service/characteristic

        To be implemented by subclass"""
        pass

    def on_message(self, msg):
        """Receive subscribed MQTT messages

        To be implemented by subclass"""
        pass

    # TODO: change this to report overall status of device
    def report(self):
        """Report a successful value write"""
        payload = self.controller.mqtt_data_report_payload(self._name.lower(),self._internal_value)
        self.controller.publish(self.report_topic,payload)

    def control_point_response(self, characteristic, response_type: int, error = None):
        """Handle responses from the control point"""

        # return if the device's control point has not been set
        if self.control_point is None: return

        # if the response is not from the relevant control point then return
        if characteristic.uuid != self.control_point.uuid: return

        # on successful write terminate the thread and update the internal device value
        if response_type == WRITE_SUCCESS: 
            # TODO: LOCK this property at start of method
            self.terminate_write = True
            self._internal_value = self._new_internal_value

            # report & log a successful write
            self.report()
            logger.debug(f'{self._name} WRITE SUCCESS: {self._new_internal_value}') 
        
        # on failed write try writing again until timeout
        elif response_type == WRITE_FAIL:
            self.write_timeout_count += 1
            logger.debug(f'{self._name} WRITE FAILED: {self._new_internal_value}')

        # on successful enabling of notification on control point log
        elif response_type == NOTIFICATION_SUCCESS:
            logger.debug(f'{self._name} NOTIFICATION SUCCESS')

        # on fail to enable notification on control point try again
        elif response_type == NOTIFICATION_FAIL:
            logger.debug(f'{self._name} NOTIFICATION FAILED')
            self.control_point.enable_notifications() 

    def write_value(self,val):
        """Try to write a new device value until timeout, success or recieve new value to be written"""

        # define the new value internally
        self._new_write_value = val

        # terminate any current threads
        # TODO: LOCK this property at start of method
        self.terminate_write = True
        if self.write_thread != None: self.write_thread.join()

        # setup & start new thread
        self.terminate_write = False
        self.write_timeout_count = 0
        self.write_thread = threading.Thread(name=f'{self._name}_write',target=self.write_process)
        self.write_thread.start()
        
    def write_process(self):
        """Attempt to write the new device value until successful or forced to terminate"""

        # write the new value until termination or timeout
        if not (self.terminate_write and self.write_timeout_count >= self._TIMEOUT):
            self.control_point.write_value(self._new_write_value)

class Climber(SubDevice):
    """Handles control of the KICKR Climb"""

    def __init__(self, controller: KICKRDevice, args):
        super().__init__('CLIMBER',controller,args.incline_command_topic,args.incline_report_topic)

    def set_control_point(self, service_or_characteristic):
        
        # find the custom KICKR climb control point service & characteristic
        if service_or_characteristic_found_full_match(INCLINE_CONTROL_SERVICE_UUID, service_or_characteristic.uuid):
            self.control_point_service = service_or_characteristic
            logger.debug(f'{self._name} service found')

        elif service_or_characteristic_found_full_match(INCLINE_CONTROL_CHARACTERISTIC_UUID, service_or_characteristic.uuid):
            self.control_point = service_or_characteristic
            logger.debug(f'{self._name} characteristic found')
            self.control_point.enable_notifications() 

    def on_message(self, msg):
        """Receive MQTT messages"""
        
        # check if it is the incline topic
        if bool(re.search("/incline/control", msg.topic, re.IGNORECASE)):

            logger.info(f'{self._name} MQTT message received')
            logger.debug(f'Received Climber Message: {msg}')

            # convert, validate, and write the new value
            value = str(msg.payload, 'utf-8')

            # TODO: add error checking and reporting for converting from str to dict
            value = json.loads(value)
            value = value['incline']
            if INCLINE_MIN <= value <= INCLINE_MAX and value % 0.5 == 0:
                self._new_internal_value = value
                self.write_value(bytearray([INCLINE_CONTROL_OP_CODE] + convert_incline_to_op_value(self._new_internal_value)))
            else:
                logger.info(f'{self._name} MQTT COMMAND FAIL : value must be in range 19 to -10 with 0.5 resolution : {value}')
                # TODO: report error
            # TODO: check and report other errors like wrong value type


class Resistance(SubDevice):
    """Handles control of the Resistance aspect of the KICKR Smart Trainer"""

    def __init__(self, controller: KICKRDevice, args):
        super().__init__('Resistance',controller,args.resistance_command_topic,args.resistance_report_topic)

    def set_control_point(self, service_or_characteristic):

        # setup aliases for the FTMS control point service & characteristic
        self.control_point_service = self.controller.ftms
        self.control_point = self.controller.ftms_control_point
    
    def on_message(self, msg):
        """Receive MQTT messages"""

        # check if it is the resistance topic
        if bool(re.search("/resistance/control", msg.topic, re.IGNORECASE)):

            logger.info(f'{self._name} MQTT message received')

            # convert, validate, and write the new value
            value = str(msg.payload, 'utf-8')

            # TODO: add error checking and reporting for converting from str to dict
            value = json.loads(value)
            value = float(value['resistance'])
            if RESISTANCE_MIN <= value <= RESISTANCE_MAX:
                self._new_internal_value = value
                self.write_value(bytearray([FTMS_SET_TARGET_RESISTANCE_LEVEL, int(self._new_internal_value)])) # FIXME: Should be able to write as a float but temp rounding to int
            else:
                logger.info(f'{self._name} MQTT COMMAND FAIL : value must be an integer between 0 and 100 : {value}')
                # TODO: report error

class WahooData:

    def __init__(self, controller: KICKRDevice, args):
        """Pulls data from the KICKR"""
        
        # device controller
        self.controller = controller

        # CLI parser arguments
        self.args = args

        # track if bike is new data
        self.idle = False

        # data flags
        """Many of these are for Wahoo devices that we are not using/do not have"""
        self.flag_instantaneous_speed = None
        self.flag_average_speed = None
        self.flag_instantaneous_cadence = None
        self.flag_average_cadence = None
        self.flag_total_distance = None
        self.flag_resistance_level = None
        self.flag_instantaneous_power = None
        self.flag_average_power = None
        self.flag_expended_energy = None
        self.flag_heart_rate = None
        self.flag_metabolic_equivalent = None
        self.flag_elapsed_time = None
        self.flag_remaining_time = None

        # data values
        self.instantaneous_speed = None
        self.average_speed = None
        self.instantaneous_cadence = None
        self.average_cadence = None
        self.total_distance = None
        self.resistance_level = None
        self.instantaneous_power = None
        self.average_power = None
        self.expended_energy_total = None
        self.expended_energy_per_hour = None
        self.expended_energy_per_minute = None
        self.heart_rate = None
        self.metabolic_equivalent = None
        self.elapsed_time = None
        self.remaining_time = None

    def process_data(self, value):
        self.reported_data(value)
        self.pull_value(value)
        self.publish_data()

    def reported_data(self, value):
        """Check the received bit data for which data was reported"""
        self.flag_instantaneous_speed = not((value[0] & 1) >> 0)
        self.flag_average_speed = (value[0] & 2) >> 1
        self.flag_instantaneous_cadence = (value[0] & 4) >> 2
        self.flag_average_cadence = (value[0] & 8) >> 3
        self.flag_total_distance = (value[0] & 16) >> 4
        self.flag_resistance_level = (value[0] & 32) >> 5
        self.flag_instantaneous_power = (value[0] & 64) >> 6
        self.flag_average_power = (value[0] & 128) >> 7
        self.flag_expended_energy = (value[1] & 1) >> 0
        self.flag_heart_rate = (value[1] & 2) >> 1
        self.flag_metabolic_equivalent = (value[1] & 4) >> 2
        self.flag_elapsed_time = (value[1] & 8) >> 3
        self.flag_remaining_time = (value[1] & 16) >> 4

    def pull_value(self, value):
        """Get the reported data from the bit data"""
        offset = 2

        if self.flag_instantaneous_speed:
            self.instantaneous_speed = float((value[offset+1] << 8) + value[offset]) / 100.0 * 5.0 / 18.0
            offset += 2
            logger.debug(f"Instantaneous Speed: {self.instantaneous_speed} m/s")

        if self.flag_average_speed:
            self.average_speed = float((value[offset+1] << 8) + value[offset]) / 100.0 * 5.0 / 18.0
            offset += 2
            logger.debug(f"Average Speed: {self.average_speed} m/s")

        if self.flag_instantaneous_cadence:
            self.instantaneous_cadence = float((value[offset+1] << 8) + value[offset]) / 10.0
            offset += 2
            logger.debug(f"Instantaneous Cadence: {self.instantaneous_cadence} rpm")

        if self.flag_average_cadence:
            self.average_cadence = float((value[offset+1] << 8) + value[offset]) / 10.0
            offset += 2
            logger.debug(f"Average Cadence: {self.average_cadence} rpm")

        if self.flag_total_distance:
            self.total_distance = int((value[offset+2] << 16) + (value[offset+1] << 8) + value[offset])
            offset += 3
            logger.debug(f"Total Distance: {self.total_distance} m")

        if self.flag_resistance_level:
           self.resistance_level = int((value[offset+1] << 8) + value[offset])
           offset += 2
           logger.debug(f"Resistance Level: {self.resistance_level}")

        if self.flag_instantaneous_power:
            self.instantaneous_power = int((value[offset+1] << 8) + value[offset])
            offset += 2
            logger.debug(f"Instantaneous Power: {self.instantaneous_power} W")

        if self.flag_average_power:
            self.average_power = int((value[offset+1] << 8) + value[offset])
            offset += 2
            logger.debug(f"Average Power: {self.average_power} W")

        if self.flag_expended_energy:
            expended_energy_total = int((value[offset+1] << 8) + value[offset])
            offset += 2
            if expended_energy_total != 0xFFFF:
                self.expended_energy_total = expended_energy_total
                logger.debug(f"Expended Energy: {self.expended_energy_total} kCal total")

            expended_energy_per_hour = int((value[offset+1] << 8) + value[offset])
            offset += 2
            if expended_energy_per_hour != 0xFFFF:
                self.expended_energy_per_hour = expended_energy_per_hour
                logger.debug(f"Expended Energy: {self.expended_energy_per_hour} kCal/hour")

            expended_energy_per_minute = int(value[offset])
            offset += 1
            if expended_energy_per_minute != 0xFF:
                self.expended_energy_per_minute = expended_energy_per_minute
                logger.debug(f"Expended Energy: {self.expended_energy_per_minute} kCal/min")

        if self.flag_heart_rate:
            self.heart_rate = int(value[offset])
            offset += 1
            logger.debug(f"Heart Rate: {self.heart_rate} bpm")

        if self.flag_metabolic_equivalent:
            self.metabolic_equivalent = float(value[offset]) / 10.0
            offset += 1
            logger.debug(f"Metabolic Equivalent: {self.metabolic_equivalent} METS")

        if self.flag_elapsed_time:
            self.elapsed_time = int((value[offset+1] << 8) + value[offset])
            offset += 2
            logger.debug(f"Elapsed Time: {self.elapsed_time} seconds")

        if self.flag_remaining_time:
            self.remaining_time = int((value[offset+1] << 8) + value[offset])
            offset += 2
            logger.debug(f"Remaining Time: {self.remaining_time} seconds")

        if offset != len(value):
            logger.info("ERROR: Payload was not parsed correctly")
            return
        
    def publish_data(self):
        """Publish if data or log that there was no relevant data"""

        if self.instantaneous_cadence > 0 or self.instantaneous_cadence > 0:
            self.idle = False
            self.publish()
        else:
            if not self.idle:
                self.publish()
                self.idle = True

    def publish(self):
        """Publish data"""

        if self.flag_instantaneous_speed:
            self.controller.publish(self.args.speed_report_topic, self.controller.mqtt_data_report_payload('speed', self.instantaneous_speed))
        if self.flag_instantaneous_cadence:
            self.controller.mqtt_client.publish(self.args.cadence_report_topic, self.controller.mqtt_data_report_payload('cadence', self.instantaneous_cadence))
        if self.flag_instantaneous_power:
            self.controller.mqtt_client.publish(self.args.power_report_topic, self.controller.mqtt_data_report_payload('power', self.instantaneous_power))

# ======== TICKR Heart Rate Monitor driver ========

class TICKRDevice(WahooDevice):

    def __init__(self, mac_address, manager, args, managed=True):
        super().__init__(mac_address, manager, args, managed)

        # define service & characteristic
        self.heart_rate_service = None
        self.heart_rate_measurement_characteristic = None

    def set_service_or_characteristic(self, service_or_characteristic):
        super().set_service_or_characteristic(service_or_characteristic)

        if service_or_characteristic.uuid[4:8] == '180d':
            self.heart_rate_service = service_or_characteristic

        if service_or_characteristic.uuid[4:8] == '2a37':
            self.heart_rate_measurement_characteristic = service_or_characteristic
            self.heart_rate_measurement_characteristic.enable_notifications()
    
    def characteristic_value_updated(self, characteristic, value):

        # return if not TICKR characteristic
        if characteristic.uuid != self.heart_rate_measurement_characteristic.uuid: return

        # Store the timestamp
        ts = time.time()

        # Check the flags
        hr16bit = value[0] & 1
        sensorcontact = (value[0] & 6) >> 1
        energyexpended = (value[0] & 8) >> 3
        rrinterval = (value[0] & 16) >> 4

        # Offset is the current byte in the packet being processed
        offset = 1

        # Parse the heartrate
        if hr16bit:
            heartrate = (value[offset+1] << 8) + value[offset]
            offset += 2
        else:
            heartrate = value[offset]
            offset += 1

        #check for zero heartrate and if limit reached
        if not(heartrate == 0 and self.zeroCount >= self.zero_limit):
            # Parse the sensor contact information (if present)
            if sensorcontact == 2:
                contact = "Not detected"
            elif sensorcontact == 3:
                contact = "Detected"
            else:
                contact = None

            #Parse heartrate to check if 0
            if heartrate == 0:
                self.zeroCount += 1
            else:
                self.zeroCount = 0

            # Parse the energy expended (if present)
            if energyexpended:
                energy = (value[offset+1] << 8) + value[offset]
                offset += 2
            else:
                energy = None

            # Parse the RR interval(s) (if present)
            # If several intervals have occurred since the last measurement
            # they are sent from oldest to newest
            if rrinterval:
                interval = []
                for index in range(offset, len(value), 2):
                    interval.append(float((value[index+1] << 8) + value[index])/1024.0)
                offset = len(value)
            else:
                interval = None

            # publish measure
            payload = self.mqtt_data_report_payload(heartrate, ts)
            self.publish(self.args.heartrate_report_topic, payload)

    def mqtt_data_report_payload(self, value, timestamp):
        return json.dumps({"value": value, "unitName": 'BPM', "timestamp": timestamp, "metadata": { "deviceName": platform.node() } }) 

"""
FIXME: the fan code needs a total rewrite
- The characteristics and values written to them are undocumented.
- There is no real flow control - values are rewritten multiple times in the hope that the value write will succeed.
"""
class HeadwindFan(WahooDevice):

    def __init__(self, mac_address, manager, args, managed=True):
        super().__init__(mac_address, manager, args, managed)

        # define services & characteristics
        self.enable_service = None
        self.enable_characteristic = None
        self.fan_service = None
        self.fan_characteristic = None

        # write counts for "flow control"
        self.enableCount = 0
        self.startCount = 0
        self.sendCount = 0

    def on_message(self, msg):

        # ignore if message is not from fan control topic
        if not bool(re.search("/fan/control", msg.topic, re.IGNORECASE)): return

        # extract value from payload
        payload = msg.payload.decode("utf-8")
        dict_of_payload = json.loads(payload)
        fan_power = int(dict_of_payload["value"])

        # abort if the value is not within 0% to 100%
        if not (0 <= fan_power <= 100): return

        # write new fan power value
        if self.enableCount < 3:
            value = bytes([0x20, 0xee, 0xfc])
            self.enable_characteristic.write_value(value)
        elif self.startCount < 3:
            value = bytes([0x04, 0x04])
            self.fan_characteristic.write_value(value)
        else:
            value = bytes([0x02, self.speed])
            self.fan_characteristic.write_value(value)

    def characteristic_write_value_succeeded(self, characteristic):
        # repeat writes to increase chances of successful write
        # FIXME: implement proper flow control using the control point responses
        if characteristic == self.enable_characteristic:
            if self.enableCount < 3:
                value = bytes([0x20, 0xee, 0xfc])
                self.enable_characteristic.write_value(value)
                self.enableCount+=1
            elif self.startCount < 3:
                value = bytes([0x04, 0x04])
                self.fan_characteristic.write_value(value)
                self.startCount+=1
        if characteristic == self.fan_characteristic:
            if self.startCount < 3:
                value = bytes([0x04, 0x04])
                self.fan_characteristic.write_value(value)
                self.startCount+=1
            elif self.sendCount < 3:
                value = bytes([0x02, self.speed])
                self.fan_characteristic.write_value(value)
                self.sendCount = self.sendCount + 1
                if self.sendCount == 3:
                    print(f"Speed set to {self.speed}")
    
    def set_service_or_characteristic(self, service_or_characteristic):
        super().set_service_or_characteristic(service_or_characteristic)

        if service_or_characteristic.uuid[4:8] == 'ee01':
            self.enable_service = service_or_characteristic
        
        elif service_or_characteristic.uuid[4:8] == 'e002':
            self.enable_characteristic = service_or_characteristic
            self.enable_characteristic.enable_notifications()
            value = bytes([0x20, 0xee, 0xfc])
            self.enable_characteristic.write_value(value)
        
        elif service_or_characteristic.uuid[4:8] == 'ee0c':
            self.fan_service = service_or_characteristic
        
        elif service_or_characteristic.uuid[4:8] == 'e038':
            self.fan_characteristic = service_or_characteristic
            self.fan_characteristic.enable_notifications()


# ======== Main Process ========

def main():
    # define CLI parse arguments
    parser = ArgumentParser(description="Wahoo Device Controller")

    # BLE connection params
    parser.add_argument('--kickr_mac_address', dest='kickr_mac_address', type=str, help="The KICKR smart trainer's mac address", default=os.getenv('KICKR_MAC_ADDRESS'))
    parser.add_argument('--tickr_mac_address', dest='tickr_mac_address', type=str, help="The TICKR heart rate monitor's mac address", default=os.getenv('TICKR_MAC_ADDRESS'))
    parser.add_argument('--fan_mac_address', dest='fan_mac_address', type=str, help="The headwind fan's mac address", default=os.getenv('FAN_MAC_ADDRESS'))

    # MQTT connection params
    parser.add_argument('--broker_address', dest='broker_address', type=str, help='The MQTT broker address', default=os.getenv('MQTT_HOSTNAME'))
    parser.add_argument('--username', dest='username', type=str, help='username', default=os.getenv('MQTT_USERNAME'))
    parser.add_argument('--password', dest='password', type=str, help='password', default=os.getenv('MQTT_PASSWORD'))
    parser.add_argument('--port', dest='port', type=int, help='port', default=int(os.getenv('MQTT_PORT', '1883')))

    DEVICE_ID = os.getenv('DEVICE_ID')

    parser.add_argument('--incline_command_topic', dest='incline_command_topic', type=str, help='a MQTT topic that will send incline control commands to this driver', default=f'bike/{DEVICE_ID}/incline/control')
    parser.add_argument('--incline_report_topic', dest='incline_report_topic', type=str, help='a MQTT topic that will receieve the current incline levels data from this driver', default=f'bike/{DEVICE_ID}/incline/report')
    parser.add_argument('--resistance_command_topic', dest='resistance_command_topic', type=str, help='a MQTT topic that will send resistance control commands to this driver', default=f'bike/{DEVICE_ID}/resistance/control')
    parser.add_argument('--resistance_report_topic', dest='resistance_report_topic', type=str, help='a MQTT topic that will receieve the current resistance levels data from this driver', default=f'bike/{DEVICE_ID}/resistance/report')
    parser.add_argument('--fan_command_topic', dest='fan_command_topic', type=str, help='a MQTT topic that will send fan control commands to this driver', default=f'bike/{DEVICE_ID}/fan/control')
    parser.add_argument('--fan_report_topic', dest='fan_report_topic', type=str, help='a MQTT topic that will receieve the current incline or resistance levels data from this driver', default=f'bike/{DEVICE_ID}/fan/report')
    parser.add_argument('--speed_report_topic', dest='speed_report_topic', type=str, help='a MQTT topic that will receive the current instantaneous speed data in m/s from this driver', default=f'bike/{DEVICE_ID}/speed')
    parser.add_argument('--cadence_report_topic', dest='cadence_report_topic', type=str, help='a MQTT topic that will receive the current instantaneous cadence data in rpm from this driver', default=f'bike/{DEVICE_ID}/cadence')
    parser.add_argument('--power_report_topic', dest='power_report_topic', type=str, help='a MQTT topic that will receive the current instantaneous power data in W from this driver', default=f'bike/{DEVICE_ID}/power')
    parser.add_argument('--heartrate_report_topic', dest='heartrate_report_topic', type=str, help='a MQTT topic that will receive the current heart rate data in BPM from this driver', default=f'bike/{DEVICE_ID}/heartrate')

    args = parser.parse_args()

    print("Connecting to the BLE device...")
    manager = gatt.DeviceManager(adapter_name='hci0')

    # initialise the KICKR, TICKR, and Fan drivers
    kickr = KICKRDevice(args.kickr_mac_address, manager, args)
    tickr = TICKRDevice(args.tickr_mac_address, manager, args)
    headwind_fan = HeadwindFan(args.fan_mac_address, manager, args)

    # connect to the devices
    manager.start_discovery()
    logger.info('connecting to KICKR')
    kickr.connect()
    logger.info('connecting to TICKR')
    tickr.connect()
    logger.info('connecting to Headwind Fan')
    headwind_fan.connect()
    manager.stop_discovery()

    try:
        print("Running the device manager now...")
        # run the device manager in the main thread forever
        manager.run()
    except KeyboardInterrupt:
        print ('Exit the program.')
        manager.stop()
        sys.exit(0)

if __name__ == '__main__':
    main()