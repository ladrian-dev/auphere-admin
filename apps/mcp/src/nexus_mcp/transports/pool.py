"""Pool de clientes stdio MCP per-tenant.

Decisión arquitectónica (Bloque E): un proceso Node por tenant. Browserbase
context_id es per-tenant por diseño y Stagehand mantiene la sesión browser
ligada al context — context-switching mid-process abre la puerta a leaks
visibles entre tenants (cookies, storage). Phase 1 = 1 cliente real, así
que en steady state es 1 proceso. Memoria por proceso ronda 150-300MB.

Lifecycle:
  1. ``acquire(tenant_id)`` retorna un cliente listo. Lazy-spawn al primer
     dispatch del tenant.
  2. El cliente persiste entre calls (el handshake + initialize cuesta
     500ms-1s, no se quiere repetir).
  3. Idle timeout: si no hay actividad por ``idle_timeout_s`` segundos,
     un task de barrido kill al proceso. Re-spawn transparente en el
     próximo acquire.
  4. ``shutdown()`` cierra todos los clientes (worker SIGTERM).

Concurrencia:
  - ``_locks[tenant_id]`` (asyncio.Lock) serializa los calls del MISMO
     tenant. Esto resuelve la gotcha de race en context_id de Browserbase.
     Sí, baja el throughput per-tenant a 1 call concurrente; sí, está
     bien para Phase 1 (la latencia de browser dominates de todos modos).
  - El spawn lock (``_spawn_lock``) evita doble-spawn si dos calls del
     mismo tenant llegan exactamente al mismo tiempo.

Inyección de dependencias:
  - El pool acepta una ``StdioMCPClientFactory`` por server name. Tests
     pasan una factory que construye un ``FakeAgendaProTransport`` (no
     spawnea nada).
"""

from __future__ import annotations

import asyncio
import contextlib
import time
import uuid
from collections.abc import Mapping
from typing import Any

import structlog

from nexus_mcp.transports.stdio import (
    StdioMCPClient,
    StdioMCPClientFactory,
    StdioTransportError,
)

log = structlog.get_logger(__name__)


class SubprocessPool:
    """Gestiona clientes per-tenant de un único server name.

    Para Bloque E habrá una sola instancia (server name=
    ``agendapro_browser_mcp``). Si en el futuro hay más servers
    subprocess, se instancia un pool por server.
    """

    def __init__(
        self,
        factory: StdioMCPClientFactory,
        *,
        idle_timeout_s: float = 1800.0,
        sweep_interval_s: float = 300.0,
    ) -> None:
        self._factory = factory
        self._idle_timeout_s = idle_timeout_s
        self._sweep_interval_s = sweep_interval_s
        self._clients: dict[str, StdioMCPClient] = {}
        self._last_used: dict[str, float] = {}
        self._tenant_locks: dict[str, asyncio.Lock] = {}
        self._spawn_lock = asyncio.Lock()
        self._sweep_task: asyncio.Task[None] | None = None
        self._closed = False

    @property
    def server_name(self) -> str:
        return self._factory.server_name

    async def acquire(self, tenant_id: uuid.UUID) -> StdioMCPClient:
        """Devuelve un cliente vivo para ``tenant_id``. Spawnea si hace falta.

        El caller debe usar ``async with pool.tenant_lock(tenant_id):``
        alrededor de cada secuencia de calls que comparta estado del
        context Browserbase. ``SubprocessTool`` lo hace por defecto.
        """
        if self._closed:
            raise StdioTransportError("subprocess pool is closed")
        key = str(tenant_id)
        client = self._clients.get(key)
        if client is not None and client.alive:
            self._last_used[key] = time.monotonic()
            return client
        # Drop dead client if present.
        if client is not None and not client.alive:
            await self._discard(key)
        # Spawn under lock — two concurrent acquire() calls for the same
        # tenant must produce one client, not two.
        async with self._spawn_lock:
            client = self._clients.get(key)
            if client is not None and client.alive:
                self._last_used[key] = time.monotonic()
                return client
            client = await self._factory.spawn(tenant_id=key)
            self._clients[key] = client
            self._last_used[key] = time.monotonic()
            self._ensure_sweep_running()
            return client

    def tenant_lock(self, tenant_id: uuid.UUID) -> asyncio.Lock:
        """Lock per-tenant que serializa calls. ``SubprocessTool`` lo
        agarra en cada ``run()``.

        Browserbase context_id NO es thread-safe — dos pipelines del
        mismo tenant invocando AgendaPro al mismo tiempo romperían la
        sesión. Esto bloquea ese caso a costo de 1 RTT por call por
        tenant, lo cual es aceptable para una operación de browser que
        ya cuesta 1-3s.
        """
        key = str(tenant_id)
        lock = self._tenant_locks.get(key)
        if lock is None:
            lock = asyncio.Lock()
            self._tenant_locks[key] = lock
        return lock

    async def call_tool(
        self,
        *,
        tenant_id: uuid.UUID,
        name: str,
        arguments: Mapping[str, Any],
        timeout: float = 90.0,
    ) -> dict[str, Any]:
        """Helper que toma el lock per-tenant + acquire + ``tools/call``.

        El caller que necesite múltiples calls atómicos (ej. health check
        que hace varios tools/call seguidos) puede usar el lock
        manualmente y llamar ``acquire().call_tool()`` directo.
        """
        async with self.tenant_lock(tenant_id):
            client = await self.acquire(tenant_id)
            try:
                return await client.call_tool(name, arguments, timeout=timeout)
            except StdioTransportError:
                # Si la conexión murió, descarta el cliente para que el
                # próximo acquire spawnee uno fresh.
                await self._discard(str(tenant_id))
                raise
            finally:
                self._last_used[str(tenant_id)] = time.monotonic()

    async def shutdown(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._sweep_task is not None and not self._sweep_task.done():
            self._sweep_task.cancel()
            with contextlib.suppress(asyncio.CancelledError, Exception):
                await self._sweep_task
        await asyncio.gather(
            *(c.close() for c in self._clients.values()),
            return_exceptions=True,
        )
        self._clients.clear()
        self._last_used.clear()

    # ── internals ────────────────────────────────────────────────────────

    async def _discard(self, key: str) -> None:
        client = self._clients.pop(key, None)
        self._last_used.pop(key, None)
        if client is not None:
            await client.close()

    def _ensure_sweep_running(self) -> None:
        if self._sweep_task is not None and not self._sweep_task.done():
            return
        self._sweep_task = asyncio.create_task(
            self._sweep_loop(),
            name=f"subprocess-pool-sweep:{self._factory.server_name}",
        )

    async def _sweep_loop(self) -> None:
        try:
            while not self._closed:
                await asyncio.sleep(self._sweep_interval_s)
                if self._closed:
                    return
                cutoff = time.monotonic() - self._idle_timeout_s
                stale = [key for key, last in self._last_used.items() if last < cutoff]
                for key in stale:
                    log.info(
                        "subprocess_pool.idle_evict",
                        server=self._factory.server_name,
                        tenant_id=key,
                        idle_for_s=time.monotonic() - self._last_used.get(key, 0),
                    )
                    await self._discard(key)
        except asyncio.CancelledError:
            return
