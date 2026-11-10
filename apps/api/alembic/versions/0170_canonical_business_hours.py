"""El horario del negocio en una sola forma — bug ``horario-del-negocio-en-tres-formas``.

``tenants.business_hours`` llegó a la base en tres formas: la del asistente del
panel de operador (``"09:00-18:00"``/``"closed"``), la de la semilla de Boreal
(``{"open", "close"}``/``None``) y la que esperaba la disponibilidad del agente
(``{"start", "end"}``). Desde el arreglo, la API solo guarda la canónica::

    {"monday": [{"from": "09:00", "to": "18:00"}], ..., "sunday": []}

Esto pasa las filas existentes a esa forma. Una fila que no se entiende entera
**se deja como estaba**: el lector (``services/business_hours.py``) la lee
igual, día a día, y un día ilegible sale cerrado. Mejor eso que inventar.

El normalizador está copiado aquí a propósito, congelado: una migración no
importa código de la aplicación, que mañana puede cambiar.

Idempotente: la forma canónica es un punto fijo. ``downgrade`` no deshace la
normalización (la forma antigua no se recuerda y la canónica la leen todos).

Revision ID: 0170_canonical_business_hours
Revises: 0169_client_phone_audit_vocab
"""

from __future__ import annotations

import json
import re
from collections.abc import Sequence
from itertools import pairwise
from typing import Any

import sqlalchemy as sa

from alembic import op

revision: str = "0170_canonical_business_hours"
down_revision: str | Sequence[str] | None = "0169_client_phone_audit_vocab"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_DAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
_HHMM = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")
_RANGE = re.compile(r"^\s*(\d{2}:\d{2})\s*-\s*(\d{2}:\d{2})\s*$")
_PAIRS = (("from", "to"), ("start", "end"), ("open", "close"))


def _hhmm(v: Any) -> str | None:
    return v.strip() if isinstance(v, str) and _HHMM.match(v.strip()) else None


def _one(raw: Any) -> tuple[str, str] | None:
    a = b = None
    if isinstance(raw, str):
        m = _RANGE.match(raw)
        if m:
            a, b = _hhmm(m.group(1)), _hhmm(m.group(2))
    elif isinstance(raw, dict):
        for x, y in _PAIRS:
            if x in raw or y in raw:
                a, b = _hhmm(raw.get(x)), _hhmm(raw.get(y))
                break
    if a is None or b is None or b <= a:
        return None
    return (a, b)


def _day(raw: Any) -> list[dict[str, str]] | None:
    if raw is None or (isinstance(raw, list) and not raw):
        return []
    if isinstance(raw, str) and raw.strip().lower() in ("", "closed", "cerrado"):
        return []
    items = raw if isinstance(raw, list) else [raw]
    ranges = []
    for item in items:
        r = _one(item)
        if r is None:
            return None
        ranges.append(r)
    ranges.sort()
    for prev, nxt in pairwise(ranges):
        if nxt[0] < prev[1]:
            return None
    return [{"from": a, "to": b} for a, b in ranges]


def _canonical(raw: Any) -> dict[str, list[dict[str, str]]] | None:
    if not isinstance(raw, dict) or not any(d in raw for d in _DAYS):
        return None
    if any(k not in _DAYS and k != "label" for k in raw):
        return None
    out: dict[str, list[dict[str, str]]] = {}
    for d in _DAYS:
        day = _day(raw.get(d))
        if day is None:
            return None
        out[d] = day
    return out


def upgrade() -> None:
    conn = op.get_bind()
    rows = conn.execute(
        sa.text("SELECT id, business_hours FROM tenants WHERE business_hours IS NOT NULL")
    ).all()
    for tenant_id, raw in rows:
        canonical = _canonical(raw)
        if canonical is None or canonical == raw:
            continue
        conn.execute(
            sa.text("UPDATE tenants SET business_hours = CAST(:h AS jsonb) WHERE id = :i"),
            {"h": json.dumps(canonical), "i": tenant_id},
        )


def downgrade() -> None:
    # La forma canónica la leen todas las versiones del lector posteriores al
    # arreglo; la anterior no se recuerda. No hay nada útil que deshacer.
    pass
