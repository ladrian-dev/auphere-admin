"""El ciclo de vida de una acción del Companion (CO-04, §3 del contrato).

Aquí vive lo que pasa entre *proponer* y *quedar aplicado*: persistir la
propuesta, caducarla, revalidar el hash, aplicar la escritura por el router
y **verificar releyendo**.

Cuatro reglas del motor, no del prompt
--------------------------------------

- **``action_id`` determinista + UPSERT** (corrección C2). ``interrupt()`` de
  LangGraph reanuda re-ejecutando el nodo desde la primera línea. Con un id
  aleatorio y un ``INSERT``, cada confirmación duplicaría la fila. El id sale
  de ``uuid5(namespace, "{run_id}:{step_index}")`` y la escritura es
  ``ON CONFLICT (id) DO UPDATE``. La 0090 creó la columna sin ``default``
  justo para esto.

- **Solo ``confirmed`` pasa a ``applying``** (garantía C4). La comprobación
  está en :func:`apply_action`, no en una frase del prompt: un modelo
  convencido de que ya tiene permiso choca contra un ``if`` y se queda ahí.

- **La caducidad es perezosa.** No hay cron. Se calcula al leer y se
  persiste en la misma transacción — el mismo patrón que ``_is_expired``
  para runs. Un cron para esto sería un proceso más que puede fallar, y
  fallaría en silencio.

- **La verificación es código** (corrección C5). :func:`verify_action` relee
  el recurso por HTTP y compara con lo que la propuesta prometió. Nunca un
  subagente, nunca una instrucción de "revisa tu trabajo": la guía de
  migración a Opus 5 es explícita en que eso produce sobre-verificación sin
  ganancia, y además un verificador que es el mismo modelo no verifica nada.
"""

from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

import sqlalchemy as sa
import structlog
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.companion.tools.proposals import (
    Proposal,
    canonical_hash,
    short_digest,
)
from nexus_api.core.principal_context import apply_principal_to_session
from nexus_api.db.models.companion import CompanionAction

log = structlog.get_logger(__name__)

#: Espacio de nombres del ``uuid5`` de una acción. Constante fija del módulo:
#: si cambiara, las acciones ya propuestas dejarían de encontrarse a sí
#: mismas al reanudar y cada confirmación pendiente se convertiría en una
#: fila huérfana.
NAMESPACE_COMPANION_ACTION = uuid.UUID("c0a1a100-0000-4000-8000-000000000004")

# ── estados (§3.3 del contrato) ────────────────────────────────────────

STATUS_PROPOSED = "proposed"
STATUS_CONFIRMED = "confirmed"
STATUS_SUPERSEDED = "superseded"
STATUS_CANCELLED = "cancelled"
STATUS_EXPIRED = "expired"
STATUS_APPLYING = "applying"
STATUS_APPLIED = "applied"
STATUS_FAILED = "failed"

#: Una vez aquí, la acción no se mueve más. La única que no lo es entre las
#: decididas es ``confirmed``, porque le queda aplicarse.
TERMINAL_ACTION_STATUSES: frozenset[str] = frozenset(
    {STATUS_APPLIED, STATUS_FAILED, STATUS_CANCELLED, STATUS_SUPERSEDED, STATUS_EXPIRED}
)

DECISIONS: frozenset[str] = frozenset({"confirm", "edit", "cancel"})

#: Decisión → estado resultante. Un mapa y no tres ``if``: es el sitio donde
#: A, B y C tienen que estar de acuerdo, y se lee de un vistazo.
DECISION_STATUS: dict[str, str] = {
    "confirm": STATUS_CONFIRMED,
    "edit": STATUS_SUPERSEDED,
    "cancel": STATUS_CANCELLED,
}


def action_id_for(run_id: uuid.UUID, step_index: int) -> uuid.UUID:
    """El id determinista del §3.2 del contrato."""
    return uuid.uuid5(NAMESPACE_COMPANION_ACTION, f"{run_id}:{step_index}")


def expires_at_of(proposed_at: datetime, ttl_seconds: float) -> datetime:
    at = proposed_at if proposed_at.tzinfo else proposed_at.replace(tzinfo=UTC)
    return at + timedelta(seconds=ttl_seconds)


