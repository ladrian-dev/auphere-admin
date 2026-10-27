"""AgentConfigService — orchestrates AgentConfigRepository + AuditRepository
+ ToolCatalogRepository, applying validation rules from
architecture/agent-assembly.md "Validaciones pre-promote".

Spec 047 (requisito 3): **one draft per agent**. Every writer — the console,
the admin, the partner API, the Companion through the console, connectors,
scripts — writes into that draft through this service, and every write that
changes it moves ``agents.draft_revision`` and leaves an ``agent_config.*``
audit row that says which fields it touched. That row is what a stale writer
is shown (``changes_since``): «there are newer changes by Luis, here».
"""

from __future__ import annotations

import decimal
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

import sqlalchemy as sa
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.errors import AgentConfigConflict, UnknownAgent
from nexus_api.db.models import AgentConfig, AgentConfigStatus, AuditLog, ToolStatus
from nexus_api.repositories import (
    AgentConfigRepository,
    AuditRepository,
    ToolCatalogRepository,
)
from nexus_api.services.agent_console_policy import ConsolePolicy


class DraftRevisionConflict(AgentConfigConflict):
    """``If-Match`` names a revision of the draft that is no longer the
    current one: somebody wrote in between (R3.3)."""

    def __init__(self, *, agent_id: uuid.UUID, expected: int, current: int) -> None:
        super().__init__(f"the draft of agent {agent_id} is at revision {current}, not {expected}")
        self.agent_id = agent_id
        self.expected = expected
        self.current = current


class NoDraft(AgentConfigConflict):
    """The agent has no draft to discard."""


ChangeKind = Literal["edit", "publish", "rollback", "discard"]

#: The audit actions that move an agent's draft, and what each one was.
DRAFT_EVENTS: dict[str, ChangeKind] = {
    "agent_config.stage": "edit",
    "agent_config.promote": "publish",
    "agent_config.rollback": "rollback",
    "agent_config.discard": "discard",
}


@dataclass(frozen=True)
class DraftChange:
    """One write on an agent's draft, as a stale writer is shown it."""

    revision: int
    kind: ChangeKind
    actor: str
    at: datetime
    fields: list[str]


@dataclass
class DraftWrite:
    """An open write on the agent's draft: the draft, whether this write
    created it, and what it was before (to say what the write changed).
    Close it with :meth:`AgentConfigService.finish_draft`."""

    draft: AgentConfig
    created: bool
    before: dict[str, Any]


# ── what a version is made of, in keys that say what changed ───────────

_RUNTIME = (
    "runtime_memory_tool",
    "runtime_outcome_grader",
    "runtime_mcp_connector",
    "runtime_mcp_servers",
    "grader_mode",
    "grader_sample_rate",
)
_MISSING = object()


def _plain(value: Any) -> Any:
    return str(value) if isinstance(value, decimal.Decimal) else value


def _console_sections(raw: Any) -> dict[str, Any]:
    """``policies.console`` read through ``ConsolePolicy``: a section the form
    fills with its default is the same as one that is not there, so saving
    the name does not read as six changes. Unreadable → as it is."""
    try:
        parsed = ConsolePolicy.model_validate(raw if isinstance(raw, dict) else {})
    except ValidationError:
        return dict(raw) if isinstance(raw, dict) else {}
    out = parsed.model_dump(mode="json")
    out.pop("schema_version", None)
    return out


def draft_fields(cfg: AgentConfig | None) -> dict[str, Any]:
    """A version as stable keys, to tell which of them a write changed.

    Each section of the settings is a key of its own (``settings.tone``…);
    who the agent answers (``admin_access``) and who reviews payments are
    ``audience`` and ``payment_review``, the screen's words for them; the
    other platform keys of ``policies`` go together as ``policies``."""
    if cfg is None:
        return {}
    policies = dict(cfg.policies or {})
    console = policies.pop("console", None)
    out: dict[str, Any] = {
        "system_prompt": cfg.system_prompt_rendered or "",
        "tools": list(cfg.tools or []),
        "skills": [dict(s) for s in cfg.runtime_skills or []],
        "channels": list(cfg.channels or []),
        "audience": policies.pop("admin_access", None),
        "payment_review": policies.pop("payment_review", None),
        "policies": policies,
        "seed_template_ref": cfg.seed_template_ref,
        "kg_schema_id": str(cfg.kg_schema_id) if cfg.kg_schema_id else None,
        "runtime": {name: _plain(getattr(cfg, name)) for name in _RUNTIME},
    }
    for key, value in _console_sections(console).items():
        out[f"settings.{key}"] = value
    return out


