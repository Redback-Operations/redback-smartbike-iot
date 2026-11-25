import os
import sys

import pytest

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..")))

from lib.mqtt_client import MQTTClient, load_mqtt_config  # noqa: E402

KEYS = ["MQTT_HOSTNAME", "MQTT_HOST", "MQTT_PORT", "MQTT_USERNAME", "MQTT_USER",
        "MQTT_PASSWORD", "MQTT_PASS", "MQTT_USE_TLS"]


@pytest.fixture(autouse=True)
def clean_env(monkeypatch):
    for key in KEYS:
        monkeypatch.delenv(key, raising=False)


def test_missing_host_fails_instead_of_using_localhost():
    with pytest.raises(ValueError):
        MQTTClient()


def test_reads_primary_env_vars(monkeypatch):
    monkeypatch.setenv("MQTT_HOSTNAME", "10.0.0.5")
    monkeypatch.setenv("MQTT_PORT", "1884")
    monkeypatch.setenv("MQTT_USERNAME", "bike")
    monkeypatch.setenv("MQTT_PASSWORD", "secret")
    client = MQTTClient()
    assert (client.broker_address, client.port, client.username, client.password) == ("10.0.0.5", 1884, "bike", "secret")
    assert client.use_tls is False


def test_legacy_aliases_still_work(monkeypatch):
    monkeypatch.setenv("MQTT_HOST", "old-host")
    monkeypatch.setenv("MQTT_USER", "old-user")
    monkeypatch.setenv("MQTT_PASS", "old-pass")
    config = load_mqtt_config()
    assert (config["host"], config["username"], config["password"]) == ("old-host", "old-user", "old-pass")


def test_tls_on_for_8883_or_flag(monkeypatch):
    monkeypatch.setenv("MQTT_HOSTNAME", "cloud")
    monkeypatch.setenv("MQTT_PORT", "8883")
    assert MQTTClient().use_tls is True
    monkeypatch.setenv("MQTT_PORT", "1883")
    monkeypatch.setenv("MQTT_USE_TLS", "true")
    assert MQTTClient().use_tls is True


def test_explicit_args_override_env(monkeypatch):
    monkeypatch.setenv("MQTT_HOSTNAME", "env-host")
    client = MQTTClient("arg-host", port=2000, use_tls=False)
    assert (client.broker_address, client.port, client.use_tls) == ("arg-host", 2000, False)
