"""La configuración de cada canal — spec 047, T112 y T113 (requisitos 32 y 33;
``contracts/console-api.md`` §5).

Cada número tiene su página: a quién responde, excepciones, escalado, mensaje de
espera y comprobaciones (32.1). Lo que se guarda aquí es del **canal**, no del
agente: dos números del mismo agente pueden responder a gente distinta (32.6).

- **Audiencia** (``channels.audience_mode`` y ``channel_audience_numbers``):
  «Solo mi equipo» exige un número de prueba (32.2); «A todos» admite excepciones
  (32.3) y exige un agente publicado, una bolsa con saldo y que la plantilla del
  agente no sea de solo administradores (32.5, 32.8). Los números se guardan en
  E.164 y sin duplicados (32.4). La puerta del turno la aplica
  ``core.admin_gate.audience_suppresses``.
- **Escalado** (``channel_escalation_recipients``): hasta 10 destinatarios, cada
  uno con su vía (33.1). ``notify_from`` dice de qué número saldrá el aviso por
  WhatsApp: del canal si tiene la plantilla aprobada, si no del de Auphere (33.3).
- **Guardar** sube ``config_revision`` (``If-Match``), deja el antes y el después
  en ``channel_config_changes`` y se puede deshacer durante 10 minutos (32.7).
  Se aplica desde el siguiente mensaje: la puerta lo lee en cada turno.
- **Comprobaciones**: las pruebas al día y el escalado con destinatario avisan
  sin bloquear (32.8).

Los permisos de las personas del equipo (``full`` y ``readonly``) se quedan en el
agente (32.10): aquí no se tocan.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any, Final, Literal

import sqlalchemy as sa
from nexus_channels.whatsapp_meta.phone import to_e164
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.db.models import (
    Agent,
    AgentConfig,
    AgentConfigStatus,
    AuditLog,
    Channel,
    ChannelAudienceNumber,
    ChannelConfigChange,
    ChannelEscalationRecipient,
    ChannelStatus,
    Partner,
    Tenant,
    WhatsAppTemplateStatus,
)

AudienceMode = Literal["unset", "team_only", "everyone"]
Via = Literal["whatsapp", "email", "inbox"]
NotifyFrom = Literal["channel", "auphere"]

UNDO_WINDOW: Final = timedelta(minutes=10)
MAX_RECIPIENTS: Final = 10
MAX_NUMBERS: Final = 200
WAIT_MESSAGE_MAX: Final = 500
#: La plantilla de aviso de escalado; aprobada en el WABA del canal, el aviso
#: sale de ese número (33.3).
ESCALATION_TEMPLATE: Final = "alert_escalation_v1"
_E164 = re.compile(r"^\+[1-9]\d{6,14}$")
_EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


class ChannelConfigError(Exception):
    """Un error con su código de ``contracts/console-api.md`` §9."""

    def __init__(self, code: str, status: int = 409, **extra: Any) -> None:
        super().__init__(code)
        self.code = code
        self.status = status
        self.extra = extra


@dataclass(frozen=True)
class Recipient:
    name: str
    via: Via
    phone_e164: str | None = None
    email: str | None = None
    client_user_id: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "via": self.via,
            "phone_e164": self.phone_e164,
            "email": self.email,
            "client_user_id": self.client_user_id,
        }


@dataclass
class ConfigIn:
    """Lo que la consola manda al guardar."""

    mode: AudienceMode
    test_numbers: list[str] = field(default_factory=list)
    exceptions: list[str] = field(default_factory=list)
    recipients: list[Recipient] = field(default_factory=list)
    summary: bool = True
    wait_message: str | None = None


# ── números ────────────────────────────────────────────────────────────────


def normalize_phone(raw: str) -> str:
    """E.164 o ``invalid_phone`` (32.4)."""
    e164 = to_e164((raw or "").strip())
    if not e164 or not _E164.match(e164):
        raise ChannelConfigError("invalid_phone", 422, value=raw)
    return str(e164)


def normalize_numbers(values: Sequence[str]) -> list[str]:
    """En E.164, sin duplicados y en el orden en que llegaron (32.4)."""
    out: list[str] = []
    for raw in values:
        e164 = normalize_phone(raw)
        if e164 not in out:
            out.append(e164)
    if len(out) > MAX_NUMBERS:
        raise ChannelConfigError("too_many_numbers", 422, limit=MAX_NUMBERS)
    return out


def _recipient(item: Recipient) -> Recipient:
    name = (item.name or "").strip()
    if not name:
        raise ChannelConfigError("recipient_name_required", 422)
    if item.via == "whatsapp":
        if not item.phone_e164:
            raise ChannelConfigError("recipient_phone_required", 422, name=name)
        return Recipient(
            name=name[:80], via="whatsapp", phone_e164=normalize_phone(item.phone_e164)
        )
    if item.via == "email":
        email = (item.email or "").strip().lower()
        if not _EMAIL.match(email):
            raise ChannelConfigError("recipient_email_invalid", 422, name=name)
        return Recipient(name=name[:80], via="email", email=email)
    return Recipient(name=name[:80], via="inbox", client_user_id=item.client_user_id or None)


# ── lectura ────────────────────────────────────────────────────────────────


async def _numbers(session: AsyncSession, channel: Channel) -> dict[str, list[str]]:
    rows = (
        await session.execute(
            sa.select(ChannelAudienceNumber.kind, ChannelAudienceNumber.phone_e164)
            .where(
                ChannelAudienceNumber.tenant_id == channel.tenant_id,
                ChannelAudienceNumber.channel_id == channel.id,
            )
            .order_by(ChannelAudienceNumber.created_at, ChannelAudienceNumber.phone_e164)
        )
    ).all()
    out: dict[str, list[str]] = {"test": [], "exception": []}
    for kind, phone in rows:
        out.setdefault(kind, []).append(phone)
    return out


async def recipients_of(session: AsyncSession, channel_id: uuid.UUID) -> list[Recipient]:
    rows = (
        await session.scalars(
            sa.select(ChannelEscalationRecipient)
            .where(ChannelEscalationRecipient.channel_id == channel_id)
            .order_by(ChannelEscalationRecipient.position, ChannelEscalationRecipient.created_at)
        )
    ).all()
    return [
        Recipient(
            name=r.name,
            via=r.via,  # type: ignore[arg-type]
            phone_e164=r.phone_e164,
            email=r.email,
            client_user_id=r.client_user_id,
        )
        for r in rows
    ]


async def notify_from(session: AsyncSession, channel: Channel) -> NotifyFrom:
    """De qué número sale el aviso por WhatsApp (33.3): el del canal si su WABA
    tiene la plantilla de aviso aprobada; si no, el de Auphere."""
    waba_id = (channel.config or {}).get("waba_id")
    if not waba_id:
        return "auphere"
    approved = await session.scalar(
        sa.select(WhatsAppTemplateStatus.id)
        .where(
            WhatsAppTemplateStatus.waba_id == str(waba_id),
            WhatsAppTemplateStatus.template_name == ESCALATION_TEMPLATE,
            sa.func.upper(WhatsAppTemplateStatus.status) == "APPROVED",
        )
        .limit(1)
    )
    return "channel" if approved is not None else "auphere"


async def read_config(session: AsyncSession, channel: Channel) -> dict[str, Any]:
    """La forma ``config`` del contrato."""
    numbers = await _numbers(session, channel)
    cfg = channel.config or {}
    return {
        "audience": {
            "mode": channel.audience_mode,
            "test_numbers": numbers["test"],
            "exceptions": numbers["exception"],
        },
        "escalation": {
            "recipients": [r.as_dict() for r in await recipients_of(session, channel.id)],
            "summary": bool(cfg.get("escalation_summary", True)),
        },
        "wait_message": cfg.get("wait_message"),
        "notify_from": await notify_from(session, channel),
    }


def _stored(config: Mapping[str, Any]) -> dict[str, Any]:
    """Lo que entra en el historial: todo menos lo que se deriva."""
    return {k: v for k, v in config.items() if k != "notify_from"}


async def gate_audience(session: AsyncSession, channel_id: uuid.UUID) -> dict[str, Any] | None:
    """Lo que la puerta del turno necesita del canal (``admin_gate``):
    ``strict`` es un canal de Meta (WhatsApp, Instagram o Messenger) de un
    partner en la consola nueva. Instagram y Messenger seguían con el
    ``admin_access`` de la versión aunque la página dijera otra cosa (QA
    2026-10-30, INC-08)."""
    channel = await session.get(Channel, channel_id)
    if channel is None:
        return None
    numbers = await _numbers(session, channel)
    return {
        "mode": channel.audience_mode,
        "test": numbers["test"],
        "exception": numbers["exception"],
        "strict": _audience_applies(channel) and await partner_on_v2(session, channel.tenant_id),
    }


def _is_whatsapp(channel: Channel) -> bool:
    kind = channel.type.value if hasattr(channel.type, "value") else str(channel.type)
    return kind == "whatsapp"


#: Los canales donde manda la audiencia de la página del canal.
AUDIENCE_CHANNELS: Final = frozenset({"whatsapp", "instagram", "messenger"})


def _audience_applies(channel: Channel) -> bool:
    kind = channel.type.value if hasattr(channel.type, "value") else str(channel.type)
    return kind in AUDIENCE_CHANNELS


async def partner_on_v2(session: AsyncSession, tenant_id: uuid.UUID) -> bool:
    """El cliente es de un partner con la consola nueva."""
    found = await session.scalar(
        sa.select(Partner.id)
        .join(Tenant, Tenant.partner_id == Partner.id)
        .where(Tenant.id == tenant_id, Partner.console_v2_enabled_at.is_not(None))
        .limit(1)
    )
    if found is not None:
        return True
    found = await session.scalar(
        sa.text(
            "SELECT 1 FROM partner_tenants pt JOIN partners p ON p.id = pt.partner_id "
            "WHERE pt.tenant_id = :t AND p.console_v2_enabled_at IS NOT NULL LIMIT 1"
        ),
        {"t": str(tenant_id)},
    )
    return found is not None


# ── comprobaciones ─────────────────────────────────────────────────────────


async def _agent_of(session: AsyncSession, channel: Channel) -> Agent | None:
    if channel.agent_id is not None:
        return await session.get(Agent, channel.agent_id)
    found: Agent | None = await session.scalar(
        sa.select(Agent)
        .where(Agent.tenant_id == channel.tenant_id, Agent.lifecycle != "archived")
        .order_by(Agent.is_default.desc(), Agent.created_at, Agent.id)
        .limit(1)
    )
    return found


async def _active_version(session: AsyncSession, agent: Agent | None) -> AgentConfig | None:
    if agent is None:
        return None
    found: AgentConfig | None = await session.scalar(
        sa.select(AgentConfig)
        .where(
            AgentConfig.tenant_id == agent.tenant_id,
            AgentConfig.agent_id == agent.id,
            AgentConfig.status == AgentConfigStatus.ACTIVE,
        )
        .order_by(AgentConfig.version.desc())
        .limit(1)
    )
    return found


async def admin_only_template(session: AsyncSession, channel: Channel) -> bool:
    """El agente del canal viene de una plantilla de solo administradores (32.5)."""
    from nexus_api.services.agent_audience import is_locked_template

    version = await _active_version(session, await _agent_of(session, channel))
    if version is None:
        agent = await _agent_of(session, channel)
        if agent is None:
            return False
        version = await session.scalar(
            sa.select(AgentConfig)
            .where(AgentConfig.tenant_id == agent.tenant_id, AgentConfig.agent_id == agent.id)
            .order_by(AgentConfig.version.desc())
            .limit(1)
        )
    return bool(version is not None and is_locked_template(version.seed_template_ref))


async def _bag_has_balance(tenant_id: uuid.UUID) -> bool:
    from nexus_api.metering.wallet import allow_channel_turn

    return await allow_channel_turn(tenant_id)


async def everyone_blockers(session: AsyncSession, channel: Channel) -> list[dict[str, Any]]:
    """Lo que impide «A todos» (32.5, 32.8), cada uno con su arreglo."""
    out: list[dict[str, Any]] = []
    if await admin_only_template(session, channel):
        out.append({"code": "audience_admin_only_template", "fix": None})
    agent = await _agent_of(session, channel)
    if await _active_version(session, agent) is None:
        out.append({"code": "agent_not_published", "fix": "publish_agent"})
    if not await _bag_has_balance(channel.tenant_id):
        out.append({"code": "bag_empty", "fix": "assign_balance"})
    return out


async def checks(session: AsyncSession, channel: Channel) -> list[dict[str, Any]]:
    """Las comprobaciones de la página (32.8). Las de pruebas y escalado avisan
    (``level: warn``); las de «A todos» se enseñan con su arreglo."""
    from nexus_api.services.testing.runs import latest_results, outcome_of, summarize
    from nexus_api.services.testing.suites import get_suite, list_tests

    out: list[dict[str, Any]] = []
    agent = await _agent_of(session, channel)
    tests_ok = False
    if agent is not None:
        suite = await get_suite(session, agent.id)
        if suite is not None:
            tests = await list_tests(session, suite)
            latest = await latest_results(session, agent.id)
            summary = summarize(tests, {t.id: outcome_of(t, latest.get(t.id, [])) for t in tests})
            tests_ok = bool(tests) and not (
                summary["stale"] or summary["failed"] or summary["not_run"]
            )
    out.append(
        {
            "code": "tests_up_to_date",
            "ok": tests_ok,
            "level": "warn",
            "fix": None if tests_ok else "run_tests",
        }
    )
    has_recipient = bool(await recipients_of(session, channel.id))
    out.append(
        {
            "code": "escalation_recipient",
            "ok": has_recipient,
            "level": "warn",
            "fix": None if has_recipient else "add_recipient",
        }
    )
    if channel.audience_mode == "everyone" or channel.audience_mode == "unset":
        for blocker in await everyone_blockers(session, channel):
            out.append({**blocker, "ok": False, "level": "block"})
    return out


async def escalation_failed_attempts(session: AsyncSession, channel: Channel) -> int | None:
    """Tras cuántos intentos fallidos escala el agente (el disparador
    ``failed_attempts``), para la página en solo lectura."""
    spec = await _agent_spec(session, channel)
    escalation = spec.escalation if spec is not None else None
    return escalation.failed_attempts if escalation is not None else None


async def _agent_spec(session: AsyncSession, channel: Channel) -> Any:
    from nexus_api.services.agent_spec.legacy import spec_from_version
    from nexus_api.services.agent_spec.schema import AgentSpec

    agent = await _agent_of(session, channel)
    version = await _active_version(session, agent)
    if agent is None or version is None:
        return None
    if version.spec:
        return AgentSpec.model_validate(version.spec)
    return spec_from_version(
        agent_name=agent.name,
        system_prompt_rendered=version.system_prompt_rendered or "",
        tools=list(version.tools or []),
        policies=dict(version.policies or {}),
    )


async def escalation_triggers(session: AsyncSession, channel: Channel) -> list[Any]:
    """Los disparadores del escalado viven en el agente; la página los enseña en
    solo lectura (33.5)."""
    from nexus_api.services.agent_spec.legacy import spec_from_version
    from nexus_api.services.agent_spec.schema import AgentSpec

    agent = await _agent_of(session, channel)
    version = await _active_version(session, agent)
    if agent is None or version is None:
        return []
    spec = (
        AgentSpec.model_validate(version.spec)
        if version.spec
        else spec_from_version(
            agent_name=agent.name,
            system_prompt_rendered=version.system_prompt_rendered or "",
            tools=list(version.tools or []),
            policies=dict(version.policies or {}),
        )
    )
    escalation = spec.escalation
    triggers = escalation.triggers if escalation is not None else None
    return [t if isinstance(t, str) else t.model_dump() for t in (triggers or [])]


# ── escritura ──────────────────────────────────────────────────────────────


async def _replace_numbers(
    session: AsyncSession, channel: Channel, kind: str, numbers: Sequence[str]
) -> None:
    await session.execute(
        sa.delete(ChannelAudienceNumber).where(
            ChannelAudienceNumber.tenant_id == channel.tenant_id,
            ChannelAudienceNumber.channel_id == channel.id,
            ChannelAudienceNumber.kind == kind,
        )
    )
    for phone in numbers:
        session.add(
            ChannelAudienceNumber(
                tenant_id=channel.tenant_id, channel_id=channel.id, kind=kind, phone_e164=phone
            )
        )


async def _replace_recipients(
    session: AsyncSession, channel: Channel, recipients: Sequence[Recipient]
) -> None:
    await session.execute(
        sa.delete(ChannelEscalationRecipient).where(
            ChannelEscalationRecipient.tenant_id == channel.tenant_id,
            ChannelEscalationRecipient.channel_id == channel.id,
        )
    )
    for position, r in enumerate(recipients):
        session.add(
            ChannelEscalationRecipient(
                tenant_id=channel.tenant_id,
                channel_id=channel.id,
                name=r.name,
                via=r.via,
                phone_e164=r.phone_e164,
                email=r.email,
                client_user_id=r.client_user_id,
                position=position,
            )
        )


async def _apply(session: AsyncSession, channel: Channel, stored: Mapping[str, Any]) -> None:
    """Escribe una configuración ya validada (al guardar y al deshacer)."""
    audience = stored.get("audience") or {}
    escalation = stored.get("escalation") or {}
    channel.audience_mode = str(audience.get("mode") or "unset")
    await _replace_numbers(session, channel, "test", list(audience.get("test_numbers") or []))
    await _replace_numbers(session, channel, "exception", list(audience.get("exceptions") or []))
    await _replace_recipients(
        session,
        channel,
        [
            Recipient(
                name=r["name"],
                via=r["via"],
                phone_e164=r.get("phone_e164"),
                email=r.get("email"),
                client_user_id=r.get("client_user_id"),
            )
            for r in escalation.get("recipients") or []
        ],
    )
    cfg = dict(channel.config or {})
    cfg["escalation_summary"] = bool(escalation.get("summary", True))
    wait = stored.get("wait_message")
    if wait:
        cfg["wait_message"] = wait
    else:
        cfg.pop("wait_message", None)
    channel.config = cfg
    channel.config_revision = (channel.config_revision or 0) + 1


def _diff(before: Mapping[str, Any] | None, after: Mapping[str, Any]) -> list[str]:
    """Qué secciones cambiaron."""
    before = before or {}
    return sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k))


async def _changed_since(session: AsyncSession, channel: Channel, revision: int) -> list[str]:
    """Las secciones que cambiaron desde la revisión que leyó la consola: cada
    escritura sube la revisión en uno y deja una fila en el historial."""
    missed = max(0, (channel.config_revision or 0) - revision)
    if not missed:
        return []
    rows = (
        await session.scalars(
            sa.select(ChannelConfigChange)
            .where(
                ChannelConfigChange.tenant_id == channel.tenant_id,
                ChannelConfigChange.channel_id == channel.id,
            )
            .order_by(ChannelConfigChange.at.desc())
            .limit(missed)
        )
    ).all()
    return sorted({section for r in rows for section in _diff(r.before, r.after)})


async def validate(session: AsyncSession, channel: Channel, payload: ConfigIn) -> dict[str, Any]:
    """Normaliza y valida; devuelve lo que se guardará."""
    tests = normalize_numbers(payload.test_numbers)
    exceptions = normalize_numbers(payload.exceptions)
    if len(payload.recipients) > MAX_RECIPIENTS:
        raise ChannelConfigError("too_many_recipients", 422, limit=MAX_RECIPIENTS)
    recipients = [_recipient(r) for r in payload.recipients]
    wait = (payload.wait_message or "").strip() or None
    if wait is not None and len(wait) > WAIT_MESSAGE_MAX:
        raise ChannelConfigError("wait_message_too_long", 422, limit=WAIT_MESSAGE_MAX)
    if payload.mode == "team_only" and not _is_whatsapp(channel):
        # Los números de prueba son teléfonos; en Instagram y Messenger quien
        # escribe es un IGSID o un PSID y nunca casaría.
        raise ChannelConfigError("team_only_needs_whatsapp", 422)
    if payload.mode == "team_only" and not tests:
        raise ChannelConfigError("channel_test_numbers_required", 422)
    if payload.mode == "everyone":
        blockers = await everyone_blockers(session, channel)
        if blockers:
            first = blockers[0]
            raise ChannelConfigError(
                first["code"], 409, fix=first["fix"], blocking=[b["code"] for b in blockers]
            )
    return {
        "audience": {"mode": payload.mode, "test_numbers": tests, "exceptions": exceptions},
        "escalation": {"recipients": [r.as_dict() for r in recipients], "summary": payload.summary},
        "wait_message": wait,
    }


def _audit(channel: Channel, actor: str, action: str, after: Mapping[str, Any]) -> AuditLog:
    return AuditLog(
        tenant_id=channel.tenant_id,
        actor=actor,
        action=action,
        target=f"channel:{channel.id}",
        after_json=dict(after),
    )


async def write_config(
    session: AsyncSession,
    channel: Channel,
    payload: ConfigIn,
    *,
    revision: int | None,
    actor: str,
    origin: str = "console",
) -> ChannelConfigChange:
    """Guardar (32.7): ``If-Match`` contra ``config_revision``; el cambio queda
    en el historial con 10 minutos para deshacerlo."""
    before = _stored(await read_config(session, channel))
    if revision is not None and revision != channel.config_revision:
        raise ChannelConfigError(
            "revision_conflict",
            412,
            current=channel.config_revision,
            changes=await _changed_since(session, channel, revision),
        )
    after = await validate(session, channel, payload)
    await _apply(session, channel, after)
    now = datetime.now(UTC)
    change = ChannelConfigChange(
        tenant_id=channel.tenant_id,
        channel_id=channel.id,
        before=before,
        after=after,
        actor=actor,
        origin=origin,
        at=now,
        undo_until=now + UNDO_WINDOW,
    )
    session.add(change)
    session.add(
        _audit(channel, actor, "channel.config_changed", {"sections": _diff(before, after)})
    )
    await session.flush()
    return change


async def undo(session: AsyncSession, channel: Channel, *, actor: str) -> ChannelConfigChange:
    """Deshacer el último cambio, durante 10 minutos (32.7). Devuelve lo de antes
    sin volver a pasar las comprobaciones: era lo que había."""
    last = await session.scalar(
        sa.select(ChannelConfigChange)
        .where(
            ChannelConfigChange.tenant_id == channel.tenant_id,
            ChannelConfigChange.channel_id == channel.id,
            ChannelConfigChange.undone_at.is_(None),
            ChannelConfigChange.undo_until.is_not(None),
        )
        .order_by(ChannelConfigChange.at.desc())
        .limit(1)
        .with_for_update()
    )
    now = datetime.now(UTC)
    if last is None or last.undo_until is None or last.undo_until < now:
        raise ChannelConfigError("undo_window_closed", 409)
    current = _stored(await read_config(session, channel))
    restored = last.before or {
        "audience": {"mode": "unset", "test_numbers": [], "exceptions": []},
        "escalation": {"recipients": [], "summary": True},
        "wait_message": None,
    }
    await _apply(session, channel, restored)
    last.undone_at = now
    last.undo_until = None
    change = ChannelConfigChange(
        tenant_id=channel.tenant_id,
        channel_id=channel.id,
        before=current,
        after=restored,
        actor=actor,
        origin="undo",
        at=now,
    )
    session.add(change)
    session.add(_audit(channel, actor, "channel.config_undone", {"change_id": str(last.id)}))
    await session.flush()
    return change


async def history(
    session: AsyncSession, channel: Channel, *, limit: int = 50
) -> list[ChannelConfigChange]:
    return list(
        (
            await session.scalars(
                sa.select(ChannelConfigChange)
                .where(
                    ChannelConfigChange.tenant_id == channel.tenant_id,
                    ChannelConfigChange.channel_id == channel.id,
                )
                .order_by(ChannelConfigChange.at.desc(), ChannelConfigChange.id)
                .limit(limit)
            )
        ).all()
    )


async def start_in_test_mode(
    session: AsyncSession, channel: Channel, *, connector_phone: str | None, actor: str
) -> None:
    """Un número recién conectado (32.9): «Solo mi equipo» con el número de quien
    lo conectó; sin ese número, «Sin configurar». No pisa una audiencia que ya
    tenga (reconectar conserva la configuración, 30.7)."""
    if channel.audience_mode != "unset":
        return
    phone: str | None = None
    if connector_phone:
        try:
            phone = normalize_phone(connector_phone)
        except ChannelConfigError:
            phone = None
    if phone is None:
        return
    after = {
        "audience": {"mode": "team_only", "test_numbers": [phone], "exceptions": []},
        "escalation": {
            "recipients": [r.as_dict() for r in await recipients_of(session, channel.id)],
            "summary": bool((channel.config or {}).get("escalation_summary", True)),
        },
        "wait_message": (channel.config or {}).get("wait_message"),
    }
    await _apply(session, channel, after)
    session.add(
        ChannelConfigChange(
            tenant_id=channel.tenant_id,
            channel_id=channel.id,
            before=None,
            after=after,
            actor=actor,
            origin="connect",
            at=datetime.now(UTC),
        )
    )
    await session.flush()


def _status_of(channel: Channel) -> str:
    return channel.status.value if hasattr(channel.status, "value") else str(channel.status)


async def pause_channel(
    session: AsyncSession,
    channel: Channel,
    *,
    by_kind: str,
    by_id: str | None,
    origin: str,
    actor: str,
) -> bool:
    """Pausar el número (requisito 27): lo que llega se guarda y espera a una
    persona con «Canal en pausa»; ni respuesta ni ticks azules. Guarda quién,
    desde dónde y el estado de antes, que es lo que devuelve reanudar. Lo usan la
    consola del partner, la lite y la app. ``True`` si cambió algo: quien llama
    invalida la caché del número y avisa."""
    if channel.status is ChannelStatus.DISCONNECTED:
        raise ChannelConfigError("channel_disconnected", 409)
    if channel.status is ChannelStatus.PAUSED:
        return False
    before = _status_of(channel)
    channel.status = ChannelStatus.PAUSED
    channel.paused_at = datetime.now(UTC)
    channel.paused_by_kind = by_kind
    channel.paused_by_id = by_id
    channel.paused_origin = origin
    cfg = dict(channel.config or {})
    cfg["before_pause"] = before
    channel.config = cfg
    session.add(_audit(channel, actor, "channel.paused", {"before": before, "origin": origin}))
    await session.flush()
    return True


def health_degraded(channel: Channel) -> bool:
    """¿El número está degradado? En pausa lo dice el estado que devolverá
    reanudar, no ``status``."""
    if channel.status is ChannelStatus.PAUSED:
        return (channel.config or {}).get("before_pause") == ChannelStatus.DEGRADED.value
    return channel.status is ChannelStatus.DEGRADED


def set_health(channel: Channel, *, degraded: bool) -> None:
    """Degradar o sanar el número sin pisar una pausa del partner: en pausa se
    cambia lo que devolverá reanudar y el estado sigue en ``paused`` (el cron
    de salud y los eventos de cuenta lo despausaban; QA 2026-10-30, INC-06)."""
    target = ChannelStatus.DEGRADED if degraded else ChannelStatus.ACTIVE
    if channel.status is ChannelStatus.PAUSED:
        channel.config = {**(channel.config or {}), "before_pause": target.value}
    else:
        channel.status = target


async def resume_channel(
    session: AsyncSession, channel: Channel, *, origin: str, actor: str
) -> bool:
    """Reanudar devuelve el estado de antes de la pausa (27.3). ``True`` si
    cambió algo."""
    if channel.status is not ChannelStatus.PAUSED:
        return False
    cfg = dict(channel.config or {})
    previous = str(cfg.pop("before_pause", "active"))
    channel.status = (
        ChannelStatus.DEGRADED if previous == ChannelStatus.DEGRADED.value else ChannelStatus.ACTIVE
    )
    channel.config = cfg
    channel.paused_at = None
    channel.paused_by_kind = None
    channel.paused_by_id = None
    channel.paused_origin = None
    session.add(
        _audit(channel, actor, "channel.resumed", {"to": _status_of(channel), "origin": origin})
    )
    await session.flush()
    return True


#: El interruptor del teléfono que lleva cada aviso de la 047 a la persona del
#: cliente (``events.md`` §3.1): la bolsa va con el saldo de antes; el tope, las
#: pausas y los números, con «Agentes y números».
CLIENT_PUSH_KIND: dict[str, str] = {
    "client.wallet.low": "client.balance",
    "client.wallet.not_enough": "client.balance",
    "client.wallet.empty": "client.balance",
    "agent.cap.warning": "agents.state",
    "agent.cap.reached": "agents.state",
    "agent.paused": "agents.state",
    "agent.resumed": "agents.state",
    "channel.paused": "agents.state",
    "channel.resumed": "agents.state",
    "channel.problem": "agents.state",
}


async def announce(
    *,
    tenant_id: uuid.UUID,
    kind: str,
    data: Mapping[str, Any],
    severity: str = "info",
    dedupe_key: str | None = None,
    to_client: bool = False,
    to_partner: bool = True,
) -> None:
    """Un aviso al partner sobre un número de su cliente (``events.md`` §3) y, con
    ``to_client``, también a las personas del cliente: su campana y su teléfono
    (§3.1). Tras el commit y en su propia sesión: ``console_notifications`` es de
    plataforma. Nunca lanza: el aviso no puede deshacer lo que ya pasó."""
    import structlog

    from nexus_api.db.base import get_sessionmaker
    from nexus_api.db.models import PartnerTenant
    from nexus_api.services.console_notifications import emit

    try:
        async with get_sessionmaker()() as session, session.begin():
            row = (
                await session.execute(
                    sa.select(PartnerTenant.partner_id, PartnerTenant.external_client_ref).where(
                        PartnerTenant.tenant_id == tenant_id
                    )
                )
            ).first()
            if row is None:
                return
            if to_partner:
                await emit(
                    session,
                    partner_id=row.partner_id,
                    kind=kind,
                    severity=severity,
                    external_client_ref=row.external_client_ref,
                    data=dict(data),
                    dedupe_key=dedupe_key,
                )
            push_kind = CLIENT_PUSH_KIND.get(kind)
            if to_client and push_kind is not None:
                from nexus_api.db.models import NotificationAudience
                from nexus_api.services import push_events

                notice = await emit(
                    session,
                    partner_id=row.partner_id,
                    kind=kind,
                    severity=severity,
                    external_client_ref=row.external_client_ref,
                    data=dict(data),
                    dedupe_key=f"client:{dedupe_key}" if dedupe_key else None,
                    audience=NotificationAudience.CLIENT,
                )
                if notice is not None:
                    await push_events.enqueue(
                        session,
                        tenant_id=tenant_id,
                        kind=push_kind,
                        notification_id=notice.id,
                        dedupe_key=f"{push_kind}:{notice.id}",
                    )
    except Exception as exc:
        structlog.get_logger(__name__).warning(
            "channel.announce_failed", tenant_id=str(tenant_id), kind=kind, error=str(exc)
        )


__all__ = [
    "ESCALATION_TEMPLATE",
    "MAX_RECIPIENTS",
    "UNDO_WINDOW",
    "ChannelConfigError",
    "ConfigIn",
    "Recipient",
    "announce",
    "checks",
    "escalation_failed_attempts",
    "escalation_triggers",
    "everyone_blockers",
    "gate_audience",
    "history",
    "normalize_numbers",
    "normalize_phone",
    "notify_from",
    "partner_on_v2",
    "pause_channel",
    "read_config",
    "recipients_of",
    "resume_channel",
    "start_in_test_mode",
    "undo",
    "validate",
    "write_config",
]
