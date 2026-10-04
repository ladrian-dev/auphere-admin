"""Spec 029: every audit sentence complete, in the partner's words.

``console_audit_vocabulary`` holds one template per action, and before this
module ``summarise()`` filled only half of the placeholders those templates
use: 37 of the first 50 rows of a real partner read «cambió la capacidad ?
de Lola Mento: ?.». Here each placeholder gets a value built from what the
writer stored in ``after_json``/``before_json``, translated when it is a
code (a status, a role, a plan) and resolved to a name when it is a
reference (a client ref, a capability key, a model id).

``test_console_audit_words`` reads every template in the vocabulary and
fails if one of them uses a placeholder this module does not fill, so a new
action cannot bring the «?» back.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from datetime import datetime
from typing import Any

from nexus_api.api.console.capability_names import business_name
from nexus_api.core.respond_catalog import RESPOND_MODELS

#: Every placeholder this module fills. The test compares it with the
#: vocabulary.
PLACEHOLDERS = frozenset(
    {
        "actor",
        "client",
        "v",
        "status",
        "email",
        "role",
        "key",
        "channel",
        "template",
        "document",
        "cap",
        "percent",
        "ticket",
        "topic",
        "amount",
        "from",
        "to",
        "capability",
        "change",
        "connector",
        "model",
        "partner",
        "credit_expires_at",
        "tier",
        "category",
        "from_status",
        "to_status",
        "executable",
        "machine",
        "mode",
        "ceiling",
        "teammate",
        "reason",
        # 0142: the actions written outside the console.
        "account",
        "cost",
        "count",
        "day",
        "from_quality",
        "to_quality",
        "models",
        "phone",
        "service",
        "threshold",
        "tool",
        "wa_mode",
        "when",
    }
)

_Words = dict[str, dict[str, str]]

STATUS: _Words = {
    "active": {"es": "activo", "en": "active"},
    "connected": {"es": "conectado", "en": "connected"},
    "disconnected": {"es": "desconectado", "en": "disconnected"},
    "needs_reauth": {"es": "pide volver a iniciar sesión", "en": "needs signing in again"},
    "degraded": {"es": "degradado", "en": "degraded"},
    "indexed": {"es": "leído", "en": "read"},
    "failed": {"es": "con error", "en": "failed"},
    "paused": {"es": "en pausa", "en": "paused"},
    "archived": {"es": "archivado", "en": "archived"},
    "provisioning": {"es": "sin activar", "en": "not activated"},
    "suspended": {"es": "suspendido", "en": "suspended"},
    "open": {"es": "abierto", "en": "open"},
    "pending": {"es": "pendiente", "en": "pending"},
    "closed": {"es": "cerrado", "en": "closed"},
}

ROLE: _Words = {
    "owner": {"es": "propietario", "en": "owner"},
    "admin": {"es": "administrador", "en": "admin"},
    "builder": {"es": "constructor", "en": "builder"},
    "analyst": {"es": "analista", "en": "analyst"},
    "billing": {"es": "facturación", "en": "billing"},
    # The role of a WhatsApp number (``console.channel.role``).
    "agent": {"es": "agente", "en": "agent"},
    "notifications": {"es": "avisos", "en": "notifications"},
}

TIER: _Words = {
    "free": {"es": "Free", "en": "Free"},
    "pro": {"es": "Pro", "en": "Pro"},
    "team": {"es": "Team", "en": "Team"},
    "business": {"es": "Business", "en": "Business"},
}

EXEC_MODE: _Words = {
    "ask": {"es": "preguntar", "en": "ask"},
    "always": {"es": "permitir siempre", "en": "always allow"},
    "never": {"es": "nunca", "en": "never"},
}

REASON: _Words = {
    "archivada_consola": {"es": "desde la consola", "en": "from the console"},
    "principal_not_an_account": {"es": "no era una cuenta", "en": "not an account"},
    "session_not_recently_confirmed": {"es": "sesión sin confirmar", "en": "session not confirmed"},
    "machine_cap_reached": {"es": "límite de máquinas", "en": "machine limit reached"},
    "vanished": {"es": "la máquina desapareció", "en": "the machine vanished"},
}

TICKET_CATEGORY: _Words = {
    "help": {"es": "ayuda", "en": "help"},
    "capability": {"es": "capacidad", "en": "capability"},
}

QUALITY: _Words = {
    "GREEN": {"es": "alta", "en": "high"},
    "YELLOW": {"es": "media", "en": "medium"},
    "RED": {"es": "baja", "en": "low"},
}

WA_MODE: _Words = {
    "coexistence": {"es": "en coexistencia con la app", "en": "alongside the app"},
    "cloud_api": {"es": "con la API de WhatsApp", "en": "through the WhatsApp API"},
}

CAPABILITY_MODE: _Words = {
    "always": {"es": "siempre permitida", "en": "always allowed"},
    "blocked": {"es": "bloqueada", "en": "blocked"},
    "needs_approval": {"es": "pide aprobación", "en": "needs approval"},
    "default": {"es": "como viene por defecto", "en": "back to default"},
}

_FALLBACK: dict[str, dict[str, str]] = {
    "client": {"es": "un cliente", "en": "a client"},
    "document": {"es": "un documento", "en": "a document"},
    "someone": {"es": "alguien", "en": "someone"},
    "no_cap": {"es": "sin tope", "en": "no cap"},
    "cap": {"es": "tope de {n} mensajes", "en": "cap of {n} messages"},
    "all": {"es": "todas", "en": "all"},
    "enabled": {"es": "activada", "en": "enabled"},
    "disabled": {"es": "desactivada", "en": "disabled"},
    "and": {"es": " y ", "en": " and "},
    "changed": {"es": "cambiada", "en": "changed"},
    "unknown": {"es": "sin dato", "en": "not recorded"},
}

_MODELS: dict[str, str] = dict(RESPOND_MODELS)
_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)


def word(table: _Words, code: Any, lang: str) -> str:
    """A code in the partner's language; an unknown code shows as itself,
    which is still better than «?» because it says something."""
    if code is None or code == "":
        return _FALLBACK["unknown"][lang]
    entry = table.get(str(code))
    return entry[lang] if entry else str(code)


def _say(key: str, lang: str) -> str:
    return _FALLBACK[key][lang]


def _number(n: int, lang: str) -> str:
    # Spanish keeps four-digit numbers ungrouped (RAE), as ``format_usd`` does.
    if lang == "es":
        return f"{n:,}".replace(",", ".") if n >= 10_000 else str(n)
    return f"{n:,}"


def _date(value: Any, lang: str) -> str:
    try:
        d = datetime.fromisoformat(str(value))
    except ValueError:
        return _say("unknown", lang)
    return d.strftime("%d/%m/%Y") if lang == "es" else d.strftime("%Y-%m-%d")


def _client_ref(ref: Any, names_by_ref: Mapping[str, str], lang: str) -> str:
    if not ref:
        return _say("client", lang)
    return names_by_ref.get(str(ref), str(ref))


def _capability(after: dict[str, Any], lang: str) -> str:
    key = after.get("key")
    if not key:
        return _say("unknown", lang)
    name = (
        business_name(str(key), "skill", lang)
        if after.get("kind") == "skill"
        else business_name(str(key), "tool", lang)
    )
    return f"«{name}»"


def _change(after: dict[str, Any], lang: str) -> str:
    parts: list[str] = []
    if after.get("enabled") is True:
        parts.append(_say("enabled", lang))
    elif after.get("enabled") is False:
        parts.append(_say("disabled", lang))
    if after.get("mode"):
        parts.append(word(CAPABILITY_MODE, after["mode"], lang))
    return _say("and", lang).join(parts) if parts else _say("changed", lang)


def _model(model_id: Any, lang: str) -> str:
    if not model_id:
        return _say("unknown", lang)
    return _MODELS.get(str(model_id), str(model_id).rsplit("/", 1)[-1])


def _cap(after: dict[str, Any], lang: str) -> str:
    cap = after.get("cap")
    if isinstance(cap, int) and cap > 0:
        return _say("cap", lang).format(n=_number(cap, lang))
    return _say("no_cap", lang)


def _executable(value: Any, lang: str) -> str:
    if value == "*":
        return _say("all", lang)
    return str(value) if value else _say("unknown", lang)


def _document(after: dict[str, Any], before: dict[str, Any], lang: str) -> str:
    """QA-21: knowledge rows must not show a raw uuid as the document name."""
    raw = (
        after.get("filename")
        or after.get("title")
        or before.get("filename")
        or after.get("document_id")
    )
    if raw is None or _UUID_RE.match(str(raw).strip()):
        return _say("document", lang)
    return str(raw)


def _target_tail(target: str, prefix: str) -> str | None:
    return target.removeprefix(prefix) if target.startswith(prefix) else None


def _connector(after: dict[str, Any], target: str, names: Mapping[str, str], lang: str) -> str:
    """Connector rows keep the slug in the target (``connector:<slug>``),
    in ``connector_slug`` or, for pause and resume, in ``slug``."""
    slug = _target_tail(target, "connector:") or after.get("connector_slug") or after.get("slug")
    return names.get(str(slug), str(slug)) if slug else _say("unknown", lang)


def _tool(target: str, lang: str) -> str:
    name = _target_tail(target, "tool:")
    return f"«{business_name(name, 'tool', lang)}»" if name else _say("unknown", lang)


def _usd(value: Any, lang: str) -> str:
    from nexus_api.billing.pricing import format_usd

    try:
        return format_usd(round(float(value) * 100), lang)
    except (TypeError, ValueError):
        return _say("unknown", lang)


def _when(value: Any, lang: str) -> str:
    try:
        d = datetime.fromisoformat(str(value))
    except ValueError:
        return _say("unknown", lang)
    return d.strftime("%d/%m/%Y %H:%M") if lang == "es" else d.strftime("%Y-%m-%d %H:%M")


def _count(after: dict[str, Any]) -> int:
    for key in ("added", "tools_added"):
        if isinstance(after.get(key), list):
            return len(after[key])
    return 0


class Safe(dict[str, Any]):
    """``str.format_map`` helper: a placeholder nobody fills renders as
    ``?`` instead of raising, so a vocabulary typo never 500s the page.
    The test keeps that from happening with the seeded vocabulary."""

    def __missing__(self, key: str) -> str:
        return "?"


def values(
    *,
    after: dict[str, Any],
    before: dict[str, Any],
    actor: str,
    client_name: str | None,
    lang: str,
    names_by_ref: Mapping[str, str],
    connector_names: Mapping[str, str],
    partner_name: str | None,
    amount: str,
    target: str = "",
) -> Safe:
    """Every placeholder of the vocabulary, filled for one row."""
    role = after.get("role")
    return Safe(
        actor=actor,
        client=client_name or _client_ref(after.get("client_ref"), names_by_ref, lang),
        v=after.get("version", before.get("version", "?")),
        status=word(STATUS, after.get("status"), lang),
        email=after.get("email", before.get("email")) or _say("someone", lang),
        role=word(ROLE, role, lang) if role else word(ROLE, before.get("role"), lang),
        key=after.get("prefix_snippet", before.get("prefix_snippet")) or _say("unknown", lang),
        # ``console.channel.role`` keeps the phone as ``identifier``.
        channel=(
            after.get("channel")
            or after.get("provider_identifier")
            or after.get("identifier")
            or before.get("channel")
            or _say("unknown", lang)
        ),
        template=after.get("name")
        or after.get("template")
        or after.get("template_name")
        or before.get("name")
        or _say("unknown", lang),
        document=_document(after, before, lang),
        cap=_cap(after, lang),
        percent=after.get("percent", "?"),
        ticket=after.get("ticket_ref") or _say("unknown", lang),
        topic=after.get("topic") or _say("unknown", lang),
        category=word(TICKET_CATEGORY, after.get("category"), lang),
        amount=amount,
        capability=_capability(after, lang),
        change=_change(after, lang),
        connector=_connector(after, target, connector_names, lang),
        model=_model(after.get("model_id"), lang),
        partner=partner_name or _say("unknown", lang),
        credit_expires_at=_date(after.get("credit_expires_at"), lang),
        tier=word(TIER, after.get("tier"), lang),
        from_status=word(STATUS, before.get("status"), lang),
        to_status=word(STATUS, after.get("status"), lang),
        executable=_executable(after.get("executable"), lang),
        machine=after.get("machine") or after.get("hostname") or _say("unknown", lang),
        mode=word(EXEC_MODE, after.get("mode"), lang),
        ceiling=word(EXEC_MODE, after.get("ceiling"), lang),
        teammate=after.get("teammate") or _say("unknown", lang),
        reason=word(REASON, after.get("reason"), lang),
        account=after.get("display_name") or _say("unknown", lang),
        cost=_usd(after.get("cost_usd_total", after.get("spent_usd")), lang),
        threshold=_usd(after.get("threshold_usd", after.get("limit_usd")), lang),
        day=_date(after.get("day"), lang),
        count=_count(after),
        from_quality=word(QUALITY, str(before.get("quality_rating") or "").upper() or None, lang),
        to_quality=word(QUALITY, str(after.get("quality_rating") or "").upper() or None, lang),
        models=", ".join(_model(m, lang) for m in after.get("model_ids") or [])
        or _say("unknown", lang),
        phone=(
            after.get("display_phone_number")
            or after.get("phone_e164")
            or before.get("phone_e164")
            or _target_tail(target, "auphere_channel:")
            or _say("unknown", lang)
        ),
        service=after.get("service") or _say("unknown", lang),
        when=_when(after.get("starts_at"), lang),
        tool=_tool(target, lang),
        wa_mode=word(WA_MODE, after.get("mode"), lang),
        **{
            "from": _client_ref(after.get("from"), names_by_ref, lang),
            "to": _client_ref(after.get("to"), names_by_ref, lang),
        },
    )
