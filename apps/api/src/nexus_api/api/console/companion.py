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
from datetime import UTC, datetime, timedelta
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
from nexus_api.companion.tools.actions import (
    DECISION_STATUS,
    STATUS_APPLIED,
    STATUS_EXPIRED,
    STATUS_PROPOSED,
    expires_at_of,
    load_action,
)
from nexus_api.companion.tools.support import SUPPORT_KINDS
from nexus_api.config import get_settings
from nexus_api.core.console_auth import ConsolePrincipal, require_console_principal
from nexus_api.core.otel_metrics import record_companion, record_companion_turn
from nexus_api.core.principal_context import (
    apply_principal_to_session,
    principal_context,
)
from nexus_api.core.rate_limit import allow
from nexus_api.db.models import Partner, PartnerMembership, PartnerTenant
from nexus_api.db.models.companion import (
    RUN_COMPLETED,
    RUN_ERROR,
    RUN_INTERRUPTED,
    RUN_PAUSED,
    RUN_RUNNING,
    TERMINAL_RUN_STATUSES,
    CompanionAction,
    CompanionMessage,
    CompanionRun,
    CompanionThread,
)
from nexus_api.db.models.console_notification import (
    ConsoleNotification,
    NotificationSeverity,
)

from .deps import resolve_mapping
from .playground import MonthWindow, month_window
from .schemas_companion import (
    CompanionActionOut,
    CompanionBudgetOut,
    CompanionEventOut,
    CompanionEventsOut,
    CompanionResumeIn,
    CompanionResumeOut,
    CompanionRunStartIn,
    CompanionRunStartOut,
    CompanionRunSummaryOut,
    CompanionThreadCreateIn,
    CompanionThreadOut,
    CompanionThreadPatchIn,
    CompanionThreadRunsOut,
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


def _companion_disabled() -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail={
            "code": "companion_disabled",
            "detail": (
                "The Companion is not enabled for this partner yet. Ask Auphere to turn it on."
            ),
        },
    )


def companion_caller(*, write: bool = True) -> Callable[..., Awaitable[CompanionCaller]]:
    """La puerta del Companion: ``companion:use`` **Y** la bandera (§10).

    Con ``write=False`` solo se exige el permiso. Es lo que hace que apagar
    la bandera **no borre la historia**: un hilo que ya existe se sigue
    leyendo, con sus runs y sus eventos, porque lo que pasó pasó y esconderlo
    sería peor que no haberlo permitido. Lo que se cierra es empezar trabajo
    nuevo.

    ``DELETE …/runs/{id}`` va también sin bandera, y es deliberado: si el
    interruptor se apaga con un turno en vuelo, el botón *Detener* tiene que
    seguir funcionando. Un freno de emergencia que no se puede pisar es peor
    que no tenerlo.
    """
    principal_dep = require_console_principal("companion:use")

    async def _dependency(
        principal: ConsolePrincipal = Depends(principal_dep),
    ) -> CompanionCaller:
        if write and not principal.partner.companion_enabled:
            raise _companion_disabled()
        return CompanionCaller(principal=principal)

    return _dependency


#: Azúcar para las rutas de lectura. Se nombra aparte para que en cada
#: endpoint se lea de un vistazo de qué lado de la bandera está.
def companion_reader() -> Callable[..., Awaitable[CompanionCaller]]:
    return companion_caller(write=False)


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
    ref = await session.scalar(
        sa.select(PartnerTenant.external_client_ref).where(
            PartnerTenant.partner_id == thread.partner_id,
            PartnerTenant.tenant_id == thread.tenant_id,
        )
    )
    return str(ref) if ref is not None else None


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


def _budget_paused(used: int, cap: int, window: MonthWindow) -> HTTPException:
    """El tope mensual alcanzado: **409, no 429** (§6.2 de CONTRACT-V2).

    429 significa *vuelve a intentarlo*, y aquí reintentar no sirve de nada:
    no pasa el tiempo, pasa que alguien sube el tope. Un ``Retry-After``
    sería mentira — le diría al navegador que espere un mes.

    El cuerpo lleva la instantánea del presupuesto para que la interfaz
    pinte la explicación sin una segunda petición, y para que lo que pinte
    sea un **estado de tope alcanzado y no un error**: el hilo sigue ahí, la
    historia sigue ahí y la confirmación pendiente —si la había— sigue
    siendo respondible. Rojo de error para algo que se resuelve subiendo un
    número enseña a temer la herramienta.
    """
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "code": "budget_paused",
            "used": used,
            "cap": cap,
            "period": window.period,
            "resets_at": window.next_start.isoformat(),
        },
    )


@router.get("/companion/budget", response_model=CompanionBudgetOut)
async def get_budget(
    caller: CompanionCaller = Depends(companion_reader()),
    session: AsyncSession = Depends(get_db_session),
) -> CompanionBudgetOut:
    """Gasto del Companion del partner en el mes en curso, en tokens (C9)."""
    window = month_window()
    used = await partner_companion_tokens_used(session, caller.partner.id, window)
    return budget_out(used, caller.partner.companion_monthly_token_cap, window)


# ── hilos ──────────────────────────────────────────────────────────────


