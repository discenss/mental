"""day sessions (morning/evening) on daily_entries

Revision ID: e3c4d5f6a7b8
Revises: d2b3c4e5f6a7
Create Date: 2026-07-15
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import table, column

revision = "e3c4d5f6a7b8"
down_revision = "d2b3c4e5f6a7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("daily_entries") as batch:
        batch.add_column(sa.Column("morning_done", sa.Boolean(), nullable=False, server_default="0"))
        batch.add_column(sa.Column("evening_done", sa.Boolean(), nullable=False, server_default="0"))
    # существующие полностью пройденные дни считаем закрытыми обеими сессиями.
    # Через table()-конструкцию (не сырой SQL) — литерал True компилируется под диалект
    # (SQLite: 1, Postgres: true), чтобы миграция работала на обоих движках.
    entries = table("daily_entries", column("morning_done", sa.Boolean()),
                    column("evening_done", sa.Boolean()))
    op.execute(entries.update().values(morning_done=True, evening_done=True))


def downgrade() -> None:
    with op.batch_alter_table("daily_entries") as batch:
        batch.drop_column("evening_done")
        batch.drop_column("morning_done")
