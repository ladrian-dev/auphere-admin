"""La ficha del negocio: lo básico, lo que el alta deduce y lo que sugiere — spec 047, T047.

Tres cosas, y las tres son puras salvo :func:`create_profile`:

- **La deducción** (requisito 4.5). «Más ajustes» llega relleno con la zona
  horaria, el país, la moneda de los precios, la moneda de la bolsa y «Solo
  UE». Las fuentes van por este orden: el dominio de la web y el prefijo de los
  teléfonos detectados; el país del partner; el navegador. Lo que no se sabe no
  se inventa: sin país, UTC y sin moneda de precios.
- **Las sugerencias de nicho** (requisito 4.2): las de las plantillas, en los
  6 grupos de la spec 046 más «Otro», y los nichos más usados del partner. No
  restringen el texto, y pulsar una nunca sustituye lo escrito
  (:func:`merge_niche_suggestion`).
- **El alta de la ficha** (:func:`create_profile`): la fila de
  ``business_profiles``, las nueve secciones, la procedencia de cada dato
  («Escrito por {persona}») y la web y las redes.

Dos monedas que no se mezclan (research D26): la de los precios del negocio
(ISO 4217, deducida del país) y la de la bolsa (EUR o USD, la del partner).
"""

from __future__ import annotations

import re
import unicodedata
import zoneinfo
from collections.abc import Sequence
from dataclasses import dataclass
from functools import lru_cache
from typing import Final, Literal

from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.tenant_context import require_current_tenant
from nexus_api.db.models.business import (
    INFO_MAX,
    NICHE_MAX,
    NICHE_MIN,
    BusinessFieldProvenance,
    BusinessLink,
    BusinessProfile,
)
from nexus_api.services.business.links import DetectedLink
from nexus_api.services.business.sections import Actor, init_sections

NAME_MIN, NAME_MAX = 1, 60

WalletCurrency = Literal["EUR", "USD"]
WALLET_CURRENCIES: Final[tuple[str, ...]] = ("EUR", "USD")
#: Hoy todo el dinero de la plataforma va en US$ (spec 047, §Origen): mientras
#: la cuenta del partner no tenga moneda propia (ola 7), su bolsa nace en USD.
DEFAULT_WALLET_CURRENCY: Final = "USD"

DeductionSource = Literal["web", "phone", "partner", "browser", "default"]


# ── países ──────────────────────────────────────────────────────────────────


@dataclass(frozen=True)
class Country:
    #: La primera es la que se propone; las demás, las que se aceptan del navegador.
    timezones: tuple[str, ...]
    #: ISO 4217 de los precios del negocio.
    currency: str
    #: De la UE o del EEE: nace con «Solo UE» (research D22).
    eu_eea: bool
    #: ISO 639-1: el idioma en el que se proponen los datos leídos.
    language: str


def _c(tz: str | tuple[str, ...], currency: str, *, eu: bool = False, lang: str = "es") -> Country:
    return Country(
        timezones=(tz,) if isinstance(tz, str) else tz, currency=currency, eu_eea=eu, language=lang
    )


