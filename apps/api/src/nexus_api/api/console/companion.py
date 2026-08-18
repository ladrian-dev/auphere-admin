"""``/console/companion/*`` — el Companion de la consola (CO-01).

El agente que hace por conversación lo que hoy se hace a mano en la
consola. Este módulo es su superficie HTTP; el grafo vive en
``nexus_worker.runtime.companion`` y el log durable de cada run en
``api/companion_streaming.py``.

Lo que este módulo copia del playground, porque ya está probado
--------------------------------------------------------------
- **Identidad sin token de backend.** El sujeto es el ``ConsolePrincipal``;
  no hay meta-tenant. La RLS de ``companion.*`` es por ``principal_id``,
  igual que la de ``qa.*`` por operador. El hilo de otro miembro es un 404
  opaco, no un 403.
- **Ningún endpoint acepta ``tenant_id`` ni ``partner_id``.** El cliente
  opcional de un hilo se nombra con ``client_ref`` y se resuelve con
  ``resolve_mapping`` bajo el principal.
- **Tope de gasto comprobado ANTES de abrir el turno**, con 429 +
  ``Retry-After``, y limitador de ráfaga por miembro porque el tope mensual
  se mide sobre runs terminados.
- **Arranque del run fuera de la transacción**: la fila del hilo y la del
  run se comprometen antes de que la tarea empiece a publicar.

Lo que cambia, y es la corrección C1 de la investigación
-------------------------------------------------------
El run **no muere con la conexión**. ``POST …/runs`` devuelve 202 y el
trabajo sigue pase lo que pase con el navegador. Los eventos van a un log
durable en Redis, así que:

- ``GET …/events`` sirve el historial por REST — el patrón de reconexión
  sin pérdida es *abrir el stream, listar el historial, deduplicar por
  ``seq``*, y sin el segundo paso ``resume.gap`` es un callejón sin salida;
- ``GET …/stream`` es un lector puro de ese log: cualquier réplica sirve
  cualquier run;
- ``DELETE …/runs/{id}`` es la ÚNICA forma de cancelar. Cerrar el ``fetch``
  no llega hasta aquí y por tanto no para nada.
"""

from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Annotated, Any

import sqlalchemy as sa
import structlog
from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response, status
from fastapi.responses import StreamingResponse
from redis.asyncio import Redis
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api import companion_streaming as streaming
from nexus_api.api.deps import get_db_session, get_redis
from nexus_api.config import get_settings
from nexus_api.core.console_auth import ConsolePrincipal, require_console_principal
from nexus_api.core.principal_context import (
    apply_principal_to_session,
    principal_context,
)
from nexus_api.core.rate_limit import allow
from nexus_api.db.models import Partner, PartnerMembership, PartnerTenant
from nexus_api.db.models.companion import (
    RUN_ERROR,
    RUN_INTERRUPTED,
    RUN_RUNNING,
    TERMINAL_RUN_STATUSES,
    CompanionMessage,
    CompanionRun,
    CompanionThread,
)
from nexus_api.db.models.console_notification import (
    ConsoleNotification,
    NotificationSeverity,
)

from .deps import resolve_mapping
from .playground import MonthWindow, month_window, retry_after_seconds
from .schemas_companion import (
    CompanionBudgetOut,
    CompanionEventOut,
    CompanionEventsOut,
    CompanionRunStartIn,
    CompanionRunStartOut,
    CompanionThreadCreateIn,
    CompanionThreadOut,
    CompanionThreadPatchIn,
)

log = structlog.get_logger(__name__)

router = APIRouter()

#: Notification kind of a Companion cap. Not in ``NotificationKind``: that
#: enum is the console's published vocabulary and CP-22 renders it; adding
#: a value there is a console change, not a backend one. The dedupe key is
#: what makes it fire once per partner and month.
COMPANION_CAP_REACHED = "companion.cap_reached"


def companion_principal_id(principal: ConsolePrincipal) -> str:
    """RLS key of everything the Companion writes for this person.

    Es el ``user_id`` del principal a secas, sin prefijo: a diferencia de
    ``qa.*`` —donde ``console:<id>`` convive con operadores de Auphere en
    la misma tabla— el esquema ``companion`` solo tiene principales de
    consola, así que un prefijo no distinguiría nada y solo sería una
    cadena más que recordar al depurar.
    """
    return principal.user_id


