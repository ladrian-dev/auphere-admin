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
    """

    actor: InProcessActor
    #: Tope duro de llamadas por turno. El presupuesto que el modelo *ve*
    #: es otra cosa (una nota de sistema); esto es la red de abajo.
    max_calls: int = 25
    app: Any = None
    timeout_s: float = 10.0

    calls_made: int = 0
    citations: list[Citation] = field(default_factory=list)
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

        return tool_specs()

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

        invalid = _validate(spec, arguments)
        if invalid is not None:
            return self._failed(name, spec.label, invalid, started)

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
