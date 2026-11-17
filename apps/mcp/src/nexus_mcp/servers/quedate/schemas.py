"""Entradas y salidas de las herramientas ``quedate.*`` (spec 061, enmienda del 2026-11-16).

Ninguna entrada acepta cliente, tenant, conversación ni clave. Las de la persona no
aceptan ``host_id``: su anfitrión sale del vínculo. Las salidas llevan los campos que
el agente necesita (research D10). Las públicas y las de la persona no llevan correo,
teléfono ni documento.
"""

from __future__ import annotations

from datetime import date
from typing import Literal

from pydantic import Field

from nexus_mcp.base import InputModel, OutputModel

RentalType = Literal["nightly", "monthly"]
DocumentType = Literal["CI", "PASAPORTE", "RIF"]


class _Empty(InputModel):
    """Sin argumentos."""


# ── catálogo ─────────────────────────────────────────────────────────────


class ListLocationsInput(InputModel):
    state: str | None = Field(None, max_length=80, description="Estado, p. ej. Miranda.")
    city: str | None = Field(None, max_length=80, description="Ciudad dentro del estado.")


class Named(OutputModel):
    id: str
    name: str


class ListLocationsOutput(OutputModel):
    level: Literal["states", "cities", "sectors"]
    items: list[Named]
    truncated: bool = False
    message: str | None = None


class ListingOptionsOutput(OutputModel):
    property_types: list[Named]
    amenities: list[Named]
    rental_types: list[str]
    booking_modes: list[str]
    document_types: list[str]
    bcv_rate: float | None = None


# ── públicas (API general, sin clave) ────────────────────────────────────


class SearchListingsInput(InputModel):
    q: str | None = Field(None, max_length=120)
    city: str | None = Field(None, max_length=80)
    state: str | None = Field(None, max_length=80)
    check_in: date | None = None
    check_out: date | None = None
    guests: int | None = Field(None, ge=1, le=50)
    property_type: str | None = Field(None, max_length=60)
    min_price: float | None = Field(None, ge=0)
    max_price: float | None = Field(None, ge=0)
    rental_type: RentalType | None = None


class ListingSummary(OutputModel):
    id: str
    slug: str | None = None
    title: str | None = None
    city: str | None = None
    state: str | None = None
    rental_type: str | None = None
    price: float | None = None
    currency: str | None = None
    max_guests: int | None = None
    rating: float | None = None


class SearchListingsOutput(OutputModel):
    items: list[ListingSummary]
    total: int | None = None
    truncated: bool = False


class GetListingInput(InputModel):
    listing: str = Field(..., min_length=1, max_length=120, description="UUID o slug del anuncio.")


class ListingDetail(OutputModel):
    id: str
    slug: str | None = None
    title: str | None = None
    description: str | None = None
    property_type: str | None = None
    city: str | None = None
    state: str | None = None
    rental_type: str | None = None
    price: float | None = None
    currency: str | None = None
    max_guests: int | None = None
    bedrooms: int | None = None
    beds: int | None = None
    bathrooms: float | None = None
    booking_mode: str | None = None
    min_nights: int | None = None
    max_nights: int | None = None
    check_in_time: str | None = None
    check_out_time: str | None = None
    amenities: list[str] = Field(default_factory=list)
    unavailable_dates: list[str] = Field(default_factory=list)
    unavailable_dates_truncated: bool = False
    host_name: str | None = None


class QuoteStayInput(InputModel):
    listing_id: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description="Id del alojamiento, de quedate.search_listings. Nunca lo inventes.",
    )
    check_in: date
    check_out: date
    guests: int = Field(..., ge=1, le=50)


class QuoteStayOutput(OutputModel):
    available: bool
    nights: int | None = None
    total_usd: float | None = None
    total_ves: float | None = None
    bcv_rate: float | None = None
    message: str | None = None


class BookingSettingsOutput(OutputModel):
    booking_mode: Literal["immediate", "request"] | None = None
    support_whatsapp: str | None = None


# ── fotos de la conversación ─────────────────────────────────────────────


class RecentPhoto(OutputModel):
    photo_id: str
    sent_at: str


class RecentPhotosOutput(OutputModel):
    photos: list[RecentPhoto]
    message: str | None = None


# ── anfitriones ──────────────────────────────────────────────────────────


class _HostData(InputModel):
    first_name: str = Field(..., min_length=1, max_length=80)
    last_name: str = Field(..., min_length=1, max_length=80)
    document_type: DocumentType = Field(..., description="CI, PASAPORTE o RIF.")
    document_number: str = Field(
        ...,
        min_length=3,
        max_length=20,
        description="Para CI: V- (6 a 8 dígitos) o E- (6 a 9), p. ej. V-18234567.",
    )
    date_of_birth: date
    sex: Literal["M", "F"]
    nationality: str = Field(
        "VEN", min_length=3, max_length=3, description="ISO alfa-3, p. ej. VEN."
    )


_EMAIL = r"^[^@\s]+@[^@\s]+\.[^@\s]+$"


class RegisterMeInput(_HostData):
    email: str = Field(..., min_length=5, max_length=160, pattern=_EMAIL)
    email_confirmed: bool = Field(
        ...,
        description=(
            "true solo si le leíste el correo a la persona y confirmó que es el suyo y "
            "está bien escrito."
        ),
    )


class RegisterMeOutput(OutputModel):
    registered: bool
    already_linked: bool = False
    linked_existing: bool = False
    kyc_verified: bool | None = None
    rejected_field: str | None = None
    message: str | None = None
    next_step: str | None = None


