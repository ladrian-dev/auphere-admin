"""Dos estados que faltaban en ``companion.actions`` (CO-04).

La 0090 creó la tabla con el CHECK cerrado a seis valores::

    proposed · confirmed · cancelled · expired · applied · failed

El ciclo de vida real del §3.3 de ``docs/companion/CONTRACT-V1.md`` necesita
dos más, y los dos son estados de verdad, no matices:

- ``superseded`` — la decisión fue ``edit``. La acción **muere** y el modelo
  replanifica con la nota del humano. No es ``cancelled``: cancelar cierra el
  trabajo, editar lo continúa por otro camino, y la diferencia importa cuando
  alguien mira la traza para entender por qué se hicieron dos propuestas
  seguidas sobre el mismo cliente.
- ``applying`` — la petición de escritura está EN VUELO. Sin este estado, un
  proceso que muere entre el ``confirmed`` y el ``applied`` deja la fila
  diciendo "confirmada, sin aplicar", que es indistinguible de una acción que
  nadie llegó a ejecutar. Con él se sabe que algo salió y no se sabe qué pasó
  — que es la verdad, y es accionable.

Solo se amplía el CHECK. Ninguna columna cambia y ninguna fila se toca: en
producción la tabla está vacía, porque CO-04 es quien la escribe por primera
vez.

Revision ID: 0091_companion_action_states
Revises: 0090_companion
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0091_companion_action_states"
down_revision: str | Sequence[str] | None = "0090_companion"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "companion"
CONSTRAINT = "ck_companion_actions_status"

_OLD = "'proposed', 'confirmed', 'cancelled', 'expired', 'applied', 'failed'"
_NEW = _OLD + ", 'superseded', 'applying'"


def upgrade() -> None:
    op.execute(f"ALTER TABLE {SCHEMA}.actions DROP CONSTRAINT IF EXISTS {CONSTRAINT}")
    op.execute(
        f"ALTER TABLE {SCHEMA}.actions ADD CONSTRAINT {CONSTRAINT} CHECK (status IN ({_NEW}))"
    )


def downgrade() -> None:
    # Las filas en los dos estados nuevos no caben en el CHECK viejo. Se
    # reencaminan a los terminales más cercanos ANTES de estrecharlo, en vez
    # de dejar que el ALTER falle a mitad de una bajada de versión.
    op.execute(f"UPDATE {SCHEMA}.actions SET status = 'cancelled' WHERE status = 'superseded'")
    op.execute(f"UPDATE {SCHEMA}.actions SET status = 'failed' WHERE status = 'applying'")
    op.execute(f"ALTER TABLE {SCHEMA}.actions DROP CONSTRAINT IF EXISTS {CONSTRAINT}")
    op.execute(
        f"ALTER TABLE {SCHEMA}.actions ADD CONSTRAINT {CONSTRAINT} CHECK (status IN ({_OLD}))"
    )
