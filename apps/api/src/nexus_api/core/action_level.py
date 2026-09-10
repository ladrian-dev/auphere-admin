"""El nivel de aviso de una aprobación — spec 003, Requisito 7.1.

Tres niveles, fijados **al proponer** y no al pintar: la pantalla no puede
inventarse la urgencia de algo que no vio hacer, y el móvil (beta 3) tendrá que
decidir si suena con el mismo dato.

* ``critico``     — toca la máquina de la persona, o el propio agente lo marcó
                    de riesgo alto. Interrumpe: aviso del sistema operativo.
* ``aviso``       — cambia algo. Marca la bandeja, no interrumpe.
* ``informativo`` — no cambia nada (un ticket de soporte, una nota). No suena.

Vive en ``core`` y no en ``services`` por una regla del carril que un test de
aislamiento vigila: **un módulo de herramientas del Companion no importa
servicios ni repositorios** — una herramienta llama a ``/console/*`` por HTTP, y
llamar a un servicio se saltaría el ámbito, la RLS, la cuota y la auditoría.
Esto es un clasificador puro sin base de datos, así que su sitio es ``core``,
junto a ``respond_catalog`` y ``partner_allowlist``.

Es deliberadamente **cerrado y sin configuración**: un nivel que el partner
pudiera subir convertiría «crítico» en ruido y dejaría de significar nada.
"""

from __future__ import annotations

ACTION_LEVELS: tuple[str, ...] = ("critico", "aviso", "informativo")

#: Lo que se ejecuta en la máquina del partner (Requisito 10). Siempre crítico:
#: es lo único de esta lista que sale de la plataforma.
MACHINE_KINDS: frozenset[str] = frozenset({"local_exec"})

#: Lo que no cambia nada de nadie. Todo lo demás que se propone, cambia algo.
INFORMATIVE_KINDS: frozenset[str] = frozenset({"support_ticket", "support_help", "note"})


def level_for(*, kind: str, risk: str | None) -> str:
    """El nivel de una acción por su tipo y el riesgo que declaró el agente."""
    if kind in MACHINE_KINDS or risk == "high":
        return "critico"
    if not kind or kind in INFORMATIVE_KINDS:
        return "informativo"
    return "aviso"


__all__ = ["ACTION_LEVELS", "INFORMATIVE_KINDS", "MACHINE_KINDS", "level_for"]
