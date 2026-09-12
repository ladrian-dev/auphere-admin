"""Specs 004 y 005 · puerta de licencias (§VIII).

Convierte «se leyó la licencia» en algo que se comprueba al fusionar, en vez de
en una frase de un documento.

Vigila tres cosas:

1. Que no aparezca una dependencia que ningún plan declaró.
2. Que la instantánea no se quede vieja y deje de vigilar nada.
3. Que ``stripe`` esté acompañada de su párrafo de licencia. La Spec A declaró
   cero dependencias nuevas y este fichero llegó a prohibir ``stripe``
   explícitamente, para que no se colara antes de tiempo y se llevara por
   delante el corte entre las dos specs. **La Spec 005 es la que la trae**, así
   que esa prohibición se convierte en su contraria: ahora exige que, si está,
   traiga la licencia citada donde se pueda leer.
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
        # Spec 005 (2026-09-12). Licencia MIT, leída entera. El párrafo que
        # permite el uso multi-tenant como servicio, citado en
        # specs/005-membresias-y-cobro/research.md D1:
        #
        #   "Permission is hereby granted, free of charge, to any person
        #    obtaining a copy of this software and associated documentation
        #    files (the "Software"), to deal in the Software without
        #    restriction, including without limitation the rights to use,
        #    copy, modify, merge, publish, distribute, sublicense, and/or
        #    sell copies of the Software [...]"
        #
        # MIT no alcanza el uso en red, no impone reciprocidad y no restringe
        # el uso multi-tenant. Es un sí (§VIII).
        "stripe",
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


async def test_stripe_carries_its_licence_paragraph() -> None:
    """``stripe`` solo vale si alguien leyó su licencia y lo dejó escrito.

    Este test era lo contrario hasta la spec 005: prohibía la dependencia para
    que no se colara en la Spec A. Ahora que entra, lo que hay que vigilar es
    que no entre **desnuda** — que el párrafo siga aquí el día que alguien
    audite por qué este proyecto propietario puede redistribuir ese paquete.
    """
    assert "stripe" in _names(), (
        "la spec 005 la declara; si se retiró, quítala también del BASELINE"
    )
    source = Path(__file__).read_text()
    assert "MIT" in source and "Permission is hereby granted" in source, (
        "``stripe`` está en pyproject.toml pero su párrafo de licencia no está "
        "citado aquí. El principio VIII pide leer la licencia ENTERA y dejar "
        "escrito el párrafo que permite el uso multi-tenant como servicio"
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
