"""Aislamiento de ``tenant_model_bindings`` (WP-19).

Qué se protege exactamente: **en qué modelo corre cada cliente**. No es un
dato cosmético — dice cuánto le cuesta a Auphere atender a ese cliente y,
por tanto, con qué margen se le está facturando. Una fuga aquí filtra
economía de un cliente a otro, no una preferencia técnica.

Y hay una segunda cosa, más sutil, que se comprueba abajo: el runtime lee
los bindings SIN ``WHERE tenant_id`` a propósito (ver
``runtime/model_resolver.py``). Eso solo es seguro si la RLS realmente
filtra. Si alguien la desactivara, el agente de un cliente empezaría a
resolver el modelo de otro y ningún test de negocio lo notaría — el turno
seguiría respondiendo, solo que con el modelo equivocado y facturando
contra el catálogo equivocado. Este archivo es lo único que lo caza.

Bloqueante como el resto de la suite.
"""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker

pytestmark = pytest.mark.asyncio


async def _as_app_role(session, tenant_id: uuid.UUID | None) -> None:
    await session.execute(
        sa.text("SELECT set_config('app.tenant_id', :t, false)"),
        {"t": "" if tenant_id is None else str(tenant_id)},
    )
    await session.execute(sa.text("SET ROLE nexus_app"))


async def _profile_id(session, model_id: str) -> uuid.UUID:
    pid = await session.scalar(
        sa.text("SELECT id FROM model_profiles WHERE model_id = :m"), {"m": model_id}
    )
    assert pid is not None, f"{model_id} no está en el catálogo sembrado por 0072"
    return pid


async def _seed_tenant(session, tenant_id: uuid.UUID) -> None:
    await session.execute(
        sa.text(
            "INSERT INTO tenants (id, name, slug, plan) "
            "VALUES (:id, :n, :s, 'pro') ON CONFLICT DO NOTHING"
        ),
        {"id": str(tenant_id), "n": "Binding", "s": f"binding-{tenant_id.hex[:8]}"},
    )


async def _bind(session, tenant_id: uuid.UUID, role: str, model_id: str) -> None:
    await session.execute(
        sa.text(
            "INSERT INTO tenant_model_bindings (tenant_id, role, model_profile_id) "
            "VALUES (:t, :r, :p)"
        ),
        {"t": str(tenant_id), "r": role, "p": await _profile_id(session, model_id)},
    )


async def test_a_tenant_never_sees_another_tenants_binding(db_session) -> None:
    a, b = uuid.uuid4(), uuid.uuid4()
    sm = get_sessionmaker()

    async with sm() as session:
        await _seed_tenant(session, a)
        await _seed_tenant(session, b)
        await session.execute(
            sa.text("SELECT set_config('app.tenant_id', :t, false)"), {"t": str(a)}
        )
        await _bind(session, a, "respond", "anthropic/claude-sonnet-4-6")
        await session.execute(
            sa.text("SELECT set_config('app.tenant_id', :t, false)"), {"t": str(b)}
        )
        await _bind(session, b, "respond", "anthropic/claude-haiku-4-5")
        await session.commit()

    async with sm() as session:
        await _as_app_role(session, a)
        # Sin WHERE por tenant: es exactamente la consulta del resolver.
        rows = (await session.execute(sa.text("SELECT tenant_id FROM tenant_model_bindings"))).all()
        assert [r[0] for r in rows] == [a], "un tenant vio la elección de modelo de otro"


async def test_unscoped_session_sees_no_bindings(db_session) -> None:
    """Sin GUC, cero filas y no un error: el resolver cae a la config
    global en vez de tumbar el turno."""
    a = uuid.uuid4()
    sm = get_sessionmaker()

    async with sm() as session:
        await _seed_tenant(session, a)
        await session.execute(
            sa.text("SELECT set_config('app.tenant_id', :t, false)"), {"t": str(a)}
        )
        await _bind(session, a, "respond", "anthropic/claude-sonnet-4-6")
        await session.commit()

    async with sm() as session:
        await _as_app_role(session, None)
        visible = await session.scalar(sa.text("SELECT count(*) FROM tenant_model_bindings"))
        assert visible == 0


async def test_binding_another_tenant_is_rejected(db_session) -> None:
    """Elegirle el modelo a otro cliente — y por tanto su coste — lo
    bloquea el WITH CHECK implícito de la policy."""
    a, b = uuid.uuid4(), uuid.uuid4()
    sm = get_sessionmaker()

    async with sm() as session:
        await _seed_tenant(session, a)
        await _seed_tenant(session, b)
        await session.commit()

    async with sm() as session:
        await _as_app_role(session, a)
        with pytest.raises(Exception, match=r"row-level security|violates"):
            await _bind(session, b, "respond", "anthropic/claude-haiku-4-5")


