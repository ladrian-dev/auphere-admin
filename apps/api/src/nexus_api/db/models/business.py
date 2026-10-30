"""La ficha del negocio — spec 047, ola 2 (migración 0179, ``data-model.md`` §1).

La ficha vive en tablas por cliente; el ClientSpec es su vista tipada
(research D3). Esta tanda trae lo del alta y la lectura de la web; las sedes,
los horarios, las fechas especiales, los servicios y las preguntas frecuentes
llegan con la T055.

Todas por cliente, con RLS FORCE. La información, la descripción y lo leído de
una web son **datos no confiables** (§III): viajan vallados y nunca como
instrucción. ``content_rev`` sube con cualquier cambio de la ficha y entra en la
clave de compilación del agente (research D4).

Los vocabularios son ``String`` con su ``CHECK``, como en Reservas.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    DateTime,
    ForeignKeyConstraint,
    Integer,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from nexus_api.db.base import Base
from nexus_api.db.models._mixins import UUIDPrimaryKey

#: Las secciones de la ficha, cada una con su revisión para ``If-Match``.
SECTIONS: tuple[str, ...] = (
    "basics",
    "locations",
    "hours",
    "special_dates",
    "services",
    "policies",
    "faqs",
    "sources",
    "links",
)
#: Requisito 8.5.
SECTION_STATES: tuple[str, ...] = ("complete", "read_pending", "pending", "optional")
#: De dónde viene un dato (requisito 13).
SOURCES: tuple[str, ...] = (
    "person",
    "web",
    "document",
    "social",
    "migrated",
    "builder",
    "inbox_correction",
    "import",
)
#: Desde dónde se escribió.
ORIGINS: tuple[str, ...] = ("console", "lite_web", "app", "admin", "api", "system")
#: Quién lo escribió. ``actor_id`` es su identificador en su espacio.
ACTOR_KINDS: tuple[str, ...] = ("partner_member", "client_user", "operator", "system", "builder")
#: ``pending`` se pinta «Leído de la web · revísalo».
REVIEWS: tuple[str, ...] = ("pending", "confirmed")
CHANGE_KINDS: tuple[str, ...] = (
    "edit",
    "read_applied",
    "builder_applied",
    "correction",
    "migration",
    "import",
    "undo",
)
DECISIONS: tuple[str, ...] = ("accepted", "edited", "discarded")
NETWORKS: tuple[str, ...] = (
    "web",
    "instagram",
    "facebook",
    "tiktok",
    "linkedin",
    "youtube",
    "x",
    "threads",
)

NICHE_MIN, NICHE_MAX = 2, 80
INFO_MAX = 2000


def _in(values: tuple[str, ...]) -> str:
    return ", ".join(f"'{v}'" for v in values)


def _created_at() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), nullable=False, server_default=text("now()"))


class BusinessProfile(Base):
    """1:1 con el cliente."""

    __tablename__ = "business_profiles"
    __table_args__ = (
        CheckConstraint(
            f"char_length(niche) BETWEEN {NICHE_MIN} AND {NICHE_MAX}",
            name="ck_business_profiles_niche",
        ),
        CheckConstraint(
            f"info IS NULL OR char_length(info) <= {INFO_MAX}", name="ck_business_profiles_info"
        ),
        CheckConstraint(
            "country IS NULL OR country ~ '^[A-Z]{2}$'", name="ck_business_profiles_country"
        ),
        CheckConstraint(
            "price_currency IS NULL OR price_currency ~ '^[A-Z]{3}$'",
            name="ck_business_profiles_currency",
        ),
        CheckConstraint("content_rev >= 1", name="ck_business_profiles_rev"),
        CheckConstraint(
            "sector IS NULL OR (jsonb_typeof(sector) = 'object' "
            "AND sector ? 'key' AND sector ? 'label' "
            "AND (sector->>'key') ~ '^[a-z_]{1,40}$' "
            "AND char_length(sector->>'label') BETWEEN 1 AND 40)",
            name="ck_business_profiles_sector",
        ),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    niche: Mapped[str] = mapped_column(String(NICHE_MAX), nullable=False)
    #: Dato no confiable (§III).
    info: Mapped[str | None] = mapped_column(Text, nullable=True)
    website: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: ISO 3166-1 alfa-2.
    country: Mapped[str | None] = mapped_column(String(2), nullable=True)
    #: IANA, validada con ``zoneinfo``.
    timezone: Mapped[str] = mapped_column(String(64), nullable=False)
    #: ISO 4217 de los precios del negocio (no la moneda de la bolsa).
    price_currency: Mapped[str | None] = mapped_column(String(3), nullable=True)
    #: Por defecto, cierto si el país es de la UE o del EEE (research D22).
    eu_only: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    #: Solo el admin (requisito 54.6).
    sovereign: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    #: ``{cancellation, payments, deposit, no_show}``, cada una ≤ 1.000.
    policies: Mapped[dict[str, Any]] = mapped_column(
        JSONB, nullable=False, default=dict, server_default=text("'{}'::jsonb")
    )
    content_rev: Mapped[int] = mapped_column(
        BigInteger, nullable=False, default=1, server_default="1"
    )
    #: Spec 047, enmienda del 2026-10-29 (requisito 57.1, migración 0206): el sector
    #: del negocio, ``{key, label, confidence, source, decided_by}``; ``None``
    #: mientras se identifica. Se lee con ``services.business.sector.stored``.
    sector: Mapped[dict[str, Any] | None] = mapped_column(JSONB(none_as_null=True), nullable=True)
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
        onupdate=text("now()"),
    )


class BusinessSection(Base):
    __tablename__ = "business_sections"
    __table_args__ = (
        CheckConstraint(f"section IN ({_in(SECTIONS)})", name="ck_business_sections_section"),
        CheckConstraint(f"state IN ({_in(SECTION_STATES)})", name="ck_business_sections_state"),
        CheckConstraint(
            f"updated_by_kind IS NULL OR updated_by_kind IN ({_in(ACTOR_KINDS)})",
            name="ck_business_sections_by",
        ),
        CheckConstraint(
            f"updated_origin IS NULL OR updated_origin IN ({_in(ORIGINS)})",
            name="ck_business_sections_origin",
        ),
        CheckConstraint("revision >= 0", name="ck_business_sections_revision"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    section: Mapped[str] = mapped_column(String(16), primary_key=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    state: Mapped[str] = mapped_column(
        String(16), nullable=False, default="pending", server_default="pending"
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_by_kind: Mapped[str | None] = mapped_column(String(16), nullable=True)
    updated_by_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    updated_origin: Mapped[str | None] = mapped_column(String(16), nullable=True)


class BusinessFieldProvenance(Base):
    """La procedencia **vigente** de cada dato, por su puntero JSON en el ClientSpec."""

    __tablename__ = "business_field_provenance"
    __table_args__ = (
        CheckConstraint(f"source IN ({_in(SOURCES)})", name="ck_business_provenance_source"),
        CheckConstraint(
            f"actor_kind IS NULL OR actor_kind IN ({_in(ACTOR_KINDS)})",
            name="ck_business_provenance_actor",
        ),
        CheckConstraint(f"origin IN ({_in(ORIGINS)})", name="ck_business_provenance_origin"),
        CheckConstraint(f"review IN ({_in(REVIEWS)})", name="ck_business_provenance_review"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True)
    pointer: Mapped[str] = mapped_column(String(300), primary_key=True)
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    actor_kind: Mapped[str | None] = mapped_column(String(16), nullable=True)
    actor_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    origin: Mapped[str] = mapped_column(String(16), nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: «Traducido de {idioma}».
    translated_from: Mapped[str | None] = mapped_column(String(16), nullable=True)
    review: Mapped[str] = mapped_column(
        String(16), nullable=False, default="confirmed", server_default="confirmed"
    )
    at: Mapped[datetime] = _created_at()


class BusinessChange(UUIDPrimaryKey, Base):
    """El historial y el deshacer. Deshacer aplica ``before`` si nadie escribió la
    sección después; si alguien escribió, ``412`` con lo que cambió."""

    __tablename__ = "business_changes"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_business_changes_tenant_id"),
        CheckConstraint(f"section IN ({_in(SECTIONS)})", name="ck_business_changes_section"),
        CheckConstraint(f"kind IN ({_in(CHANGE_KINDS)})", name="ck_business_changes_kind"),
        CheckConstraint(
            f"actor_kind IS NULL OR actor_kind IN ({_in(ACTOR_KINDS)})",
            name="ck_business_changes_actor",
        ),
        CheckConstraint(f"origin IN ({_in(ORIGINS)})", name="ck_business_changes_origin"),
        ForeignKeyConstraint(
            ["tenant_id", "undo_of"],
            ["business_changes.tenant_id", "business_changes.id"],
            name="fk_business_changes_undo_of",
        ),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    section: Mapped[str] = mapped_column(String(16), nullable=False)
    kind: Mapped[str] = mapped_column(String(20), nullable=False)
    before: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    after: Mapped[dict[str, Any] | None] = mapped_column(JSONB, nullable=True)
    actor_kind: Mapped[str | None] = mapped_column(String(16), nullable=True)
    actor_id: Mapped[str | None] = mapped_column(String(160), nullable=True)
    origin: Mapped[str] = mapped_column(String(16), nullable=False)
    at: Mapped[datetime] = _created_at()
    undone_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    undone_by: Mapped[str | None] = mapped_column(String(160), nullable=True)
    undo_of: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)


class BusinessSuggestion(UUIDPrimaryKey, Base):
    """Lo leído que no se aplicó solo: lo que contradice un dato escrito por una
    persona (requisito 5.8) y lo «Sugerido · confirma» (requisito 18.3). Sin caducidad."""

    __tablename__ = "business_suggestions"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_business_suggestions_tenant_id"),
        CheckConstraint(f"source IN ({_in(SOURCES)})", name="ck_business_suggestions_source"),
        CheckConstraint(
            "(decision IS NULL) = (decided_at IS NULL) "
            f"AND (decision IS NULL OR decision IN ({_in(DECISIONS)}))",
            name="ck_business_suggestions_decision",
        ),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    pointer: Mapped[str] = mapped_column(String(300), nullable=False)
    proposed_value: Mapped[Any] = mapped_column(JSONB, nullable=False)
    current_value: Mapped[Any | None] = mapped_column(JSONB, nullable=True)
    source: Mapped[str] = mapped_column(String(20), nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    translated_from: Mapped[str | None] = mapped_column(String(16), nullable=True)
    created_at: Mapped[datetime] = _created_at()
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    decided_by: Mapped[str | None] = mapped_column(String(160), nullable=True)
    decision: Mapped[str | None] = mapped_column(String(16), nullable=True)


class BusinessLink(UUIDPrimaryKey, Base):
    """La web y las redes. Única por cliente, red y ``coalesce(handle, url)``."""

    __tablename__ = "business_links"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_business_links_tenant_id"),
        CheckConstraint(f"network IN ({_in(NETWORKS)})", name="ck_business_links_network"),
        CheckConstraint("url IS NOT NULL OR handle IS NOT NULL", name="ck_business_links_target"),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    network: Mapped[str] = mapped_column(String(16), nullable=False)
    url: Mapped[str | None] = mapped_column(Text, nullable=True)
    handle: Mapped[str | None] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = _created_at()


# ── Spec 047, T055 (migración 0183): sedes, horarios, fechas especiales, FAQ ──

#: ``blocks`` (los mismos turnos para varios días) o ``daily`` (día por día).
SCHEDULE_LAYOUTS: tuple[str, ...] = ("blocks", "daily")
#: Las horas son minutos desde la medianoche del día que abre: un turno nocturno
#: cierra después de 1.440 (research D15).
MINUTES_PER_DAY = 1440
MAX_SHIFTS_PER_DAY = 6

_SHIFT_CHECKS = (
    "open_min BETWEEN 0 AND 1439",
    "close_min BETWEEN 1 AND 2880",
    "close_min > open_min AND close_min - open_min <= 1440",
)


def _updated_at() -> Mapped[datetime]:
    return mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
        onupdate=text("now()"),
    )


class BusinessLocation(UUIDPrimaryKey, Base):
    """Una sede: nombre, dirección, teléfono y horario propio opcional."""

    __tablename__ = "business_locations"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_business_locations_tenant_id"),
        CheckConstraint("char_length(name) BETWEEN 1 AND 80", name="ck_business_locations_name"),
        CheckConstraint(
            "phone_e164 IS NULL OR phone_e164 ~ '^\\+[1-9][0-9]{6,14}$'",
            name="ck_business_locations_phone",
        ),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    address: Mapped[str | None] = mapped_column(String(300), nullable=True)
    phone_e164: Mapped[str | None] = mapped_column(String(20), nullable=True)
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    archived_by: Mapped[str | None] = mapped_column(String(160), nullable=True)
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()


class BusinessSchedule(UUIDPrimaryKey, Base):
    """El horario del negocio (``location_id`` nulo) o de una sede. Uno de cada."""

    __tablename__ = "business_schedules"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_business_schedules_tenant_id"),
        UniqueConstraint(
            "tenant_id",
            "location_id",
            name="uq_business_schedules_owner",
            postgresql_nulls_not_distinct=True,
        ),
        CheckConstraint(
            f"layout IN ({_in(SCHEDULE_LAYOUTS)})", name="ck_business_schedules_layout"
        ),
        ForeignKeyConstraint(
            ["tenant_id", "location_id"],
            ["business_locations.tenant_id", "business_locations.id"],
            name="fk_business_schedules_location",
            ondelete="CASCADE",
        ),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    location_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    layout: Mapped[str] = mapped_column(
        String(8), nullable=False, default="blocks", server_default="blocks"
    )
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()


class BusinessShift(UUIDPrimaryKey, Base):
    """Un turno: ``weekday`` 0 = lunes; ``close_min`` > 1.440 cierra al día siguiente."""

    __tablename__ = "business_shifts"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_business_shifts_tenant_id"),
        CheckConstraint("weekday BETWEEN 0 AND 6", name="ck_business_shifts_weekday"),
        CheckConstraint(_SHIFT_CHECKS[0], name="ck_business_shifts_open"),
        CheckConstraint(_SHIFT_CHECKS[1], name="ck_business_shifts_close"),
        CheckConstraint(_SHIFT_CHECKS[2], name="ck_business_shifts_span"),
        ForeignKeyConstraint(
            ["tenant_id", "schedule_id"],
            ["business_schedules.tenant_id", "business_schedules.id"],
            name="fk_business_shifts_schedule",
            ondelete="CASCADE",
        ),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    schedule_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    weekday: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    open_min: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    close_min: Mapped[int] = mapped_column(SmallInteger, nullable=False)


class BusinessSpecialDate(UUIDPrimaryKey, Base):
    """Un cierre o un horario distinto, de un día o de un rango, con nombre."""

    __tablename__ = "business_special_dates"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_business_special_dates_tenant_id"),
        CheckConstraint("date_to >= date_from", name="ck_business_special_dates_range"),
        ForeignKeyConstraint(
            ["tenant_id", "location_id"],
            ["business_locations.tenant_id", "business_locations.id"],
            name="fk_business_special_dates_location",
            ondelete="CASCADE",
        ),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    location_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    name: Mapped[str] = mapped_column(String(80), nullable=False)
    date_from: Mapped[date] = mapped_column(Date, nullable=False)
    date_to: Mapped[date] = mapped_column(Date, nullable=False)
    #: Cerrado todo el día; si no, valen sus ``BusinessSpecialShift``.
    closed: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True, server_default=text("true")
    )
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = _created_at()


class BusinessSpecialShift(UUIDPrimaryKey, Base):
    __tablename__ = "business_special_shifts"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_business_special_shifts_tenant_id"),
        CheckConstraint(_SHIFT_CHECKS[0], name="ck_business_special_shifts_open"),
        CheckConstraint(_SHIFT_CHECKS[1], name="ck_business_special_shifts_close"),
        CheckConstraint(_SHIFT_CHECKS[2], name="ck_business_special_shifts_span"),
        ForeignKeyConstraint(
            ["tenant_id", "special_date_id"],
            ["business_special_dates.tenant_id", "business_special_dates.id"],
            name="fk_business_special_shifts_date",
            ondelete="CASCADE",
        ),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    special_date_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    open_min: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    close_min: Mapped[int] = mapped_column(SmallInteger, nullable=False)


class BusinessFaq(UUIDPrimaryKey, Base):
    """Una pregunta frecuente **del negocio**. Las propias de un agente van en su AgentSpec."""

    __tablename__ = "business_faqs"
    __table_args__ = (UniqueConstraint("tenant_id", "id", name="uq_business_faqs_tenant_id"),)

    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    q: Mapped[str] = mapped_column(String(300), nullable=False)
    a: Mapped[str] = mapped_column(String(2000), nullable=False)
    #: «Sugerido · confirma» (requisito 18.3).
    suggested: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("false")
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    archived_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()


# ── Spec 047, enmienda del 2026-10-29 (migración 0206): los agentes sugeridos ──

SUGGESTED_AGENT_STATUSES: tuple[str, ...] = ("open", "dismissed", "superseded")
SUGGESTED_AGENT_ROLES: tuple[str, ...] = ("reception", "sales", "billing", "support")


class SuggestedAgent(UUIDPrimaryKey, Base):
    """Un agente que propone el constructor del cliente (requisito 60.6). No se crea
    solo: «Crear este agente» abre «Nuevo agente» relleno y «Descartar» lo aparta
    (no vuelve). ``name_key`` es el nombre normalizado, para no repetirlo."""

    __tablename__ = "suggested_agents"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_suggested_agents_tenant_id"),
        CheckConstraint(
            f"status IN ({_in(SUGGESTED_AGENT_STATUSES)})", name="ck_suggested_agents_status"
        ),
        CheckConstraint(
            f"role IS NULL OR role IN ({_in(SUGGESTED_AGENT_ROLES)})",
            name="ck_suggested_agents_role",
        ),
        CheckConstraint(
            "(status = 'open') = (decided_at IS NULL)", name="ck_suggested_agents_decided"
        ),
        ForeignKeyConstraint(
            ["tenant_id", "job_id"],
            ["jobs.tenant_id", "jobs.id"],
            name="fk_suggested_agents_job",
            ondelete="SET NULL",
        ),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    name: Mapped[str] = mapped_column(String(40), nullable=False)
    name_key: Mapped[str] = mapped_column(String(60), nullable=False)
    description: Mapped[str] = mapped_column(String(1024), nullable=False)
    role: Mapped[str | None] = mapped_column(String(12), nullable=True)
    status: Mapped[str] = mapped_column(
        String(12), nullable=False, default="open", server_default="open"
    )
    #: La huella de la ficha con la que se propuso.
    fingerprint: Mapped[str | None] = mapped_column(String(64), nullable=True)
    job_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    decided_by: Mapped[str | None] = mapped_column(String(160), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = _created_at()
    updated_at: Mapped[datetime] = _updated_at()