def changed_fields(before: dict[str, Any], after: dict[str, Any]) -> list[str]:
    """The keys of :func:`draft_fields` whose value differs, sorted."""
    return sorted(
        key for key in {*before, *after} if before.get(key, _MISSING) != after.get(key, _MISSING)
    )


def _merge_value(base: Any, draft: Any, written: Any) -> Any:
    """Three-way: what the writer left as it was in ``base`` keeps the draft's."""
    return draft if written == base else written


def _merge_policies(
    base: dict[str, Any], draft: dict[str, Any], written: dict[str, Any]
) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key in sorted({*base, *draft, *written}):
        value = _merge_value(
            base.get(key, _MISSING), draft.get(key, _MISSING), written.get(key, _MISSING)
        )
        if value is not _MISSING:
            out[key] = value
    return out


class AgentConfigService:
    def __init__(self, session: AsyncSession) -> None:
        self.session = session
        self.configs = AgentConfigRepository(session)
        self.audit = AuditRepository(session)
        self.tools = ToolCatalogRepository(session)

    # Spec 030: every read and write names an agent or, without one, acts on
    # the client's principal agent — what every caller meant before agents.
    async def list_versions(self, *, agent_id: uuid.UUID | None = None) -> list[AgentConfig]:
        return list(await self.configs.list_all(agent_id=agent_id))

    async def get_active(self, *, agent_id: uuid.UUID | None = None) -> AgentConfig | None:
        return await self.configs.get_active(agent_id=agent_id)

    async def get_draft(self, *, agent_id: uuid.UUID | None = None) -> AgentConfig | None:
        """Spec 047: the agent's one draft, or ``None``."""
        return await self.configs.get_draft(agent_id=agent_id)

    async def draft_revision(self, agent_id: uuid.UUID) -> int:
        revision = await self.configs.draft_revision(agent_id)
        if revision is None:
            raise UnknownAgent(f"agent {agent_id} is not an agent of this tenant")
        return revision

    async def _active_of_version(self, version: int) -> AgentConfig | None:
        """The active version of the agent that ``version`` belongs to — what a
        promotion or a rollback of ``version`` replaces."""
        target = await self.configs.get_by_version(version)
        if target is None:
            return None
        return await self.configs.get_active(agent_id=target.agent_id)

    # ── spec 047: the one draft ─────────────────────────────────────────

    async def lock_draft(self, agent_id: uuid.UUID, *, expected: int | None) -> int:
        """Lock the agent's draft for this transaction and return its
        revision. With ``expected`` (the ``If-Match`` the writer sent), a
        different revision raises :class:`DraftRevisionConflict`."""
        current = await self.configs.lock_draft_revision(agent_id)
        if current is None:
            raise UnknownAgent(f"agent {agent_id} is not an agent of this tenant")
        if expected is not None and expected != current:
            raise DraftRevisionConflict(agent_id=agent_id, expected=expected, current=current)
        return current

    async def open_draft(
        self,
        *,
        actor: str,
        agent_id: uuid.UUID | None = None,
        expected_revision: int | None = None,
        prepare_policies: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    ) -> DraftWrite:
        """The agent's draft, ready to be written: the one it has, or a new one
        that copies the active version — or the last saved one — with every
        field (R3.2), or an empty scaffold when the agent has no version.

        ``prepare_policies`` runs on the policies of the draft before the
        write (the console uses it for the AI-disclosure default). The agent
        stays locked until the transaction ends; close the write with
        :meth:`finish_draft`."""
        agent = await self.configs.agent_or_principal(agent_id)
        if agent is not None:
            await self.lock_draft(agent, expected=expected_revision)
            draft = await self.configs.get_draft(agent_id=agent)
            if draft is not None:
                before = draft_fields(draft)
                if prepare_policies is not None:
                    draft.policies = prepare_policies(dict(draft.policies or {}))
                return DraftWrite(draft=draft, created=False, before=before)
        base = await self.configs.draft_base(agent_id=agent)
        policies = dict(base.policies or {}) if base is not None else {}
        if prepare_policies is not None:
            policies = prepare_policies(policies)
        draft = await self.configs.create_staged(
            system_prompt_rendered=base.system_prompt_rendered if base is not None else "",
            channels=list(base.channels or []) if base is not None else [],
            tools=list(base.tools or []) if base is not None else [],
            policies=policies,
            seed_template_ref=base.seed_template_ref if base is not None else None,
            kg_schema_id=base.kg_schema_id if base is not None else None,
            created_by=actor,
            agent_id=agent,
        )
        return DraftWrite(draft=draft, created=True, before=draft_fields(base))

    async def finish_draft(self, write: DraftWrite, *, actor: str) -> int | None:
        """Close a write: if it created the draft or changed any field, move
        the revision and leave the audit row with the fields it touched.
        Returns the new revision, or ``None`` when nothing changed."""
        draft = write.draft
        await self.session.flush()
        fields = changed_fields(write.before, draft_fields(draft))
        if not fields and not write.created:
            return None
        revision = await self.configs.bump_draft_revision(draft.agent_id)
        await self.audit.record(
            actor=actor,
            action="agent_config.stage",
            target=str(draft.id),
            after={
                "version": draft.version,
                "status": draft.status.value,
                "agent": str(draft.agent_id),
                "number": draft.agent_version_number,
                "revision": revision,
                "created": write.created,
                "fields": fields,
            },
        )
        return revision

    async def discard_draft(
        self, *, actor: str, agent_id: uuid.UUID, expected_revision: int | None
    ) -> AgentConfig:
        """Throw the draft away (R3.5): the agent goes back to its active
        version, which nobody touches. The draft is archived, not deleted."""
        await self.lock_draft(agent_id, expected=expected_revision)
        draft = await self.configs.get_draft(agent_id=agent_id)
        if draft is None:
            raise NoDraft(f"agent {agent_id} has no draft")
        await self.configs.archive_draft(draft)
        revision = await self.configs.bump_draft_revision(agent_id)
        await self.audit.record(
            actor=actor,
            action="agent_config.discard",
            target=str(draft.id),
            after={
                "version": draft.version,
                "agent": str(agent_id),
                "number": draft.agent_version_number,
                "revision": revision,
                "fields": [],
            },
        )
        return draft

    async def changes_since(self, agent_id: uuid.UUID, revision: int) -> list[DraftChange]:
        """What happened to the agent's draft after ``revision``, oldest first:
        who, when, and which fields. It is what the 412 shows (R3.3)."""
        rev = AuditLog.after_json["revision"].astext.cast(sa.Integer)
        rows = (
            await self.session.execute(
                sa.select(AuditLog.action, AuditLog.actor, AuditLog.created_at, AuditLog.after_json)
                .where(
                    AuditLog.action.in_(list(DRAFT_EVENTS)),
                    AuditLog.after_json["agent"].astext == str(agent_id),
                    AuditLog.after_json.has_key("revision"),
                    rev > revision,
                )
                .order_by(rev)
            )
        ).all()
        return [
            DraftChange(
                revision=int((after or {})["revision"]),
                kind=DRAFT_EVENTS[action],
                actor=actor,
                at=at,
                fields=[str(f) for f in (after or {}).get("fields") or []],
            )
            for action, actor, at, after in rows
        ]

    async def stage_new_version(
        self,
        *,
        actor: str,
        system_prompt_rendered: str,
        channels: list[dict[str, Any]],
        tools: list[str],
        policies: dict[str, Any],
        seed_template_ref: str | None = None,
        kg_schema_id: uuid.UUID | None = None,
        agent_id: uuid.UUID | None = None,
        note: str | None = None,
    ) -> AgentConfig:
        """Write a whole configuration into the agent's draft.

        Without a draft, it creates one with this content (R3.2: from the
        active version, whose runtime capabilities it keeps). With one —
        spec 047, R3.1: there is never a second — it writes **into** it,
        three ways: a field the caller left as it is in the active version
        keeps what the draft has, so an operator who edits from the active
        version does not undo what the partner had pending."""
        await self._validate_tools(tools)
        agent = await self.configs.agent_or_principal(agent_id)
        draft: AgentConfig | None = None
        if agent is not None:
            await self.lock_draft(agent, expected=None)
            draft = await self.configs.get_draft(agent_id=agent)
        if draft is None:
            base = await self.configs.draft_base(agent_id=agent)
            if base is None:
                # Spec 047 (T145, requisito 39.2): the agent is being born. It
                # is born in «Automático» when «Automático» can serve it; until
                # then — today, research D44 — on the path of today.
                from nexus_api.services.router_catalog import (
                    default_model_policy,
                    with_model_policy_default,
                )

                policies = with_model_policy_default(
                    policies, await default_model_policy(self.session)
                )
            config = await self.configs.create_staged(
                system_prompt_rendered=system_prompt_rendered,
                channels=channels,
                tools=tools,
                policies=policies,
                seed_template_ref=seed_template_ref,
                kg_schema_id=kg_schema_id,
                created_by=actor,
                agent_id=agent_id,
                note=note,
            )
            await self.finish_draft(
                DraftWrite(draft=config, created=True, before=draft_fields(base)), actor=actor
            )
            return config

        write = DraftWrite(draft=draft, created=False, before=draft_fields(draft))
        active = await self.configs.get_active(agent_id=agent)
        base_cfg = active if active is not None else draft
        draft.system_prompt_rendered = _merge_value(
            base_cfg.system_prompt_rendered, draft.system_prompt_rendered, system_prompt_rendered
        )
        draft.channels = _merge_value(list(base_cfg.channels or []), draft.channels, channels)
        draft.tools = _merge_value(list(base_cfg.tools or []), draft.tools, tools)
        draft.policies = _merge_policies(
            dict(base_cfg.policies or {}), dict(draft.policies or {}), dict(policies or {})
        )
        draft.seed_template_ref = _merge_value(
            base_cfg.seed_template_ref, draft.seed_template_ref, seed_template_ref
        )
        draft.kg_schema_id = _merge_value(base_cfg.kg_schema_id, draft.kg_schema_id, kg_schema_id)
        if note is not None:
            draft.note = note
        await self.finish_draft(write, actor=actor)
        return draft

    async def set_admin_access(
        self,
        *,
        actor: str,
        admin_phones: list[str],
        admins: list[dict[str, Any]] | None = None,
    ) -> AgentConfig:
        """Update the admin whitelist of the ACTIVE config and promote it.

        The whitelist (``policies.admin_access.admin_phones``) is the binary
        access model: a phone on the list can do everything the admin agent
        exposes; one off it gets no reply. Registering/editing admins from
        the partner app therefore clones the active config, swaps only
        ``admin_access``, and promotes — so the change travels through the
        normal STAGED → ACTIVE flow (audit + rollback) without touching the
        prompt/tools identity.

        Deliberately NOT gated by ``Tenant.eval_required``: changing who may
        talk to the agent is not a prompt/behaviour change, so it must not be
        blocked by (or require) an eval run. ``admins`` is optional metadata
        (e.g. ``[{"phone", "name"}]``) kept alongside the list for traceability;
        the runtime gate only ever reads ``admin_phones``.

        Spec 047 (R3.1): with a draft pending, the list is published at once
        **without** that draft (``publish_copy``), and the draft gets the
        same list — publishing it later must not undo it, nor lose anything
        it had.
        """
        active = await self.get_active()
        if active is None:
            raise AgentConfigConflict("tenant has no active agent config to update")

        policies = dict(active.policies or {})
        access = dict(policies.get("admin_access") or {})
        access["admin_only"] = True
        access["admin_phones"] = list(admin_phones)
        if admins is not None:
            access["admins"] = admins
        policies["admin_access"] = access

        await self.lock_draft(active.agent_id, expected=None)
        draft = await self.configs.get_draft(agent_id=active.agent_id)
        if draft is None:
            staged = await self.stage_new_version(
                actor=actor,
                system_prompt_rendered=active.system_prompt_rendered,
                channels=list(active.channels or []),
                tools=list(active.tools or []),
                policies=policies,
                seed_template_ref=active.seed_template_ref,
                kg_schema_id=active.kg_schema_id,
                agent_id=active.agent_id,
            )
            return await self.promote(staged.version, actor=actor)

        published = await self.configs.publish_copy(active, policies=policies, published_by=actor)
        await self.audit.record(
            actor=actor,
            action="agent_config.promote",
            target=str(published.id),
            before={"version": active.version},
            after={
                "version": published.version,
                "agent": str(published.agent_id),
                "number": published.agent_version_number,
            },
        )
        write = DraftWrite(draft=draft, created=False, before=draft_fields(draft))
        draft.policies = {**dict(draft.policies or {}), "admin_access": access}
        await self.finish_draft(write, actor=actor)
        return published

    async def promote(self, version: int, *, actor: str, origin: str | None = None) -> AgentConfig:
        """``origin`` (spec 017 R3.3) says which surface the partner pressed:
        the draft bar or the agent tab. It is audit context, never a
        behaviour switch — promoting is the same act either way.

        Spec 047: promoting the draft ends it, so its revision moves — a tab
        still editing it is told, not left writing into a new one."""
        target = await self.configs.get_by_version(version)
        was_draft = target is not None and target.status is AgentConfigStatus.STAGED
        if target is not None and was_draft:
            await self.lock_draft(target.agent_id, expected=None)
        before = await self._active_of_version(version)
        config = await self.configs.promote(version, promoted_by=actor)
        after: dict[str, Any] = {
            "version": config.version,
            "agent": str(config.agent_id),
            "number": config.agent_version_number,
        }
        if origin is not None:
            after["from"] = origin
        if was_draft:
            after["revision"] = await self.configs.bump_draft_revision(config.agent_id)
            after["fields"] = []
        await self.audit.record(
            actor=actor,
            action="agent_config.promote",
            target=str(config.id),
            before={"version": before.version} if before else None,
            after=after,
        )
        return config

    async def rollback(self, target_version: int, *, actor: str) -> AgentConfig:
        before = await self._active_of_version(target_version)
        if before is not None and before.version == target_version:
            raise AgentConfigConflict(f"version {target_version} is already active")
        target = await self.configs.get_by_version(target_version)
        was_draft = target is not None and target.status is AgentConfigStatus.STAGED
        if target is not None and was_draft:
            await self.lock_draft(target.agent_id, expected=None)
        config = await self.configs.rollback(target_version, promoted_by=actor)
        after: dict[str, Any] = {
            "version": config.version,
            "agent": str(config.agent_id),
            "number": config.agent_version_number,
        }
        if was_draft:
            after["revision"] = await self.configs.bump_draft_revision(config.agent_id)
            after["fields"] = []
        await self.audit.record(
            actor=actor,
            action="agent_config.rollback",
            target=str(config.id),
            before={"version": before.version} if before else None,
            after=after,
        )
        return config

    async def _validate_tools(self, tools: list[str]) -> None:
        if not tools:
            return
        catalog_rows = await self.tools.list_all(include_deprecated=True, include_internal=True)
        catalog = {t.name: t for t in catalog_rows}
        unknown = [t for t in tools if t not in catalog]
        if unknown:
            raise AgentConfigConflict("Tools not in catalog: " + ", ".join(unknown))
        # Bloque E: las tools internas (ej. ``agendapro.*``) NO pueden
        # entrar en la whitelist de un agent_config — solo se invocan vía
        # ``MCPRegistry.dispatch_internal`` desde otros servers. Defense
        # in depth: aunque el operator panel no las ofrezca, este check
        # captura un intento manual.
        internal = [t for t in tools if catalog[t].status == ToolStatus.INTERNAL]
        if internal:
            raise AgentConfigConflict(
                "Internal tools cannot be whitelisted for an agent: " + ", ".join(internal)
            )


__all__ = [
    "DRAFT_EVENTS",
    "AgentConfigService",
    "ChangeKind",
    "DraftChange",
    "DraftRevisionConflict",
    "DraftWrite",
    "NoDraft",
    "changed_fields",
    "draft_fields",
]
