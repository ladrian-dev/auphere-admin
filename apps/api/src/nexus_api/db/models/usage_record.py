"""Registro de consumo por evento (WP-16, plataforma v2).

Cierra B3: hoy ``messages.cost_usd`` es lo que factura **Meta**, y los
tokens del LLM no se persisten en ninguna tabla de producción — no se
puede cobrar por consumo ni vigilar el margen.

``usage_events`` (agregado diario) se conserva sin tocar; esta tabla es la
granularidad de evento de la que aquélla podrá derivarse.

Dos columnas separadas a propósito:

- ``cost_usd``    — lo que NOS cuesta el evento (precio de proveedor).
- ``billable_qty``— lo que FACTURAMOS por él.

Es lo que permite que la misma tabla sirva para emitir una factura y para
ver dónde se come el margen. Y ``agent_config_id`` da el consumo por
VERSIÓN de agente: es lo que responde si el prompt nuevo salió más caro
que el viejo.
"""

from __future__ import annotations

import decimal
import uuid
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Numeric, Text, text
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column

from nexus_api.db.base import Base


class UsageRecord(Base):
    """Una fila por evento medible. Particionada por mes sobre
    ``occurred_at`` y con RLS forzada (ver migración 0068)."""

    __tablename__ = "usage_records"

    # La clave primaria incluye la clave de partición porque Postgres lo
    # exige en cualquier índice único de una tabla particionada — mismo
    # trato que ``messages`` (0063).
    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        primary_key=True,
        nullable=False,
    )

    # Sin ``index=True``: el índice compuesto (tenant_id, meter,
    # occurred_at) de la migración ya sirve el prefijo por tenant, y un
    # segundo índice solo de tenant_id sería peso muerto en la tabla de
    # mayor escritura de la plataforma.
    tenant_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False)

    # El consumo sobrevive a la baja de un partner (hay que poder facturar
    # el mes en el que se fue), de ahí SET NULL y no CASCADE.
    partner_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("partners.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Momento de INGESTA, distinto de ``occurred_at``. El metering es
    # asíncrono (WP-17/18): sin esta columna no se puede distinguir un
    # evento que llegó tarde de uno que ocurrió tarde, ni medir el retraso
    # del consumidor.
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )

    meter: Mapped[str] = mapped_column(Text, nullable=False)
    quantity: Mapped[decimal.Decimal] = mapped_column(Numeric(20, 6), nullable=False)
    # NULL = contado pero todavía sin precio (migración 0071). El emisor
    # solo cuenta cantidades; el precio lo pone el consumidor desde
    # ``model_profiles`` (WP-19), que aún no existe. NULL lo dice; un 0
    # sería indistinguible de algo que de verdad no cuesta nada.
    cost_usd: Mapped[decimal.Decimal | None] = mapped_column(Numeric(14, 8), nullable=True)
    billable_qty: Mapped[decimal.Decimal] = mapped_column(Numeric(20, 6), nullable=False)

    provider: Mapped[str | None] = mapped_column(Text, nullable=True)
    model: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Referencias SIN clave foránea a propósito: el consumo es un hecho
    # contable y debe sobrevivir al borrado de la conversación o de la
    # versión de agente que lo originó (incluido el borrado GDPR).
    agent_config_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    conversation_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)
    workflow_run_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), nullable=True)

    # Único junto a occurred_at. El consumidor de WP-18 inserta con
    # ON CONFLICT DO NOTHING: reprocesar el stream no duplica facturación.
    idempotency_key: Mapped[str] = mapped_column(Text, nullable=False)

    # Quién originó el gasto (migración 0079). ``channel`` es tráfico del
    # cliente y es lo facturable; ``qa`` es un operador probando el agente
    # en el Playground — gasta tokens de verdad y NO lo paga el cliente.
    # Sin esta columna las pruebas internas inflaban el coste del tenant en
    # el panel de margen, y castigaban más al cliente mejor atendido.
    source: Mapped[str] = mapped_column(
        Text,
        nullable=False,
        server_default=text("'channel'"),
    )


# Medidores conocidos. Es una lista, no un enum de Postgres, porque añadir
# un medidor no debe exigir migración — pero el emisor (WP-17) y el
# consumidor (WP-18) validan contra ella para que un typo no cree una
# categoría de facturación fantasma.
USAGE_METERS: frozenset[str] = frozenset(
    {
        "llm.input_tokens",
        "llm.output_tokens",
        "llm.cache_read",
        "llm.cache_write",
        "voice.minutes",
        "channel.message",
        "workflow.step",
        "tool.call",
        "storage.gb_month",
    }
)
