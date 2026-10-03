"""El sembrado del release habla con la base DIRECTA, no con el pooler.

Por qué existe este archivo, con fecha. El 2026-10-03 **todos** los despliegues
a staging abortaron en el paso bloqueante «run migration task». El error que
emitía la tubería —«La migración falló»— era mentira: en el log de
``/nexus/staging/migrate`` ``alembic upgrade head`` había terminado bien
(0138 → 0139) y lo que moría era el paso siguiente, el sembrado del catálogo de
conectores, con ``socket.gaierror: Name or service not known``.

La causa es que las dos mitades de la misma tarea usaban URLs distintas:

- Alembic lee ``database_url_direct or database_url`` (``alembic/env.py``).
- El sembrador llamaba a ``get_engine()``, que lee ``database_url``.

En staging eso es ``pgbouncer.nexus-staging.internal``, un nombre de Service
Connect que **solo** resuelven las tareas inscritas en ese namespace. La tarea
de migración es un ``run-task`` suelto y no lo está, así que el nombre no
resuelve. Alembic pasaba porque iba al endpoint de Aurora.

Dicho de otro modo: la tarea está diseñada para hablar directo —Alembic ya lo
hace— y el sembrador era el único que se desviaba por el pooler. Además no
tiene por qué: es un trabajo de una sola pasada con ``ON CONFLICT``, no
tráfico de aplicación.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from nexus_api.db.base import get_direct_engine, reset_engine_cache

DIRECT = "postgresql+asyncpg://u:p@aurora.internal:5432/nexus"
POOLER = "postgresql+asyncpg://u:p@pgbouncer.staging.internal:5432/nexus"

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "seed_connectors.py"


@pytest.fixture(autouse=True)
def _clean_engines():
    reset_engine_cache()
    yield
    reset_engine_cache()


def test_direct_engine_prefers_the_direct_url(monkeypatch):
    """Con el pooler delante, la URL directa es la que vale."""
    monkeypatch.setenv("NEXUS_DATABASE_URL", POOLER)
    monkeypatch.setenv("NEXUS_DATABASE_URL_DIRECT", DIRECT)
    from nexus_api.config import get_settings

    get_settings.cache_clear()
    try:
        assert get_direct_engine().url.host == "aurora.internal"
    finally:
        get_settings.cache_clear()


def test_direct_engine_falls_back_when_there_is_no_pooler(monkeypatch):
    """En dev y en tests no hay pooler: la de siempre sirve."""
    monkeypatch.setenv("NEXUS_DATABASE_URL", DIRECT)
    monkeypatch.setenv("NEXUS_DATABASE_URL_DIRECT", "")
    from nexus_api.config import get_settings

    get_settings.cache_clear()
    try:
        assert get_direct_engine().url.host == "aurora.internal"
    finally:
        get_settings.cache_clear()


def test_the_seeder_asks_for_the_direct_engine():
    """El cableado, no solo la pieza.

    Dos afirmaciones, y las dos hacen falta. La primera carga el script como
    hace ``test_seed_synthetic`` —no es un módulo del paquete, así que no se
    importa— y con eso prueba que el nombre que pide existe de verdad: un
    ``get_direct_engine`` mal escrito reventaría aquí y no en el despliegue.
    La segunda es una guarda sobre el fuente, porque las pruebas de arriba
    pueden estar verdes con el sembrador llamando igualmente al pooler, que es
    exactamente el fallo que se desplegó.
    """
    spec = importlib.util.spec_from_file_location("seed_connectors_under_test", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    assert module.get_direct_engine is get_direct_engine

    source = SCRIPT.read_text()
    assert "get_engine()" not in source, "el sembrador del release no debe ir por el pooler"
