"""Spec 029: every audit sentence is complete and in the partner's words.

Before this spec 37 of the first 50 rows of a real partner read «cambió la
capacidad ? de Lola Mento: ?.». The first test is the guard: a template in
the vocabulary that uses a placeholder nobody fills fails here, before a
partner reads it.
"""

from __future__ import annotations

import re
import string
from pathlib import Path

import pytest
import sqlalchemy as sa

from nexus_api.api.console import audit as audit_module
from nexus_api.api.console import audit_words
from nexus_api.db.models import AuditLog

pytestmark = pytest.mark.asyncio


async def test_every_placeholder_of_the_vocabulary_is_filled(db_session) -> None:
    rows = (
        await db_session.execute(
            sa.text("SELECT action, summary_es, summary_en FROM console_audit_vocabulary")
        )
    ).all()
    assert rows, "the vocabulary is empty: run the migrations"
    missing: dict[str, set[str]] = {}
    for action, es, en in rows:
        for text in (es, en):
            used = {name for _, name, _, _ in string.Formatter().parse(text) if name}
            unfilled = used - audit_words.PLACEHOLDERS
            if unfilled:
                missing.setdefault(action, set()).update(unfilled)
    assert not missing, f"placeholders nobody fills: {missing}"


def _row(
    action: str, after: dict | None = None, before: dict | None = None, target: str = "x"
) -> AuditLog:
    return AuditLog(
        tenant_id=None,
        actor="console:ana@example.com",
        action=action,
        target=target,
        after_json=after,
        before_json=before,
    )


async def test_codes_become_words_and_refs_become_names(db_session) -> None:
    audit_module.reset_vocabulary_cache_for_tests()
    vocab = await audit_module.load_vocabulary(db_session, force=True)
    names = {"panaderia-la-espiga": "Panadería La Espiga", "lola": "Lola Mento"}

    def say(row: AuditLog, lang: str = "es") -> str:
        return audit_module.summarise(
            row,
            "Lola Mento",
            vocab,
            lang,
            names_by_ref=names,
            connector_names={"woocommerce": "WooCommerce"},
            partner_name="Demo",
        )

    capability = say(
        _row(
            "console.capability.update",
            {"key": "catalog.search_products", "kind": "tool", "enabled": True},
        )
    )
    assert "?" not in capability
    assert capability.endswith("de Lola Mento: activada.")
    assert "catalog.search_products" not in capability

    moved = say(
        _row(
            "console.allocation.move",
            {"from": "panaderia-la-espiga", "to": "lola", "amount_cents": 525},
        )
    )
    assert moved == "ana@example.com movió 5,25 US$ de Panadería La Espiga a Lola Mento."

    status = say(_row("console.client.status", {"status": "paused"}, {"status": "active"}))
    assert status == "ana@example.com cambió el estado de Lola Mento a en pausa."
    assert say(_row("console.client.status", {"status": "active"}), "en").endswith("to active.")

    assert say(_row("console.usage.alerts_update", {"cap": None})).endswith("(sin tope).")
    assert say(_row("console.usage.alerts_update", {"cap": 1000})).endswith(
        "(tope de 1000 mensajes)."
    )
    assert "WooCommerce" in say(_row("console.connector.connect", {"slug": "woocommerce"}))
    assert "como constructor" in say(
        _row("console.member.invite", {"email": "b@example.com", "role": "builder"})
    )
    # ``console.channel.role`` keeps the phone as ``identifier``.
    assert "+34600000000" in say(
        _row("console.channel.role", {"role": "agent", "identifier": "+34600000000"})
    )


async def test_inviting_an_owner_reads_as_a_sentence_signed_by_auphere(db_session) -> None:
    """Spec 052 (R6.4): the console shows the operator as Auphere's team, and the
    panel names the person (``actor_label``)."""
    audit_module.reset_vocabulary_cache_for_tests()
    vocab = await audit_module.load_vocabulary(db_session, force=True)
    after = {"email": "duena@negocio.test", "role": "owner"}

    def row(action: str) -> AuditLog:
        return AuditLog(
            tenant_id=None,
            actor="operator:ana@auphere.com",
            action=action,
            target="partner:x",
            after_json=after,
        )

    for action in (
        "partner.owner_invited",
        "partner.owner_invitation_resent",
        "partner.owner_invitation_revoked",
    ):
        for lang in ("es", "en"):
            sentence = audit_module.summarise(row(action), None, vocab, lang, partner_name="Acme")
            assert sentence.startswith("Auphere "), sentence
            assert "duena@negocio.test" in sentence and "Acme" in sentence
            assert "?" not in sentence and "ana@auphere.com" not in sentence
            named = audit_module.summarise(
                row(action), None, vocab, lang, partner_name="Acme", actor_label="ana@auphere.com"
            )
            assert named.startswith("ana@auphere.com ")


