import pytest
from cryptography.fernet import Fernet

from app import config


def _secure_production_environment(monkeypatch) -> None:
    values = {
        "ENVIRONMENT": "production",
        "SECRET_KEY": "s" * 48,
        "LAN_AGENT_TOKEN": "a" * 48,
        "DB_PASSWORD": "d" * 32,
        "CREDENTIALS_ENCRYPTION_KEY": Fernet.generate_key().decode(),
        "ALLOWED_NETWORKS": "10.20.0.0/16,192.168.50.0/24",
        "TRUSTED_HOSTS": "snmp.example.internal,10.20.0.10",
        "CORS_ORIGINS": "",
        "ACCESS_TOKEN_EXPIRE_MINUTES": "60",
        "ALLOW_PUBLIC_REGISTRATION": "false",
    }
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    config.allowed_networks.cache_clear()


def test_secure_production_configuration_is_accepted(monkeypatch):
    _secure_production_environment(monkeypatch)

    config.validate_runtime_config()
    assert config.ip_is_allowed("10.20.5.9")
    assert config.network_is_allowed("192.168.50.0/25")
    assert not config.ip_is_allowed("10.30.0.1")
    assert not config.network_is_allowed("10.0.0.0/8")


@pytest.mark.parametrize(
    ("name", "value", "message"),
    [
        ("ALLOWED_NETWORKS", "0.0.0.0/0", "must not contain"),
        ("TRUSTED_HOSTS", "*", "explicitly list"),
        ("CORS_ORIGINS", "*", "must not contain a wildcard"),
        ("CORS_ORIGINS", "http://snmp.example.internal", "HTTPS origin"),
        ("ACCESS_TOKEN_EXPIRE_MINUTES", "1440", "between 5 and 120"),
        ("ALLOW_PUBLIC_REGISTRATION", "true", "must be false"),
    ],
)
def test_unsafe_production_configuration_is_rejected(monkeypatch, name, value, message):
    _secure_production_environment(monkeypatch)
    monkeypatch.setenv(name, value)
    config.allowed_networks.cache_clear()

    with pytest.raises(RuntimeError, match=message):
        config.validate_runtime_config()


def test_weak_database_password_is_rejected(monkeypatch):
    _secure_production_environment(monkeypatch)
    monkeypatch.setenv("DB_PASSWORD", "short")

    with pytest.raises(RuntimeError, match="DB_PASSWORD"):
        config.validate_runtime_config()
