"""El límite de clientes deja de ser producto y se queda como guarda.

Spec 019, decisión del owner del 2026-09-28: **crear un cliente no tiene
limitantes para los partners**. Nadie paga por añadir uno, así que un tope
de cinco no defendía ningún precio: solo frenaba al partner que estaba
creciendo, que es justo a quien no hay que frenar.

Lo que **no** se retira es la comprobación. El tope tiene una segunda vida
que nadie escribió: ``provision_partner_client`` lo mira antes de crear
nada y con la fila del partner bloqueada (``FOR UPDATE``), así que hoy
acota el daño si una clave se filtra o un bucle se descontrola. Sin
ninguna comprobación nada impide crear diez mil tenants, y cada tenant
arrastra coste real.

Por eso el número sube a un techo que ningún partner real alcanza en vez
de desaparecer: deja de verse en la consola —contador, aviso y pantalla de
cupo lleno se van— y sigue estando donde protege.

Baja: se puede devolver el ``DEFAULT`` a 5, pero **los valores que cada
partner tenía antes no vuelven**: los escribió la siembra de la 0081 a
partir de su número real de clientes, y ese número ya no es el de
entonces. La baja deja a todos en el techo y lo dice en ``quota_notes``.

Revision ID: 0130_client_limit_is_a_guard
Revises: 0129_console_audit_vocab_017
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0130_client_limit_is_a_guard"
down_revision: str | Sequence[str] | None = "0129_console_audit_vocab_017"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# Un techo, no una cuota. Diez mil clientes por partner es cuatro órdenes de
# magnitud por encima del mayor de hoy: quien lo alcance está en un bucle,
# no creciendo.
GUARD_CEILING = 10_000
OLD_DEFAULT = 5


def upgrade() -> None:
    op.execute(f"ALTER TABLE partners ALTER COLUMN max_clients SET DEFAULT {GUARD_CEILING}")
    op.execute(
        f"""
        UPDATE partners
           SET max_clients = {GUARD_CEILING},
               quota_notes = COALESCE(quota_notes || ' · ', '')
                             || 'spec 019: el límite de clientes se retira; '
                             || 'queda como guarda en {GUARD_CEILING}'
         WHERE max_clients < {GUARD_CEILING}
        """
    )


def downgrade() -> None:
    op.execute(f"ALTER TABLE partners ALTER COLUMN max_clients SET DEFAULT {OLD_DEFAULT}")
