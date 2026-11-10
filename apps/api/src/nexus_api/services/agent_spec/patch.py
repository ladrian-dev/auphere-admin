"""Parches sobre un AgentSpec — spec 047, T078 (requisitos 15.2 y 16).

Una propuesta ``agent_spec_patch`` es una lista de operaciones sobre punteros
JSON del documento, el subconjunto de RFC 6902 que hace falta:

- ``add``: en un objeto, pone la clave; en una lista, inserta en la posición o al
  final con ``-``;
- ``replace``: cambia un valor que existe;
- ``remove``: quita una clave o un elemento.

Aplicar no valida: el resultado pasa por ``validator.validate_spec`` antes de
enseñarse y otra vez al aplicarse. Nunca toca el documento de entrada.
"""

from __future__ import annotations

import copy
from collections.abc import Mapping, Sequence
from typing import Any, Literal, TypedDict


class PatchError(ValueError):
    def __init__(self, pointer: str, message: str) -> None:
        super().__init__(f"{pointer}: {message}")
        self.pointer = pointer


class Op(TypedDict, total=False):
    op: Literal["add", "replace", "remove"]
    path: str
    value: Any


def _parts(pointer: str) -> list[str]:
    if pointer == "":
        return []
    if not pointer.startswith("/"):
        raise PatchError(pointer, "un puntero empieza por /")
    return [p.replace("~1", "/").replace("~0", "~") for p in pointer[1:].split("/")]


def _index(node: list[Any], part: str, pointer: str, *, allow_end: bool) -> int:
    if part == "-" and allow_end:
        return len(node)
    if not part.isdigit():
        raise PatchError(pointer, "índice no válido")
    index = int(part)
    if index > len(node) or (index == len(node) and not allow_end):
        raise PatchError(pointer, "índice fuera de la lista")
    return index


def apply_ops(doc: Mapping[str, Any], ops: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = copy.deepcopy(dict(doc))
    for raw in ops:
        op = str(raw.get("op"))
        pointer = str(raw.get("path", ""))
        parts = _parts(pointer)
        if not parts:
            raise PatchError(pointer, "no se puede cambiar el documento entero")
        parent: Any = out
        for i, part in enumerate(parts[:-1]):
            if isinstance(parent, list):
                parent = parent[_index(parent, part, pointer, allow_end=False)]
            elif isinstance(parent, dict):
                if part not in parent:
                    if op != "add":
                        raise PatchError(pointer, "no existe")
                    # ``add`` sobre una rama que no existe la crea (un objeto o
                    # una lista, según lo que venga después).
                    nxt = parts[i + 1]
                    parent[part] = [] if (nxt == "-" or nxt.isdigit()) else {}
                parent = parent[part]
            else:
                raise PatchError(pointer, "no existe")
        last = parts[-1]
        if isinstance(parent, list):
            if op == "add":
                parent.insert(
                    _index(parent, last, pointer, allow_end=True), copy.deepcopy(raw.get("value"))
                )
            elif op == "replace":
                parent[_index(parent, last, pointer, allow_end=False)] = copy.deepcopy(
                    raw.get("value")
                )
            elif op == "remove":
                parent.pop(_index(parent, last, pointer, allow_end=False))
            else:
                raise PatchError(pointer, f"operación desconocida: {op}")
        elif isinstance(parent, dict):
            if op == "add":
                parent[last] = copy.deepcopy(raw.get("value"))
            elif op == "replace":
                if last not in parent:
                    raise PatchError(pointer, "no existe")
                parent[last] = copy.deepcopy(raw.get("value"))
            elif op == "remove":
                if last not in parent:
                    raise PatchError(pointer, "no existe")
                del parent[last]
            else:
                raise PatchError(pointer, f"operación desconocida: {op}")
        else:
            raise PatchError(pointer, "no existe")
    return out


def diff_ops(before: Mapping[str, Any], after: Mapping[str, Any]) -> list[Op]:
    """Las operaciones que llevan de ``before`` a ``after``, de primer nivel y en
    orden de claves: lo justo para enseñar un diff legible y reproducirlo."""
    ops: list[Op] = []
    for key in sorted(set(before) | set(after)):
        if key not in after:
            ops.append({"op": "remove", "path": f"/{key}"})
        elif key not in before:
            ops.append({"op": "add", "path": f"/{key}", "value": copy.deepcopy(after[key])})
        elif before[key] != after[key]:
            ops.append({"op": "replace", "path": f"/{key}", "value": copy.deepcopy(after[key])})
    return ops


__all__ = ["Op", "PatchError", "apply_ops", "diff_ops"]
