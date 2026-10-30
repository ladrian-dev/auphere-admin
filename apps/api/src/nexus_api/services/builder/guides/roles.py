"""Role patterns for the builder — spec 047, amendment of 2026-10-29 (requirement
58.2; research D47 and D67).

Four of Auphere's patterns — reception, sales, billing and support — that the
builder receives as **combinable examples** of how such a job is usually done,
next to the sector's guide and the fenced profile.

There are no fixed roles (owner, 2026-10-30): a client can create an agent for
anything, and two agents can share a job. So:

- every pattern that fits the description is passed, not one winner; when none
  fits, all four are passed and the model reads the description itself (no
  «support» by default);
- no pattern decides tools nor tests: the tools come from the catalog and what
  this client has available (``validator.load_context``), the tests from the
  sector's guide;
- no pattern names an action no tool does (there is no tool that creates a
  payment link).
"""

from __future__ import annotations

import re
import unicodedata
from typing import Final

ROLES: Final[tuple[str, ...]] = ("reception", "sales", "billing", "support")

ROLE_NAMES: Final[dict[str, str]] = {
    "reception": "Recepción",
    "sales": "Ventas",
    "billing": "Cobros",
    "support": "Soporte",
}

PATTERNS: Final[dict[str, str]] = {
    "reception": (
        "Recepción: saluda, entiende qué necesita la persona y para cuándo. Si el agente "
        "tiene la agenda, busca hueco, ofrece dos opciones y confirma con el día y la hora "
        "en palabras, recordando la política de cancelación. Si no la tiene, toma los datos "
        "y pasa la petición al equipo sin prometer hora. Cambios y cancelaciones, igual."
    ),
    "sales": (
        "Ventas: entiende la necesidad con dos o tres preguntas y ofrece solo lo que está "
        "en el catálogo o en la ficha, con su precio. Nunca inventa existencias, plazos ni "
        "descuentos; para cerrar una compra, sigue lo que diga la ficha o pasa al equipo."
    ),
    "billing": (
        "Cobros: recuerda con amabilidad el importe y el vencimiento, explica cómo se paga "
        "según la ficha y pasa al equipo cualquier disputa sobre el importe. Nunca amenaza "
        "ni pide datos de tarjeta por WhatsApp."
    ),
    "support": (
        "Soporte: responde con los datos de la ficha del negocio, en frases cortas. Lo que "
        "no esté en la ficha lo dice y ofrece pasar la consulta al equipo."
    ),
}

#: Words that make a pattern fit, without accents. Only to pick examples.
_WORDS: Final[dict[str, frozenset[str]]] = {
    "reception": frozenset(
        {
            "cita", "citas", "reserva", "reservas", "reservar", "agenda", "agendar",
            "turno", "turnos", "hueco", "huecos", "mesa", "mesas", "recepcion",
            "recepcionista", "booking", "appointment", "appointments",
        }
    ),
    "sales": frozenset(
        {
            "venta", "ventas", "vende", "vender", "vendedor", "pedido", "pedidos", "catalogo",
            "producto", "productos", "comprar", "compra", "compras", "tienda", "presupuesto",
            "presupuestos", "oferta",
        }
    ),
    "billing": frozenset(
        {
            "cobro", "cobros", "cobra", "cobrar", "cobranza", "pago", "pagos", "deuda",
            "deudas", "factura", "facturas", "recibo", "recibos", "impago", "impagos",
            "moroso", "morosos",
        }
    ),
    "support": frozenset(
        {
            "duda", "dudas", "pregunta", "preguntas", "informacion", "informa", "soporte",
            "incidencia", "incidencias", "ayuda", "atencion",
        }
    ),
}  # fmt: skip


def _plain(text: str) -> str:
    folded = unicodedata.normalize("NFKD", (text or "").lower())
    return "".join(c for c in folded if not unicodedata.combining(c))


def roles_for(description: str) -> list[str]:
    """Every pattern with at least one of its words in the description, in the
    order of :data:`ROLES`; all of them when none fits."""
    words = set(re.findall(r"[a-z0-9]+", _plain(description)))
    fit = [role for role in ROLES if words & _WORDS[role]]
    return fit or list(ROLES)


def patterns_text(roles: list[str]) -> str:
    """The patterns as examples, one per line."""
    return "\n".join(f"- {PATTERNS[role]}" for role in roles if role in PATTERNS)


__all__ = ["PATTERNS", "ROLES", "ROLE_NAMES", "patterns_text", "roles_for"]
