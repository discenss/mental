"""user reminder settings

Revision ID: c1a2b3d4e5f6
Revises: ba9717516ebd
Create Date: 2026-07-15

Добавляет поля ежедневного напоминания в users. server_default проставлен,
чтобы ADD COLUMN прошёл на непустой таблице (sqlite/postgres).
"""
from alembic import op
import sqlalchemy as sa

revision = "c1a2b3d4e5f6"
down_revision = "ba9717516ebd"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.add_column(sa.Column("reminder_enabled", sa.Boolean(), nullable=False,
                                   server_default="1"))
        batch.add_column(sa.Column("reminder_hour", sa.Integer(), nullable=False,
                                   server_default="20"))
        batch.add_column(sa.Column("reminder_minute", sa.Integer(), nullable=False,
                                   server_default="0"))
        batch.add_column(sa.Column("last_reminded_date", sa.Date(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("users") as batch:
        batch.drop_column("last_reminded_date")
        batch.drop_column("reminder_minute")
        batch.drop_column("reminder_hour")
        batch.drop_column("reminder_enabled")
