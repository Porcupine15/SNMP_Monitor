import asyncio
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config
from pydantic import ValidationError
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import sessionmaker

from app.database import Base
from app.models import AuditEvent, Device, NetworkClient, User
from app.routes.clients import _client_for_observation
from app.routes.devices import update_port
from app.schemas import AgentClient, DeviceCreate, PortUpdate, UserCreate


def _session():
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine)()


def test_alembic_builds_complete_schema_from_empty_database(tmp_path, monkeypatch):
    database_path = tmp_path / "migration.sqlite"
    backend_dir = Path(__file__).resolve().parents[1]
    config = Config(str(backend_dir / "alembic.ini"))
    config.set_main_option("script_location", str(backend_dir / "alembic"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path}")
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{database_path}")

    command.upgrade(config, "head")

    schema = inspect(create_engine(f"sqlite:///{database_path}"))
    assert {
        "users",
        "devices",
        "device_events",
        "device_availability",
        "audit_events",
        "app_settings",
        "network_clients",
    }.issubset(schema.get_table_names())
    credential_columns = {
        column["name"]: column["type"] for column in schema.get_columns("devices")
    }
    assert credential_columns["community"].length == 512


def test_network_client_input_normalizes_identity_fields():
    client = AgentClient(ip="192.168.1.10", mac="AA-BB-CC-DD-EE-FF", hostname=" tv ")
    assert client.ip == "192.168.1.10"
    assert client.mac == "aa:bb:cc:dd:ee:ff"
    assert client.hostname == "tv"

    with pytest.raises(ValidationError):
        AgentClient(ip="not-an-ip", mac="invalid")
    with pytest.raises(ValidationError):
        DeviceCreate(ip="192.168.1.1", device_type="camera")
    with pytest.raises(ValidationError):
        DeviceCreate(ip="192.168.1.2", device_type="switch", snmp_version="v3")
    with pytest.raises(ValidationError):
        UserCreate(username="operator", password="too-short")

    device = DeviceCreate(
        ip="192.168.1.2",
        device_type="switch",
        snmp_version="v3",
        snmp_user="monitor",
        snmp_auth="a-secure-auth-secret",
    )
    assert device.snmp_user == "monitor"


def test_client_identity_follows_mac_when_dhcp_address_changes():
    db = _session()
    known = NetworkClient(ip="192.168.1.10", mac="aa:bb:cc:dd:ee:ff")
    stale_at_new_ip = NetworkClient(ip="192.168.1.20", mac="11:22:33:44:55:66")
    db.add_all([known, stale_at_new_ip])
    db.commit()

    resolved = _client_for_observation(db, "192.168.1.20", "aa:bb:cc:dd:ee:ff")
    db.commit()

    assert resolved.id == known.id
    assert resolved.ip == "192.168.1.20"
    assert db.query(NetworkClient).count() == 1


def test_port_metadata_update_is_persisted_for_json_column():
    db = _session()
    user = User(username="operator", hashed_password="hash", role="operator")
    device = Device(
        ip="192.168.1.2",
        device_type="switch",
        ports=[{"port": 1, "description": "old", "mode": "Access"}],
    )
    db.add_all([user, device])
    db.commit()

    asyncio.run(
        update_port(
            device_id=device.id,
            port=1,
            update_data=PortUpdate(description="new", mode="Trunk"),
            db=db,
            current_user=user,
        )
    )
    db.expire_all()

    saved_port = db.get(Device, device.id).ports[0]
    assert saved_port["description_override"] == "new"
    assert saved_port["mode_override"] == "Trunk"
    assert db.query(AuditEvent).filter_by(action="device_port_updated").count() == 1
