"""El ejecutor de herramientas del Companion (CO-02).

Recibe el nombre y los argumentos que escribió el modelo y devuelve un
:class:`ToolOutcome`. **No emite eventos**: los emite el grafo, que es
quien posee el protocolo. Así el paquete no depende de LangChain y el
grafo no depende de la API.

Tres cosas que hace además de llamar:

- **Valida** contra el esquema declarado en el catálogo. Un argumento de
  más o de otro tipo se rechaza aquí, con un mensaje que le dice al modelo
  qué corregir, en vez de convertirse en un 422 del router.
- **Recorta** la respuesta a ``max_chars``. Sin esto, tres llamadas a
  ``get_audit`` llenan la ventana de contexto y el resto del turno responde
  a ciegas. El recorte va marcado: el modelo tiene que saber que vio una
  parte.
- **Cuenta**. El tope de llamadas por turno es del motor, no del prompt.

Sobre las citas: cada lectura con éxito produce una, con la etiqueta humana
de la herramienta, la ruta que se leyó y el momento. Es lo que sostiene la
regla R1 — sin lectura no hay afirmación — y lo que el cajón pinta junto a
cada dato.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import httpx
import structlog

from nexus_api.companion.tools.catalog import TOOLS_BY_NAME, ToolSpec
from nexus_api.companion.tools.client import make_client
from nexus_api.companion.tools.errors import TIMEOUT, ToolError, translate_status
from nexus_api.core.console_auth import InProcessActor, acting_as

log = structlog.get_logger(__name__)

TRUNCATION_MARK = "\n…[recortado: {n} caracteres más. Afina los filtros si necesitas el resto.]"


@dataclass(frozen=True)
class Citation:
    """Un dato leído, con su procedencia. ``{claim, source, fetched_at}``."""

    citation_id: str
    claim: str
    source: str
    fetched_at: str

    def as_payload(self) -> dict[str, str]:
        return {
            "citation_id": self.citation_id,
            "claim": self.claim,
            "source": self.source,
            "fetched_at": self.fetched_at,
        }


@dataclass(frozen=True)
class ToolOutcome:
    """El resultado de una llamada, tal y como lo ve el grafo."""

    name: str
    label: str
    ok: bool
    #: Lo que se le devuelve al modelo como resultado de la herramienta.
    content: str
    latency_ms: int
    error_code: str | None = None
    citation: Citation | None = None


@dataclass
class CompanionToolbelt:
    """Las herramientas de un run. Una instancia por turno.

    ``actor`` es el sujeto de todas las llamadas: la persona del partner que
    está hablando. No es una credencial y no se puede fabricar desde fuera
    del proceso — ver ``core/console_auth.py``.

    Desde CO-04 es además el **puerto de acciones** del grafo: el grafo pide
    ``stage`` / ``apply`` / ``verify`` sin saber que detrás hay HTTP ni
    Postgres. Esa asimetría es deliberada — ``apps/worker`` no importa
    ``nexus_api`` en ninguna parte y conviene que siga siendo así.
    """

    actor: InProcessActor
    #: Tope duro de llamadas por turno. El presupuesto que el modelo *ve*
    #: es otra cosa (una nota de sistema); esto es la red de abajo.
    max_calls: int = 25
    app: Any = None
    timeout_s: float = 10.0
    #: Modo del HILO, que es del usuario y nunca del modelo. En ``consult``
    #: el catálogo publicado son solo las lecturas: el modelo no puede
    #: proponer un cambio ni porque alguien se lo pida dentro de un texto.
    mode: str = "build"
    #: Contexto de la acción. Lo pone el driver del run; sin él, ``stage`` no
    #: tiene dónde escribir y falla en vez de inventarse un hilo.
    principal_id: str | None = None
    thread_id: uuid.UUID | None = None
    run_id: uuid.UUID | None = None
    #: Plazo de una propuesta sin decidir. Es lo único que fija ``expires_at``,
    #: y por eso la interfaz no calcula quince minutos por su cuenta.
    action_ttl_seconds: float = 900.0

    calls_made: int = 0
    citations: list[Citation] = field(default_factory=list)
    #: Propuestas calculadas en este turno y todavía sin persistir. El grafo
    #: las recoge en el nodo ``plan``.
    pending: list[Any] = field(default_factory=list)
    #: Lo que falta para poder proponer, si algo falta. El grafo lo emite
    #: como ``intake.missing`` al cerrar el turno.
    missing_slots: list[dict[str, Any]] = field(default_factory=list)
    #: Firmas de llamadas ya hechas en este turno. Repetir una lectura
    #: idéntica no aporta nada y gasta ventana de contexto.
    _seen: dict[str, str] = field(default_factory=dict)
    _client: httpx.AsyncClient | None = None

    # ── ciclo de vida ──────────────────────────────────────────────────

    async def __aenter__(self) -> CompanionToolbelt:
        self._client = make_client(self.app, timeout_s=self.timeout_s)
        return self

    async def __aexit__(self, *exc: Any) -> None:
        if self._client is not None:
            await self._client.aclose()
            self._client = None

    # ── el catálogo que ve el modelo ───────────────────────────────────

    def specs(self) -> list[dict[str, Any]]:
        from nexus_api.companion.tools.catalog import tool_specs

        return tool_specs(mode=self.mode)

    @property
    def calls_left(self) -> int:
        return max(0, self.max_calls - self.calls_made)

    @property
    def reads_done(self) -> int:
        """Lecturas con éxito. Es el numerador de la regla R1."""
        return len(self.citations)

    # ── una llamada ────────────────────────────────────────────────────

    async def call(self, name: str, arguments: dict[str, Any]) -> ToolOutcome:
        started = time.perf_counter()
        spec = TOOLS_BY_NAME.get(name)
        if spec is None:
            # El modelo se inventó una herramienta. Pasa, y la respuesta
            # tiene que decirle qué existe en vez de dejarlo adivinando.
            return self._failed(
                name,
                name,
                ToolError(
                    "unknown_tool",
                    f"No existe la herramienta {name!r}. Las que tienes son: "
                    + ", ".join(sorted(TOOLS_BY_NAME)),
                ),
                started,
            )

        if self.calls_made >= self.max_calls:
            return self._failed(
                name,
                spec.label,
                ToolError(
                    "budget_exhausted",
                    f"Has agotado las {self.max_calls} consultas de este turno. "
                    "Responde con lo que ya has leído y di qué te faltó mirar.",
                ),
                started,
            )

        if self.mode == "consult" and spec.tool_class != "read":
            # El modo recorta el catálogo publicado, pero eso solo cambia lo
            # que el modelo VE. Un modelo que se invente el nombre de una
            # herramienta que no le dieron —y pasa— la ejecutaría igual si
            # el gate viviera solo en ``specs()``. Vive aquí, en el motor.
            return self._failed(
                name,
                spec.label,
                ToolError(
                    "read_only_mode",
                    "Este hilo está en modo Consultar, donde no se cambia nada. "
                    "Dile a la persona que cambie el hilo a Construir si quiere "
                    "que prepares el cambio; no lo hagas por tu cuenta.",
                ),
                started,
            )

        invalid = _validate(spec, arguments)
        if invalid is not None:
            return self._failed(name, spec.label, invalid, started)

        if spec.tool_class == "propose":
            self.calls_made += 1
            return await self._propose(spec, arguments, started)
        if spec.tool_class == "mutates":
            self.calls_made += 1
            return await self._apply_by_id(spec, arguments, started)

        signature = f"{name}:{json.dumps(arguments, sort_keys=True, default=str)}"
        if signature in self._seen:
            return self._failed(
                name,
                spec.label,
                ToolError(
                    "already_read",
                    "Ya hiciste exactamente esta consulta en este turno. Usa el "
                    "resultado anterior; volver a leer lo mismo no lo cambia.",
                ),
                started,
            )

        self.calls_made += 1
        path, query = _build_request(spec, arguments)
        try:
            response = await self._request(path, query)
        except httpx.TimeoutException:
            log.warning("companion.tool.timeout", tool=name, path=path)
            return self._failed(name, spec.label, TIMEOUT, started)
        except Exception as exc:  # pragma: no cover - defensivo
            log.exception("companion.tool.failed", tool=name, path=path)
            return self._failed(
                name,
                spec.label,
                ToolError("unavailable", f"La consulta falló: {exc}"),
                started,
            )

        latency_ms = _elapsed(started)
        if response.status_code >= 400:
            detail = _detail(response)
            error = translate_status(response.status_code, detail, tool=name)
            log.info(
                "companion.tool.refused",
                tool=name,
                status=response.status_code,
                code=error.code,
            )
            return ToolOutcome(
                name=name,
                label=spec.label,
                ok=False,
                content=json.dumps(error.as_payload(), ensure_ascii=False),
                latency_ms=latency_ms,
                error_code=error.code,
            )

        self._seen[signature] = path
        body = _truncate(response.text, spec.max_chars)
        citation = Citation(
            citation_id=uuid.uuid4().hex[:12],
            claim=_claim(spec, arguments),
            source=_source(path, query),
            fetched_at=datetime.now(UTC).isoformat(),
        )
        self.citations.append(citation)
        return ToolOutcome(
            name=name,
            label=spec.label,
            ok=True,
            content=body,
            latency_ms=latency_ms,
            citation=citation,
        )

    async def _request(self, path: str, query: dict[str, Any]) -> httpx.Response:
        if self._client is None:  # pragma: no cover - uso fuera del ``async with``
            raise RuntimeError("CompanionToolbelt se usa dentro de 'async with'")
        # Aquí, y solo aquí, la petición interna lleva sujeto. El bloque se
        # cierra siempre, así que el actor no sobrevive a la llamada.
        with acting_as(self.actor):
            return await self._client.get(path, params=query)

    async def read(self, path: str, query: dict[str, Any] | None = None) -> httpx.Response:
        """Una lectura cruda, con el sujeto puesto y sin contar contra el
        tope del turno.

        La usan el constructor de propuestas y la revalidación del hash: no
        son consultas del modelo, son trabajo del motor, y gastarle al
        usuario su presupuesto de consultas por ellas sería cobrarle dos
        veces la misma pregunta.
        """
        return await self._request(path, query or {})

    async def _write(self, method: str, path: str, body: Any) -> httpx.Response:
        """La ÚNICA escritura del Companion, y también por el router.

        Misma vía que las lecturas: enrutado, Pydantic, ``client_scope``
        (RLS), limitador, cuota de aprovisionamiento y auditoría. El actor
        se propaga igual y se restaura igual.
        """
        if self._client is None:  # pragma: no cover - uso fuera del ``async with``
            raise RuntimeError("CompanionToolbelt se usa dentro de 'async with'")
        with acting_as(self.actor):
            return await self._client.request(method, path, json=body)

    # ── propuesta ──────────────────────────────────────────────────────

    async def _propose(
        self, spec: ToolSpec, arguments: dict[str, Any], started: float
    ) -> ToolOutcome:
        """Calcula la propuesta y la deja pendiente. **No persiste nada.**

        Persistir aquí sería el fallo C2 con otro disfraz: el bucle de
        herramientas puede correr varias veces si el modelo se corrige, y
        cada pasada dejaría una fila. La escritura la hace el nodo ``plan``,
        una vez, con id determinista y UPSERT.
        """
        from nexus_api.companion.tools.proposals import (
            IntakeRequired,
            ProposalBuilder,
            ProposalRefused,
        )

        builder = ProposalBuilder(read=self.read)
        try:
            proposal = await builder.build(str(spec.kind), arguments)
        except IntakeRequired as intake:
            # No hay nada que corregir: falta información que solo tiene el
            # cliente. Sale por su propio evento —el cajón lo pinta como
            # chips respondibles, no como un error rojo— y el turno termina
            # preguntando en vez de proponiendo con huecos rellenados a ojo.
            self.missing_slots = intake.slots
            return self._failed(
                spec.name,
                spec.label,
                ToolError(
                    "intake_required",
                    "Faltan datos que solo sabe la persona: "
                    + ", ".join(s["label"] for s in intake.slots)
                    + ". Pregúntaselos en una frase corta, sin listas ni "
                    "formulario, y no propongas nada hasta tenerlos.",
                ),
                started,
            )
        except ProposalRefused as refused:
            return self._failed(spec.name, spec.label, refused.error, started)
        except httpx.TimeoutException:
            return self._failed(spec.name, spec.label, TIMEOUT, started)

        # Una propuesta por turno (PLAN-CO-04 §D3): es lo que permite que el
        # nodo del ``interrupt()`` tenga UNA llamada incondicional. La
        # segunda sustituye a la primera en vez de acumularse — si el modelo
        # se corrige, lo que vale es lo último que dijo.
        self.pending = [proposal]

        citation = Citation(
            citation_id=uuid.uuid4().hex[:12],
            claim=f"{spec.label} ({proposal.title})",
            source=spec.path.replace("{client_ref}", str(proposal.client_ref or "")),
            fetched_at=datetime.now(UTC).isoformat(),
        )
        self.citations.append(citation)
        body = json.dumps(
            {
                "staged": True,
                "kind": proposal.kind,
                "title": proposal.title,
                "preview": proposal.preview,
                "impact": proposal.impact,
                "risk": proposal.risk,
                "reversible": proposal.reversible,
                "note": (
                    "Propuesta preparada. NO está aplicada: la persona tiene que "
                    "confirmarla. Explícale en una frase qué va a cambiar y espera; "
                    "no llames a console.apply."
                ),
            },
            ensure_ascii=False,
            default=str,
        )
        return ToolOutcome(
            name=spec.name,
            label=spec.label,
            ok=True,
            content=_truncate(body, spec.max_chars),
            latency_ms=_elapsed(started),
            citation=citation,
        )

    # ── ejecución ──────────────────────────────────────────────────────

    async def _apply_by_id(
        self, spec: ToolSpec, arguments: dict[str, Any], started: float
    ) -> ToolOutcome:
        """``console.apply``. Falla en el MOTOR si la acción no está
        confirmada — garantía C4."""
        from nexus_api.companion.tools.errors import (
            ACTION_EXPIRED,
            APPLY_FAILED,
            NOT_CONFIRMED,
        )

        try:
            action_id = uuid.UUID(str(arguments.get("action_id")))
        except (ValueError, TypeError):
            return self._failed(
                spec.name,
                spec.label,
                ToolError(
                    "bad_arguments", "action_id tiene que ser el identificador de una acción."
                ),
                started,
            )
        outcome = await self._apply(action_id)
        if outcome is None:
            return self._failed(
                spec.name,
                spec.label,
                ToolError(
                    "unknown_action",
                    "No hay ninguna acción con ese identificador en este hilo.",
                ),
                started,
            )
        if outcome.ok:
            return ToolOutcome(
                name=spec.name,
                label=spec.label,
                ok=True,
                content=_truncate(outcome.body or "{}", spec.max_chars),
                latency_ms=_elapsed(started),
            )
        error = {
            "not_confirmed": NOT_CONFIRMED,
            "action_expired": ACTION_EXPIRED,
        }.get(outcome.error_code or "", APPLY_FAILED)
        return self._failed(spec.name, spec.label, error, started)

    # ── el puerto de acciones que usa el grafo ─────────────────────────
    #
    # El grafo llama a estos tres y no sabe que detrás hay HTTP ni Postgres.
    # Es lo que mantiene ``apps/worker`` libre de ``nexus_api``.

    async def stage(self, step_index: int) -> dict[str, Any] | None:
        """Persiste la propuesta pendiente y devuelve el payload de
        ``hitl.requested``. ``None`` si no hay nada que confirmar."""
        from nexus_api.companion.tools.actions import stage_action

        if not self.pending:
            return None
        if self.principal_id is None or self.thread_id is None or self.run_id is None:
            # Sin contexto no se escribe a ciegas: es un error de montaje del
            # run, no algo que el usuario deba pagar con una fila huérfana.
            log.warning("companion.action.stage_without_context")
            return None
        proposal = self.pending[0]
        async with _session() as session:
            staged = await stage_action(
                session,
                principal_id=self.principal_id,
                thread_id=self.thread_id,
                run_id=self.run_id,
                step_index=step_index,
                proposal=proposal,
                ttl_seconds=self.action_ttl_seconds,
            )
        return staged.as_event()

    def plan_steps(self) -> list[dict[str, Any]]:
        """Los pasos del plan, en la forma del §2.1 del contrato."""
        from nexus_api.companion.tools.catalog import PROPOSE_TOOLS
        from nexus_api.companion.tools.proposals import IRREVERSIBLE_KINDS

        by_kind = {t.kind: t.name for t in PROPOSE_TOOLS}
        return [
            {
                "index": i + 1,
                "kind": p.kind,
                "tool": by_kind.get(p.kind, ""),
                "title": p.title,
                "client_ref": p.client_ref,
                "reversible": p.kind not in IRREVERSIBLE_KINDS,
            }
            for i, p in enumerate(self.pending)
        ]

    def plan_risk(self) -> str:
        """El riesgo del plan es el del paso más arriesgado, no la media."""
        order = {"low": 0, "medium": 1, "high": 2}
        worst = max((order.get(p.risk, 0) for p in self.pending), default=0)
        return ("low", "medium", "high")[worst]

    async def _apply(self, action_id: uuid.UUID) -> Any:
        from nexus_api.companion.tools.actions import (
            STATUS_EXPIRED,
            ApplyOutcome,
            apply_action,
            load_action,
        )

        if self.principal_id is None:  # pragma: no cover - montaje del run
            return None
        async with _session() as session:
            action = await load_action(
                session,
                action_id,
                principal_id=self.principal_id,
                ttl_seconds=self.action_ttl_seconds,
            )
            if action is None:
                return None
            if action.status == STATUS_EXPIRED:
                return ApplyOutcome(ok=False, status_code=409, body="", error_code="action_expired")
            return await apply_action(session, self._write, action, principal_id=self.principal_id)

    async def verify(self, action_id: uuid.UUID) -> dict[str, Any] | None:
        """El payload de ``verify.result``. Código determinista: relee y
        compara. Nunca el modelo (C5)."""
        from nexus_api.companion.tools.actions import load_action, verify_action

        if self.principal_id is None:  # pragma: no cover - montaje del run
            return None
        async with _session() as session:
            action = await load_action(
                session,
                action_id,
                principal_id=self.principal_id,
                ttl_seconds=self.action_ttl_seconds,
            )
        if action is None:
            return None
        return await verify_action(self.read, action)

    async def apply_confirmed(self, action_id: uuid.UUID) -> Any:
        """Lo que llama el nodo ``execute``. Va por :meth:`call` para que los
        eventos ``tool.call.*`` salgan solos y la secuencia del §4.3 del
        contrato se cumpla sin código especial."""
        return await self.call("console.apply", {"action_id": str(action_id)})

    def _failed(self, name: str, label: str, error: ToolError, started: float) -> ToolOutcome:
        return ToolOutcome(
            name=name,
            label=label,
            ok=False,
            content=json.dumps(error.as_payload(), ensure_ascii=False),
            latency_ms=_elapsed(started),
            error_code=error.code,
        )


# ── helpers ────────────────────────────────────────────────────────────


def _session() -> Any:
    """Una sesión propia para el camino de escritura.

    Propia y no la de la petición: el turno corre en una tarea de fondo que
    empezó cuando el ``POST …/runs`` ya había devuelto 202, así que no hay
    ninguna transacción de petición viva a la que engancharse. Import
    perezoso porque ``db.base`` arrastra la configuración del motor y este
    módulo se importa al construir el catálogo.
    """
    from nexus_api.db.base import get_sessionmaker

    return get_sessionmaker()()


def _elapsed(started: float) -> int:
    return round((time.perf_counter() - started) * 1000)


def _detail(response: httpx.Response) -> str | None:
    try:
        payload = response.json()
    except ValueError:
        return None
    detail = payload.get("detail") if isinstance(payload, dict) else None
    return detail if isinstance(detail, str) else None


def _validate(spec: ToolSpec, arguments: dict[str, Any]) -> ToolError | None:
    known = {p.name: p for p in spec.params}
    unknown = sorted(set(arguments) - set(known))
    if unknown:
        return ToolError(
            "bad_arguments",
            f"{spec.name} no acepta {', '.join(unknown)}. Acepta: "
            + (", ".join(sorted(known)) or "ningún argumento")
            + ".",
        )
    for param in spec.params:
        value = arguments.get(param.name)
        if value is None:
            if param.required:
                return ToolError(
                    "bad_arguments",
                    f"{spec.name} necesita {param.name}: {param.description}",
                )
            continue
        if not _is_type(value, param.type):
            return ToolError(
                "bad_arguments",
                f"{param.name} tiene que ser de tipo {param.type} en {spec.name}.",
            )
        if param.enum and str(value) not in param.enum:
            return ToolError(
                "bad_arguments",
                f"{param.name} solo admite: {', '.join(param.enum)}.",
            )
    return None


def _is_type(value: Any, expected: str) -> bool:
    """``bool`` es subclase de ``int`` en Python, así que hay que
    excluirlo a mano o ``days=True`` pasaría por entero válido."""
    if expected == "integer":
        return isinstance(value, int) and not isinstance(value, bool)
    if expected == "boolean":
        return isinstance(value, bool)
    return isinstance(value, str)


def _build_request(spec: ToolSpec, arguments: dict[str, Any]) -> tuple[str, dict[str, Any]]:
    """La ruta con el ``{client_ref}`` sustituido y la query con el resto.

    El nombre del parámetro de query no siempre coincide con el del
    catálogo: el router de clientes llama ``status`` a lo que FastAPI
    recibe como ``status_filter``, y el de consumo llama ``client`` a la
    referencia. Se traduce aquí para que la herramienta hable siempre el
    idioma del partner (``client_ref``) y el router el suyo.
    """
    path = spec.path
    query: dict[str, Any] = {}
    for param in spec.params:
        if param.name not in arguments or arguments[param.name] is None:
            continue
        value = arguments[param.name]
        if param.in_path:
            path = path.replace("{" + param.name + "}", str(value))
            continue
        query["client" if param.name == "client_ref" else param.name] = value
    return path, query


def _truncate(body: str, max_chars: int) -> str:
    if len(body) <= max_chars:
        return body
    return body[:max_chars] + TRUNCATION_MARK.format(n=len(body) - max_chars)


def _claim(spec: ToolSpec, arguments: dict[str, Any]) -> str:
    """La etiqueta humana de lo que se leyó: "Consumo del partner (boreal,
    30 días)". Es lo que el cajón pinta junto al dato."""
    detail = ", ".join(
        f"{k}={v}" for k, v in sorted(arguments.items()) if v is not None and v != ""
    )
    return f"{spec.label} ({detail})" if detail else spec.label


def _source(path: str, query: dict[str, Any]) -> str:
    if not query:
        return path
    rendered = "&".join(f"{k}={v}" for k, v in sorted(query.items()))
    return f"{path}?{rendered}"


__all__ = ["TRUNCATION_MARK", "Citation", "CompanionToolbelt", "ToolOutcome"]
