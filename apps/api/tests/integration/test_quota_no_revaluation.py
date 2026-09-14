"""Spec 007 · R5 — nada se revalora.

La unidad de cuota no cambia de definición, cambia su **tasa de conversión**
desde los tokens nativos. Un millón de unidades sigue siendo un millón de
unidades; lo que cambia es cuánto trabajo compra. Por eso no hay migración de
datos, y por eso el despliegue es reversible por revert.

Esto corre sobre una base con tres clientes reales con tráfico. La comprobación
es doble a propósito: **estructural** (las migraciones no nombran ninguna tabla
de saldo) y **de estado** (los saldos siguen donde estaban después de aplicarlas).
La primera sola pasaría si alguien revalorase desde código; la segunda sola
pasaría por vacío en una base sin saldos.
"""

from __future__ import annotations

import pathlib

import pytest

pytestmark = [pytest.mark.integration]

_MIGRATIONS = pathlib.Path(__file__).resolve().parents[2] / "alembic" / "versions"
_THIS_SPEC = ("0120_quota_weights_per_lane.py", "0121_companion_run_native_input.py")

#: Tocar cualquiera de éstas sería mover dinero que ya está contado.
_LEDGER_TABLES = (
    "partner_wallets",
    "partner_allocations",
    "usage_ledger",
    "usage_records",
    "billing_events",
)


def test_the_migrations_of_this_spec_do_not_name_any_ledger_table() -> None:
    """R5.2 — sin reprecio y sin backfill.

    La 0114 y la 0076 llevaban un ``UPDATE usage_records ... SET cost_usd``
    heredado, y copiarlo por inercia aquí habría reprecificado el histórico sin
    que nadie lo pidiera. Este caso es lo que lo impide.
    """
    offenders: list[str] = []
    for name in _THIS_SPEC:
        source = (_MIGRATIONS / name).read_text(encoding="utf-8")
        body = source.split('"""', 2)[-1]  # fuera el docstring: ahí sí se nombran
        for table in _LEDGER_TABLES:
            if table in body:
                offenders.append(f"{name} nombra «{table}» fuera del docstring")
    assert not offenders, "las migraciones de esta spec tocan el libro:\n  " + "\n  ".join(
        offenders
    )


def test_the_migrations_of_this_spec_do_not_backfill_the_deprecated_columns() -> None:
    """R5.2 — ``companion.runs.input_tokens`` no se reconstruye.

    El nativo no se puede recuperar de la cuota sin asumir que el factor fue
    0,1, que es exactamente la suposición de la que esta spec sale. Un NULL
    declarado vale más que un número reconstruido.
    """
    source = (_MIGRATIONS / "0121_companion_run_native_input.py").read_text(encoding="utf-8")
    body = source.split('"""', 2)[-1]
    assert "UPDATE" not in body.upper(), "la 0121 rellena datos: no debe"


# **No hay un tercer caso que compruebe los saldos en la base, y es deliberado.**
# Se escribió, y hacía ``skip`` siempre: la base de pruebas se reconstruye desde
# cero en cada sesión y no tiene ningún libro que comparar. Un ``skip`` puntúa
# como aprobado y por tanto **no cubre nada** (§VII), así que se retira en vez de
# dejarlo dando un verde que nadie ha ganado. Lo que sí vigila que ningún saldo
# se mueva son los dos casos de arriba —ninguna migración de esta spec nombra
# una tabla del libro— y ésos no pueden pasar por vacío.
