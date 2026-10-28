"""Spec 047, T165 — cada aviso nuevo lleva su enlace al arreglo (requisito 49.5;
``contracts/events.md`` §3)."""

from __future__ import annotations

import re
from pathlib import Path

from nexus_api.api.console.notifications import LINKS, LITE_LINKS, link_for
from nexus_api.db.models.console_notification import NotificationKind

EVENTS_MD = (
    Path(__file__).resolve().parents[4]
    / "specs"
    / "047-la-fabrica-de-agentes"
    / "contracts"
    / "events.md"
)


def _spec_kinds() -> set[str]:
    """Los tipos de la tabla de ``events.md`` §3 que van a la consola (los ``ops.*``
    son del admin)."""
    text = EVENTS_MD.read_text(encoding="utf-8")
    section = re.search(r"^## 3\..*?$(.*?)^### 3\.1", text, re.M | re.S)
    assert section
    kinds: set[str] = set()
    for row in re.finditer(r"^\|([^|]+)\|", section.group(1), re.M):
        kinds.update(re.findall(r"`([a-z_.]+)`", row.group(1)))
    return {k for k in kinds if not k.startswith("ops.")}


def test_every_new_kind_of_the_spec_is_a_kind_with_a_link() -> None:
    kinds = _spec_kinds()
    assert len(kinds) >= 20, kinds
    known = {k.value for k in NotificationKind}
    assert not kinds - known, f"tipos sin ``NotificationKind``: {sorted(kinds - known)}"
    assert not kinds - set(LINKS), f"avisos sin enlace: {sorted(kinds - set(LINKS))}"


def test_the_link_fills_client_agent_and_channel_and_never_breaks() -> None:
    assert link_for("client.wallet.empty", "cultor", {}) == "/clients/cultor?assign=1"
    assert (
        link_for("agent.cap.reached", "cultor", {"agent_id": "a1"})
        == "/clients/cultor/agents/a1?tab=advanced"
    )
    assert link_for("channel.problem", "cultor", {"channel_id": "c1"}) == (
        "/clients/cultor/channels/c1"
    )
    assert link_for("channel.problem", "cultor", {}) == "/clients/cultor", "sin canal, el cliente"
    assert link_for("client.wallet.low", None, {}) is None, "sin cliente no enlaza"
    assert link_for("build.budget.exhausted", None, {}) == "/usage"
    assert link_for("partner.something_old", "cultor", {}) is None


def test_the_client_goes_to_its_own_console() -> None:
    """events.md §3.1: lo que ve la persona del cliente enlaza a la lite, nunca
    a ``/clients/…`` (que es del partner)."""
    assert link_for("client.wallet.empty", "cultor", {}, audience="client") == "/usage"
    assert link_for("agent.paused", "cultor", {"agent_id": "a1"}, audience="client") == "/agentes"
    assert link_for("channel.problem", "cultor", {"channel_id": "c1"}, audience="client") == (
        "/agentes"
    )
    assert link_for("inbox.waiting", None, {"conversation_id": "k1"}, audience="client") == (
        "/inbox?c=k1"
    )
    assert link_for("client.business_changed", "cultor", {}, audience="client") is None
    assert all(not path.startswith("/clients") for path in LITE_LINKS.values())


def test_a_connector_to_authorize_again_opens_its_own_page() -> None:
    """La página de cada conexión (T129): el aviso lleva a ella; sin su id, al
    cliente."""
    assert link_for("integration.reauth_required", "cultor", {"connection_id": "k1"}) == (
        "/clients/cultor/integrations/k1"
    )
    assert link_for("integration.reauth_required", "cultor", {}) == "/clients/cultor"
