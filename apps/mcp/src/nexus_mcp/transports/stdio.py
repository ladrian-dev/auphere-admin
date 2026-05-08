"""JSON-RPC 2.0 sobre stdio para hablar con un subprocess MCP server.

Uso típico (per-tenant): el ``SubprocessPool`` spawnea un proceso por
tenant, hace ``initialize`` + ``tools/list`` una vez, y mantiene el
cliente vivo. Cada tool dispatch hace ``tools/call``.

Protocolo MCP (oficial, JSON-RPC 2.0 con framing newline-delimited):

  → Cliente envía: ``{"jsonrpc":"2.0","id":N,"method":"...","params":{...}}\\n``
  ← Server responde: ``{"jsonrpc":"2.0","id":N,"result":{...}}\\n``
  ← O en error: ``{"jsonrpc":"2.0","id":N,"error":{"code":N,"message":"..."}}``

Notificaciones (server → cliente, no esperan respuesta) llegan SIN ``id``
y se descartan o se loggean. Bloque E no usa notifications todavía.

Gotchas implementadas:
- Stdout del proceso es EXCLUSIVAMENTE para el protocolo MCP. Stderr es
  para logs. ``StdioMCPClient`` consume stderr en una task aparte y la
  loggea con structlog (key ``subprocess.stderr``).
- Cada call lleva un id monotónico; el dispatcher mapea id → ``asyncio.Future``
  para que múltiples calls concurrentes compartan el proceso sin
  intercalarse mal.
- Timeout por call (default 30s para tools normales, 90s para mutativas).
  Override por call.
- Salud del proceso: si el proceso muere, todas las futures pendientes
  reciben ``StdioTransportError`` y el cliente queda marcado closed. El
  pool spawnea uno nuevo en el próximo dispatch.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

import structlog

log = structlog.get_logger(__name__)


class StdioTransportError(RuntimeError):
    """Subprocess-side IO falló: proceso muerto, JSON inválido, RPC error,
    o timeout. El caller (``SubprocessTool``) lo traduce a ``ToolError``."""


@dataclass
class _PendingCall:
    future: asyncio.Future[dict[str, Any]]
    method: str


@dataclass
class StdioMCPClientFactory:
    """Receta para spawnear un cliente stdio. Inmutable, reusable.

    El pool guarda una factory por server name, y un cliente vivo por
    (server_name, tenant_id).
    """

    command: Sequence[str]
    cwd: str | None = None
    env: Mapping[str, str] = field(default_factory=dict)
    server_name: str = "agendapro_browser_mcp"

    async def spawn(self, *, tenant_id: str) -> StdioMCPClient:
        full_env = {**os.environ, **self.env, "NEXUS_TENANT_ID": tenant_id}
        log.info(
            "stdio.spawn",
            server=self.server_name,
            tenant_id=tenant_id,
            command=list(self.command),
        )
        proc = await asyncio.create_subprocess_exec(
            *self.command,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=self.cwd,
            env=full_env,
        )
        client = StdioMCPClient(
            proc=proc,
            server_name=self.server_name,
            tenant_id=tenant_id,
        )
        await client._start()
        try:
            await client.initialize()
        except Exception:
            await client.close()
            raise
        return client


class StdioMCPClient:
    """Cliente JSON-RPC 2.0 stdio para un proceso MCP server.

    Concurrencia: múltiples ``call`` simultáneos comparten el mismo
    proceso. Cada call obtiene un id único y espera su respuesta. Stdin
    está protegido por un ``asyncio.Lock`` para que dos writes no se
    intercalen mid-line (las líneas del protocolo deben ser atómicas).
    """

    def __init__(
        self,
        *,
        proc: asyncio.subprocess.Process,
        server_name: str,
        tenant_id: str,
    ) -> None:
        self._proc = proc
        self.server_name = server_name
        self.tenant_id = tenant_id
        self._next_id = 1
        self._pending: dict[int, _PendingCall] = {}
        self._stdin_lock = asyncio.Lock()
        self._reader_task: asyncio.Task[None] | None = None
        self._stderr_task: asyncio.Task[None] | None = None
        self._closed = False
        self._initialized = False

    # ── lifecycle ────────────────────────────────────────────────────────

    async def _start(self) -> None:
        if self._proc.stdout is None or self._proc.stderr is None:
            raise StdioTransportError("subprocess has no stdout/stderr")
        self._reader_task = asyncio.create_task(
            self._reader_loop(),
            name=f"stdio-reader:{self.server_name}:{self.tenant_id}",
        )
        self._stderr_task = asyncio.create_task(
            self._stderr_loop(),
            name=f"stdio-stderr:{self.server_name}:{self.tenant_id}",
        )

    async def initialize(self) -> dict[str, Any]:
        """Handshake oficial MCP. Server responde con capabilities y la
        lista de tools — el caller las puede ignorar (Bloque E ya las
        registra Python-side via ``SubprocessTool`` factory)."""
        result = await self.call(
            "initialize",
            {
                "protocolVersion": "2025-03-26",
                "capabilities": {},
                "clientInfo": {
                    "name": "nexus-mcp-stdio-client",
                    "version": "0.1.0",
                },
            },
            timeout=15.0,
        )
        # MCP demands the client send "notifications/initialized" after.
        await self._notify("notifications/initialized", {})
        self._initialized = True
        return result

    @property
    def closed(self) -> bool:
        return self._closed

    @property
    def alive(self) -> bool:
        return not self._closed and self._proc.returncode is None

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        for pending in list(self._pending.values()):
            if not pending.future.done():
                pending.future.set_exception(
                    StdioTransportError(f"client closed mid-call ({pending.method})")
                )
        self._pending.clear()
        if self._proc.returncode is None:
            with contextlib.suppress(ProcessLookupError):
                self._proc.terminate()
            try:
                await asyncio.wait_for(self._proc.wait(), timeout=5.0)
            except TimeoutError:
                with contextlib.suppress(ProcessLookupError):
                    self._proc.kill()
                await self._proc.wait()
        for task in (self._reader_task, self._stderr_task):
            if task is not None and not task.done():
                task.cancel()
                with contextlib.suppress(asyncio.CancelledError, Exception):
                    await task
        log.info("stdio.closed", server=self.server_name, tenant_id=self.tenant_id)

    # ── public API ───────────────────────────────────────────────────────

    async def call(
        self,
        method: str,
        params: Mapping[str, Any] | None = None,
        *,
        timeout: float = 30.0,
    ) -> dict[str, Any]:
        if self._closed:
            raise StdioTransportError("client is closed")
        if self._proc.returncode is not None:
            raise StdioTransportError(f"subprocess exited with {self._proc.returncode}")

        request_id = self._next_id
        self._next_id += 1
        future: asyncio.Future[dict[str, Any]] = asyncio.get_running_loop().create_future()
        self._pending[request_id] = _PendingCall(future=future, method=method)

        payload = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": dict(params or {}),
        }
        await self._write_line(json.dumps(payload, separators=(",", ":")))
        try:
            return await asyncio.wait_for(future, timeout=timeout)
        except TimeoutError as exc:
            self._pending.pop(request_id, None)
            raise StdioTransportError(f"timed out after {timeout}s waiting for {method}") from exc

    async def call_tool(
        self,
        name: str,
        arguments: Mapping[str, Any],
        *,
        timeout: float = 90.0,
    ) -> dict[str, Any]:
        """``tools/call`` con el shape oficial MCP.

        El server retorna ``{"content": [...]}``. Bloque E entrega un único
        text content cuyo body es JSON con el envelope esperado por
        ``SubprocessTool``. Esto evita acoplar el shape MCP estructural a
        nuestro envelope (``tool/tenant_id/args/result/status/executed_at``).
        """
        result = await self.call(
            "tools/call",
            {"name": name, "arguments": dict(arguments)},
            timeout=timeout,
        )
        if not isinstance(result, dict):
            raise StdioTransportError(f"tools/call returned non-dict: {result!r}")
        # Server may report ``isError=true`` per MCP spec — surface it.
        if result.get("isError"):
            content = result.get("content") or []
            msg = ""
            if content and isinstance(content, list):
                first = content[0]
                if isinstance(first, dict):
                    msg = str(first.get("text") or first)
            raise StdioTransportError(f"server returned isError=true: {msg}")
        return result

    # ── internals ────────────────────────────────────────────────────────

    async def _notify(self, method: str, params: Mapping[str, Any]) -> None:
        payload = {
            "jsonrpc": "2.0",
            "method": method,
            "params": dict(params),
        }
        await self._write_line(json.dumps(payload, separators=(",", ":")))

    async def _write_line(self, line: str) -> None:
        if self._proc.stdin is None:
            raise StdioTransportError("subprocess stdin closed")
        async with self._stdin_lock:
            try:
                self._proc.stdin.write((line + "\n").encode("utf-8"))
                await self._proc.stdin.drain()
            except (BrokenPipeError, ConnectionResetError) as exc:
                raise StdioTransportError(f"stdin write failed: {exc}") from exc

    async def _reader_loop(self) -> None:
        assert self._proc.stdout is not None
        try:
            while True:
                raw = await self._proc.stdout.readline()
                if not raw:
                    break
                line = raw.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    log.warning(
                        "stdio.invalid_json",
                        server=self.server_name,
                        tenant_id=self.tenant_id,
                        line=line[:500],
                    )
                    continue
                self._dispatch_message(msg)
        except Exception as exc:  # pragma: no cover — defensive
            log.exception("stdio.reader_failed", error=str(exc))
        finally:
            await self._mark_dead()

    async def _stderr_loop(self) -> None:
        assert self._proc.stderr is not None
        try:
            while True:
                raw = await self._proc.stderr.readline()
                if not raw:
                    break
                line = raw.decode("utf-8", errors="replace").rstrip()
                if not line:
                    continue
                log.info(
                    "subprocess.stderr",
                    server=self.server_name,
                    tenant_id=self.tenant_id,
                    line=line[:1000],
                )
        except Exception:  # pragma: no cover
            pass

    def _dispatch_message(self, msg: dict[str, Any]) -> None:
        msg_id = msg.get("id")
        if msg_id is None:
            # Notification from the server — log and move on.
            method = msg.get("method")
            log.debug(
                "stdio.notification",
                server=self.server_name,
                tenant_id=self.tenant_id,
                method=method,
            )
            return
        pending = self._pending.pop(int(msg_id), None)
        if pending is None:
            log.warning(
                "stdio.unmatched_response",
                server=self.server_name,
                tenant_id=self.tenant_id,
                msg_id=msg_id,
            )
            return
        if pending.future.done():
            return
        if "error" in msg:
            err = msg["error"] or {}
            pending.future.set_exception(
                StdioTransportError(
                    f"RPC error from {pending.method}: "
                    f"code={err.get('code')} message={err.get('message')!r}"
                )
            )
        else:
            result = msg.get("result")
            if not isinstance(result, dict):
                pending.future.set_exception(
                    StdioTransportError(
                        f"{pending.method} returned non-dict result: {type(result).__name__}"
                    )
                )
            else:
                pending.future.set_result(result)

    async def _mark_dead(self) -> None:
        if self._closed:
            return
        rc = await self._proc.wait()
        log.warning(
            "stdio.subprocess_exited",
            server=self.server_name,
            tenant_id=self.tenant_id,
            returncode=rc,
        )
        for pending in list(self._pending.values()):
            if not pending.future.done():
                pending.future.set_exception(
                    StdioTransportError(
                        f"subprocess died (returncode={rc}) mid-call ({pending.method})"
                    )
                )
        self._pending.clear()
        self._closed = True