def is_stale(action: CompanionAction, ttl_seconds: float, *, now: datetime | None = None) -> bool:
    """¿Se le pasó el plazo sin que nadie decidiera?"""
    if action.status != STATUS_PROPOSED:
        return False
    return (now or datetime.now(UTC)) >= expires_at_of(action.proposed_at, ttl_seconds)


# ── persistencia ───────────────────────────────────────────────────────


@dataclass(frozen=True)
class StagedAction:
    """Lo que el nodo ``plan`` devuelve tras persistir. Es exactamente el
    payload de ``hitl.requested`` más lo que el grafo necesita después."""

    action_id: uuid.UUID
    kind: str
    title: str
    preview: dict[str, Any]
    diff: list[dict[str, Any]] | None
    impact: list[dict[str, Any]]
    expires_at: datetime

    def as_event(self) -> dict[str, Any]:
        return {
            "action_id": str(self.action_id),
            "kind": self.kind,
            "title": self.title,
            "preview": self.preview,
            "diff": self.diff,
            "impact": self.impact,
            "expires_at": self.expires_at.isoformat(),
        }


async def stage_action(
    session: AsyncSession,
    *,
    principal_id: str,
    thread_id: uuid.UUID,
    run_id: uuid.UUID,
    step_index: int,
    proposal: Proposal,
    ttl_seconds: float,
) -> StagedAction:
    """Persiste la propuesta como ``proposed``. **UPSERT, nunca INSERT.**

    Abre su propia transacción y aplica el ámbito del principal: la RLS de
    ``companion.actions`` cuelga del hilo, así que sin el GUC no entra nada
    —que es lo que se quiere si alguien llama a esto desde donde no debe.
    """
    action_id = action_id_for(run_id, step_index)
    payload = proposal.as_payload()
    now = datetime.now(UTC)
    async with session.begin():
        await apply_principal_to_session(session, principal_id)
        stmt = pg_insert(CompanionAction).values(
            id=action_id,
            thread_id=thread_id,
            run_id=run_id,
            kind=proposal.kind,
            payload=payload,
            # La columna está tipada ``dict`` en el modelo (fuera de la zona
            # de CO-04) y el contrato sirve el diff como lista. Se envuelve
            # al guardar y se desenvuelve al servir; la columna es JSONB
            # opaca y nadie más la lee.
            diff={"lines": proposal.diff} if proposal.diff is not None else None,
            state_hash=proposal.state_hash,
            status=STATUS_PROPOSED,
            proposed_at=now,
        )
        # Re-proponer el MISMO paso del MISMO run sobrescribe: es la reejecución
        # de un nodo, no una segunda propuesta. Y nunca resucita una acción ya
        # decidida — de ahí el ``WHERE`` sobre el estado.
        stmt = stmt.on_conflict_do_update(
            index_elements=[CompanionAction.id],
            set_={
                "payload": stmt.excluded.payload,
                "diff": stmt.excluded.diff,
                "state_hash": stmt.excluded.state_hash,
                "kind": stmt.excluded.kind,
                "proposed_at": stmt.excluded.proposed_at,
            },
            where=CompanionAction.status == STATUS_PROPOSED,
        )
        await session.execute(stmt)
    return StagedAction(
        action_id=action_id,
        kind=proposal.kind,
        title=proposal.title,
        preview=proposal.preview,
        diff=proposal.diff,
        impact=proposal.impact,
        expires_at=expires_at_of(now, ttl_seconds),
    )


async def load_action(
    session: AsyncSession, action_id: uuid.UUID, *, principal_id: str, ttl_seconds: float
) -> CompanionAction | None:
    """Lee una acción propia aplicando la **caducidad perezosa**.

    Si estaba en ``proposed`` y se le pasó el plazo, se persiste ``expired``
    en esta misma transacción. Así la caducidad es la misma la vea quien la
    vea, y no depende de que alguien haya arrancado un cron.
    """
    async with session.begin():
        await apply_principal_to_session(session, principal_id)
        action = await session.get(CompanionAction, action_id)
        if action is None:
            return None
        if is_stale(action, ttl_seconds):
            action.status = STATUS_EXPIRED
            action.decided_at = sa.func.now()
            await session.flush()
            await session.refresh(action)
        return action