# ── errores opacos ─────────────────────────────────────────────────────


def _unknown_thread() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown thread")


def _unknown_run() -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown run")


# ── dependencia común ──────────────────────────────────────────────────


@dataclass(frozen=True)
class CompanionCaller:
    principal: ConsolePrincipal

    @property
    def principal_id(self) -> str:
        return companion_principal_id(self.principal)

    @property
    def partner(self) -> Partner:
        return self.principal.partner


def companion_caller() -> Callable[..., Awaitable[CompanionCaller]]:
    principal_dep = require_console_principal("companion:use")

    async def _dependency(
        principal: ConsolePrincipal = Depends(principal_dep),
    ) -> CompanionCaller:
        return CompanionCaller(principal=principal)

    return _dependency


async def _thread_row(
    session: AsyncSession, thread_id: uuid.UUID, principal_id: str
) -> CompanionThread:
    """El hilo del llamante, o 404 opaco. Exige el GUC + el cambio de rol
    ya aplicados sobre la transacción (RLS por principal)."""
    thread = await session.get(CompanionThread, thread_id)
    if thread is None or thread.principal_id != principal_id:
        raise _unknown_thread()
    return thread


async def _client_ref_of(session: AsyncSession, thread: CompanionThread) -> str | None:
    """``external_client_ref`` del cliente atado al hilo, si lo hay.

    Se resuelve al salir y no se guarda en el hilo: el partner puede
    renombrar su referencia y una copia congelada mostraría la vieja.
    """
    if thread.tenant_id is None:
        return None
    return await session.scalar(
        sa.select(PartnerTenant.external_client_ref).where(
            PartnerTenant.partner_id == thread.partner_id,
            PartnerTenant.tenant_id == thread.tenant_id,
        )
    )


def _thread_out(thread: CompanionThread, client_ref: str | None) -> CompanionThreadOut:
    return CompanionThreadOut(
        id=thread.id,
        title=thread.title,
        mode=thread.mode,
        client_ref=client_ref,
        archived_at=thread.archived_at,
        last_run_at=thread.last_run_at,
        created_at=thread.created_at,
        updated_at=thread.updated_at,
    )


# ── presupuesto ────────────────────────────────────────────────────────


async def partner_companion_tokens_used(
    session: AsyncSession, partner_id: uuid.UUID, window: MonthWindow
) -> int:
    """Tokens del Companion consumidos por el partner en el mes (todos sus
    miembros).

    La fuente es ``companion.runs`` y no ``usage_records``, por dos razones
    que se refuerzan: la API cierra la fila del run al terminar el stream
    —así que la cuenta es síncrona y no depende del consumidor de
    metering—, y un hilo del Companion **sin cliente** no deja fila en
    ``usage_records`` en absoluto, porque esa tabla exige ``tenant_id``.

    ``companion.runs`` lleva RLS por principal, así que la suma se hace
    miembro a miembro: primero se leen las membresías (tabla de
    plataforma), luego se baja el rol y se reapunta ``app.principal_id``
    dentro de la misma transacción. Un miembro expulsado deja de contar —
    aceptable para un tope mensual blando, igual que en el playground.
    """
    async with session.begin():
        member_ids = list(
            (
                await session.execute(
                    sa.select(PartnerMembership.user_id).where(
                        PartnerMembership.partner_id == partner_id
                    )
                )
            ).scalars()
        )
        if not member_ids:
            return 0
        stmt = sa.select(
            sa.func.coalesce(
                sa.func.sum(
                    sa.func.coalesce(CompanionRun.input_tokens, 0)
                    + sa.func.coalesce(CompanionRun.output_tokens, 0)
                ),
                0,
            )
        ).where(
            CompanionRun.started_at >= window.start,
            CompanionRun.started_at < window.next_start,
        )
        total = 0
        for user_id in member_ids:
            await apply_principal_to_session(session, user_id)
            total += int(await session.scalar(stmt) or 0)
        return total


