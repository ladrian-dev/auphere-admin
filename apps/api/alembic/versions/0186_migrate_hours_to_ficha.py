"""El horario pasa a la ficha — spec 047, T061 (requisitos 8.2 y 55.1, research D15).

Hasta aquí el horario vivía en tres copias que no se hablaban:

1. ``tenants.business_hours`` (Reservas, la app, la disponibilidad del agente),
   en cualquiera de sus cuatro formas (la canónica de la 0170 y las tres de
   antes: ``"09:00-18:00"``/``"closed"``, ``{"open", "close"}`` y
   ``{"start", "end"}``);
2. su ``label``, la frase que se escribía a mano para el prompt;
3. ``policies.console.schedule`` de la versión activa del agente principal.

Esto las pasa a la ficha (``business_schedules`` + ``business_shifts``, el horario
del negocio), cliente a cliente, **sin tocar ningún prompt ni ninguna versión**
(research D4: recompilar al migrar rompería el «responde igual»):

- con días en ``tenants.business_hours``, esos días: es lo que edita el negocio en
  Reservas. Procedencia «Migrado», confirmada;
- si no, el horario de la consola (``policies.console.schedule``), igual;
- si las dos tenían días y no coinciden, gana el de Reservas y el de la consola
  queda como sugerencia al lado: no se pierde nada;
- si solo había la frase del prompt (``label``, texto libre que no se puede leer
  como turnos), queda como sugerencia «Migrado · revísalo» de ``/hours`` y la
  sección pendiente de revisar: el agente sigue diciendo lo de su prompt hasta
  que una persona escriba el horario.

Un cliente que ya tiene el horario en la ficha no se toca, así que es
idempotente. Un cliente de antes de la ficha recibe su ``business_profiles`` (con
lo que se sabe de él: zona, mercado y el nicho de su plantilla) y sus nueve
secciones. ``tenants.business_hours`` se queda como está: es la proyección hasta
la próxima escritura.

El lector está copiado aquí a propósito, congelado: una migración no importa
código de la aplicación, que mañana puede cambiar.

``downgrade`` quita lo que esta migración puso (los horarios con procedencia
«Migrado» y sus sugerencias); las fichas creadas se quedan, vacías de horario.

Revision ID: 0186_migrate_hours_to_ficha
Revises: 0185_bedrock_scaleway_drafts
"""

from __future__ import annotations

import json
import re
import uuid
from collections.abc import Sequence
from itertools import pairwise
from typing import Any

import sqlalchemy as sa

from alembic import op

revision: str = "0186_migrate_hours_to_ficha"
down_revision: str | Sequence[str] | None = "0185_bedrock_scaleway_drafts"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_DAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
_SHORT = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
_HHMM = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")
_RANGE = re.compile(r"^\s*(\d{2}:\d{2})\s*-\s*(\d{2}:\d{2})\s*$")
_PAIRS = (("from", "to"), ("start", "end"), ("open", "close"))
_SECTIONS = {
    "basics": "complete",
    "locations": "pending",
    "hours": "pending",
    "special_dates": "optional",
    "services": "pending",
    "policies": "optional",
    "faqs": "optional",
    "sources": "pending",
    "links": "pending",
}
#: El nicho de cada plantilla (``profile.TEMPLATE_NICHES``, congelado).
_NICHES = {
    "barbershop_v1": "Barbería",
    "beauty_salon_v1": "Peluquería y salón de belleza",
    "nail_studio_v1": "Estudio de uñas",
    "spa_v1": "Spa y bienestar",
    "clinica_v1": "Clínica o consultorio médico",
    "dental_v1": "Clínica dental",
    "aesthetic_clinic_v1": "Clínica estética",
    "medspa_v1": "Medicina estética",
    "restaurante_v1": "Restaurante",
    "woocommerce_sales_v1": "Tienda online",
    "inventario_v1": "Almacén e inventario",
    "cobranza_v1": "Cobranza",
}
#: Los mercados de la plataforma: moneda de los precios y si es de la UE.
_MARKETS = {
    "CL": ("CLP", False),
    "AR": ("ARS", False),
    "MX": ("MXN", False),
    "CO": ("COP", False),
    "PE": ("PEN", False),
    "UY": ("UYU", False),
    "US": ("USD", False),
    "ES": ("EUR", True),
    "PT": ("EUR", True),
}
_ACTOR = {"actor_kind": "system", "actor_id": "migration-0186", "origin": "system"}


# ── el lector, congelado ────────────────────────────────────────────────────


def _minutes(raw: Any) -> int | None:
    if not isinstance(raw, str):
        return None
    m = _HHMM.match(raw.strip())
    return int(m.group(1)) * 60 + int(m.group(2)) if m else None


def _one(raw: Any) -> tuple[int, int] | None:
    a = b = None
    if isinstance(raw, str):
        m = _RANGE.match(raw)
        if m:
            a, b = _minutes(m.group(1)), _minutes(m.group(2))
    elif isinstance(raw, dict):
        for x, y in _PAIRS:
            if x in raw or y in raw:
                a, b = _minutes(raw.get(x)), _minutes(raw.get(y))
                break
    if a is None or b is None or b <= a:
        return None
    return (a, b)