async def set_status(
    session: AsyncSession,
    action_id: uuid.UUID,
    *,
    principal_id: str,
    status: str,
    result: dict[str, Any] | None = None,
    applied: bool = False,
) -> None:
    """Mueve el estado de una acción. Sin lógica: quien llama ya decidió."""
    values: dict[str, Any] = {"status": status}
    if result is not None:
        values["result"] = result
    if applied:
        values["applied_at"] = sa.func.now()
    async with session.begin():
        await apply_principal_to_session(session, principal_id)
        await session.execute(
            sa.update(CompanionAction).where(CompanionAction.id == action_id).values(**values)
        )


# ── aplicación ─────────────────────────────────────────────────────────


#: Qué se queda de la RESPUESTA de aplicar, por ``kind``. Lista blanca
#: cerrada, nunca el cuerpo entero.
#:
#: Existe porque el identificador de un ticket de soporte **nace al aplicar**
#: (CO-08 §4.4) y el evento ``support.ticket`` tiene que poder decirlo: sin
#: esto habría que reabrir la respuesta HTTP desde otro sitio, o inventar un
#: segundo camino de lectura.
#:
#: Que sea una lista blanca **por clave y por kind** es lo que la hace segura
#: (C8): estas cuatro son un identificador y tres enums, y ninguna puede
#: llevar texto de un cliente final. Añadir un ``kind`` aquí es una decisión
#: consciente, no un efecto colateral de que un endpoint devuelva más campos.
APPLY_ECHO: dict[str, tuple[str, ...]] = {
    "support_help": ("ticket_ref", "sla", "category", "topic"),
    "support_capability": ("ticket_ref", "sla", "category", "topic"),
}


def apply_echo(kind: str, body: str) -> dict[str, str]:
    """Las claves declaradas de la respuesta, como cadenas. Nunca lanza."""
    allowed = APPLY_ECHO.get(kind)
    if not allowed:
        return {}
    try:
        parsed = json.loads(body or "{}")
    except ValueError:  # pragma: no cover - el router siempre da JSON
        return {}
    if not isinstance(parsed, dict):  # pragma: no cover - defensivo
        return {}
    return {k: str(parsed[k]) for k in allowed if isinstance(parsed.get(k), str | int | float)}


@dataclass(frozen=True)
class ApplyOutcome:
    ok: bool
    status_code: int
    #: Cuerpo de la respuesta del router, recortado. Va al contexto del
    #: modelo, **no** al stream: el stream solo lleva ``ok`` y la latencia.
    body: str
    error_code: str | None = None


async def apply_action(
    session: AsyncSession,
    write: Any,
    action: CompanionAction,
    *,
    principal_id: str,
) -> ApplyOutcome:
    """Ejecuta la escritura de una acción **confirmada**.

    ``write`` es la función de escritura del ejecutor: la misma vía HTTP en
    proceso que usan las lecturas, así que la petición pasa por el enrutado,
    la validación Pydantic, ``client_scope`` (RLS), el limitador, la cuota y
    la auditoría. Saltarse eso "porque es más rápido" convertiría al
    Companion en un camino paralelo con sus propios agujeros.

    El destino sale del payload guardado, **no de un argumento**: el modelo
    no vuelve a intervenir entre la confirmación y la escritura.
    """
    if action.status != STATUS_CONFIRMED:
        # Garantía C4, y falla AQUÍ. Un modelo convencido de que ya tiene
        # permiso choca contra este ``if``, no contra una frase de prompt.
        return ApplyOutcome(
            ok=False,
            status_code=409,
            body="",
            error_code="not_confirmed",
        )

    request = dict((action.payload or {}).get("apply") or {})
    method = str(request.get("method") or "").upper()
    path = str(request.get("path") or "")
    if not method or not path:  # pragma: no cover - lo escribe la propuesta
        return ApplyOutcome(ok=False, status_code=500, body="", error_code="unavailable")

    await set_status(session, action.id, principal_id=principal_id, status=STATUS_APPLYING)
    try:
        response = await write(method, path, request.get("body"))
    except Exception as exc:
        log.exception("companion.apply.failed", action_id=str(action.id), path=path)
        await set_status(
            session,
            action.id,
            principal_id=principal_id,
            status=STATUS_FAILED,
            result={"error": str(exc)[:500]},
        )
        return ApplyOutcome(ok=False, status_code=0, body="", error_code="unavailable")

    body = response.text[:4000]
    if response.status_code >= 400:
        await set_status(
            session,
            action.id,
            principal_id=principal_id,
            status=STATUS_FAILED,
            result={"status": response.status_code, "body": body[:1000]},
        )
        return ApplyOutcome(
            ok=False, status_code=response.status_code, body=body, error_code="apply_failed"
        )

    await set_status(
        session,
        action.id,
        principal_id=principal_id,
        status=STATUS_APPLIED,
        result={"status": response.status_code, **apply_echo(action.kind, body)},
        applied=True,
    )
    return ApplyOutcome(ok=True, status_code=response.status_code, body=body)