@router.get("/companion/threads", response_model=list[CompanionThreadOut])
async def list_threads(
    caller: CompanionCaller = Depends(companion_reader()),
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
        # Denominador de la primera razón del §17 ("tareas completadas sin
        # salir del cajón / hilos abiertos").
        record_companion("companion.thread.opened")
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


def _is_parked() -> Any:
    """Predicado SQL: «este run está esperando a que una persona decida».

    Un run aparcado sigue en ``running`` porque el grafo no ha terminado —
    está parado en un ``interrupt()`` y la fila es lo que lo dice—, pero **no
    está trabajando**: no consume una tarea, no gasta y no puede fallar.
    Contarlo como trabajo en vuelo tendría dos consecuencias, las dos
    absurdas: el tercer hilo pendiente de confirmación bloquearía al miembro
    entero, y el techo de duración (300 s) mataría cada espera humana mucho
    antes de que la propuesta caducara a los quince minutos.

    Es una subconsulta y no una columna nueva a propósito: el estado de la
    espera lo define la acción, y duplicarlo en el run crearía la
    posibilidad de que las dos filas discrepen.
    """
    return sa.exists(
        sa.select(sa.literal(1))
        .select_from(CompanionAction)
        .where(
            CompanionAction.run_id == CompanionRun.id,
            CompanionAction.status == STATUS_PROPOSED,
        )
    )


async def _guard_concurrency(session: AsyncSession, principal_id: str) -> None:
    """Rechaza el turno si el miembro ya tiene demasiados runs EN VUELO.

    Por qué existe además del límite por minuto: son cosas distintas. El
    limitador de ráfaga acota cuántos turnos se *arrancan*; el techo mensual
    acota cuánto se *gasta* y se mide sobre runs ya cerrados. Ninguno de los
    dos acota el trabajo simultáneo, y un run del Companion dura minutos:
    con 15 arranques por minuto y un techo de 300 s, un solo miembro podía
    tener del orden de 75 tareas vivas a la vez —cada una con su conexión,
    su tarea de asyncio y su gasto en vuelo— sin cruzar ningún límite.

    El recuento sale de ``companion.runs`` y no de un contador en Redis por
    una razón concreta: un contador que se incrementa al arrancar y se
    decrementa al terminar se queda **alto para siempre** si el proceso
    muere entre las dos cosas, y entonces el miembro se queda bloqueado sin
    que nadie sepa por qué. La tabla se cura sola: el reaper cierra los
    huérfanos y, mientras tanto, esta consulta ya descarta los que pasaron
    su propio techo de duración.

    El ``pg_advisory_xact_lock`` por miembro es lo que hace exacto el tope.
    Sin él, dos POST simultáneos leen el mismo recuento y los dos pasan; con
    él, el segundo espera al COMMIT del primero. El bloqueo es por
    principal, dura lo que la transacción de arranque (milisegundos) y no
    toca a ningún otro miembro.
    """
    settings = get_settings()
    cap = settings.companion_max_concurrent_runs
    if cap <= 0:  # pragma: no cover - configuración de emergencia
        return
    await session.execute(
        sa.text("SELECT pg_advisory_xact_lock(hashtext(:key))"),
        {"key": f"companion:concurrency:{principal_id}"},
    )
    cutoff = datetime.now(UTC) - timedelta(seconds=settings.companion_run_max_seconds)
    live = int(
        await session.scalar(
            sa.select(sa.func.count())
            .select_from(CompanionRun)
            .where(
                CompanionRun.status == RUN_RUNNING,
                CompanionRun.started_at >= cutoff,
                sa.not_(_is_parked()),
            )
        )
        or 0
    )
    if live >= cap:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=(
                f"You already have {live} Companion turns running (limit {cap}). "
                "Wait for one to finish, or stop it with "
                "DELETE /console/companion/runs/{run_id}."
            ),
        )


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
        429: {"description": "Too many turns per minute, or too many already running."},
        409: {
            "description": (
                "Thread is archived, or the partner is over its monthly Companion "
                "token cap (``detail.code = 'budget_paused'``). The pause is derived: "
                "raising the cap resumes every thread of the partner at once."
            )
        },
        403: {"description": "The Companion is not enabled for this partner."},
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
        raise _budget_paused(used_before, cap, window)

    principal_id = caller.principal_id
    with principal_context(principal_id):
        async with session.begin():
            await apply_principal_to_session(session, principal_id)
            thread = await _thread_row(session, thread_id, principal_id)
            if thread.archived_at is not None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT, detail="Thread is archived"
                )
            await _guard_concurrency(session, principal_id)
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
            mode = thread.mode
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
        mode=mode,
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


async def _budget_gate(
    handle: streaming.CompanionRunHandle,
    *,
    used_before: int,
    cap: int,
    window: MonthWindow,
) -> bool:
    """¿Ha cruzado este turno el tope mensual del partner? (§6.3)

    Devuelve ``True`` una sola vez: la marca en ``extras`` es lo que impide
    que un turno con varias llamadas al modelo emita dos ``budget.paused``.

    Al tripar se emite el evento y el turno se corta, pero **no se pierde
    nada**: la respuesta parcial ya está acumulada en ``extras['answer']``,
    los tokens en el ``handle`` y la historia en la base. Un hilo pausado
    que pierde la historia no es una pausa, es un fallo con otro nombre.
    """
    if handle.extras.get("budget_paused"):
        return True
    used = used_before + handle.total_input_tokens + handle.total_output_tokens
    if used < cap:
        return False
    handle.extras["budget_paused"] = True
    await handle.emit(
        "budget.paused",
        {
            "used": used,
            "cap": cap,
            "period": window.period,
            "resets_at": window.next_start.isoformat(),
            # Único valor hoy; el enum queda abierto porque el día que haya
            # tope por miembro habrá que distinguirlos, y añadir la clave
            # entonces sería un cambio de contrato en caliente.
            "scope": "partner",
        },
    )
    log.info(
        "companion.budget.paused",
        run_id=str(handle.run_id),
        thread_id=str(handle.thread_id),
        used=used,
        cap=cap,
        period=window.period,
    )
    return True


