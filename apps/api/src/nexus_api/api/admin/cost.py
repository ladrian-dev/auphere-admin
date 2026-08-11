"""Coste por tenant, mes y versión de agente (WP-22, mitad backend).

Es la mitad que faltaba del panel de margen: el criterio de salida de la
Fase 2 pide poder decir **con un dato** cuánto cuesta cada cliente. El
ingreso llega con Stripe; el coste está aquí, y sale de las mismas filas
de ``usage_records`` que valoró WP-19.

**Lo importante de este endpoint no es la suma, es lo que la suma no
incluye.** ``SUM(cost_usd)`` ignora los NULL en silencio, y NULL es
exactamente lo que WP-19 decidió escribir cuando un consumo se mide pero
no se puede valorar (modelo fuera de catálogo, tarifa sin cargar). Un mes
con la mitad de las filas sin precio devolvería una cifra pequeña,
creíble y falsa. Por eso cada fila lleva ``unpriced_records`` y la
respuesta lleva ``complete``: un panel que muestre el total sin mirar ese
campo está mintiendo, y ahora se le nota.

Va por tenant y no por plataforma entera porque ``usage_records`` tiene
RLS ENABLE + FORCE: una consulta agregada sobre todos los tenants no
devolvería nada desde ``nexus_app``. El roll-up entre clientes necesita
antes la misma decisión que se tomó para ``invoices`` en la 0073 (quién
lee por encima del tenant y con qué rol), y esa decisión no se toma de
paso en un endpoint.
"""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

import sqlalchemy as sa
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.deps import scoped_session_from_path
from nexus_api.core.security import require_admin_token

router = APIRouter()

# Tope de ventana. 24 meses cubre cualquier revisión anual sin invitar a
# barrer la tabla entera de un cliente antiguo desde el panel.
_MAX_MONTHS = 24


class CostBucket(BaseModel):
    """Un mes de un ``agent_config_id``."""

    month: str  # YYYY-MM
    agent_config_id: uuid.UUID | None = None
    agent_config_version: int | None = None
    cost_usd: float
    records: int
    # Filas medidas que NO se pudieron valorar. Si esto es > 0, ``cost_usd``
    # es un suelo, no el coste.
    unpriced_records: int


class CostReportOut(BaseModel):
    tenant_id: uuid.UUID
    since: date
    buckets: list[CostBucket] = Field(default_factory=list)
    total_cost_usd: float
    total_records: int
    total_unpriced_records: int
    # Campo, no propiedad: tiene que viajar en el JSON. False significa
    # "el total de arriba es un suelo", y es lo que el panel debe mirar
    # antes de pintar un margen.
    complete: bool


_SQL = sa.text(
    """
    SELECT to_char(date_trunc('month', u.occurred_at), 'YYYY-MM') AS month,
           u.agent_config_id,
           MAX(a.version)                             AS agent_config_version,
           COALESCE(SUM(u.cost_usd), 0)               AS cost_usd,
           COUNT(*)                                   AS records,
           COUNT(*) FILTER (WHERE u.cost_usd IS NULL) AS unpriced_records
      FROM usage_records u
      LEFT JOIN agent_configs a ON a.id = u.agent_config_id
     WHERE u.occurred_at >= :since
     GROUP BY 1, 2
     ORDER BY 1 DESC, 3 DESC NULLS LAST
    """
)


def _first_of_month_n_back(months: int, *, today: date | None = None) -> date:
    """Inicio de la ventana: el día 1 del mes de hace ``months - 1`` meses,
    de modo que ``months=1`` sea el mes en curso."""
    ref = today or date.today()
    total = (ref.year * 12 + ref.month - 1) - (months - 1)
    return date(total // 12, total % 12 + 1, 1)


@router.get("/tenants/{tenant_id}/cost", response_model=CostReportOut)
async def tenant_cost(
    tenant_id: uuid.UUID,
    months: int = Query(6, ge=1, le=_MAX_MONTHS),
    session: AsyncSession = Depends(scoped_session_from_path),
    _: str = Depends(require_admin_token),
) -> CostReportOut:
    """Coste medido de un cliente, por mes y por versión de agente.

    Sin ``WHERE tenant_id``: la sesión está scopeada y la RLS de
    ``usage_records`` es quien filtra — el mismo contrato que el resto del
    runtime. El filtro por ``occurred_at`` no es solo un rango: es lo que
    permite a Postgres podar las particiones mensuales (0064).
    """
    since = _first_of_month_n_back(months)
    rows = (await session.execute(_SQL, {"since": since})).mappings().all()

    # Los totales se suman en Decimal y se convierten UNA vez. Sumar floats
    # de ocho decimales arrastra error binario a una cifra que después se
    # resta de un ingreso para llamarlo margen.
    total_cost = Decimal(0)
    buckets: list[CostBucket] = []
    for r in rows:
        total_cost += r["cost_usd"]
        buckets.append(
            CostBucket(
                month=r["month"],
                agent_config_id=r["agent_config_id"],
                agent_config_version=r["agent_config_version"],
                cost_usd=float(r["cost_usd"]),
                records=int(r["records"]),
                unpriced_records=int(r["unpriced_records"]),
            )
        )
    total_unpriced = sum(b.unpriced_records for b in buckets)
    return CostReportOut(
        tenant_id=tenant_id,
        since=since,
        buckets=buckets,
        total_cost_usd=float(total_cost),
        total_records=sum(b.records for b in buckets),
        total_unpriced_records=total_unpriced,
        complete=total_unpriced == 0,
    )
