"""Mundo y juego de herramientas de los evals del Companion (CO-07).

Reutiliza ``console_world`` de la conftest raíz: dos partners con consola
habilitada, un cliente cada uno y una membresía ``owner`` activa. Es el mundo
mínimo en el que "el cliente del otro partner" existe de verdad — sin eso la
familia 3 no prueba nada.

Encima se añade un **segundo cliente del partner A cuyo nombre choca con el
primero**, que es lo que hace que la familia 2 sea de verdad ambigua: dos
candidatos reales en la base, no una suposición del caso.
"""

from __future__ import annotations

import re
import uuid
from typing import Any

import pytest
import pytest_asyncio

from nexus_api.companion.tools import CompanionToolbelt
from nexus_api.core.console_auth import InProcessActor
from tests.conftest import add_console_member

#: Los dos clientes de A comparten esta raíz de nombre. Un ``client_ref``
#: que la contenga no resuelve a exactamente uno → R2 exige preguntar.
AMBIGUOUS_NAME = "Clínica Boreal"


def actor_for(side: dict[str, Any]) -> InProcessActor:
    return InProcessActor(
        user_id=side["user_id"],
        partner_id=side["partner_id"],
        jti=f"companion-eval:{uuid.uuid4()}",
    )


@pytest_asyncio.fixture
async def eval_world(db_session, console_world, belt_for) -> dict[str, Any]:
    """``console_world``, más las tres cosas que las familias necesitan:

    - el **cliente gemelo** que crea la ambigüedad de la familia 2;
    - un miembro **`builder`**, que es el único principal con el que se puede
      probar el techo de rol de C6 — un `owner` no puede escalar por encima
      de sí mismo, así que desde el `owner` del mundo la garantía no se ve;
    - los **nombres reales** de la primera herramienta y la primera skill del
      catálogo del cliente. Van al mundo y no escritos a mano en el JSON para
      que un cambio de la plantilla semilla no ponga rojo un caso que no
      habla de eso.
    """
    from nexus_api.db.models import PartnerTenant, Tenant, TenantPlan, TenantStatus

    a = console_world["a"]
    twin_tenant = uuid.uuid4()
    twin_ref = "client-a-2"
    db_session.add(
        Tenant(
            id=twin_tenant,
            name=f"{AMBIGUOUS_NAME} Centro",
            slug=f"p-{a['slug']}-two",
            plan=TenantPlan.PRO,
            status=TenantStatus.ACTIVE,
            partner_id=a["partner_id"],
        )
    )
    await db_session.flush()
    db_session.add(
        PartnerTenant(
            partner_id=a["partner_id"],
            external_client_ref=twin_ref,
            tenant_id=twin_tenant,
            client_name=f"{AMBIGUOUS_NAME} Centro",
        )
    )
    # El primero de A se renombra para que ambos encajen con la búsqueda.
    first = await db_session.get(Tenant, a["tenant_id"])
    assert first is not None
    first.name = f"{AMBIGUOUS_NAME} Sur"
    mapping = await db_session.get(PartnerTenant, (a["partner_id"], a["ref"]))
    assert mapping is not None
    mapping.client_name = f"{AMBIGUOUS_NAME} Sur"
    # ``commit`` y no ``flush``: la aplicación lee por su propia sesión, y
    # el patrón de la conftest raíz (SAVEPOINT sobre una transacción
    # externa) solo hace visible lo confirmado. ``console_world`` hace lo
    # mismo por la misma razón.
    await db_session.commit()

    builder = await add_console_member(db_session, partner_id=a["partner_id"], role="builder")

    side_a = {**a, "twin_ref": twin_ref, "twin_tenant_id": twin_tenant}
    catalogue = await _catalogue_names(await belt_for(side_a, max_calls=8), a["ref"])

    world = {
        "a": {**side_a, **catalogue},
        # Mismo partner, rol menor. Es el principal de los casos de C6.
        "a_builder": {**side_a, **catalogue, "user_id": builder["user_id"], "role": "builder"},
        "b": console_world["b"],
        "ambiguous_query": "boreal",
    }
    return world


async def _catalogue_names(belt: Any, ref: str) -> dict[str, str]:
    """La primera herramienta y la primera skill del catálogo del cliente.

    Se leen y no se escriben a mano porque el catálogo lo fija la plantilla
    semilla del vertical: un caso que nombrase ``booking.check_availability``
    a pelo se caería el día que alguien renombre la plantilla, y el rojo
    hablaría de otra cosa distinta de la que el caso prueba.
    """
    tools = re.findall(
        r'"name":"([\w.]+)"', (await belt.call("console.list_tools", {"client_ref": ref})).content
    )
    skills = re.findall(
        r'"name":"([\w.-]+)"', (await belt.call("console.list_skills", {"client_ref": ref})).content
    )
    assert tools, "el cliente semilla no trae herramientas: la familia 1 no puede proponer"
    assert skills, "el cliente semilla no trae skills: la familia 1 no puede proponer"
    return {"first_tool": tools[0], "first_skill": skills[0]}


@pytest_asyncio.fixture
async def belt_for(client):
    """Un juego de herramientas contra la aplicación real, con lifespan.

    ``client`` se pide aunque no se use: es quien abre el lifespan de la
    app, y sin él las llamadas en proceso salen contra una app a medio
    montar.
    """
    from nexus_api.main import app

    made: list[CompanionToolbelt] = []

    async def _make(side: dict[str, Any], **kwargs: Any) -> CompanionToolbelt:
        belt = CompanionToolbelt(actor=actor_for(side), app=app, **kwargs)
        await belt.__aenter__()
        made.append(belt)
        return belt

    yield _make
    for belt in made:
        await belt.__aexit__(None, None, None)


@pytest.fixture
def dataset(eval_world):
    """El dataset con las ``$a.ref`` ya resueltas contra el mundo."""
    from nexus_api.services.evals.companion.dataset import load_dataset

    return load_dataset(world=eval_world)
