"""Presupuestos por tenant y por partner (WP-20, arrastre de Fase 2).

WP-20 dejó el corte construido y probado, pero la tabla que lo gobierna
solo se podía tocar por SQL. Es el mismo problema que tenía
``tenant_model_bindings`` antes de WP-19, y aquí es peor: lo que se edita
a ciegas no es qué modelo usa un cliente, es a partir de qué cifra su
agente deja de abrir turnos.

Tres validaciones que existen porque el fallo contrario es SILENCIOSO —
la política se guarda, el operador cree que hay un tope puesto, y no lo
hay:

- **El ``scope_id`` tiene que existir.** Un UUID mal copiado crea una
  política que jamás se evalúa, porque nadie consulta ese ámbito.
- **El ``meter`` tiene que ser uno de los que llevan contador.** El
  consumidor de metering solo alimenta ``cost_usd``; una política sobre
  cualquier otro medidor lee un contador que siempre vale cero y nunca
  dispara. La columna es texto libre en la base a propósito (habrá más
  medidores), pero aceptar hoy uno sin contador sería vender un tope que
  no corta.
- **El blando no puede superar al duro.** La base ya lo comprueba, pero
  un ``CheckViolation`` sale como 500 y el operador no sabe qué corregir.

Lo que aquí NO hay, y es deliberado:

- **No hay invalidación de caché.** ``budget.load_policies`` cachea 60 s
  en el proceso del worker; una edición surte efecto en el siguiente
  minuto. Publicar en un canal que nadie escucha daría una sensación de
  inmediatez falsa, y 60 s de retraso en un umbral de presupuesto no
  cambia ninguna decisión.
- **La fila de auditoría va a nivel de plataforma** (``tenant_id`` NULL),
  igual que la creación de un canal Auphere: ``budget_policies`` no es
  dato de un tenant — puede apuntar a un partner — y la policy de
  ``audit_log`` solo admite NULL desde una sesión sin ámbito.
"""

from __future__ import annotations

import uuid
from typing import Literal

import sqlalchemy as sa
import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field, model_validator
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.deps import get_db_session
from nexus_api.core.security import require_admin_token
from nexus_api.db.models import AuditLog

log = structlog.get_logger(__name__)

router = APIRouter()

# Medidores con contador vivo. Hoy solo el agregado en dólares: el
# consumidor de metering llama a ``add_spend`` únicamente con el coste
# total del lote. Ampliar esto exige ampliar antes el consumidor, no al
# revés.
BUDGETED_METERS = ("cost_usd",)

# Tabla por ámbito para comprobar que el ``scope_id`` apunta a algo real.
_SCOPE_TABLES = {"tenant": "tenants", "partner": "partners"}


class BudgetPolicyIn(BaseModel):
    scope: Literal["tenant", "partner"]
    scope_id: uuid.UUID
    meter: str = "cost_usd"
    period: Literal["day", "month"]
    soft_limit: float = Field(ge=0)
    hard_limit: float = Field(ge=0)
    soft_action: Literal["downgrade", "grader_off", "both"] = "downgrade"
    active: bool = True

    @model_validator(mode="after")
    def _check(self) -> BudgetPolicyIn:
        if self.meter not in BUDGETED_METERS:
            raise ValueError(
                f"medidor sin contador: {self.meter!r}. "
                f"Una política sobre él nunca dispararía. Válidos: "
                f"{', '.join(BUDGETED_METERS)}"
            )
        if self.soft_limit > self.hard_limit:
            raise ValueError(
                "soft_limit no puede superar a hard_limit: la degradación "
                "quedaría inalcanzable y se cortaría en seco"
            )
        return self


class BudgetPolicyOut(BaseModel):
    id: uuid.UUID
    scope: str
    scope_id: uuid.UUID
    meter: str
    period: str
    soft_limit: float
    hard_limit: float
    soft_action: str
    active: bool


_SELECT = """
    SELECT id, scope, scope_id, meter, period,
           soft_limit, hard_limit, soft_action, active
      FROM budget_policies
"""