async def test_the_resolver_only_returns_the_active_tenants_bindings(db_session) -> None:
    """El camino REAL: ``load_bindings`` dentro de una sesión scopeada.

    Los tres tests anteriores fijan la RLS; éste fija que el runtime la
    use — que no haya un ``WHERE`` de más ni de menos entre la tabla y el
    modelo que acaba invocándose.
    """
    from nexus_worker.runtime.model_resolver import load_bindings

    a, b = uuid.uuid4(), uuid.uuid4()
    sm = get_sessionmaker()

    async with sm() as session:
        await _seed_tenant(session, a)
        await _seed_tenant(session, b)
        await session.execute(
            sa.text("SELECT set_config('app.tenant_id', :t, false)"), {"t": str(a)}
        )
        await _bind(session, a, "respond", "anthropic/claude-sonnet-4-6")
        await session.execute(
            sa.text("SELECT set_config('app.tenant_id', :t, false)"), {"t": str(b)}
        )
        await _bind(session, b, "respond", "anthropic/claude-haiku-4-5")
        await _bind(session, b, "classify", "anthropic/claude-haiku-4-5")
        await session.commit()

    async with sm() as session, tenant_scoped_session(session, a):
        bindings = await load_bindings(session, a)
    assert set(bindings) == {"respond"}
    assert bindings["respond"].model_id == "anthropic/claude-sonnet-4-6"

    async with sm() as session, tenant_scoped_session(session, b):
        bindings = await load_bindings(session, b)
    assert set(bindings) == {"respond", "classify"}
    assert bindings["respond"].model_id == "anthropic/claude-haiku-4-5"


# ── spec 016 (garantía 1): el modelo de un cliente no cruza partners ──────────


async def _binding_of(db_session, tenant_id: uuid.UUID) -> str | None:
    row = (
        await db_session.execute(
            sa.text(
                "SELECT p.model_id FROM tenant_model_bindings b "
                "JOIN model_profiles p ON p.id = b.model_profile_id "
                "WHERE b.tenant_id = :t AND b.role = 'respond'"
            ),
            {"t": str(tenant_id)},
        )
    ).first()
    return None if row is None else str(row[0])


async def test_console_put_model_never_touches_another_partners_binding(
    client, console_world, db_session
) -> None:
    a, b = console_world["a"], console_world["b"]
    sol, luna = "openai/gpt-5.6-sol", "openai/gpt-5.6-luna"
    ok_b = await client.put(
        "/console/clients/{}/model".format(b["ref"]),
        headers=b["headers"](),
        json={"model_id": luna},
    )
    assert ok_b.status_code == 200, ok_b.text
    # A escribe el suyo; con el ref de B es el 404 opaco y B no cambia.
    ok_a = await client.put(
        "/console/clients/{}/model".format(a["ref"]), headers=a["headers"](), json={"model_id": sol}
    )
    assert ok_a.status_code == 200, ok_a.text
    foreign = await client.put(
        "/console/clients/{}/model".format(b["ref"]), headers=a["headers"](), json={"model_id": sol}
    )
    assert foreign.status_code == 404
    assert await _binding_of(db_session, a["tenant_id"]) == sol
    assert await _binding_of(db_session, b["tenant_id"]) == luna


async def test_reconciling_one_partners_allowlist_leaves_the_other_partners_bindings(
    client, console_world, db_session, admin_headers
) -> None:
    from nexus_api.db.models import ConsoleNotification

    a, b = console_world["a"], console_world["b"]
    sol = "openai/gpt-5.6-sol"
    for w in (a, b):
        ok = await client.put(
            "/console/clients/{}/model".format(w["ref"]),
            headers=w["headers"](),
            json={"model_id": sol},
        )
        assert ok.status_code == 200, ok.text
    shrink = await client.put(
        f"/admin/partners/{a['partner_id']}/models",
        headers=admin_headers,
        json={"model_ids": ["openai/gpt-5.6-luna"]},
    )
    assert shrink.status_code == 200, shrink.text
    assert await _binding_of(db_session, a["tenant_id"]) is None
    assert await _binding_of(db_session, b["tenant_id"]) == sol
    assert (
        await db_session.scalar(
            sa.select(sa.func.count())
            .select_from(ConsoleNotification)
            .where(ConsoleNotification.partner_id == b["partner_id"])
        )
    ) == 0
