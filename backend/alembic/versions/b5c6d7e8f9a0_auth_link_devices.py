"""auth: link codes + device tokens (авторизация iOS, §3.1)

Только новые таблицы: существующие не меняются, поэтому бот и его запросы
не затронуты.

Revision ID: b5c6d7e8f9a0
Revises: a4b1c9d7e2f3
"""
import sqlalchemy as sa
from alembic import op

revision = "b5c6d7e8f9a0"
down_revision = "a4b1c9d7e2f3"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "link_codes",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("code", sa.String(16), nullable=False, index=True),
        sa.Column("provider", sa.String(16), nullable=False),
        sa.Column("expires_at", sa.DateTime(), nullable=False),
        sa.Column("used", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
    )
    op.create_table(
        "device_tokens",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("token", sa.String(255), nullable=False),
        sa.Column("platform", sa.String(16), nullable=False, server_default="ios"),
        sa.Column("sandbox", sa.Boolean(), nullable=False, server_default="0"),
        sa.Column("language", sa.String(8), nullable=True),
        sa.Column("last_seen_at", sa.DateTime(), server_default=sa.func.now()),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now()),
        sa.UniqueConstraint("token", name="uq_device_tokens_token"),
    )


def downgrade() -> None:
    op.drop_table("device_tokens")
    op.drop_table("link_codes")