def budget_out(used: int, cap: int, window: MonthWindow) -> CompanionBudgetOut:
    remaining = max(0, cap - used)
    percent = 100.0 if cap <= 0 else min(100.0, round(used * 100.0 / cap, 2))
    return CompanionBudgetOut(
        used=used,
        cap=cap,
        remaining=remaining,
        percent=percent,
        exhausted=used >= cap,
        period=window.period,
        resets_at=window.next_start,
    )


async def notify_cap_reached(partner_id: uuid.UUID, window: MonthWindow) -> None:
    """Aviso una vez por partner y mes. Nunca rompe un run."""
    from nexus_api.db.base import get_sessionmaker

    try:
        sm = get_sessionmaker()
        async with sm() as session, session.begin():
            session.add(
                ConsoleNotification(
                    partner_id=partner_id,
                    kind=COMPANION_CAP_REACHED,
                    severity=NotificationSeverity.WARNING.value,
                    payload={"period": window.period},
                    dedupe_key=f"partner:{partner_id}:companion_cap:{window.period}",
                )
            )
    except IntegrityError:
        pass  # ya avisado este mes
    except Exception:  # pragma: no cover - un aviso no puede tumbar un turno
        log.exception("console.companion.cap_notify_failed", partner_id=str(partner_id))


@router.get("/companion/budget", response_model=CompanionBudgetOut)
async def get_budget(
    caller: CompanionCaller = Depends(companion_caller()),
    session: AsyncSession = Depends(get_db_session),
) -> CompanionBudgetOut:
    """Gasto del Companion del partner en el mes en curso, en tokens (C9)."""
    window = month_window()
    used = await partner_companion_tokens_used(session, caller.partner.id, window)
    return budget_out(used, caller.partner.companion_monthly_token_cap, window)


# ── hilos ──────────────────────────────────────────────────────────────


@router.get("/companion/threads", response_model=list[CompanionThreadOut])
async def list_threads(
    caller: CompanionCaller = Depends(companion_caller()),
    session: AsyncSession = Depends(get_db_session),
    include_archived: bool = Query(default=False),
    limit: int = Query(default=50, ge=1, le=200),
) -> list[CompanionThreadOut]:
    """Los hilos del miembro que llama (RLS por principal)."""
    async with session.begin():
        await apply_principal_to_session(session, caller.principal_id)
        stmt = sa.select(CompanionThread).order_by(CompanionThread.updated_at.desc()).limit(limit)
        if not include_archived:
            stmt = stmt.where(CompanionThread.archived_at.is_(None))
        rows = list((await session.execute(stmt)).scalars().all())
        return [_thread_out(t, await _client_ref_of(session, t)) for t in rows]


@router.post(
    "/companion/threads",
    response_model=CompanionThreadOut,
    status_code=status.HTTP_201_CREATED,
    responses={404: {"description": "Unknown client reference."}},
)
async def create_thread(
    body: CompanionThreadCreateIn,
    caller: CompanionCaller = Depends(companion_caller()),
    session: AsyncSession = Depends(get_db_session),
) -> CompanionThreadOut:
    """Un hilo nuevo, opcionalmente atado a un cliente del partner."""
    tenant_id: uuid.UUID | None = None
    if body.client_ref is not None:
        mapping = await resolve_mapping(session, caller.principal, body.client_ref)
        tenant_id = mapping.tenant_id

    async with session.begin():
        await apply_principal_to_session(session, caller.principal_id)
        thread = CompanionThread(
            principal_id=caller.principal_id,
            partner_id=caller.partner.id,
            tenant_id=tenant_id,
            title=body.title,
            mode=body.mode,
        )
        session.add(thread)
        await session.flush()
        await session.refresh(thread)
        return _thread_out(thread, body.client_ref)


