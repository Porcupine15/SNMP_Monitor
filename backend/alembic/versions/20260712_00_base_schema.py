"""create the core users and devices schema

This revision is intentionally tolerant of the early development installations
where FastAPI ``create_all`` created these tables before Alembic was introduced.
"""

from alembic import op
import sqlalchemy as sa


revision = "20260712_00"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())

    if "devices" not in tables:
        op.create_table(
            "devices",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("ip", sa.String(length=45), nullable=False),
            sa.Column("hostname", sa.String(length=100), nullable=True),
            sa.Column("model", sa.String(length=100), nullable=True),
            sa.Column("device_type", sa.String(length=20), nullable=True),
            sa.Column("snmp_version", sa.String(length=5), server_default="v2c", nullable=False),
            sa.Column("community", sa.String(length=512), nullable=True),
            sa.Column("snmp_user", sa.String(length=512), nullable=True),
            sa.Column("snmp_auth", sa.String(length=512), nullable=True),
            sa.Column("snmp_priv", sa.String(length=512), nullable=True),
            sa.Column("status", sa.String(length=20), server_default="unknown", nullable=False),
            sa.Column("last_seen", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=True),
            sa.Column("ports", sa.JSON(), nullable=True),
            sa.Column("toner", sa.Integer(), nullable=True),
            sa.Column("error_msg", sa.Text(), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("ip", name="uq_devices_ip"),
        )
        op.create_index("ix_devices_id", "devices", ["id"], unique=False)
        op.create_index("ix_devices_ip", "devices", ["ip"], unique=False)

    if "users" not in tables:
        op.create_table(
            "users",
            sa.Column("id", sa.Integer(), nullable=False),
            sa.Column("username", sa.String(length=50), nullable=False),
            sa.Column("email", sa.String(length=255), nullable=True),
            sa.Column("hashed_password", sa.String(length=255), nullable=False),
            sa.Column("role", sa.String(length=20), server_default="viewer", nullable=False),
            sa.Column("is_active", sa.Boolean(), server_default=sa.true(), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
            sa.PrimaryKeyConstraint("id"),
            sa.UniqueConstraint("email", name="uq_users_email"),
            sa.UniqueConstraint("username", name="uq_users_username"),
        )
        op.create_index("ix_users_email", "users", ["email"], unique=False)
        op.create_index("ix_users_id", "users", ["id"], unique=False)
        op.create_index("ix_users_username", "users", ["username"], unique=False)


def downgrade() -> None:
    tables = set(sa.inspect(op.get_bind()).get_table_names())
    if "users" in tables:
        op.drop_table("users")
    if "devices" in tables:
        op.drop_table("devices")