#: Los mercados de la plataforma: Europa (UE y EEE, y sus vecinos) y América.
#: Un país que no está aquí no se deduce: la persona lo elige en «Más ajustes».
COUNTRIES: Final[dict[str, Country]] = {
    # UE
    "ES": _c(("Europe/Madrid", "Atlantic/Canary", "Africa/Ceuta"), "EUR", eu=True),
    "PT": _c(("Europe/Lisbon", "Atlantic/Madeira", "Atlantic/Azores"), "EUR", eu=True, lang="pt"),
    "FR": _c("Europe/Paris", "EUR", eu=True, lang="fr"),
    "DE": _c(("Europe/Berlin", "Europe/Busingen"), "EUR", eu=True, lang="de"),
    "IT": _c("Europe/Rome", "EUR", eu=True, lang="it"),
    "NL": _c("Europe/Amsterdam", "EUR", eu=True, lang="nl"),
    "BE": _c("Europe/Brussels", "EUR", eu=True, lang="nl"),
    "LU": _c("Europe/Luxembourg", "EUR", eu=True, lang="fr"),
    "IE": _c("Europe/Dublin", "EUR", eu=True, lang="en"),
    "AT": _c("Europe/Vienna", "EUR", eu=True, lang="de"),
    "FI": _c("Europe/Helsinki", "EUR", eu=True, lang="fi"),
    "GR": _c("Europe/Athens", "EUR", eu=True, lang="el"),
    "CY": _c("Asia/Nicosia", "EUR", eu=True, lang="el"),
    "MT": _c("Europe/Malta", "EUR", eu=True, lang="en"),
    "SK": _c("Europe/Bratislava", "EUR", eu=True, lang="sk"),
    "SI": _c("Europe/Ljubljana", "EUR", eu=True, lang="sl"),
    "EE": _c("Europe/Tallinn", "EUR", eu=True, lang="et"),
    "LV": _c("Europe/Riga", "EUR", eu=True, lang="lv"),
    "LT": _c("Europe/Vilnius", "EUR", eu=True, lang="lt"),
    "HR": _c("Europe/Zagreb", "EUR", eu=True, lang="hr"),
    # Bulgaria entró en el euro el 1 de enero de 2026.
    "BG": _c("Europe/Sofia", "EUR", eu=True, lang="bg"),
    "PL": _c("Europe/Warsaw", "PLN", eu=True, lang="pl"),
    "CZ": _c("Europe/Prague", "CZK", eu=True, lang="cs"),
    "HU": _c("Europe/Budapest", "HUF", eu=True, lang="hu"),
    "RO": _c("Europe/Bucharest", "RON", eu=True, lang="ro"),
    "SE": _c("Europe/Stockholm", "SEK", eu=True, lang="sv"),
    "DK": _c("Europe/Copenhagen", "DKK", eu=True, lang="da"),
    # EEE fuera de la UE
    "NO": _c("Europe/Oslo", "NOK", eu=True, lang="no"),
    "IS": _c("Atlantic/Reykjavik", "ISK", eu=True, lang="is"),
    "LI": _c("Europe/Vaduz", "CHF", eu=True, lang="de"),
    # Europa fuera de la UE y del EEE
    "GB": _c("Europe/London", "GBP", lang="en"),
    "CH": _c("Europe/Zurich", "CHF", lang="de"),
    "AD": _c("Europe/Andorra", "EUR", lang="ca"),
    # América del Norte y Central
    "US": _c(
        (
            "America/New_York",
            "America/Chicago",
            "America/Denver",
            "America/Phoenix",
            "America/Los_Angeles",
            "America/Anchorage",
            "Pacific/Honolulu",
        ),
        "USD",
        lang="en",
    ),
    "CA": _c(
        (
            "America/Toronto",
            "America/Vancouver",
            "America/Edmonton",
            "America/Winnipeg",
            "America/Halifax",
            "America/St_Johns",
        ),
        "CAD",
        lang="en",
    ),
    "MX": _c(
        (
            "America/Mexico_City",
            "America/Cancun",
            "America/Merida",
            "America/Monterrey",
            "America/Chihuahua",
            "America/Mazatlan",
            "America/Hermosillo",
            "America/Tijuana",
        ),
        "MXN",
    ),
    "GT": _c("America/Guatemala", "GTQ"),
    "SV": _c("America/El_Salvador", "USD"),
    "HN": _c("America/Tegucigalpa", "HNL"),
    "NI": _c("America/Managua", "NIO"),
    "CR": _c("America/Costa_Rica", "CRC"),
    # Panamá cobra en dólares (el balboa no circula en billetes).
    "PA": _c("America/Panama", "USD"),
    "CU": _c("America/Havana", "CUP"),
    "DO": _c("America/Santo_Domingo", "DOP"),
    "PR": _c("America/Puerto_Rico", "USD"),
    # América del Sur
    "CO": _c("America/Bogota", "COP"),
    # Venezuela pone sus precios en dólares de hecho: es lo que se propone.
    "VE": _c("America/Caracas", "USD"),
    "EC": _c(("America/Guayaquil", "Pacific/Galapagos"), "USD"),
    "PE": _c("America/Lima", "PEN"),
    "BO": _c("America/La_Paz", "BOB"),
    "CL": _c(("America/Santiago", "America/Punta_Arenas", "Pacific/Easter"), "CLP"),
    "AR": _c(
        (
            "America/Argentina/Buenos_Aires",
            "America/Argentina/Cordoba",
            "America/Argentina/Mendoza",
            "America/Argentina/Salta",
            "America/Argentina/Ushuaia",
        ),
        "ARS",
    ),
    "UY": _c("America/Montevideo", "UYU"),
    "PY": _c("America/Asuncion", "PYG"),
    "BR": _c(
        (
            "America/Sao_Paulo",
            "America/Manaus",
            "America/Fortaleza",
            "America/Recife",
            "America/Belem",
            "America/Bahia",
            "America/Cuiaba",
            "America/Noronha",
        ),
        "BRL",
        lang="pt",
    ),
}