async def _emit_support_ticket(
    handle: streaming.CompanionRunHandle,
    action_id: uuid.UUID | None,
) -> None:
    """``support.ticket`` (§4.5), si esta continuación aplicó un ticket.

    ``action_id`` solo llega cuando el ``resume`` confirmó una acción de
    soporte, así que un turno normal no paga ni una consulta. El
    identificador y la expectativa salen de ``companion.actions.result``,
    donde los dejó la lista blanca ``APPLY_ECHO`` al aplicar: nacen en la
    respuesta del endpoint y sin este rodeo no habría de dónde sacarlos
    para pintar la tarjeta.

    Nunca rompe el turno: si la fila no se pudo leer, el ticket existe
    igual —está en la auditoría, en la notificación y en el log— y lo único
    que falta es el adorno de la tarjeta.
    """
    if action_id is None or handle.extras.get("support_emitted"):
        return
    handle.extras["support_emitted"] = True
    try:
        from nexus_api.db.base import get_sessionmaker

        sm = get_sessionmaker()
        async with sm() as session, session.begin():
            await apply_principal_to_session(session, handle.principal_id)
            action = await session.get(CompanionAction, action_id)
            if action is None or action.status != STATUS_APPLIED:
                return
            result = dict(action.result or {})
            ticket_ref = str(result.get("ticket_ref") or "")
            if not ticket_ref:
                return
            payload = {
                "action_id": str(action_id),
                "ticket_ref": ticket_ref,
                "category": str(result.get("category") or ""),
                "topic": str(result.get("topic") or ""),
                "sla": str(result.get("sla") or ""),
            }
        await handle.emit("support.ticket", payload)
    except Exception:  # pragma: no cover - un adorno no tumba un turno
        log.exception("companion.support_ticket_event_failed", action_id=str(action_id))


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
    mode: str = "build",
    resume: dict[str, Any] | None = None,
    support_action: uuid.UUID | None = None,
) -> streaming.CompanionDriver:
    """El driver: mueve el grafo y vuelca sus eventos al log durable.

    Con ``resume`` puesto no arranca un turno: **reanuda** el grafo parado en
    el ``interrupt()`` de este hilo, con el valor de la decisión. Es el mismo
    código porque es el mismo trabajo — lo único que cambia es lo que se le
    entrega a LangGraph, y unificar los dos caminos evita que la medición del
    gasto o el cierre de la fila se hagan de dos maneras distintas.
    """

    async def _driver(handle: streaming.CompanionRunHandle) -> None:
        import contextlib as _contextlib

        from nexus_worker.metering.collector import SOURCE_COMPANION, usage_turn

        from nexus_api.companion.tools import CompanionToolbelt
        from nexus_api.core.console_auth import InProcessActor

        settings = get_settings()
        # Un juego de herramientas POR TURNO: lleva el sujeto de las
        # llamadas y el contador de consultas. Compartirlo entre runs sería
        # compartir la identidad de una persona con otra.
        toolbelt = CompanionToolbelt(
            actor=InProcessActor(
                user_id=principal.user_id,
                partner_id=principal.partner.id,
                jti=f"companion:{run_id}",
            ),
            max_calls=settings.companion_max_tool_calls_per_turn,
            timeout_s=settings.companion_tool_timeout_s,
            # El modo es del HILO y lo cambia la persona con un PATCH, nunca
            # el modelo: en ``consult`` el catálogo publicado son solo las
            # lecturas, así que no hay forma de que un texto convenza al
            # agente de proponer un cambio.
            mode=mode,
            principal_id=companion_principal_id(principal),
            thread_id=thread_id,
            run_id=run_id,
            action_ttl_seconds=settings.companion_action_ttl_seconds,
        )
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
        if resume is not None:
            from langgraph.types import Command

            # El estado no se reenvía: lo tiene el checkpoint. Mandarlo otra
            # vez sobrescribiría lo que el turno pausado había acumulado
            # —``tool_messages``, ``reads_done``, los contadores— y el nodo
            # de cierre respondería sin saber qué se leyó.
            entry: Any = Command(resume=resume)
        else:
            entry = state

        async with _contextlib.AsyncExitStack() as stack:
            await stack.enter_async_context(toolbelt)
            graph = _get_companion_graph(toolbelt)
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
            # ``aclosing`` y no un ``async for`` a secas: al tripar la puerta
            # del presupuesto se sale del bucle, y un generador que solo se
            # cierra cuando le toca al recolector es un turno que sigue
            # gastando un rato más.
            stream = graph.astream_events(entry, config=config, version="v2")
            async with _contextlib.aclosing(stream):
                async for event in stream:
                    if event.get("event") == "on_chain_end" and event.get("name") == "respond":
                        # El veredicto de R1 lo calcula el grafo (una sola vez,
                        # con el estado completo) y viaja en la salida del nodo
                        # de cierre. El driver solo lo recoge para meterlo en el
                        # evento terminal: así la métrica se toma en un punto
                        # que se ejecuta siempre.
                        output = (event.get("data") or {}).get("output")
                        if isinstance(output, dict):
                            handle.extras["unsupported"] = bool(output.get("unsupported"))
                        continue
                    if event.get("event") != "on_custom_event":
                        continue
                    name = str(event.get("name") or "")
                    data = event.get("data")
                    if not isinstance(data, dict):
                        continue
                    if name == "cost.updated":
                        handle.total_input_tokens += int(data.get("input_tokens") or 0)
                        handle.total_output_tokens += int(data.get("output_tokens") or 0)
                        handle.total_cache_read += int(data.get("cache_read") or 0)
                        handle.total_cache_write += int(data.get("cache_write") or 0)
                        handle.total_steps += int(data.get("steps") or 0)
                        handle.model = data.get("model") or handle.model
                    if name == "context.updated":
                        handle.last_input_tokens = int(data.get("input_tokens") or 0)
                    if name == "text.delta":
                        handle.extras.setdefault("answer", []).append(str(data.get("text") or ""))
                    if name == "hitl.requested":
                        # El grafo va a parar en el ``interrupt()`` justo después
                        # de esto. Se marca aquí y no leyendo la base al terminar
                        # porque es el único punto donde consta sin ambigüedad, y
                        # porque una consulta más por turno para saber algo que
                        # acaba de pasar delante es trabajo regalado.
                        handle.extras["awaiting_action"] = str(data.get("action_id") or "")
                        record_companion("companion.hitl.proposed")
                    if name == "hitl.resolved" and data.get("decision") == "cancel":
                        # La razón que MANDA del §17: por encima del 15 % el
                        # Companion propone mal, y proponer mal enseña a
                        # desconfiar de él.
                        record_companion("companion.hitl.cancelled")
                    if name == "verify.result":
                        record_companion("companion.verify.total")
                        if data.get("ok"):
                            record_companion("companion.task.completed")
                        else:
                            record_companion("companion.verify.failed")
                        # §4.5: el evento del ticket va DESPUÉS del 2xx de
                        # ``console.apply`` y ANTES de ``verify.result``. Como
                        # este bucle es secuencial, emitirlo aquí —antes de
                        # relanzar el que estamos mirando— cumple el orden por
                        # construcción y no por suerte.
                        await _emit_support_ticket(handle, support_action)
                    try:
                        await handle.emit(name, data)
                    except streaming.UnknownCompanionEvent:
                        # El grafo emitió algo fuera del catálogo. Se registra y
                        # se sigue: el turno del usuario no se tira por un
                        # evento de telemetría que nadie declaró.
                        log.warning("companion.event.unknown", sse_event=name, run_id=str(run_id))
                    if name == "cost.updated" and await _budget_gate(
                        handle,
                        used_before=used_before,
                        cap=cap,
                        window=window,
                    ):
                        # La puerta se comprueba cada vez que el turno reporta
                        # su gasto, y al tripar se sale del bucle: el
                        # generador se cierra y el grafo no vuelve a llamar al
                        # proveedor.
                        #
                        # **Hoy eso es una vez por turno, no una por llamada
                        # al modelo.** ``cost.updated`` lo emite el nodo
                        # ``respond`` con los totales acumulados
                        # (``runtime/companion/graph.py``), así que el corte
                        # llega al final del turno que cruza el tope, no en
                        # mitad de él. El efecto observable del §6.2 se cumple
                        # entero —409 al trabajo nuevo, 202 al cierre, la
                        # historia y los tokens conservados—; lo que no se
                        # cumple es el "como mucho una llamada de más" del
                        # §6.3: el exceso puede ser un turno entero.
                        #
                        # La puerta por llamada tiene que vivir donde se llama
                        # al modelo, que es la zona del grafo. Este bucle ya
                        # está escrito para aprovecharla el día que
                        # ``cost.updated`` se emita por llamada: la condición
                        # no cambia, solo se dispara antes.
                        break

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
        # La pausa por presupuesto MANDA sobre el aparcado del HITL: si el
        # turno se paró de verdad, no está esperando a nadie. Son dos
        # esperas distintas y confundirlas dejaría la fila en ``running``
        # para siempre, con un run que ya no va a continuar.
        paused = bool(handle.extras.get("budget_paused"))
        await _finalise_run(
            principal_id=principal_id,
            run_id=handle.run_id,
            thread_id=handle.thread_id,
            status=RUN_PAUSED if paused else (handle.final_status or RUN_ERROR),
            error=handle.final_error,
            input_tokens=handle.total_input_tokens,
            output_tokens=handle.total_output_tokens,
            model=handle.model,
            answer=answer,
            parked=(not paused) and bool(handle.extras.get("awaiting_action")),
        )
        # La medida del TURNO, que es la unidad sobre la que se fija la cuota.
        # Va después de ``_finalise_run`` a propósito: si la fila no se cerró,
        # el turno no se cuenta, y así el panel y la base no pueden discrepar.
        record_companion_turn(
            billable_tokens=handle.total_input_tokens + handle.total_output_tokens,
            cost_usd=await _turn_cost_usd(handle),
            steps=handle.total_steps,
        )
        if used_before + handle.total_input_tokens + handle.total_output_tokens >= cap:
            await notify_cap_reached(partner_id, window)

    return _on_complete


