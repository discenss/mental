"""three reminder slots (morning/afternoon/evening)

Revision ID: d2b3c4e5f6a7
Revises: c1a2b3d4e5f6
Create Date: 2026-07-15

Утро/обед добавляются; вечер = существующие reminder_hour/minute/last_reminded_date.
"""
from alembic import op
import sqlalchemy as sa

revision = "d2b3c4e5f6a7"
down_revision = "c1a2b3d4e5f6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("reminder_morning_hour", sa.Integer(), nullable=False,
                                   server_default="10"))
        batch.add_column(sa.Column("reminder_morning_minute", sa.Integer(), nullable=False,
                                   server_default="0"))
        batch.add_column(sa.Column("reminder_afternoon_hour", sa.Integer(), nullable=False,
                                   server_default="14"))
        batch.add_column(sa.Column("reminder_afternoon_minute", sa.Integer(), nullable=False,
                                   server_default="0"))
        batch.add_column(sa.Column("last_morning_date", sa.Date(), nullable=True))
        batch.add_column(sa.Column("last_afternoon_date", sa.Date(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.drop_column("last_afternoon_date")
        batch.drop_column("last_morning_date")
        batch.drop_column("reminder_afternoon_minute")
        batch.drop_column("reminder_afternoon_hour")
        batch.drop_column("reminder_morning_minute")
        batch.drop_column("reminder_morning_hour")
