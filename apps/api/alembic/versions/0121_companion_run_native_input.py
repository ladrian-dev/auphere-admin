"""La entrada del turno de Companion, en nativo (spec 007, R1.2 · research D4).

**El defecto.** Desde la 0093, ``companion.runs.input_tokens`` guarda **la
cuota**, no el nativo — su propio docstring lo dice: *«``input_tokens`` del run
es la CUOTA (uncached + 0.1 x cache_read, C3)»*. Y la API la **des-pondera**
restando ``0,1 x cache_read`` para recuperar el uncached y poder valorar el turno
en dólares.

Esa inversión sólo funciona porque el factor es **una constante global única**.
Con un peso por carril y por modelo deja de ser invertible: para des-hacerla
haría falta saber de qué modelo se trata, y el punto donde se acumula —el bucle
del grafo— no lo tiene. Mantenerla obligaría a meter el catálogo de precios
dentro del agente, que es justo el acoplamiento que la spec 007 viene a quitar.

**La decisión: medir es nativo; ponderar ocurre una vez, en el borde.** El grafo
acumula la entrada no cacheada tal cual, y la ponderación la hace quien debita.

**Por qué una columna nueva y no reinterpretar la que hay.** Reinterpretarla
dejaría filas cuya lectura depende de su fecha —las de antes, cuota; las de
después, nativo— y un ``downgrade()`` incapaz de devolver los datos. Es el mismo
patrón con el que la 0115 conservó ``companion_monthly_token_cap`` y con el que
la 0120 conserva ``quota_weight``.

**Sin backfill, a propósito.** ``uncached_input_tokens`` queda NULL en las filas
históricas, y eso es la verdad: el nativo no se puede recuperar de la cuota sin
asumir que el factor fue 0,1 — que es exactamente la suposición de la que esta
spec sale. Un NULL declarado vale más que un número reconstruido, y
``WHERE uncached_input_tokens IS NULL`` encuentra después las filas viejas.

Revision ID: 0121_companion_run_native_input
Revises: 0120_quota_weights_per_lane
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0121_companion_run_native_input"
down_revision: str | Sequence[str] | None = "0120_quota_weights_per_lane"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("ALTER TABLE companion.runs ADD COLUMN IF NOT EXISTS uncached_input_tokens integer")
    op.execute(
        """
        ALTER TABLE companion.runs
          ADD CONSTRAINT ck_companion_runs_uncached_input_nonneg
          CHECK (uncached_input_tokens IS NULL OR uncached_input_tokens >= 0)
        """
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE companion.runs "
        "DROP CONSTRAINT IF EXISTS ck_companion_runs_uncached_input_nonneg"
    )
    op.execute("ALTER TABLE companion.runs DROP COLUMN IF EXISTS uncached_input_tokens")
    # ``input_tokens`` sigue donde estaba, con los valores que tenía: esta
    # migración nunca lo tocó, y por eso la bajada no puede perder nada.