async def _turn_cost_usd(handle: streaming.CompanionRunHandle) -> float | None:
    """Lo que costó el turno, en dólares, o ``None`` si no se puede valorar.

    Las tarifas salen de ``model_profiles`` por el mismo catálogo cacheado que
    ya usa el medidor de ventana (``pricing.get_catalog``), así que no añade
    una consulta por turno ni una tabla de precios que mantener aparte — la
    que hay ya se mantiene, porque es con la que se factura a los clientes.

    Las cuatro componentes se valoran por separado **porque tienen precios
    distintos**: la lectura de caché cuesta una décima parte de la entrada y
    la escritura un 25 % más. Sumarlas antes de valorar —que es lo que hacía
    la cuota— es exactamente el error que convertía un turno de 25.000 tokens
    en uno de 135.000.

    Devuelve ``None`` y no cero cuando falta el modelo o la tarifa: un cero
    sería indistinguible de un turno gratis.
    """
    model = handle.model
    if not model:
        return None
    try:
        from nexus_worker.metering.pricing import get_catalog

        row = (await get_catalog()).get(model)
    except Exception as exc:  # pragma: no cover - defensivo
        log.warning("companion.turn_cost_unavailable", model=model, error=str(exc))
        return None
    if row is None:
        return None

    total = 0.0
    seen_any = False
    for tokens, rate in (
        (handle.total_input_tokens, row.input_per_mtok),
        (handle.total_output_tokens, row.output_per_mtok),
        (handle.total_cache_read, row.cache_read_per_mtok),
        (handle.total_cache_write, row.cache_write_per_mtok),
    ):
        if rate is None:
            continue
        seen_any = True
        total += float(rate) * tokens / 1_000_000
    return total if seen_any else None


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
    parked: bool = False,
) -> None:
    """Cierra la fila del run y persiste la respuesta.

    Con ``parked`` el run **no se cierra**: se guardan los tokens y lo que el
    Companion alcanzó a decir, y la fila sigue en ``running`` sin
    ``ended_at``. Es un turno que espera a una persona, no un turno
    terminado, y esa diferencia es la que hace que el cajón siga mostrando la
    tarjeta de confirmación en vez de dar el trabajo por hecho.

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
            if not parked:
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
_provider: Any = None


def _get_provider() -> Any:
    """El proveedor del proceso. Uno solo: no tiene estado por run y
    construirlo por turno solo añadiría trabajo."""
    global _provider
    if _provider is None:
        from nexus_worker.runtime.llm import LiteLLMProvider

        # ``cache_tail`` encendido SOLO aquí. El Companion es el único bucle
        # agéntico largo de la plataforma —hasta doce pasadas, con resultados
        # de herramienta de miles de tokens— y es donde el historial sin
        # cachear crece de forma cuadrática. El agente de cliente y los
        # playgrounds comparten la clase pero construyen su propio proveedor,
        # así que su comportamiento no cambia.
        _provider = LiteLLMProvider(timeout_s=get_settings().llm_improve_timeout_s, cache_tail=True)
    return _provider


def _get_companion_graph(toolbelt: Any = None) -> Any:
    """El grafo del turno.

    **Se compila por run cuando hay herramientas**, y no se cachea: el
    juego de herramientas lleva el sujeto de las llamadas y el contador de
    consultas del turno, así que compartirlo entre runs sería compartir la
    identidad de una persona con otra. Compilar es construir un objeto en
    memoria — microsegundos —, no un coste que valga la pena optimizar a
    ese precio.

    Sin herramientas se cachea, que es el camino de CO-01 y el de los tests
    que solo ejercitan el prompt. Los imports viven dentro para que el
    arranque del módulo no pague LiteLLM ni LangGraph.
    """
    global _graph
    if _graph is not None:
        # Inyección de test: gana siempre.
        return _graph

    from nexus_worker.runtime.companion import build_companion_graph

    from nexus_api.core.qa_checkpointer import get_qa_checkpointer

    settings = get_settings()
    compiled = build_companion_graph(
        provider=_get_provider(),
        model=settings.llm_companion_model,
        checkpointer=get_qa_checkpointer(),
        toolbelt=toolbelt,
        effort=settings.companion_effort,
    )
    if toolbelt is None:
        _graph = compiled
    return compiled


def reset_graph_cache_for_tests() -> None:
    global _graph, _provider
    _graph = None
    _provider = None


def set_graph_for_tests(graph: Any) -> None:
    """Inyecta un grafo YA compilado. Útil cuando el turno no usa
    herramientas; con herramientas usa :func:`set_provider_for_tests`, que
    deja que cada run compile el suyo con su propio juego."""
    global _graph
    _graph = graph


def set_provider_for_tests(provider: Any) -> None:
    """Inyecta el proveedor (en memoria) y deja el resto del camino real:
    el grafo se compila por run, con su toolbelt."""
    global _provider, _graph
    _provider = provider
    _graph = None


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


@router.get(
    "/companion/threads/{thread_id}/runs",
    response_model=CompanionThreadRunsOut,
    responses={404: {"description": "No such thread for this member."}},
)
async def list_thread_runs(
    thread_id: Annotated[uuid.UUID, Path(...)],
    caller: CompanionCaller = Depends(companion_reader()),
    session: AsyncSession = Depends(get_db_session),
) -> CompanionThreadRunsOut:
    """Los runs de un hilo, del más viejo al más nuevo (contrato v1.1, §5.2).

    El timeline del cajón es del **hilo**, no del run: una conversación son
    el turno, la pausa para confirmar y el run que continúa después.
    Reconstruir esa vista es concatenar los eventos de cada run en orden —
    y sin este endpoint el navegador no puede ni saber qué runs tiene el
    hilo.

    La alternativa era un índice en ``localStorage``, y eso rompe que la URL
    del hilo se pueda compartir con el equipo: quien la abriera en otra
    máquina vería una conversación vacía. Un índice local no es un atajo de
    la interfaz, es un dato que faltaba en el servidor.

    Sin paginación a propósito: un hilo con cientos de runs es un problema
    de CO-06, y meter un cursor hoy sería resolver un caso que no existe con
    una interfaz que habría que rehacer igual.
    """
    async with session.begin():
        await apply_principal_to_session(session, caller.principal_id)
        # El 404 opaco sale de aquí: un hilo de otro miembro no se
        # distingue de uno que no existe.
        await _thread_row(session, thread_id, caller.principal_id)
        rows = (
            await session.execute(
                sa.select(
                    CompanionRun.id,
                    CompanionRun.status,
                    CompanionRun.started_at,
                    CompanionRun.ended_at,
                )
                .where(CompanionRun.thread_id == thread_id)
                .order_by(CompanionRun.started_at.asc())
            )
        ).all()
    return CompanionThreadRunsOut(
        thread_id=thread_id,
        runs=[
            CompanionRunSummaryOut(
                run_id=run_id, status=status_, started_at=started_at, ended_at=ended_at
            )
            for run_id, status_, started_at, ended_at in rows
        ],
    )


@router.get("/companion/runs/{run_id}/events", response_model=CompanionEventsOut)
async def get_run_events(
    run_id: Annotated[uuid.UUID, Path(...)],
    caller: CompanionCaller = Depends(companion_reader()),
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
    caller: CompanionCaller = Depends(companion_reader()),
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
                waiting = await s.scalar(
                    sa.select(sa.func.count())
                    .select_from(CompanionAction)
                    .where(
                        CompanionAction.run_id == run_id,
                        CompanionAction.status == STATUS_PROPOSED,
                    )
                )
                if waiting:
                    # Esperando a una persona. No es un run huérfano y no se
                    # cierra: el cajón tiene que seguir con el stream abierto
                    # mientras la tarjeta de confirmación está en pantalla.
                    return None
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
    caller: CompanionCaller = Depends(companion_reader()),
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


# ── acciones y reanudación (CO-04) ─────────────────────────────────────


def _unknown_action() -> HTTPException:
    """Opaco a propósito, y **antes** que cualquier 409.

    Se comprueba la pertenencia primero: si un tercero pudiera distinguir
    "no existe" de "existe y ya está aplicada", el endpoint sería un oráculo
    para saber qué está haciendo otro partner con sus clientes.
    """
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Unknown action")


def _conflict(code: str, detail: str) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT, detail={"code": code, "detail": detail}
    )


def _action_out(action: CompanionAction, ttl: float) -> CompanionActionOut:
    payload = dict(action.payload or {})
    raw_diff = action.diff or {}
    result = action.result or {}
    return CompanionActionOut(
        action_id=action.id,
        thread_id=action.thread_id,
        run_id=action.run_id,
        kind=action.kind,
        title=str(payload.get("title") or ""),
        preview=dict(payload.get("preview") or {}),
        # Se guarda envuelto (``{"lines": [...]}``) porque la columna está
        # tipada ``dict`` en un archivo que no es de este carril; se sirve
        # como lista, que es lo que el contrato declara.
        diff=list(raw_diff.get("lines") or []) if raw_diff.get("lines") is not None else None,
        impact=list(payload.get("impact") or []),
        risk=str(payload.get("risk") or "low"),
        reversible=bool(payload.get("reversible", True)),
        status=action.status,
        state_hash=str(action.state_hash or ""),
        proposed_at=action.proposed_at,
        expires_at=expires_at_of(action.proposed_at, ttl),
        decided_at=action.decided_at,
        decided_by=action.decided_by,
        applied_at=action.applied_at,
        ok=result.get("verified") if isinstance(result.get("verified"), bool) else None,
        # §19.4. Salen de ``companion.actions.result``, donde los dejó la
        # lista blanca ``APPLY_ECHO`` al aplicar. Nulos hasta que se aplica,
        # y nulos para siempre en los ``kind`` que no son de soporte: el
        # mapa no tiene entrada para ellos.
        ticket_ref=str(result["ticket_ref"]) if result.get("ticket_ref") else None,
        sla=str(result["sla"]) if result.get("sla") else None,
    )


@router.get(
    "/companion/actions/{action_id}",
    response_model=CompanionActionOut,
    responses={404: {"description": "No such action for this member."}},
)
async def get_action(
    action_id: Annotated[uuid.UUID, Path(...)],
    caller: CompanionCaller = Depends(companion_reader()),
    session: AsyncSession = Depends(get_db_session),
) -> CompanionActionOut:
    """Una acción propia, con la caducidad aplicada al leer.

    Existe para el estado *parcial* de la interfaz: recargar con una
    confirmación pendiente tiene que pintar la tarjeta aunque el log de Redis
    ya haya expirado. Sin esto, cerrar el portátil quince minutos y volver
    dejaría al usuario mirando un hilo que dice que está esperando algo que
    no se puede ver.
    """
    ttl = get_settings().companion_action_ttl_seconds
    action = await load_action(
        session, action_id, principal_id=caller.principal_id, ttl_seconds=ttl
    )
    if action is None:
        raise _unknown_action()
    return _action_out(action, ttl)


@router.post(
    "/companion/runs/{run_id}/resume",
    response_model=CompanionResumeOut,
    status_code=status.HTTP_202_ACCEPTED,
    responses={
        404: {"description": "No such run or action for this member."},
        409: {"description": "The action was already decided, or it expired."},
        412: {"description": "The underlying state changed since it was proposed."},
        429: {"description": "Too many Companion turns running, or too many per minute."},
    },
)
async def resume_run(
    body: CompanionResumeIn,
    run_id: Annotated[uuid.UUID, Path(...)],
    response: Response,
    caller: CompanionCaller = Depends(companion_caller()),
    session: AsyncSession = Depends(get_db_session),
    redis: Redis = Depends(get_redis),
) -> CompanionResumeOut:
    """La decisión de una persona sobre una acción propuesta.

    Tres cosas que este endpoint decide y el resto del sistema obedece:

    - **412 es exclusivamente la deriva de estado**, y la caducidad por
      tiempo es 409 con ``action_expired``. La salida es la misma —volver a
      proponer— pero la causa no, y la interfaz las cuenta distinto:
      «alguien cambió esto mientras decidías» no es «se te pasó el plazo».
    - **El tope mensual de tokens NO se comprueba aquí.** Responder una
      confirmación no arranca trabajo nuevo, así que un hilo esperando
      decisión no puede quedarse atrapado porque el partner haya gastado su
      presupuesto entre la propuesta y el sí. El 429 de aquí es solo por
      runs simultáneos y por ráfaga.
    - **``edit`` y ``cancel`` también devuelven 202 y arrancan un run.** El
      modelo tiene que reaccionar al motivo del rechazo; un "no" que no
      vuelve al agente deja al usuario repitiéndose.
    """
    settings = get_settings()
    ttl = settings.companion_action_ttl_seconds
    principal_id = caller.principal_id

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

    # 404 antes que nada: pertenencia primero, estado después.
    parked_run = await _owned_run(session, run_id, principal_id)
    action = await load_action(session, body.action_id, principal_id=principal_id, ttl_seconds=ttl)
    if action is None or action.run_id != run_id:
        raise _unknown_action()

    if action.status == STATUS_EXPIRED:
        raise _conflict(
            "action_expired",
            "This proposal expired without a decision. The Companion will propose "
            "it again with fresh data.",
        )
    if action.status != STATUS_PROPOSED:
        raise _conflict(
            "action_already_decided",
            f"This action is already {action.status}; it cannot be decided again.",
        )

    if body.decision == "confirm":
        await _revalidate_state_hash(caller, action, principal_id=principal_id, ttl=ttl)

    decided_status = DECISION_STATUS[body.decision]
    decided_at = datetime.now(UTC)
    with principal_context(principal_id):
        async with session.begin():
            await apply_principal_to_session(session, principal_id)
            await session.execute(
                sa.update(CompanionAction)
                .where(CompanionAction.id == action.id)
                .values(
                    status=decided_status,
                    decided_at=decided_at,
                    decided_by=principal_id,
                )
            )
            # El run que esperaba ya cumplió: la persona decidió y el trabajo
            # continúa en OTRO run. Cerrarlo aquí, y no dejarlo al reaper, es
            # lo que hace que el hilo no se quede con dos runs "vivos".
            parked = await session.get(CompanionRun, run_id)
            if parked is not None and parked.status == RUN_RUNNING:
                parked.status = RUN_COMPLETED
                parked.ended_at = sa.func.now()
            thread = await _thread_row(session, action.thread_id, principal_id)
            if thread.archived_at is not None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT, detail="Thread is archived"
                )
            await _guard_concurrency(session, principal_id)
            new_run = CompanionRun(
                thread_id=thread.id, principal_id=principal_id, status=RUN_RUNNING
            )
            session.add(new_run)
            await session.flush()
            if body.note:
                # El motivo entra en el hilo como texto de la persona: es lo
                # que le dijo a Auphere, y tiene que sobrevivir al turno para
                # que el siguiente sepa por qué se descartó lo anterior.
                session.add(
                    CompanionMessage(
                        thread_id=thread.id,
                        run_id=new_run.id,
                        seq=await _next_message_seq(session, thread.id),
                        role="user",
                        content=body.note,
                    )
                )
            thread.last_run_at = sa.func.now()
            thread.updated_at = sa.func.now()
            await session.flush()
            await session.refresh(new_run)
            new_run_id = new_run.id
            tenant_id = thread.tenant_id
            mode = thread.mode
            history = await _thread_history(session, thread.id, exclude_run=new_run_id)

    window = month_window()
    used_before = await partner_companion_tokens_used(session, caller.partner.id, window)
    cap = caller.partner.companion_monthly_token_cap

    driver = _make_driver(
        principal=caller.principal,
        thread_id=action.thread_id,
        run_id=new_run_id,
        tenant_id=tenant_id,
        user_message=body.note or "",
        page_context=None,
        history=history,
        used_before=used_before,
        cap=cap,
        window=window,
        mode=mode,
        # Solo cuando la acción confirmada ES de soporte. Así un turno
        # normal no paga ni una consulta extra por una función que no usa.
        support_action=(
            action.id if body.decision == "confirm" and action.kind in SUPPORT_KINDS else None
        ),
        resume={
            "decision": body.decision,
            "note": body.note,
            # El ``principal_id``, no el correo: la interfaz ya sabe quién es
            # el usuario en sesión, y para otro miembro pinta el
            # identificador. Correos completos de terceros en el chat, nunca.
            "by": principal_id,
            "at": decided_at.isoformat(),
        },
    )
    await streaming.start_run(
        redis=redis,
        run_id=new_run_id,
        thread_id=action.thread_id,
        principal_id=principal_id,
        driver=driver,
        on_complete=_make_on_complete(
            principal_id=principal_id,
            partner_id=caller.partner.id,
            used_before=used_before,
            cap=cap,
            window=window,
        ),
    )
    log.info(
        "companion.action.decided",
        action_id=str(action.id),
        decision=body.decision,
        paused_run=str(parked_run.id),
        run_id=str(new_run_id),
    )
    response.headers["Cache-Control"] = "no-store"
    return CompanionResumeOut(
        run_id=new_run_id,
        thread_id=action.thread_id,
        action_id=action.id,
        status=decided_status,
    )


async def _revalidate_state_hash(
    caller: CompanionCaller,
    action: CompanionAction,
    *,
    principal_id: str,
    ttl: float,
) -> None:
    """Recalcula la huella del estado leído y compara. **412 si cambió.**

    Es el CAS del Companion, y vive entero aquí: los endpoints ``/console/*``
    de debajo no tienen comparación-e-intercambio y hoy no la van a tener.
    Se recalcula por el mismo camino que la propuesta —los mismos routers,
    con el mismo sujeto— porque un hash calculado de otra forma no compara
    nada.

    Un fallo de lectura **no** bloquea la confirmación: se registra y se deja
    pasar. Negarse a aplicar porque una comprobación auxiliar no respondió
    convertiría una caída de un endpoint de lectura en un bloqueo total de la
    escritura, y el 409/422 del router de destino sigue estando detrás.
    """
    from nexus_api.companion.tools import CompanionToolbelt
    from nexus_api.companion.tools.actions import set_status
    from nexus_api.companion.tools.proposals import ProposalBuilder, ProposalRefused
    from nexus_api.core.console_auth import InProcessActor

    payload = dict(action.payload or {})
    args = dict(payload.get("propose_args") or {})
    if not args:  # pragma: no cover - toda propuesta guarda sus argumentos
        # Sin argumentos no hay nada que rehacer. Se deja pasar: el hash
        # existe para detectar deriva, no para inventar motivos de bloqueo.
        return

    belt = CompanionToolbelt(
        actor=InProcessActor(
            user_id=caller.principal.user_id,
            partner_id=caller.partner.id,
            jti=f"companion:revalidate:{action.id}",
        ),
        principal_id=principal_id,
        action_ttl_seconds=ttl,
    )
    drifted = True
    async with belt:
        # ``checked`` (CO-08) es parte de la propuesta ORIGINAL, no del
        # estado fresco: son las lecturas de aquel turno. Sin devolvérselo
        # al constructor, rehacer un ticket de soporte fallaría por falta de
        # expediente y toda confirmación de soporte saldría 412.
        builder = ProposalBuilder(
            read=belt.read,
            checked=tuple(
                str(c) for c in (dict(payload.get("preview") or {}).get("checked") or [])
            ),
        )
        try:
            fresh = await builder.build(action.kind, args)
        except ProposalRefused:
            # La propuesta ya no se puede construir (el cliente cambió, la
            # versión desapareció, el rol bajó): eso ES deriva de estado, y
            # es de los casos donde más importa no aplicar lo viejo.
            drifted = True
        except Exception as exc:
            # La comprobación auxiliar no respondió. NO se bloquea: negarse a
            # aplicar porque un endpoint de lectura tuvo un mal momento
            # convertiría una caída parcial en un bloqueo total de la
            # escritura, y el 409/422 del router de destino sigue detrás.
            log.warning(
                "companion.action.revalidate_failed",
                action_id=str(action.id),
                error=str(exc),
            )
            # El fail-open se mantiene, pero deja de ser silencioso: sin esta
            # serie, una relectura que empieza a fallar apaga el compare-and-swap
            # para todos los partners y lo único que queda es una línea de log
            # que nadie mira.
            record_companion("companion.cas.revalidate_failed")
            return
        else:
            drifted = fresh.state_hash != action.state_hash

    if not drifted:
        return

    from nexus_api.db.base import get_sessionmaker

    sm = get_sessionmaker()
    async with sm() as fresh_session:
        await set_status(fresh_session, action.id, principal_id=principal_id, status=STATUS_EXPIRED)
    raise HTTPException(
        status_code=status.HTTP_412_PRECONDITION_FAILED,
        detail={
            "code": "state_changed",
            "detail": (
                "Someone changed this while the proposal was pending, so the diff "
                "shown is no longer accurate. The Companion will propose again "
                "with fresh data."
            ),
        },
    )


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
                    # Un run aparcado esperando confirmación NO está muerto:
                    # está parado a propósito, y su propuesta vive quince
                    # minutos, más que el techo de duración de un run. Sin
                    # esta exclusión el reaper mataría cada espera humana a
                    # los cinco minutos y el usuario vería «el turno se
                    # interrumpió» con la tarjeta todavía en pantalla.
                    sa.not_(_is_parked()),
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