class MyListingBrief(OutputModel):
    id: str
    title: str | None = None
    status: str | None = None
    price: float | None = None


class MyHostOutput(OutputModel):
    linked: bool
    needs_review: bool = False
    name: str | None = None
    kyc_verified: bool | None = None
    kyc_document_status: str | None = None
    kyc_selfie_status: str | None = None
    listings_count: int | None = None
    next_step: str | None = None


class VerificationLinkOutput(OutputModel):
    url: str
    reused: bool
    expires_at: str | None = None


class UploadMyIdentityInput(InputModel):
    document_photo_id: str = Field(..., min_length=1, max_length=64)
    selfie_photo_id: str | None = Field(None, min_length=1, max_length=64)


class IdentityOutput(OutputModel):
    uploaded: bool
    kyc_document_status: str | None = None
    kyc_selfie_status: str | None = None
    message: str | None = None


# ── anuncios ─────────────────────────────────────────────────────────────


class _ListingFields(InputModel):
    title: str = Field(..., min_length=3, max_length=120)
    description: str = Field(..., min_length=10, max_length=3000)
    property_type_id: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description=(
            "De quedate.listing_options, consultada en este mismo turno. Nunca lo escribas "
            "de memoria."
        ),
    )
    sector_id: str = Field(
        ...,
        min_length=1,
        max_length=64,
        description=(
            "De quedate.list_locations, consultada en este mismo turno. Nunca lo escribas "
            "de memoria."
        ),
    )
    street_address: str = Field(..., min_length=3, max_length=200)
    apartment_suite: str | None = Field(None, max_length=120)
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    price_per_night: float = Field(..., gt=0)
    max_guests: int = Field(..., ge=1, le=50)
    bedrooms: int = Field(..., ge=0, le=50)
    beds: int = Field(..., ge=0, le=100)
    bathrooms: float = Field(..., ge=0, le=50, multiple_of=0.5)
    amenities: list[str] = Field(
        default_factory=list, max_length=30, description="Nombres de quedate.listing_options."
    )


class CreateMyListingInput(_ListingFields):
    pass


class ListingWriteOutput(OutputModel):
    listing_id: str
    status: str | None = None
    message: str | None = None


_LISTING_ID = (
    "Id del anuncio. Si no lo devolvió una herramienta en este mismo turno, búscalo con "
    "quedate.my_listings (los de la persona) o quedate.list_listings (equipo); nunca lo inventes."
)


class ListingPhotosInput(InputModel):
    listing_id: str = Field(..., min_length=1, max_length=64, description=_LISTING_ID)
    photo_ids: list[str] = Field(
        ..., min_length=1, max_length=20, description="De quedate.recent_photos."
    )


class PhotosOutput(OutputModel):
    listing_id: str
    total_photos: int | None = None
    message: str | None = None


class ListingRefInput(InputModel):
    listing_id: str = Field(..., min_length=1, max_length=64, description=_LISTING_ID)


class StatusOutput(OutputModel):
    listing_id: str
    status: str
    message: str | None = None


class MyListingsOutput(OutputModel):
    linked: bool
    items: list[MyListingBrief] = Field(default_factory=list)
    total: int | None = None
    next_step: str | None = None


# ── equipo (cualquier anfitrión de la clave) ─────────────────────────────


class PageInput(InputModel):
    page: int = Field(1, ge=1, le=1000)


class HostBrief(OutputModel):
    id: str
    name: str | None = None
    email: str | None = None
    kyc_verified: bool | None = None
    listings_count: int | None = None


class HostsOutput(OutputModel):
    items: list[HostBrief]
    total: int | None = None
    page: int = 1
    last_page: int | None = None


class HostRefInput(InputModel):
    host_id: str = Field(..., min_length=1, max_length=64)


class HostDetailOutput(OutputModel):
    id: str
    name: str | None = None
    email: str | None = None
    phone: str | None = None
    document_type: str | None = None
    kyc_verified: bool | None = None
    kyc_document_status: str | None = None
    kyc_selfie_status: str | None = None
    listings: list[MyListingBrief] = Field(default_factory=list)


class CreateHostInput(_HostData):
    email: str = Field(..., min_length=5, max_length=160, pattern=_EMAIL)
    phone: str = Field(..., min_length=7, max_length=20, pattern=r"^\+?[0-9 ()-]{7,20}$")


class CreateHostOutput(OutputModel):
    created: bool
    host_id: str | None = None
    already_existed: bool = False
    rejected_field: str | None = None
    message: str | None = None


class UploadHostIdentityInput(UploadMyIdentityInput):
    host_id: str = Field(..., min_length=1, max_length=64)


class ListListingsInput(PageInput):
    host_id: str | None = Field(None, min_length=1, max_length=64)


class ManagedListing(OutputModel):
    id: str
    host_id: str | None = None
    title: str | None = None
    status: str | None = None
    price: float | None = None


class ListingsOutput(OutputModel):
    items: list[ManagedListing]
    total: int | None = None
    page: int = 1
    last_page: int | None = None


class ManagedListingDetail(ManagedListing):
    rental_type: str | None = None
    booking_mode: str | None = None
    max_guests: int | None = None
    street_address: str | None = None


class CreateListingInput(_ListingFields):
    host_id: str = Field(..., min_length=1, max_length=64)


__all__ = [n for n in dir() if not n.startswith("__")]
