#!/usr/bin/env python3
"""
Publishing helpers for the error code scheme.

Everything that reports a status goes through publish_status(), so the payload
shape can never drift between components.

    {
      "code": 2001,                     numeric code, for range comparisons
      "name": "VALUE_OUT_OF_RANGE",     stable symbolic name, for readability
      "severity": "error",              ok | warning | error | fatal
      "message": "incline value ...",   for humans and logs only
      "topic":   "bike/000001/incline",
      "value":   100,
      "timestamp": 1756543200.123
    }

Never branch on `message` - it is free text and may change.
"""

import json
import time

from error_codes import Code, severity_for, message_for, name_for


def status_topic(command_topic):
    """bike/000001/incline  ->  bike/000001/incline/status"""
    return f"{command_topic}/status"


def device_status_topic(device_id):
    """Device-level topic, for faults not tied to a single command."""
    return f"bike/{device_id}/status"


def build_payload(code, message=None, topic=None, value=None):
    return {
        "code": int(code),
        "name": name_for(code),
        "severity": severity_for(code),
        "message": message or message_for(code),
        "topic": topic,
        "value": value,
        "timestamp": round(time.time(), 3),
    }


def publish_status(client, command_topic, code, message=None, value=None,
                   qos=1, retain=False):
    """Publish a status reply for a given command topic."""
    payload = build_payload(code, message, command_topic, value)
    client.publish(status_topic(command_topic), json.dumps(payload),
                   qos=qos, retain=retain)
    return payload


def publish_device_status(client, device_id, code, message=None, retain=True,
                          wait=False):
    """
    Publish a device-level status.

    Retained by default so an application connecting after a failure still
    learns the current state. Because it is retained, the bike MUST publish a
    fresh status on startup and on shutdown so a stale message is never left
    behind.

    Pass wait=True when the client is about to disconnect. Publishing is
    asynchronous, so without waiting the message can still be sitting in the
    queue when disconnect() is called - the broker then sees an abrupt
    disconnect and publishes the Last Will instead, reporting a crash when the
    bike actually shut down cleanly.
    """
    topic = device_status_topic(device_id)
    payload = build_payload(code, message, topic, None)
    info = client.publish(topic, json.dumps(payload), qos=1, retain=retain)
    if wait:
        try:
            info.wait_for_publish(timeout=2)
        except Exception:
            pass
    return payload


def register_last_will(client, device_id):
    """
    Register the Last Will and Testament with the broker.

    A bike that has fatally failed usually cannot publish anything - if the Pi
    loses power or the process is killed, no message is sent and consumers wait
    forever. The will is held by the BROKER and published on its behalf when the
    connection drops unexpectedly.

    The payload is built now and stored by the broker, which republishes it
    verbatim whenever the connection drops - possibly much later. Its timestamp
    is therefore deliberately left null: it would otherwise record when the will
    was registered, not when the bike died. Consumers should use their own time
    of receipt.

    Must be called BEFORE client.connect().
    """
    payload = build_payload(Code.BIKE_OFFLINE,
                            topic=device_status_topic(device_id))
    payload["timestamp"] = None
    client.will_set(device_status_topic(device_id), json.dumps(payload),
                    qos=1, retain=True)