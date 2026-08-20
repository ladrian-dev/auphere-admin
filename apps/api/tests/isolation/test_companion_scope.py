"""Garantía de aislamiento — el alcance del Companion (CO-01).

Tres dimensiones, y las tres tienen que fallar cerradas:

1. **Entre principales del MISMO partner.** Dos personas del mismo partner
   no ven los hilos ni los runs de la otra. Es el equivalente de la
   garantía por operador de ``qa.*``, y aquí importa más: un hilo del
   Companion puede contener el borrador de un prompt que su autor todavía
   no quiere enseñar.
2. **Entre partners.** El ``client_ref`` de otro partner devuelve un 404
   **byte a byte idéntico** al de una referencia que no existe. Confirmar
   que el cliente existe para otro ya es una fuga.
3. **Contra la RLS de Postgres.** Sin ``app.principal_id`` no se ve una
   sola fila. Es el techo duro: si fallara una de las dos capas de arriba,
   esta sigue.

La regla del rol (``companion:use``) se prueba aparte, en el test
parametrizado de ``test_console_scope.py``, que recorre todas las rutas.
"""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa

from nexus_api.core.principal_context import apply_principal_to_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models.companion import CompanionRun, CompanionThread
from tests.conftest import add_console_member

pytestmark = [pytest.mark.isolation]


async def _thread_of(client, headers, **body) -> dict:
    resp = await client.post("/console/companion/threads", headers=headers(), json=body)
    assert resp.status_code == 201, resp.text
    return resp.json()


# ── 1. entre principales del mismo partner ─────────────────────────────


async def test_a_thread_of_another_member_is_an_opaque_404(client, console_world, db_session):
    a = console_world["a"]
    other = await add_console_member(db_session, partner_id=a["partner_id"], role="builder")

    mine = await _thread_of(client, a["headers"], title="mi borrador")

    seen = await client.patch(
        f"/console/companion/threads/{mine['id']}",
        headers=other["headers"](),
        json={"title": "robado"},
    )
    assert seen.status_code == 404
    # Idéntico a un hilo que no existe: el 404 no confirma nada.
    missing = await client.patch(
        f"/console/companion/threads/{uuid.uuid4()}",
        headers=other["headers"](),
        json={"title": "x"},
    )
    assert seen.json() == missing.json() == {"detail": "Unknown thread"}


async def test_the_thread_list_only_shows_your_own(client, console_world, db_session):
    a = console_world["a"]
    other = await add_console_member(db_session, partner_id=a["partner_id"], role="builder")
    mine = await _thread_of(client, a["headers"], title="mío")

    theirs = await client.get("/console/companion/threads", headers=other["headers"]())
    assert theirs.status_code == 200
    assert mine["id"] not in [t["id"] for t in theirs.json()]

    ours = await client.get("/console/companion/threads", headers=a["headers"]())
    assert mine["id"] in [t["id"] for t in ours.json()]


async def test_a_run_of_another_member_is_an_opaque_404(client, console_world, db_session):
    """El ``run_id`` es un UUID que puede acabar en un log o en una URL
    compartida. Que se filtre no puede bastar para leer la conversación."""
    a = console_world["a"]
    other = await add_console_member(db_session, partner_id=a["partner_id"], role="builder")
    mine = await _thread_of(client, a["headers"], title="mío")

    sm = get_sessionmaker()
    run_id = uuid.uuid4()
    async with sm() as session, session.begin():
        await apply_principal_to_session(session, a["user_id"])
        session.add(
            CompanionRun(id=run_id, thread_id=uuid.UUID(mine["id"]), principal_id=a["user_id"])
        )

    for path in (f"/console/companion/runs/{run_id}/events",):
        resp = await client.get(path, headers=other["headers"]())
        assert resp.status_code == 404, f"{path} → {resp.status_code}"
        assert resp.json() == {"detail": "Unknown run"}

    cancelled = await client.delete(f"/console/companion/runs/{run_id}", headers=other["headers"]())
    assert cancelled.status_code == 404


# ── 2. entre partners ──────────────────────────────────────────────────


async def test_another_partners_client_ref_is_the_same_404_as_a_missing_one(client, console_world):
    a, b = console_world["a"], console_world["b"]
    foreign = await client.post(
        "/console/companion/threads",
        headers=a["headers"](),
        json={"title": "x", "client_ref": b["ref"]},
    )
    missing = await client.post(
        "/console/companion/threads",
        headers=a["headers"](),
        json={"title": "x", "client_ref": "does-not-exist"},
    )
    assert foreign.status_code == missing.status_code == 404
    assert foreign.json() == missing.json() == {"detail": "Unknown client reference"}


async def test_the_thread_never_answers_with_an_internal_tenant_id(client, console_world):
    """El partner habla ``client_ref``; el ``tenant_id`` es un id interno y
    la consola no lo ve nunca, ni siquiera del cliente que sí es suyo."""
    a = console_world["a"]
    thread = await _thread_of(client, a["headers"], title="x", client_ref=a["ref"])
    assert thread["client_ref"] == a["ref"]
    assert "tenant_id" not in thread
    assert str(a["tenant_id"]) not in str(thread)


