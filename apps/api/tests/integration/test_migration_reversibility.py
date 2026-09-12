"""Spec 005 · las dos migraciones se pueden deshacer (T018).

La regla 3 de `[[nexus/PLAN-CONSOLE-V1]]` pide ``downgrade()`` real. Un
``downgrade`` que nadie ejecuta nunca es una función que se escribe por
costumbre y falla el día que hace falta — que es siempre el peor día.

Se comprueba lo que de verdad importa de una reversión: **que se pueda volver a
subir después**. Un ``downgrade`` que deja un resto —un índice, una política de
RLS, una columna— no da error al bajar; lo da al subir otra vez, en medio del
despliegue siguiente.

Este fichero corre en su propio proceso de Alembic y NO usa la sesión de tests,
porque toca el esquema que esa sesión da por hecho.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

pytestmark = [pytest.mark.integration]

_API = Path(__file__).resolve().parents[2]
_HEAD = "0117_billing_events"
_BEFORE = "0115_weekly_pool_and_weight"


def _alembic(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["uv", "run", "alembic", *args],
        cwd=_API,
        capture_output=True,
        text=True,
        check=False,
    )


def _current() -> str:
    out = _alembic("current").stdout
    return out.strip().splitlines()[-1] if out.strip() else ""


@pytest.fixture
def restored() -> object:
    """Deja la base en head pase lo que pase — otros tests dependen de ella."""
    yield
    _alembic("upgrade", "head")


def test_the_two_migrations_go_down_and_come_back_up(restored: object) -> None:
    assert _HEAD in _current(), "la base no está en head antes de empezar"

    down = _alembic("downgrade", _BEFORE)
    assert down.returncode == 0, f"el downgrade falló:\n{down.stderr}"
    assert _HEAD not in _current()

    # Lo que de verdad se prueba: que no quedó ningún resto que impida subir.
    up = _alembic("upgrade", "head")
    assert up.returncode == 0, f"el downgrade dejó restos y la subida vuelve a fallar:\n{up.stderr}"
    assert _HEAD in _current()


def test_the_revision_ids_fit_in_the_version_column() -> None:
    """``alembic_version.version_num`` es ``varchar(32)``.

    Una revisión más larga hace todo su trabajo y **luego** revienta al
    registrarse, dejando el esquema migrado y la tabla de versión sin
    actualizar. Pasó en la spec 004 con la 0114.
    """
    for revision in (_HEAD, "0116_membership_tiers"):
        assert len(revision) <= 32, f"«{revision}» mide {len(revision)}, el límite es 32"