# ── verificación determinista (C5) ─────────────────────────────────────
#
# Qué se relee por ``kind`` y de dónde sale cada comprobación. Es un mapa y
# no una cadena de ``if`` porque así se ve de un vistazo que TODO ``kind``
# tiene verificación — un ``kind`` que se colara sin ella pasaría de largo
# en un ``if`` y nadie lo notaría hasta que alguien preguntara por qué la
# tabla salió vacía.

VERIFY_READS: dict[str, str] = {
    "client": "/console/clients/{client_ref}",
    "prompt": "/console/clients/{client_ref}/agent",
    "policy": "/console/clients/{client_ref}/agent/settings",
    "tools": "/console/clients/{client_ref}/tools",
    "skills": "/console/clients/{client_ref}/skills",
    "publish": "/console/clients/{client_ref}/agent",
    "channel_role": "/console/clients/{client_ref}/channels",
    "usage_alerts": "/console/usage/alerts",
    "allocation": "/console/clients/{client_ref}/allocation",
    "model": "/console/clients/{client_ref}/model",
    "invite": "/console/team",
    # CO-08. No hay sistema de tickets que releer —§25.1 es explícito en que
    # no se crea uno—, así que lo que se verifica es lo que SÍ se prometió:
    # que el ticket aterrizó en la tubería que ya existe y que el partner lo
    # ve en su centro de notificaciones. Declarar aquí un ``kind`` sin
    # comprobación dejaría la tabla vacía en verde, que es peor que no
    # verificar: parece verificado.
    "support_help": "/console/notifications",
    "support_capability": "/console/notifications",
}


async def verify_action(read: Any, action: CompanionAction) -> dict[str, Any]:
    """Relee el recurso y compara con lo prometido. Devuelve el payload de
    ``verify.result``.

    ``expected`` y ``actual`` son **cadenas siempre**, incluso para números
    (§2.5 del contrato): evita que ``8`` y ``"8"`` se pinten distinto y que
    un float redondee delante de alguien que decide sobre un negocio.
    """
    payload = dict(action.payload or {})
    expectations: dict[str, str] = dict(payload.get("expectations") or {})
    client_ref = payload.get("client_ref")
    template = VERIFY_READS.get(action.kind)
    if template is None or not expectations:  # pragma: no cover - todo kind tiene ambos
        return {"action_id": str(action.id), "checks": [], "ok": True}

    path = template.format(client_ref=client_ref) if client_ref else template
    try:
        response = await read(path, {})
        fresh = response.json() if response.status_code < 400 else None
    except Exception:  # pragma: no cover - defensivo
        fresh = None
    if fresh is None:
        # No se pudo releer. Se dice, y se dice como fallo: un "no lo sé"
        # presentado como verde es peor que no verificar.
        checks = [
            {"name": name, "expected": expected, "actual": "unreadable", "ok": False}
            for name, expected in sorted(expectations.items())
        ]
        return {"action_id": str(action.id), "checks": checks, "ok": False}

    # ``result`` entra en lo que ve el observador porque hay ``kind`` cuya
    # comprobación depende de algo que nació AL APLICAR —el ``ticket_ref``—
    # y no de lo que se prometió al proponer.
    # ``getattr`` y no ``action.result``: los dobles de los unitarios son
    # objetos mínimos con ``kind`` y ``payload``, y obligarles a crecer una
    # columna para una rama que no ejercitan sería acoplarlos de balde.
    actual = _observed(
        action.kind, fresh, {**payload, "result": dict(getattr(action, "result", None) or {})}
    )
    checks = [
        {
            "name": name,
            "expected": str(expected),
            "actual": str(actual.get(name, "missing")),
            "ok": str(actual.get(name, "missing")) == str(expected),
        }
        for name, expected in sorted(expectations.items())
    ]
    return {
        "action_id": str(action.id),
        "checks": checks,
        "ok": all(c["ok"] for c in checks),
    }


