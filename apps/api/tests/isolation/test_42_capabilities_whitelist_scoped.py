"""Garantía 12.2 sobre Capacidades — spec 017, R5.

La pantalla de Capacidades es una puerta **nueva a la lista blanca del
agente**, que es lo que el runtime usa para decidir qué herramientas ve el
modelo (garantía 2). Hasta ahora esa lista se escribía desde
`/tools` mandándola entera; ahora se escribe capacidad a capacidad desde
`PUT /console/clients/{ref}/capabilities`. Una puerta nueva a un dato
sensible se prueba por sus dos costuras:

1. **Por partner.** Un partner nombrando el `ref` de otro no escribe nada, y
   el error no le dice si ese cliente existe. Lo que se comprueba no es solo
   el 404: es que **no queda rastro** — ni borrador creado, ni override, ni
   fila de auditoría en el otro tenant. El endpoint llama a `ensure_draft`,
   así que si la comprobación de alcance llegara tarde, un intento fallido
   dejaría un borrador en el cliente de otro.

2. **Por catálogo.** Lo que se escribe en la lista blanca es siempre
   subconjunto del catálogo visible. `test_2_tool_whitelist_contract.py`
   prueba que el servicio rechaza lo no catalogado al publicar; aquí se
   prueba la puerta de antes, que es la que toca el partner, e incluye el
   caso que el servicio no ve: una herramienta que **sí está** en
   `tool_catalog` pero marcada `INTERNAL` o `DEPRECATED`. La lectura las
   esconde; la escritura tiene que esconderlas igual, o la pantalla es una
   forma de encender lo que no se ofrece.

No se prueba por el camino feliz: en cada caso se **intenta** el cruce y se
mira el dato del otro lado.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
import sqlalchemy as sa

from nexus_api.db.models import (
    AgentConfig,
    AgentConfigStatus,
    AuditLog,
    TenantConnectorToolOverride,
    ToolCatalog,
    ToolStatus,
)

pytestmark = [pytest.mark.asyncio, pytest.mark.isolation]

#: Una capacidad real del catálogo base, para que el cruce falle por alcance
#: y no porque el nombre no exista.
UNA = "booking.create_appointment"


def _agent(tenant_id: uuid.UUID, *, tools: list[str]) -> AgentConfig:
    return AgentConfig(
        tenant_id=tenant_id,
        version=1,
        status=AgentConfigStatus.ACTIVE,
        system_prompt_rendered="Atiende a los clientes.",
        channels=[],
        tools=tools,
        policies={},
    )


async def _seed(db_session, tenant_id: uuid.UUID, *, tools: list[str]) -> None:
    db_session.add(_agent(tenant_id, tools=tools))
    await db_session.commit()


async def _drafts(db_session, tenant_id: uuid.UUID) -> list[AgentConfig]:
    rows = await db_session.scalars(
        sa.select(AgentConfig).where(
            AgentConfig.tenant_id == tenant_id,
            AgentConfig.status == AgentConfigStatus.STAGED,
        )
    )
    return list(rows.all())


async def _catalogue(db_session, *, visible: bool = True) -> set[str]:
    stmt = sa.select(ToolCatalog.name)
    if visible:
        stmt = stmt.where(ToolCatalog.status.notin_([ToolStatus.INTERNAL, ToolStatus.DEPRECATED]))
    return set((await db_session.scalars(stmt)).all())


async def _hidden_tool(db_session, *, status: ToolStatus) -> str:
    """Una herramienta que está en el catálogo y **no** se ofrece.

    El catálogo sembrado cambia según el entorno, así que el test se la crea
    en vez de confiar en que alguna esté marcada así.
    """
    name = f"oculta.{status.value.lower()}_{uuid.uuid4().hex[:8]}"
    db_session.add(
        ToolCatalog(
            id=uuid.uuid4(),
            name=name,
            description="No se ofrece en la pantalla.",
            mcp_server="test",
            input_schema={},
            output_schema={},
            capability_tags=[],
            status=status,
            read_only=True,
            destructive=False,
            default_mode="always",
        )
    )
    await db_session.commit()
    return name


# ── 1. por partner ─────────────────────────────────────────────────────


async def test_a_foreign_ref_writes_nothing_and_leaves_no_trace(
    client, console_world, db_session
) -> None:
    a, b = console_world["a"], console_world["b"]
    await _seed(db_session, b["tenant_id"], tools=["booking.check_availability"])

    for body in (
        {"key": UNA, "kind": "tool", "enabled": True},
        {"key": "escalation-policy", "kind": "skill", "enabled": True},
        {"key": UNA, "kind": "tool", "mode": "blocked"},
    ):
        r = await client.put(
            f"/console/clients/{b['ref']}/capabilities", headers=a["headers"](), json=body
        )
        assert r.status_code == 404, f"{body} → {r.status_code}"

    # La lista blanca de B, intacta: ni la capacidad pedida ni una vuelta más
    # de versión.
    activo = await db_session.scalar(
        sa.select(AgentConfig).where(
            AgentConfig.tenant_id == b["tenant_id"],
            AgentConfig.status == AgentConfigStatus.ACTIVE,
        )
    )
    assert activo is not None and activo.tools == ["booking.check_availability"]

    # Y sobre todo: el intento no le dejó un borrador. `ensure_draft` corre
    # dentro de este endpoint; si el alcance se comprobara después, B se
    # encontraría cambios sin publicar que nadie de su partner hizo.
    assert await _drafts(db_session, b["tenant_id"]) == []

    # Ni override de modo, ni rastro en auditoría.
    overrides = (await db_session.scalars(sa.select(TenantConnectorToolOverride))).all()
    assert [o for o in overrides if o.tenant_id == b["tenant_id"]] == []
    filas = (
        await db_session.scalars(
            sa.select(AuditLog).where(AuditLog.action == "console.capability.update")
        )
    ).all()
    assert list(filas) == [], "un intento cruzado no es un cambio: no puede auditarse como tal"


async def test_the_error_does_not_say_whether_that_client_exists(
    client, console_world, db_session
) -> None:
    """Garantía 12.2 «por error»: el 404 del cliente de otro y el de un
    cliente que no existe son el mismo, byte a byte."""
    a, b = console_world["a"], console_world["b"]
    await _seed(db_session, b["tenant_id"], tools=[])
    body: dict[str, Any] = {"key": UNA, "kind": "tool", "enabled": True}

    ajeno = await client.put(
        f"/console/clients/{b['ref']}/capabilities", headers=a["headers"](), json=body
    )
    fantasma = await client.put(
        "/console/clients/no-existe-nunca/capabilities", headers=a["headers"](), json=body
    )
    assert ajeno.status_code == fantasma.status_code == 404
    assert ajeno.text == fantasma.text

    # También en la lectura, que es la que se enumera.
    ga = await client.get(f"/console/clients/{b['ref']}/capabilities", headers=a["headers"]())
    gf = await client.get("/console/clients/no-existe-nunca/capabilities", headers=a["headers"]())
    assert ga.status_code == gf.status_code == 404
    assert ga.text == gf.text


# ── 2. por catálogo ────────────────────────────────────────────────────


async def test_what_gets_written_stays_inside_the_catalogue(
    client, console_world, db_session
) -> None:
    a = console_world["a"]
    await _seed(db_session, a["tenant_id"], tools=[])

    # Un nombre inventado no entra.
    r = await client.put(
        f"/console/clients/{a['ref']}/capabilities",
        headers=a["headers"](),
        json={"key": "payment.charge", "kind": "tool", "enabled": True},
    )
    assert r.status_code == 404
    assert r.json()["detail"] == "unknown_capability"

    # Ni una habilidad que no está en el bundle.
    r = await client.put(
        f"/console/clients/{a['ref']}/capabilities",
        headers=a["headers"](),
        json={"key": "habilidad-que-no-existe", "kind": "skill", "enabled": True},
    )
    assert r.status_code == 404

    # Un cambio legítimo sí, y lo que queda escrito es subconjunto de lo que
    # el catálogo ofrece.
    ok = await client.put(
        f"/console/clients/{a['ref']}/capabilities",
        headers=a["headers"](),
        json={"key": UNA, "kind": "tool", "enabled": True},
    )
    assert ok.status_code == 200, ok.text

    borradores = await _drafts(db_session, a["tenant_id"])
    assert len(borradores) == 1
    escrito = set(borradores[0].tools or [])
    assert escrito == {UNA}
    assert escrito <= await _catalogue(db_session), (
        f"la lista blanca salió del catálogo: {sorted(escrito - await _catalogue(db_session))}"
    )


@pytest.mark.parametrize("status", [ToolStatus.INTERNAL, ToolStatus.DEPRECATED])
async def test_a_tool_the_screen_hides_cannot_be_turned_on_through_it(
    client, console_world, db_session, status: ToolStatus
) -> None:
    """La lectura esconde `INTERNAL` y `DEPRECATED`; la escritura tiene que
    esconderlas igual.

    Si no, la pantalla se convierte en la forma de encender lo que la
    plataforma decidió no ofrecer — y lo haría sin que el partner lo vea,
    porque lo que acaba de escribir no sale en la lista que lee después.
    """
    a = console_world["a"]
    nombre = await _hidden_tool(db_session, status=status)
    await _seed(db_session, a["tenant_id"], tools=[])

    r = await client.put(
        f"/console/clients/{a['ref']}/capabilities",
        headers=a["headers"](),
        json={"key": nombre, "kind": "tool", "enabled": True},
    )
    assert r.status_code == 404, f"{status.value} se aceptó: {r.text}"

    for borrador in await _drafts(db_session, a["tenant_id"]):
        assert nombre not in (borrador.tools or []), (
            f"{nombre} ({status.value}) quedó en la lista blanca aunque la respuesta fue "
            f"{r.status_code}: el rechazo llegó después de escribir"
        )
