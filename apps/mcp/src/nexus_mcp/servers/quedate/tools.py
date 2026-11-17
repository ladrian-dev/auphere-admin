"""Las 27 herramientas ``quedate.*`` (spec 061, enmienda del 2026-11-16).

Cuatro grupos sobre la clave del cliente (``Connection``):

- **catálogo y públicas**: ubicaciones y opciones de anuncio (API del agente), y
  buscar, ver, cotizar y modo de reserva (API general, sin clave);
- **fotos de la conversación**: lo que la persona del turno mandó, para que elija;
- **de la persona que escribe**: su anfitrión sale del vínculo resuelto en el
  servidor, nunca de un argumento (garantía 8);
- **de equipo**: cualquier anfitrión de la clave. Qué agente las tiene lo decide el
  partner (Luis, 2026-11-16).

Ninguna publica: solo mandan a revisión de Quédate (``pending_approval``) u ocultan
(``hidden``). Quédate no borra, así que nada que cree se reintenta solo.
"""

from __future__ import annotations

import unicodedata
import uuid
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta
from typing import Any, ClassVar

import structlog
from nexus_api.core.tenant_context import get_current_customer, require_current_tenant

from nexus_mcp._customer import current_customer_or_refuse
from nexus_mcp.base import ToolBase, ToolError
from nexus_mcp.servers.quedate import photos as photo_source
from nexus_mcp.servers.quedate.accounts import Connection, Link, store
from nexus_mcp.servers.quedate.client import ListingStatus, QuedateClient
from nexus_mcp.servers.quedate.errors import (
    QuedateConflict,
    QuedateError,
    QuedateForbidden,
    QuedateNotFound,
    QuedateRateLimited,
    QuedateUnavailable,
    QuedateValidationError,
)
from nexus_mcp.servers.quedate.schemas import (
    BookingSettingsOutput,
    CreateHostInput,
    CreateHostOutput,
    CreateListingInput,
    CreateMyListingInput,
    GetListingInput,
    HostBrief,
    HostDetailOutput,
    HostRefInput,
    HostsOutput,
    IdentityOutput,
    ListingDetail,
    ListingOptionsOutput,
    ListingPhotosInput,
    ListingRefInput,
    ListingsOutput,
    ListingSummary,
    ListingWriteOutput,
    ListListingsInput,
    ListLocationsInput,
    ListLocationsOutput,
    ManagedListing,
    ManagedListingDetail,
    MyHostOutput,
    MyListingBrief,
    MyListingsOutput,
    Named,
    PageInput,
    PhotosOutput,
    QuoteStayInput,
    QuoteStayOutput,
    RecentPhoto,
    RecentPhotosOutput,
    RegisterMeInput,
    RegisterMeOutput,
    SearchListingsInput,
    SearchListingsOutput,
    StatusOutput,
    UploadHostIdentityInput,
    UploadMyIdentityInput,
    VerificationLinkOutput,
    _Empty,
)

log = structlog.get_logger(__name__)

MAX_ITEMS = 10
MAX_DESCRIPTION = 600
MAX_AMENITIES = 20
MAX_UNAVAILABLE_DATES = 120
MAX_LOCATIONS = 60
#: Para buscar un anuncio o un correo entre los de la clave.
SCAN_PER_PAGE = 50
SCAN_MAX_PAGES = 20
#: El enlace de KYC vale 7 días: se reutiliza mientras le quede más de un día (3.7).
LINK_MARGIN = timedelta(days=1)

_UNAVAILABLE = "Quédate no responde ahora mismo. Inténtalo de nuevo en unos minutos."
_REGISTER_FIRST = (
    "Esta persona aún no es anfitriona en Quédate: dala de alta con quedate.register_me."
)
_REVIEW = (
    "No puedo acceder desde aquí al anfitrión de esta persona en Quédate (la clave del "
    "negocio ya no lo alcanza). Puede darse de alta de nuevo; si no, que lo revise el "
    "equipo del negocio con Quédate."
)
_NOT_THIS_KEY = "La clave de este negocio no alcanza ese anfitrión o ese anuncio en Quédate."
_EMAIL_TAKEN = (
    "Ese correo ya es de otra cuenta de anfitriona en Quédate. Si es suyo, que el equipo "
    "del negocio lo revise con Quédate; si no, que dé otro correo."
)
_UNCONFIRMED = (
    "Quédate no respondió y puede que se haya hecho. Compruébalo con la lista de anuncios "
    "antes de repetirlo: Quédate no borra, y un duplicado se queda."
)


# ── cliente HTTP (con gancho de pruebas) ─────────────────────────────────

ClientFactory = Callable[..., QuedateClient]
_client_factory: ClientFactory | None = None


def set_test_client_factory(factory: ClientFactory | None) -> None:
    """Sustituye la construcción del cliente (las pruebas pasan un transporte falso)."""
    global _client_factory
    _client_factory = factory


def _client(conn: Connection, *, public: bool = False, retries: int | None = None) -> QuedateClient:
    token = None if public else conn.token
    if _client_factory is not None:
        return _client_factory(environment=conn.environment, token=token, max_retries=retries)
    return QuedateClient(environment=conn.environment, token=token, max_retries=retries)


# ── lectura tolerante de respuestas ──────────────────────────────────────


def _as_dict(v: Any) -> dict[str, Any]:
    return v if isinstance(v, dict) else {}


def _as_list(v: Any) -> list[Any]:
    return v if isinstance(v, list) else []


def _bool(v: Any) -> bool | None:
    if isinstance(v, bool):
        return v
    if isinstance(v, int) and v in (0, 1):
        return bool(v)
    return None


def _data(body: Any) -> Any:
    return body["data"] if isinstance(body, dict) and "data" in body else body


def _page(body: Any) -> tuple[list[dict[str, Any]], int | None, int, int | None]:
    """El paginador de Laravel (``data.data``) o una lista plana."""
    d = _data(body)
    if isinstance(d, list):
        return [x for x in d if isinstance(x, dict)], len(d), 1, 1
    d = _as_dict(d)
    rows: list[dict[str, Any]] = [x for x in _as_list(d.get("data")) if isinstance(x, dict)]
    total, page, last = d.get("total"), d.get("current_page"), d.get("last_page")
    return (
        rows,
        total if isinstance(total, int) else None,
        page if isinstance(page, int) else 1,
        last if isinstance(last, int) else None,
    )


def _first(d: dict[str, Any], *keys: str) -> Any:
    for k in keys:
        v = d.get(k)
        if v is not None and v != "":
            return v
    return None


