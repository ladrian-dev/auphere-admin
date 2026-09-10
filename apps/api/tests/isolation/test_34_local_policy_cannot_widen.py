"""Garantías 2 y 3 — la aplicación no puede ampliar lo que la máquina ejecuta.

La lista blanca de ejecutables es del cliente y solo se toca desde la consola
(001-R2). La spec 003 le pone encima dos capas —el techo del partner y la
preferencia de la persona— que **solo pueden restringir**. Este fichero prueba
justo eso, y las tres cosas que se romperían primero si alguien invirtiera un
``if``:

* con techo y preferencia en «permitir siempre», un ejecutable **fuera de la
  lista** sigue denegado, y no como decisión aprobable;
* la preferencia de una persona no toca a la de otra —ni siquiera cuando dice
  «permitir siempre», que es la que tendría premio si se filtrara—;
* el techo del partner no lo puede leer ni escribir otro partner.

En rojo bloquea el merge.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import select, text, update

from nexus_api.core.tenant_context import tenant_context
from nexus_api.db.models import (
    LocalExecutable,
    PartnerLocalExecPolicy,
    PrincipalLocalExecPref,
)
from nexus_api.db.models.local_workstation import (
    DENIAL_EJECUTABLE_NO_PERMITIDO,
    DENIAL_POLITICA_NUNCA,
    EXEC_ALWAYS,
    EXEC_ASK,
    EXEC_NEVER,
)
from nexus_api.services.local_exec_gate import LocalExecGate
from nexus_api.services.local_exec_policy import LocalExecPolicyRepository

from .conftest import set_partner, set_tenant

pytestmark = [pytest.mark.isolation, pytest.mark.asyncio]

ALLOWED = "make"
NOT_ALLOWED = "curl"


async def _whitelist(db_session, tenant_id: uuid.UUID) -> None:
    await set_tenant(db_session, tenant_id)
    with tenant_context(tenant_id):
        db_session.add(
            LocalExecutable(
                id=uuid.uuid4(), tenant_id=tenant_id, executable=ALLOWED, added_by="auphere"
            )
        )
        await db_session.flush()


async def _decide(db_session, tenant_id: uuid.UUID, executable: str, policy):
    await set_tenant(db_session, tenant_id)
    with tenant_context(tenant_id):
        return await LocalExecGate(db_session).evaluate(
            executable=executable, args=["test"], policy=policy
        )


# ── lo que ninguna capa de arriba puede hacer ──────────────────────────


async def test_no_policy_can_run_an_executable_outside_the_whitelist(db_session, console_world):
    from nexus_api.services.local_exec_policy import resolve

    a = console_world["a"]
    await _whitelist(db_session, a["tenant_id"])
    permissive = resolve(ceiling=EXEC_ALWAYS, global_pref=EXEC_ALWAYS, executable_pref=EXEC_ALWAYS)
    decision = await _decide(db_session, a["tenant_id"], NOT_ALLOWED, permissive)
    assert decision.outcome == "denegada"
    assert decision.denial_reason == DENIAL_EJECUTABLE_NO_PERMITIDO
    assert decision.is_approvable is False, (
        "ampliar la lista es un acto de la consola, no del turno"
    )


async def test_the_ceiling_lowers_what_the_person_asked_for(db_session, console_world):
    from nexus_api.services.local_exec_policy import resolve

    a = console_world["a"]
    await _whitelist(db_session, a["tenant_id"])
    capped = resolve(ceiling=EXEC_ASK, global_pref=EXEC_ALWAYS, executable_pref=None)
    decision = await _decide(db_session, a["tenant_id"], ALLOWED, capped)
    assert decision.outcome == "requiere_aprobacion"
    assert decision.capped is True, "la pantalla tiene que poder decir que manda el techo"


async def test_never_denies_with_its_own_reason_and_is_not_approvable(db_session, console_world):
    from nexus_api.services.local_exec_policy import resolve

    a = console_world["a"]
    await _whitelist(db_session, a["tenant_id"])
    forbidden = resolve(ceiling=EXEC_ALWAYS, global_pref=EXEC_NEVER, executable_pref=None)
    decision = await _decide(db_session, a["tenant_id"], ALLOWED, forbidden)
    assert decision.outcome == "denegada"
    assert decision.denial_reason == DENIAL_POLITICA_NUNCA
    assert decision.is_approvable is False


async def test_always_allows_without_writing_a_durable_grant(db_session, console_world):
    """Un permiso de argumentos es del **tenant** (001): escribir uno aquí
    dejaría pasar también a quien prefiere que le pregunten."""
    from nexus_api.db.models import LocalArgumentGrant
    from nexus_api.services.local_exec_policy import resolve

    a = console_world["a"]
    await _whitelist(db_session, a["tenant_id"])
    decision = await _decide(
        db_session,
        a["tenant_id"],
        ALLOWED,
        resolve(ceiling=EXEC_ALWAYS, global_pref=EXEC_ALWAYS, executable_pref=None),
    )
    assert decision.outcome == "permitida"
    assert decision.by_policy is True
    assert decision.grant_id is None
    grants = (await db_session.execute(select(LocalArgumentGrant.id))).scalars().all()
    assert grants == []


# ── la preferencia es de la persona; el techo, del partner ─────────────


async def test_one_persons_preference_never_reaches_another(db_session, console_world):
    a = console_world["a"]
    await set_partner(db_session, a["partner_id"], principal_id=a["user_id"])
    await LocalExecPolicyRepository(db_session).set_pref(
        partner_id=a["partner_id"], principal_id=a["user_id"], executable=None, mode=EXEC_ALWAYS
    )
    await db_session.commit()

    await set_partner(db_session, a["partner_id"], principal_id="user_colleague_a")
    mine = await LocalExecPolicyRepository(db_session).prefs(principal_id="user_colleague_a")
    assert mine == []
    everything = (await db_session.execute(select(PrincipalLocalExecPref.mode))).scalars().all()
    assert everything == [], "la RLS filtra por persona, no solo la consulta"


async def test_another_partner_cannot_read_or_move_the_ceiling(db_session, console_world):
    a, b = console_world["a"], console_world["b"]
    await set_partner(db_session, a["partner_id"], principal_id=a["user_id"])
    await LocalExecPolicyRepository(db_session).set_ceiling(
        a["partner_id"], ceiling=EXEC_NEVER, by=a["user_id"]
    )
    await db_session.commit()

    await set_partner(db_session, b["partner_id"], principal_id=b["user_id"])
    assert await LocalExecPolicyRepository(db_session).ceiling(a["partner_id"]) is None
    result = await db_session.execute(
        update(PartnerLocalExecPolicy)
        .where(PartnerLocalExecPolicy.partner_id == a["partner_id"])
        .values(ceiling=EXEC_ALWAYS)
    )
    assert result.rowcount == 0
    await db_session.rollback()

    await set_partner(db_session, a["partner_id"], principal_id=a["user_id"])
    assert await LocalExecPolicyRepository(db_session).ceiling(a["partner_id"]) == EXEC_NEVER


async def test_without_the_gucs_neither_table_answers(db_session, console_world):
    a = console_world["a"]
    await set_partner(db_session, a["partner_id"], principal_id=a["user_id"])
    await LocalExecPolicyRepository(db_session).set_ceiling(
        a["partner_id"], ceiling=EXEC_NEVER, by=a["user_id"]
    )
    await LocalExecPolicyRepository(db_session).set_pref(
        partner_id=a["partner_id"], principal_id=a["user_id"], executable="make", mode=EXEC_ALWAYS
    )
    await db_session.commit()
    await db_session.execute(
        text(
            "SELECT set_config('app.partner_id', '', true), "
            "set_config('app.principal_id', '', true), set_config('role', 'nexus_app', true)"
        )
    )
    assert (await db_session.execute(select(PartnerLocalExecPolicy.ceiling))).scalars().all() == []
    assert (await db_session.execute(select(PrincipalLocalExecPref.mode))).scalars().all() == []