# ── 3. la RLS de Postgres, el techo duro ───────────────────────────────


async def test_without_the_principal_guc_no_row_is_visible(client, console_world):
    """Fail-closed: un camino que olvide aplicar el ámbito no ve datos de
    nadie, en vez de verlos todos."""
    a = console_world["a"]
    thread = await _thread_of(client, a["headers"], title="secreto")

    sm = get_sessionmaker()
    async with sm() as session, session.begin():
        # Rol degradado SIN ``app.principal_id``.
        await session.execute(sa.text("SET LOCAL ROLE nexus_app"))
        rows = (
            await session.execute(
                sa.select(CompanionThread.id).where(CompanionThread.id == uuid.UUID(thread["id"]))
            )
        ).all()
    assert rows == []


async def test_the_rls_check_would_catch_a_leak(client, console_world):
    """Control del control: con el GUC correcto, la misma consulta SÍ ve la
    fila. Sin esto, el test de arriba pasaría igual con una tabla vacía."""
    a = console_world["a"]
    thread = await _thread_of(client, a["headers"], title="secreto")

    sm = get_sessionmaker()
    async with sm() as session, session.begin():
        await apply_principal_to_session(session, a["user_id"])
        rows = (
            await session.execute(
                sa.select(CompanionThread.id).where(CompanionThread.id == uuid.UUID(thread["id"]))
            )
        ).all()
    assert len(rows) == 1


async def test_messages_inherit_the_isolation_of_their_thread(client, console_world, db_session):
    """``companion.messages`` no lleva ``principal_id``: se cubre por
    ``EXISTS`` sobre el hilo. Si esa policy se rompiera, la transcripción
    sería legible con solo saber el ``thread_id``."""
    from nexus_api.db.models.companion import CompanionMessage

    a = console_world["a"]
    other = await add_console_member(db_session, partner_id=a["partner_id"], role="builder")
    thread = await _thread_of(client, a["headers"], title="x")

    sm = get_sessionmaker()
    async with sm() as session, session.begin():
        await apply_principal_to_session(session, a["user_id"])
        session.add(
            CompanionMessage(
                thread_id=uuid.UUID(thread["id"]), seq=1, role="user", content="mi secreto"
            )
        )

    async with sm() as session, session.begin():
        await apply_principal_to_session(session, other["user_id"])
        rows = (
            await session.execute(
                sa.select(CompanionMessage.content).where(
                    CompanionMessage.thread_id == uuid.UUID(thread["id"])
                )
            )
        ).all()
    assert rows == []


# ── el invariante del que depende toda la dimensión 2 ──────────────────


async def test_cross_partner_isolation_rests_on_a_declared_invariant(db_session) -> None:
    """La RLS del Companion filtra por ``principal_id`` **y nada más**.

    Eso aísla bien hoy, pero no por sí solo: aísla porque ``principal_id`` es
    el ``user_id`` a secas y la migración 0080 impone ``UNIQUE (user_id)`` en
    ``partner_memberships`` — "en v1 un usuario pertenece a exactamente un
    partner". Las dos piezas están a seis migraciones de distancia y nada las
    ata.

    El día que se admita multi-membresía —lo natural para agencias y
    revendedores, y lo que el plan de la app v2 ya contempla— los hilos de un
    partner aparecerían en la sesión del otro **sin que nada falle ni avise**:
    misma persona, mismo ``principal_id``, política satisfecha. La tabla ya
    guarda ``partner_id``; simplemente no se usa para filtrar.

    Este test es el hilo que ata las dos piezas. Acepta cualquiera de las dos
    defensas —el índice único, o una política que mire el partner— y solo
    falla si desaparecen las dos. Así no estorba a quien haga el cambio bien:
    quien añada multi-membresía y arregle la política a la vez lo verá seguir
    en verde.
    """
    unique_user = await db_session.scalar(
        sa.text("SELECT count(*) FROM pg_indexes WHERE indexname = :name"),
        {"name": "uq_partner_memberships_user"},
    )

    # ``qual`` es el USING de la política, tal y como Postgres lo reescribe.
    quals = (
        await db_session.execute(
            sa.text(
                "SELECT qual FROM pg_policies "
                "WHERE schemaname = 'companion' AND tablename = 'threads'"
            )
        )
    ).scalars().all()
    policy_scopes_partner = any("partner_id" in (q or "") for q in quals)

    assert unique_user == 1 or policy_scopes_partner, (
        "El aislamiento entre partners del Companion se quedó sin suelo.\n"
        "La política RLS de companion.threads filtra solo por principal_id, y el "
        "índice único uq_partner_memberships_user ya no está — así que un usuario "
        "puede pertenecer a dos partners y ver en uno los hilos que creó en el otro.\n"
        "Arréglalo por cualquiera de los dos lados: devuelve el índice único, o "
        "añade partner_id a la política (USING y WITH CHECK) de las cuatro tablas "
        "del esquema companion."
    )