def _num(v: Any) -> float | None:
    if isinstance(v, bool):
        return None
    if isinstance(v, int | float):
        return float(v)
    if isinstance(v, str):
        try:
            return float(v.replace(",", "."))
        except ValueError:
            return None
    return None


def _int(v: Any) -> int | None:
    n = _num(v)
    return int(n) if n is not None else None


def _str(v: Any) -> str | None:
    if isinstance(v, str) and v.strip():
        return v.strip()
    if isinstance(v, dict):
        name = v.get("name")
        return name.strip() if isinstance(name, str) and name.strip() else None
    return None


def _fold(text: str) -> str:
    return (
        unicodedata.normalize("NFKD", text)
        .encode("ascii", "ignore")
        .decode("ascii")
        .casefold()
        .strip()
    )


def _named(rows: list[Any]) -> list[Named]:
    out: list[Named] = []
    for r in rows:
        if isinstance(r, dict) and r.get("id") is not None and _str(r.get("name")):
            out.append(Named(id=str(r["id"]), name=str(_str(r.get("name")))))
    return out


def _brief(raw: dict[str, Any]) -> MyListingBrief:
    return MyListingBrief(
        id=str(raw.get("id")),
        title=_str(raw.get("title")),
        status=_str(raw.get("status")),
        price=_num(_first(raw, "price_per_night", "priceUSDT", "price")),
    )


def _managed(raw: dict[str, Any]) -> ManagedListing:
    return ManagedListing(
        id=str(raw.get("id")),
        host_id=_str(_first(raw, "host_id", "user_id")),
        title=_str(raw.get("title")),
        status=_str(raw.get("status")),
        price=_num(_first(raw, "price_per_night", "priceUSDT", "price")),
    )


def _location(raw: dict[str, Any], key: str) -> str | None:
    direct = _str(raw.get(key))
    if direct:
        return direct
    return _str(_as_dict(raw.get("location")).get(key))


def _friendly(exc: QuedateError) -> ToolError:
    if isinstance(exc, QuedateUnavailable | QuedateRateLimited):
        return ToolError(_UNAVAILABLE)
    if isinstance(exc, QuedateForbidden):
        return ToolError(_NOT_THIS_KEY)
    if isinstance(exc, QuedateNotFound):
        return ToolError("Quédate no encuentra lo que se pidió.")
    return ToolError(f"Quédate rechazó la petición: {exc}")


async def _scan(
    fetch: Callable[[int], Awaitable[Any]], match: Callable[[dict[str, Any]], bool]
) -> dict[str, Any] | None:
    """Recorre las páginas de un listado de la clave hasta encontrar una fila."""
    for page in range(1, SCAN_MAX_PAGES + 1):
        rows, _total, _page_no, last = _page(await fetch(page))
        for r in rows:
            if match(r):
                return r
        if not rows or (last is not None and page >= last):
            return None
    return None


# ── base ─────────────────────────────────────────────────────────────────


class _QuedateTool(ToolBase):
    side_effects: ClassVar[tuple[str, ...]] = ()

    async def _connected(self) -> tuple[uuid.UUID, Connection]:
        tenant_id: uuid.UUID = require_current_tenant()
        return tenant_id, await store().require_connection(tenant_id)


class _WriteTool(_QuedateTool):
    side_effects: ClassVar[tuple[str, ...]] = ("mutates_db",)


async def _unconfirmed(tenant_id: uuid.UUID, operation: str) -> None:
    """Una escritura sin respuesta queda en la auditoría (4.6)."""
    customer = get_current_customer()
    if customer is None:
        log.warning("quedate.write_unconfirmed", tenant_id=str(tenant_id), operation=operation)
        return
    try:
        await store().audit(tenant_id, customer, "connector.external_write_unconfirmed", operation)
    except Exception:
        log.error("quedate.write_unconfirmed_audit_failed", tenant_id=str(tenant_id))


def _listing_payload(fields: Any, host_id: str) -> dict[str, Any]:
    body: dict[str, Any] = fields.model_dump(mode="json", exclude={"host_id"}, exclude_none=True)
    body["host_id"] = host_id
    return body


def _host_payload(data: Any, *, email: str, phone: str | None) -> dict[str, Any]:
    body: dict[str, Any] = data.model_dump(
        mode="json",
        include={
            "first_name",
            "last_name",
            "document_type",
            "document_number",
            "date_of_birth",
            "sex",
            "nationality",
        },
    )
    body["email"] = email
    if phone:
        body["phone"] = phone
    return body


# ── catálogo ─────────────────────────────────────────────────────────────


class ListLocations(_QuedateTool):
    name = "quedate.list_locations"
    description = (
        "Valid Quédate locations with their ids. No arguments: the states. With state: its "
        "cities. With state and city: its sectors. A listing needs the sector id."
    )
    input_model = ListLocationsInput
    output_model = ListLocationsOutput

    async def run(self, payload: ListLocationsInput) -> ListLocationsOutput:  # type: ignore[override]
        _, conn = await self._connected()
        try:
            body = await _client(conn).catalogs()
        except QuedateError as exc:
            raise _friendly(exc) from exc
        states = [s for s in _as_list(_as_dict(_data(body)).get("states")) if isinstance(s, dict)]

        def pick(rows: list[Any], wanted: str) -> dict[str, Any] | None:
            for r in rows:
                if isinstance(r, dict) and _fold(str(r.get("name") or "")) == _fold(wanted):
                    return r
            return None

        def out(level: str, rows: list[Any], message: str | None = None) -> ListLocationsOutput:
            named = _named(rows)
            return ListLocationsOutput(
                level=level,  # type: ignore[arg-type]
                items=named[:MAX_LOCATIONS],
                truncated=len(named) > MAX_LOCATIONS,
                message=message,
            )

        if payload.state is None:
            return out("states", states)
        state = pick(states, payload.state)
        if state is None:
            return out(
                "states", states, f"No hay un estado «{payload.state}». Estos son los válidos."
            )
        cities = _as_list(state.get("cities"))
        if payload.city is None:
            return out("cities", cities)
        city = pick(cities, payload.city)
        if city is None:
            return out("cities", cities, f"No hay una ciudad «{payload.city}» en {payload.state}.")
        return out("sectors", _as_list(city.get("sectors")))


