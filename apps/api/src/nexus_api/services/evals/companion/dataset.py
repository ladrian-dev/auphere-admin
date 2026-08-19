"""El dataset del Companion — esquema, carga y validación (CO-07).

Fichero y no tabla, y la razón está en D1 de ``docs/companion/PLAN-CO-07.md``:
``eval_datasets`` es **por tenant** y la conduce el grafo del agente de
cliente. El Companion no tiene tenant —su ``COMPANION_TENANT_ID`` es un UUID
sintético que en los logs significa "esto no es de nadie"— y su grafo es
otro. Meter estos casos ahí obligaría a inventar un tenant dueño.

Un caso declara tres cosas:

- **qué pidió la persona** (``user_message``) y con qué principal;
- **qué hizo el modelo** (``trajectory``): la lista de llamadas a
  herramienta y el texto que escribió. En modo offline es el dato de
  entrada; en modo live se descarta y lo produce el modelo de verdad;
- **qué tiene que cumplirse** (``expect``), y aparte lo que solo se puede
  exigir con un modelo detrás (``live``).

Las referencias al mundo sembrado se escriben como ``$a.ref`` / ``$b.ref`` /
``$a.user_id`` y se resuelven al cargar. **Ningún caso puede escribir un
``tenant_id`` ni un ``partner_id``**: no hay dónde ponerlo, y hay un test
que lo comprueba recorriendo el JSON en crudo.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

DATASET_DIR = Path(__file__).parent / "dataset"

Family = Literal["known_answer", "ambiguous", "cross_partner", "destructive"]

FAMILIES: tuple[Family, ...] = (
    "known_answer",
    "ambiguous",
    "cross_partner",
    "destructive",
)

#: Un fichero por familia. El nombre del fichero **es** la familia: un caso
#: cuya ``family`` no coincide con su fichero es un error de carga, no una
#: curiosidad.
FAMILY_FILES: dict[Family, str] = {
    "known_answer": "known_answer.json",
    "ambiguous": "ambiguous.json",
    "cross_partner": "cross_partner.json",
    "destructive": "destructive.json",
}

#: Prohibido en cualquier parte de un caso (§1.2 del contrato). Si un caso
#: necesitara nombrar un tenant, el catálogo estaría mal, no el caso.
FORBIDDEN_KEYS: frozenset[str] = frozenset({"tenant_id", "tenantid", "partner_id", "partnerid"})

#: Las seis prohibiciones del §6.5. Un caso de la familia 4 declara cuál
#: intenta cruzar; el nombre es estable y la interfaz no lo pinta.
FORBIDDEN_CAPABILITIES: frozenset[str] = frozenset(
    {
        "delete_client",
        "billing",
        "rotate_or_reveal_key",
        "disable_ai_disclosure",
        "other_partner",
        "reveal_secret_in_chat",
    }
)

_VAR_RE = re.compile(r"\$([ab])\.(\w+)")


class DatasetError(ValueError):
    """El fichero del dataset está malformado. Falla al cargar, no al correr."""


@dataclass(frozen=True)
class Step:
    """Un paso de la trayectoria guionizada.

    O pide una herramienta (``tool`` + ``args``) o escribe texto (``text``).
    Nunca las dos, porque el bucle del grafo trata cada paso como una
    llamada al proveedor y mezclarlas escondería en qué paso pasó qué.
    """

    tool: str | None = None
    args: dict[str, Any] = field(default_factory=dict)
    text: str | None = None

    @property
    def is_tool(self) -> bool:
        return self.tool is not None


@dataclass(frozen=True)
class Expect:
    """Lo exigible sin modelo. Todo opcional; un caso sin nada aquí se
    rechaza al cargar."""

    #: Lecturas con éxito esperadas en el turno. Es el numerador de R1.
    reads_ok: int | None = None
    #: Subcadenas que el CUERPO de la última lectura tiene que contener. Es
    #: lo que hace que "respuesta conocida" signifique algo: el dato sale de
    #: la base, no del caso.
    tool_body_contains: tuple[str, ...] = ()
    #: Y lo que NO puede traer. Es la forma de la filtración: un endpoint
    #: que acepta un ``client_ref`` ajeno sin rechazarlo tiene que devolver
    #: algo que no hable de ese cliente.
    tool_body_must_not_contain: tuple[str, ...] = ()
    #: Código de error esperado de la última llamada (``unknown_client``,
    #: ``bad_arguments``, ``unknown_tool``, ``already_read``…).
    tool_error_code: str | None = None
    #: El fallo tiene que ser indistinguible del de un ref inexistente.
    opaque_as_missing: bool = False
    #: Veredicto de R1 sobre el texto final del turno.
    unsupported: bool | None = None
    #: R2 — con más de un candidato, la trayectoria tiene que preguntar.
    r2_must_ask: bool = False
    #: R2 al revés: esta trayectoria eligió "el más probable" y el detector
    #: **tiene que** cazarla. Sin estos casos el detector se puede vaciar
    #: sin que nada se ponga rojo.
    r2_detects_violation: bool = False
    #: Cuántos candidatos tiene que devolver la búsqueda para que el caso
    #: sea de verdad ambiguo.
    min_candidates: int | None = None
    #: §6.5 — la capacidad que este caso intenta cruzar.
    forbidden_capability: str | None = None
    #: Herramientas que la trayectoria NO puede haber llamado.
    tools_must_not_call: tuple[str, ...] = ()
    #: **C4 (activado en la Fase 2).** La puerta única de escritura rechaza
    #: una acción que no esté ``confirmed``. No se prueba pidiéndoselo al
    #: modelo: se prueba llamando a ``console.apply`` con una acción en cada
    #: estado no confirmado y exigiendo que ninguna aplique.
    apply_requires_confirmation: bool = False

    def is_empty(self) -> bool:
        return not any(
            (
                self.reads_ok is not None,
                self.tool_body_contains,
                self.tool_body_must_not_contain,
                self.tool_error_code,
                self.opaque_as_missing,
                self.unsupported is not None,
                self.r2_must_ask,
                self.r2_detects_violation,
                self.apply_requires_confirmation,
                self.min_candidates is not None,
                self.forbidden_capability,
                self.tools_must_not_call,
            )
        )


@dataclass(frozen=True)
class CompanionCase:
    id: str
    family: Family
    title: str
    user_message: str
    #: Qué principal habla. ``a_builder`` es el mismo partner con un rol
    #: menor: es el único con el que se puede ver el techo de C6, porque un
    #: ``owner`` no puede escalar por encima de sí mismo.
    principal: Literal["a", "b", "a_builder"]
    trajectory: tuple[Step, ...]
    expect: Expect
    #: Aserciones que solo tienen sentido con el modelo real detrás. En modo
    #: offline se ignoran; el informe dice cuántas quedaron sin correr.
    live: dict[str, Any] = field(default_factory=dict)
    #: Trabajo del que depende el caso. ``None`` = corre hoy en verde.
    #: ``"co-04"`` = camino de escritura, ``xfail`` hasta la Fase 2.
    #: ``"live"`` = necesita modelo, ``xfail`` fuera del modo live.
    requires: str | None = None
    xfail_reason: str | None = None
    #: Texto de terceros que el caso inyecta en el contexto (documentos,
    #: motivos de rechazo). Se valla antes de entrar.
    untrusted_text: str | None = None
    #: Tope de llamadas del turno. Solo lo fijan los dos casos de control
    #: que prueban el tope duro; el resto usa el de producción.
    max_calls: int | None = None
    #: Modo del hilo. ``build`` por defecto; ``consult`` es el modo de solo
    #: lectura, y el caso que lo fija comprueba que el recorte no vive solo
    #: en el catálogo publicado sino en el motor.
    mode: str | None = None

    @property
    def final_text(self) -> str:
        """El último texto de la trayectoria. Es lo que juzga R1."""
        for step in reversed(self.trajectory):
            if step.text:
                return step.text
        return ""

    @property
    def tool_names(self) -> tuple[str, ...]:
        return tuple(s.tool for s in self.trajectory if s.tool)


def _resolve(value: Any, world: dict[str, Any]) -> Any:
    """Sustituye ``$a.ref`` por el valor real del mundo sembrado."""
    if isinstance(value, str):

        def _sub(match: re.Match[str]) -> str:
            side, key = match.group(1), match.group(2)
            try:
                return str(world[side][key])
            except KeyError as exc:  # pragma: no cover - error de caso
                raise DatasetError(f"el mundo no tiene {match.group(0)}") from exc

        return _VAR_RE.sub(_sub, value)
    if isinstance(value, dict):
        return {k: _resolve(v, world) for k, v in value.items()}
    if isinstance(value, list):
        return [_resolve(v, world) for v in value]
    return value


def _check_forbidden(node: Any, *, where: str) -> None:
    """Recorre el JSON en crudo buscando ``tenant_id`` / ``partner_id``."""
    if isinstance(node, dict):
        for key, value in node.items():
            if key.lower() in FORBIDDEN_KEYS:
                raise DatasetError(f"{where}: ninguna clave puede llamarse {key!r} (§1.2)")
            _check_forbidden(value, where=where)
    elif isinstance(node, list):
        for item in node:
            _check_forbidden(item, where=where)


def _step(raw: dict[str, Any], *, where: str) -> Step:
    has_tool = bool(raw.get("tool"))
    has_text = raw.get("text") is not None
    if has_tool == has_text:
        raise DatasetError(f"{where}: un paso es una herramienta O un texto, no las dos ni ninguna")
    return Step(tool=raw.get("tool"), args=dict(raw.get("args") or {}), text=raw.get("text"))


def _case(raw: dict[str, Any], *, family: Family, where: str) -> CompanionCase:
    case_id = raw.get("id")
    if not case_id:
        raise DatasetError(f"{where}: falta 'id'")
    where = f"{where}[{case_id}]"

    declared = raw.get("family")
    if declared != family:
        raise DatasetError(f"{where}: family={declared!r} en el fichero de {family!r}")

    principal = raw.get("principal", "a")
    if principal not in ("a", "b", "a_builder"):
        raise DatasetError(f"{where}: principal tiene que ser 'a', 'b' o 'a_builder'")

    trajectory = tuple(_step(s, where=where) for s in raw.get("trajectory") or [])
    if not trajectory:
        raise DatasetError(f"{where}: la trayectoria no puede estar vacía")

    expect_raw = dict(raw.get("expect") or {})
    unknown = set(expect_raw) - {f.name for f in Expect.__dataclass_fields__.values()}
    if unknown:
        raise DatasetError(f"{where}: expect no conoce {sorted(unknown)}")
    for key in ("tool_body_contains", "tool_body_must_not_contain", "tools_must_not_call"):
        if key in expect_raw:
            expect_raw[key] = tuple(expect_raw[key])
    expect = Expect(**expect_raw)
    if expect.is_empty():
        raise DatasetError(f"{where}: un caso sin 'expect' no comprueba nada")

    capability = expect.forbidden_capability
    if capability and capability not in FORBIDDEN_CAPABILITIES:
        raise DatasetError(f"{where}: {capability!r} no está en la lista cerrada del §6.5")

    requires = raw.get("requires")
    if requires and not raw.get("xfail_reason"):
        raise DatasetError(f"{where}: requires={requires!r} sin 'xfail_reason' legible")

    return CompanionCase(
        id=case_id,
        family=family,
        title=raw.get("title") or case_id,
        user_message=raw.get("user_message") or "",
        principal=principal,
        trajectory=trajectory,
        expect=expect,
        live=dict(raw.get("live") or {}),
        requires=requires,
        xfail_reason=raw.get("xfail_reason"),
        untrusted_text=raw.get("untrusted_text"),
        max_calls=raw.get("max_calls"),
        mode=raw.get("mode"),
    )


def load_family(family: Family, *, world: dict[str, Any] | None = None) -> list[CompanionCase]:
    """Carga y valida una familia. ``world`` resuelve las ``$a.ref``."""
    path = DATASET_DIR / FAMILY_FILES[family]
    payload = json.loads(path.read_text(encoding="utf-8"))
    _check_forbidden(payload, where=path.name)
    if world is not None:
        payload = _resolve(payload, world)
    cases = [_case(raw, family=family, where=path.name) for raw in payload.get("cases") or []]

    seen: set[str] = set()
    for case in cases:
        if case.id in seen:
            raise DatasetError(f"{path.name}: id duplicado {case.id!r}")
        seen.add(case.id)
    return cases


def load_dataset(*, world: dict[str, Any] | None = None) -> list[CompanionCase]:
    """Las cuatro familias, en orden. Es el dataset completo."""
    out: list[CompanionCase] = []
    for family in FAMILIES:
        out.extend(load_family(family, world=world))
    return out


__all__ = [
    "DATASET_DIR",
    "FAMILIES",
    "FAMILY_FILES",
    "FORBIDDEN_CAPABILITIES",
    "FORBIDDEN_KEYS",
    "CompanionCase",
    "DatasetError",
    "Expect",
    "Family",
    "Step",
    "load_dataset",
    "load_family",
]
