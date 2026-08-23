"""Catálogo de modelos y elección por tenant (WP-19).

Sin estos endpoints, ``tenant_model_bindings`` solo se puede tocar por
SQL — y una tabla que solo se edita por SQL en producción acaba
divergiendo de lo que cree el equipo. Aquí vive el mecanismo real:
cambiar el modelo de un cliente es un PUT y surte efecto en el siguiente
turno, sin redeploy.

Dos detalles que no son obvios:

- **Se reutiliza el canal de promote.** El binding viaja dentro del
  ``AgentBundle`` (comparte caché y ciclo de vida con el agent_config),
  así que invalidarlo es exactamente lo mismo que promover una versión.
  Un segundo canal solo añadiría una forma más de olvidarse de avisar.
- **La ficha de tenant necesita el catálogo entero, no solo lo elegido.**
  De ahí que el listado devuelva también los roles SIN binding, con el
  modelo global que se está usando: un selector que solo muestra lo
  configurado deja al operador sin saber qué pasa en los demás roles.
"""

from __future__ import annotations

import json
import uuid

import sqlalchemy as sa
import structlog
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from redis.asyncio import Redis
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.admin.agent_configs import PROMOTE_CHANNEL
from nexus_api.api.deps import get_db_session, scoped_session_from_path
from nexus_api.core.redis_client import get_redis
from nexus_api.core.security import require_admin_token
from nexus_api.db.models import MODEL_ROLES

log = structlog.get_logger(__name__)

router = APIRouter()


class ModelProfileOut(BaseModel):
    id: uuid.UUID
    provider: str
    model_id: str
    display_name: str
    price_input_per_mtok: float | None = None
    price_output_per_mtok: float | None = None
    price_cache_read_per_mtok: float | None = None
    price_cache_write_per_mtok: float | None = None
    price_per_minute: float | None = None
    max_context: int | None = None
    cache_min_tokens: int | None = None
    supports_tools: bool
    supports_vision: bool
    status: str


class ModelBindingOut(BaseModel):
    role: str
    model_id: str | None = None
    display_name: str | None = None
    fallback_chain: list[str] = Field(default_factory=list)
    max_cost_per_turn_usd: float | None = None
    # False = este rol no tiene fila y corre con la configuración global.
    # Se expone para que el panel distinga "elegido" de "heredado" en vez
    # de mostrar un hueco.
    is_bound: bool = False