class ListingOptions(_QuedateTool):
    name = "quedate.listing_options"
    description = (
        "Options to create a Quédate listing: property types and amenities with their ids, "
        "rental types, booking modes, identity document types and today's BCV rate."
    )
    input_model = _Empty
    output_model = ListingOptionsOutput

    async def run(self, payload: _Empty) -> ListingOptionsOutput:  # type: ignore[override]
        _, conn = await self._connected()
        try:
            body = await _client(conn).catalogs()
        except QuedateError as exc:
            raise _friendly(exc) from exc
        d = _as_dict(_data(body))

        def strs(v: Any) -> list[str]:
            return [x for x in _as_list(v) if isinstance(x, str)]

        return ListingOptionsOutput(
            property_types=_named(_as_list(d.get("property_types"))),
            amenities=_named(_as_list(d.get("amenities")))[:MAX_LOCATIONS],
            rental_types=strs(d.get("rental_types")),
            booking_modes=strs(d.get("booking_modes")),
            document_types=strs(d.get("document_types")),
            bcv_rate=_num(d.get("bcv_rate")),
        )


# ── públicas (API general, sin clave) ────────────────────────────────────


def _summary(raw: dict[str, Any]) -> ListingSummary | None:
    ident = _first(raw, "id", "uuid")
    if ident is None:
        return None
    return ListingSummary(
        id=str(ident),
        slug=_str(raw.get("slug")),
        title=_str(raw.get("title")),
        city=_location(raw, "city"),
        state=_location(raw, "state"),
        rental_type=_str(raw.get("rental_type")),
        price=_num(_first(raw, "price_per_night", "priceUSDT", "price")),
        currency=_str(raw.get("currency")),
        max_guests=_int(raw.get("max_guests")),
        rating=_num(_first(raw, "rating", "average_rating", "rating_avg")),
    )


class SearchListings(_QuedateTool):
    name = "quedate.search_listings"
    description = (
        "Search Quédate's published stays by free text, city, state, dates (YYYY-MM-DD), "
        "guests, property type, price per night and rental type. Up to 10 results."
    )
    input_model = SearchListingsInput
    output_model = SearchListingsOutput

    async def run(self, payload: SearchListingsInput) -> SearchListingsOutput:  # type: ignore[override]
        _, conn = await self._connected()
        params = {k: v for k, v in payload.model_dump(mode="json").items() if v is not None}
        try:
            body = await _client(conn, public=True).search_listings(params)
        except QuedateError as exc:
            raise _friendly(exc) from exc
        rows, total, _p, _l = _page(body)
        items = [s for s in (_summary(r) for r in rows[:MAX_ITEMS]) if s is not None]
        total = total if total is not None else len(rows)
        return SearchListingsOutput(items=items, total=total, truncated=total > len(items))


class GetListing(_QuedateTool):
    name = "quedate.get_listing"
    description = (
        "Public details of one Quédate stay by id or slug, with the dates that are not "
        "available. Never includes the host's contact data."
    )
    input_model = GetListingInput
    output_model = ListingDetail

    async def run(self, payload: GetListingInput) -> ListingDetail:  # type: ignore[override]
        _, conn = await self._connected()
        try:
            body = await _client(conn, public=True).public_listing(payload.listing)
        except QuedateError as exc:
            raise _friendly(exc) from exc
        raw = _as_dict(_data(body))
        if _first(raw, "id", "uuid") is None:
            raise ToolError("Quédate no devolvió ese anuncio.")
        description = _str(raw.get("description"))
        amenities = [a for a in (_str(x) for x in _as_list(raw.get("amenities"))) if a][
            :MAX_AMENITIES
        ]
        dates = [
            d
            for d in _as_list(_first(raw, "unavailableDates", "unavailable_dates"))
            if isinstance(d, str)
        ]
        return ListingDetail(
            id=str(_first(raw, "id", "uuid")),
            slug=_str(raw.get("slug")),
            title=_str(raw.get("title")),
            description=description[:MAX_DESCRIPTION] if description else None,
            property_type=_str(_first(raw, "property_type", "propertyType")),
            city=_location(raw, "city"),
            state=_location(raw, "state"),
            rental_type=_str(raw.get("rental_type")),
            price=_num(_first(raw, "price_per_night", "priceUSDT", "price")),
            currency=_str(raw.get("currency")),
            max_guests=_int(raw.get("max_guests")),
            bedrooms=_int(raw.get("bedrooms")),
            beds=_int(raw.get("beds")),
            bathrooms=_num(raw.get("bathrooms")),
            booking_mode=_str(raw.get("booking_mode")),
            min_nights=_int(raw.get("min_nights")),
            max_nights=_int(raw.get("max_nights")),
            check_in_time=_str(raw.get("check_in_time")),
            check_out_time=_str(raw.get("check_out_time")),
            amenities=amenities,
            unavailable_dates=dates[:MAX_UNAVAILABLE_DATES],
            unavailable_dates_truncated=len(dates) > MAX_UNAVAILABLE_DATES,
            host_name=_str(_as_dict(raw.get("host")).get("name")),
        )


class QuoteStay(_QuedateTool):
    name = "quedate.quote_stay"
    description = (
        "Price a stay in a Quédate listing: total in USD and VES with the BCV rate. If the "
        "dates are taken or the guests exceed capacity, available=false with Quédate's message. "
        "The listing_id comes from quedate.search_listings."
    )
    input_model = QuoteStayInput
    output_model = QuoteStayOutput

    async def run(self, payload: QuoteStayInput) -> QuoteStayOutput:  # type: ignore[override]
        _, conn = await self._connected()
        if payload.check_out <= payload.check_in:
            return QuoteStayOutput(
                available=False, message="La salida debe ser después de la entrada."
            )
        try:
            body = await _client(conn, public=True).quote(
                listing_id=payload.listing_id,
                check_in=payload.check_in.isoformat(),
                check_out=payload.check_out.isoformat(),
                guests=payload.guests,
            )
        except (QuedateConflict, QuedateValidationError) as exc:
            return QuoteStayOutput(available=False, message=str(exc))
        except QuedateError as exc:
            raise _friendly(exc) from exc
        raw = _as_dict(_data(body))
        return QuoteStayOutput(
            available=True,
            nights=_int(_first(raw, "nights", "noches", "nights_count")),
            total_usd=_num(_first(raw, "total_usd", "totalUSD")),
            total_ves=_num(_first(raw, "total_ves", "totalVES")),
            bcv_rate=_num(_first(raw, "bcv_rate", "exchange_rate", "rate")),
        )


class BookingSettings(_QuedateTool):
    name = "quedate.booking_settings"
    description = "How booking works in Quédate now ('immediate' or 'request') and Quédate's support WhatsApp."
    input_model = _Empty
    output_model = BookingSettingsOutput

    async def run(self, payload: _Empty) -> BookingSettingsOutput:  # type: ignore[override]
        _, conn = await self._connected()
        try:
            body = await _client(conn, public=True).public_settings()
        except QuedateError as exc:
            raise _friendly(exc) from exc
        raw = _as_dict(_data(body))
        charge = raw.get("nightly_charge_enabled")
        if isinstance(charge, str):
            charge = charge.strip().lower() == "true"
        return BookingSettingsOutput(
            booking_mode=("immediate" if charge else "request")
            if isinstance(charge, bool)
            else None,
            support_whatsapp=_str(raw.get("support_whatsapp")),
        )


