"""SQLAlchemy-модели Mental Club по docs/mental-architecture.md §3, §12.

Смысловые сущности разделены (норматив §19): не один универсальный content_block.
JSON-колонки работают и в PostgreSQL, и в SQLite (для локальной проверки/тестов).
"""
from __future__ import annotations

from datetime import datetime, date

from sqlalchemy import (
    String, Text, Integer, Boolean, ForeignKey, JSON, DateTime, Date, UniqueConstraint, func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


# ─────────────────────────────────────────────────────────────────────────────
# КОНТЕНТ МОДУЛЯ (статика, версионируется; загрузка из content/modules/*.yaml)
# ─────────────────────────────────────────────────────────────────────────────

class Module(Base):
    __tablename__ = "modules"
    code: Mapped[str] = mapped_column(String(16), primary_key=True)          # REAL, BOUND, ...
    name: Mapped[str] = mapped_column(String(255))
    subtitle: Mapped[str | None] = mapped_column(String(255), nullable=True)
    content_version: Mapped[str] = mapped_column(String(32))
    final_product_kind: Mapped[str] = mapped_column(String(32))              # protocol|map|...
    postmodule_kind: Mapped[str] = mapped_column(String(16))                 # test|flags|none
    passport: Mapped[dict] = mapped_column(JSON)

    weeks: Mapped[list["ModuleWeek"]] = relationship(back_populates="module", cascade="all, delete-orphan")
    markers: Mapped[list["Marker"]] = relationship(cascade="all, delete-orphan")
    audio: Mapped[list["AudioAsset"]] = relationship(cascade="all, delete-orphan")
    final_product: Mapped["FinalProductTemplate"] = relationship(cascade="all, delete-orphan", uselist=False)
    postmodule: Mapped["PostmoduleConfig"] = relationship(cascade="all, delete-orphan", uselist=False)


class ModuleWeek(Base):
    __tablename__ = "module_weeks"
    __table_args__ = (UniqueConstraint("module_code", "n"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    module_code: Mapped[str] = mapped_column(ForeignKey("modules.code"))
    n: Mapped[int] = mapped_column(Integer)                                  # 1..6
    title: Mapped[str] = mapped_column(String(255))
    intro_screen: Mapped[str] = mapped_column(Text)
    meaning: Mapped[str] = mapped_column(Text)
    goal: Mapped[str] = mapped_column(Text)
    result: Mapped[str] = mapped_column(Text)
    key_themes: Mapped[list] = mapped_column(JSON, default=list)
    intent_questions: Mapped[list] = mapped_column(JSON, default=list)       # W6-спец

    module: Mapped["Module"] = relationship(back_populates="weeks")
    days: Mapped[list["ModuleDay"]] = relationship(cascade="all, delete-orphan")
    selfcheck: Mapped[list["SelfcheckQuestion"]] = relationship(cascade="all, delete-orphan")
    zones: Mapped[list["ZoneInterp"]] = relationship(cascade="all, delete-orphan")
    critical_triggers: Mapped[list["CriticalTrigger"]] = relationship(cascade="all, delete-orphan")


class ModuleDay(Base):
    __tablename__ = "module_days"
    __table_args__ = (UniqueConstraint("week_id", "day_n"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    week_id: Mapped[int] = mapped_column(ForeignKey("module_weeks.id"))
    day_n: Mapped[int] = mapped_column(Integer)                              # 1..7
    title: Mapped[str] = mapped_column(String(255))
    focus: Mapped[str] = mapped_column(Text)                                 # §8.1
    task_text: Mapped[str] = mapped_column(Text)                             # §8.2 (практика)
    task_subtasks: Mapped[list] = mapped_column(JSON, default=list)
    quiz: Mapped[dict] = mapped_column(JSON)                                 # §8.5 {kind,question,options,...}
    reflection: Mapped[list] = mapped_column(JSON, default=list)             # §8.6 (3 вопроса)


class Marker(Base):
    """5 утренних + 5 вечерних, константы модуля. Не в дневник, без весов (§5)."""
    __tablename__ = "markers"
    __table_args__ = (UniqueConstraint("module_code", "phase", "idx"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    module_code: Mapped[str] = mapped_column(ForeignKey("modules.code"))
    phase: Mapped[str] = mapped_column(String(8))                            # morning|evening
    idx: Mapped[int] = mapped_column(Integer)                                # 1..5
    question: Mapped[str] = mapped_column(Text)
    options: Mapped[list] = mapped_column(JSON)


class AudioAsset(Base):
    """Практика-«слот» программы (неделя+слот) — языко-независимая часть учебного плана.
    Сами файлы/язык/доставка — в дочерних AudioVariant (§ аудио: многоязычность, каналы)."""
    __tablename__ = "audio_assets"
    __table_args__ = (UniqueConstraint("code"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    module_code: Mapped[str] = mapped_column(ForeignKey("modules.code"))
    week_n: Mapped[int] = mapped_column(Integer)
    slot: Mapped[str] = mapped_column(String(8))                             # A1|A2|A3|FINAL
    code: Mapped[str] = mapped_column(String(64))                            # AUDIO_{MOD}_W{n}_{slot}
    day_range: Mapped[str] = mapped_column(String(16))
    title: Mapped[str | None] = mapped_column(String(255), nullable=True)
    theme: Mapped[str | None] = mapped_column(Text, nullable=True)

    variants: Mapped[list["AudioVariant"]] = relationship(cascade="all, delete-orphan",
                                                          back_populates="audio_asset")


class AudioVariant(Base):
    """Одна языковая запись практики: где лежит файл + кэш ID доставки по каналам.

    storage_key — относительный путь/ключ, НЕ привязан к конкретному хранилищу (диск сейчас,
    S3-совместимое хранилище потом — меняется только то, как storage_key превращается в URL,
    см. app.services.audio). channel_cache — {"telegram": "<file_id>", "whatsapp": "<media_id>"}:
    у каждого канала свой механизм кэширования после первой отправки (Telegram file_id и WhatsApp
    media_id — разные вещи, ни одна не переносится на другой канал).
    """
    __tablename__ = "audio_variants"
    __table_args__ = (UniqueConstraint("audio_asset_id", "language"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    audio_asset_id: Mapped[int] = mapped_column(ForeignKey("audio_assets.id"))
    language: Mapped[str] = mapped_column(String(8))                        # ru|en|uk…
    storage_key: Mapped[str] = mapped_column(String(255))                   # напр. AUDIO_BOUND_W1_A2_ru.mp3
    mime: Mapped[str | None] = mapped_column(String(64), nullable=True)
    duration_sec: Mapped[int | None] = mapped_column(Integer, nullable=True)
    size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    channel_cache: Mapped[dict] = mapped_column(JSON, default=dict)

    audio_asset: Mapped["AudioAsset"] = relationship(back_populates="variants")


class SelfcheckQuestion(Base):
    __tablename__ = "selfcheck_questions"
    __table_args__ = (UniqueConstraint("week_id", "q_index"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    week_id: Mapped[int] = mapped_column(ForeignKey("module_weeks.id"))
    q_index: Mapped[int] = mapped_column(Integer)                            # 1..10
    kind: Mapped[str] = mapped_column(String(8))                             # core|flag
    tag: Mapped[str | None] = mapped_column(String(16), nullable=True)       # ANX|SELF|... для flag
    question: Mapped[str] = mapped_column(Text)
    options: Mapped[list] = mapped_column(JSON)                              # [{text, weight|flag_weight, critical?}]


class ZoneInterp(Base):
    __tablename__ = "zone_interps"
    __table_args__ = (UniqueConstraint("week_id", "zone"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    week_id: Mapped[int] = mapped_column(ForeignKey("module_weeks.id"))
    zone: Mapped[str] = mapped_column(String(8))                            # GREEN|YELLOW|RED
    score_min: Mapped[int] = mapped_column(Integer)
    score_max: Mapped[int] = mapped_column(Integer)
    sys_action: Mapped[str] = mapped_column(String(32))
    meaning: Mapped[str] = mapped_column(Text)
    user_text: Mapped[str] = mapped_column(Text)
    recommendation: Mapped[str] = mapped_column(Text)


class CriticalTrigger(Base):
    __tablename__ = "critical_triggers"
    id: Mapped[int] = mapped_column(primary_key=True)
    week_id: Mapped[int] = mapped_column(ForeignKey("module_weeks.id"))
    condition: Mapped[str] = mapped_column(Text)
    options: Mapped[list] = mapped_column(JSON, default=list)         # legacy: тексты вариантов (fallback)
    refs: Mapped[list] = mapped_column(JSON, default=list)           # [{q, opt}] — точные ссылки на варианты
    min_hits: Mapped[int] = mapped_column(Integer, default=1)        # сколько refs должно совпасть для срабатывания
    additional_text: Mapped[str] = mapped_column(Text)


class FinalProductTemplate(Base):
    __tablename__ = "final_product_templates"
    module_code: Mapped[str] = mapped_column(ForeignKey("modules.code"), primary_key=True)
    title: Mapped[str] = mapped_column(String(255))
    sections: Mapped[list] = mapped_column(JSON)


class PostmoduleConfig(Base):
    __tablename__ = "postmodule_config"
    module_code: Mapped[str] = mapped_column(ForeignKey("modules.code"), primary_key=True)
    kind: Mapped[str] = mapped_column(String(16))                            # test|flags|none
    config: Mapped[dict] = mapped_column(JSON)                               # rule/tags/adjacent_focus_texts | topics


# ─────────────────────────────────────────────────────────────────────────────
# ВХОДНАЯ САМООЦЕНКА — слой D (§12). Загрузка из content/intake.yaml
# ─────────────────────────────────────────────────────────────────────────────

class IntakeConfig(Base):
    __tablename__ = "intake_config"
    id: Mapped[int] = mapped_column(primary_key=True, default=1)
    version: Mapped[str] = mapped_column(String(32))
    client_intro: Mapped[str] = mapped_column(Text)
    start_button: Mapped[str] = mapped_column(String(64))
    reference_period: Mapped[str] = mapped_column(String(64))
    answer_scale: Mapped[list] = mapped_column(JSON)                         # [{value,label}]
    thresholds: Mapped[list] = mapped_column(JSON)
    soft_threshold: Mapped[int] = mapped_column(Integer)
    soft_no_leading: Mapped[str] = mapped_column(Text)
    tie_priority: Mapped[list] = mapped_column(JSON)                         # [код...]
    no_show: Mapped[list] = mapped_column(JSON)
    must_include: Mapped[str] = mapped_column(Text)


class IntakeDirection(Base):
    __tablename__ = "intake_directions"
    code: Mapped[str] = mapped_column(String(16), primary_key=True)          # = тег = код модуля
    name_short: Mapped[str] = mapped_column(String(255))
    name_leading: Mapped[str] = mapped_column(String(255))
    purpose: Mapped[str] = mapped_column(Text)
    questions: Mapped[list] = mapped_column(JSON)                            # [n,n,n]
    tie_priority: Mapped[int] = mapped_column(Integer)
    module_code: Mapped[str | None] = mapped_column(ForeignKey("modules.code"), nullable=True)


class IntakeQuestion(Base):
    __tablename__ = "intake_questions"
    n: Mapped[int] = mapped_column(Integer, primary_key=True)                # 1..30
    direction_code: Mapped[str] = mapped_column(ForeignKey("intake_directions.code"))
    text: Mapped[str] = mapped_column(Text)


class IntakeInterp(Base):
    __tablename__ = "intake_interps"
    __table_args__ = (UniqueConstraint("direction_code", "slot"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    direction_code: Mapped[str] = mapped_column(ForeignKey("intake_directions.code"))
    slot: Mapped[str] = mapped_column(String(16))                           # leading|focus1|focus2
    client_text: Mapped[str] = mapped_column(Text)


class IntakeStaticText(Base):
    __tablename__ = "intake_static_texts"
    key: Mapped[str] = mapped_column(String(32), primary_key=True)           # pre_result|result_template|outro
    text: Mapped[str] = mapped_column(Text)


# ─────────────────────────────────────────────────────────────────────────────
# IDENTITY — multi-provider пользователь (telegram|ios|whatsapp)
# ─────────────────────────────────────────────────────────────────────────────

class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    preferred_language: Mapped[str] = mapped_column(String(8), default="ru")
    timezone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    # ежедневные напоминания: утро / день(обед) / вечер (время — в таймзоне пользователя).
    # ВЕЧЕР исторически хранится в reminder_hour/minute + last_reminded_date.
    reminder_enabled: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")
    reminder_morning_hour: Mapped[int] = mapped_column(Integer, default=10, server_default="10")
    reminder_morning_minute: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    reminder_afternoon_hour: Mapped[int] = mapped_column(Integer, default=14, server_default="14")
    reminder_afternoon_minute: Mapped[int] = mapped_column(Integer, default=0, server_default="0")
    reminder_hour: Mapped[int] = mapped_column(Integer, default=20, server_default="20")       # вечер
    reminder_minute: Mapped[int] = mapped_column(Integer, default=0, server_default="0")        # вечер
    last_morning_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    last_afternoon_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    last_reminded_date: Mapped[date | None] = mapped_column(Date, nullable=True)                # вечер

    identities: Mapped[list["UserIdentity"]] = relationship(back_populates="user",
                                                            cascade="all, delete-orphan")


class UserIdentity(Base):
    __tablename__ = "user_identities"
    __table_args__ = (UniqueConstraint("provider", "provider_user_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    provider: Mapped[str] = mapped_column(String(16))            # telegram|ios|whatsapp
    provider_user_id: Mapped[str] = mapped_column(String(64))

    user: Mapped["User"] = relationship(back_populates="identities")


# ─────────────────────────────────────────────────────────────────────────────
# СОСТОЯНИЕ ПОЛЬЗОВАТЕЛЯ (runtime)
# ─────────────────────────────────────────────────────────────────────────────

class Enrollment(Base):
    __tablename__ = "enrollments"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    module_code: Mapped[str] = mapped_column(ForeignKey("modules.code"))
    started_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    current_week: Mapped[int] = mapped_column(Integer, default=1)
    current_day: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(16), default="active")        # active|selfcheck_due|completed
    mode: Mapped[str] = mapped_column(String(8), default="normal")           # normal|test (перемотка)


class DailyEntry(Base):
    __tablename__ = "daily_entries"
    __table_args__ = (UniqueConstraint("enrollment_id", "week_n", "day_n"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    enrollment_id: Mapped[int] = mapped_column(ForeignKey("enrollments.id"))
    week_n: Mapped[int] = mapped_column(Integer)
    day_n: Mapped[int] = mapped_column(Integer)
    entry_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    morning_answers: Mapped[dict] = mapped_column(JSON, default=dict)
    task_status: Mapped[str | None] = mapped_column(String(16), nullable=True)  # DONE|PARTIAL|NOT_DONE
    task_answer: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    quiz_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    evening_answers: Mapped[dict] = mapped_column(JSON, default=dict)
    reflection_answers: Mapped[list] = mapped_column(JSON, default=list)
    # день из двух сессий: утро (открыть) и вечер (закрыть)
    morning_done: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")
    evening_done: Mapped[bool] = mapped_column(Boolean, default=False, server_default="0")


class SelfcheckResult(Base):
    __tablename__ = "selfcheck_results"
    id: Mapped[int] = mapped_column(primary_key=True)
    enrollment_id: Mapped[int] = mapped_column(ForeignKey("enrollments.id"))
    week_n: Mapped[int] = mapped_column(Integer)
    core_score: Mapped[int] = mapped_column(Integer)
    zone: Mapped[str] = mapped_column(String(8))
    triggered_criticals: Mapped[list] = mapped_column(JSON, default=list)
    flags: Mapped[dict] = mapped_column(JSON, default=dict)                  # {tag: weight}


class FlagAccumulator(Base):
    __tablename__ = "flag_accumulator"
    __table_args__ = (UniqueConstraint("enrollment_id", "tag"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    enrollment_id: Mapped[int] = mapped_column(ForeignKey("enrollments.id"))
    tag: Mapped[str] = mapped_column(String(16))
    total_weight: Mapped[int] = mapped_column(Integer, default=0)
    weeks_hit: Mapped[int] = mapped_column(Integer, default=0)


class JournalEntry(Base):
    __tablename__ = "journal_entries"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    source_type: Mapped[str] = mapped_column(String(16))                     # task|reflection|final_product|note
    module_code: Mapped[str | None] = mapped_column(String(16), nullable=True)
    week_n: Mapped[int | None] = mapped_column(Integer, nullable=True)
    day_n: Mapped[int | None] = mapped_column(Integer, nullable=True)
    text: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class FinalProductInstance(Base):
    __tablename__ = "final_product_instances"
    id: Mapped[int] = mapped_column(primary_key=True)
    enrollment_id: Mapped[int] = mapped_column(ForeignKey("enrollments.id"))
    saved_content: Mapped[dict] = mapped_column(JSON)


class PostmoduleResult(Base):
    __tablename__ = "postmodule_results"
    id: Mapped[int] = mapped_column(primary_key=True)
    enrollment_id: Mapped[int] = mapped_column(ForeignKey("enrollments.id"))
    topic_scores: Mapped[dict] = mapped_column(JSON)
    recommended_modules: Mapped[list] = mapped_column(JSON)


class IntakeResult(Base):
    __tablename__ = "intake_results"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    completed_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    scores: Mapped[dict] = mapped_column(JSON)                               # {code: 0..12}
    leading: Mapped[str] = mapped_column(String(16))
    focus1: Mapped[str | None] = mapped_column(String(16), nullable=True)
    focus2: Mapped[str | None] = mapped_column(String(16), nullable=True)
    is_soft: Mapped[bool] = mapped_column(Boolean, default=False)
    chosen_module_code: Mapped[str | None] = mapped_column(String(16), nullable=True)
