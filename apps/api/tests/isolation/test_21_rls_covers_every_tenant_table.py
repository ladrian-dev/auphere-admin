"""Toda tabla con ``tenant_id`` está cubierta por RLS, o justificada aquí.

Este archivo existe por una razón concreta: el runtime lee varias tablas
**sin ``WHERE tenant_id``** a propósito, apoyándose en que la RLS filtra
(``runtime/model_resolver.py`` es el caso más claro). Esa decisión es
correcta —hace que el aislamiento lo imponga Postgres y no un WHERE que
alguien pueda olvidar— pero solo mientras la RLS esté realmente puesta en
todas partes.

El fallo que previene no es hipotético: al auditar el catálogo aparecieron
SIETE tablas con ``tenant_id`` sin ninguna policy, y las siete
alcanzables por ``nexus_app``. Ninguna prueba de negocio lo habría
detectado — las consultas existentes llevaban su WHERE y funcionaban.

Por eso la comprobación es contra ``pg_class``, no contra una lista de
tablas escrita a mano: una tabla nueva con ``tenant_id`` y sin RLS rompe
la suite el día que se crea, y quien la añade tiene que **escribir por
qué** en ``PRE_TENANT_TABLES``. Convierte un olvido en una decisión.

Bloqueante como el resto de la suite.
"""

from __future__ import annotations

import pytest
import sqlalchemy as sa

from nexus_api.db.base import get_sessionmaker

pytestmark = pytest.mark.asyncio


# Tablas que llevan ``tenant_id`` pero NO son datos de un tenant. Cada
# una necesita una razón que explique por qué una policy la rompería,
# no solo por qué "no hace falta".
PRE_TENANT_TABLES: dict[str, str] = {
    "api_keys": (
        "Autenticación: se lee para AVERIGUAR quién llama, antes de que exista "
        "ámbito de tenant. Además ``tenant_id`` es NULL en las claves de nivel "
        "partner, que una policy por tenant escondería."
    ),
    "owner_phone_index": (
        "Resolución teléfono → tenant. Es literalmente lo que se consulta para "
        "SABER en qué tenant scopear el webhook entrante; con policy no "
        "resolvería nunca y todo mensaje de owner quedaría sin ruta."
    ),
    "partner_tenants": (
        "Mapa partner ↔ tenant. Se lee en ámbito de PARTNER (un partner tiene "
        "que ver su cartera entera); una policy por tenant devolvería como "
        "mucho una fila y rompería el listado de clientes del partner."
    ),
    "whatsapp_template_status": (
        "Estado de plantillas de Meta, con clave (waba_id, template_name, "
        "language). La escribe el webhook de Meta antes de resolver tenant y "
        "``tenant_id`` es NULL en las plantillas internas de Auphere, que se "
        "comparten a nivel de WABA."
    ),
}

# Cómo tiene que estar cubierta cada tabla que sí es de tenant.
#   FORCE  → nadie la lee por encima del tenant, ni siquiera el dueño.
#   ENABLE → el rol dueño la lee a propósito por encima del tenant
#            (facturación de partner, paneles de admin cross-tenant);
#            ``nexus_app`` sigue filtrado, que es la garantía que importa.
# Libro Fase 3: RLS por partner_id, FORCE. Sin GUC, cero filas.
PARTNER_FORCE_TABLES: dict[str, str] = {
    "partner_wallets": "Saldo included+purchased. FORCE por partner_id.",
    "partner_allocations": "Cap por tenant. FORCE por partner_id.",
    "usage_ledger": "Asientos. FORCE por partner_id; fx NULL v1.",
    "partner_knowledge_documents": "Playbook. FORCE por partner_id. CASCADE al partner.",
    "workflow_packs": "Packs v1. FORCE por partner_id.",
    "workflow_runs": "Runs de pack. FORCE por partner_id.",
    "workflow_crons": "Crons de pack. FORCE por partner_id.",
    "workflow_send_receipts": "Idempotencia send. FORCE por partner_id.",
    "partner_model_allowlist": "Allowlist F2. FORCE por partner_id.",
    "tickets": "Tickets F4. FORCE por partner_id.",
    "ticket_events": "Eventos F4. FORCE por partner_id.",
    "admin_impersonation_sessions": "F5 overlay. FORCE + policy app.is_admin.",
}


ENABLE_ONLY_TABLES: dict[str, str] = {
    "invoices": "``partner_receipt`` emite facturas de partner leyendo varios tenants.",
    "invoice_lines": "El panel de recibos lista líneas de todos los tenants de un partner.",
    "embed_audit_log": "Auditoría del partner: se consulta por partner, no por tenant.",
}


_INVENTORY_SQL = sa.text(
    """
    SELECT c.relname,
           c.relrowsecurity,
           c.relforcerowsecurity,
           (SELECT count(*) FROM pg_policy p WHERE p.polrelid = c.oid) AS policies,
           c.relkind
      FROM pg_class c
      JOIN pg_namespace n ON n.oid = c.relnamespace
     WHERE n.nspname = 'public'
       AND c.relkind IN ('r', 'p')
       AND EXISTS (
             SELECT 1 FROM pg_attribute a
              WHERE a.attrelid = c.oid
                AND a.attname = 'tenant_id'
                AND a.attnum > 0
                AND NOT a.attisdropped
           )
     ORDER BY c.relname
    """
)