# ── fotos de la conversación ─────────────────────────────────────────────


class RecentPhotos(_QuedateTool):
    name = "quedate.recent_photos"
    description = (
        "The photos the person you are talking to sent in this conversation in the last 24 "
        "hours (up to 20), each with a photo_id and when it was sent. Ask them which ones to "
        "use: an uploaded photo cannot be removed from Quédate."
    )
    input_model = _Empty
    output_model = RecentPhotosOutput

    async def run(self, payload: _Empty) -> RecentPhotosOutput:  # type: ignore[override]
        tenant_id, _ = await self._connected()
        customer = current_customer_or_refuse("ver sus fotos")
        found = await photo_source.source().recent(tenant_id, customer)
        if not found:
            return RecentPhotosOutput(
                photos=[], message="La persona no ha mandado fotos en las últimas 24 horas."
            )
        return RecentPhotosOutput(
            photos=[RecentPhoto(photo_id=p.photo_id, sent_at=p.sent_at.isoformat()) for p in found]
        )


# ── de la persona que escribe ────────────────────────────────────────────


class _PersonTool(_QuedateTool):
    async def _person(self, what: str) -> tuple[uuid.UUID, Connection, uuid.UUID]:
        tenant_id, conn = await self._connected()
        return tenant_id, conn, current_customer_or_refuse(what)

    async def _linked(self, tenant_id: uuid.UUID, customer_id: uuid.UUID) -> Link:
        link = await store().load(tenant_id, customer_id)
        if link is None:
            raise ToolError(_REGISTER_FIRST)
        if link.needs_review:
            raise ToolError(_REVIEW)
        return link

    async def _call(
        self, tenant_id: uuid.UUID, customer_id: uuid.UUID, call: Awaitable[Any]
    ) -> Any:
        """Una llamada sobre el anfitrión de la persona. Un 403 marca el vínculo (3.10)."""
        try:
            return await call
        except QuedateForbidden as exc:
            await store().mark_review(tenant_id, customer_id)
            log.warning("quedate.linked_host_forbidden", tenant_id=str(tenant_id))
            raise ToolError(_REVIEW) from exc
        except QuedateError as exc:
            raise _friendly(exc) from exc

    async def _own_listing(
        self,
        conn: Connection,
        tenant_id: uuid.UUID,
        customer_id: uuid.UUID,
        link: Link,
        listing_id: str,
    ) -> dict[str, Any]:
        """El anuncio, si es del anfitrión vinculado (4.5). Si no, nada se escribe."""
        client = _client(conn)
        row = await self._call(
            tenant_id,
            customer_id,
            _scan(
                lambda p: client.list_listings(page=p, per_page=SCAN_PER_PAGE),
                lambda r: str(r.get("id")) == listing_id,
            ),
        )
        if row is None or str(_first(row, "user_id", "host_id")) != link.host_id:
            raise ToolError("Ese anuncio no es de esta persona.")
        return dict(row)


class RegisterMe(_PersonTool):
    name = "quedate.register_me"
    description = (
        "Sign up the person you are talking to as a host on Quédate. Ask for first and last "
        "name, email, identity document (CI with V- or E-, PASAPORTE or RIF) and number, date "
        "of birth, sex and nationality (VEN by default). READ THE EMAIL BACK and pass "
        "email_confirmed=true only after they confirm it. Their phone is taken from this "
        "chat. If they are already linked, nothing is created."
    )
    input_model = RegisterMeInput
    output_model = RegisterMeOutput
    side_effects: ClassVar[tuple[str, ...]] = ("mutates_db",)

    async def run(self, payload: RegisterMeInput) -> RegisterMeOutput:  # type: ignore[override]
        tenant_id, conn, customer = await self._person("darla de alta en Quédate")
        if not payload.email_confirmed:
            return RegisterMeOutput(
                registered=False,
                message="Antes de darla de alta, lee el correo a la persona y espera su confirmación.",
            )
        st = store()
        async with st.lock(tenant_id, customer):
            existing = await st.load(tenant_id, customer)
            if existing is not None and not existing.needs_review:
                return RegisterMeOutput(
                    registered=False,
                    already_linked=True,
                    next_step="Ya es anfitriona. Consulta su estado con quedate.my_host.",
                )
            phone = await st.customer_phone(tenant_id, customer)
            body_in = _host_payload(payload, email=payload.email, phone=phone)
            client = _client(conn, retries=0)
            try:
                body = await client.create_host(body_in)
            except QuedateValidationError as exc:
                if exc.field != "email":
                    return RegisterMeOutput(
                        registered=False, rejected_field=exc.field, message=str(exc)
                    )
                return await self._link_existing(conn, tenant_id, customer, payload.email, phone)
            except QuedateUnavailable as exc:
                await _audit_failed(tenant_id, customer)
                raise ToolError(
                    "Quédate no respondió a tiempo y puede que la haya dado de alta. Vuelve a "
                    "intentarlo en unos minutos: si ya existe, se vinculará."
                ) from exc
            except QuedateError as exc:
                raise _friendly(exc) from exc
            host = _as_dict(_data(body))
            host_id = host.get("id")
            if host_id is None:
                await _audit_failed(tenant_id, customer)
                raise ToolError("Quédate no devolvió el anfitrión creado.")
            await _save_link(tenant_id, customer, str(host_id))
            return RegisterMeOutput(
                registered=True,
                kyc_verified=_bool(host.get("kyc_verified")),
                next_step=(
                    "Ya es anfitriona. Falta verificar su identidad: quedate.my_verification_link, "
                    "o quedate.upload_my_identity con las fotos de su documento."
                ),
            )

    async def _link_existing(
        self,
        conn: Connection,
        tenant_id: uuid.UUID,
        customer: uuid.UUID,
        email: str,
        phone: str | None,
    ) -> RegisterMeOutput:
        """Correo tomado (3.5). Se vincula el anfitrión de esta clave con ese correo
        **solo** si su teléfono es el del chat y nadie más del negocio lo tiene: el
        correo lo puede decir cualquiera; el teléfono sale del canal (/cso del
        2026-11-16)."""
        refused = RegisterMeOutput(registered=False, rejected_field="email", message=_EMAIL_TAKEN)
        client = _client(conn)
        try:
            row = await _scan(
                lambda p: client.list_hosts(page=p, per_page=SCAN_PER_PAGE),
                lambda r: str(r.get("email") or "").casefold() == email.casefold(),
            )
        except QuedateError as exc:
            raise _friendly(exc) from exc
        if row is None or row.get("id") is None:
            return refused
        host_id = str(row["id"])
        if not _same_phone(phone, row.get("phone")) or await store().linked_to_other(
            tenant_id, customer, host_id
        ):
            log.warning("quedate.email_taken_not_linked", tenant_id=str(tenant_id))
            return refused
        await _save_link(tenant_id, customer, host_id)
        return RegisterMeOutput(
            registered=True,
            linked_existing=True,
            kyc_verified=_bool(row.get("kyc_verified")),
            next_step="Ya tenía cuenta de anfitriona con este negocio: queda vinculada.",
        )