class ModelBindingIn(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_id: str
    fallback_chain: list[str] = Field(default_factory=list)
    max_cost_per_turn_usd: float | None = None


@router.get(
    "/model-profiles",
    response_model=list[ModelProfileOut],
    dependencies=[Depends(require_admin_token)],
)
async def list_model_profiles(
    include_deprecated: bool = False,
    session: AsyncSession = Depends(get_db_session),
) -> list[ModelProfileOut]:
    """Catálogo de plataforma. Sin ámbito de tenant: es igual para todos."""
    sql = """
        SELECT id, provider, model_id, display_name,
               price_input_per_mtok, price_output_per_mtok,
               price_cache_read_per_mtok, price_cache_write_per_mtok,
               price_per_minute, max_context, cache_min_tokens,
               supports_tools, supports_vision, status
          FROM model_profiles
    """
    if not include_deprecated:
        sql += " WHERE status = 'active'"
    sql += " ORDER BY provider, model_id"

    rows = (await session.execute(sa.text(sql))).mappings().all()
    return [ModelProfileOut.model_validate(dict(r)) for r in rows]


@router.get(
    "/tenants/{tenant_id}/model-bindings",
    response_model=list[ModelBindingOut],
)
async def list_bindings(
    tenant_id: uuid.UUID,
    session: AsyncSession = Depends(scoped_session_from_path),
    _: str = Depends(require_admin_token),
) -> list[ModelBindingOut]:
    """Un elemento por rol conocido, tenga fila o no."""
    rows = (
        (
            await session.execute(
                sa.text(
                    """
                    SELECT b.role, p.model_id, p.display_name,
                           b.fallback_chain, b.max_cost_per_turn_usd
                      FROM tenant_model_bindings b
                      JOIN model_profiles p ON p.id = b.model_profile_id
                    """
                )
            )
        )
        .mappings()
        .all()
    )
    bound = {r["role"]: r for r in rows}

    out: list[ModelBindingOut] = []
    for role in sorted(MODEL_ROLES):
        row = bound.get(role)
        if row is None:
            out.append(ModelBindingOut(role=role, is_bound=False))
            continue
        out.append(
            ModelBindingOut(
                role=role,
                model_id=row["model_id"],
                display_name=row["display_name"],
                fallback_chain=[str(m) for m in (row["fallback_chain"] or [])],
                max_cost_per_turn_usd=(
                    float(row["max_cost_per_turn_usd"])
                    if row["max_cost_per_turn_usd"] is not None
                    else None
                ),
                is_bound=True,
            )
        )
    return out


@router.put(
    "/tenants/{tenant_id}/model-bindings/{role}",
    response_model=ModelBindingOut,
)
async def upsert_binding(
    tenant_id: uuid.UUID,
    role: str,
    payload: ModelBindingIn,
    session: AsyncSession = Depends(scoped_session_from_path),
    redis: Redis = Depends(get_redis),
    _: str = Depends(require_admin_token),
) -> ModelBindingOut:
    if role not in MODEL_ROLES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"rol desconocido: {role}",
        )

    profile = (
        (
            await session.execute(
                sa.text(
                    "SELECT id, model_id, display_name FROM model_profiles "
                    "WHERE model_id = :m AND status = 'active'"
                ),
                {"m": payload.model_id},
            )
        )
        .mappings()
        .first()
    )
    if profile is None:
        # Fallar aquí y no al resolver: un binding a un modelo que no
        # existe no daría error hasta el primer turno del cliente.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"modelo no está en el catálogo activo: {payload.model_id}",
        )

    await session.execute(
        sa.text(
            """
            INSERT INTO tenant_model_bindings
                (tenant_id, role, model_profile_id, fallback_chain, max_cost_per_turn_usd)
            VALUES (:t, :r, :p, CAST(:fc AS jsonb), :mc)
            ON CONFLICT (tenant_id, role) DO UPDATE
               SET model_profile_id = EXCLUDED.model_profile_id,
                   fallback_chain = EXCLUDED.fallback_chain,
                   max_cost_per_turn_usd = EXCLUDED.max_cost_per_turn_usd,
                   updated_at = now()
            """
        ),
        {
            "t": str(tenant_id),
            "r": role,
            "p": profile["id"],
            "fc": json.dumps(payload.fallback_chain),
            "mc": payload.max_cost_per_turn_usd,
        },
    )
    await session.commit()
    await _invalidate(redis, tenant_id)

    return ModelBindingOut(
        role=role,
        model_id=profile["model_id"],
        display_name=profile["display_name"],
        fallback_chain=payload.fallback_chain,
        max_cost_per_turn_usd=payload.max_cost_per_turn_usd,
        is_bound=True,
    )


@router.delete(
    "/tenants/{tenant_id}/model-bindings/{role}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_binding(
    tenant_id: uuid.UUID,
    role: str,
    session: AsyncSession = Depends(scoped_session_from_path),
    redis: Redis = Depends(get_redis),
    _: str = Depends(require_admin_token),
) -> None:
    """Devuelve el rol a la configuración global."""
    await session.execute(
        # Sin ``WHERE tenant_id``: la sesión está scopeada y la RLS de la
        # tabla es quien filtra, igual que en el resolver del runtime.
        sa.text("DELETE FROM tenant_model_bindings WHERE role = :r"),
        {"r": role},
    )
    await session.commit()
    await _invalidate(redis, tenant_id)


async def _invalidate(redis: Redis, tenant_id: uuid.UUID) -> None:
    """Mismo canal que el promote: el binding viaja en el ``AgentBundle``.

    Best-effort — si la publicación falla, el worker sigue con el binding
    anterior hasta el siguiente fallo de caché. Peor es tumbar el PUT y
    dejar la base y la caché en desacuerdo sin que nadie lo sepa.
    """
    try:
        await redis.publish(PROMOTE_CHANNEL, str(tenant_id))
    except Exception as exc:
        log.warning("model_binding.invalidate_failed", tenant_id=str(tenant_id), error=str(exc))