async def test_the_client_access_actions_name_who_did_them(db_session) -> None:
    """Spec 056 (3.8, 0225): the partner changes its client's access too, so the
    sentence names who did it instead of saying «Auphere» outright. Auphere's
    team still reads as «Auphere» in the console."""
    audit_module.reset_vocabulary_cache_for_tests()
    vocab = await audit_module.load_vocabulary(db_session, force=True)
    after = {"enabled": True, "modules": ["panel"]}

    def say(actor: str, action: str, lang: str) -> str:
        row = AuditLog(
            tenant_id=None, actor=actor, action=action, target="tenant:x", after_json=after
        )
        return audit_module.summarise(row, "Lola Mento", vocab, lang)

    for action in (
        "client_access.updated",
        "client_member.invited",
        "client_member.resent",
        "client_member.revoked",
    ):
        for lang in ("es", "en"):
            assert vocab[action].summary(lang).startswith("{actor} "), (action, lang)
            by_partner = say("console:maria@negocio.test", action, lang)
            assert by_partner.startswith("maria@negocio.test "), by_partner
            assert "Lola Mento" in by_partner and "?" not in by_partner
            by_operator = say("operator:ana@auphere.com", action, lang)
            assert by_operator.startswith("Auphere "), by_operator
            assert "ana@auphere.com" not in by_operator
    assert say("console:maria@negocio.test", "client_access.updated", "es") == (
        "maria@negocio.test cambió el acceso de Lola Mento a su consola."
    )


async def test_the_brake_and_the_correction_batches_have_their_sentences(db_session) -> None:
    """Spec 056 (1.5, 9.2, 0225): the booking brake writes as the worker, and the
    partner accepts or discards a correction for several agents at once."""
    audit_module.reset_vocabulary_cache_for_tests()
    vocab = await audit_module.load_vocabulary(db_session, force=True)

    def say(actor: str, action: str, after: dict, lang: str = "es") -> str:
        row = AuditLog(tenant_id=None, actor=actor, action=action, target="x", after_json=after)
        return audit_module.summarise(row, "Lola Mento", vocab, lang)

    brake = {"agent_id": "a", "turn_id": "t", "outcome": "retried"}
    assert say("system:worker", "agent.booking_brake", brake) == (
        "El freno de citas actuó en una conversación de Lola Mento."
    )
    assert say("system:worker", "agent.booking_brake", brake, "en") == (
        "The booking brake stepped in on a conversation of Lola Mento."
    )
    assert vocab["agent.booking_brake"].category == "agents"

    batch = {"agents": ["a", "b"], "skipped": []}
    for action, es, en in (
        ("correction.batch_accepted", "aceptó", "accepted"),
        ("correction.batch_discarded", "descartó", "discarded"),
    ):
        assert vocab[action].category == "improvement"
        spanish = say("console:maria@negocio.test", action, batch)
        assert spanish.startswith(f"maria@negocio.test {es} una corrección de Lola Mento")
        english = say("console:maria@negocio.test", action, batch, "en")
        assert english.startswith(f"maria@negocio.test {en} a correction from Lola Mento")
        assert "?" not in spanish + english


async def test_the_actions_written_outside_the_console_read_as_sentences(db_session) -> None:
    """What staging showed as «Auphere · connector.disconnect ·
    connector:googlesheets», with the payloads the real writers store."""
    audit_module.reset_vocabulary_cache_for_tests()
    vocab = await audit_module.load_vocabulary(db_session, force=True)

    def say(row: AuditLog, lang: str = "es") -> str:
        return audit_module.summarise(
            row,
            "Lola Mento",
            vocab,
            lang,
            connector_names={"googlesheets": "Google Sheets"},
            partner_name="Demo",
        )

    cases = {
        say(
            _row(
                "connector.disconnect", {"status": "disconnected"}, target="connector:googlesheets"
            )
        ): "ana@example.com desconectó Google Sheets en Lola Mento.",
        say(
            _row(
                "connector.pause",
                {"status": "paused", "slug": "googlesheets"},
                target="tenant_connector:1",
            )
        ): "ana@example.com pausó Google Sheets en Lola Mento.",
        say(
            _row(
                "channel.whatsapp.quality_rating_changed",
                {"quality_rating": "YELLOW"},
                {"quality_rating": "GREEN"},
            )
        ): "La calidad del WhatsApp de Lola Mento pasó de alta a media.",
        say(
            _row(
                "cost.daily_threshold_exceeded",
                {"day": "2026-10-03", "cost_usd_total": "12.34", "threshold_usd": "10.00"},
            )
        ): "Lola Mento gastó 12,34 US$ el 03/10/2026, por encima del aviso de 10,00 US$.",
        say(
            _row(
                "channel.whatsapp.meta_signup",
                {"display_phone_number": "+34 600 00 00 00", "mode": "coexistence"},
            )
        ): "ana@example.com conectó el WhatsApp +34 600 00 00 00 en Lola Mento en coexistencia con la app.",
        say(
            _row(
                "connector.override_upsert",
                {"mode": "blocked"},
                target="tool:catalog.search_products",
            )
        ).split(": ")[-1]: "bloqueada.",
        say(
            _row("budget.hard_limit_reached", {"spent_usd": "50", "limit_usd": "50"})
        ): "Lola Mento llegó a su límite de gasto (50,00 US$ de 50,00 US$) y el agente pasó la conversación al equipo.",
    }
    for got, want in cases.items():
        assert got == want
    tool = say(
        _row(
            "connector.override_upsert", {"mode": "blocked"}, target="tool:catalog.search_products"
        )
    )
    assert "catalog.search_products" not in tool and "?" not in tool