def _digits(value: Any) -> str:
    return "".join(c for c in str(value or "") if c.isdigit())


def _same_phone(ours: str | None, theirs: Any) -> bool:
    """Los mismos últimos dígitos (hasta 10). Menos de 7 no prueba nada."""
    a, b = _digits(ours), _digits(theirs)
    if len(a) < 7 or len(b) < 7:
        return False
    n = min(len(a), len(b), 10)
    return a[-n:] == b[-n:]


async def _save_link(tenant_id: uuid.UUID, customer: uuid.UUID, host_id: str) -> None:
    try:
        await store().save(tenant_id, customer, host_id=host_id)
    except Exception as exc:
        log.error("quedate.link_save_failed", tenant_id=str(tenant_id))
        await _audit_failed(tenant_id, customer)
        raise ToolError(
            "La anfitriona quedó dada de alta en Quédate, pero no pude vincularla aquí. "
            "Vuelve a intentarlo: se vinculará la que ya existe."
        ) from exc


async def _audit_failed(tenant_id: uuid.UUID, customer: uuid.UUID) -> None:
    try:
        await store().audit(tenant_id, customer, "connector.customer_account_link_failed")
    except Exception:
        log.error("quedate.link_failed_audit_failed", tenant_id=str(tenant_id))


class MyHost(_PersonTool):
    name = "quedate.my_host"
    description = (
        "The Quédate host account of the person you are talking to: whether they are linked, "
        "their name, identity verification status and how many listings they have."
    )
    input_model = _Empty
    output_model = MyHostOutput

    async def run(self, payload: _Empty) -> MyHostOutput:  # type: ignore[override]
        tenant_id, conn, customer = await self._person("consultar su cuenta de anfitriona")
        link = await store().load(tenant_id, customer)
        if link is None:
            return MyHostOutput(linked=False, next_step=_REGISTER_FIRST)
        if link.needs_review:
            return MyHostOutput(linked=True, needs_review=True, next_step=_REVIEW)
        body = await self._call(tenant_id, customer, _client(conn).get_host(link.host_id))
        host = _as_dict(_data(body))
        listings = _as_list(host.get("listings"))
        return MyHostOutput(
            linked=True,
            name=_str(host.get("name")),
            kyc_verified=_bool(host.get("kyc_verified")),
            kyc_document_status=_str(host.get("kyc_document_status")),
            kyc_selfie_status=_str(host.get("kyc_selfie_status")),
            listings_count=_int(host.get("listings_count"))
            if host.get("listings_count") is not None
            else len(listings),
        )


class MyVerificationLink(_PersonTool):
    name = "quedate.my_verification_link"
    description = (
        "The Quédate link the person you are talking to opens on their phone to verify their "
        "identity. It lasts 7 days; the same link is returned while it is valid."
    )
    input_model = _Empty
    output_model = VerificationLinkOutput
    side_effects: ClassVar[tuple[str, ...]] = ("mutates_db",)

    async def run(self, payload: _Empty) -> VerificationLinkOutput:  # type: ignore[override]
        tenant_id, conn, customer = await self._person("pedir su enlace de verificación")
        st = store()
        async with st.lock(tenant_id, customer):
            link = await self._linked(tenant_id, customer)
            last = _as_dict(link.state.get("verification_link"))
            expires = last.get("expires_at")
            if isinstance(last.get("url"), str) and isinstance(expires, str):
                try:
                    if datetime.fromisoformat(expires) - datetime.now(UTC) > LINK_MARGIN:
                        return VerificationLinkOutput(
                            url=last["url"], reused=True, expires_at=expires
                        )
                except ValueError:
                    pass
            body = await self._call(tenant_id, customer, _client(conn).kyc_link(link.host_id))
            return await _link_out(tenant_id, customer, link, body)


async def _link_out(
    tenant_id: uuid.UUID, customer: uuid.UUID | None, link: Link | None, body: Any
) -> VerificationLinkOutput:
    d = _as_dict(_data(body))
    url = _str(_first(d, "kyc_url", "url"))
    if not url or not url.startswith("https://"):
        raise ToolError("Quédate no devolvió un enlace de verificación.")
    days = _int(d.get("expires_in_days")) or 7
    expires = (datetime.now(UTC) + timedelta(days=days)).isoformat()
    if link is not None and customer is not None:
        state = dict(link.state)
        state["verification_link"] = {"url": url, "expires_at": expires}
        await store().save_state(tenant_id, customer, state)
    return VerificationLinkOutput(url=url, reused=False, expires_at=expires)


async def _upload_identity(
    client: QuedateClient,
    tenant_id: uuid.UUID,
    customer: uuid.UUID,
    host_id: str,
    document_photo_id: str,
    selfie_photo_id: str | None,
) -> Awaitable[Any]:
    ids = [document_photo_id] + ([selfie_photo_id] if selfie_photo_id else [])
    files = await photo_source.chosen(tenant_id, customer, ids)
    return client.upload_kyc(
        host_id, document=files[0], selfie=files[1] if len(files) > 1 else None
    )


def _identity_out(body: Any) -> IdentityOutput:
    d = _as_dict(_data(body))
    return IdentityOutput(
        uploaded=True,
        kyc_document_status=_str(d.get("kyc_document_status")),
        kyc_selfie_status=_str(d.get("kyc_selfie_status")),
        message=_str(_as_dict(body).get("message")),
    )