def _day(raw: Any) -> list[tuple[int, int]]:
    """Los turnos de un día; un día ilegible sale cerrado (como el lector)."""
    if raw is None or (isinstance(raw, list) and not raw):
        return []
    if isinstance(raw, str) and raw.strip().lower() in ("", "closed", "cerrado"):
        return []
    items = raw if isinstance(raw, list) else [raw]
    ranges = []
    for item in items:
        r = _one(item)
        if r is None:
            return []
        ranges.append(r)
    ranges.sort()
    for prev, nxt in pairwise(ranges):
        if nxt[0] < prev[1]:
            return []
    return ranges[:6]


def week_of_business_hours(raw: Any) -> list[list[tuple[int, int]]] | None:
    """``tenants.business_hours`` en cualquiera de sus formas → siete días.
    ``None``: no hay días (nada guardado, o solo la frase del prompt)."""
    if not isinstance(raw, dict) or not any(d in raw for d in _DAYS):
        return None
    return [_day(raw.get(d)) for d in _DAYS]


def week_of_console(policies: Any) -> list[list[tuple[int, int]]] | None:
    """``policies.console.schedule.weekly`` → siete días. ``None`` sin turnos."""
    console = policies.get("console") if isinstance(policies, dict) else None
    schedule = console.get("schedule") if isinstance(console, dict) else None
    weekly = schedule.get("weekly") if isinstance(schedule, dict) else None
    if not isinstance(weekly, list) or not weekly:
        return None
    days: list[list[tuple[int, int]]] = [[] for _ in _DAYS]
    for slot in weekly:
        if not isinstance(slot, dict) or slot.get("day") not in _SHORT:
            continue
        a, b = _minutes(slot.get("open")), _minutes(slot.get("close"))
        if a is None or b is None or b <= a:
            continue
        days[_SHORT.index(slot["day"])].append((a, b))
    out: list[list[tuple[int, int]]] = []
    for d in days:
        d.sort()
        clean: list[tuple[int, int]] = []
        for r in d:
            if clean and r[0] < clean[-1][1]:
                continue
            clean.append(r)
        out.append(clean[:6])
    return out if any(out) else None


def _hhmm(minutes: int) -> str:
    return f"{minutes // 60:02d}:{minutes % 60:02d}"


def _view(week: list[list[tuple[int, int]]]) -> dict[str, Any]:
    layout = "blocks" if all(d == week[0] for d in week[1:5]) else "daily"
    return {
        "layout": layout,
        "days": {
            _SHORT[i]: [{"open": _hhmm(a), "close": _hhmm(b)} for a, b in week[i]] for i in range(7)
        },
    }


# ── la migración ────────────────────────────────────────────────────────────


def _ensure_profile(conn: Any, tenant: Any) -> None:
    exists = conn.execute(
        sa.text("SELECT 1 FROM business_profiles WHERE tenant_id = :t"), {"t": tenant.id}
    ).first()
    if exists is None:
        template = conn.execute(
            sa.text(
                "SELECT seed_template_ref FROM agent_configs WHERE tenant_id = :t "
                "AND seed_template_ref IS NOT NULL ORDER BY version DESC LIMIT 1"
            ),
            {"t": tenant.id},
        ).scalar()
        market = (tenant.market or "").upper()
        currency, eu = _MARKETS.get(market, (None, False))
        conn.execute(
            sa.text(
                "INSERT INTO business_profiles (tenant_id, niche, timezone, country, "
                "price_currency, eu_only, policies, content_rev) VALUES "
                "(:t, :niche, :tz, :country, :currency, :eu, '{}'::jsonb, 1)"
            ),
            {
                "t": tenant.id,
                "niche": _NICHES.get(template or "", "Negocio"),
                "tz": tenant.timezone or "UTC",
                "country": market if market in _MARKETS else None,
                "currency": currency,
                "eu": eu,
            },
        )
        for pointer in ("/business/niche", "/business/timezone"):
            _provenance(conn, tenant.id, pointer, review="confirmed")
    for section, state in _SECTIONS.items():
        conn.execute(
            sa.text(
                "INSERT INTO business_sections (tenant_id, section, revision, state, "
                "updated_by_kind, updated_by_id, updated_origin) VALUES "
                "(:t, :s, 0, :state, 'system', 'migration-0186', 'system') "
                "ON CONFLICT (tenant_id, section) DO NOTHING"
            ),
            {"t": tenant.id, "s": section, "state": state},
        )


def _provenance(conn: Any, tenant_id: Any, pointer: str, *, review: str) -> None:
    conn.execute(
        sa.text(
            "INSERT INTO business_field_provenance (tenant_id, pointer, source, actor_kind, "
            "actor_id, origin, review) VALUES (:t, :p, 'migrated', :actor_kind, :actor_id, "
            ":origin, :review) ON CONFLICT (tenant_id, pointer) DO UPDATE SET "
            "source = 'migrated', review = EXCLUDED.review, at = now()"
        ),
        {"t": tenant_id, "p": pointer, "review": review, **_ACTOR},
    )


