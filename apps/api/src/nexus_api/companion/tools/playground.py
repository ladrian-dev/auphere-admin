"""Probar el agente de un cliente antes de publicar (CO-05, §7 de CONTRACT-V2).

Manda uno o varios mensajes de prueba por el playground de la consola y
devuelve, por cada uno, **si respondió y cuánto tardó** — nunca el texto de
la respuesta.

Por qué no vuelve el texto
--------------------------
Regla dura del §7 del contrato, y no es prudencia de más: la respuesta del
agente puede citar literalmente el mensaje de prueba y, en un agente que ya
lleva contenido del cliente, arrastrar texto que la decisión C8 prohíbe sacar
por este camino. Quien quiera leer la conversación abre el hilo de playground,
donde ya hay autorización y ya está el guardián del §1.3 de la investigación.

Lo que viaja es ``probe`` (que redacta el Companion, como ``citation.claim``),
aserciones con nombre estable y metadatos.

Lo que esta herramienta NO prueba
---------------------------------
**No prueba el borrador.** El §6.4 de la investigación pedía "un turno en seco
contra el agente **borrador**", y eso hoy no se puede: el playground corre la
tubería normal del tenant, que resuelve su paquete por
``AgentLoader.load(tenant_id)`` — y ese cargador devuelve **la versión activa**,
por diseño ("a staged version that is NOT promoted does not change the active
row"). No hay forma de pasarle una versión, y la única inyección que existe
(``prime()``) escribe en una caché de proceso compartida con el tráfico real,
así que usarla haría vivo un borrador para clientes de verdad.

Se prueba, por tanto, **la versión activa**, y se dice así en todas partes:
``trial.tested_version`` lo lleva explícito y el aviso de publicación distingue
"no se probó nada" de "se probó lo que ya estaba, no lo que vas a publicar".
Prometer lo contrario sería exactamente la clase de afirmación sin respaldo que
la regla R1 existe para impedir.
"""

from __future__ import annotations

import asyncio
import json
import time
from dataclasses import dataclass, field
from typing import Any

import httpx
import structlog

from nexus_api.companion.tools.errors import ToolError, translate_status

log = structlog.get_logger(__name__)

#: Tope de mensajes de prueba por llamada. Cinco es suficiente para
#: ejercitar un cambio y bastante poco para que probar no se coma el tope
#: mensual del playground de un partner en una tarde.
MAX_PROBES = 5

#: Espera máxima por mensaje de prueba. Un turno de playground que tarda más
#: de esto no es una prueba, es un incidente — y se reporta como tal.
PROBE_TIMEOUT_S = 90.0


@dataclass
class TrialRecord:
    """Lo que el turno recuerda de haber probado.

    Vive en el estado del hilo del Companion, no en una tabla: un hecho por
    versión, compartido entre hilos, exige migración y eso es alcance que la
    Ola 2 no abre. Consecuencia declarada: publicar desde un hilo distinto de
    aquel donde se probó da ``trial_ran: false``, que es honesto — *en esta
    conversación nadie probó*.
    """

    client_ref: str
    thread_id: str
    ok: bool
    tokens: int
    tested_version: int | None
    turns: list[dict[str, Any]] = field(default_factory=list)

    def as_payload(self) -> dict[str, Any]:
        return {
            "ran": True,
            "client_ref": self.client_ref,
            "thread_id": self.thread_id,
            "ok": self.ok,
            "tokens": self.tokens,
            "tested_version": self.tested_version,
            "turns": list(self.turns),
        }


def parse_probes(raw: str) -> list[str]:
    """Un mensaje por línea, sin vacías, como mucho :data:`MAX_PROBES`."""
    probes = [line.strip() for line in str(raw or "").splitlines() if line.strip()]
    return probes[:MAX_PROBES]


async def _await_run(
    client: httpx.AsyncClient, *, ref: str, thread_id: str, run_id: str
) -> tuple[bool, int, str | None]:
    """Sigue el SSE del run hasta que termina.

    Devuelve ``(ok, tokens, error)``. Es el único canal que hay: el playground
    no expone el estado de un run por GET, a propósito (el transcripto vive
    solo en el stream).
    """
    tokens = 0
    url = f"/console/clients/{ref}/playground/threads/{thread_id}/stream"
    params: dict[str, str] = {"run_id": run_id, "since_seq": "0"}
    event: str | None = None
    async with client.stream("GET", url, params=params, timeout=PROBE_TIMEOUT_S) as response:
        if response.status_code >= 400:
            await response.aread()
            return False, 0, f"stream_{response.status_code}"
        async for line in response.aiter_lines():
            if line.startswith("event:"):
                event = line.removeprefix("event:").strip()
                continue
            if not line.startswith("data:"):
                continue
            try:
                data = json.loads(line.removeprefix("data:").strip())
            except json.JSONDecodeError:  # pragma: no cover - defensivo
                continue
            if event == "cost.updated":
                tokens += int(data.get("input_tokens") or 0)
                tokens += int(data.get("output_tokens") or 0)
            elif event == "run.completed":
                status_value = str(data.get("status") or "")
                return status_value == "completed", tokens, data.get("error")
    # El stream se cerró sin ``run.completed``: no se puede afirmar que el
    # turno saliera bien, y afirmarlo sería una alucinación con respaldo.
    return False, tokens, "stream_closed"