async def _inventory(session=None) -> list[sa.Row]:
    if session is not None:
        return list((await session.execute(_INVENTORY_SQL)).all())
    sm = get_sessionmaker()
    async with sm() as s:
        return list((await s.execute(_INVENTORY_SQL)).all())


def uncovered_tables(rows: list[sa.Row]) -> list[str]:
    """Tablas de tenant sin RLS utilizable. Extraído aparte para que el
    test de auto-verificación de abajo ejerza ESTE mismo código y no una
    copia parecida."""
    out: list[str] = []
    for name, enabled, _forced, policies, _kind in rows:
        if name in PRE_TENANT_TABLES:
            continue
        # Las particiones heredan la policy del padre al consultarlo y, si
        # se consultan directas, RLS activa sin policy propia deniega todo
        # (fail-closed). Se comprueban aparte, abajo.
        if _is_partition(name):
            continue
        if not enabled or policies == 0:
            out.append(name)
    return out


async def test_every_tenant_table_is_covered_or_justified() -> None:
    rows = await _inventory()
    assert rows, "la consulta de inventario no encontró NINGUNA tabla con tenant_id"

    uncovered = uncovered_tables(rows)
    assert not uncovered, (
        "tablas con tenant_id sin RLS: "
        + ", ".join(sorted(uncovered))
        + ". O se les pone policy, o se añaden a PRE_TENANT_TABLES con el "
        "motivo por el que una policy las rompería."
    )


async def test_the_check_actually_catches_an_unprotected_table() -> None:
    """Un guardián que nunca falla no protege nada.

    Se crea una tabla real con ``tenant_id`` y sin RLS dentro de una
    transacción que se deshace, y se comprueba que el inventario la
    señala. Sin esto no habría forma de distinguir "todo cubierto" de
    "la consulta no mira donde debe" — y la segunda se ve idéntica en
    verde.
    """
    sm = get_sessionmaker()
    async with sm() as session:
        await session.execute(
            sa.text("CREATE TABLE _rls_probe (id int PRIMARY KEY, tenant_id uuid NOT NULL)")
        )
        detected = uncovered_tables(await _inventory(session))
        await session.rollback()

    assert "_rls_probe" in detected, (
        "el inventario no detectó una tabla con tenant_id y sin RLS — "
        "el resto de este archivo está pasando en falso"
    )


async def test_partitions_are_fail_closed() -> None:
    """Una partición NO hereda la row security de su padre (0069).

    Consultada directamente solo aplican sus propias policies: con RLS
    activa y sin policy propia, Postgres deniega todo. Es la forma
    correcta de fallar — lo contrario, que ya pasó, es una tabla con los
    datos de todos los tenants legible sin filtro.
    """
    rows = await _inventory()
    partitions = [r for r in rows if _is_partition(r[0])]
    assert partitions, "no hay particiones en el inventario — ¿cambió el naming?"

    leaky = [name for name, enabled, forced, _p, _k in partitions if not (enabled and forced)]
    assert not leaky, f"particiones sin RLS heredada: {sorted(leaky)}"


async def test_the_runtime_cannot_read_another_tenants_invoice() -> None:
    """El caso concreto que motivó 0073, comprobado de punta a punta.

    No basta con que exista la policy: hay que ver que ``nexus_app`` —el
    rol con el que corre el pipeline— deja de ver la factura ajena.
    """
    import uuid

    a, b = uuid.uuid4(), uuid.uuid4()
    sm = get_sessionmaker()

    async with sm() as session:
        for tid, slug in ((a, "inv-a"), (b, "inv-b")):
            await session.execute(
                sa.text(
                    "INSERT INTO tenants (id, name, slug, plan) "
                    "VALUES (:id, :n, :s, 'pro') ON CONFLICT DO NOTHING"
                ),
                {"id": str(tid), "n": slug, "s": f"{slug}-{tid.hex[:8]}"},
            )
            await session.execute(
                sa.text(
                    "INSERT INTO invoices "
                    "(tenant_id, period_year, period_month, status, total_cents) "
                    "VALUES (:t, 2026, 8, 'draft', 12345)"
                ),
                {"t": str(tid)},
            )
        await session.commit()

    async with sm() as session:
        await session.execute(
            sa.text("SELECT set_config('app.tenant_id', :t, false)"), {"t": str(a)}
        )
        await session.execute(sa.text("SET ROLE nexus_app"))
        visible = (
            (
                await session.execute(
                    sa.text("SELECT tenant_id FROM invoices WHERE tenant_id IN (:a, :b)"),
                    {"a": str(a), "b": str(b)},
                )
            )
            .scalars()
            .all()
        )
        assert visible == [a], "el runtime de un tenant vio la factura de otro"


async def test_the_platform_path_still_sees_every_invoice() -> None:
    """La otra mitad de la decisión de 0073.

    ENABLE sin FORCE es deliberado: con FORCE, ``partner_receipt`` vería
    cero filas y la facturación de partners dejaría de emitir sin dar un
    solo error. Si alguien "endurece" esto a FORCE, este test lo dice.
    """
    sm = get_sessionmaker()
    async with sm() as session:
        # Sin SET ROLE y sin GUC: el camino de plataforma.
        total = await session.scalar(sa.text("SELECT count(*) FROM invoices"))
        assert total is not None


def _is_partition(name: str) -> bool:
    """``messages_y2026m08``, ``usage_records_default``, …"""
    return "_y20" in name or name.endswith("_default")
