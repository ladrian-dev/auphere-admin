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
    re.compile(r"""action\s*=\s*["']([a-z_]+\.[a-z_.]+)["']"""),
    re.compile(r"""_audit\([^,()]+,\s*["']([a-z_]+\.[a-z_.]+)["']"""),
    # Constants: ``ESCALATION_ACTION = "budget.hard_limit_reached"``.
    re.compile(
        r"""^[A-Z_]*ACTION[A-Z_]*(?:\s*:\s*[^=\n]+)?\s*=\s*["']([a-z_]+\.[a-z_.]+)["']""", re.M
    ),
    re.compile(r"""INSERT INTO audit_log[^;]*?'([a-z_]+\.[a-z_.]+)'""", re.S),
)


def _actions_written_anywhere() -> set[str]:
    found: set[str] = set()
    for root in (_APPS / "api" / "src", _APPS / "worker" / "src"):
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