class UploadMyIdentity(_PersonTool):
    name = "quedate.upload_my_identity"
    description = (
        "Upload the photo of the identity document (required) and a selfie (optional) of the "
        "person you are talking to, chosen by photo_id from quedate.recent_photos after they "
        "tell you which ones. Quédate reviews them."
    )
    input_model = UploadMyIdentityInput
    output_model = IdentityOutput
    side_effects: ClassVar[tuple[str, ...]] = ("mutates_db",)

    async def run(self, payload: UploadMyIdentityInput) -> IdentityOutput:  # type: ignore[override]
        tenant_id, conn, customer = await self._person("subir su documento")
        async with store().lock(tenant_id, customer):
            link = await self._linked(tenant_id, customer)
            call = await _upload_identity(
                _client(conn, retries=0),
                tenant_id,
                customer,
                link.host_id,
                payload.document_photo_id,
                payload.selfie_photo_id,
            )
            try:
                body = await self._call(tenant_id, customer, call)
            except ToolError as exc:
                if isinstance(exc.__cause__, QuedateUnavailable):
                    await _unconfirmed(tenant_id, "upload_identity")
                raise
            return _identity_out(body)


class CreateMyListing(_PersonTool):
    name = "quedate.create_my_listing"
    description = (
        "Create a draft listing for the person you are talking to, with property type and "
        "sector ids from quedate.listing_options and quedate.list_locations. Then add photos "
        "and send it to Quédate's review. Not retried: Quédate does not delete."
    )
    input_model = CreateMyListingInput
    output_model = ListingWriteOutput
    side_effects: ClassVar[tuple[str, ...]] = ("mutates_db",)

    async def run(self, payload: CreateMyListingInput) -> ListingWriteOutput:  # type: ignore[override]
        tenant_id, conn, customer = await self._person("crear su anuncio")
        async with store().lock(tenant_id, customer):
            link = await self._linked(tenant_id, customer)
            try:
                body = await self._call(
                    tenant_id,
                    customer,
                    _client(conn, retries=0).create_listing(
                        _listing_payload(payload, link.host_id)
                    ),
                )
            except ToolError as exc:
                if isinstance(exc.__cause__, QuedateUnavailable):
                    await _unconfirmed(tenant_id, "create_listing")
                    raise ToolError(_UNCONFIRMED) from exc
                raise
            return _write_out(body)


def _write_out(body: Any) -> ListingWriteOutput:
    d = _as_dict(_data(body))
    return ListingWriteOutput(
        listing_id=str(d.get("id")),
        status=_str(d.get("status")),
        message=_str(_as_dict(body).get("message")),
    )


async def _send_photos(
    client: QuedateClient,
    tenant_id: uuid.UUID,
    customer: uuid.UUID,
    listing_id: str,
    photo_ids: list[str],
) -> Awaitable[Any]:
    files = await photo_source.chosen(tenant_id, customer, photo_ids)
    return client.upload_media(listing_id, files)


def _photos_out(listing_id: str, body: Any) -> PhotosOutput:
    d = _as_dict(_data(body))
    return PhotosOutput(
        listing_id=listing_id,
        total_photos=_int(d.get("total_photos")),
        message=_str(_as_dict(body).get("message")),
    )


class AddMyListingPhotos(_PersonTool):
    name = "quedate.add_my_listing_photos"
    description = (
        "Upload to a listing of the person you are talking to the photos they chose, by "
        "photo_id from quedate.recent_photos (1 to 20). A photo cannot be removed later."
        " If you do not have its listing_id from this same turn, find it with quedate.my_listings first."
    )
    input_model = ListingPhotosInput
    output_model = PhotosOutput
    side_effects: ClassVar[tuple[str, ...]] = ("mutates_db",)

    async def run(self, payload: ListingPhotosInput) -> PhotosOutput:  # type: ignore[override]
        tenant_id, conn, customer = await self._person("subir fotos a su anuncio")
        async with store().lock(tenant_id, customer):
            link = await self._linked(tenant_id, customer)
            await self._own_listing(conn, tenant_id, customer, link, payload.listing_id)
            call = await _send_photos(
                _client(conn, retries=0), tenant_id, customer, payload.listing_id, payload.photo_ids
            )
            try:
                body = await self._call(tenant_id, customer, call)
            except ToolError as exc:
                if isinstance(exc.__cause__, QuedateUnavailable):
                    await _unconfirmed(tenant_id, "upload_photos")
                    raise ToolError(_UNCONFIRMED) from exc
                raise
            return _photos_out(payload.listing_id, body)


class _MyStatusTool(_PersonTool):
    target: ClassVar[ListingStatus]
    side_effects: ClassVar[tuple[str, ...]] = ("mutates_db",)
    input_model = ListingRefInput
    output_model = StatusOutput

    async def run(self, payload: ListingRefInput) -> StatusOutput:  # type: ignore[override]
        tenant_id, conn, customer = await self._person("cambiar su anuncio")
        async with store().lock(tenant_id, customer):
            link = await self._linked(tenant_id, customer)
            await self._own_listing(conn, tenant_id, customer, link, payload.listing_id)
            body = await self._call(
                tenant_id,
                customer,
                _client(conn, retries=0).set_status(payload.listing_id, self.target),
            )
            return _status_out(payload.listing_id, self.target, body)


def _status_out(listing_id: str, target: str, body: Any) -> StatusOutput:
    d = _as_dict(_data(body))
    status = _str(d.get("status")) or target
    message = (
        "Enviado a revisión de Quédate: lo publicarán cuando lo aprueben."
        if status == "pending_approval"
        else "Anuncio oculto: ya no se muestra."
    )
    return StatusOutput(listing_id=listing_id, status=status, message=message)


class SubmitMyListing(_MyStatusTool):
    name = "quedate.submit_my_listing"
    description = (
        "Send a listing of the person you are talking to to Quédate's review "
        "(pending_approval). Quédate publishes it when approved; this tool never publishes."
        " If you do not have its listing_id from this same turn, find it with quedate.my_listings first."
    )
    target = "pending_approval"


class HideMyListing(_MyStatusTool):
    name = "quedate.hide_my_listing"
    description = (
        "Hide a listing of the person you are talking to (status hidden). Quédate does not "
        "delete listings."
        " If you do not have its listing_id from this same turn, find it with quedate.my_listings first."
    )
    target = "hidden"


