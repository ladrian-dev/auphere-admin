"""Apoyo de las pruebas de ``quedate.*`` (spec 061, enmienda del 2026-11-16): un Quédate
falso por transporte, un almacén de vínculos y unas fotos en memoria. Sin red y sin
base de datos.

- ``Recorder`` es un ``httpx.MockTransport`` que responde por ruta y guarda cada
  petición tal como sale del cliente: anfitrión (entorno), método, ruta, cabeceras,
  cuerpo JSON o los nombres de los campos multipart.
- ``OpenAPI`` es la copia congelada del contrato **general** de Quédate (2.1.0), del
  que el conector usa solo las rutas públicas.
- ``AGENT`` es el contrato de la API **del agente**, que no está en ``openapi.json``:
  sale de su página de documentación y de las peticiones que Quédate dev aceptó el
  2026-11-16 (research, tabla de resultados).
- ``FakeStore`` implementa ``AccountStore``; ``FakePhotos``, ``PhotoSource``.

``EXAMPLES`` son capturas de Quédate dev sin datos personales ni claves.
"""

from __future__ import annotations

import json
import re
import uuid
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
from nexus_api.core.tenant_context import customer_context, tenant_context

from nexus_mcp.servers.quedate import accounts, photos, tools
from nexus_mcp.servers.quedate.accounts import Connection, Link, QuedateNotConfigured
from nexus_mcp.servers.quedate.client import QuedateClient
from nexus_mcp.servers.quedate.photos import Photo

FIXTURES = Path(__file__).parent / "fixtures" / "quedate"
EXAMPLES: dict[str, Any] = json.loads((FIXTURES / "examples.json").read_text())
SPEC: dict[str, Any] = json.loads((FIXTURES / "openapi-2.1.0.json").read_text())
BASE_PATH = "/api/v1"
HOSTS = {"production": "api-v2.quedate.net", "development": "dev-api.quedate.net"}

#: El anfitrión y el anuncio de las capturas.
HOST_ID = EXAMPLES["host_create_201"]["data"]["id"]
LISTING_ID = EXAMPLES["listing_create_201"]["data"]["id"]
OTHER_HOST = "01a1e5e0-0000-7000-8000-00000000beef"
OTHER_LISTING = "01a1e5e0-0000-7000-8000-00000000cafe"


@dataclass
class Sent:
    host: str
    method: str
    path: str
    params: dict[str, str]
    headers: dict[str, str]
    body: Any
    #: Nombres de los campos multipart, en orden (``None`` si no es multipart).
    parts: list[str] | None = None


class Recorder:
    """Responde por ``(MÉTODO, ruta)`` y guarda lo enviado."""

    def __init__(self) -> None:
        self.routes: dict[tuple[str, str], list[tuple[int, Any]]] = {}
        self.failures: dict[tuple[str, str], Exception] = {}
        self.sent: list[Sent] = []
        #: El ``max_retries`` y el entorno que pidió cada herramienta.
        self.retries_asked: list[int | None] = []
        self.environments: list[str] = []

    def on(self, method: str, path: str, status: int = 200, body: Any = None) -> Recorder:
        """Responde siempre lo mismo."""
        self.routes[(method.upper(), path)] = [
            (status, {"success": True} if body is None else body)
        ]
        return self

    def then(self, method: str, path: str, status: int, body: Any) -> Recorder:
        """Encadena respuestas: la última se repite."""
        self.routes.setdefault((method.upper(), path), []).append((status, body))
        return self

    def fail(self, method: str, path: str, exc: Exception) -> Recorder:
        """La ruta falla en el transporte (tiempo agotado, DNS…), sin respuesta HTTP."""
        self.failures[(method.upper(), path)] = exc
        return self

    def to(self, method: str, path: str) -> list[Sent]:
        return [s for s in self.sent if s.method == method and s.path == path]

    def _handle(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        assert path.startswith(BASE_PATH), path
        rel = path[len(BASE_PATH) :]
        ctype = request.headers.get("content-type", "")
        raw = request.content
        body: Any = None
        parts: list[str] | None = None
        if ctype.startswith("multipart/"):
            parts = [m.decode() for m in re.findall(rb'form-data; name="([^"]+)"', raw)]
        elif raw:
            body = json.loads(raw.decode("utf-8"))
        self.sent.append(
            Sent(
                host=request.url.host,
                method=request.method,
                path=rel,
                params=dict(request.url.params),
                headers={k.lower(): v for k, v in request.headers.items()},
                body=body,
                parts=parts,
            )
        )
        failure = self.failures.get((request.method, rel))
        if failure is not None:
            raise failure
        queue = self.routes.get((request.method, rel))
        if not queue:
            return httpx.Response(404, json={"success": False, "message": "no route"})
        status, payload = queue.pop(0) if len(queue) > 1 else queue[0]
        return httpx.Response(status, json=payload)

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self._handle)

    def factory(self) -> Any:
        def make(
            *,
            environment: Any = "production",
            token: str | None = None,
            max_retries: int | None = None,
        ) -> QuedateClient:
            # Se apunta lo que pide la herramienta; el cliente se construye sin
            # reintentos para no esperar (el reintento lo prueba el cliente base).
            self.retries_asked.append(max_retries)
            self.environments.append(environment)
            return QuedateClient(
                environment=environment, token=token, max_retries=0, transport=self.transport()
            )

        return make


