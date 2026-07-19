"""Runtime security configuration shared by API routes and startup checks."""

from __future__ import annotations

import ipaddress
import os
from functools import lru_cache
from urllib.parse import urlparse

from cryptography.fernet import Fernet


TRUE_VALUES = {"1", "true", "yes", "on"}


def environment() -> str:
    return os.getenv("ENVIRONMENT", "development").strip().lower()


def public_registration_enabled() -> bool:
    return os.getenv("ALLOW_PUBLIC_REGISTRATION", "false").strip().lower() in TRUE_VALUES


@lru_cache(maxsize=1)
def allowed_networks() -> tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...]:
    raw = os.getenv("ALLOWED_NETWORKS", "")
    networks = []
    for value in raw.split(","):
        value = value.strip()
        if value:
            networks.append(ipaddress.ip_network(value, strict=False))
    return tuple(networks)


def ip_is_allowed(value: str) -> bool:
    configured = allowed_networks()
    if not configured:
        return environment() != "production"
    address = ipaddress.ip_address(value)
    return any(address.version == network.version and address in network for network in configured)


def network_is_allowed(value: str) -> bool:
    configured = allowed_networks()
    if not configured:
        return environment() != "production"
    requested = ipaddress.ip_network(value, strict=False)
    return any(
        requested.version == network.version and requested.subnet_of(network)
        for network in configured
    )


def _secure_value(name: str, minimum_length: int = 32) -> str:
    value = os.getenv(name, "")
    if len(value) < minimum_length or "change_" in value.lower():
        raise RuntimeError(f"{name} must be set to a unique value of at least {minimum_length} characters")
    return value


def validate_runtime_config() -> None:
    """Fail before serving requests when production security settings are unsafe."""
    if environment() != "production":
        return

    _secure_value("SECRET_KEY")
    _secure_value("LAN_AGENT_TOKEN")
    _secure_value("DB_PASSWORD", minimum_length=16)
    encryption_key = _secure_value("CREDENTIALS_ENCRYPTION_KEY")
    try:
        Fernet(encryption_key.encode())
    except (TypeError, ValueError) as exc:
        raise RuntimeError("CREDENTIALS_ENCRYPTION_KEY must be a valid Fernet key") from exc

    networks = allowed_networks()
    if not networks:
        raise RuntimeError("ALLOWED_NETWORKS must contain approved CIDR ranges in production")
    if any(network.prefixlen == 0 for network in networks):
        raise RuntimeError("ALLOWED_NETWORKS must not contain 0.0.0.0/0 or ::/0")

    trusted_hosts = [value.strip() for value in os.getenv("TRUSTED_HOSTS", "").split(",") if value.strip()]
    if not trusted_hosts or "*" in trusted_hosts:
        raise RuntimeError("TRUSTED_HOSTS must explicitly list the corporate FQDN and/or server IP")

    cors_origins = [value.strip() for value in os.getenv("CORS_ORIGINS", "").split(",") if value.strip()]
    if "*" in cors_origins:
        raise RuntimeError("CORS_ORIGINS must not contain a wildcard in production")
    for origin in cors_origins:
        parsed = urlparse(origin)
        if parsed.scheme != "https" or not parsed.netloc:
            raise RuntimeError("Every production CORS_ORIGINS entry must be an HTTPS origin")

    try:
        token_minutes = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "60"))
    except ValueError as exc:
        raise RuntimeError("ACCESS_TOKEN_EXPIRE_MINUTES must be an integer") from exc
    if not 5 <= token_minutes <= 120:
        raise RuntimeError("ACCESS_TOKEN_EXPIRE_MINUTES must be between 5 and 120 in production")

    if public_registration_enabled():
        raise RuntimeError("ALLOW_PUBLIC_REGISTRATION must be false in production")