@router.patch("/companion/threads/{thread_id}", response_model=CompanionThreadOut)
async def patch_thread(
    body: CompanionThreadPatchIn,
    thread_id: Annotated[uuid.UUID, Path(...)],
    caller: CompanionCaller = Depends(companion_caller()),
    session: AsyncSession = Depends(get_db_session),
) -> CompanionThreadOut:
    """Renombrar, archivar/desarchivar o cambiar el modo de un hilo propio.

    El cambio de modo (Consultar ↔ Construir) es un acto del usuario y por
    eso es un endpoint, no algo que el modelo pueda decidir.
    """
    if body.title is None and body.archived is None and body.mode is None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="At least one of title, archived or mode must be set",
        )
    async with session.begin():
        await apply_principal_to_session(session, caller.principal_id)
        thread = await _thread_row(session, thread_id, caller.principal_id)
        if body.title is not None:
            thread.title = body.title
        if body.mode is not None:
            thread.mode = body.mode
        if body.archived is not None:
            if body.archived and thread.archived_at is None:
                thread.archived_at = sa.func.now()
            elif not body.archived and thread.archived_at is not None:
                thread.archived_at = None
        thread.updated_at = sa.func.now()
        await session.flush()
        await session.refresh(thread)
        return _thread_out(thread, await _client_ref_of(session, thread))


# ── runs ───────────────────────────────────────────────────────────────


async def _next_message_seq(session: AsyncSession, thread_id: uuid.UUID) -> int:
    current = await session.scalar(
        sa.select(sa.func.coalesce(sa.func.max(CompanionMessage.seq), 0)).where(
            CompanionMessage.thread_id == thread_id
        )
    )
    return int(current or 0) + 1


@router.post(
    "/companion/threads/{thread_id}/runs",
    response_model=CompanionRunStartOut,
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        429: {"description": "Monthly Companion token cap reached (Retry-After set)."},
        409: {"description": "Thread is archived."},
    },
)
async def start_run(
    body: CompanionRunStartIn,
    response: Response,
    thread_id: Annotated[uuid.UUID, Path(...)],
    caller: CompanionCaller = Depends(companion_caller()),
    session: AsyncSession = Depends(get_db_session),
    redis: Redis = Depends(get_redis),
) -> CompanionRunStartOut:
    """Un turno: tope → persistir el mensaje y la fila del run → lanzar la
    tarea → **202 y a otra cosa**.

    El 202 es el punto de todo esto: el trabajo sigue en AWS aunque el
    navegador se cierre. El cliente abre luego el stream (o pide el
    historial) con el ``run_id``.
    """
    settings = get_settings()
    if not await allow(
        redis,
        key=f"console:companion_run:{caller.principal.user_id}",
        per_minute=settings.companion_runs_per_minute,
        surface="console",
    ):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many Companion turns — slow down for a minute.",
        )

    partner = caller.partner
    window = month_window()
    used_before = await partner_companion_tokens_used(session, partner.id, window)
    cap = partner.companion_monthly_token_cap
    if used_before >= cap:
        await notify_cap_reached(partner.id, window)
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"Companion token cap reached for {window.period}: {used_before:,} of "
                f"{cap:,} tokens used. The cap resets on "
                f"{window.next_start:%Y-%m-%d} (UTC); contact Auphere to raise it."
            ),
            headers={"Retry-After": str(retry_after_seconds(window))},
        )

    principal_id = caller.principal_id
    with principal_context(principal_id):
        async with session.begin():
            await apply_principal_to_session(session, principal_id)
            thread = await _thread_row(session, thread_id, principal_id)
            if thread.archived_at is not None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT, detail="Thread is archived"
                )
            run = CompanionRun(thread_id=thread.id, principal_id=principal_id, status=RUN_RUNNING)
            session.add(run)
            await session.flush()
            session.add(
                CompanionMessage(
                    thread_id=thread.id,
                    run_id=run.id,
                    seq=await _next_message_seq(session, thread.id),
                    role="user",
                    content=body.prompt,
                )
            )
            thread.last_run_at = sa.func.now()
            thread.updated_at = sa.func.now()
            await session.flush()
            await session.refresh(run)
            run_id = run.id
            tenant_id = thread.tenant_id
            history = await _thread_history(session, thread.id, exclude_run=run_id)

    driver = _make_driver(
        principal=caller.principal,
        thread_id=thread_id,
        run_id=run_id,
        tenant_id=tenant_id,
        user_message=body.prompt,
        page_context=body.page_context,
        history=history,
        used_before=used_before,
        cap=cap,
        window=window,
    )
    await streaming.start_run(
        redis=redis,
        run_id=run_id,
        thread_id=thread_id,
        principal_id=principal_id,
        driver=driver,
        on_complete=_make_on_complete(
            principal_id=principal_id,
            partner_id=partner.id,
            used_before=used_before,
            cap=cap,
            window=window,
        ),
    )
    response.headers["Cache-Control"] = "no-store"
    return CompanionRunStartOut(run_id=run_id, thread_id=thread_id, status=RUN_RUNNING)