#: El dominio de primer nivel de cada país. ``.co`` solo cuenta como Colombia
#: con segundo nivel (``.com.co``): suelto, es la «compañía» de medio mundo.
_TLD_COUNTRY: Final[dict[str, str]] = {
    **{code.lower(): code for code in COUNTRIES if code not in {"GB", "CO"}},
    "uk": "GB",
    # Los dominios de las lenguas de España.
    "cat": "ES",
    "eus": "ES",
    "gal": "ES",
}
_SECOND_LEVEL: Final = frozenset({"com", "net", "org", "gob", "gov", "edu", "nom", "co", "info"})

#: Prefijo telefónico → país. Los de América del Norte que no son de EE. UU.
#: van con su código de área.
_PHONE_PREFIX: Final[dict[str, str]] = {
    "1809": "DO",
    "1829": "DO",
    "1849": "DO",
    "1787": "PR",
    "1939": "PR",
    "1": "US",
    "34": "ES",
    "351": "PT",
    "33": "FR",
    "49": "DE",
    "39": "IT",
    "31": "NL",
    "32": "BE",
    "352": "LU",
    "353": "IE",
    "43": "AT",
    "358": "FI",
    "30": "GR",
    "357": "CY",
    "356": "MT",
    "421": "SK",
    "386": "SI",
    "372": "EE",
    "371": "LV",
    "370": "LT",
    "385": "HR",
    "359": "BG",
    "48": "PL",
    "420": "CZ",
    "36": "HU",
    "40": "RO",
    "46": "SE",
    "45": "DK",
    "47": "NO",
    "354": "IS",
    "423": "LI",
    "44": "GB",
    "41": "CH",
    "376": "AD",
    "52": "MX",
    "502": "GT",
    "503": "SV",
    "504": "HN",
    "505": "NI",
    "506": "CR",
    "507": "PA",
    "53": "CU",
    "57": "CO",
    "58": "VE",
    "593": "EC",
    "51": "PE",
    "591": "BO",
    "56": "CL",
    "54": "AR",
    "598": "UY",
    "595": "PY",
    "55": "BR",
}
_PHONE_RE: Final = re.compile(r"(?<![\w+])\+\s?(\d[\d\s().-]{5,18}\d)")

#: La zona del navegador → su país (la primera que lo dice).
_TIMEZONE_COUNTRY: Final[dict[str, str]] = {
    tz: code for code, country in COUNTRIES.items() for tz in country.timezones
}

#: Cómo se nombra cada idioma en el prompt de la lectura (que va en español).
LANGUAGE_NAMES: Final[dict[str, str]] = {
    "es": "español",
    "en": "inglés",
    "pt": "portugués",
    "fr": "francés",
    "de": "alemán",
    "it": "italiano",
    "nl": "neerlandés",
    "ca": "catalán",
}


@lru_cache(maxsize=1)
def _iana_zones() -> frozenset[str]:
    return frozenset(zoneinfo.available_timezones()) | {"UTC"}


