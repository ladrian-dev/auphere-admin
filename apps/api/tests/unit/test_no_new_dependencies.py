"""Spec 004 · puerta de licencias (§VIII).

El plan declara **cero dependencias nuevas**. Este test lo convierte en algo
que se comprueba al fusionar en vez de en una frase de un documento.

Vigila dos cosas distintas:

1. Que no aparezca una dependencia que el plan no declaró.
2. Que **``stripe`` no se cuele aquí**. Es de la Spec B, entra con su párrafo
   de licencia citado (MIT, verificado el 2026-09-11) y con el webhook y la
   idempotencia que ADR-022 §13-§15 ya diseñaron. Colarla antes se llevaría por
   delante el corte entre las dos specs, que es lo que hace que ésta se pueda
   desplegar sola.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

pytestmark = [pytest.mark.asyncio]

_API = Path(__file__).resolve().parents[2] / "pyproject.toml"

#: Instantánea de las dependencias de tiempo de ejecución al abrir la spec 004.
#: Añadir una entrada aquí es una decisión: exige leer la licencia entera y
#: citar el párrafo que permite el uso multi-tenant como servicio (§VIII).
BASELINE: frozenset[str] = frozenset(
    {
        "alembic",
        "asyncpg",
        "boto3",
        "composio",
        "cryptography",
        "email-validator",
        "fastapi",
        "langgraph",
        "litellm",
        "nexus-channels",
        "nexus-mcp",
        "nexus-ucm-schema",
        "nexus-worker",
        "opentelemetry-api",
        "opentelemetry-exporter-otlp-proto-http",
        "opentelemetry-instrumentation-asyncpg",
        "opentelemetry-instrumentation-fastapi",
        "opentelemetry-instrumentation-redis",
        "opentelemetry-instrumentation-sqlalchemy",
        "opentelemetry-sdk",
        "pydantic",
        "pydantic-settings",
        "pyjwt",
        "pypdf",
        "python-multipart",
        "pyyaml",
        "redis",
        "sqlalchemy",
        "sse-starlette",
        "structlog",
        "uvicorn",
    }
)


def _names() -> set[str]:
    data = tomllib.loads(_API.read_text())
    out: set[str] = set()
    for raw in data["project"]["dependencies"]:
        name = raw.split(";")[0].split("[")[0]
        for sep in (">=", "==", "<=", "~=", ">", "<"):
            name = name.split(sep)[0]
        out.add(name.strip().lower())
    return out


async def test_no_dependency_arrived_without_a_licence_read() -> None:
    new = sorted(_names() - BASELINE)
    assert not new, (
        f"dependencias nuevas sin declarar: {new}. El principio VIII pide leer la "
        "licencia ENTERA y citar en el plan el párrafo que permite el uso "
        "multi-tenant como servicio. AGPL es un no. Si la dependencia es "
        "legítima, añádela a BASELINE en el mismo commit que su párrafo."
    )


async def test_stripe_does_not_sneak_into_this_spec() -> None:
    """La Spec A no cobra. Que ``stripe`` aparezca aquí significaría que el
    corte entre las dos specs se rompió, y con él la propiedad de que ésta se
    puede desplegar sola."""
    assert "stripe" not in _names(), (
        "``stripe`` es de la Spec B: entra con su párrafo de licencia citado y "
        "con el webhook idempotente de ADR-022 §13-§15, no de rebote aquí"
    )


async def test_the_baseline_still_describes_reality() -> None:
    """Una instantánea que se queda vieja deja de vigilar nada.

    Si se retira una dependencia y nadie toca la lista, este test sigue en
    verde para siempre y ya no comprueba lo que dice comprobar.
    """
    gone = sorted(BASELINE - _names())
    assert not gone, (
        f"estas dependencias ya no existen y siguen en BASELINE: {gone}. "
        "Quítalas, o la instantánea deja de describir el proyecto."
    )
