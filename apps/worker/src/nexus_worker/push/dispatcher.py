"""``push-dispatcher`` — reparte los avisos al teléfono (spec 031, research D6).

El mismo patrón que ``streams/outbound.py`` (WP-12): el disparador de 0160 hace
``pg_notify('nexus_push', tenant_id)`` por cada evento nuevo, y un barrido cada
30 s recoge los avisos perdidos y los reintentos (que el disparador de
inserción no ve). Por tenant:

1. ``push_fanout.claim`` en la transacción del tenant: toma los eventos, les pone
   plazo, calcula destinatarios y compone los avisos;
2. el envío a APNs y FCM, **fuera** de cualquier transacción;
3. ``push_fanout.settle`` en otra transacción: anota lo que pasó.

Toda la lógica de a quién y qué vive en la API (``services/push_fanout.py``),
donde la barren las suites de aislamiento; aquí solo el bucle y el envío.
"""

from __future__ import annotations

import asyncio
import contextlib
import uuid
from collections.abc import Awaitable, Callable

import structlog
from nexus_api.config import get_settings
from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_sessionmaker
from nexus_api.services import push_fanout, push_payloads

from nexus_worker.push._result import SendResult
from nexus_worker.push.apns import ApnsClient
from nexus_worker.push.fcm import FcmClient

log = structlog.get_logger(__name__)

NOTIFY_CHANNEL = "nexus_push"
SWEEP_SECONDS = 30.0
#: Avisos enviados a la vez por tenant: Apple y Google aguantan mucho más; esto
#: solo evita abrir cientos de flujos HTTP/2 por un evento con muchos teléfonos.
MAX_CONCURRENT_SENDS = 16
MAX_CONCURRENT_TENANTS = 8


class PushWorkSet:
    """Tenants con trabajo probable, por LISTEN o por el barrido."""

    def __init__(self) -> None:
        self._tenants: set[uuid.UUID] = set()
        self._wakeup = asyncio.Event()

    def add(self, tenant_id: uuid.UUID) -> None:
        self._tenants.add(tenant_id)
        self._wakeup.set()

    def add_raw(self, payload: str) -> None:
        with contextlib.suppress(ValueError):
            self.add(uuid.UUID(payload))

    def pop_all(self) -> set[uuid.UUID]:
        drained = self._tenants
        self._tenants = set()
        self._wakeup.clear()
        return drained

    async def wait(self, timeout: float) -> None:
        with contextlib.suppress(TimeoutError):
            await asyncio.wait_for(self._wakeup.wait(), timeout=timeout)


def clients_from_settings() -> tuple[ApnsClient, FcmClient]:
    s = get_settings()
    return (
        ApnsClient(
            key_id=s.apns_key_id,
            team_id=s.apns_team_id,
            key_pem=s.apns_key_pem,
            topic=s.apns_topic,
        ),
        FcmClient(project_id=s.fcm_project_id, service_account_json=s.fcm_service_account_json),
    )


async def deliver(
    outgoing: push_fanout.Outgoing, *, apns: ApnsClient, fcm: FcmClient
) -> push_fanout.Result:
    """Un aviso a un teléfono. Nunca lanza: lo inesperado se reintenta."""
    try:
        if outgoing.provider == "apns":
            headers, body = push_payloads.apns(outgoing.notice, topic=apns.topic)
            sent: SendResult = await apns.send(
                token=outgoing.token,
                environment=outgoing.apns_environment,
                headers=headers,
                payload=body,
            )
        else:
            sent = await fcm.send(push_payloads.fcm(outgoing.notice, token=outgoing.token))
    except Exception as exc:  # pragma: no cover - defensa: el reparto sigue
        log.warning("push.deliver_failed", error=str(exc))
        sent = SendResult(outcome="retry", error_code="unexpected")
    return push_fanout.Result(
        delivery_id=outgoing.delivery_id,
        event_id=outgoing.event_id,
        phone_id=outgoing.phone_id,
        outcome=sent.outcome,
        provider_message_id=sent.provider_message_id,
        error_code=sent.error_code,
    )


