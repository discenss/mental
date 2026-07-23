"""multilingual content: sidecar *Translation tables (ru unchanged, en/uk/es/de overlay)

Revision ID: a4b1c9d7e2f3
Revises: f4a5b6c7d8e9
Create Date: 2026-07-24

Ru-контент остаётся как есть в базовых таблицах — эта миграция только ДОБАВЛЯЕТ 14 новых
сайдкар-таблиц `*_translations` (по одной на существующую контентную таблицу с текстом),
без единого ALTER существующей таблицы. Каждая — (родительский FK ON DELETE CASCADE, language,
только переводимые текстовые поля); UniqueConstraint(родительский FK, language).
ON DELETE CASCADE — потому что перезагрузка контента (content_loader.load_module) удаляет и
пересоздаёт недели/дни/маркеры при каждом ре-импорте ru-YAML, а load_intake делает bulk-DELETE
через raw SQL (ORM-каскад туда не долетает) — только constraint на уровне БД гарантирует, что
переводы не осиротеют.
"""
from alembic import op
import sqlalchemy as sa

revision = "a4b1c9d7e2f3"
down_revision = "f4a5b6c7d8e9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "module_translations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("module_code", sa.String(length=16), sa.ForeignKey("modules.code", ondelete="CASCADE"), nullable=False),
        sa.Column("language", sa.String(length=8), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=True),
        sa.Column("subtitle", sa.String(length=255), nullable=True),
        sa.Column("passport", sa.JSON(), nullable=True),
        sa.UniqueConstraint("module_code", "language", name="uq_module_translation"),
    )

    op.create_table(
        "module_week_translations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("week_id", sa.Integer(), sa.ForeignKey("module_weeks.id", ondelete="CASCADE"), nullable=False),
        sa.Column("language", sa.String(length=8), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("intro_screen", sa.Text(), nullable=True),
        sa.Column("meaning", sa.Text(), nullable=True),
        sa.Column("goal", sa.Text(), nullable=True),
        sa.Column("result", sa.Text(), nullable=True),
        sa.Column("key_themes", sa.JSON(), nullable=True),
        sa.Column("intent_questions", sa.JSON(), nullable=True),
        sa.UniqueConstraint("week_id", "language", name="uq_module_week_translation"),
    )

    op.create_table(
        "module_day_translations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("day_id", sa.Integer(), sa.ForeignKey("module_days.id", ondelete="CASCADE"), nullable=False),
        sa.Column("language", sa.String(length=8), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("focus", sa.Text(), nullable=True),
        sa.Column("task_text", sa.Text(), nullable=True),
        sa.Column("task_subtasks", sa.JSON(), nullable=True),
        sa.Column("quiz", sa.JSON(), nullable=True),
        sa.Column("reflection", sa.JSON(), nullable=True),
        sa.UniqueConstraint("day_id", "language", name="uq_module_day_translation"),
    )

    op.create_table(
        "marker_translations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("marker_id", sa.Integer(), sa.ForeignKey("markers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("language", sa.String(length=8), nullable=False),
        sa.Column("question", sa.Text(), nullable=True),
        sa.Column("options", sa.JSON(), nullable=True),
        sa.UniqueConstraint("marker_id", "language", name="uq_marker_translation"),
    )

    op.create_table(
        "selfcheck_question_translations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("question_id", sa.Integer(), sa.ForeignKey("selfcheck_questions.id", ondelete="CASCADE"), nullable=False),
        sa.Column("language", sa.String(length=8), nullable=False),
        sa.Column("question", sa.Text(), nullable=True),
        sa.Column("option_texts", sa.JSON(), nullable=True),
        sa.UniqueConstraint("question_id", "language", name="uq_selfcheck_question_translation"),
    )

    op.create_table(
        "zone_interp_translations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("zone_id", sa.Integer(), sa.ForeignKey("zone_interps.id", ondelete="CASCADE"), nullable=False),
        sa.Column("language", sa.String(length=8), nullable=False),
        sa.Column("meaning", sa.Text(), nullable=True),
        sa.Column("user_text", sa.Text(), nullable=True),
        sa.Column("recommendation", sa.Text(), nullable=True),
        sa.UniqueConstraint("zone_id", "language", name="uq_zone_interp_translation"),
    )

    op.create_table(
        "critical_trigger_translations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("trigger_id", sa.Integer(), sa.ForeignKey("critical_triggers.id", ondelete="CASCADE"), nullable=False),
        sa.Column("language", sa.String(length=8), nullable=False),
        sa.Column("additional_text", sa.Text(), nullable=True),
        sa.UniqueConstraint("trigger_id", "language", name="uq_critical_trigger_translation"),
    )

    op.create_table(
        "final_product_template_translations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("module_code", sa.String(length=16), sa.ForeignKey("final_product_templates.module_code", ondelete="CASCADE"), nullable=False),
        sa.Column("language", sa.String(length=8), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("sections", sa.JSON(), nullable=True),
        sa.UniqueConstraint("module_code", "language", name="uq_final_product_template_translation"),
    )

    op.create_table(
        "postmodule_config_translations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("module_code", sa.String(length=16), sa.ForeignKey("postmodule_config.module_code", ondelete="CASCADE"), nullable=False),
        sa.Column("language", sa.String(length=8), nullable=False),
        sa.Column("config", sa.JSON(), nullable=True),
        sa.UniqueConstraint("module_code", "language", name="uq_postmodule_config_translation"),
    )

    op.create_table(
        "intake_config_translations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("config_id", sa.Integer(), sa.ForeignKey("intake_config.id", ondelete="CASCADE"), nullable=False),
        sa.Column("language", sa.String(length=8), nullable=False),
        sa.Column("client_intro", sa.Text(), nullable=True),
        sa.Column("start_button", sa.String(length=64), nullable=True),
        sa.Column("reference_period", sa.String(length=64), nullable=True),
        sa.Column("soft_no_leading", sa.Text(), nullable=True),
        sa.Column("must_include", sa.Text(), nullable=True),
        sa.UniqueConstraint("config_id", "language", name="uq_intake_config_translation"),
    )

    op.create_table(
        "intake_direction_translations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("direction_code", sa.String(length=16), sa.ForeignKey("intake_directions.code", ondelete="CASCADE"), nullable=False),
        sa.Column("language", sa.String(length=8), nullable=False),
        sa.Column("name_short", sa.String(length=255), nullable=True),
        sa.Column("name_leading", sa.String(length=255), nullable=True),
        sa.Column("purpose", sa.Text(), nullable=True),
        sa.UniqueConstraint("direction_code", "language", name="uq_intake_direction_translation"),
    )

    op.create_table(
        "intake_question_translations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("question_n", sa.Integer(), sa.ForeignKey("intake_questions.n", ondelete="CASCADE"), nullable=False),
        sa.Column("language", sa.String(length=8), nullable=False),
        sa.Column("text", sa.Text(), nullable=True),
        sa.UniqueConstraint("question_n", "language", name="uq_intake_question_translation"),
    )

    op.create_table(
        "intake_interp_translations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("interp_id", sa.Integer(), sa.ForeignKey("intake_interps.id", ondelete="CASCADE"), nullable=False),
        sa.Column("language", sa.String(length=8), nullable=False),
        sa.Column("client_text", sa.Text(), nullable=True),
        sa.UniqueConstraint("interp_id", "language", name="uq_intake_interp_translation"),
    )

    op.create_table(
        "intake_static_text_translations",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("static_key", sa.String(length=32), sa.ForeignKey("intake_static_texts.key", ondelete="CASCADE"), nullable=False),
        sa.Column("language", sa.String(length=8), nullable=False),
        sa.Column("text", sa.Text(), nullable=True),
        sa.UniqueConstraint("static_key", "language", name="uq_intake_static_text_translation"),
    )


def downgrade() -> None:
    op.drop_table("intake_static_text_translations")
    op.drop_table("intake_interp_translations")
    op.drop_table("intake_question_translations")
    op.drop_table("intake_direction_translations")
    op.drop_table("intake_config_translations")
    op.drop_table("postmodule_config_translations")
    op.drop_table("final_product_template_translations")
    op.drop_table("critical_trigger_translations")
    op.drop_table("zone_interp_translations")
    op.drop_table("selfcheck_question_translations")
    op.drop_table("marker_translations")
    op.drop_table("module_day_translations")
    op.drop_table("module_week_translations")
    op.drop_table("module_translations")
