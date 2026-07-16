"""create monitoring runtime tables and expand encrypted credentials"""

from alembic import op
import sqlalchemy as sa


revision = "20260716_02"
down_revision = "20260712_01"
branch_labels = None
depends_on = None


def _credential_columns_to_expand() -> list[tuple[str, sa.types.TypeEngine]]:
    inspector = sa.inspect(op.get_bind())
    if "devices" not in inspector.get_table_names():
        return []
    columns = {column["name"]: column["type"] for column in inspector.get_columns("devices")}
    result = []
    for name in ("community", "snmp_user", "snmp_auth", "snmp_priv"):
        current_type = columns.get(name)
        if current_type is not None and (getattr(current_type, "length", None) or 0) < 512:
            result.append((name, current_type))
    return result


def upgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())

    if "device_events" not in tables:
        op.create_table(
            "device_events",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("device_id", sa.Integer(), nullable=False),
            sa.Column("event_type", sa.String(length=50), nullable=False),
            sa.Column("message", sa.Text(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index("ix_device_events_device_id", "device_events", ["device_id"], unique=False)
        op.create_index("ix_device_events_id", "device_events", ["id"], unique=False)

    if "device_availability" not in tables:
        op.create_table(
            "device_availability",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("device_id", sa.Integer(), nullable=False),
            sa.Column("status", sa.String(length=20), nullable=False),
            sa.Column("checked_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )
        op.create_index(
            "ix_device_availability_device_id",
            "device_availability",
            ["device_id"],
            unique=False,
        )

    if "audit_events" not in tables:
        op.create_table(
            "audit_events",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("username", sa.String(length=100), nullable=False),
            sa.Column("action", sa.String(length=80), nullable=False),
            sa.Column("details", sa.Text(), server_default="", nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
        )

    if "app_settings" not in tables:
        op.create_table(
            "app_settings",
            sa.Column("key", sa.String(length=100), nullable=False),
            sa.Column("value", sa.String(length=500), nullable=False),
            sa.PrimaryKeyConstraint("key"),
        )

    if "network_clients" not in tables:
        op.create_table(
            "network_clients",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("ip", sa.String(length=45), nullable=False),
            sa.Column("mac", sa.String(length=17), nullable=True),
            sa.Column("hostname", sa.String(length=255), nullable=True),
            sa.Column("vendor", sa.String(length=100), nullable=True),
            sa.Column("status", sa.String(length=20), server_default="unknown", nullable=False),
            sa.Column("first_seen", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("last_seen", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("ip", name="uq_network_clients_ip"),
        )
        op.create_index("ix_network_clients_ip", "network_clients", ["ip"], unique=False)
        op.create_index("ix_network_clients_mac", "network_clients", ["mac"], unique=False)

    columns_to_expand = _credential_columns_to_expand()
    if columns_to_expand:
        with op.batch_alter_table("devices") as batch_op:
            for column_name, current_type in columns_to_expand:
                batch_op.alter_column(
                    column_name,
                    existing_type=current_type,
                    type_=sa.String(length=512),
                    existing_nullable=True,
                )


def downgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    for table_name in (
        "network_clients",
        "app_settings",
        "audit_events",
        "device_availability",
        "device_events",
    ):
        if table_name in tables:
            op.drop_table(table_name)
