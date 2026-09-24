#!/usr/bin/env python3
"""
Error codes for the Smart Bike VR IoT layer.

CODE BANDS
----------
    0000s    Success  - the command was carried out (0 = exactly as asked)
    1000s    Protocol - the message itself was not understood
    2000s    Validation - the message was understood but the value is invalid
    3000s    Device   - the bike hardware misbehaved, but the bike is STILL RUNNING
    4000s    Internal - something failed inside the bike software
    5000s-8000s  RESERVED - do not use
    9000s    Terminal - the bike is no longer available; stop sending commands

3000s VERSUS 9000s: both describe hardware problems. The difference is
recoverability. 3000s = still running, will accept further commands.
9000s = gone, further commands will not be actioned.

TWO RULES THAT MUST NOT BE BROKEN
1. Codes are APPEND-ONLY. A number's meaning is never changed and a retired
   number is never reused.
2. The 5000-8999 bands are reserved.

Codes 3003-3010 map one-to-one onto the exception classes already defined in
lib/gatt/errors.py, so that convention is extended rather than replaced.
"""

import logging
from enum import IntEnum

log = logging.getLogger(__name__)

_USING_FALLBACK_RANGES = False
try:
    from lib.constants import (INCLINE_MIN, INCLINE_MAX,
                               RESISTANCE_MIN, RESISTANCE_MAX,
                               FAN_MIN, FAN_MAX)
except ImportError:
    try:
        from Drivers.lib.constants import (INCLINE_MIN, INCLINE_MAX,
                                           RESISTANCE_MIN, RESISTANCE_MAX,
                                           FAN_MIN, FAN_MAX)
    except ImportError:
        _USING_FALLBACK_RANGES = True
        INCLINE_MIN, INCLINE_MAX = -10, 19
        RESISTANCE_MIN, RESISTANCE_MAX = 0, 100
        FAN_MIN, FAN_MAX = 0, 100
        log.warning(
            "lib.constants could not be imported - using built-in fallback "
            "ranges. These are copies, not the source of truth.")


class Severity:
    OK = "ok"
    WARNING = "warning"
    ERROR = "error"
    FATAL = "fatal"


class Code(IntEnum):
    # --- 0000s : success ---
    OK = 0
    VALUE_CLAMPED = 1
    NO_ACTION_TAKEN = 2

    # --- 1000s : protocol ---
    UNKNOWN_COMMAND = 1001
    MALFORMED_PAYLOAD = 1002
    MISSING_FIELD = 1003

    # --- 2000s : validation ---
    VALUE_OUT_OF_RANGE = 2001
    VALUE_WRONG_TYPE = 2002

    # --- 3000s : device (recoverable) ---
    DEVICE_DISCONNECTED = 3001
    DEVICE_NOT_RESPONDING = 3002
    DEVICE_NOT_READY = 3003              # errors.NotReady
    DEVICE_ACCESS_DENIED = 3004          # errors.AccessDenied
    DEVICE_NOT_AUTHORIZED = 3005         # errors.NotAuthorized
    DEVICE_NOT_PERMITTED = 3006          # errors.NotPermitted
    DEVICE_NOT_SUPPORTED = 3007          # errors.NotSupported
    DEVICE_INVALID_VALUE_LENGTH = 3008   # errors.InvalidValueLength
    DEVICE_OPERATION_IN_PROGRESS = 3009  # errors.InProgress
    DEVICE_FAILED = 3010                 # errors.Failed
    DEVICE_TIMEOUT = 3011

    # --- 4000s : internal ---
    COMMAND_FAILED = 4001
    RESOURCE_NOT_FOUND = 4002
    CONTROL_NOT_CONFIGURED = 4003

    # --- 9000s : terminal ---
    FATAL_DEVICE_FAILURE = 9001
    BIKE_OFFLINE = 9002
    BIKE_SHUTDOWN = 9003


