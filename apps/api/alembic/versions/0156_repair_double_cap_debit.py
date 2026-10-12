"""Devuelve a cada cliente lo que el doble cobro le quitó de su tope esta semana
— bug ``doble-cobro-del-tope``.

Del 2026-09-02 (2026-09-13 en producción) al arreglo, cada turno de canal bajó
``partner_allocations.remaining`` dos veces: una dentro de ``debit_wallet`` y
otra en ``debit_allocation``, que además lo bajaba sin cobro. Con el tope a
cero, ``allow_channel_turn`` deja al cliente mudo: el 2026-10-10 había dos
clientes de producción mudos con tope de sobra.

El arreglo de código deja de descontar dos veces. Esto repara lo que ya está
descontado de más, **solo en la semana en curso**: el tope se repone al
renovarse el saldo incluido del partner (semanal, ``renew_included_if_expired``
→ ``replenish_allocations``), así que lo de semanas anteriores ya se repuso.

Para cada tope que tenga asientos ``…:allocation`` en la semana::

    remaining = LEAST(cap, GREATEST(remaining, cap - lo cobrado en la semana))

- ``cap - lo cobrado`` es la verdad: lo que el cliente ha gastado de verdad
  desde la reposición (los asientos de canal que no son ``:allocation``).
- ``GREATEST(remaining, …)``: nunca baja un restante. Si la semana se hubiera
  estimado mal, el error es dar margen, nunca dejar mudo a nadie.
- ``LEAST(cap, …)``: nunca por encima del tope.
- La semana empieza en ``included_expires_at - 7 días``; un partner sin
  monedero o sin caducidad no se toca.

Idempotente: tras el arreglo no se escriben asientos ``:allocation``, y una
segunda pasada calcula el mismo valor o uno menor, que ``GREATEST`` descarta.

``downgrade`` no hace nada: volver a dejar mudo a un cliente no deshace nada
útil.

Revision ID: 0156_repair_double_cap_debit
Revises: 0155_agents_tenant_fk
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0156_repair_double_cap_debit"
down_revision: str | Sequence[str] | None = "0155_agents_tenant_fk"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# ``\:`` keeps SQLAlchemy from reading ``:allocation`` as a bind parameter.
REPAIR = sa.text(
    r"""
    UPDATE partner_allocations AS a
       SET remaining = LEAST(a.cap, GREATEST(a.remaining, a.cap - week.charged)),
           updated_at = now()
      FROM (
            SELECT a2.id,
                   COALESCE(SUM(l.qty) FILTER (
                       WHERE l.idempotency_key LIKE 'channel\:%'
                         AND l.idempotency_key NOT LIKE '%\:allocation'), 0) AS charged,
                   COUNT(*) FILTER (WHERE l.idempotency_key LIKE '%\:allocation') AS extra_rows
              FROM partner_allocations AS a2
              JOIN partner_wallets AS w ON w.partner_id = a2.partner_id
              JOIN usage_ledger AS l
                ON l.partner_id = a2.partner_id
               AND l.tenant_id = a2.tenant_id
               AND l.created_at >= w.included_expires_at - interval '7 days'
             WHERE w.included_expires_at IS NOT NULL
             GROUP BY a2.id
           ) AS week
     WHERE week.id = a.id
       AND week.extra_rows > 0
    """
)


def upgrade() -> None:
    op.get_bind().execute(REPAIR)


def downgrade() -> None:
    pass