class MyListings(_PersonTool):
    name = "quedate.my_listings"
    description = (
        "The Quédate listings of the person you are talking to, with their id, status and "
        "price. Only theirs. Use it to find the listing_id before adding photos, sending it "
        "to review or hiding it."
    )
    input_model = _Empty
    output_model = MyListingsOutput

    async def run(self, payload: _Empty) -> MyListingsOutput:  # type: ignore[override]
        tenant_id, conn, customer = await self._person("consultar sus anuncios")
        link = await store().load(tenant_id, customer)
        if link is None:
            return MyListingsOutput(linked=False, next_step=_REGISTER_FIRST)
        if link.needs_review:
            raise ToolError(_REVIEW)
        client = _client(conn)
        mine: list[dict[str, Any]] = []

        async def collect() -> None:
            for page in range(1, SCAN_MAX_PAGES + 1):
                rows, _t, _p, last = _page(
                    await client.list_listings(page=page, per_page=SCAN_PER_PAGE)
                )
                mine.extend(r for r in rows if str(_first(r, "user_id", "host_id")) == link.host_id)
                if not rows or (last is not None and page >= last):
                    return

        await self._call(tenant_id, customer, collect())
        return MyListingsOutput(
            linked=True, items=[_brief(r) for r in mine[:MAX_ITEMS]], total=len(mine)
        )


# ── de equipo (cualquier anfitrión de la clave) ──────────────────────────


class _TeamTool(_QuedateTool):
    async def _do(self, call: Awaitable[Any]) -> Any:
        try:
            return await call
        except QuedateError as exc:
            raise _friendly(exc) from exc


class ListHosts(_TeamTool):
    name = "quedate.list_hosts"
    description = "All hosts this business's Quédate key created, 10 per page, with their verification status."
    input_model = PageInput
    output_model = HostsOutput

    async def run(self, payload: PageInput) -> HostsOutput:  # type: ignore[override]
        _, conn = await self._connected()
        body = await self._do(_client(conn).list_hosts(page=payload.page, per_page=MAX_ITEMS))
        rows, total, page, last = _page(body)
        return HostsOutput(
            items=[
                HostBrief(
                    id=str(r.get("id")),
                    name=_str(r.get("name")),
                    email=_str(r.get("email")),
                    kyc_verified=_bool(r.get("kyc_verified")),
                    listings_count=_int(r.get("listings_count")),
                )
                for r in rows[:MAX_ITEMS]
                if r.get("id") is not None
            ],
            total=total,
            page=page,
            last_page=last,
        )


class GetHost(_TeamTool):
    name = "quedate.get_host"
    description = (
        "One host of this business's Quédate key: contact, verification status and listings."
    )
    input_model = HostRefInput
    output_model = HostDetailOutput

    async def run(self, payload: HostRefInput) -> HostDetailOutput:  # type: ignore[override]
        _, conn = await self._connected()
        host = _as_dict(_data(await self._do(_client(conn).get_host(payload.host_id))))
        return HostDetailOutput(
            id=str(host.get("id") or payload.host_id),
            name=_str(host.get("name")),
            email=_str(host.get("email")),
            phone=_str(host.get("phone")),
            document_type=_str(host.get("document_type")),
            kyc_verified=_bool(host.get("kyc_verified")),
            kyc_document_status=_str(host.get("kyc_document_status")),
            kyc_selfie_status=_str(host.get("kyc_selfie_status")),
            listings=[
                _brief(r) for r in _as_list(host.get("listings"))[:MAX_ITEMS] if isinstance(r, dict)
            ],
        )


class CreateHost(_TeamTool):
    name = "quedate.create_host"
    description = (
        "Create a Quédate host for someone else (team use): name, email, phone, identity "
        "document (CI with V- or E-, PASAPORTE or RIF), date of birth, sex and nationality "
        "(VEN by default). If the email already belongs to a host of this key, returns it."
    )
    input_model = CreateHostInput
    output_model = CreateHostOutput
    side_effects: ClassVar[tuple[str, ...]] = ("mutates_db",)

    async def run(self, payload: CreateHostInput) -> CreateHostOutput:  # type: ignore[override]
        tenant_id, conn = await self._connected()
        client = _client(conn, retries=0)
        try:
            body = await client.create_host(
                _host_payload(payload, email=payload.email, phone=payload.phone)
            )
        except QuedateValidationError as exc:
            if exc.field == "email":
                row = await self._do(
                    _scan(
                        lambda p: _client(conn).list_hosts(page=p, per_page=SCAN_PER_PAGE),
                        lambda r: str(r.get("email") or "").casefold() == payload.email.casefold(),
                    )
                )
                if row is not None:
                    return CreateHostOutput(
                        created=False, already_existed=True, host_id=str(row.get("id"))
                    )
            return CreateHostOutput(created=False, rejected_field=exc.field, message=str(exc))
        except QuedateUnavailable as exc:
            await _unconfirmed(tenant_id, "create_host")
            raise ToolError(
                "Quédate no respondió y puede que lo haya creado. Compruébalo con "
                "quedate.list_hosts antes de repetir."
            ) from exc
        except QuedateError as exc:
            raise _friendly(exc) from exc
        host = _as_dict(_data(body))
        return CreateHostOutput(
            created=True, host_id=str(host.get("id")) if host.get("id") else None
        )


class HostVerificationLink(_TeamTool):
    name = "quedate.host_verification_link"
    description = "The identity verification link of a host of this key, to send to that person. Lasts 7 days."
    input_model = HostRefInput
    output_model = VerificationLinkOutput
    side_effects: ClassVar[tuple[str, ...]] = ("mutates_db",)

    async def run(self, payload: HostRefInput) -> VerificationLinkOutput:  # type: ignore[override]
        tenant_id, conn = await self._connected()
        body = await self._do(_client(conn).kyc_link(payload.host_id))
        return await _link_out(tenant_id, None, None, body)


class UploadHostIdentity(_TeamTool):
    name = "quedate.upload_host_identity"
    description = (
        "Upload the identity document photo (required) and selfie (optional) of a host of this "
        "key, chosen by photo_id from quedate.recent_photos of this conversation."
    )
    input_model = UploadHostIdentityInput
    output_model = IdentityOutput
    side_effects: ClassVar[tuple[str, ...]] = ("mutates_db",)

    async def run(self, payload: UploadHostIdentityInput) -> IdentityOutput:  # type: ignore[override]
        tenant_id, conn = await self._connected()
        customer = current_customer_or_refuse("subir fotos de esta conversación")
        call = await _upload_identity(
            _client(conn, retries=0),
            tenant_id,
            customer,
            payload.host_id,
            payload.document_photo_id,
            payload.selfie_photo_id,
        )
        try:
            body = await self._do(call)
        except ToolError as exc:
            if isinstance(exc.__cause__, QuedateUnavailable):
                await _unconfirmed(tenant_id, "upload_identity")
            raise
        return _identity_out(body)


