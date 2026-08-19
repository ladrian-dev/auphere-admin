"""El LISTEN del dispatcher de salida NO puede ir por PgBouncer.

``LISTEN`` es estado de sesión y el pooler corre en ``pool_mode =
transaction`` (WP-15): la conexión al servidor vuelve al pool al cerrar cada
transacción, el registro se pierde y las notificaciones no llegan. El fallo
es **silencioso** — ``add_listener`` completa, se registra
``outbound.listener.connected``, no hay reconexiones — y el dispatcher queda
viviendo del barrido de seguridad de 30 s.

Se detectó en producción el 2026-08-19, en el primer turno real tras el corte
a AWS: mensaje creado 09:50:16.174, recogido 09:50:22.032 (5,86 s), justo en
la cadencia del barrido. Nada en los logs lo delataba.

Estos tests fijan la elección del DSN. Sin ellos, volver a poner
``database_url`` ahí no rompe ninguna prueba y la latencia de salida pasa
otra vez a ser uniforme entre 0 y 30 s sin que nadie lo note.
"""

from __future__ import annotations

from dataclasses import dataclass

from nexus_worker.streams import outbound


@dataclass
class _Settings:
    database_url: str
    database_url_direct: str = ""


def _dsn(monkeypatch, **kwargs) -> str:
    from nexus_api import config

    monkeypatch.setattr(config, "get_settings", lambda: _Settings(**kwargs))
    return outbound._asyncpg_dsn()


PGB = "postgresql+asyncpg://nexus:pw@nexus-prod-pgbouncer.nexus.local:5432/nexus"
DIRECT = "postgresql+asyncpg://nexus:pw@nexus-prod-aurora.cluster-x.rds.amazonaws.com:5432/nexus"


def test_prefiere_la_conexion_directa_sobre_el_pooler(monkeypatch) -> None:
    """Con las dos definidas gana la directa: es la única que sostiene LISTEN."""
    dsn = _dsn(monkeypatch, database_url=PGB, database_url_direct=DIRECT)
    assert "aurora" in dsn
    assert "pgbouncer" not in dsn


def test_cae_a_database_url_cuando_no_hay_directa(monkeypatch) -> None:
    """En dev no hay pooler delante, así que la de siempre vale."""
    dsn = _dsn(monkeypatch, database_url="postgresql+asyncpg://nexus:pw@localhost:5433/nexus")
    assert "localhost:5433" in dsn


def test_traduce_el_dialecto_para_asyncpg(monkeypatch) -> None:
    """asyncpg.connect no entiende el prefijo de SQLAlchemy."""
    dsn = _dsn(monkeypatch, database_url=PGB, database_url_direct=DIRECT)
    assert dsn.startswith("postgresql://")
    assert "+asyncpg" not in dsn
