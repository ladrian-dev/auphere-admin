"""Rutinas de agente — spec 082 (migración 0244, ``data-model.md``).

Una rutina es una instrucción que el agente de un cliente ejecuta a su hora, y
cuya respuesta lee el partner en la consola. Todo cuelga del cliente: FORCE RLS
por ``tenant_id`` y clave compuesta ``(tenant_id, agent_id)`` al agente, porque
la comprobación de una clave foránea no pasa por la RLS.

Dos cosas que parecen detalles y no lo son:

- ``Schedule.state`` es **la intención del partner**, no lo que va a pasar. El
  estado efectivo se calcula al leer, cruzándolo con el del agente y con el
  saldo de la bolsa, así ninguna rutina se queda pegada en pausa porque nadie
  corrió el proceso que la despierta.
- ``ScheduleRun.instruction`` guarda el texto **con el que se ejecutó**. Editar
  la rutina no reescribe su historial: lo que contestó el agente contestaba a
  otra pregunta.

Aquí no hay nada de ningún cliente final, porque una rutina no tiene
conversación. Si alguna vez una columna de estas dos tablas necesita nombrar a
una persona de fuera, el diseño se torció.
"""

from __future__ import annotations

import datetime as dt
import uuid
from typing import Any, Final

from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    ForeignKeyConstraint,
    Integer,
    SmallInteger,
    String,
    Text,
    Time,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import Mapped, mapped_column

from nexus_api.db.base import Base
from nexus_api.db.models._mixins import UUIDPrimaryKey

#: Las cuatro periodicidades, y ninguna más. Nada de cron de cinco campos.
CADENCES: Final[tuple[str, ...]] = ("daily", "weekly", "monthly", "once")
#: Lo que el partner quiere que pase con la rutina.
SCHEDULE_STATES: Final[tuple[str, ...]] = ("active", "paused", "archived")
#: Por qué está parada. ``manual`` la pone una persona y solo una persona la
#: quita: las otras tres las pone y las quita el sistema.
PAUSE_REASONS: Final[tuple[str, ...]] = (
    "manual",
    "agent_unavailable",
    "no_balance",
    "failures",
)
#: La pausa que el sistema deshace solo, como ya hace con los agentes.
SYSTEM_PAUSE_REASONS: Final[frozenset[str]] = frozenset(
    {"agent_unavailable", "no_balance", "failures"}
)
#: Cómo acabó una ejecución. ``partial`` es de primera clase: una ejecución a la
#: que le faltó una herramienta nunca aparece como hecha.
RUN_STATUSES: Final[tuple[str, ...]] = ("running", "done", "partial", "failed", "skipped")
RUN_TRIGGERS: Final[tuple[str, ...]] = ("schedule", "manual")
#: Intentos de una ejecución antes de darla por fallida (requisito 7.2).
MAX_ATTEMPTS: Final = 3
#: Lo que se espera a una ejecución que no llegó a empezar. Pasada, no se
#: ejecuta tarde: nadie quiere a las dos de la tarde el informe de las nueve.
GRACE: Final = dt.timedelta(hours=1)
#: Ejecuciones seguidas fallidas que pausan la rutina (requisito 7.5).
FAILURES_BEFORE_PAUSE: Final = 3
#: Rutinas activas por cliente (requisito 12.1).
MAX_ACTIVE_PER_TENANT: Final = 20