class ListListings(_TeamTool):
    name = "quedate.list_listings"
    description = (
        "All listings of this business's Quédate key, 10 per page, optionally of one host."
    )
    input_model = ListListingsInput
    output_model = ListingsOutput

    async def run(self, payload: ListListingsInput) -> ListingsOutput:  # type: ignore[override]
        _, conn = await self._connected()
        client = _client(conn)
        if payload.host_id is None:
            rows, total, page, last = _page(
                await self._do(client.list_listings(page=payload.page, per_page=MAX_ITEMS))
            )
            return ListingsOutput(
                items=[_managed(r) for r in rows[:MAX_ITEMS]],
                total=total,
                page=page,
                last_page=last,
            )
        # Quédate ignora el filtro por anfitrión: se filtra aquí.
        matched: list[dict[str, Any]] = []
        for p in range(1, SCAN_MAX_PAGES + 1):
            rows, _t, _pg, last = _page(
                await self._do(client.list_listings(page=p, per_page=SCAN_PER_PAGE))
            )
            matched.extend(
                r for r in rows if str(_first(r, "user_id", "host_id")) == payload.host_id
            )
            if not rows or (last is not None and p >= last):
                break
        start = (payload.page - 1) * MAX_ITEMS
        pages = max(1, -(-len(matched) // MAX_ITEMS))
        return ListingsOutput(
            items=[_managed(r) for r in matched[start : start + MAX_ITEMS]],
            total=len(matched),
            page=payload.page,
            last_page=pages,
        )


class GetManagedListing(_TeamTool):
    name = "quedate.get_managed_listing"
    description = (
        "One listing of this business's Quédate key, with its status and host."
        " If you do not have its listing_id from this same turn, find it with quedate.list_listings first."
    )
    input_model = ListingRefInput
    output_model = ManagedListingDetail

    async def run(self, payload: ListingRefInput) -> ManagedListingDetail:  # type: ignore[override]
        _, conn = await self._connected()
        raw = _as_dict(_data(await self._do(_client(conn).get_listing_managed(payload.listing_id))))
        base = _managed({**raw, "id": raw.get("id") or payload.listing_id})
        return ManagedListingDetail(
            **base.model_dump(),
            rental_type=_str(raw.get("rental_type")),
            booking_mode=_str(raw.get("booking_mode")),
            max_guests=_int(raw.get("max_guests")),
            street_address=_str(raw.get("street_address")),
        )


class CreateListing(_TeamTool):
    name = "quedate.create_listing"
    description = (
        "Create a draft listing for a host of this key (team use), with property type and "
        "sector ids from the catalog. Not retried: Quédate does not delete."
    )
    input_model = CreateListingInput
    output_model = ListingWriteOutput
    side_effects: ClassVar[tuple[str, ...]] = ("mutates_db",)

    async def run(self, payload: CreateListingInput) -> ListingWriteOutput:  # type: ignore[override]
        tenant_id, conn = await self._connected()
        try:
            body = await _client(conn, retries=0).create_listing(
                _listing_payload(payload, payload.host_id)
            )
        except QuedateUnavailable as exc:
            await _unconfirmed(tenant_id, "create_listing")
            raise ToolError(_UNCONFIRMED) from exc
        except QuedateError as exc:
            raise _friendly(exc) from exc
        return _write_out(body)


class AddListingPhotos(_TeamTool):
    name = "quedate.add_listing_photos"
    description = (
        "Upload to a listing of this key the photos chosen by photo_id from "
        "quedate.recent_photos of this conversation (1 to 20). Photos cannot be removed later."
        " If you do not have its listing_id from this same turn, find it with quedate.list_listings first."
    )
    input_model = ListingPhotosInput
    output_model = PhotosOutput
    side_effects: ClassVar[tuple[str, ...]] = ("mutates_db",)

    async def run(self, payload: ListingPhotosInput) -> PhotosOutput:  # type: ignore[override]
        tenant_id, conn = await self._connected()
        customer = current_customer_or_refuse("subir fotos de esta conversación")
        call = await _send_photos(
            _client(conn, retries=0), tenant_id, customer, payload.listing_id, payload.photo_ids
        )
        try:
            body = await call
        except QuedateUnavailable as exc:
            await _unconfirmed(tenant_id, "upload_photos")
            raise ToolError(_UNCONFIRMED) from exc
        except QuedateError as exc:
            raise _friendly(exc) from exc
        return _photos_out(payload.listing_id, body)


class _TeamStatusTool(_TeamTool):
    target: ClassVar[ListingStatus]
    side_effects: ClassVar[tuple[str, ...]] = ("mutates_db",)
    input_model = ListingRefInput
    output_model = StatusOutput

    async def run(self, payload: ListingRefInput) -> StatusOutput:  # type: ignore[override]
        _, conn = await self._connected()
        body = await self._do(_client(conn, retries=0).set_status(payload.listing_id, self.target))
        return _status_out(payload.listing_id, self.target, body)


class SubmitListing(_TeamStatusTool):
    name = "quedate.submit_listing"
    description = (
        "Send a listing of this key to Quédate's review (pending_approval). This tool never "
        "publishes."
        " If you do not have its listing_id from this same turn, find it with quedate.list_listings first."
    )
    target = "pending_approval"


class HideListing(_TeamStatusTool):
    name = "quedate.hide_listing"
    description = (
        "Hide a listing of this key (status hidden). Quédate does not delete listings."
        " If you do not have its listing_id from this same turn, find it with quedate.list_listings first."
    )
    target = "hidden"


QUEDATE_TOOLS: tuple[type[ToolBase], ...] = (
    # catálogo y públicas
    ListLocations,
    ListingOptions,
    SearchListings,
    GetListing,
    QuoteStay,
    BookingSettings,
    # fotos de la conversación
    RecentPhotos,
    # de la persona que escribe
    RegisterMe,
    MyHost,
    MyVerificationLink,
    UploadMyIdentity,
    CreateMyListing,
    AddMyListingPhotos,
    SubmitMyListing,
    HideMyListing,
    MyListings,
    # de equipo
    ListHosts,
    GetHost,
    CreateHost,
    HostVerificationLink,
    UploadHostIdentity,
    ListListings,
    GetManagedListing,
    CreateListing,
    AddListingPhotos,
    SubmitListing,
    HideListing,
)

#: Las que actúan sobre la persona del turno (garantía 8): ninguna acepta ``host_id``.
PERSON_TOOLS = frozenset(
    t.name
    for t in (
        RecentPhotos,
        RegisterMe,
        MyHost,
        MyVerificationLink,
        UploadMyIdentity,
        CreateMyListing,
        AddMyListingPhotos,
        SubmitMyListing,
        HideMyListing,
        MyListings,
    )
)

__all__ = ["PERSON_TOOLS", "QUEDATE_TOOLS", "set_test_client_factory"]