def _suggest(conn: Any, tenant_id: Any, value: dict[str, Any], current: Any) -> None:
    conn.execute(
        sa.text(
            "INSERT INTO business_suggestions (id, tenant_id, pointer, proposed_value, "
            "current_value, source) VALUES (:id, :t, '/hours', CAST(:v AS jsonb), "
            "CAST(:c AS jsonb), 'migrated')"
        ),
        {
            "id": uuid.uuid4(),
            "t": tenant_id,
            "v": json.dumps(value),
            "c": json.dumps(current) if current is not None else None,
        },
    )


def _touch(conn: Any, tenant_id: Any, state: str) -> None:
    conn.execute(
        sa.text(
            "UPDATE business_sections SET revision = revision + 1, state = :state, "
            "updated_at = now(), updated_by_kind = 'system', updated_by_id = 'migration-0186', "
            "updated_origin = 'system' WHERE tenant_id = :t AND section = 'hours'"
        ),
        {"t": tenant_id, "state": state},
    )


def _write_week(conn: Any, tenant_id: Any, week: list[list[tuple[int, int]]]) -> dict[str, Any]:
    view = _view(week)
    schedule_id = uuid.uuid4()
    conn.execute(
        sa.text(
            "INSERT INTO business_schedules (id, tenant_id, location_id, layout) "
            "VALUES (:id, :t, NULL, :layout)"
        ),
        {"id": schedule_id, "t": tenant_id, "layout": view["layout"]},
    )
    for weekday, shifts in enumerate(week):
        for open_min, close_min in shifts:
            conn.execute(
                sa.text(
                    "INSERT INTO business_shifts (id, tenant_id, schedule_id, weekday, "
                    "open_min, close_min) VALUES (:id, :t, :s, :w, :o, :c)"
                ),
                {
                    "id": uuid.uuid4(),
                    "t": tenant_id,
                    "s": schedule_id,
                    "w": weekday,
                    "o": open_min,
                    "c": close_min,
                },
            )
    conn.execute(
        sa.text(
            "INSERT INTO business_changes (id, tenant_id, section, kind, before, after, "
            "actor_kind, actor_id, origin) VALUES (:id, :t, 'hours', 'migration', NULL, "
            "CAST(:after AS jsonb), :actor_kind, :actor_id, :origin)"
        ),
        {"id": uuid.uuid4(), "t": tenant_id, "after": json.dumps({"hours": view}), **_ACTOR},
    )
    return view


def upgrade() -> None:
    conn = op.get_bind()
    tenants = conn.execute(
        sa.text("SELECT id, timezone, market, business_hours FROM tenants ORDER BY created_at")
    ).all()
    for tenant in tenants:
        has_schedule = conn.execute(
            sa.text(
                "SELECT 1 FROM business_schedules WHERE tenant_id = :t AND location_id IS NULL"
            ),
            {"t": tenant.id},
        ).first()
        if has_schedule is not None:
            continue
        policies = conn.execute(
            sa.text(
                "SELECT c.policies FROM agent_configs c JOIN agents a "
                "ON a.tenant_id = c.tenant_id AND a.id = c.agent_id "
                "WHERE c.tenant_id = :t AND c.status = 'active' AND a.status = 'active' "
                "ORDER BY a.created_at LIMIT 1"
            ),
            {"t": tenant.id},
        ).scalar()
        stored = week_of_business_hours(tenant.business_hours)
        console = week_of_console(policies)
        raw = tenant.business_hours if isinstance(tenant.business_hours, dict) else {}
        label = raw.get("label") if isinstance(raw.get("label"), str) else None
        week = stored or console
        if week is None and not label:
            continue
        _ensure_profile(conn, tenant)
        if week is None:
            # Solo la frase del prompt: no se puede leer como turnos.
            _suggest(conn, tenant.id, {"label": label}, None)
            _provenance(conn, tenant.id, "/hours", review="pending")
            _touch(conn, tenant.id, "read_pending")
            continue
        view = _write_week(conn, tenant.id, week)
        _provenance(conn, tenant.id, "/hours", review="confirmed")
        if stored is not None and console is not None and console != stored:
            _suggest(conn, tenant.id, _view(console), view)
        _touch(conn, tenant.id, "complete")


def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(
        sa.text(
            "DELETE FROM business_schedules s USING business_field_provenance p "
            "WHERE s.location_id IS NULL AND p.tenant_id = s.tenant_id "
            "AND p.pointer = '/hours' AND p.source = 'migrated'"
        )
    )
    conn.execute(
        sa.text("DELETE FROM business_suggestions WHERE pointer = '/hours' AND source = 'migrated'")
    )
    conn.execute(
        sa.text(
            "DELETE FROM business_changes WHERE section = 'hours' AND kind = 'migration' "
            "AND actor_id = 'migration-0186'"
        )
    )
    conn.execute(
        sa.text(
            "DELETE FROM business_field_provenance WHERE pointer = '/hours' AND source = 'migrated'"
        )
    )