@router.get(
    "/budget-policies",
    response_model=list[BudgetPolicyOut],
    dependencies=[Depends(require_admin_token)],
)
async def list_budget_policies(
    scope: Literal["tenant", "partner"] | None = None,
    scope_id: uuid.UUID | None = None,
    session: AsyncSession = Depends(get_db_session),
) -> list[BudgetPolicyOut]:
    """Configuración de plataforma: sin ámbito de tenant, como el catálogo
    de modelos. Devuelve también las inactivas — una política apagada es
    justo lo que un operador necesita ver cuando se pregunta por qué no
    cortó nada."""
    sql = _SELECT
    params: dict[str, object] = {}
    clauses = []
    if scope is not None:
        clauses.append("scope = :scope")
        params["scope"] = scope
    if scope_id is not None:
        clauses.append("scope_id = :scope_id")
        params["scope_id"] = str(scope_id)
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY scope, scope_id, period"

    rows = (await session.execute(sa.text(sql), params)).mappings().all()
    return [BudgetPolicyOut.model_validate(dict(r)) for r in rows]


@router.put("/budget-policies", response_model=BudgetPolicyOut)
async def upsert_budget_policy(
    payload: BudgetPolicyIn,
    session: AsyncSession = Depends(get_db_session),
    actor: str = Depends(require_admin_token),
) -> BudgetPolicyOut:
    """Alta o edición por la clave natural ``(scope, scope_id, meter,
    period)``. Es un PUT y no un POST porque esa cuádrupla ya es única en
    la base: un POST invitaría a crear duplicados que la base rechazaría
    con un 500."""
    table = _SCOPE_TABLES[payload.scope]
    exists = await session.scalar(
        sa.text(f"SELECT 1 FROM {table} WHERE id = :id"),
        {"id": str(payload.scope_id)},
    )
    if not exists:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"no existe ningún {payload.scope} con id {payload.scope_id}; "
                "la política no se evaluaría nunca"
            ),
        )

    row = (
        (
            await session.execute(
                sa.text(
                    """
                    INSERT INTO budget_policies
                        (scope, scope_id, meter, period,
                         soft_limit, hard_limit, soft_action, active)
                    VALUES (:scope, :scope_id, :meter, :period,
                            :soft_limit, :hard_limit, :soft_action, :active)
                    ON CONFLICT (scope, scope_id, meter, period) DO UPDATE
                       SET soft_limit = EXCLUDED.soft_limit,
                           hard_limit = EXCLUDED.hard_limit,
                           soft_action = EXCLUDED.soft_action,
                           active = EXCLUDED.active,
                           updated_at = now()
                    RETURNING id, scope, scope_id, meter, period,
                              soft_limit, hard_limit, soft_action, active
                    """
                ),
                payload.model_dump(mode="json"),
            )
        )
        .mappings()
        .one()
    )

    session.add(
        AuditLog(
            tenant_id=None,
            actor=f"admin:{actor[:8]}",
            action="budget_policy.upsert",
            target=f"{payload.scope}:{payload.scope_id}",
            before_json=None,
            after_json=payload.model_dump(mode="json"),
        )
    )
    await session.commit()
    log.warning(
        "budget_policy.upsert",
        scope=payload.scope,
        scope_id=str(payload.scope_id),
        period=payload.period,
        soft_limit=payload.soft_limit,
        hard_limit=payload.hard_limit,
        active=payload.active,
        actor=actor[:8],
    )
    return BudgetPolicyOut.model_validate(dict(row))


@router.delete(
    "/budget-policies/{policy_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_budget_policy(
    policy_id: uuid.UUID,
    session: AsyncSession = Depends(get_db_session),
    actor: str = Depends(require_admin_token),
) -> None:
    """Quitar la política deja al ámbito SIN tope, no con el tope por
    defecto: sin política no se corta (WP-20). Para pausar un tope sin
    perder sus cifras está ``active=false``."""
    row = (
        (
            await session.execute(
                sa.text(_SELECT + " WHERE id = :id"),
                {"id": str(policy_id)},
            )
        )
        .mappings()
        .first()
    )
    if row is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"política {policy_id} no encontrada",
        )

    await session.execute(
        sa.text("DELETE FROM budget_policies WHERE id = :id"),
        {"id": str(policy_id)},
    )
    session.add(
        AuditLog(
            tenant_id=None,
            actor=f"admin:{actor[:8]}",
            action="budget_policy.delete",
            target=f"{row['scope']}:{row['scope_id']}",
            before_json={k: str(v) for k, v in dict(row).items()},
            after_json=None,
        )
    )
    await session.commit()
    log.warning(
        "budget_policy.delete",
        scope=row["scope"],
        scope_id=str(row["scope_id"]),
        actor=actor[:8],
    )
