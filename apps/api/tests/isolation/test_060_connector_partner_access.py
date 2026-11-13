"""Garantía 2 — un conector no disponible para el partner no llega a su cliente
(spec 060, T010 a T013).

La disponibilidad por partner es una capa más sobre las herramientas de un
agente, y **solo puede quitar**. Se prueba por los caminos reales:

1. **El turno** (`_load_tool_policy` con la sesión del worker): un cliente cuyo
   partner perdió el conector no ve ni ejecuta ninguna de sus herramientas,
   tampoco por la rama que hoy deja pasar sin mirar (fuera de la consola v2 y sin
   activaciones). Se barre **todo** conector del catálogo, no uno de muestra.
2. **La consola**: el conector no aparece en ningún listado del cliente, y su
   detalle responde igual que uno que no existe.
3. **Las altas**: ningún camino crea ni activa una conexión utilizable.
4. **Los cargadores** de credenciales, que usan también los procesos programados.

Las tablas de la regla no tienen RLS (research D3): si la tuvieran por
``app.partner_id``, el turno no vería ninguna fila y, como «sin fila = habilitado»,
todo quedaría abierto. Por eso estas pruebas pasan por la sesión del cliente.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

import pytest
import sqlalchemy as sa
from nexus_worker.runtime.pipeline import _load_tool_policy
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import (
    AgentConnectorActivation,
    Connector,
    ConnectorAccessDefault,
    ConnectorPartnerAccess,
    Partner,
    Tenant,
    TenantConnector,
    ToolCatalog,
)
from nexus_api.services import activations
from nexus_api.services.connectors import availability
from nexus_api.services.connectors.availability import ConnectorUnavailable

from ..integration.business._business_world import Biz, new_business
from ..integration.connectors._activation_world import (
    READ,
    SLUG,
    WRITE,
    agent_with_spec,
    connect,
    seed_integration,
)
from ..integration.connectors.conftest import fake_composio, seeded_catalog  # noqa: F401

pytestmark = [pytest.mark.isolation]  # asyncio_mode=auto


@pytest.fixture
async def two_partners(
    client: Any, db_session: AsyncSession, console_world: dict[str, Any]
) -> tuple[Biz, Biz]:
    """A, en la consola nueva y con el agente activado; B, fuera de ella y sin
    activaciones: la rama de `tool_policy` que hoy deja pasar sin mirar."""
    a = await new_business(client, db_session, console_world, name="Tienda A", label="a")
    b = await new_business(client, db_session, console_world, name="Tienda B", label="b")
    for biz in (a, b):
        tenant = await db_session.get(Tenant, biz.tenant_id)
        assert tenant is not None and tenant.partner_id == biz.partner_id, (
            "el partner del cliente es tenants.partner_id (research D4)"
        )
    partner_a = await db_session.get(Partner, a.partner_id)
    assert partner_a is not None
    partner_a.console_v2_enabled_at = datetime.now(UTC)
    await db_session.commit()
    return a, b


async def _decide(
    db_session: AsyncSession, slug: str, partner_id: uuid.UUID, *, enabled: bool
) -> None:
    await db_session.merge(
        ConnectorPartnerAccess(
            connector_slug=slug, partner_id=partner_id, enabled=enabled, reason="t", set_by="t"
        )
    )
    await db_session.commit()


async def _default(db_session: AsyncSession, slug: str, *, enabled: bool) -> None:
    await db_session.merge(
        ConnectorAccessDefault(connector_slug=slug, enabled=enabled, reason="t", updated_by="t")
    )
    await db_session.commit()


async def _agent_and_connection(
    db_session: AsyncSession, biz: Biz, connector: Connector, *, activate: bool
) -> uuid.UUID:
    agent_id = await agent_with_spec(db_session, biz, "Ventas")
    # El AgentSpec pide 20 caracteres de descripción al leer el borrador.
    from nexus_api.db.models import AgentConfig

    async with tenant_scoped_session(db_session, biz.tenant_id):
        cfg = (
            await db_session.scalars(sa.select(AgentConfig).where(AgentConfig.agent_id == agent_id))
        ).first()
        assert cfg is not None
        spec = dict(cfg.spec or {})
        spec["identity"] = {**spec["identity"], "description": "Vende por WhatsApp a sus clientes."}
        cfg.spec = spec
    await db_session.commit()
    install_id = await connect(db_session, biz, connector)
    if activate:
        async with tenant_scoped_session(db_session, biz.tenant_id):
            db_session.add(
                AgentConnectorActivation(
                    tenant_id=biz.tenant_id,
                    agent_id=agent_id,
                    connector_id=install_id,
                    permission="read_write",
                    settings={},
                )
            )
        await db_session.commit()
    return agent_id


# ── 1. el turno ─────────────────────────────────────────────────────────────


async def test_the_turn_never_offers_a_connector_its_partner_lost(
    db_session: AsyncSession, two_partners: tuple[Biz, Biz]
) -> None:
    """Requisitos 5.3 y 1.3, por el camino real del turno."""
    a, b = two_partners
    connector = await seed_integration(db_session)
    agent_a = await _agent_and_connection(db_session, a, connector, activate=True)
    agent_b = await _agent_and_connection(db_session, b, connector, activate=False)
    tools = (READ, WRITE)

    # Antes de restringir: los dos ven sus herramientas (B por la rama sin activaciones).
    for biz, agent in ((a, agent_a), (b, agent_b)):
        policy = await _load_tool_policy(biz.tenant_id, agent)
        assert not policy.closed
        assert set(activations.allowed_names(tools, policy)) == set(tools), biz.ref

    # Deshabilitado para B: B no ve nada, A sigue igual.
    await _decide(db_session, SLUG, b.partner_id, enabled=False)
    assert activations.allowed_names(tools, await _load_tool_policy(b.tenant_id, agent_b)) == ()
    assert set(
        activations.allowed_names(tools, await _load_tool_policy(a.tenant_id, agent_a))
    ) == set(tools)

    # Deshabilitado por defecto y habilitado solo para A: el mismo resultado.
    await db_session.execute(sa.delete(ConnectorPartnerAccess))
    await db_session.commit()
    await _default(db_session, SLUG, enabled=False)
    await _decide(db_session, SLUG, a.partner_id, enabled=True)
    assert activations.allowed_names(tools, await _load_tool_policy(b.tenant_id, agent_b)) == ()
    assert set(
        activations.allowed_names(tools, await _load_tool_policy(a.tenant_id, agent_a))
    ) == set(tools)

    # El cliente de B pasa a A: desde el turno siguiente la regla ya no le quita nada.
    # (A está en la consola nueva, donde además hace falta una activación por agente:
    # esa capa es otra y no se mide aquí.)
    tenant_b = await db_session.get(Tenant, b.tenant_id)
    assert tenant_b is not None
    tenant_b.partner_id = a.partner_id
    await db_session.commit()
    async with get_sessionmaker()() as s, tenant_scoped_session(s, b.tenant_id):
        assert await availability.unavailable_slugs_for_tenant(s, b.tenant_id) == frozenset()


async def test_every_catalogued_connector_is_withheld_when_unavailable(
    db_session: AsyncSession, two_partners: tuple[Biz, Biz]
) -> None:
    """Requisito 1.5, barrido: toda herramienta de todo conector del catálogo
    (seeds y Composio incluidos) queda fuera si su conector no está disponible,
    salvo canales y conectores de sistema."""
    from nexus_api.services.connectors.seed_loader import load_all_seeds
    from nexus_api.services.connectors.seed_runner import apply_seeds

    _a, b = two_partners
    await apply_seeds(db_session, load_all_seeds())
    await seed_integration(db_session)
    # Uno de Composio, para que el barrido no dependa de los seeds.
    from nexus_api.db.models import ToolStatus

    gmail = await db_session.scalar(sa.select(Connector).where(Connector.slug == "gmail_060"))
    if gmail is None:
        gmail = Connector(
            slug="gmail_060",
            display_name="Gmail",
            vendor="Google",
            category="email",
            auth_kind="oauth_composio",
            mcp_server_ref="composio:gmail",
            status="available",
        )
        db_session.add(gmail)
        await db_session.flush()
        db_session.add(
            ToolCatalog(
                name="GMAIL_060_SEND_EMAIL",
                description="x",
                mcp_server="composio:gmail",
                status=ToolStatus.ACTIVE,
                connector_id=gmail.id,
                read_only=False,
                destructive=False,
                default_mode="always",
            )
        )
    await db_session.commit()
    rows = (
        await db_session.execute(
            sa.select(ToolCatalog.name, Connector.slug, Connector.id).join(
                Connector, Connector.id == ToolCatalog.connector_id
            )
        )
    ).all()
    unmanaged = await availability.unmanaged_slugs(db_session)
    managed = {(name, slug, cid) for name, slug, cid in rows if slug not in unmanaged}
    slugs = {slug for _n, slug, _c in managed}
    # En la base de pruebas los seeds no traen herramientas enlazadas: el mínimo son
    # el conector propio y el de Composio que monta esta prueba.
    assert {SLUG, "gmail_060"} <= slugs, f"barrido roto: {sorted(slugs)}"
    await db_session.commit()

    agent_b = await agent_with_spec(db_session, b, "Ventas")
    async with tenant_scoped_session(db_session, b.tenant_id):
        for cid in {cid for _n, _s, cid in managed}:
            db_session.add(
                TenantConnector(
                    tenant_id=b.tenant_id,
                    connector_id=cid,
                    status="connected",
                    credentials_ref={},
                    connected_at=datetime.now(UTC),
                )
            )
    await db_session.commit()
    for slug in {slug for _n, slug, _c in managed}:
        await _default(db_session, slug, enabled=False)

    names = tuple(sorted({name for name, _s, _c in managed}))
    policy = await _load_tool_policy(b.tenant_id, agent_b)
    leaked = set(activations.allowed_names(names, policy))
    assert not leaked, sorted(leaked)


async def test_an_unreadable_rule_closes_the_turn(
    db_session: AsyncSession, two_partners: tuple[Biz, Biz], monkeypatch: pytest.MonkeyPatch
) -> None:
    """Requisito 5.8: nunca se interpreta como «todo disponible»."""
    a, _b = two_partners
    connector = await seed_integration(db_session)
    agent_a = await _agent_and_connection(db_session, a, connector, activate=True)

    async def unreadable(*_args: object, **_kwargs: object) -> frozenset[str]:
        raise RuntimeError("the rule cannot be read")

    monkeypatch.setattr(availability, "unavailable_slugs_for_tenant", unreadable)
    policy = await _load_tool_policy(a.tenant_id, agent_a)
    assert policy.closed, "falla cerrada"
    assert activations.allowed_names((READ, WRITE), policy) == ()


# ── 2. la consola ───────────────────────────────────────────────────────────


async def test_the_console_never_lists_a_connector_its_partner_lost(
    client: Any,
    db_session: AsyncSession,
    two_partners: tuple[Biz, Biz],
    seeded_catalog: None,  # noqa: F811
    fake_composio: Any,  # noqa: F811
) -> None:
    """Requisito 5.1: ni integraciones, ni las del agente, ni sus herramientas, ni
    capacidades, ni lo que el constructor ofrece. El detalle, como si no existiera."""
    from nexus_api.services.agent_spec.validator import load_context

    a, b = two_partners
    connector = await seed_integration(db_session)
    agent_b = await _agent_and_connection(db_session, b, connector, activate=False)
    await _decide(db_session, SLUG, b.partner_id, enabled=False)

    listing = await client.get(f"/console/clients/{b.ref}/connectors", headers=b.headers())
    assert listing.status_code == 200, listing.text
    assert SLUG not in {c["slug"] for c in listing.json()}

    base = f"/console/clients/{b.ref}/agents/{agent_b}"
    integrations = await client.get(f"{base}/integrations", headers=b.headers())
    assert integrations.status_code == 200, integrations.text
    assert SLUG not in {c["slug"] for c in integrations.json()}

    hidden = await client.get(f"{base}/integrations/{SLUG}/tools", headers=b.headers())
    unknown = await client.get(f"{base}/integrations/no_existe_060/tools", headers=b.headers())
    assert (hidden.status_code, hidden.json()) == (unknown.status_code, unknown.json())

    caps = await client.get(
        f"/console/clients/{b.ref}/capabilities?agent={agent_b}", headers=b.headers()
    )
    assert caps.status_code == 200, caps.text
    assert READ not in caps.text and WRITE not in caps.text

    async with tenant_scoped_session(db_session, b.tenant_id):
        ctx = await load_context(db_session, partner_id=b.partner_id, agent_id=agent_b)
    assert SLUG not in ctx.offered_connectors()

    # El control: A sí lo ve.
    listing_a = await client.get(f"/console/clients/{a.ref}/connectors", headers=a.headers())
    assert SLUG in {c["slug"] for c in listing_a.json()}


# ── 3. las altas ────────────────────────────────────────────────────────────


async def test_no_path_creates_or_activates_a_connection_its_partner_lost(
    client: Any,
    db_session: AsyncSession,
    two_partners: tuple[Biz, Biz],
    seeded_catalog: None,  # noqa: F811
    fake_composio: Any,  # noqa: F811
) -> None:
    """Requisito 5.2: consola (clave, `/connections` y activación), panel y
    servicio (el alta de clientes de la API de partners pasa por él)."""
    from nexus_api.services.connectors.service import bootstrap_api_key

    _a, b = two_partners
    connector = await seed_integration(db_session)
    agent_b = await agent_with_spec(db_session, b, "Ventas")
    await _decide(db_session, SLUG, b.partner_id, enabled=False)
    unknown_key = await client.post(
        f"/console/clients/{b.ref}/connectors/no_existe_060/api-key",
        json={"secrets": {"key": "x"}, "endpoint_meta": {}},
        headers=b.headers(),
    )
    hidden_key = await client.post(
        f"/console/clients/{b.ref}/connectors/{SLUG}/api-key",
        json={"secrets": {"key": "x"}, "endpoint_meta": {"store_url": "https://t.example"}},
        headers=b.headers(),
    )
    assert hidden_key.status_code == unknown_key.status_code == 404, hidden_key.text

    connection = await client.post(
        f"/console/clients/{b.ref}/connections",
        json={"integration": SLUG, "agent_id": str(agent_b)},
        headers=b.headers(),
    )
    assert connection.status_code == 404, connection.text

    with pytest.raises(ConnectorUnavailable):
        async with get_sessionmaker()() as s, tenant_scoped_session(s, b.tenant_id):
            tenant_b = await s.get(Tenant, b.tenant_id)
            assert tenant_b is not None
            await bootstrap_api_key(
                s,
                tenant=tenant_b,
                connector_slug=SLUG,
                secret_payload={"key": "x"},
                endpoint_meta={"store_url": "https://t.example"},
                actor="test",
            )

    # Una conexión que ya existía no se puede activar en un agente.
    await connect(db_session, b, connector)
    activation = await client.put(
        f"/console/clients/{b.ref}/agents/{agent_b}/activations/{SLUG}",
        json={"permission": "read"},
        headers=b.headers(),
    )
    assert activation.status_code == 404, activation.text
    async with get_sessionmaker()() as s, tenant_scoped_session(s, b.tenant_id):
        count = await s.scalar(sa.select(sa.func.count()).select_from(AgentConnectorActivation))
    assert count == 0


async def test_a_consent_completed_after_losing_access_is_not_usable(
    db_session: AsyncSession,
    two_partners: tuple[Biz, Biz],
    fake_composio: Any,  # noqa: F811
) -> None:
    """Requisito 5.2: el webhook de Composio que llega tarde no conecta nada."""
    from nexus_api.services.connectors.service import complete_consent_from_webhook

    _a, b = two_partners
    connector = await seed_integration(db_session)
    async with tenant_scoped_session(db_session, b.tenant_id):
        install = TenantConnector(
            tenant_id=b.tenant_id,
            connector_id=connector.id,
            status="pending",
            credentials_ref={"composio_connection_id": "ca_060"},
        )
        db_session.add(install)
        await db_session.flush()
        install_id = install.id
    await db_session.commit()
    await _decide(db_session, SLUG, b.partner_id, enabled=False)

    async with tenant_scoped_session(db_session, b.tenant_id):
        await complete_consent_from_webhook(
            db_session,
            composio_connection_id="ca_060",
            upstream_status="ACTIVE",
            granted_scopes=[],
            composio=fake_composio,
        )
    await db_session.commit()
    async with get_sessionmaker()() as s, tenant_scoped_session(s, b.tenant_id):
        status = await s.scalar(
            sa.select(TenantConnector.status).where(TenantConnector.id == install_id)
        )
    assert str(getattr(status, "value", status)) == "error"


# ── 4. los cargadores de credenciales (y los procesos programados) ──────────


async def test_each_credential_loader_says_not_configured_when_its_partner_lost_it(
    db_session: AsyncSession, two_partners: tuple[Biz, Biz]
) -> None:
    """Requisito 5.4, por los cargadores reales: cada uno lanza su «sin conexión»,
    que es lo que ``cobranza_reminder_cron`` y ``agent_sales_poll_cron`` saltan."""
    from nexus_mcp.servers.amigable_cobro.tools import (
        AmigableCobroNotConfigured,
        _load_amigable_client,
    )
    from nexus_mcp.servers.inventory.tools import (
        InventoryNotConfigured,
        _load_amigable_venta_client,
    )
    from nexus_mcp.servers.woocommerce.tools import (
        WooCommerceNotConfigured,
        _load_woocommerce_client,
    )

    from nexus_api.services.connectors.seed_loader import load_all_seeds
    from nexus_api.services.connectors.seed_runner import apply_seeds

    _a, b = two_partners
    await apply_seeds(db_session, load_all_seeds())
    await db_session.commit()
    loaders = (
        ("woocommerce", _load_woocommerce_client, WooCommerceNotConfigured),
        ("amigable_cobro", _load_amigable_client, AmigableCobroNotConfigured),
        ("amigable_venta", _load_amigable_venta_client, InventoryNotConfigured),
    )
    connectors = {
        c.slug: c
        for c in (
            await db_session.scalars(
                sa.select(Connector).where(Connector.slug.in_([s for s, _l, _e in loaders]))
            )
        ).all()
    }
    await db_session.commit()
    assert set(connectors) == {s for s, _l, _e in loaders}
    for slug, _loader, _error in loaders:
        await connect(db_session, b, connectors[slug])
        await _decide(db_session, slug, b.partner_id, enabled=False)
    for slug, loader, error in loaders:
        with pytest.raises(error, match="not available"):
            await loader(b.tenant_id)


async def test_the_credential_loaders_refuse_a_connector_its_partner_lost(
    db_session: AsyncSession, two_partners: tuple[Biz, Biz]
) -> None:
    """Requisito 5.4: `cobranza_reminder_cron` y `agent_sales_poll_cron` usan estos
    cargadores, y los saltan como «sin conexión»."""
    from nexus_mcp._connector_access import connection_is_available

    a, b = two_partners
    await _decide(db_session, "woocommerce", b.partner_id, enabled=False)
    for slug in ("woocommerce", "amigable_cobro", "amigable_venta"):
        async with get_sessionmaker()() as s, tenant_scoped_session(s, b.tenant_id):
            expected = slug != "woocommerce"
            assert await connection_is_available(s, b.tenant_id, slug) is expected, slug
        async with get_sessionmaker()() as s, tenant_scoped_session(s, a.tenant_id):
            assert await connection_is_available(s, a.tenant_id, slug) is True, slug


# ── 5. barrido de la consola entera (constitución §I: barrer, no enumerar) ───

_FAKE = "no_existe_060"
_FAKE_TOOL = f"{_FAKE}.list_items"
_ALLOWED_PARAMS = {"ref", "agent_id", "slug", "integration", "connection_id", "tool_name"}


def _console_routes() -> list[tuple[str, str]]:
    import re

    from nexus_api.main import app

    out: list[tuple[str, str]] = []
    for route in app.routes:
        path = getattr(route, "path", "")
        if not path.startswith("/console/clients/{ref}"):
            continue
        params = set(re.findall(r"{(\w+)}", path))
        if not params <= _ALLOWED_PARAMS:
            continue
        for method in sorted(getattr(route, "methods", set()) or set()):
            if method not in {"HEAD", "OPTIONS"}:
                out.append((method, path))
    return out


def _same(text: str, *names: str) -> str:
    for n in names:
        text = text.replace(n, "<x>")
    return text


async def test_no_console_route_reveals_a_connector_its_partner_lost(
    client: Any,
    db_session: AsyncSession,
    two_partners: tuple[Biz, Biz],
    seeded_catalog: None,  # noqa: F811
    fake_composio: Any,  # noqa: F811
) -> None:
    """Requisitos 5.1 y 5.2, barridos sobre ``app.routes``: ninguna lectura de la
    consola de B nombra el conector retenido ni sus herramientas, y toda ruta que
    lo nombra en la dirección (slug, conexión o herramienta) responde lo mismo que
    a uno que no existe."""
    _a, b = two_partners
    connector = await seed_integration(db_session)
    agent_b = await _agent_and_connection(db_session, b, connector, activate=False)
    # Un agente que no nombra el conector: lo que mide el barrido es si la consola
    # lo ofrece o lo enseña. Lo que un agente ya tenía sigue en su propia ficha
    # (5.7), y eso lo prueba test_connector_access_agent.
    from nexus_api.db.models import AgentConfig

    async with tenant_scoped_session(db_session, b.tenant_id):
        for cfg in (
            await db_session.scalars(sa.select(AgentConfig).where(AgentConfig.agent_id == agent_b))
        ).all():
            cfg.tools = []
            cfg.spec = {**(cfg.spec or {}), "skills": [], "procedures": []}
    await db_session.commit()
    async with get_sessionmaker()() as s, tenant_scoped_session(s, b.tenant_id):
        connection_id = await s.scalar(
            sa.select(TenantConnector.id).where(TenantConnector.connector_id == connector.id)
        )
    assert connection_id is not None
    await _decide(db_session, SLUG, b.partner_id, enabled=False)
    fake_connection = uuid.uuid4()

    routes = _console_routes()
    assert len(routes) > 100, "barrido roto: no encuentra las rutas de la consola"
    leaks: list[str] = []
    oracles: list[str] = []
    for method, path in routes:
        base = path.replace("{ref}", b.ref).replace("{agent_id}", str(agent_b))
        named = any(
            p in path for p in ("{slug}", "{integration}", "{connection_id}", "{tool_name}")
        )
        if not named:
            if method != "GET":
                continue
            resp = await client.get(base, headers=b.headers())
            if SLUG in resp.text or READ in resp.text or WRITE in resp.text:
                leaks.append(f"{method} {path}")
            continue
        real = (
            base.replace("{slug}", SLUG)
            .replace("{integration}", SLUG)
            .replace("{connection_id}", str(connection_id))
            .replace("{tool_name}", READ)
        )
        fake = (
            base.replace("{slug}", _FAKE)
            .replace("{integration}", _FAKE)
            .replace("{connection_id}", str(fake_connection))
            .replace("{tool_name}", _FAKE_TOOL)
        )
        kwargs: dict[str, Any] = {} if method in {"GET", "DELETE"} else {"json": {}}
        r1 = await client.request(method, real, headers=b.headers(), **kwargs)
        r2 = await client.request(method, fake, headers=b.headers(), **kwargs)
        t1 = _same(r1.text, SLUG, READ, str(connection_id))
        t2 = _same(r2.text, _FAKE, _FAKE_TOOL, str(fake_connection))
        if (r1.status_code, t1) != (r2.status_code, t2):
            oracles.append(f"{method} {path}: {r1.status_code} vs {r2.status_code}")

    # Las dos escrituras que nombran la herramienta en el cuerpo.
    for method, path, real_body, fake_body in (
        (
            "PUT",
            f"/console/clients/{b.ref}/capabilities?agent={agent_b}",
            {"key": READ, "kind": "tool", "enabled": True},
            {"key": _FAKE_TOOL, "kind": "tool", "enabled": True},
        ),
        (
            "PUT",
            f"/console/clients/{b.ref}/tools",
            {"tools": [READ]},
            {"tools": [_FAKE_TOOL]},
        ),
    ):
        r1 = await client.request(method, path, json=real_body, headers=b.headers())
        r2 = await client.request(method, path, json=fake_body, headers=b.headers())
        if (r1.status_code, _same(r1.text, READ, SLUG)) != (
            r2.status_code,
            _same(r2.text, _FAKE_TOOL, _FAKE),
        ):
            oracles.append(
                f"{method} {path.split('?')[0]} (cuerpo): {r1.status_code} vs {r2.status_code}"
            )

    assert not leaks, "lecturas que nombran el conector retenido:\n" + "\n".join(leaks)
    assert not oracles, "rutas que distinguen «retenido» de «no existe»:\n" + "\n".join(oracles)