async def _thread_history(
    session: AsyncSession, thread_id: uuid.UUID, *, exclude_run: uuid.UUID | None = None
) -> list[dict[str, Any]]:
    """Turnos anteriores del hilo, en forma de mensajes de proveedor.

    Solo ``user`` y ``assistant``: el razonamiento no se persiste y los
    mensajes de sistema se reconstruyen en cada turno (el prompt estable
    tiene que ser idéntico byte a byte para que el caché encaje).
    """
    stmt = (
        sa.select(CompanionMessage.role, CompanionMessage.content)
        .where(
            CompanionMessage.thread_id == thread_id,
            CompanionMessage.role.in_(("user", "assistant")),
        )
        .order_by(CompanionMessage.seq)
    )
    if exclude_run is not None:
        stmt = stmt.where(
            sa.or_(CompanionMessage.run_id.is_(None), CompanionMessage.run_id != exclude_run)
        )
    rows = (await session.execute(stmt)).all()
    return [{"role": role, "content": content} for role, content in rows if content]


def _make_driver(
    *,
    principal: ConsolePrincipal,
    thread_id: uuid.UUID,
    run_id: uuid.UUID,
    tenant_id: uuid.UUID | None,
    user_message: str,
    page_context: dict[str, Any] | None,
    history: list[dict[str, Any]],
    used_before: int,
    cap: int,
    window: MonthWindow,
) -> streaming.CompanionDriver:
    """El driver: mueve el grafo y vuelca sus eventos al log durable."""

    async def _driver(handle: streaming.CompanionRunHandle) -> None:
        import contextlib as _contextlib

        from nexus_worker.metering.collector import SOURCE_COMPANION, usage_turn

        graph = _get_companion_graph()
        state = {
            "thread_id": str(thread_id),
            "principal": {
                "role": principal.role,
                "partner": principal.partner.slug,
                "permissions": sorted(principal.permissions),
            },
            "page_context": page_context,
            "history": history,
            "user_message": user_message,
            "total_input_tokens": 0,
            "total_output_tokens": 0,
        }
        config = {"configurable": {"thread_id": str(thread_id)}}

        async with _contextlib.AsyncExitStack() as stack:
            # ``usage_records`` exige ``tenant_id``, así que un hilo sin
            # cliente no deja fila ahí. No es un olvido: el tope se mide en
            # ``companion.runs``, que siempre existe, y relajar la columna a
            # NULL rompería la policy RLS de una tabla particionada de alta
            # escritura para alimentar un desglose de panel.
            if tenant_id is not None:
                await stack.enter_async_context(
                    usage_turn(
                        tenant_id=tenant_id,
                        turn_id=str(run_id),
                        source=SOURCE_COMPANION,
                    )
                )
            async for event in graph.astream_events(state, config=config, version="v2"):
                if event.get("event") != "on_custom_event":
                    continue
                name = str(event.get("name") or "")
                data = event.get("data")
                if not isinstance(data, dict):
                    continue
                if name == "cost.updated":
                    handle.total_input_tokens += int(data.get("input_tokens") or 0)
                    handle.total_output_tokens += int(data.get("output_tokens") or 0)
                    handle.model = data.get("model") or handle.model
                if name == "context.updated":
                    handle.last_input_tokens = int(data.get("input_tokens") or 0)
                if name == "text.delta":
                    handle.extras.setdefault("answer", []).append(str(data.get("text") or ""))
                try:
                    await handle.emit(name, data)
                except streaming.UnknownCompanionEvent:
                    # El grafo emitió algo fuera del catálogo. Se registra y
                    # se sigue: el turno del usuario no se tira por un
                    # evento de telemetría que nadie declaró.
                    log.warning("companion.event.unknown", sse_event=name, run_id=str(run_id))

        # La barra del partner se mueve sin polling: lo gastado antes + este
        # turno. Va ANTES del evento terminal para que el cajón lo pinte en
        # el mismo cierre.
        snapshot = budget_out(
            used_before + handle.total_input_tokens + handle.total_output_tokens, cap, window
        )
        await handle.emit(
            "budget.updated",
            {
                "used": snapshot.used,
                "cap": snapshot.cap,
                "remaining": snapshot.remaining,
                "percent": snapshot.percent,
                "exhausted": snapshot.exhausted,
                "period": snapshot.period,
                "resets_at": snapshot.resets_at.isoformat(),
            },
        )

    return _driver


