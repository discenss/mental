"""text assets (text-only meditations, independent from audio)

Revision ID: a1b2c3d4e5f7
Revises: b5c6d7e8f9a0
Create Date: 2026-10-03

Смена парадигмы: практика дня может быть аудио, текстом, и тем и другим, или не быть вовсе.
text_assets/text_variants — независимый от audio_assets/audio_variants список (см.
app.models.TextAsset): свой day_range на запись (не фиксированный slot, как у аудио),
тело практики — просто текст в БД (без файла, как task_text/focus у ModuleDay).
"""
from alembic import op
import sqlalchemy as sa

revision = "a1b2c3d4e5f7"
down_revision = "b5c6d7e8f9a0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "text_assets",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("module_code", sa.String(length=16), sa.ForeignKey("modules.code"), nullable=False),
        sa.Column("week_n", sa.Integer(), nullable=False),
        sa.Column("slot", sa.String(length=8), nullable=False),
        sa.Column("code", sa.String(length=64), nullable=False),
        sa.Column("day_range", sa.String(length=16), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("theme", sa.Text(), nullable=True),
        sa.UniqueConstraint("code", name="uq_text_asset_code"),
    )
    op.create_table(
        "text_variants",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("text_asset_id", sa.Integer(), sa.ForeignKey("text_assets.id"), nullable=False),
        sa.Column("language", sa.String(length=8), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.UniqueConstraint("text_asset_id", "language", name="uq_text_variant_asset_lang"),
    )


def downgrade() -> None:
    op.drop_table("text_variants")
    op.drop_table("text_assets")
