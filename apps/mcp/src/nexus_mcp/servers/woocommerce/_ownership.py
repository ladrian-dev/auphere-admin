"""De quién es un pedido — la garantía 8 aplicada a la tienda.

`booking.*` lo tiene fácil: la cita lleva `customer_id`, que es una fila
nuestra, y comparar dos UUID no admite interpretación. Aquí no. El pedido vive
en WooCommerce, la persona vive en `customers`, y lo único que las dos conocen
es cómo contactar a alguien: un teléfono, a veces un correo.

Así que la pertenencia es un juicio, y los juicios se equivocan en dos
direcciones que **no cuestan lo mismo**:

- Decir que no a un pedido que sí era suyo: la persona se queda sin ver su
  seguimiento y el agente la deriva a un humano. Molesto.
- Decir que sí a un pedido ajeno: `get_order` devuelve la dirección de envío.
  Eso no es una molestia, es la dirección de casa de alguien.

Por eso todo lo de aquí **falla cerrado**. Sin identificador, sin coincidencia,
o con un dato a medias: no es suyo. Un pedido de invitado sin teléfono ni correo
no se le atribuye a nadie, aunque el número de pedido sea el que la persona
acaba de decir en voz alta.

Puro a propósito: sin base de datos y sin red, para que la regla se pueda leer
y probar de un vistazo.
"""

from __future__ import annotations

import re
from typing import Any

# Lo mínimo para que dos teléfonos escritos por humanos distintos se reconozcan.
# `customers.identifier` es E.164 sin el `+` (``56912345678``); WooCommerce
# guarda lo que la persona tecleó en el checkout (``+56 9 1234 5678``).
_NON_DIGITS = re.compile(r"\D+")

# Dos números cortos coinciden por casualidad con demasiada facilidad. Nueve
# dígitos es el móvil más corto de los países donde operamos; por debajo de eso
# preferimos no atribuir.
_MIN_SIGNIFICANT_DIGITS = 9

# Las líneas nacionales difieren en el prefijo internacional y en el 0 de
# tránsito, así que se comparan los últimos dígitos, que es la parte que
# identifica de verdad al abonado.
_COMPARE_TAIL = 9


def phone_key(raw: str | None) -> str | None:
    """Los dígitos que identifican a un abonado, o None si no bastan."""
    if not raw:
        return None
    digits = _NON_DIGITS.sub("", raw)
    if len(digits) < _MIN_SIGNIFICANT_DIGITS:
        return None
    return digits[-_COMPARE_TAIL:]


def email_key(raw: str | None) -> str | None:
    """Un correo comparable, o None si no lo parece."""
    if not raw:
        return None
    cleaned = raw.strip().lower()
    if "@" not in cleaned or cleaned.startswith("@") or cleaned.endswith("@"):
        return None
    return cleaned


def _billing(order: dict[str, Any]) -> dict[str, Any]:
    billing = order.get("billing")
    return billing if isinstance(billing, dict) else {}


def order_belongs_to(order: dict[str, Any], *, phone: str | None, email: str | None) -> bool:
    """¿Este pedido es de la persona que está escribiendo?

    `phone` y `email` son de **nuestra** fila de cliente, nunca del modelo.
    """
    mine_phone = phone_key(phone)
    mine_email = email_key(email)
    if mine_phone is None and mine_email is None:
        # No sabemos quién es. Falla cerrado: ver arriba por qué.
        return False

    billing = _billing(order)

    if mine_email is not None and email_key(billing.get("email")) == mine_email:
        return True
    return mine_phone is not None and phone_key(billing.get("phone")) == mine_phone


def own_orders(
    orders: list[dict[str, Any]], *, phone: str | None, email: str | None
) -> list[dict[str, Any]]:
    return [o for o in orders if order_belongs_to(o, phone=phone, email=email)]


__all__ = ["email_key", "order_belongs_to", "own_orders", "phone_key"]