def _observed(kind: str, fresh: Any, payload: dict[str, Any]) -> dict[str, str]:
    """Traduce la relectura a los mismos nombres que usó ``expectations``."""
    if kind == "client":
        # Que la ficha se pueda leer ES la comprobación: el 404 del cliente
        # inexistente ya salió por la rama de "no se pudo releer".
        ref = str((fresh or {}).get("external_client_ref") or "")
        return {"client_exists": "true" if ref else "false", "client_ref": ref}
    if kind == "prompt":
        draft = _staged_or_active(fresh)
        return {"draft_prompt": short_digest(str((draft or {}).get("system_prompt") or ""))}
    if kind == "policy":
        return {"policy": canonical_hash((fresh or {}).get("settings") or {})[:12]}
    if kind in ("tools", "skills"):
        rows = (fresh or {}).get(kind) or []
        return {f"{kind}_enabled": str(sum(1 for r in rows if r.get("enabled")))}
    if kind == "publish":
        active = (fresh or {}).get("active_version")
        return {"active_version": str(active) if active is not None else "none"}
    if kind == "channel_role":
        wanted = str((payload.get("apply") or {}).get("path") or "").split("/channels/")[-1]
        channel_id = wanted.removesuffix("/role")
        rows = fresh if isinstance(fresh, list) else []
        row = next((c for c in rows if str(c.get("id")) == channel_id), None)
        return {"channel_role": str((row or {}).get("role") or "null")}
    if kind == "usage_alerts":
        cap = (fresh or {}).get("cap_messages_month")
        return {
            "alerts_cap": str(cap) if cap is not None else "null",
            "alerts_recipients": str(len((fresh or {}).get("recipients") or [])),
        }
    if kind == "allocation":
        cap = (fresh or {}).get("cap")
        return {"allocation_cap": str(cap) if cap is not None else "missing"}
    if kind == "model":
        mid = (fresh or {}).get("model_id")
        return {"model_id": str(mid) if mid else ""}
    if kind in ("support_help", "support_capability"):
        ref = str((payload.get("result") or {}).get("ticket_ref") or "")
        seen = {
            str(((item or {}).get("data") or {}).get("ticket_ref") or "")
            for item in ((fresh or {}).get("items") or [])
        }
        return {"ticket_visible": "true" if ref and ref in seen else "false"}
    if kind == "invite":
        body = (payload.get("apply") or {}).get("body") or {}
        email = str(body.get("email") or "").lower()
        pending = {
            str(i.get("email") or "").lower() for i in ((fresh or {}).get("invitations") or [])
        }
        return {"invitation_pending": "true" if email in pending else "false"}
    return {}  # pragma: no cover - el mapa cubre los nueve


def _staged_or_active(bundle: Any) -> dict[str, Any] | None:
    versions = (bundle or {}).get("versions") or []
    for v in versions:
        if v.get("status") == "staged":
            return dict(v)
    active = (bundle or {}).get("active_version")
    for v in versions:
        if active is not None and int(v.get("version") or 0) == int(active):
            return dict(v)
    return None


__all__ = [
    "APPLY_ECHO",
    "DECISIONS",
    "DECISION_STATUS",
    "NAMESPACE_COMPANION_ACTION",
    "STATUS_APPLIED",
    "STATUS_APPLYING",
    "STATUS_CANCELLED",
    "STATUS_CONFIRMED",
    "STATUS_EXPIRED",
    "STATUS_FAILED",
    "STATUS_PROPOSED",
    "STATUS_SUPERSEDED",
    "TERMINAL_ACTION_STATUSES",
    "VERIFY_READS",
    "ApplyOutcome",
    "StagedAction",
    "action_id_for",
    "apply_action",
    "apply_echo",
    "expires_at_of",
    "is_stale",
    "load_action",
    "set_status",
    "stage_action",
    "verify_action",
]
