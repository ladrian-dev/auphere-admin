"""Qué modelos se ofrecen, y qué modelos puede ejecutar un hop.

Son dos conjuntos distintos y confundirlos costó un corte:

- ``RESPOND_MODELS`` es la **oferta al partner**: hoy Sol, Terra y Luna. Es lo
  que la consola deja elegir para el rol ``respond``. Ids de LiteLLM verbatim;
  no existe el alias ``gpt-5.6`` (404 en el vendor, probado el 2026-09-01).
- ``HOP_MODEL_IDS`` es lo que un hop puede **ejecutar**: todo el catálogo vivo
  de ``model_profiles``. Incluye Anthropic, que es con lo que producción responde
  a diario, y ``whisper-1`` y ``gpt-4o``, que sirven a visión, transcripción,
  grader y evals.

Validar el hop contra la oferta mata el turno de cualquier tenant con binding a
Anthropic con un ``UnknownCatalogModel`` que **nadie captura**. Un id fuera de
``HOP_MODEL_IDS`` sigue siendo un error humano (409), nunca un ``acompletion`` a
pelo contra el vendor.

**Spec 047 (T139, requisito 39.3): las dos listas salen de los datos.** La
oferta son las filas con ``offer_label`` y estado ``active``; lo ejecutable, las
filas en ``active``, ``retiring`` (siguen sirviendo hasta su fecha, 41.7) o
``certifying`` (tienen que poder correr su batería). Los nombres de este módulo
son **vistas** del último catálogo leído, no copias: quien hizo ``from
respond_catalog import RESPOND_MODEL_ID_SET`` ve la fila nueva sin desplegar.

Se refresca con :func:`refresh_from_rows`, que llaman quienes ya leen
``model_profiles`` (el catálogo de precios del worker y la lectura del router),
o con :func:`refresh_from_db`. Hasta la primera lectura se sirve ``BOOT_*``: lo
que sembraron las migraciones 0072, 0076, 0095 y 0180, para que el camino
caliente del hop no consulte la base y no rechace nada antes de leerla. El
guardián ``test_model_catalog_matches_db`` las mantiene iguales a la base.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Iterator, Mapping, Sequence
from collections.abc import Set as AbstractSet
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, overload

SOL_MODEL_ID = "openai/gpt-5.6-sol"
RESPOND_ROLE: str = "respond"

# Same human phrase the channel uses when a hop cannot complete (QA-14).
HUMAN_TURN_ERROR = "Disculpa, tuve un inconveniente."

#: Lo que la consola puede ofrecer: solo lo activo (requisito 39.7).
OFFERED_STATUSES: frozenset[str] = frozenset({"active"})
#: Lo que un hop puede ejecutar.
EXECUTABLE_STATUSES: frozenset[str] = frozenset({"active", "retiring", "certifying"})

#: La semilla de arranque: las filas de las migraciones, solo hasta la primera
#: lectura y como último valor conocido si una lectura llega vacía.
BOOT_OFFER: tuple[tuple[str, str], ...] = (
    (SOL_MODEL_ID, "Sol"),
    ("openai/gpt-5.6-terra", "Terra"),
    ("openai/gpt-5.6-luna", "Luna"),
)
BOOT_HOP_MODEL_IDS: tuple[str, ...] = (
    *(model_id for model_id, _ in BOOT_OFFER),
    "anthropic/claude-sonnet-4-6",
    "anthropic/claude-haiku-4-5",
    "anthropic/claude-haiku-4-5-20251001",
    "openai/gpt-4o",
    "openai/whisper-1",
)


@dataclass(frozen=True)
class CatalogLists:
    """Una lectura del catálogo: la oferta (en orden) y lo ejecutable."""

    offer: tuple[tuple[str, str], ...]
    hop: tuple[str, ...]

    @property
    def offer_ids(self) -> tuple[str, ...]:
        return tuple(model_id for model_id, _ in self.offer)


_BOOT = CatalogLists(offer=BOOT_OFFER, hop=BOOT_HOP_MODEL_IDS)
_current: CatalogLists = _BOOT
_offer_set: frozenset[str] = frozenset(_BOOT.offer_ids)
_hop_set: frozenset[str] = frozenset(_BOOT.hop)


def _price(row: Mapping[str, Any]) -> Decimal:
    value = row.get("price_input_per_mtok")
    return Decimal(str(value)) if value is not None else Decimal(-1)


def lists_from_rows(rows: Iterable[Mapping[str, Any]]) -> CatalogLists | None:
    """Las dos listas a partir de filas de ``model_profiles``.

    La oferta va de la más capaz a la más barata (precio de entrada, que es lo
    que distingue Sol de Terra y de Luna), y a igualdad por id. Ninguna fila es
    una lectura rota, no una decisión: devuelve None.
    """
    materialized = [r for r in rows if r.get("model_id")]
    if not materialized:
        return None
    offered = [
        r for r in materialized if r.get("offer_label") and r.get("status") in OFFERED_STATUSES
    ]
    offered.sort(key=lambda r: (-_price(r), str(r["model_id"])))
    hop = tuple(str(r["model_id"]) for r in materialized if r.get("status") in EXECUTABLE_STATUSES)
    return CatalogLists(
        offer=tuple((str(r["model_id"]), str(r["offer_label"])) for r in offered),
        hop=hop,
    )


def _install(lists: CatalogLists) -> None:
    global _current, _offer_set, _hop_set
    _current = lists
    _offer_set = frozenset(lists.offer_ids)
    _hop_set = frozenset(lists.hop)


def refresh_from_rows(rows: Iterable[Mapping[str, Any]]) -> bool:
    """Instala el catálogo leído. False (y se queda el anterior) si no había filas."""
    lists = lists_from_rows(rows)
    if lists is None:
        return False
    _install(lists)
    return True


async def refresh_from_db(session: Any) -> bool:
    """Lee ``model_profiles`` (plataforma, sin RLS) e instala el catálogo."""
    import sqlalchemy as sa

    result = await session.execute(
        sa.text("SELECT model_id, status, offer_label, price_input_per_mtok FROM model_profiles")
    )
    return refresh_from_rows([dict(r) for r in result.mappings()])


def reset() -> None:
    """Vuelve a la semilla de arranque (tests)."""
    _install(_BOOT)


def current() -> CatalogLists:
    return _current


# ── las vistas ─────────────────────────────────────────────────────────────


class _SeqView(Sequence[Any]):
    """Una secuencia que siempre lee el último catálogo instalado."""

    def __init__(self, read: Callable[[], tuple[Any, ...]], name: str) -> None:
        self._read = read
        self._name = name

    @overload
    def __getitem__(self, index: int) -> Any: ...
    @overload
    def __getitem__(self, index: slice) -> tuple[Any, ...]: ...
    def __getitem__(self, index: int | slice) -> Any:
        return self._read()[index]

    def __len__(self) -> int:
        return len(self._read())

    def __iter__(self) -> Iterator[Any]:
        return iter(self._read())

    def __contains__(self, value: object) -> bool:
        return value in self._read()

    def __eq__(self, other: object) -> bool:
        if isinstance(other, _SeqView):
            return self._read() == other._read()
        if isinstance(other, tuple | list):
            return list(self._read()) == list(other)
        return NotImplemented

    __hash__ = None  # type: ignore[assignment]

    def __repr__(self) -> str:
        return f"{self._name}{self._read()!r}"


class _SetView(AbstractSet[str]):
    """Un conjunto que siempre lee el último catálogo instalado."""

    def __init__(self, read: Callable[[], frozenset[str]], name: str) -> None:
        self._read = read
        self._name = name

    def __contains__(self, value: object) -> bool:
        return value in self._read()

    def __iter__(self) -> Iterator[str]:
        return iter(sorted(self._read()))

    def __len__(self) -> int:
        return len(self._read())

    @classmethod
    def _from_iterable(cls, it: Iterable[Any]) -> frozenset[Any]:
        return frozenset(it)

    def __repr__(self) -> str:
        return f"{self._name}({sorted(self._read())!r})"


RESPOND_MODELS: Sequence[tuple[str, str]] = _SeqView(lambda: _current.offer, "RESPOND_MODELS")
RESPOND_MODEL_IDS: Sequence[str] = _SeqView(lambda: _current.offer_ids, "RESPOND_MODEL_IDS")
RESPOND_MODEL_ID_SET: AbstractSet[str] = _SetView(lambda: _offer_set, "RESPOND_MODEL_ID_SET")
HOP_MODEL_IDS: Sequence[str] = _SeqView(lambda: _current.hop, "HOP_MODEL_IDS")
HOP_MODEL_ID_SET: AbstractSet[str] = _SetView(lambda: _hop_set, "HOP_MODEL_ID_SET")


class UnknownCatalogModel(ValueError):
    """id fuera del catálogo de plataforma. No llamar a ``acompletion``."""

    def __init__(self, model_id: str) -> None:
        super().__init__(model_id)
        self.model_id = model_id


def require_hop_model(model_id: str) -> str:
    """Rechaza un hop cuyo id no está en el catálogo de plataforma.

    Contra lo ejecutable, no contra la oferta: un tenant con binding a Anthropic
    ejecuta un hop perfectamente válido. Lo que la consola deja *elegir* es
    ``RESPOND_MODEL_IDS`` y eso lo comprueba ``console/models``.
    """
    if model_id not in _hop_set:
        raise UnknownCatalogModel(model_id)
    return model_id


def hop_models_in_catalog(*model_ids: str) -> bool:
    """True si todos los ids no vacíos son ejecutables por un hop.

    Contra el catálogo de plataforma, no contra la oferta: quien pregunta
    —el Playground— quiere saber si el turno va a poder correr, y un
    despliegue cuyo modelo global de QA sea Anthropic corre perfectamente.
    """
    return all(model_id in _hop_set for model_id in model_ids if model_id)


__all__ = [
    "BOOT_HOP_MODEL_IDS",
    "BOOT_OFFER",
    "EXECUTABLE_STATUSES",
    "HOP_MODEL_IDS",
    "HOP_MODEL_ID_SET",
    "HUMAN_TURN_ERROR",
    "OFFERED_STATUSES",
    "RESPOND_MODELS",
    "RESPOND_MODEL_IDS",
    "RESPOND_MODEL_ID_SET",
    "RESPOND_ROLE",
    "SOL_MODEL_ID",
    "CatalogLists",
    "UnknownCatalogModel",
    "current",
    "hop_models_in_catalog",
    "lists_from_rows",
    "refresh_from_db",
    "refresh_from_rows",
    "require_hop_model",
    "reset",
]