def _make_on_complete(
    *,
    principal_id: str,
    partner_id: uuid.UUID,
    used_before: int,
    cap: int,
    window: MonthWindow,
) -> streaming.OnComplete:
    async def _on_complete(handle: streaming.CompanionRunHandle) -> None:
        answer = "".join(handle.extras.get("answer") or [])
        await _finalise_run(
            principal_id=principal_id,
            run_id=handle.run_id,
            thread_id=handle.thread_id,
            status=handle.final_status or RUN_ERROR,
            error=handle.final_error,
            input_tokens=handle.total_input_tokens,
            output_tokens=handle.total_output_tokens,
            model=handle.model,
            answer=answer,
        )
        if used_before + handle.total_input_tokens + handle.total_output_tokens >= cap:
            await notify_cap_reached(partner_id, window)

    return _on_complete


async def _finalise_run(
    *,
    principal_id: str,
    run_id: uuid.UUID,
    thread_id: uuid.UUID,
    status: str,
    error: str | None,
    input_tokens: int,
    output_tokens: int,
    model: str | None,
    answer: str,
) -> None:
    """Cierra la fila del run y persiste la respuesta.

    Corre FUERA de cualquier transacción de petición: el 202 se devolvió
    hace rato. Abre su propia sesión y aplica el ámbito del principal para
    que la RLS deje pasar el UPDATE.

    La respuesta se guarda aunque el run fallara a mitad: lo que el
    Companion alcanzó a decir es parte del hilo, y borrarlo dejaría al
    usuario con una conversación que no coincide con lo que vio.
    """
    from nexus_api.db.base import get_sessionmaker

    try:
        sm = get_sessionmaker()
        async with sm() as session, session.begin():
            await apply_principal_to_session(session, principal_id)
            run = await session.get(CompanionRun, run_id)
            if run is None:
                log.warning("companion.run.finalise_missing", run_id=str(run_id))
                return
            run.status = status
            run.error = error
            run.ended_at = sa.func.now()
            run.input_tokens = input_tokens
            run.output_tokens = output_tokens
            if answer:
                session.add(
                    CompanionMessage(
                        thread_id=thread_id,
                        run_id=run_id,
                        seq=await _next_message_seq(session, thread_id),
                        role="assistant",
                        content=answer,
                        input_tokens=input_tokens,
                        output_tokens=output_tokens,
                        model=model,
                    )
                )
    except Exception:  # pragma: no cover - defensivo
        log.exception("companion.run.finalise_failed", run_id=str(run_id))


# ── grafo (cacheado por proceso) ───────────────────────────────────────

_graph: Any = None


def _get_companion_graph() -> Any:
    """Compila el grafo una vez por proceso y lo reutiliza.

    El grafo compilado no tiene estado: cada ``astream_events`` trae el
    suyo. Comparte el ``AsyncPostgresSaver`` del proceso para que la
    reanudación siga siendo durable entre reinicios. Los imports viven
    dentro para que el arranque del módulo no pague LiteLLM ni LangGraph.
    """
    global _graph
    if _graph is not None:
        return _graph

    from nexus_worker.runtime.companion import build_companion_graph
    from nexus_worker.runtime.llm import LiteLLMProvider

    from nexus_api.core.qa_checkpointer import get_qa_checkpointer

    settings = get_settings()
    _graph = build_companion_graph(
        provider=LiteLLMProvider(timeout_s=settings.llm_improve_timeout_s),
        model=settings.llm_companion_model,
        checkpointer=get_qa_checkpointer(),
    )
    return _graph


def reset_graph_cache_for_tests() -> None:
    global _graph
    _graph = None


def set_graph_for_tests(graph: Any) -> None:
    """Inyecta un grafo compilado (proveedor en memoria) sin tocar red."""
    global _graph
    _graph = graph