class OpenAPI:
    """La copia congelada del contrato general de Quédate."""

    def __init__(self, spec: dict[str, Any] = SPEC) -> None:
        self.spec = spec
        self._paths = [
            (re.compile("^" + re.sub(r"\{[^}]+\}", "[^/]+", p) + "$"), p) for p in spec["paths"]
        ]

    def operation(self, method: str, path: str) -> dict[str, Any] | None:
        for rx, template in self._paths:
            if rx.match(path):
                op = self.spec["paths"][template].get(method.lower())
                if op is not None:
                    return dict(op)
        return None

    def body_schema(self, op: dict[str, Any]) -> dict[str, Any] | None:
        content = (op.get("requestBody") or {}).get("content") or {}
        schema = (content.get("application/json") or {}).get("schema")
        if not schema:
            return None
        if "$ref" in schema:
            name = schema["$ref"].split("/")[-1]
            return dict(self.spec["components"]["schemas"][name])
        return dict(schema)

    def query_names(self, op: dict[str, Any]) -> set[str]:
        return {p["name"] for p in op.get("parameters", []) if p.get("in") == "query"}


HOST_FIELDS = frozenset(
    {
        "first_name",
        "last_name",
        "email",
        "phone",
        "document_type",
        "document_number",
        "date_of_birth",
        "sex",
        "nationality",
    }
)
LISTING_FIELDS = frozenset(
    {
        "host_id",
        "title",
        "description",
        "property_type_id",
        "sector_id",
        "street_address",
        "apartment_suite",
        "latitude",
        "longitude",
        "price_per_night",
        "max_guests",
        "bedrooms",
        "beds",
        "bathrooms",
        "amenities",
    }
)


@dataclass(frozen=True)
class AgentOp:
    """Una operación de la API del agente."""

    query: frozenset[str] = frozenset()
    json_allowed: frozenset[str] | None = None
    json_required: frozenset[str] = frozenset()
    parts_allowed: frozenset[str] | None = None
    parts_required: frozenset[str] = frozenset()


_ID = r"[0-9A-Za-z-]+"
AGENT: dict[tuple[str, str], AgentOp] = {
    ("GET", r"/agent/catalogs"): AgentOp(),
    ("GET", r"/agent/hosts"): AgentOp(query=frozenset({"page", "per_page"})),
    ("POST", r"/agent/hosts"): AgentOp(
        json_allowed=HOST_FIELDS, json_required=HOST_FIELDS - {"phone"}
    ),
    ("GET", rf"/agent/hosts/{_ID}"): AgentOp(),
    ("GET", rf"/agent/hosts/{_ID}/kyc-link"): AgentOp(),
    ("POST", rf"/agent/hosts/{_ID}/kyc"): AgentOp(
        parts_allowed=frozenset({"document_image", "selfie_image"}),
        parts_required=frozenset({"document_image"}),
    ),
    ("GET", r"/agent/listings"): AgentOp(query=frozenset({"page", "per_page"})),
    ("POST", r"/agent/listings"): AgentOp(
        json_allowed=LISTING_FIELDS,
        json_required=LISTING_FIELDS - {"apartment_suite", "amenities"},
    ),
    ("GET", rf"/agent/listings/{_ID}"): AgentOp(),
    ("POST", rf"/agent/listings/{_ID}/media"): AgentOp(
        parts_allowed=frozenset({"files[]"}), parts_required=frozenset({"files[]"})
    ),
    ("PATCH", rf"/agent/listings/{_ID}/status"): AgentOp(
        json_allowed=frozenset({"status"}), json_required=frozenset({"status"})
    ),
}