async def drain_tenant(
    tenant_id: uuid.UUID,
    *,
    apns: ApnsClient,
    fcm: FcmClient,
    send: Callable[[push_fanout.Outgoing], Awaitable[push_fanout.Result]] | None = None,
) -> int:
    """Un tenant: tomar, enviar, anotar. Devuelve cuántos avisos intentó."""
    sm = get_sessionmaker()
    async with sm() as session, tenant_scoped_session(session, tenant_id):
        outgoing = await push_fanout.claim(session, sm)
    if not outgoing:
        return 0
    limit = asyncio.Semaphore(MAX_CONCURRENT_SENDS)
    one = send or (lambda o: deliver(o, apns=apns, fcm=fcm))

    async def _limited(o: push_fanout.Outgoing) -> push_fanout.Result:
        async with limit:
            return await one(o)

    results = await asyncio.gather(*(_limited(o) for o in outgoing))
    async with sm() as session, tenant_scoped_session(session, tenant_id):
        await push_fanout.settle(session, sm, results)
    log.info(
        "push.dispatcher.drained",
        tenant_id=str(tenant_id),
        sent=sum(1 for r in results if r.outcome == "sent"),
        retry=sum(1 for r in results if r.outcome == "retry"),
        failed=sum(1 for r in results if r.outcome in ("failed", "unregistered")),
    )
    return len(results)


async def _run_listener(work: PushWorkSet, stop: asyncio.Event) -> None:
    import asyncpg

    from nexus_worker.streams.outbound import _asyncpg_dsn

    while not stop.is_set():
        conn = None
        try:
            conn = await asyncpg.connect(_asyncpg_dsn())

            def _on_notify(_conn, _pid, _channel, payload):  # type: ignore[no-untyped-def]
                work.add_raw(payload)

            await conn.add_listener(NOTIFY_CHANNEL, _on_notify)
            log.info("push.listener.connected", channel=NOTIFY_CHANNEL)
            while not stop.is_set():
                with contextlib.suppress(TimeoutError):
                    await asyncio.wait_for(stop.wait(), timeout=15.0)
                if not stop.is_set():
                    await conn.execute("SELECT 1")
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            log.warning("push.listener.reconnecting", error=str(exc))
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(stop.wait(), timeout=2.0)
        finally:
            if conn is not None:
                with contextlib.suppress(Exception):
                    await conn.close()


async def run_push_dispatcher(
    *,
    stop: asyncio.Event,
    apns: ApnsClient | None = None,
    fcm: FcmClient | None = None,
    work: PushWorkSet | None = None,
    listen: bool = True,
    sweep_seconds: float = SWEEP_SECONDS,
) -> None:
    """La tarea. Vuelve cuando ``stop`` se activa."""
    if apns is None or fcm is None:
        apns, fcm = clients_from_settings()
    log.info(
        "push.dispatcher.start",
        apns_configured=apns.configured,
        fcm_configured=fcm.configured,
    )
    work = work if work is not None else PushWorkSet()
    listener = (
        asyncio.create_task(_run_listener(work, stop), name="push-listener") if listen else None
    )
    tenants = asyncio.Semaphore(MAX_CONCURRENT_TENANTS)

    async def _drain(tid: uuid.UUID) -> None:
        async with tenants:
            try:
                await drain_tenant(tid, apns=apns, fcm=fcm)
            except Exception as exc:
                log.error("push.dispatcher.drain_failed", tenant_id=str(tid), error=str(exc))

    last_sweep = float("-inf")
    try:
        while not stop.is_set():
            try:
                now = asyncio.get_running_loop().time()
                if now - last_sweep >= sweep_seconds:
                    last_sweep = now
                    async with get_sessionmaker()() as identity:
                        for tid in await push_fanout.tenants_with_pending(identity):
                            work.add(tid)
                notified = work.pop_all()
                if notified:
                    await asyncio.gather(*(_drain(tid) for tid in notified))
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.error("push.dispatcher.tick_failed", error=str(exc))
            remaining = max(0.1, sweep_seconds - (asyncio.get_running_loop().time() - last_sweep))
            wait_task = asyncio.create_task(work.wait(remaining))
            stop_task = asyncio.create_task(stop.wait())
            _done, pending = await asyncio.wait(
                {wait_task, stop_task}, return_when=asyncio.FIRST_COMPLETED
            )
            for task in pending:
                task.cancel()
            with contextlib.suppress(Exception):
                await asyncio.gather(*pending, return_exceptions=True)
    finally:
        if listener is not None:
            listener.cancel()
            with contextlib.suppress(Exception):
                await asyncio.gather(listener, return_exceptions=True)
        await apns.aclose()
        await fcm.aclose()
    log.info("push.dispatcher.stopped")


__all__ = [
    "NOTIFY_CHANNEL",
    "PushWorkSet",
    "clients_from_settings",
    "deliver",
    "drain_tenant",
    "run_push_dispatcher",
]
