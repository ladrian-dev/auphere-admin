"""Lo común de las pruebas de la lectura (spec 047, T044 y T045).

- un DNS de mentira: ``assert_public_url`` resuelve con la tabla de aquí y no
  con la red, así que las guardas de direcciones públicas se prueban **de
  verdad** sin salir a internet;
- un extractor de mentira en lugar del modelo: devuelve lo que se le diga,
  guarda los mensajes que recibió y anota el consumo como lo anota el
  proveedor (``record_llm_usage`` con ``task="read_source"``);
- el trabajo ``client_read`` corrido por el consumidor de verdad
  (``drain_once`` con ``DbJobStore``) contra la fila de ``jobs``.

Ninguna prueba llama a internet ni a un modelo real: las páginas son de
``respx`` y el modelo es :class:`FakeExtractor`.
"""

from __future__ import annotations

import asyncio
import json
import socket
import uuid
from dataclasses import dataclass, field
from typing import Any

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.models import Partner, PartnerTenant

#: Lo que «resuelve» cada nombre. Lo que no está, no existe.
DNS: dict[str, str] = {
    "cultorbarber.com": "93.184.216.34",
    "www.cultorbarber.com": "93.184.216.34",
    "cultorbarber.es": "93.184.216.37",
    "barberia-london.co.uk": "93.184.216.35",
    "otrodominio.com": "93.184.216.36",
    "www.instagram.com": "157.240.0.1",
    "www.tiktok.com": "23.0.0.1",
    "intranet.cultorbarber.com": "10.0.0.7",
    "interna.example": "192.168.1.20",
}


#: La base y Redis de las pruebas también resuelven por el bucle: esos pasan.
_INFRA = frozenset({"localhost"})


def _fake_getaddrinfo(real: Any) -> Any:
    async def resolve(host: str, port: Any, *args: Any, **kwargs: Any) -> list[Any]:
        name = (host or "").strip("[]")
        if name.lower() in _INFRA:
            return list(await real(host, port, *args, **kwargs))
        try:
            socket.inet_pton(socket.AF_INET, name)
            ip = name
        except OSError:
            ip = DNS.get(name.lower(), "")
        if not ip:
            raise socket.gaierror(socket.EAI_NONAME, "Name or service not known")
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (ip, 0))]

    return resolve


@pytest.fixture
async def fake_dns(monkeypatch: pytest.MonkeyPatch) -> None:
    """``assert_public_url`` pregunta al bucle; el bucle contesta con :data:`DNS`.
    Asíncrona a propósito: el bucle que se parchea es el que corre la prueba."""
    loop = asyncio.get_running_loop()
    monkeypatch.setattr(loop, "getaddrinfo", _fake_getaddrinfo(loop.getaddrinfo))


@dataclass
class FakeExtractor:
    """El modelo de la tarea ``read_source``, de mentira."""

    reply: dict[str, Any] | str = field(default_factory=dict)
    calls: list[list[dict[str, str]]] = field(default_factory=list)
    model: str = "anthropic/claude-haiku-5-5"

    async def __call__(self, messages: list[dict[str, str]]) -> str:
        from nexus_worker.metering.collector import record_llm_usage

        self.calls.append(messages)
        # Lo que hace el proveedor en su único punto de paso (``_record_call``).
        record_llm_usage(
            model=self.model,
            provider="anthropic",
            usage={"prompt_tokens": 1200, "completion_tokens": 300},
            task="read_source",
        )
        return self.reply if isinstance(self.reply, str) else json.dumps(self.reply)

    @property
    def prompt(self) -> str:
        assert self.calls, "the extractor was never called"
        return "\n".join(m["content"] for m in self.calls[-1])


#: Lo que encuentra el extractor en la web de Barbería Cultor.
CULTOR_READ: dict[str, Any] = {
    "source_language": "es",
    "locations": [
        {"name": "Cultor Centro", "address": "Calle Mayor 1, Madrid", "phone": "+34 600 123 456"},
        {"name": "Cultor Norte", "address": "Calle Bravo Murillo 200, Madrid"},
    ],
    "hours": {
        "mon": [{"open": "10:00", "close": "14:00"}, {"open": "16:00", "close": "20:00"}],
        "sat": [{"open": "10:00", "close": "14:00"}],
        "sun": [],
    },
    "services": [
        {
            "name": "Corte de pelo",
            "duration_min": 30,
            "price_amount": 15,
            "currency": "EUR",
            "bookable": True,
        },
        {"name": "Arreglo de barba", "duration_min": 20, "price_amount": 9.5, "currency": "EUR"},
        {"name": "Cera para el pelo", "bookable": False, "price_amount": 12, "currency": "EUR"},
    ],
    "policies": {
        "cancellation": "Avisa con 24 h de antelación.",
        "payments": "Tarjeta y efectivo.",
    },
    "faqs": [{"q": "¿Hay que pedir cita?", "a": "Sí, por WhatsApp o en la web."}],
}


async def roomy(db_session: AsyncSession, world: dict[str, Any]) -> None:
    """``max_clients`` es una guarda contra bucles; aquí no se prueba."""
    for label in ("a", "b"):
        partner = await db_session.get(Partner, world[label]["partner_id"])
        assert partner is not None
        partner.max_clients = 50
    await db_session.commit()


async def create_client(client: Any, headers: dict[str, str], **body: Any) -> dict[str, Any]:
    resp = await client.post("/console/clients", json=body, headers=headers)
    assert resp.status_code == 201, resp.text
    out: dict[str, Any] = resp.json()
    return out


async def tenant_of(db_session: AsyncSession, partner_id: uuid.UUID, ref: str) -> uuid.UUID:
    async with db_session.begin():
        tenant_id = await db_session.scalar(
            sa.select(PartnerTenant.tenant_id).where(
                PartnerTenant.partner_id == partner_id, PartnerTenant.external_client_ref == ref
            )
        )
    assert tenant_id is not None
    return tenant_id


async def scoped(db_session: AsyncSession, tenant_id: uuid.UUID, stmt: Any) -> list[Any]:
    async with tenant_scoped_session(db_session, tenant_id):
        fresh = stmt.execution_options(populate_existing=True)
        return list((await db_session.execute(fresh)).scalars().all())


async def run_reader(fake_redis: Any, extract: FakeExtractor) -> int:
    """Corre los trabajos en cola con el manejador ``client_read`` de verdad,
    con el extractor de mentira en lugar del modelo."""
    from nexus_worker.jobs import DbJobStore, JobRegistry, drain_once
    from nexus_worker.jobs.handlers.client_read import make_client_read_handler

    registry = JobRegistry()
    registry.register(
        "client_read",
        make_client_read_handler(extractor_factory=lambda _tenant: extract),
        timeout_s=60,
    )
    return await drain_once(fake_redis, registry=registry, store=DbJobStore())


def page(body: str, *, title: str = "Barbería Cultor", head: str = "") -> str:
    return f"<html><head><title>{title}</title>{head}</head><body>{body}</body></html>"