def agent_op(method: str, path: str) -> AgentOp | None:
    for (m, rx), op in AGENT.items():
        if m == method and re.fullmatch(rx, path):
            return op
    return None


@dataclass
class FakeStore:
    """``AccountStore`` en memoria."""

    connected: bool = True
    environment: Any = "production"
    token: str = "tenant-key-of-the-business"
    links: dict[tuple[uuid.UUID, uuid.UUID], Link] = field(default_factory=dict)
    audits: list[tuple[uuid.UUID, uuid.UUID, str, str | None]] = field(default_factory=list)
    phones: dict[uuid.UUID, str] = field(default_factory=dict)
    save_fails: bool = False
    locks: int = 0
    reviews: int = 0

    async def require_connection(self, tenant_id: uuid.UUID) -> Connection:
        if not self.connected:
            raise QuedateNotConfigured("Quédate no está disponible para este negocio.")
        return Connection(environment=self.environment, token=self.token)

    async def load(self, tenant_id: uuid.UUID, customer_id: uuid.UUID) -> Link | None:
        link = self.links.get((tenant_id, customer_id))
        if link is None:
            return None
        return Link(host_id=link.host_id, state=dict(link.state), needs_review=link.needs_review)

    async def save(self, tenant_id: uuid.UUID, customer_id: uuid.UUID, *, host_id: str) -> None:
        if self.save_fails:
            raise RuntimeError("db down")
        self.links[(tenant_id, customer_id)] = Link(host_id=host_id)
        self.audits.append((tenant_id, customer_id, "connector.customer_account_linked", None))

    async def linked_to_other(
        self, tenant_id: uuid.UUID, customer_id: uuid.UUID, host_id: str
    ) -> bool:
        return any(
            t == tenant_id and c != customer_id and link.host_id == host_id
            for (t, c), link in self.links.items()
        )

    async def mark_review(self, tenant_id: uuid.UUID, customer_id: uuid.UUID) -> None:
        self.reviews += 1
        self.links[(tenant_id, customer_id)].needs_review = True

    async def save_state(
        self, tenant_id: uuid.UUID, customer_id: uuid.UUID, state: dict[str, Any]
    ) -> None:
        self.links[(tenant_id, customer_id)].state = dict(state)

    async def audit(
        self,
        tenant_id: uuid.UUID,
        customer_id: uuid.UUID,
        action: str,
        operation: str | None = None,
    ) -> None:
        self.audits.append((tenant_id, customer_id, action, operation))

    async def customer_phone(self, tenant_id: uuid.UUID, customer_id: uuid.UUID) -> str | None:
        return self.phones.get(customer_id)

    @asynccontextmanager
    async def lock(self, tenant_id: uuid.UUID, customer_id: uuid.UUID) -> AsyncIterator[None]:
        self.locks += 1
        yield


PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


@dataclass
class FakePhotos:
    """``PhotoSource`` en memoria: las fotos de cada persona y lo que se leyó."""

    by_customer: dict[uuid.UUID, list[Photo]] = field(default_factory=dict)
    reads: list[str] = field(default_factory=list)

    def give(self, customer_id: uuid.UUID, n: int, mime: str = "image/jpeg") -> list[str]:
        now = datetime.now(UTC)
        photos = [
            Photo(
                photo_id=str(uuid.uuid4()),
                sent_at=now - timedelta(minutes=i),
                key=f"tenant/x/media/{customer_id}/{i}",
                mime=mime,
            )
            for i in range(n)
        ]
        self.by_customer.setdefault(customer_id, []).extend(photos)
        return [p.photo_id for p in photos]

    async def recent(self, tenant_id: uuid.UUID, customer_id: uuid.UUID) -> list[Photo]:
        return list(self.by_customer.get(customer_id, []))

    async def read(self, photo: Photo) -> tuple[bytes, str]:
        self.reads.append(photo.photo_id)
        return PNG, photo.mime