class Schedule(UUIDPrimaryKey, Base):
    """Lo que el partner configura una vez."""

    __tablename__ = "schedules"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_schedules_tenant_id"),
        ForeignKeyConstraint(
            ["tenant_id", "agent_id"],
            ["agents.tenant_id", "agents.id"],
            name="fk_schedules_agent",
            ondelete="CASCADE",
        ),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    agent_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    name: Mapped[str] = mapped_column(String(60), nullable=False)
    instruction: Mapped[str] = mapped_column(Text, nullable=False)

    cadence: Mapped[str] = mapped_column(String(16), nullable=False)
    #: Solo ``weekly``. **Lunes 0, domingo 6**, la convención de
    #: ``datetime.weekday()`` y de ``WEEKDAYS`` en ``services/business_hours.py``.
    #: La consola traduce, porque en JavaScript el domingo es 0.
    weekdays: Mapped[list[int] | None] = mapped_column(ARRAY(SmallInteger), nullable=True)
    #: Solo ``monthly``. Del 1 al 28, para que exista todos los meses.
    day_of_month: Mapped[int | None] = mapped_column(SmallInteger, nullable=True)
    #: Solo ``once``.
    run_date: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    #: La hora del negocio. Sin zona: la zona se lee de ``tenants.timezone`` al
    #: calcular, y así un cambio de zona mueve las próximas sin migrar nada.
    local_time: Mapped[dt.time] = mapped_column(Time, nullable=False)

    email: Mapped[bool] = mapped_column(Boolean, nullable=False, server_default=text("false"))

    state: Mapped[str] = mapped_column(String(16), nullable=False, server_default="active")
    pause_reason: Mapped[str | None] = mapped_column(String(32), nullable=True)
    #: El siguiente disparo, en absoluto. Materializado para que el barrido vaya
    #: por índice y para que dos réplicas no se pisen.
    next_run_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    #: Cuenta **ejecuciones**, nunca intentos. A cero en cuanto una acaba bien.
    consecutive_failures: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default="0"
    )

    created_by: Mapped[str] = mapped_column(String(160), nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
        onupdate=text("now()"),
    )


class ScheduleRun(UUIDPrimaryKey, Base):
    """Una vez que la rutina corrió, con sus intentos dentro.

    La ejecución **es** el conjunto de sus intentos: el partner ve una tarjeta
    con cuántos llevó, no tres. Lo que impide que dos réplicas disparen la misma
    es ``uq_schedule_runs_slot``, una clave única y no un candado.
    """

    __tablename__ = "schedule_runs"
    __table_args__ = (
        UniqueConstraint("tenant_id", "id", name="uq_schedule_runs_tenant_id"),
        UniqueConstraint("tenant_id", "schedule_id", "scheduled_for", name="uq_schedule_runs_slot"),
        ForeignKeyConstraint(
            ["tenant_id", "schedule_id"],
            ["schedules.tenant_id", "schedules.id"],
            name="fk_schedule_runs_schedule",
            ondelete="CASCADE",
        ),
    )

    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    schedule_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)
    #: La hora que le tocaba. Para una manual, el instante en que se pidió.
    scheduled_for: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    trigger: Mapped[str] = mapped_column(String(16), nullable=False, server_default="schedule")
    status: Mapped[str] = mapped_column(String(16), nullable=False, server_default="running")
    attempts: Mapped[int] = mapped_column(SmallInteger, nullable=False, server_default="1")

    #: La instrucción con la que se ejecutó, no la de ahora.
    instruction: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    tools_used: Mapped[list[Any] | None] = mapped_column(JSONB, nullable=True)
    #: Lo que no se pudo ofrecer y por qué. Es lo que hace honesto el
    #: ``partial``: un informe al que le falta una parte y no lo dice es peor
    #: que no tenerlo.
    withheld: Mapped[list[Any] | None] = mapped_column(JSONB, nullable=True)

    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_micros: Mapped[int] = mapped_column(BigInteger, nullable=False, server_default="0")
    error_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    error_detail: Mapped[str | None] = mapped_column(Text, nullable=True)
    #: El trabajo del intento en curso.
    job_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    started_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=text("now()")
    )


__all__ = [
    "CADENCES",
    "FAILURES_BEFORE_PAUSE",
    "GRACE",
    "MAX_ACTIVE_PER_TENANT",
    "MAX_ATTEMPTS",
    "PAUSE_REASONS",
    "RUN_STATUSES",
    "RUN_TRIGGERS",
    "SCHEDULE_STATES",
    "SYSTEM_PAUSE_REASONS",
    "Schedule",
    "ScheduleRun",
]
