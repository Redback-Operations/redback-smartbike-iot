#!/usr/bin/env python3
"""Offline tests for the error code scheme. No broker, no network, no MQTT."""

import sys

from error_codes import (Code, Severity, RANGES, severity_for, name_for,
                         message_for, is_success, validate_value,
                         code_for_gatt_error)

results = []


def check(description, actual, expected):
    results.append((description, expected, actual, actual == expected))


# --- severity follows the band ---
check("OK is a success severity", severity_for(Code.OK), Severity.OK)
check("Protocol error severity", severity_for(Code.UNKNOWN_COMMAND), Severity.ERROR)
check("Validation error severity", severity_for(Code.VALUE_OUT_OF_RANGE), Severity.ERROR)
check("Device error severity", severity_for(Code.DEVICE_TIMEOUT), Severity.ERROR)
check("Terminal severity", severity_for(Code.FATAL_DEVICE_FAILURE), Severity.FATAL)
check("Unknown code falls back to error", severity_for(4999), Severity.ERROR)

# --- overrides ---
check("Clamped is a warning", severity_for(Code.VALUE_CLAMPED), Severity.WARNING)
check("Deliberate shutdown is a warning", severity_for(Code.BIKE_SHUTDOWN), Severity.WARNING)

# --- success band ---
check("OK counts as success", is_success(Code.OK), True)
check("Clamped counts as success", is_success(Code.VALUE_CLAMPED), True)
check("No action counts as success", is_success(Code.NO_ACTION_TAKEN), True)
check("Protocol error is not success", is_success(Code.UNKNOWN_COMMAND), False)

# --- names and messages ---
check("Name lookup", name_for(2001), "VALUE_OUT_OF_RANGE")
check("Name lookup for unknown code", name_for(7777), "")
check("Message lookup", message_for(Code.DEVICE_TIMEOUT), "Timed out waiting for the device")
check("Message for unknown code is safe", message_for(7777), "Unrecognised error code 7777")

# --- reserved bands are empty ---
check("5000-8999 reserved and unallocated",
      [c for c in Code if 5000 <= int(c) < 9000], [])

# --- no duplicate numbers ---
values = [int(c) for c in Code]
check("All codes are unique", len(values), len(set(values)))

# --- validation, rejecting ---
code, _, value = validate_value("incline", 5)
check("Valid incline accepted", (code, value), (Code.OK, 5.0))

code, _, value = validate_value("incline", 100)
check("High incline rejected", code, Code.VALUE_OUT_OF_RANGE)

code, _, value = validate_value("resistance", -5)
check("Low resistance rejected", code, Code.VALUE_OUT_OF_RANGE)

code, _, value = validate_value("incline", "high")
check("Non-numeric rejected", code, Code.VALUE_WRONG_TYPE)

code, _, value = validate_value("brake", 1)
check("Unconfigured control reported", code, Code.CONTROL_NOT_CONFIGURED)

# --- validation, clamping ---
high = RANGES["incline"][1]
low = RANGES["resistance"][0]

code, _, value = validate_value("incline", 100, clamp=True)
check("High incline clamped to max", (code, value), (Code.VALUE_CLAMPED, high))

code, _, value = validate_value("resistance", -5, clamp=True)
check("Low resistance clamped to min", (code, value), (Code.VALUE_CLAMPED, low))

code, _, value = validate_value("incline", 5, clamp=True)
check("In-range value untouched when clamping", (code, value), (Code.OK, 5.0))

# --- boundaries are inclusive ---
code, _, _ = validate_value("incline", RANGES["incline"][0])
check("Minimum incline is valid", code, Code.OK)
code, _, _ = validate_value("incline", RANGES["incline"][1])
check("Maximum incline is valid", code, Code.OK)

# --- BLE exception mapping ---
for cls_name, expected in [("NotReady", Code.DEVICE_NOT_READY),
                           ("NotSupported", Code.DEVICE_NOT_SUPPORTED),
                           ("InProgress", Code.DEVICE_OPERATION_IN_PROGRESS),
                           ("Failed", Code.DEVICE_FAILED)]:
    exc = type(cls_name, (Exception,), {})()
    check(f"gatt {cls_name} maps correctly", code_for_gatt_error(exc), expected)

unknown = type("SomethingElse", (Exception,), {})()
check("Unknown gatt error falls back to DEVICE_FAILED",
      code_for_gatt_error(unknown), Code.DEVICE_FAILED)


def main():
    width = max(len(r[0]) for r in results) + 2
    print(f"\n{'Check'.ljust(width)}Result")
    print("-" * (width + 8))
    failed = 0
    for description, expected, actual, ok in results:
        print(f"{description.ljust(width)}{'PASS' if ok else 'FAIL'}")
        if not ok:
            print(f"{''.ljust(width)}  expected {expected!r}, got {actual!r}")
            failed += 1
    print("-" * (width + 8))
    print(f"{len(results) - failed} passed, {failed} failed\n")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())