@dataclass
class Env:
    store: FakeStore
    rec: Recorder
    photos: FakePhotos


@contextmanager
def installed(tenant_id: uuid.UUID, customer_id: uuid.UUID | None) -> Iterator[Env]:
    """Sustituye base de datos, fotos y Quédate durante una prueba."""
    env = Env(store=FakeStore(), rec=Recorder(), photos=FakePhotos())
    accounts.set_test_store(env.store)
    photos.set_test_photos(env.photos)
    tools.set_test_client_factory(env.rec.factory())
    try:
        with tenant_context(tenant_id), customer_context(customer_id):
            yield env
    finally:
        accounts.set_test_store(None)
        photos.set_test_photos(None)
        tools.set_test_client_factory(None)


def result(envelope: Any) -> dict[str, Any]:
    out: dict[str, Any] = envelope.result if hasattr(envelope, "result") else envelope["result"]
    return out


def tool(name: str) -> Any:
    return next(t for t in tools.QUEDATE_TOOLS if t.name == name)()


def serve_everything(rec: Recorder) -> None:
    """Todas las rutas que usa el conector, con las capturas de Quédate dev."""
    ex = EXAMPLES
    rec.on("GET", "/agent/catalogs", body=ex["catalogs_200"])
    rec.on("GET", "/agent/hosts", body=ex["hosts_page_200"])
    rec.on("POST", "/agent/hosts", 201, ex["host_create_201"])
    rec.on("GET", f"/agent/hosts/{HOST_ID}", body=ex["host_get_200"])
    rec.on("GET", f"/agent/hosts/{HOST_ID}/kyc-link", body=ex["kyc_link_200"])
    rec.on(
        "POST",
        f"/agent/hosts/{HOST_ID}/kyc",
        body={
            "success": True,
            "message": "Documentos recibidos.",
            "data": {"kyc_document_status": "pending"},
        },
    )
    rec.on("GET", "/agent/listings", body=ex["listings_page_200"])
    rec.on("GET", f"/agent/listings/{LISTING_ID}", body=ex["listing_get_200"])
    rec.on("POST", "/agent/listings", 201, ex["listing_create_201"])
    rec.on("POST", f"/agent/listings/{LISTING_ID}/media", body=ex["media_200"])
    rec.on("PATCH", f"/agent/listings/{LISTING_ID}/status", body=ex["status_pending_200"])
    rec.on("GET", "/search/listings", body={"success": True, "data": {"data": [], "total": 0}})
    rec.on("GET", f"/listings/{LISTING_ID}", body={"success": True, "data": {"id": LISTING_ID}})
    rec.on("POST", "/checkout/quote", body={"success": True, "data": {"total_usd": 20.0}})
    rec.on("GET", "/settings/public", body=ex["settings_public_200"])


HOST_DATA: dict[str, Any] = {
    "first_name": "Ana",
    "last_name": "Prueba",
    "document_type": "CI",
    "document_number": "V-00000000",
    "date_of_birth": "1990-01-01",
    "sex": "F",
}
LISTING_DATA: dict[str, Any] = {
    "title": "Apartamento de prueba",
    "description": "Un apartamento de prueba, luminoso y tranquilo.",
    "property_type_id": EXAMPLES["catalogs_200"]["data"]["property_types"][0]["id"],
    "sector_id": "01a1e5e0-5ec7-7000-8000-000000000001",
    "street_address": "Calle Ficticia 1",
    "latitude": 10.5,
    "longitude": -66.9,
    "price_per_night": 25,
    "max_guests": 2,
    "bedrooms": 1,
    "beds": 1,
    "bathrooms": 1,
    "amenities": ["Wifi"],
}
