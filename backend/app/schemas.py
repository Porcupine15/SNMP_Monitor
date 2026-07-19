from datetime import datetime
from ipaddress import ip_address, ip_network
import re

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from typing import Literal, Optional


Role = Literal["admin", "operator", "viewer"]
DeviceType = Literal["switch", "printer", "router"]
SnmpVersion = Literal["v1", "v2c", "v3"]


def normalize_mac(value: Optional[str]) -> Optional[str]:
    if value is None or not value.strip():
        return None
    compact = re.sub(r"[^0-9a-fA-F]", "", value)
    if len(compact) != 12:
        raise ValueError("Укажите корректный MAC-адрес")
    return ":".join(compact[index:index + 2].lower() for index in range(0, 12, 2))

# Пользователи
class UserCreate(BaseModel):
    username: str = Field(..., min_length=3, max_length=50)
    password: str = Field(..., min_length=12, max_length=128)
    email: Optional[str] = Field(None, max_length=255)

    @field_validator("username", mode="before")
    def valid_username(cls, value: str) -> str:
        if not isinstance(value, str):
            return value
        value = value.strip()
        if not value or not all(char.isalnum() or char in "_.-" for char in value):
            raise ValueError("Имя может содержать буквы, цифры, точку, дефис и подчёркивание")
        return value

    @field_validator("email")
    def valid_email(cls, value: Optional[str]) -> Optional[str]:
        if value is None or not value.strip():
            return None
        value = value.strip().lower()
        if value.count("@") != 1 or value.startswith("@") or value.endswith("@"):
            raise ValueError("Укажите корректный email")
        return value

class UserLogin(BaseModel):
    username: str = Field(..., min_length=1, max_length=50)
    password: str = Field(..., min_length=1, max_length=128)

    @field_validator("username")
    def normalize_username(cls, value: str) -> str:
        return value.strip()

class Token(BaseModel):
    access_token: str
    token_type: str

class UserRoleUpdate(BaseModel):
    role: Role


class UserAdminCreate(UserCreate):
    role: Role = "viewer"


class UserAdminUpdate(BaseModel):
    username: Optional[str] = Field(None, min_length=3, max_length=50)
    email: Optional[str] = Field(None, max_length=255)
    password: Optional[str] = Field(None, min_length=12, max_length=128)
    role: Optional[Role] = None
    is_active: Optional[bool] = None

    @field_validator("username", mode="before")
    def valid_optional_username(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        if not isinstance(value, str):
            return value
        value = value.strip()
        if not value or not all(char.isalnum() or char in "_.-" for char in value):
            raise ValueError("Имя может содержать буквы, цифры, точку, дефис и подчёркивание")
        return value

    @field_validator("email")
    def valid_optional_email(cls, value: Optional[str]) -> Optional[str]:
        if value is None or not value.strip():
            return None
        value = value.strip().lower()
        if value.count("@") != 1 or value.startswith("@") or value.endswith("@"):
            raise ValueError("Укажите корректный email")
        return value

    @model_validator(mode="after")
    def at_least_one_change(self):
        if not self.model_fields_set:
            raise ValueError("Укажите хотя бы одно изменяемое поле")
        for field in ("username", "password", "role", "is_active"):
            if field in self.model_fields_set and getattr(self, field) is None:
                raise ValueError(f"Поле {field} не может быть пустым")
        return self


class UserStatusUpdate(BaseModel):
    is_active: bool

class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str
    email: Optional[str]
    is_active: bool
    role: str

# Устройства 
class DeviceCreate(BaseModel):
    ip: str
    hostname: str = Field("", max_length=100)
    model: str = Field("", max_length=100)
    device_type: DeviceType
    snmp_version: SnmpVersion = "v2c"
    # Devices without SNMP can still be kept for ICMP-only availability checks.
    community: Optional[str] = Field(None, max_length=255)
    snmp_user: Optional[str] = Field(None, max_length=255)
    snmp_auth: Optional[str] = Field(None, max_length=255)
    snmp_priv: Optional[str] = Field(None, max_length=255)

    @field_validator("ip")
    def valid_ip(cls, value: str) -> str:
        try:
            return str(ip_address(value))
        except ValueError as exc:
            raise ValueError("Укажите корректный IPv4 или IPv6 адрес") from exc

    @field_validator("hostname", "model")
    def strip_optional_text(cls, value: str) -> str:
        return value.strip()

    @model_validator(mode="after")
    def validate_snmp_credentials(self):
        if self.snmp_version == "v3" and (not self.snmp_user or not self.snmp_auth):
            raise ValueError("SNMPv3 requires a security username and authentication password")
        return self


class DeviceUpdate(BaseModel):
    ip: Optional[str] = None
    hostname: Optional[str] = Field(None, max_length=100)
    model: Optional[str] = Field(None, max_length=100)
    device_type: Optional[DeviceType] = None
    snmp_version: Optional[SnmpVersion] = None
    community: Optional[str] = Field(None, max_length=255)
    snmp_user: Optional[str] = Field(None, max_length=255)
    snmp_auth: Optional[str] = Field(None, max_length=255)
    snmp_priv: Optional[str] = Field(None, max_length=255)

    @field_validator("ip")
    def valid_optional_ip(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        try:
            return str(ip_address(value))
        except ValueError as exc:
            raise ValueError("Укажите корректный IPv4 или IPv6 адрес") from exc

    @field_validator("hostname", "model")
    def strip_optional_device_text(cls, value: Optional[str]) -> Optional[str]:
        return value.strip() if value is not None else None


class DeviceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    ip: str
    hostname: Optional[str]
    model: Optional[str]
    device_type: Optional[str]
    snmp_version: str
    status: str
    last_seen: Optional[datetime]
    toner: Optional[int]
    error_msg: Optional[str]


class PortUpdate(BaseModel):
    """Локальные метаданные порта; SNMP-конфигурацию не меняет."""

    description: Optional[str] = Field(None, max_length=255)
    mode: Optional[str] = None

    @field_validator("mode")
    def valid_mode(cls, value: Optional[str]) -> Optional[str]:
        if value is not None and value not in {"Access", "Trunk"}:
            raise ValueError("Режим порта может быть только Access или Trunk")
        return value


class NetworkScanRequest(BaseModel):
    network: str

    @field_validator("network")
    def valid_network(cls, value: str) -> str:
        try:
            return str(ip_network(value, strict=False))
        except ValueError as exc:
            raise ValueError("Укажите корректную сеть в формате CIDR") from exc


class AgentClient(BaseModel):
    ip: str
    mac: Optional[str] = None
    hostname: Optional[str] = Field(None, max_length=255)

    @field_validator("ip")
    def valid_client_ip(cls, value: str) -> str:
        try:
            return str(ip_address(value))
        except ValueError as exc:
            raise ValueError("Укажите корректный IP-адрес клиента") from exc

    @field_validator("mac")
    def valid_mac(cls, value: Optional[str]) -> Optional[str]:
        return normalize_mac(value)

    @field_validator("hostname")
    def normalize_hostname(cls, value: Optional[str]) -> Optional[str]:
        if value is None or not value.strip():
            return None
        return value.strip()


class AgentSync(BaseModel):
    clients: list[AgentClient] = Field(..., max_length=4096)