# ── historial, stream y cancelación ────────────────────────────────────


def _is_expired(run: CompanionRun) -> bool:
    """Un run ``running`` que ya pasó su techo de duración está muerto.

    No se puede saber SI el proceso que lo ejecutaba sigue vivo, pero sí que
    ningún run legítimo dura más que su propio máximo. Es lo que evita que
    el cajón se quede haciendo ping para siempre contra un turno huérfano,
    sin tener que arriesgar el barrido indiscriminado que rompería un
    despliegue rodante.
    """
    started = run.started_at
    if started is None:  # pragma: no cover - la columna es NOT NULL
        return False
    if started.tzinfo is None:  # pragma: no cover - la columna es timestamptz
        started = started.replace(tzinfo=UTC)
    return (datetime.now(UTC) - started).total_seconds() > get_settings().companion_run_max_seconds


async def _owned_run(session: AsyncSession, run_id: uuid.UUID, principal_id: str) -> CompanionRun:
    async with session.begin():
        await apply_principal_to_session(session, principal_id)
        run = await session.get(CompanionRun, run_id)
        if run is None or run.principal_id != principal_id:
            raise _unknown_run()
        return run


@router.get("/companion/runs/{run_id}/events", response_model=CompanionEventsOut)
async def get_run_events(
    run_id: Annotated[uuid.UUID, Path(...)],
    caller: CompanionCaller = Depends(companion_caller()),
    session: AsyncSession = Depends(get_db_session),
    redis: Redis = Depends(get_redis),
    since_seq: int = Query(default=0, ge=0),
    limit: int = Query(default=500, ge=1, le=2000),
) -> CompanionEventsOut:
    """Historial del run por REST — la otra mitad de la reanudación.

    El patrón que recomienda Anthropic para reconectar sin pérdida es
    **abrir el stream, listar el historial y deduplicar por id de evento**.
    Con solo el stream, un ``resume.gap`` avisa del hueco pero no ofrece de
    dónde rellenarlo; este endpoint es de dónde.
    """
    await _owned_run(session, run_id, caller.principal_id)
    events, available_from = await streaming.read_events(
        redis, run_id, since_seq=since_seq, limit=limit
    )
    next_seq = events[-1].seq if events else since_seq
    return CompanionEventsOut(
        run_id=run_id,
        events=[CompanionEventOut(seq=e.seq, event=e.event, data=e.data) for e in events],
        next_seq=next_seq,
        available_from=available_from,
    )


@router.get("/companion/runs/{run_id}/stream")
async def stream_run(
    run_id: Annotated[uuid.UUID, Path(...)],
    caller: CompanionCaller = Depends(companion_caller()),
    session: AsyncSession = Depends(get_db_session),
    redis: Redis = Depends(get_redis),
    since_seq: int = Query(default=0, ge=0),
) -> StreamingResponse:
    """SSE en vivo del run, desde ``since_seq``.

    La propiedad se comprueba en una transacción corta que **cierra antes**
    de que empiece el stream: mantener una transacción abierta durante
    minutos ataría una conexión del pool a un navegador.
    """
    await _owned_run(session, run_id, caller.principal_id)
    principal_id = caller.principal_id

    async def _terminal_check() -> str | None:
        """¿Este run ya no va a producir nada más?

        Dos formas de estarlo, y las dos pasan cuando el proceso que lo
        ejecutaba murió: la fila ya está cerrada (el reaper llegó antes), o
        sigue en ``running`` pero pasó su techo de duración. Sin esta salida
        el cajón se quedaría haciendo ping para siempre contra un turno que
        ya no ejecuta nadie.
        """
        from nexus_api.db.base import get_sessionmaker

        try:
            sm = get_sessionmaker()
            async with sm() as s, s.begin():
                await apply_principal_to_session(s, principal_id)
                row = await s.get(CompanionRun, run_id)
                if row is None:
                    return None
                if row.status in TERMINAL_RUN_STATUSES:
                    return str(row.status)
                if _is_expired(row):
                    return RUN_INTERRUPTED
        except Exception:  # pragma: no cover - defensivo
            log.warning("companion.terminal_check_failed", run_id=str(run_id))
        return None

    return StreamingResponse(
        streaming.subscribe(redis, run_id, since_seq=since_seq, terminal_check=_terminal_check),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-store",
            "X-Accel-Buffering": "no",
            "Connection": "keep-alive",
        },
    )