def is_valid_timezone(tz: str | None) -> bool:
    """¿Es una zona IANA? (requisito 6.2: el servidor la valida). Exacta: ni
    rutas ni mayúsculas cambiadas."""
    if not tz or len(tz) > 64:
        return False
    if tz not in _iana_zones():
        return False
    try:
        zoneinfo.ZoneInfo(tz)
    except (zoneinfo.ZoneInfoNotFoundError, ValueError):
        return False
    return True


def country_from_host(host: str) -> str | None:
    """``cultorbarber.es`` → ES; ``cafeorigen.com.mx`` → MX; ``.com`` → ``None``."""
    labels = [label for label in host.lower().strip(".").split(".") if label]
    if len(labels) < 2:
        return None
    tld = labels[-1]
    if tld == "co":
        return "CO" if len(labels) >= 3 and labels[-2] in _SECOND_LEVEL else None
    return _TLD_COUNTRY.get(tld)


def country_from_links(links: Sequence[DetectedLink]) -> str | None:
    """El país del dominio de la primera web que lo dice."""
    from urllib.parse import urlsplit

    for link in links:
        if link.network != "web" or not link.url:
            continue
        country = country_from_host(urlsplit(link.url).hostname or "")
        if country is not None:
            return country
    return None


def country_from_phones(text: str) -> str | None:
    """El país del prefijo del primer teléfono con ``+`` que lo dice."""
    for match in _PHONE_RE.finditer(text or ""):
        digits = re.sub(r"\D", "", match.group(1))
        for size in (4, 3, 2, 1):
            country = _PHONE_PREFIX.get(digits[:size])
            if country is not None:
                return country
    return None


def country_from_browser(timezone: str | None, locale: str | None) -> str | None:
    """La zona del navegador, y si no, la región de su idioma (``es-CL``)."""
    if timezone and timezone in _TIMEZONE_COUNTRY:
        return _TIMEZONE_COUNTRY[timezone]
    if locale:
        match = re.match(r"^[A-Za-z]{2,3}[-_]([A-Za-z]{2})\b", locale.strip())
        if match and match.group(1).upper() in COUNTRIES:
            return match.group(1).upper()
    return None


@dataclass(frozen=True)
class Deduction:
    """Lo que «Más ajustes» propone, y de dónde salió el país."""

    country: str | None
    timezone: str
    price_currency: str | None
    wallet_currency: str
    eu_only: bool
    source: DeductionSource


def deduce_settings(
    *,
    info: str,
    links: Sequence[DetectedLink],
    partner_country: str | None = None,
    partner_currency: str | None = None,
    browser_timezone: str | None = None,
    browser_locale: str | None = None,
) -> Deduction:
    """Requisito 4.5, por orden: dominio y prefijo, país del partner, navegador."""
    country: str | None
    source: DeductionSource
    candidates: tuple[tuple[str | None, DeductionSource], ...] = (
        (country_from_links(links), "web"),
        (country_from_phones(info), "phone"),
        (partner_country if partner_country in COUNTRIES else None, "partner"),
        (country_from_browser(browser_timezone, browser_locale), "browser"),
    )
    country, source = next(((c, s) for c, s in candidates if c is not None), (None, "default"))
    browser_tz = browser_timezone if is_valid_timezone(browser_timezone) else None
    info_country = COUNTRIES.get(country) if country else None
    if info_country is not None:
        timezone = browser_tz if browser_tz in info_country.timezones else info_country.timezones[0]
    else:
        timezone = browser_tz or "UTC"
    wallet = partner_currency if partner_currency in WALLET_CURRENCIES else DEFAULT_WALLET_CURRENCY
    return Deduction(
        country=country,
        timezone=timezone,
        price_currency=info_country.currency if info_country else None,
        wallet_currency=wallet,
        eu_only=bool(info_country and info_country.eu_eea),
        source=source,
    )


def business_language(country: str | None) -> str:
    """El idioma en el que se proponen los datos leídos del negocio."""
    found = COUNTRIES.get(country) if country else None
    return found.language if found else "es"


def eu_by_default(country: str | None) -> bool:
    found = COUNTRIES.get(country) if country else None
    return bool(found and found.eu_eea)


# ── sugerencias de nicho ─────────────────────────────────────────────────────