async def test_auphere_monitoring_rows_stay_out_of_the_partner_trail(
    client, console_world, db_session
) -> None:
    a = console_world["a"]
    db_session.add(
        AuditLog(
            tenant_id=a["tenant_id"],
            actor="system:isolation_watcher",
            action="isolation.violation_detected",
            target=f"tenant:{a['tenant_id']}:metric:x",
        )
    )
    await db_session.commit()
    items = (await client.get("/console/audit", headers=a["headers"]())).json()["items"]
    assert all(i["action"] != "isolation.violation_detected" for i in items)


async def test_rows_carry_category_severity_and_who_wrote_them(
    client, console_world, db_session
) -> None:
    a = console_world["a"]
    audit_module.reset_vocabulary_cache_for_tests()
    db_session.add_all(
        [
            AuditLog(
                tenant_id=a["tenant_id"],
                actor="console:owner-a@example.com",
                action="tenant.delete",
                target="tenant:x",
            ),
            AuditLog(
                tenant_id=a["tenant_id"],
                actor=f"companion:{a['user_id']}",
                action="agent_config.promote",
                target="agent_config:1",
                after_json={"version": 2},
            ),
        ]
    )
    await db_session.commit()
    items = (await client.get("/console/audit?lang=es", headers=a["headers"]())).json()["items"]
    by_action = {i["action"]: i for i in items}
    assert by_action["tenant.delete"]["severity"] == "critical"
    assert by_action["tenant.delete"]["category"] == "clients"
    assert by_action["tenant.delete"]["actor_kind"] == "person"
    assert by_action["agent_config.promote"]["actor_kind"] == "companion"

    # «Filtrar por categoría» (spec 017 R11.5).
    agents = (await client.get("/console/audit?category=agents", headers=a["headers"]())).json()[
        "items"
    ]
    assert {i["action"] for i in agents} == {"agent_config.promote"}
    nothing = (await client.get("/console/audit?category=nope", headers=a["headers"]())).json()[
        "items"
    ]
    assert nothing == []


async def test_filters_offer_clients_people_and_categories_of_this_partner_only(
    client, console_world
) -> None:
    a = console_world["a"]
    r = await client.get("/console/audit/filters?lang=es", headers=a["headers"]())
    assert r.status_code == 200, r.text
    body = r.json()
    assert [c["label"] for c in body["clients"]] == ["Client A One"]
    people = {p["value"]: p["label"] for p in body["people"]}
    assert people["owner-a@example.com"] == "Owner A"
    assert "owner-b@example.com" not in people
    assert people["companion:"] == "Companion" and people["admin:"] == "Auphere"
    labels = {c["value"]: c["label"] for c in body["categories"]}
    assert labels["clients"] == "Clientes" and labels["workstation"] == "Máquinas"
    assert not {"admin", "critical", "info", "warning"} & labels.keys()


_APPS = Path(__file__).resolve().parents[3]
#: Written to ``qa.audit_log`` (the Playground's own trail), not ``audit_log``.
_NOT_THE_PARTNER_TRAIL = {"thread.create", "thread.patch"}
_WRITTEN = (
    re.compile(r"""action\s*=\s*["']([a-z_]+\.[a-z0-9_.]+)["']"""),
    re.compile(r"""_audit\([^,()]+,\s*["']([a-z_]+\.[a-z0-9_.]+)["']"""),
    # Constants: ``ESCALATION_ACTION = "budget.hard_limit_reached"``.
    re.compile(
        r"""^[A-Z_]*ACTION[A-Z_]*(?:\s*:\s*[^=\n]+)?\s*=\s*["']([a-z_]+\.[a-z0-9_.]+)["']""", re.M
    ),
    re.compile(r"""INSERT INTO audit_log[^;]*?'([a-z_]+\.[a-z0-9_.]+)'""", re.S),
)


def _actions_written_anywhere() -> set[str]:
    found: set[str] = set()
    # Every service that writes ``audit_log``: the agent's tools (``mcp``)
    # write the escalation, and missing them let one row read as code.
    for root in (_APPS / name / "src" for name in ("api", "worker", "mcp", "channels")):
        for path in root.rglob("*.py"):
            text = path.read_text()
            for pattern in _WRITTEN:
                found.update(pattern.findall(text))
    return found - _NOT_THE_PARTNER_TRAIL


async def test_every_action_the_code_writes_has_a_sentence(db_session) -> None:
    """A row without a sentence reads as code («Auphere · connector.disconnect
    · connector:googlesheets»), which is what the partner saw in staging."""
    seeded = {
        r[0]
        for r in (
            await db_session.execute(sa.text("SELECT action FROM console_audit_vocabulary"))
        ).all()
    }
    missing = sorted(a for a in _actions_written_anywhere() - seeded if not a.endswith("_failed"))
    assert not missing, f"actions without a sentence in console_audit_vocabulary: {missing}"
