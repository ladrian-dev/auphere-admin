"""Draft handling shared by the agent lanes of the console (CP-11/13/14).

The console never edits an ACTIVE version in place: every structured
editor (settings, tools, skills, prompt) writes onto ONE staged draft —
created on first write as a full copy of the active version (prompt,
channels, tools, policies, runtime capabilities), reused on subsequent
writes — and publishing (CP-12) is what makes it live. That keeps the
partner's mental model at "edit → one draft → publish", and the runtime's
guarantees (one ACTIVE, atomic rollback, audit rows) untouched.

Spec 047 (requisito 3): "the draft" is THE staged version of the agent —
there is at most one, the database enforces it. Every write opens it with
:func:`ensure_draft` (which locks the agent and, with ``If-Match``, checks
the revision the writer read) and closes it with :func:`draft_written`
(which moves the revision and says which fields changed).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.db.models import AgentConfig, AgentConfigStatus
from nexus_api.services.agent_audience import audience_of
from nexus_api.services.agent_config_service import AgentConfigService, DraftWrite
from nexus_api.services.agent_console_policy import with_disclosure_default
from nexus_api.services.agent_payment_review import reviewers_of

from .deps import ClientScope


@dataclass(frozen=True)
class DraftView:
    """What the editors show: the version being edited + the active one."""

    target: AgentConfig | None
    active: AgentConfig | None
    draft: AgentConfig | None

    @property
    def has_draft(self) -> bool:
        return self.draft is not None


async def load_view(scope: ClientScope) -> DraftView:
    service = AgentConfigService(scope.session)
    # Spec 030: the versions of the agent the route acts on (the principal
    # without ``?agent=``) — a draft is always one agent's.
    versions = await service.list_versions(agent_id=scope.agent_id)  # newest first
    active = next((v for v in versions if v.status is AgentConfigStatus.ACTIVE), None)
    # Spec 047: the agent's one staged version, whatever its number — a
    # change published at once (the admins of the partner API) can leave the
    # active version with a higher number than the draft still pending.
    draft = next((v for v in versions if v.status is AgentConfigStatus.STAGED), None)
    return DraftView(target=draft or active, active=active, draft=draft)


#: ``session.info`` key of the writes :func:`ensure_draft` opened and
#: :func:`draft_written` closes — one per draft, inside one transaction.
_OPEN_WRITES = "nexus.console.draft_writes"


def _open_writes(session: AsyncSession) -> dict[Any, DraftWrite]:
    writes: dict[Any, DraftWrite] = session.info.setdefault(_OPEN_WRITES, {})
    return writes


async def ensure_draft(
    scope: ClientScope, *, expected_revision: int | None = None, disclosure_default: bool = True
) -> tuple[AgentConfig, bool]:
    """Return ``(draft, created)``: the agent's draft, or a new one that
    copies the active version — or the last saved one — with every field
    (or an empty scaffold when there is none).

    Locks the agent until the transaction ends, so two writers queue. With
    ``expected_revision`` (the ``If-Match`` of the request) a stale one gets
    ``DraftRevisionConflict``. A draft written from the console always
    carries an AI-disclosure decision (CP-31). Close the write with
    :func:`draft_written` once the fields are set."""
    actor = scope.principal.actor
    write = await AgentConfigService(scope.session).open_draft(
        actor=actor,
        agent_id=scope.agent_id,
        expected_revision=expected_revision,
        # Spec 047: un borrador escrito como AgentSpec trae su propia decisión
        # del aviso de IA (16.6), y sin ella queda sin decidir.
        prepare_policies=(
            (lambda policies: with_disclosure_default(policies, actor=actor))
            if disclosure_default
            else None
        ),
    )
    _open_writes(scope.session)[write.draft.id] = write
    return write.draft, write.created


async def draft_written(scope: ClientScope, draft: AgentConfig) -> int | None:
    """Close the write :func:`ensure_draft` opened on ``draft``: the revision
    moves and the audit row says which fields changed. ``None`` when the
    write changed nothing."""
    write = _open_writes(scope.session).pop(draft.id, None)
    if write is None:  # pragma: no cover - a programming error, not an input
        raise RuntimeError("draft_written() without ensure_draft()")
    # Spec 047 (T128): connector tools put on the list by today's screens keep
    # working — they get their activation (not on the new console).
    from nexus_api.services.activations import ensure_activations_for_tools

    await ensure_activations_for_tools(
        scope.session,
        tenant_id=scope.tenant.id,
        agent_id=draft.agent_id,
        tools=list(draft.tools or []),
        actor=scope.principal.actor,
    )
    return await AgentConfigService(scope.session).finish_draft(write, actor=scope.principal.actor)


__all__ = ["DraftView", "draft_written", "ensure_draft", "load_view"]


# ── qué cambia el borrador (spec 017, R3.1/R3.2) ───────────────────────
#
# Dos lecturas derivadas, sin estado nuevo: `draft_screens` dice QUÉ
# pantallas de la ficha difieren, para que la pestaña pueda llevar un
# punto; `draft_diff` dice EN QUÉ difieren, en claves estables. Las frases
# las pone la consola: la API no sabe en qué idioma mira el partner.

DraftScreen = Literal["settings", "capabilities", "knowledge", "prompt"]
SCREEN_ORDER: tuple[DraftScreen, ...] = ("settings", "capabilities", "knowledge", "prompt")


def _console_policy(cfg: AgentConfig | None) -> dict[str, object]:
    if cfg is None:
        return {}
    raw = (cfg.policies or {}).get("console")
    return dict(raw) if isinstance(raw, dict) else {}


def _capabilities(cfg: AgentConfig | None) -> set[tuple[str, str]]:
    """Lo que el agente puede hacer, herramientas y habilidades juntas:
    para el partner son la misma pregunta («¿qué sabe hacer?»)."""
    if cfg is None:
        return set()
    caps = {(name, "tool") for name in (cfg.tools or [])}
    for skill in cfg.runtime_skills or []:
        # Las entradas guardan `skill_id`, no `name`: leer `name` hacía que
        # encender una habilidad no contara como cambio y la barra de
        # borrador no se enterara. `name` se acepta por si una fila antigua
        # lo trae.
        key = skill.get("skill_id") or skill.get("name")
        if key:
            caps.add((str(key), "skill"))
    return caps


def _policy_defaults() -> dict[str, object]:
    from nexus_api.services.agent_console_policy import ConsolePolicy

    return ConsolePolicy().model_dump(mode="json")


def settings_changes(active: AgentConfig | None, draft: AgentConfig) -> list[dict[str, object]]:
    """Una fila por campo de `policies.console` que difiere. `schema_version`
    no es un ajuste: es fontanería y no se enseña.

    Y un campo que **no existía** en la activa y en el borrador trae
    exactamente el valor por defecto tampoco es un cambio: el formulario de
    ajustes escribe la política entera, así que tocar el nombre del agente
    hacía aparecer seis filas con «Antes: —». El partner no podía distinguir
    lo que decidió él de lo que rellenó el formulario solo, que es justo lo
    que la hoja de revisión existe para evitar. Si la activa SÍ tenía un
    valor y el borrador lo devuelve al de por defecto, eso es una decisión y
    se enseña.
    """
    before, after = _console_policy(active), _console_policy(draft)
    defaults = _policy_defaults()
    rows: list[dict[str, object]] = []
    for field in sorted(set(before) | set(after)):
        if field == "schema_version":
            continue
        if before.get(field) == after.get(field):
            continue
        if field not in before and after.get(field) == defaults.get(field):
            continue
        rows.append({"field": field, "before": before.get(field), "after": after.get(field)})
    # Spec 024: «A quién responde» lives in ``admin_access``, not in
    # ``policies.console``; the review sheet still has to show it, or the
    # partner would publish a list without seeing it in the diff.
    audience_before, audience_after = _audience_row(active), _audience_row(draft)
    if audience_before != audience_after and not (
        active is None and audience_after["mode"] == "everyone"
    ):
        rows.append({"field": "audience", "before": audience_before, "after": audience_after})
    # Spec 025: the payment reviewers live in ``policies.payment_review``.
    reviewers_before = len(reviewers_of(active.policies if active else None))
    reviewers_after = len(reviewers_of(draft.policies))
    if reviewers_before != reviewers_after or _reviewer_phones(active) != _reviewer_phones(draft):
        rows.append(
            {
                "field": "payment_review",
                "before": {"count": reviewers_before},
                "after": {"count": reviewers_after},
            }
        )
    return rows


def _reviewer_phones(cfg: AgentConfig | None) -> list[str]:
    return [r.phone for r in reviewers_of(cfg.policies if cfg else None)]


def _audience_row(cfg: AgentConfig | None) -> dict[str, object]:
    audience = audience_of(cfg.policies if cfg else None)
    return {"mode": audience.mode, "count": len(audience.numbers)}


def capability_changes(active: AgentConfig | None, draft: AgentConfig) -> list[dict[str, object]]:
    before, after = _capabilities(active), _capabilities(draft)
    rows: list[dict[str, object]] = []
    for name, kind in sorted(after - before):
        rows.append(
            {"name": name, "kind": kind, "change": "enabled", "before": False, "after": True}
        )
    for name, kind in sorted(before - after):
        rows.append(
            {"name": name, "kind": kind, "change": "disabled", "before": True, "after": False}
        )
    return rows


def prompt_change(active: AgentConfig | None, draft: AgentConfig) -> dict[str, str]:
    return {
        "before": active.system_prompt_rendered if active else "",
        "after": draft.system_prompt_rendered,
    }


def draft_screens(view: DraftView) -> list[DraftScreen]:
    """Las pantallas de la ficha en las que el borrador difiere de la activa,
    en el orden en que se leen. Vacío sin borrador."""
    if view.draft is None:
        return []
    screens: list[DraftScreen] = []
    if settings_changes(view.active, view.draft):
        screens.append("settings")
    if capability_changes(view.active, view.draft):
        screens.append("capabilities")
    # Los documentos de conocimiento no se versionan con el agente, así que
    # entre borrador y activa no hay nada que comparar todavía.
    if prompt_change(view.active, view.draft)["before"] != view.draft.system_prompt_rendered:
        screens.append("prompt")
    return screens


def draft_diff(view: DraftView) -> dict[str, object]:
    """El borrador contra la activa, en claves. Llamar solo con borrador."""
    assert view.draft is not None
    return {
        "version": {
            "draft": view.draft.version,
            "active": view.active.version if view.active else None,
        },
        "settings": settings_changes(view.active, view.draft),
        "capabilities": capability_changes(view.active, view.draft),
        "knowledge": [],
        "prompt": prompt_change(view.active, view.draft),
    }
