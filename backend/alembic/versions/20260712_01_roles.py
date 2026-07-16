"""add user roles safely to existing installations"""

from alembic import op
import sqlalchemy as sa

revision = "20260712_01"
down_revision = "20260712_00"
branch_labels = None
depends_on = None


def upgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "users" in inspector.get_table_names():
        columns = {column["name"] for column in inspector.get_columns("users")}
        if "role" not in columns:
            op.add_column("users", sa.Column("role", sa.String(length=20), nullable=True))
            op.execute("UPDATE users SET role = 'admin' WHERE role IS NULL")
            op.alter_column("users", "role", nullable=False, server_default="viewer")


def downgrade() -> None:
    inspector = sa.inspect(op.get_bind())
    if "users" in inspector.get_table_names() and "role" in {c["name"] for c in inspector.get_columns("users")}:
        op.drop_column("users", "role")