MESSAGES = {
    Code.OK: "Command accepted",
    Code.VALUE_CLAMPED: "Command accepted, value adjusted to the permitted range",
    Code.NO_ACTION_TAKEN: "Already in the requested state, no action taken",
    Code.UNKNOWN_COMMAND: "Unknown command",
    Code.MALFORMED_PAYLOAD: "Payload could not be parsed",
    Code.MISSING_FIELD: "Required field missing from payload",
    Code.VALUE_OUT_OF_RANGE: "Value outside the permitted range",
    Code.VALUE_WRONG_TYPE: "Value is not of the expected type",
    Code.DEVICE_DISCONNECTED: "Bluetooth connection to the trainer was lost",
    Code.DEVICE_NOT_RESPONDING: "Trainer did not respond to the command",
    Code.DEVICE_NOT_READY: "Bluetooth adapter is not ready",
    Code.DEVICE_ACCESS_DENIED: "Access denied - root permissions required",
    Code.DEVICE_NOT_AUTHORIZED: "Not authorised to perform this operation",
    Code.DEVICE_NOT_PERMITTED: "Operation not permitted by the device",
    Code.DEVICE_NOT_SUPPORTED: "Operation not supported by the device",
    Code.DEVICE_INVALID_VALUE_LENGTH: "Value length rejected by the device",
    Code.DEVICE_OPERATION_IN_PROGRESS: "A device operation is already in progress",
    Code.DEVICE_FAILED: "Device operation failed",
    Code.DEVICE_TIMEOUT: "Timed out waiting for the device",
    Code.COMMAND_FAILED: "Command could not be carried out",
    Code.RESOURCE_NOT_FOUND: "Required file or resource was not found",
    Code.CONTROL_NOT_CONFIGURED: "No permitted range is configured for this control",
    Code.FATAL_DEVICE_FAILURE: "Bike has failed and cannot continue",
    Code.BIKE_OFFLINE: "Bike disconnected unexpectedly",
    Code.BIKE_SHUTDOWN: "Bike was shut down",
}

# Codes whose severity does not follow from their band.
SEVERITY_OVERRIDES = {
    Code.VALUE_CLAMPED: Severity.WARNING,
    Code.BIKE_SHUTDOWN: Severity.WARNING,
}

GATT_ERROR_CODES = {
    "NotReady": Code.DEVICE_NOT_READY,
    "AccessDenied": Code.DEVICE_ACCESS_DENIED,
    "NotAuthorized": Code.DEVICE_NOT_AUTHORIZED,
    "NotPermitted": Code.DEVICE_NOT_PERMITTED,
    "NotSupported": Code.DEVICE_NOT_SUPPORTED,
    "InvalidValueLength": Code.DEVICE_INVALID_VALUE_LENGTH,
    "InProgress": Code.DEVICE_OPERATION_IN_PROGRESS,
    "Failed": Code.DEVICE_FAILED,
    "TimeoutError": Code.DEVICE_TIMEOUT,
}


def code_for_gatt_error(error):
    """Map an exception from lib/gatt/errors.py to its numeric code."""
    return GATT_ERROR_CODES.get(type(error).__name__, Code.DEVICE_FAILED)


def severity_for(code):
    """Severity for a code: an explicit override, else derived from its band."""
    code = int(code)
    try:
        override = SEVERITY_OVERRIDES.get(Code(code))
        if override:
            return override
    except ValueError:
        pass
    if code < 1000:
        return Severity.OK
    if code >= 9000:
        return Severity.FATAL
    return Severity.ERROR


def name_for(code):
    """Stable symbolic name, e.g. 'VALUE_OUT_OF_RANGE'. Empty if unknown."""
    try:
        return Code(int(code)).name
    except ValueError:
        return ""


def message_for(code):
    """Default text for a code, or a safe fallback for unknown codes."""
    try:
        return MESSAGES[Code(int(code))]
    except (ValueError, KeyError):
        return f"Unrecognised error code {code}"


def is_success(code):
    """True if the command was carried out, even if the value was adjusted."""
    return int(code) < 1000


RANGES = {
    "incline": (float(INCLINE_MIN), float(INCLINE_MAX)),
    "resistance": (float(RESISTANCE_MIN), float(RESISTANCE_MAX)),
    "fan": (float(FAN_MIN), float(FAN_MAX)),
}


def validate_value(control, value, clamp=False):
    """
    Check a numeric control value.
    Returns (code, message, value). `value` is the number to actually apply.
    """
    if control not in RANGES:
        return (Code.CONTROL_NOT_CONFIGURED,
                f"No permitted range configured for control '{control}'", None)

    try:
        number = float(value)
    except (TypeError, ValueError):
        return Code.VALUE_WRONG_TYPE, f"'{value}' is not a number", None

    low, high = RANGES[control]
    if low <= number <= high:
        return Code.OK, None, number

    if clamp:
        clamped = low if number < low else high
        return (Code.VALUE_CLAMPED,
                f"{control} value {number} adjusted to {clamped} "
                f"(permitted range {low} to {high})", clamped)

    return (Code.VALUE_OUT_OF_RANGE,
            f"{control} value {number} out of range ({low} to {high})", None)