NicheGroup = Literal["beauty", "health", "aesthetics", "food", "retail", "services", "other"]
#: Los 6 grupos de plantillas de la spec 046 más «Otro» (decisión del owner del
#: 2026-10-24). Sus nombres son de la consola (``business.niche.group.<key>``).
NICHE_GROUPS: Final[tuple[str, ...]] = (
    "beauty",
    "health",
    "aesthetics",
    "food",
    "retail",
    "services",
    "other",
)


@dataclass(frozen=True)
class TemplateNiche:
    key: str
    group: NicheGroup
    #: La plantilla de la que sale (``services/templating/seeds``).
    template: str
    #: Solo para buscar: el texto lo pone la consola (``business.niche.<key>``).
    words: tuple[str, ...]


TEMPLATE_NICHES: Final[tuple[TemplateNiche, ...]] = (
    TemplateNiche("barbershop", "beauty", "barbershop_v1", ("Barbería", "Barbershop")),
    TemplateNiche(
        "hair_salon",
        "beauty",
        "beauty_salon_v1",
        ("Peluquería y salón de belleza", "Hair and beauty salon"),
    ),
    TemplateNiche("nail_studio", "beauty", "nail_studio_v1", ("Estudio de uñas", "Nail studio")),
    TemplateNiche("spa", "beauty", "spa_v1", ("Spa y bienestar", "Spa and wellness")),
    TemplateNiche(
        "clinic", "health", "clinica_v1", ("Clínica o consultorio médico", "Clinic or practice")
    ),
    TemplateNiche("dental", "health", "dental_v1", ("Clínica dental", "Dental clinic")),
    TemplateNiche(
        "aesthetic_clinic",
        "aesthetics",
        "aesthetic_clinic_v1",
        ("Clínica estética", "Aesthetic clinic"),
    ),
    TemplateNiche("medspa", "aesthetics", "medspa_v1", ("Medicina estética", "Medical aesthetics")),
    TemplateNiche("restaurant", "food", "restaurante_v1", ("Restaurante", "Restaurant")),
    TemplateNiche(
        "online_store", "retail", "woocommerce_sales_v1", ("Tienda online", "Online store")
    ),
    TemplateNiche(
        "warehouse", "retail", "inventario_v1", ("Almacén e inventario", "Warehouse and inventory")
    ),
    TemplateNiche("collections", "services", "cobranza_v1", ("Cobranza", "Debt collection")),
)
#: Cuántos de los más usados se proponen.
MAX_USED_NICHES: Final = 8


@dataclass(frozen=True)
class NicheSuggestion:
    source: Literal["template", "used"]
    #: De una plantilla: su clave (la consola pone el texto en su idioma).
    key: str | None = None
    group: NicheGroup | None = None
    #: De los más usados: el nicho tal como lo escribió el partner.
    value: str | None = None
    uses: int = 0


