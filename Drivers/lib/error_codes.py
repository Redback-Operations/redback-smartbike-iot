#!/usr/bin/env python3
"""
Error codes for the Smart Bike VR IoT layer.

Single source of truth. Every component that raises or consumes an error should
import from this module rather than hardcoding numbers or message strings.

CODE BANDS
----------
    0000s    Success  - the command was carried out (0 = exactly as asked)
    1000s    Protocol - the message itself was not understood
    2000s    Validation - the message was understood but the value is invalid
    3000s    Device   - the bike hardware misbehaved, but the bike is STILL RUNNING
    4000s    Internal - something failed inside the bike software
    5000s    RESERVED - do not use
    6000s    RESERVED - do not use
    7000s    RESERVED - do not use
    8000s    RESERVED - do not use
    9000s    Terminal - the bike is no longer available; stop sending commands

An application can therefore branch on the band alone:

    if code >= 9000:
        stop_using_bike()
    elif code >= 1000:
        report_failure(message)
    else:
        command_succeeded()

3000s VERSUS 9000s
------------------
Both describe hardware problems. The difference is recoverability:

    3000s  the bike is still running and will accept further commands
    9000s  the bike is gone; further commands will not be actioned

TWO RULES THAT MUST NOT BE BROKEN
---------------------------------
1. Codes are APPEND-ONLY. A number's meaning is never changed and a retired
   number is never reused. Consumers hardcode these values, so redefining one
   silently breaks every application still using the old meaning.
2. The 5000-8999 bands are reserved. Do not allocate from them without
   agreement, or two teams will invent incompatible meanings for the same
   number.

CONSISTENCY WITH THE EXISTING CODEBASE
--------------------------------------
lib/gatt/errors.py already defines named exception classes for BLE failures.
That convention is kept: codes 3003-3010 map one-to-one onto those classes, so
nothing is renamed. This module adds the numeric layer needed to communicate
errors to applications that cannot see Python exceptions.

Permitted value ranges are NOT redefined here - they are imported from
lib/constants.py, which is already the single source of truth for them.
"""

import logging
from enum import IntEnum

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Ranges and workout names come from the existing lib/constants.py.
# The fallback below exists only so this module can be imported and tested
# standalone; it warns loudly rather than failing silently, because silently
# validating against the wrong numbers is worse than not running at all.
# ---------------------------------------------------------------------------
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
            "ranges (incline %s..%s, resistance %s..%s, fan %s..%s). These are "
            "copies, not the source of truth. Do not rely on them in "
            "production.",
            INCLINE_MIN, INCLINE_MAX, RESISTANCE_MIN, RESISTANCE_MAX,
            FAN_MIN, FAN_MAX)


class Severity:
    """Coarse handling hint, so consumers need not know every code."""
    OK = "ok"
    WARNING = "warning"
    ERROR = "error"
    FATAL = "fatal"


class Code(IntEnum):
    # --- 0000s : success ---------------------------------------------------
    OK = 0                      # carried out exactly as requested
    VALUE_CLAMPED = 1           # carried out, but the value was adjusted
    NO_ACTION_TAKEN = 2         # already in the requested state

    # --- 1000s : protocol --------------------------------------------------
    UNKNOWN_COMMAND = 1001
    MALFORMED_PAYLOAD = 1002
    MISSING_FIELD = 1003

    # --- 2000s : validation ------------------------------------------------
    VALUE_OUT_OF_RANGE = 2001
    VALUE_WRONG_TYPE = 2002

    # --- 3000s : device (recoverable) --------------------------------------
    DEVICE_DISCONNECTED = 3001
    DEVICE_NOT_RESPONDING = 3002
    DEVICE_NOT_READY = 3003             # errors.NotReady
    DEVICE_ACCESS_DENIED = 3004         # errors.AccessDenied
    DEVICE_NOT_AUTHORIZED = 3005        # errors.NotAuthorized
    DEVICE_NOT_PERMITTED = 3006         # errors.NotPermitted
    DEVICE_NOT_SUPPORTED = 3007         # errors.NotSupported
    DEVICE_INVALID_VALUE_LENGTH = 3008  # errors.InvalidValueLength
    DEVICE_OPERATION_IN_PROGRESS = 3009  # errors.InProgress
    DEVICE_FAILED = 3010                # errors.Failed
    DEVICE_TIMEOUT = 3011               # waited for the device and gave up

    # --- 4000s : internal --------------------------------------------------
    COMMAND_FAILED = 4001
    RESOURCE_NOT_FOUND = 4002
    CONTROL_NOT_CONFIGURED = 4003       # bike has no range defined for it

    # --- 5000s-8000s : RESERVED, do not allocate ---------------------------

    # --- 9000s : terminal --------------------------------------------------
    FATAL_DEVICE_FAILURE = 9001
    BIKE_OFFLINE = 9002                 # dropped out unexpectedly
    BIKE_SHUTDOWN = 9003                # stopped deliberately, not a fault


#: Default human-readable text. Callers may override with something more
#: specific; these exist so no code is ever published without a message.
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

#: Codes whose severity does not follow from their band.
#: VALUE_CLAMPED succeeded but changed the request, so it warns rather than
#: reports OK. BIKE_SHUTDOWN makes the bike unavailable but is not a fault.
SEVERITY_OVERRIDES = {
    Code.VALUE_CLAMPED: Severity.WARNING,
    Code.BIKE_SHUTDOWN: Severity.WARNING,
}


# ---------------------------------------------------------------------------
# Bridge from the existing BLE exception classes to numeric codes.
# Keyed by class name so this module does not need to import the gatt package
# (which requires dbus and only installs on Linux).
# ---------------------------------------------------------------------------
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
    """
    Map an exception from lib/gatt/errors.py to its numeric code.

    Anything unrecognised becomes DEVICE_FAILED, matching the behaviour of
    _error_from_dbus_error() in gatt_linux.py, which also falls back to Failed.
    """
    return GATT_ERROR_CODES.get(type(error).__name__, Code.DEVICE_FAILED)


def severity_for(code):
    """Severity for a code: an explicit override, else derived from its band."""
    code = int(code)
    try:
        override = SEVERITY_OVERRIDES.get(Code(code))
        if override:
            return override
    except ValueError:
        pass                      # unknown code, fall through to the band rule
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


# ---------------------------------------------------------------------------
# Permitted value ranges, taken from lib/constants.py.
#
# NOTE: constants.py carries the comment "TODO: set the correct resistance and
# inclination range values once we've got the real Wahoo device data". The
# incline bounds are corroborated by the BLE op codes in the same file
# (0x666c07 = 19%, 0x6619fc = -10%), so they are likely correct. Worth
# confirming before these codes are treated as final.
# ---------------------------------------------------------------------------
RANGES = {
    "incline": (float(INCLINE_MIN), float(INCLINE_MAX)),
    "resistance": (float(RESISTANCE_MIN), float(RESISTANCE_MAX)),
    "fan": (float(FAN_MIN), float(FAN_MAX)),
}


def validate_value(control, value, clamp=False):
    """
    Check a numeric control value.

    Returns a (code, message, value) triple. `value` is the number that should
    actually be applied - the original when valid, the clamped bound when
    clamping, and None when nothing usable could be derived.

    With clamp=False an out-of-range value is rejected (VALUE_OUT_OF_RANGE).
    With clamp=True it is pulled to the nearest bound and reported as
    VALUE_CLAMPED, which is a success code carrying a warning severity.
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
