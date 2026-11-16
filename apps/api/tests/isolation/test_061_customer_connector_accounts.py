"""Garantías 8 y 1: el anfitrión de Quédate de una persona solo lo usa esa persona
(spec 061, enmienda del 2026-11-16; T010 a T014).

Todas las llamadas van con la clave del negocio, que en Quédate solo alcanza los
anfitriones que ella misma creó. Auphere guarda, por cliente final, **qué anfitrión
es suyo** (sin credencial). Aquí se prueba con la base de datos de verdad y las
herramientas reales, con un Quédate falso por transporte que aísla por clave como
el de verdad:

1. **RLS** (garantía 1): el vínculo de un negocio no se ve ni se escribe desde otro.
2. **Dos clientes del mismo negocio** (garantía 8): con el turno de una persona,
   ninguna herramienta toca el anfitrión, los anuncios ni las fotos de otra, ni
   dando su correo (un anfitrión, una persona; /cso del 2026-11-16).
3. **Cada negocio, su clave y su entorno**: el turno de A nunca sale con la de B.
4. **Barrido de argumentos**: las de la persona no dejan nombrar cliente, tenant,
   anfitrión, clave ni conversación; la única entrada del eje de personas es
   ``register_me.email`` (research D11). Las de equipo, solo ``host_id`` y los
   datos de la persona que dan de alta.
5. **Barrido de fugas**: la clave del negocio no aparece en salidas, errores,
   registros ni auditoría; la tabla no tiene dónde guardar una credencial.
6. **Revisión, borrado en cascada y partner sin acceso** (spec 060).
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
import sqlalchemy as sa
import structlog
from nexus_mcp import build_default_registry
from nexus_mcp.base import ToolError
from nexus_mcp.servers.quedate import photos as qphotos
from nexus_mcp.servers.quedate import tools as qtools
from nexus_mcp.servers.quedate.client import QuedateClient
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.tenant_context import customer_context, tenant_context, tenant_scoped_session
from nexus_api.db.models import (
    AuditLog,
    Channel,
    ChannelStatus,
    ChannelType,
    Connector,
    ConnectorPartnerAccess,
    Conversation,
    ConversationStatus,
    Customer,
    CustomerConnectorAccount,
    Message,
    MessageDirection,
    MessageStatus,
    TenantConnector,
    TenantCredentials,
)

from ..integration.business._business_world import Biz, new_business
from ..integration.connectors._activation_world import connect
from ..integration.connectors.conftest import fake_composio, seeded_catalog  # noqa: F401
from .test_51_new_tools_take_no_end_customer import END_CUSTOMER_AXIS

pytestmark = [pytest.mark.isolation]  # asyncio_mode=auto

SLUG = "quedate"
KEY_A = "41|business-a-key-never-shown"
KEY_B = "42|business-b-key-never-shown"
PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32


class FakeQuedate:
    """La API del agente de Quédate por transporte, aislada por clave como la de verdad:
    una clave solo ve los anfitriones y anuncios que creó, y lo ajeno da 403."""

    def __init__(self) -> None:
        self.sent: list[httpx.Request] = []
        self.hosts: dict[str, dict[str, Any]] = {}
        self.listings: dict[str, dict[str, Any]] = {}

    @staticmethod
    def _key(request: httpx.Request) -> str:
        return request.headers.get("authorization", "").removeprefix("Bearer ")

    @staticmethod
    def _page(rows: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            "success": True,
            "data": {
                "current_page": 1,
                "data": rows,
                "last_page": 1,
                "per_page": 50,
                "total": len(rows),
            },
        }

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.sent.append(request)
        key = self._key(request)
        path = request.url.path.removeprefix("/api/v1")
        method = request.method
        forbidden = httpx.Response(
            403, json={"success": False, "error_code": "FORBIDDEN", "message": "No."}
        )
        parts = path.strip("/").split("/")

        if (method, path) == ("POST", "/agent/hosts"):
            body = json.loads(request.content)
            if any(h["email"] == body["email"] for h in self.hosts.values()):
                return httpx.Response(
                    422,
                    json={
                        "success": False,
                        "error_code": "VALIDATION_ERROR",
                        "message": "Validation failed",
                        "errors": {"email": ["The email has already been taken."]},
                    },
                )
            hid = str(uuid.uuid4())
            self.hosts[hid] = {
                "key": key,
                "id": hid,
                "email": body["email"],
                "phone": body.get("phone"),
                "name": "Anfitriona",
            }
            return httpx.Response(
                201, json={"success": True, "data": {"id": hid, "kyc_verified": False}}
            )
        if (method, path) == ("GET", "/agent/hosts"):
            rows = [
                {k: v for k, v in h.items() if k != "key"}
                for h in self.hosts.values()
                if h["key"] == key
            ]
            return httpx.Response(200, json=self._page(rows))
        if parts[:2] == ["agent", "hosts"] and len(parts) >= 3:
            host = self.hosts.get(parts[2])
            if host is None or host["key"] != key:
                return forbidden
            if len(parts) == 3:
                return httpx.Response(
                    200,
                    json={
                        "success": True,
                        "data": {"id": host["id"], "name": "Anfitriona", "listings": []},
                    },
                )
            if parts[3] == "kyc-link":
                return httpx.Response(
                    200,
                    json={
                        "success": True,
                        "data": {"kyc_url": "https://dev.quedate.net/kyc/t", "expires_in_days": 7},
                    },
                )
            if parts[3] == "kyc":
                return httpx.Response(
                    200, json={"success": True, "data": {"kyc_document_status": "pending"}}
                )
        if (method, path) == ("POST", "/agent/listings"):
            body = json.loads(request.content)
            host = self.hosts.get(body["host_id"])
            if host is None or host["key"] != key:
                return forbidden
            lid = str(uuid.uuid4())
            self.listings[lid] = {
                "key": key,
                "id": lid,
                "user_id": body["host_id"],
                "status": "draft",
            }
            return httpx.Response(
                201, json={"success": True, "data": {"id": lid, "status": "draft"}}
            )
        if (method, path) == ("GET", "/agent/listings"):
            rows = [
                {k: v for k, v in x.items() if k != "key"}
                for x in self.listings.values()
                if x["key"] == key
            ]
            return httpx.Response(200, json=self._page(rows))
        if parts[:2] == ["agent", "listings"] and len(parts) >= 3:
            listing = self.listings.get(parts[2])
            if listing is None or listing["key"] != key:
                return forbidden
            if len(parts) == 4 and parts[3] == "status":
                listing["status"] = json.loads(request.content)["status"]
                return httpx.Response(
                    200,
                    json={
                        "success": True,
                        "data": {"id": listing["id"], "status": listing["status"]},
                    },
                )
            if len(parts) == 4 and parts[3] == "media":
                return httpx.Response(200, json={"success": True, "data": {"total_photos": 1}})
            return httpx.Response(
                200,
                json={"success": True, "data": {k: v for k, v in listing.items() if k != "key"}},
            )
        if (method, path) == ("GET", "/agent/catalogs"):
            return httpx.Response(200, json={"success": True, "data": {"states": []}})
        return httpx.Response(200, json={"success": True, "data": []})

    def factory(self) -> Any:
        def make(
            *,
            environment: Any = "production",
            token: str | None = None,
            max_retries: int | None = None,
        ) -> QuedateClient:
            return QuedateClient(
                environment=environment,
                token=token,
                max_retries=0,
                transport=httpx.MockTransport(self.handle),
            )

        return make

    def keys_of(self, requests: list[httpx.Request]) -> set[str]:
        return {self._key(r) for r in requests}


class _StorelessPhotos(qphotos._DbPhotos):
    """Las fotos de verdad (base de datos y RLS) sin el almacén de medios."""

    def __init__(self) -> None:
        self.reads: list[str] = []

    async def read(self, photo: qphotos.Photo) -> tuple[bytes, str]:
        self.reads.append(photo.photo_id)
        return PNG, photo.mime


async def _customer(
    db_session: AsyncSession, tenant_id: uuid.UUID, phone: str, *, known_phone: bool = True
) -> uuid.UUID:
    await db_session.commit()  # tenant_scoped_session abre su propia transacción
    async with tenant_scoped_session(db_session, tenant_id):
        c = Customer(
            tenant_id=tenant_id,
            identifier=phone,
            name=f"Persona {phone[-2:]}",
            phone=f"+{phone}" if known_phone else None,
        )
        db_session.add(c)
        await db_session.flush()
        cid = c.id
    await db_session.commit()
    return cid


async def _conversation(
    db_session: AsyncSession,
    tenant_id: uuid.UUID,
    customer_id: uuid.UUID,
    kind: ChannelType = ChannelType.WHATSAPP,
) -> uuid.UUID:
    """Una conversación de la persona en un canal de ese tipo."""
    now = datetime.now(UTC)
    await db_session.commit()
    async with tenant_scoped_session(db_session, tenant_id):
        channel = Channel(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            type=kind,
            provider="meta",
            provider_identifier=f"+3460000{uuid.uuid4().int % 10000:04d}",
            config={"phone_number_id": "PN"},
            status=ChannelStatus.ACTIVE,
        )
        db_session.add(channel)
        await db_session.flush()
        conv = Conversation(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            channel_id=channel.id,
            customer_id=customer_id,
            status=ConversationStatus.OPEN,
            last_inbound_at=now,
            last_message_at=now,
        )
        db_session.add(conv)
        await db_session.flush()
        conv_id = conv.id
    await db_session.commit()
    return conv_id


async def _photo(db_session: AsyncSession, tenant_id: uuid.UUID, customer_id: uuid.UUID) -> str:
    """Una conversación de la persona con una imagen recibida hace un minuto."""
    now = datetime.now(UTC)
    conv_id = await _conversation(db_session, tenant_id, customer_id)
    async with tenant_scoped_session(db_session, tenant_id):
        msg = Message(
            id=uuid.uuid4(),
            tenant_id=tenant_id,
            conversation_id=conv_id,
            direction=MessageDirection.INBOUND,
            status=MessageStatus.DELIVERED,
            content="",
            media_kind="image",
            media_s3_key=f"tenants/{tenant_id}/inbound/{customer_id}.jpg",
            media_mime="image/jpeg",
            media_filename="doc.jpg",
            created_at=now - timedelta(minutes=1),
        )
        db_session.add(msg)
        await db_session.flush()
        mid = str(msg.id)
    await db_session.commit()
    return mid


async def _set_key(
    db_session: AsyncSession, biz: Biz, connector: Connector, key: str, environment: str | None
) -> None:
    await db_session.commit()
    async with tenant_scoped_session(db_session, biz.tenant_id):
        cred = await db_session.scalar(
            sa.select(TenantCredentials).where(
                TenantCredentials.tenant_id == biz.tenant_id, TenantCredentials.integration == SLUG
            )
        )
        payload = json.dumps({"api_key": key}).encode()
        if cred is None:
            db_session.add(
                TenantCredentials(
                    tenant_id=biz.tenant_id, integration=SLUG, encrypted_payload=payload
                )
            )
        else:
            cred.encrypted_payload = payload
        tc = await db_session.scalar(
            sa.select(TenantConnector).where(
                TenantConnector.tenant_id == biz.tenant_id,
                TenantConnector.connector_id == connector.id,
            )
        )
        assert tc is not None
        tc.credentials_ref = {"endpoint_meta": {"environment": environment} if environment else {}}
    await db_session.commit()


@pytest.fixture
async def world(
    client: Any,
    db_session: AsyncSession,
    console_world: dict[str, Any],
    seeded_catalog: None,  # noqa: F811
) -> Any:
    a = await new_business(client, db_session, console_world, name="Quédate A", label="a")
    b = await new_business(client, db_session, console_world, name="Quédate B", label="b")
    connector = await db_session.scalar(sa.select(Connector).where(Connector.slug == SLUG))
    assert connector is not None, "la semilla de quedate no está"
    # Nace deshabilitado por defecto (0233): Auphere lo habilita para el partner.
    for biz in (a, b):
        await db_session.merge(
            ConnectorPartnerAccess(
                connector_slug=SLUG, partner_id=biz.partner_id, enabled=True, reason="t", set_by="t"
            )
        )
    await db_session.commit()
    await connect(db_session, a, connector)
    await connect(db_session, b, connector)
    await _set_key(db_session, a, connector, KEY_A, "dev")
    await _set_key(db_session, b, connector, KEY_B, None)
    fake = FakeQuedate()
    photos = _StorelessPhotos()
    qtools.set_test_client_factory(fake.factory())
    qphotos.set_test_photos(photos)
    yield {
        "a": a,
        "b": b,
        "connector": connector,
        "a1": await _customer(db_session, a.tenant_id, "584140000001"),
        "a2": await _customer(db_session, a.tenant_id, "584140000002"),
        "b1": await _customer(db_session, b.tenant_id, "584140000003"),
        "fake": fake,
        "photos": photos,
    }
    qtools.set_test_client_factory(None)
    qphotos.set_test_photos(None)


HOST = {
    "first_name": "María",
    "last_name": "Pérez",
    "document_type": "CI",
    "document_number": "V-12345678",
    "date_of_birth": "1990-01-01",
    "sex": "F",
}
REGISTER = {**HOST, "email": "maria@example.com", "email_confirmed": True}
LISTING = {
    "title": "Apartamento de prueba",
    "description": "Un apartamento de prueba, luminoso y tranquilo.",
    "property_type_id": "pt-1",
    "sector_id": "sec-1",
    "street_address": "Calle Ficticia 1",
    "latitude": 10.5,
    "longitude": -66.9,
    "price_per_night": 25,
    "max_guests": 2,
    "bedrooms": 1,
    "beds": 1,
    "bathrooms": 1,
}


async def _run(biz: Biz, customer: uuid.UUID | None, name: str, args: dict[str, Any]) -> Any:
    cls = next(t for t in qtools.QUEDATE_TOOLS if t.name == name)
    with tenant_context(biz.tenant_id), customer_context(customer):
        envelope = await cls().invoke(args)
    result: dict[str, Any] = envelope.result if hasattr(envelope, "result") else envelope["result"]
    return result


# ── 1. RLS (garantía 1) ──────────────────────────────────────────────────


async def test_another_business_neither_sees_nor_writes_a_link(
    world: dict[str, Any], db_session: AsyncSession
) -> None:
    a, b = world["a"], world["b"]
    await _run(a, world["a1"], "quedate.register_me", REGISTER)

    await db_session.commit()
    async with tenant_scoped_session(db_session, a.tenant_id):
        mine = (await db_session.scalars(sa.select(CustomerConnectorAccount))).all()
        assert len(mine) == 1 and mine[0].customer_id == world["a1"]
    await db_session.commit()

    async with tenant_scoped_session(db_session, b.tenant_id):
        seen = (await db_session.scalars(sa.select(CustomerConnectorAccount))).all()
        assert seen == []
    await db_session.commit()

    with pytest.raises(Exception, match=r"row-level security|violates"):
        async with tenant_scoped_session(db_session, b.tenant_id):
            db_session.add(
                CustomerConnectorAccount(
                    tenant_id=a.tenant_id,
                    customer_id=world["a1"],
                    connector_slug=SLUG,
                    external_user_id="x",
                )
            )
            await db_session.flush()
    await db_session.rollback()


# ── 2. Dos clientes del mismo negocio (garantía 8) ───────────────────────


async def test_the_person_of_the_turn_never_reaches_another_persons_host(
    world: dict[str, Any],
) -> None:
    a, fake = world["a"], world["fake"]
    await _run(a, world["a1"], "quedate.register_me", REGISTER)
    created = await _run(a, world["a1"], "quedate.create_my_listing", LISTING)
    a1_listing = created["listing_id"]
    (a1_host,) = list(fake.hosts)
    fake.sent.clear()

    # Con el turno de A2, que no tiene anfitrión: nada de A1.
    assert (await _run(a, world["a2"], "quedate.my_host", {}))["linked"] is False
    assert (await _run(a, world["a2"], "quedate.my_listings", {}))["linked"] is False
    for name, args in (
        ("quedate.my_verification_link", {}),
        ("quedate.create_my_listing", LISTING),
        ("quedate.submit_my_listing", {"listing_id": a1_listing}),
        ("quedate.hide_my_listing", {"listing_id": a1_listing}),
    ):
        with pytest.raises(ToolError, match="register_me"):
            await _run(a, world["a2"], name, args)
    assert fake.sent == [], "el turno de otra persona llegó a Quédate"

    # A2 se da de alta: su propio anfitrión. El anuncio de A1 sigue sin ser suyo,
    # aunque la clave del negocio lo alcance.
    await _run(a, world["a2"], "quedate.register_me", {**REGISTER, "email": "otra@example.com"})
    a2_host = next(h for h in fake.hosts if h != a1_host)
    with pytest.raises(ToolError, match="no es de esta persona"):
        await _run(a, world["a2"], "quedate.submit_my_listing", {"listing_id": a1_listing})
    assert not [r for r in fake.sent if r.method == "PATCH"]
    assert (await _run(a, world["a2"], "quedate.my_listings", {}))["items"] == []

    fake.sent.clear()
    await _run(a, world["a2"], "quedate.my_host", {})
    await _run(a, world["a1"], "quedate.my_host", {})
    assert [r.url.path for r in fake.sent] == [
        f"/api/v1/agent/hosts/{a2_host}",
        f"/api/v1/agent/hosts/{a1_host}",
    ]


async def test_someone_elses_email_never_links_their_host(
    world: dict[str, Any], db_session: AsyncSession
) -> None:
    """/cso del 2026-11-16: A2 da el correo de A1. Quédate dice que está tomado y el
    anfitrión es de la clave, pero su teléfono es el de A1: no se vincula (3.5)."""
    a, fake = world["a"], world["fake"]
    await _run(a, world["a1"], "quedate.register_me", REGISTER)
    out = await _run(a, world["a2"], "quedate.register_me", REGISTER)
    assert out["registered"] is False and out["rejected_field"] == "email"
    assert (await _run(a, world["a2"], "quedate.my_host", {}))["linked"] is False

    await db_session.commit()
    async with tenant_scoped_session(db_session, a.tenant_id):
        rows = (await db_session.scalars(sa.select(CustomerConnectorAccount))).all()
        assert [r.customer_id for r in rows] == [world["a1"]]
        host_id = rows[0].external_user_id
    await db_session.commit()

    # Y la base no deja dos personas en un mismo anfitrión.
    with pytest.raises(Exception, match=r"uq_customer_connector_accounts_external|duplicate"):
        async with tenant_scoped_session(db_session, a.tenant_id):
            db_session.add(
                CustomerConnectorAccount(
                    tenant_id=a.tenant_id,
                    customer_id=world["a2"],
                    connector_slug=SLUG,
                    external_user_id=host_id,
                )
            )
            await db_session.flush()
    await db_session.rollback()
    assert len(fake.hosts) == 1


@pytest.mark.parametrize(
    ("kind", "sent"),
    [(ChannelType.WHATSAPP, "+584140000077"), (ChannelType.INSTAGRAM, None)],
    ids=["whatsapp", "instagram"],
)
async def test_the_phone_is_the_channels_only_on_whatsapp(
    world: dict[str, Any], db_session: AsyncSession, kind: ChannelType, sent: str | None
) -> None:
    """3.2: sin ``phone`` de Meta, el identificador solo es un teléfono en WhatsApp. En
    Instagram es el id de Meta y no viaja a Quédate como teléfono."""
    a, fake = world["a"], world["fake"]
    who = await _customer(db_session, a.tenant_id, "584140000077", known_phone=False)
    await _conversation(db_session, a.tenant_id, who, kind)
    await _run(a, who, "quedate.register_me", {**REGISTER, "email": f"{kind.value}@example.com"})
    (created,) = [
        r for r in fake.sent if r.method == "POST" and r.url.path.endswith("/agent/hosts")
    ]
    assert json.loads(created.content).get("phone") == sent


async def test_a_person_cannot_send_another_persons_photos(
    world: dict[str, Any], db_session: AsyncSession
) -> None:
    """Las fotos son las de la conversación de la persona del turno (3.8)."""
    a, fake, photos = world["a"], world["fake"], world["photos"]
    # La de A2 primero: la conversación más reciente del negocio es la de A1, y la de
    # B1 la más reciente de todas. Solo el filtro por persona y la RLS dejan a A2 la suya.
    a2_photo = await _photo(db_session, a.tenant_id, world["a2"])
    a1_photo = await _photo(db_session, a.tenant_id, world["a1"])
    b1_photo = await _photo(db_session, world["b"].tenant_id, world["b1"])
    await _run(a, world["a2"], "quedate.register_me", {**REGISTER, "email": "a2@example.com"})

    listed = await _run(a, world["a2"], "quedate.recent_photos", {})
    assert [p["photo_id"] for p in listed["photos"]] == [a2_photo]

    fake.sent.clear()
    for foreign in (a1_photo, b1_photo):
        with pytest.raises(ToolError, match="no está entre"):
            await _run(a, world["a2"], "quedate.upload_my_identity", {"document_photo_id": foreign})
    assert photos.reads == [] and fake.sent == []

    out = await _run(a, world["a2"], "quedate.upload_my_identity", {"document_photo_id": a2_photo})
    assert out["uploaded"] is True and photos.reads == [a2_photo]


async def test_the_same_customer_id_in_another_business_is_another_link(
    world: dict[str, Any],
) -> None:
    """El cliente del turno se busca con el tenant del turno: la RLS manda."""
    await _run(world["a"], world["a1"], "quedate.register_me", REGISTER)
    out = await _run(world["b"], world["a1"], "quedate.my_host", {})
    assert out["linked"] is False


# ── 3. Cada negocio, su clave y su entorno ───────────────────────────────


async def test_each_business_calls_with_its_own_key_and_environment(world: dict[str, Any]) -> None:
    a, b, fake = world["a"], world["b"], world["fake"]
    await _run(a, world["a1"], "quedate.register_me", REGISTER)
    a_sent = list(fake.sent)
    fake.sent.clear()
    await _run(b, world["b1"], "quedate.register_me", {**REGISTER, "email": "b1@example.com"})
    b_sent = list(fake.sent)

    assert fake.keys_of(a_sent) == {KEY_A} and {r.url.host for r in a_sent} == {
        "dev-api.quedate.net"
    }
    assert fake.keys_of(b_sent) == {KEY_B} and {r.url.host for r in b_sent} == {
        "api-v2.quedate.net"
    }

    # Un anfitrión de A, pedido desde B con su clave: Quédate dice 403 y se cuenta así.
    a_host = next(h for h, v in fake.hosts.items() if v["key"] == KEY_A)
    with pytest.raises(ToolError, match="no alcanza"):
        await _run(b, None, "quedate.get_host", {"host_id": a_host})


# ── 4. Barrido de argumentos ─────────────────────────────────────────────

FORBIDDEN = END_CUSTOMER_AXIS | {
    "tenant",
    "tenant_id",
    "customer_id",
    "account",
    "account_id",
    "user_id",
    "external_user_id",
    "token",
    "api_key",
    "key",
    "credential",
    "password",
    "conversation_id",
    "host_id",
    "owner_id",
    "environment",
}


def test_no_quedate_tool_lets_the_model_name_a_person_an_account_or_a_key() -> None:
    registry = build_default_registry()
    names = sorted(n for n in registry.names() if n.startswith("quedate."))
    assert len(names) == 27, names
    found = {
        (d.name, arg)
        for d in registry.get_tool_definitions(names)
        for arg in ((d.parameters or {}).get("properties") or {})
        if arg in FORBIDDEN
    }
    person = {pair for pair in found if pair[0] in qtools.PERSON_TOOLS}
    team = found - person
    assert person == {("quedate.register_me", "email")}
    # Las de equipo nombran un anfitrión de la clave, o los datos de quien dan de alta.
    assert {arg for _, arg in team} <= {"host_id", "email", "phone"}
    assert {name for name, arg in team if arg != "host_id"} == {"quedate.create_host"}


# ── 5. Barrido de fugas ──────────────────────────────────────────────────


async def test_the_business_key_never_leaks_and_no_credential_is_stored(
    world: dict[str, Any], db_session: AsyncSession
) -> None:
    a, b = world["a"], world["b"]
    outputs: list[str] = []
    errors: list[str] = []
    with structlog.testing.capture_logs() as logs:
        outputs.append(json.dumps(await _run(a, world["a1"], "quedate.register_me", REGISTER)))
        for name in ("quedate.my_host", "quedate.my_verification_link", "quedate.my_listings"):
            outputs.append(json.dumps(await _run(a, world["a1"], name, {})))
        outputs.append(json.dumps(await _run(a, world["a1"], "quedate.create_my_listing", LISTING)))
        with pytest.raises(ToolError) as exc:
            await _run(b, None, "quedate.get_host", {"host_id": next(iter(world["fake"].hosts))})
        errors.append(str(exc.value))

    await db_session.commit()
    async with tenant_scoped_session(db_session, a.tenant_id):
        audits = (
            await db_session.scalars(sa.select(AuditLog).where(AuditLog.tenant_id == a.tenant_id))
        ).all()
    await db_session.commit()
    columns = set(
        (
            await db_session.execute(
                sa.text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'customer_connector_accounts'"
                )
            )
        ).scalars()
    )
    await db_session.commit()

    haystacks = {
        "salidas": "\n".join(outputs),
        "errores": "\n".join(errors),
        "registros": json.dumps(logs, default=str),
        "auditoría": json.dumps(
            [(x.actor, x.action, x.target, x.before_json, x.after_json) for x in audits],
            default=str,
        ),
    }
    for where, text in haystacks.items():
        for secret in (KEY_A, KEY_B):
            assert secret not in text, f"la clave del negocio aparece en {where}"
        if where in {"registros", "auditoría"}:
            for personal in ("maria@example.com", "María", "V-12345678"):
                assert personal not in text, f"un dato personal aparece en {where}"
    assert any(x.action == "connector.customer_account_linked" for x in audits)
    assert not columns & {"credential", "token", "api_key", "password"}, columns


# ── 6. Revisión, borrado en cascada y partner sin acceso ─────────────────


async def test_a_new_business_key_marks_the_link_for_review(
    world: dict[str, Any], db_session: AsyncSession
) -> None:
    """3.10: una clave nueva deja al anfitrión fuera; Quédate da 403 y el vínculo
    queda en revisión, sin escribir nada."""
    a = world["a"]
    await _run(a, world["a1"], "quedate.register_me", REGISTER)
    await _set_key(db_session, a, world["connector"], "43|rotated-key", "dev")

    with pytest.raises(ToolError, match="ya no lo alcanza"):
        await _run(a, world["a1"], "quedate.my_host", {})
    await db_session.commit()
    async with tenant_scoped_session(db_session, a.tenant_id):
        row = await db_session.scalar(sa.select(CustomerConnectorAccount))
        assert row is not None and row.needs_review is True
    await db_session.commit()
    world["fake"].sent.clear()
    with pytest.raises(ToolError, match="ya no lo alcanza"):
        await _run(a, world["a1"], "quedate.create_my_listing", LISTING)
    assert world["fake"].sent == []


async def test_erasing_the_customer_erases_the_link(
    world: dict[str, Any], db_session: AsyncSession
) -> None:
    a = world["a"]
    await _run(a, world["a1"], "quedate.register_me", REGISTER)
    await db_session.commit()
    async with tenant_scoped_session(db_session, a.tenant_id):
        await db_session.execute(sa.delete(Customer).where(Customer.id == world["a1"]))
    await db_session.commit()
    async with tenant_scoped_session(db_session, a.tenant_id):
        left = (await db_session.scalars(sa.select(CustomerConnectorAccount))).all()
    await db_session.commit()
    assert left == []


ARGS: dict[str, dict[str, Any]] = {
    "quedate.search_listings": {"city": "Caracas"},
    "quedate.get_listing": {"listing": "abc"},
    "quedate.quote_stay": {
        "listing_id": "abc",
        "check_in": "2026-12-10",
        "check_out": "2026-12-12",
        "guests": 2,
    },
    "quedate.register_me": REGISTER,
    "quedate.upload_my_identity": {"document_photo_id": "x"},
    "quedate.create_my_listing": LISTING,
    "quedate.add_my_listing_photos": {"listing_id": "abc", "photo_ids": ["x"]},
    "quedate.submit_my_listing": {"listing_id": "abc"},
    "quedate.hide_my_listing": {"listing_id": "abc"},
    "quedate.get_host": {"host_id": "h"},
    "quedate.create_host": {**HOST, "email": "x@example.com", "phone": "+584120000000"},
    "quedate.host_verification_link": {"host_id": "h"},
    "quedate.upload_host_identity": {"host_id": "h", "document_photo_id": "x"},
    "quedate.get_managed_listing": {"listing_id": "abc"},
    "quedate.create_listing": {**LISTING, "host_id": "h"},
    "quedate.add_listing_photos": {"listing_id": "abc", "photo_ids": ["x"]},
    "quedate.submit_listing": {"listing_id": "abc"},
    "quedate.hide_listing": {"listing_id": "abc"},
}


async def test_without_partner_access_every_quedate_tool_refuses_before_calling(
    world: dict[str, Any], db_session: AsyncSession
) -> None:
    a, fake = world["a"], world["fake"]
    await db_session.merge(
        ConnectorPartnerAccess(
            connector_slug=SLUG, partner_id=a.partner_id, enabled=False, reason="t", set_by="t"
        )
    )
    await db_session.commit()
    for cls in qtools.QUEDATE_TOOLS:
        with pytest.raises(ToolError, match="no está disponible"):
            await _run(a, world["a1"], cls.name, ARGS.get(cls.name, {}))
    assert fake.sent == [] and world["photos"].reads == []


async def test_no_customer_in_the_turn_refuses_the_persons_tools(world: dict[str, Any]) -> None:
    for name in sorted(qtools.PERSON_TOOLS):
        with pytest.raises(ToolError, match="no hay cliente"):
            await _run(world["a"], None, name, ARGS.get(name, {}))
    assert world["fake"].sent == []