@router.delete("/companion/runs/{run_id}", status_code=status.HTTP_204_NO_CONTENT)
async def cancel_run(
    run_id: Annotated[uuid.UUID, Path(...)],
    caller: CompanionCaller = Depends(companion_caller()),
    session: AsyncSession = Depends(get_db_session),
    redis: Redis = Depends(get_redis),
) -> None:
    """Detener el run. **Esta es la única forma de cancelar.**

    Cerrar el ``fetch`` del navegador no llega hasta aquí: el trabajo vive
    en el servidor por diseño (C1). El botón *Detener* del cajón tiene que
    llamar a este endpoint, no limitarse a abortar la petición.
    """
    await _owned_run(session, run_id, caller.principal_id)
    await streaming.cancel(redis, run_id)


# ── reaper de arranque ─────────────────────────────────────────────────


async def reap_stale_runs(*, older_than_seconds: float | None = None) -> int:
    """Cierra los runs que quedaron en ``running`` de un proceso muerto.

    Se llama en el arranque de la API. Sin esto, un reinicio a mitad de run
    deja la fila abierta para siempre: el hilo se ve "trabajando" en la
    lista, el tope mensual no cuenta esos tokens y el cajón que reconecta
    espera eventos que nadie va a escribir.

    **El corte es la duración máxima de un run, no cero.** Un proceso que
    arranca no sabe qué runs son suyos y cuáles está ejecutando otra réplica
    ahora mismo: barrer todo lo que esté en ``running`` mataría, en cada
    despliegue rodante, los turnos vivos de la réplica que todavía no se ha
    apagado. En cambio, un run más viejo que su propio techo de duración
    está muerto lo ejecute quien lo ejecute — eso sí se puede afirmar sin
    saber de quién es.

    El hueco que deja (un run huérfano hace diez segundos sigue en
    ``running`` hasta cumplir su techo) lo cubre :func:`_is_expired` por el
    lado del lector, que es donde importa: el usuario ve el cierre en su
    stream sin esperar a que nadie reinicie nada.

    Corre con el rol dueño (sin ``app.principal_id``) a propósito: es
    mantenimiento de plataforma sobre runs de todos los principales, no una
    lectura en nombre de nadie. Es la única consulta del módulo que lo hace.
    """
    from nexus_api.core.redis_client import get_redis as _get_redis
    from nexus_api.db.base import get_sessionmaker

    settings = get_settings()
    cutoff = datetime.now(UTC).timestamp() - (
        older_than_seconds if older_than_seconds is not None else settings.companion_run_max_seconds
    )
    cutoff_dt = datetime.fromtimestamp(cutoff, tz=UTC)

    sm = get_sessionmaker()
    reaped: list[uuid.UUID] = []
    async with sm() as session, session.begin():
        rows = (
            await session.execute(
                sa.select(CompanionRun.id).where(
                    CompanionRun.status == RUN_RUNNING,
                    CompanionRun.started_at < cutoff_dt,
                )
            )
        ).scalars()
        for run_id in rows:
            reaped.append(run_id)
        if reaped:
            await session.execute(
                sa.update(CompanionRun)
                .where(CompanionRun.id.in_(reaped))
                .values(
                    status=RUN_INTERRUPTED,
                    ended_at=sa.func.now(),
                    error="La API se reinició mientras este turno estaba en curso.",
                )
            )
    if not reaped:
        return 0
    redis = _get_redis()
    for run_id in reaped:
        try:
            await streaming.append_terminal_event(redis, run_id, status=RUN_INTERRUPTED)
        except Exception:  # pragma: no cover - el log puede haber expirado
            log.warning("companion.reaper.log_closed_failed", run_id=str(run_id))
    log.info("companion.reaper.closed", runs=len(reaped))
    return len(reaped)


__all__ = [
    "COMPANION_CAP_REACHED",
    "budget_out",
    "companion_principal_id",
    "partner_companion_tokens_used",
    "reap_stale_runs",
    "reset_graph_cache_for_tests",
    "router",
    "set_graph_for_tests",
]
