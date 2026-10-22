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

Y el arreglo de entonces dejó otro fallo igual de mudo: la contraseña de Aurora
la genera RDS y puede llevar ``[`` o ``]``. asyncpg lee un DSN con ``urllib``,
que la toma por una IPv6 rota (``Invalid IPv6 URL``), así que el LISTEN no
conectó nunca en producción — 43 000 reintentos al día desde el corte y la
salida otra vez a merced del barrido. Por eso el URL se descompone con el mismo
parser de SQLAlchemy que ya usa el resto de la aplicación.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

import asyncpg
import pytest

from nexus_worker.streams import outbound


@dataclass
class _Settings:
    database_url: str
    database_url_direct: str = ""


def _kwargs(monkeypatch, **kwargs) -> dict[str, Any]:
    from nexus_api import config

    monkeypatch.setattr(config, "get_settings", lambda: _Settings(**kwargs))
    return outbound._asyncpg_connect_kwargs()


PGB = "postgresql+asyncpg://nexus:pw@nexus-prod-pgbouncer.nexus.local:5432/nexus"
DIRECT = "postgresql+asyncpg://nexus:pw@nexus-prod-aurora.cluster-x.rds.amazonaws.com:5432/nexus"


def test_prefiere_la_conexion_directa_sobre_el_pooler(monkeypatch) -> None:
    """Con las dos definidas gana la directa: es la única que sostiene LISTEN."""
    kwargs = _kwargs(monkeypatch, database_url=PGB, database_url_direct=DIRECT)
    assert kwargs["host"] == "nexus-prod-aurora.cluster-x.rds.amazonaws.com"


def test_cae_a_database_url_cuando_no_hay_directa(monkeypatch) -> None:
    """En dev no hay pooler delante, así que la de siempre vale."""
    kwargs = _kwargs(monkeypatch, database_url="postgresql+asyncpg://nexus:pw@localhost:5433/nexus")
    assert (kwargs["host"], kwargs["port"]) == ("localhost", 5433)


@pytest.mark.parametrize("password", ["ab[cd", "ab]cd", "a[b]c", "x#y", "x?y"])
def test_la_password_llega_entera_aunque_lleve_caracteres_de_url(monkeypatch, password) -> None:
    """RDS no genera ``/``, ``@``, ``"`` ni espacios; el resto sí puede salir."""
    url = f"postgresql+asyncpg://nexus:{password}@aurora.internal:5432/nexus"
    kwargs = _kwargs(monkeypatch, database_url=PGB, database_url_direct=url)
    assert kwargs["password"] == password
    assert (kwargs["host"], kwargs["port"], kwargs["database"]) == (
        "aurora.internal",
        5432,
        "nexus",
    )


async def test_asyncpg_pasa_del_parseo_con_una_password_con_corchete(monkeypatch) -> None:
    """El fallo de producción, contra asyncpg de verdad: antes moría al leer el
    URL (``ValueError: Invalid IPv6 URL``); ahora llega a abrir el socket. El
    puerto 1 de loopback rechaza la conexión sin tocar la red."""
    url = "postgresql+asyncpg://nexus:ab[cd@127.0.0.1:1/nexus"
    kwargs = _kwargs(monkeypatch, database_url=PGB, database_url_direct=url)
    with pytest.raises(OSError):
        await asyncpg.connect(**kwargs, timeout=5)
