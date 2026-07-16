from sqlalchemy import Boolean, Column, DateTime, Integer, JSON, String, Text
from sqlalchemy.sql import func

from app.database import Base


SNMP_CREDENTIAL_LENGTH = 512


class Device(Base):
    __tablename__ = "devices"

    id = Column(Integer, primary_key=True, index=True)
    ip = Column(String(45), unique=True, index=True, nullable=False)
    hostname = Column(String(100))
    model = Column(String(100))
    device_type = Column(String(20))  # switch, printer, router
    snmp_version = Column(String(5), nullable=False, default="v2c", server_default="v2c")
    # Fernet turns even short secrets into values longer than 100 characters.
    # Keep enough room for encrypted SNMPv2/v3 credentials.
    community = Column(String(SNMP_CREDENTIAL_LENGTH))
    snmp_user = Column(String(SNMP_CREDENTIAL_LENGTH), nullable=True)
    snmp_auth = Column(String(SNMP_CREDENTIAL_LENGTH), nullable=True)
    snmp_priv = Column(String(SNMP_CREDENTIAL_LENGTH), nullable=True)
    status = Column(String(20), nullable=False, default="unknown", server_default="unknown")
    last_seen = Column(DateTime(timezone=True), server_default=func.now())
    ports = Column(JSON, default=list)  # будем хранить порты как JSON
    toner = Column(Integer, nullable=True)  # для принтеров
    error_msg = Column(Text, nullable=True)

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    username = Column(String(50), unique=True, index=True, nullable=False)
    email = Column(String(255), unique=True, index=True, nullable=True)
    hashed_password = Column(String(255), nullable=False)
    role = Column(String(20), nullable=False, default="viewer", server_default="viewer")
    is_active = Column(Boolean, nullable=False, default=True, server_default="true")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now())


class DeviceEvent(Base):
    """Короткий журнал изменений состояния устройств."""

    __tablename__ = "device_events"

    id = Column(Integer, primary_key=True, index=True)
    device_id = Column(Integer, nullable=False, index=True)
    event_type = Column(String(50), nullable=False)
    message = Column(Text, nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class DeviceAvailability(Base):
    __tablename__ = "device_availability"
    id = Column(Integer, primary_key=True)
    device_id = Column(Integer, nullable=False, index=True)
    status = Column(String(20), nullable=False)
    checked_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AuditEvent(Base):
    __tablename__ = "audit_events"
    id = Column(Integer, primary_key=True)
    username = Column(String(100), nullable=False)
    action = Column(String(80), nullable=False)
    details = Column(Text, nullable=False, default="")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class AppSetting(Base):
    __tablename__ = "app_settings"
    key = Column(String(100), primary_key=True)
    value = Column(String(500), nullable=False)


class NetworkClient(Base):
    __tablename__ = "network_clients"
    id = Column(Integer, primary_key=True)
    ip = Column(String(45), unique=True, nullable=False, index=True)
    mac = Column(String(17), nullable=True, index=True)
    hostname = Column(String(255), nullable=True)
    vendor = Column(String(100), nullable=True)
    status = Column(String(20), nullable=False, default="unknown", server_default="unknown")
    first_seen = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    last_seen = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