async def run_trial(
    client: httpx.AsyncClient,
    *,
    ref: str,
    probes: list[str],
) -> tuple[TrialRecord | None, ToolError | None]:
    """Ejecuta los mensajes de prueba en un hilo nuevo y arma el registro."""
    if not probes:
        return None, ToolError(
            "bad_arguments",
            "No me diste ningún mensaje de prueba. Escribe al menos uno, como se "
            "lo escribiría un cliente final, y que ejercite el cambio que quieres "
            "comprobar.",
        )

    created = await client.post(
        f"/console/clients/{ref}/playground/threads",
        json={"title": "Prueba del Companion"},
    )
    if created.status_code >= 400:
        return None, _translate(created)
    thread_id = str(created.json()["id"])

    version = await _active_version(client, ref)

    turns: list[dict[str, Any]] = []
    tokens = 0
    for index, probe in enumerate(probes, start=1):
        started = time.perf_counter()
        try:
            accepted = await client.post(
                f"/console/clients/{ref}/playground/threads/{thread_id}/runs",
                json={"prompt": probe},
            )
        except httpx.TimeoutException:
            turns.append(_turn(index, probe, False, started, "timeout"))
            break
        if accepted.status_code >= 400:
            error = _translate(accepted)
            turns.append(_turn(index, probe, False, started, error.code))
            # Un tope de playground alcanzado no tira el turno del Companion:
            # es un límite de la prueba, no del trabajo. Se reporta y se para.
            break

        run_id = str(accepted.json()["run_id"])
        try:
            ok, spent, error_code = await asyncio.wait_for(
                _await_run(client, ref=ref, thread_id=thread_id, run_id=run_id),
                timeout=PROBE_TIMEOUT_S,
            )
        except TimeoutError:
            turns.append(_turn(index, probe, False, started, "timeout"))
            break
        tokens += spent
        turns.append(_turn(index, probe, ok, started, error_code))

    record = TrialRecord(
        client_ref=ref,
        thread_id=thread_id,
        ok=bool(turns) and all(t["ok"] for t in turns),
        tokens=tokens,
        tested_version=version,
        turns=turns,
    )
    log.info(
        "companion.trial.finished",
        client_ref=ref,
        probes=len(probes),
        ok=record.ok,
        tokens=tokens,
    )
    return record, None


async def _active_version(client: httpx.AsyncClient, ref: str) -> int | None:
    """La versión que de verdad respondió. Sin esto, ``trial`` no puede decir
    QUÉ se probó, y una prueba que no dice qué probó no respalda nada."""
    try:
        response = await client.get(f"/console/clients/{ref}/agent")
    except Exception:  # pragma: no cover - defensivo
        return None
    if response.status_code >= 400:
        return None
    active = response.json().get("active_version")
    return int(active) if active is not None else None


def _turn(
    index: int, probe: str, ok: bool, started: float, error_code: str | None
) -> dict[str, Any]:
    """Una fila del panel. ``checks`` lleva nombres estables en inglés que
    traduce la interfaz; ``expected`` y ``actual`` son cadenas siempre."""
    checks = [
        {
            "name": "agent_answered",
            "expected": "true",
            "actual": "true" if ok else "false",
            "ok": ok,
        }
    ]
    if not ok and error_code:
        checks.append(
            {"name": "failure_reason", "expected": "none", "actual": error_code, "ok": False}
        )
    return {
        "index": index,
        "probe": probe,
        "ok": ok,
        "latency_ms": int((time.perf_counter() - started) * 1000),
        "checks": checks,
    }


def _translate(response: httpx.Response) -> ToolError:
    detail: str | None = None
    try:
        body = response.json()
        detail = body.get("detail") if isinstance(body, dict) else None
    except Exception:  # pragma: no cover - defensivo
        detail = None
    return translate_status(
        response.status_code,
        detail if isinstance(detail, str) else None,
        tool="companion.run_playground_turn",
    )


__all__ = [
    "MAX_PROBES",
    "PROBE_TIMEOUT_S",
    "TrialRecord",
    "parse_probes",
    "run_trial",
]
