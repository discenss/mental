"""audio variants (multi-language + multi-channel delivery)

Revision ID: f4a5b6c7d8e9
Revises: 096cebe99ba6
Create Date: 2026-07-23

Разделяет "практику-слот" (AudioAsset, языко-независимо) и "языковую запись" (AudioVariant:
язык + storage_key + кэш доставки по каналам telegram/whatsapp/…). Существующие ru-записи
переносятся из audio_assets в audio_variants (language='ru'), затем старые поля удаляются.
"""
from alembic import op
import sqlalchemy as sa

revision = "f4a5b6c7d8e9"
down_revision = "096cebe99ba6"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "audio_variants",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("audio_asset_id", sa.Integer(), sa.ForeignKey("audio_assets.id"), nullable=False),
        sa.Column("language", sa.String(length=8), nullable=False),
        sa.Column("storage_key", sa.String(length=255), nullable=False),
        sa.Column("mime", sa.String(length=64), nullable=True),
        sa.Column("duration_sec", sa.Integer(), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=True),
        sa.Column("channel_cache", sa.JSON(), nullable=False),
        sa.UniqueConstraint("audio_asset_id", "language", name="uq_audio_variant_asset_lang"),
    )

    # перенос существующих ru-записей: audio_assets.media_filename/mime/… → audio_variants
    conn = op.get_bind()
    assets = sa.table(
        "audio_assets",
        sa.column("id", sa.Integer()), sa.column("media_filename", sa.String()),
        sa.column("mime", sa.String()), sa.column("duration_sec", sa.Integer()),
        sa.column("size_bytes", sa.Integer()), sa.column("tg_file_id", sa.String()),
    )
    variants = sa.table(
        "audio_variants",
        sa.column("audio_asset_id", sa.Integer()), sa.column("language", sa.String()),
        sa.column("storage_key", sa.String()), sa.column("mime", sa.String()),
        sa.column("duration_sec", sa.Integer()), sa.column("size_bytes", sa.Integer()),
        sa.column("channel_cache", sa.JSON()),
    )
    rows = conn.execute(sa.select(assets.c.id, assets.c.media_filename, assets.c.mime,
                                  assets.c.duration_sec, assets.c.size_bytes,
                                  assets.c.tg_file_id)).fetchall()
    for r in rows:
        if not r.media_filename:
            continue
        cache = {"telegram": r.tg_file_id} if r.tg_file_id else {}
        conn.execute(variants.insert().values(
            audio_asset_id=r.id, language="ru", storage_key=r.media_filename,
            mime=r.mime, duration_sec=r.duration_sec, size_bytes=r.size_bytes,
            channel_cache=cache,
        ))

    with op.batch_alter_table("audio_assets") as batch:
        batch.drop_column("media_filename")
        batch.drop_column("mime")
        batch.drop_column("duration_sec")
        batch.drop_column("size_bytes")
        batch.drop_column("tg_file_id")


def downgrade() -> None:
    with op.batch_alter_table("audio_assets") as batch:
        batch.add_column(sa.Column("media_filename", sa.String(length=255), nullable=True))
        batch.add_column(sa.Column("mime", sa.String(length=64), nullable=True))
        batch.add_column(sa.Column("duration_sec", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("size_bytes", sa.Integer(), nullable=True))
        batch.add_column(sa.Column("tg_file_id", sa.String(length=255), nullable=True))

    conn = op.get_bind()
    assets = sa.table("audio_assets", sa.column("id", sa.Integer()),
                      sa.column("media_filename", sa.String()), sa.column("mime", sa.String()),
                      sa.column("duration_sec", sa.Integer()), sa.column("size_bytes", sa.Integer()),
                      sa.column("tg_file_id", sa.String()))
    variants = sa.table("audio_variants", sa.column("audio_asset_id", sa.Integer()),
                        sa.column("language", sa.String()), sa.column("storage_key", sa.String()),
                        sa.column("mime", sa.String()), sa.column("duration_sec", sa.Integer()),
                        sa.column("size_bytes", sa.Integer()), sa.column("channel_cache", sa.JSON()))
    rows = conn.execute(sa.select(variants.c.audio_asset_id, variants.c.storage_key,
                                  variants.c.mime, variants.c.duration_sec, variants.c.size_bytes,
                                  variants.c.channel_cache)
                       .where(variants.c.language == "ru")).fetchall()
    for r in rows:
        tg = (r.channel_cache or {}).get("telegram")
        conn.execute(assets.update().where(assets.c.id == r.audio_asset_id).values(
            media_filename=r.storage_key, mime=r.mime, duration_sec=r.duration_sec,
            size_bytes=r.size_bytes, tg_file_id=tg))

    op.drop_table("audio_variants")