def fold(text: str) -> str:
    """Sin tildes ni mayúsculas, para comparar lo que se escribe."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).casefold().strip()


def niche_suggestions(q: str | None, *, used: Sequence[tuple[str, int]]) -> list[NicheSuggestion]:
    """Las de las plantillas que casan con ``q`` y los más usados que casan.
    Sin ``q``, todas las de las plantillas y los más usados. Nunca restringen:
    un nicho sin parecido no tiene sugerencias y se escribe igual."""
    needle = fold(q or "")
    templates = [
        NicheSuggestion(source="template", key=n.key, group=n.group)
        for n in TEMPLATE_NICHES
        if not needle or any(needle in fold(w) for w in (*n.words, n.key))
    ]
    totals: dict[str, tuple[str, int]] = {}
    for value, uses in used:
        clean = " ".join((value or "").split())
        if not clean:
            continue
        key = fold(clean)
        prior = totals.get(key)
        totals[key] = (prior[0] if prior else clean, (prior[1] if prior else 0) + int(uses))
    ranked = sorted(totals.values(), key=lambda item: (-item[1], fold(item[0])))
    popular = [
        NicheSuggestion(source="used", value=value, uses=uses)
        for value, uses in ranked
        if not needle or needle in fold(value)
    ][:MAX_USED_NICHES]
    return [*templates, *popular]


def merge_niche_suggestion(current: str, suggestion: str) -> str:
    """Pulsar una sugerencia: rellena el campo vacío o la añade a lo escrito;
    nunca sustituye (requisito 4.2). Si ya está, o no cabe en 80, no cambia."""
    written = " ".join((current or "").split())
    if not written:
        return suggestion.strip()
    if fold(suggestion) in fold(written):
        return current
    merged = f"{written} · {suggestion.strip()}"
    return merged if len(merged) <= NICHE_MAX else current


# ── el alta de la ficha ───────────────────────────────────────────────────────


def clean_name(raw: str) -> str:
    return " ".join((raw or "").split())


async def create_profile(
    session: AsyncSession,
    *,
    niche: str,
    info: str | None,
    country: str | None,
    timezone: str,
    price_currency: str | None,
    eu_only: bool,
    links: Sequence[DetectedLink],
    actor: Actor,
) -> BusinessProfile:
    """La ficha de un cliente recién creado, con la procedencia de cada dato.

    El nombre vive en ``tenants``; aquí deja su procedencia. Dentro de la
    transacción del alta y con el cliente puesto. La web es la
    primera de ``links`` que es una web; las demás webs y las redes van a
    ``business_links``. Nada de esto toca un agente.
    """
    if not NICHE_MIN <= len(niche) <= NICHE_MAX:
        raise ValueError("niche out of bounds")
    if info is not None and len(info) > INFO_MAX:
        raise ValueError("info out of bounds")
    tenant_id = require_current_tenant()
    website = next((link.url for link in links if link.network == "web" and link.url), None)
    profile = BusinessProfile(
        tenant_id=tenant_id,
        niche=niche,
        info=info or None,
        website=website,
        country=country,
        timezone=timezone,
        price_currency=price_currency,
        eu_only=eu_only,
        sovereign=False,
        policies={},
        content_rev=1,
    )
    session.add(profile)
    await session.flush()

    pointers: list[str] = [
        "/business/name",
        "/business/niche",
        "/business/timezone",
        "/business/eu_only",
    ]
    if info:
        pointers.append("/business/info")
    if website:
        pointers.append("/business/website")
    if country:
        pointers.append("/business/country")
    if price_currency:
        pointers.append("/business/price_currency")

    saved_links: list[BusinessLink] = []
    seen: set[tuple[str, str]] = set()
    for link in links:
        target = (link.handle or link.url or "").lower()
        if not target or (link.network, target) in seen:
            continue
        seen.add((link.network, target))
        row = BusinessLink(
            tenant_id=tenant_id, network=link.network, url=link.url, handle=link.handle
        )
        session.add(row)
        saved_links.append(row)
    await session.flush()
    pointers.extend(f"/links/{row.id}" for row in saved_links)

    for pointer in pointers:
        session.add(
            BusinessFieldProvenance(
                tenant_id=tenant_id,
                pointer=pointer,
                source="person",
                actor_kind=actor.kind,
                actor_id=actor.id,
                origin=actor.origin,
                review="confirmed",
            )
        )
    await init_sections(session, actor=actor, links=bool(saved_links))
    return profile


__all__ = [
    "COUNTRIES",
    "DEFAULT_WALLET_CURRENCY",
    "INFO_MAX",
    "LANGUAGE_NAMES",
    "MAX_USED_NICHES",
    "NAME_MAX",
    "NAME_MIN",
    "NICHE_GROUPS",
    "NICHE_MAX",
    "NICHE_MIN",
    "TEMPLATE_NICHES",
    "WALLET_CURRENCIES",
    "Country",
    "Deduction",
    "NicheSuggestion",
    "TemplateNiche",
    "business_language",
    "clean_name",
    "country_from_browser",
    "country_from_host",
    "country_from_links",
    "country_from_phones",
    "create_profile",
    "deduce_settings",
    "eu_by_default",
    "fold",
    "is_valid_timezone",
    "merge_niche_suggestion",
    "niche_suggestions",
]
