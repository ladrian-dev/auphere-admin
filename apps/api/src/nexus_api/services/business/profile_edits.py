"""Las ediciones de los datos básicos, las políticas y las redes — spec 047 (T063, T069).

Tres secciones de la ficha sin tabla propia que viven en ``tenants``,
``partner_tenants``, ``business_profiles`` y ``business_links``. Cada función
valida, escribe sus filas y anota la escritura con ``writes.write_section``
(historial, procedencia, revisión, auditoría, aviso y recompilación):

- :func:`update_basics`: lo que edita el modal «Editar cliente» (requisito 6.1):
  nombre, nicho, información, web, país, zona horaria (IANA, validada aquí, 6.2),
  moneda de los precios y «Solo UE». La moneda de la bolsa no se cambia aquí: con
  saldo dentro exige convertirlo (6.7), y eso es de la ola 7 (``PUT
  /bag/currency``). El nombre vive en ``tenants`` y en ``partner_tenants``;
  cambiarlo cambia los dos.
- :func:`update_policies`: cancelación, pagos, señal y no presentarse (≤ 1.000
  cada una). La ruta ``PUT /policies`` (de la consola de Negocio) llama aquí.
- :func:`put_links`: la web y las redes (requisito 12.4), con la normalización
  del alta (``links.link_from_choice``). Lo que ya estaba conserva su id y su
  procedencia; la web del negocio sigue a la primera web de la lista.

Y los adaptadores de las tres para deshacer y para aplicar propuestas
(``writes.register_section_adapter``).
"""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, Final

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.core.tenant_context import require_current_tenant
from nexus_api.db.models import PartnerTenant, Tenant
from nexus_api.db.models.business import BusinessLink, BusinessProfile
from nexus_api.services.business import client_spec
from nexus_api.services.business.links import MAX_LINKS, link_from_choice
from nexus_api.services.business.profile import (
    DEFAULT_WALLET_CURRENCY,
    INFO_MAX,
    NAME_MAX,
    NICHE_MAX,
    NICHE_MIN,
    clean_name,
    is_valid_timezone,
)
from nexus_api.services.business.sections import Actor
from nexus_api.services.business.writes import (
    NothingWritten,
    Op,
    SectionWritten,
    WriteContext,
    register_section_adapter,
    write_section,
)

POLICY_KEYS: Final[tuple[str, ...]] = ("cancellation", "payments", "deposit", "no_show")
POLICY_MAX: Final = 1000
#: Los campos de los datos básicos que se editan (``/business/<campo>``).
BASICS_FIELDS: Final[tuple[str, ...]] = (
    "name",
    "niche",
    "info",
    "website",
    "country",
    "timezone",
    "price_currency",
    "wallet_currency",
    "eu_only",
)
_COUNTRY = re.compile(r"^[A-Z]{2}$")
_CURRENCY = re.compile(r"^[A-Z]{3}$")


class InvalidField(ValueError):
    """Un dato que no vale: ``field`` y un código cerrado (la consola pone las palabras)."""

    def __init__(self, field: str, code: str) -> None:
        super().__init__(f"{field}: {code}")
        self.field = field
        self.code = code


class BagCurrencyLocked(Exception):
    """La moneda de la bolsa se cambia desde Consumo, con su conversión (ola 7)."""


class NoBusinessProfile(LookupError):
    """Un cliente de antes de la 047, sin ficha todavía."""


@dataclass(frozen=True)
class Edited:
    """Lo que dejó una edición: lo escrito (``None`` si nada cambió) y qué cambió."""

    written: SectionWritten | None
    changed: list[str] = field(default_factory=list)
    before: dict[str, Any] = field(default_factory=dict)
    after: dict[str, Any] = field(default_factory=dict)


async def _ensure_profile(session: AsyncSession) -> None:
    """Un cliente de antes de la 047 estrena su ficha al editarlo
    (``hours.ensure_profile``: nace marcada «Migrado»)."""
    try:
        from nexus_api.services.business.hours import ensure_profile
    except ImportError:  # pragma: no cover - el servicio de horario es de esta ola
        return
    await ensure_profile(session)


async def _profile(session: AsyncSession) -> BusinessProfile:
    profile = await session.get(BusinessProfile, require_current_tenant())
    if profile is None:
        raise NoBusinessProfile
    return profile


# ── datos básicos ──────────────────────────────────────────────────────────────


def _clean_basics(changes: Mapping[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in changes.items():
        if key not in BASICS_FIELDS:
            raise InvalidField(key, "unknown_field")
        if key == "name":
            name = clean_name(str(value or ""))
            if not 1 <= len(name) <= NAME_MAX:
                raise InvalidField("name", "length")
            out[key] = name
        elif key == "niche":
            niche = " ".join(str(value or "").split())
            if not NICHE_MIN <= len(niche) <= NICHE_MAX:
                raise InvalidField("niche", "length")
            out[key] = niche
        elif key == "info":
            info = (str(value) if value is not None else "").strip()
            if len(info) > INFO_MAX:
                raise InvalidField("info", "length")
            out[key] = info or None
        elif key == "website":
            site = (str(value) if value is not None else "").strip()
            if site and (len(site) > 300 or not re.match(r"^https?://", site, re.I)):
                raise InvalidField("website", "invalid_url")
            out[key] = site or None
        elif key == "country":
            if value is not None and not _COUNTRY.match(str(value)):
                raise InvalidField("country", "invalid_country")
            out[key] = value
        elif key == "timezone":
            if not is_valid_timezone(value):
                raise InvalidField("timezone", "invalid_timezone")
            out[key] = value
        elif key == "price_currency":
            if value is not None and not _CURRENCY.match(str(value)):
                raise InvalidField("price_currency", "invalid_currency")
            out[key] = value
        elif key == "wallet_currency":
            if value not in ("EUR", "USD"):
                raise InvalidField("wallet_currency", "invalid_currency")
            if value != DEFAULT_WALLET_CURRENCY:
                raise BagCurrencyLocked
        elif key == "eu_only":
            out[key] = bool(value)
    return out


async def update_basics(
    session: AsyncSession,
    changes: Mapping[str, Any],
    *,
    actor: Actor,
    expected_revision: int | None = None,
    audit_actor: str | None = None,
    source: str = "person",
    kind: str = "edit",
    review: str = "confirmed",
    source_url: str | None = None,
    undo_of: Any = None,
    audit: bool = True,
) -> Edited:
    """Los datos básicos del cliente del contexto. Valida todo antes de
    escribir nada (``InvalidField``, ``BagCurrencyLocked``)."""
    clean = _clean_basics(changes)
    tenant_id = require_current_tenant()
    await _ensure_profile(session)
    profile = await _profile(session)
    tenant = await session.get(Tenant, tenant_id)
    assert tenant is not None  # el contexto viene de un cliente que existe
    before = (await client_spec.section_view(session, "basics"))["business"]

    for key, value in clean.items():
        if key == "name":
            tenant.name = value
            mapping = await session.scalar(
                sa.select(PartnerTenant).where(PartnerTenant.tenant_id == tenant_id)
            )
            if mapping is not None:
                mapping.client_name = value
        elif key == "timezone":
            tenant.timezone = value
            profile.timezone = value
        else:
            setattr(profile, key, value)
    await session.flush()
    after = (await client_spec.section_view(session, "basics"))["business"]
    changed = [k for k in BASICS_FIELDS if before.get(k) != after.get(k)]
    if not changed:
        return Edited(written=None, changed=[], before=before, after=after)
    written = await write_section(
        session,
        "basics",
        actor=actor,
        before={"business": before},
        after={"business": after},
        pointers=[f"/business/{k}" for k in changed],
        source=source,
        kind=kind,
        expected_revision=expected_revision,
        state="complete",
        source_url=source_url,
        review=review,
        audit_actor=audit_actor,
        undo_of=undo_of,
        audit=audit,
    )
    return Edited(written=written, changed=changed, before=before, after=after)


# ── políticas ──────────────────────────────────────────────────────────────────


async def update_policies(
    session: AsyncSession,
    values: Mapping[str, str | None],
    *,
    actor: Actor,
    expected_revision: int | None = None,
    replace: bool = False,
    audit_actor: str | None = None,
    source: str = "person",
    kind: str = "edit",
    review: str = "confirmed",
    source_url: str | None = None,
    undo_of: Any = None,
) -> Edited:
    """Cancelación, pagos, señal y no presentarse. ``None`` o vacío quita la
    política; ``replace`` deja solo las que llegan."""
    for key, value in values.items():
        if key not in POLICY_KEYS:
            raise InvalidField(f"policies.{key}", "unknown_field")
        if value is not None and len(str(value)) > POLICY_MAX:
            raise InvalidField(f"policies.{key}", "length")
    if actor.kind == "builder":
        # Lo mismo diría ``write_section``, pero antes de tocar las filas.
        from nexus_api.services.business.writes import BuilderWritesOnlyByProposal

        raise BuilderWritesOnlyByProposal("the builder proposes")
    # Una respuesta del constructor puede ser lo primero que se escribe en la
    # ficha de un cliente de antes de la 047 (recorrido UI: era un 500).
    await _ensure_profile(session)
    profile = await _profile(session)
    before = dict((await client_spec.section_view(session, "policies"))["policies"] or {})
    current: dict[str, Any] = {} if replace else dict(profile.policies or {})
    for key, value in values.items():
        text = " ".join(str(value).split()) if value is not None else ""
        if text:
            current[key] = text
        else:
            current.pop(key, None)
    profile.policies = current
    await session.flush()
    after = dict((await client_spec.section_view(session, "policies"))["policies"] or {})
    changed = [k for k in POLICY_KEYS if before.get(k) != after.get(k)]
    if not changed:
        return Edited(written=None, changed=[], before=before, after=after)
    written = await write_section(
        session,
        "policies",
        actor=actor,
        before={"policies": before},
        after={"policies": after},
        pointers=[f"/policies/{k}" for k in changed if k in after],
        source=source,
        kind=kind,
        expected_revision=expected_revision,
        state="complete" if after else "optional",
        source_url=source_url,
        review=review,
        audit_actor=audit_actor,
        undo_of=undo_of,
    )
    return Edited(written=written, changed=changed, before=before, after=after)


# ── la web y las redes ─────────────────────────────────────────────────────────


def _link_key(network: str, url: str | None, handle: str | None) -> tuple[str, str]:
    return (network, (handle or url or "").lower().rstrip("/"))


async def put_links(
    session: AsyncSession,
    links: Sequence[Mapping[str, Any]],
    *,
    actor: Actor,
    expected_revision: int | None = None,
    audit_actor: str | None = None,
    source: str = "person",
    kind: str = "edit",
    review: str = "confirmed",
    source_url: str | None = None,
    undo_of: Any = None,
) -> Edited:
    """La lista entera de la web y las redes (requisito 12.4)."""
    if len(links) > MAX_LINKS:
        raise InvalidField("links", "too_many")
    wanted: list[tuple[tuple[str, str], str, str | None, str | None]] = []
    seen: set[tuple[str, str]] = set()
    for i, raw in enumerate(links):
        link = link_from_choice(
            str(raw.get("network") or ""), url=raw.get("url"), handle=raw.get("handle")
        )
        if link is None:
            raise InvalidField(f"links.{i}", "invalid_link")
        key = _link_key(link.network, link.url, link.handle)
        if key in seen:
            continue
        seen.add(key)
        wanted.append((key, link.network, link.url, link.handle))

    tenant_id = require_current_tenant()
    profile = await _profile(session)
    before = (await client_spec.section_view(session, "links"))["links"]
    rows = (
        await session.scalars(sa.select(BusinessLink).where(BusinessLink.tenant_id == tenant_id))
    ).all()
    existing = {_link_key(r.network, r.url, r.handle): r for r in rows}
    for key, row in existing.items():
        if key not in seen:
            await session.delete(row)
    await session.flush()
    added: list[BusinessLink] = []
    for key, network, url, handle in wanted:
        if key in existing:
            continue
        row = BusinessLink(tenant_id=tenant_id, network=network, url=url, handle=handle)
        session.add(row)
        added.append(row)
    await session.flush()
    first_web = next((url for _k, network, url, _h in wanted if network == "web" and url), None)
    old_webs = {r.url for r in rows if r.network == "web"}
    if profile.website is None or profile.website in old_webs:
        profile.website = first_web
    await session.flush()
    after = (await client_spec.section_view(session, "links"))["links"]
    if [_strip_id(x) for x in before] == [_strip_id(x) for x in after]:
        return Edited(written=None, changed=[], before={"links": before}, after={"links": after})
    written = await write_section(
        session,
        "links",
        actor=actor,
        before={"links": before},
        after={"links": after},
        pointers=[f"/links/{row.id}" for row in added],
        source=source,
        kind=kind,
        expected_revision=expected_revision,
        state="complete" if after else "pending",
        source_url=source_url,
        review=review,
        audit_actor=audit_actor,
        undo_of=undo_of,
    )
    return Edited(
        written=written, changed=["links"], before={"links": before}, after={"links": after}
    )


def _strip_id(item: Mapping[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in item.items() if k != "id"}


# ── adaptadores: deshacer y aplicar propuestas ─────────────────────────────────


def _unwrap(view: Mapping[str, Any] | None, key: str) -> dict[str, Any]:
    """La vista de una sección, con su clave del ClientSpec (``{"business": …}``,
    la de aquí y la de la lectura) o sin ella (la de ``basics.py``)."""
    if not view:
        return {}
    inner = view.get(key)
    return dict(inner) if isinstance(inner, Mapping) else dict(view)


def _kw(ctx: WriteContext) -> dict[str, Any]:
    return {
        "actor": ctx.actor,
        "audit_actor": ctx.audit_actor,
        "source": ctx.source,
        "kind": ctx.kind,
        "review": ctx.review,
        "source_url": ctx.source_url,
        "undo_of": ctx.undo_of,
    }


def _written(edited: Edited) -> SectionWritten:
    if edited.written is None:
        raise NothingWritten
    return edited.written


async def _restore_basics(
    session: AsyncSession, view: Mapping[str, Any] | None, ctx: WriteContext
) -> SectionWritten:
    target = _unwrap(view, "business")
    changes = {k: target.get(k) for k in BASICS_FIELDS if k != "wallet_currency" and k in target}
    for k in ("info", "website", "country", "price_currency"):
        changes.setdefault(k, None)
    return _written(await update_basics(session, changes, **_kw(ctx)))


async def _apply_basics(
    session: AsyncSession, ops: Sequence[Op], ctx: WriteContext
) -> SectionWritten:
    changes: dict[str, Any] = {}
    for op in ops:
        key, rest = client_spec.split_pointer(op.path)
        if key != "business" or len(rest) != 1 or op.op != "replace":
            raise InvalidField(op.path, "invalid_pointer")
        changes[rest[0]] = op.value
    return _written(await update_basics(session, changes, **_kw(ctx)))


async def _restore_policies(
    session: AsyncSession, view: Mapping[str, Any] | None, ctx: WriteContext
) -> SectionWritten:
    target = _unwrap(view, "policies")
    values: dict[str, str | None] = {k: target.get(k) for k in POLICY_KEYS}
    return _written(await update_policies(session, values, replace=True, **_kw(ctx)))


async def _apply_policies(
    session: AsyncSession, ops: Sequence[Op], ctx: WriteContext
) -> SectionWritten:
    values: dict[str, str | None] = {}
    for op in ops:
        key, rest = client_spec.split_pointer(op.path)
        if key != "policies" or op.op != "replace":
            raise InvalidField(op.path, "invalid_pointer")
        if not rest:
            for k in POLICY_KEYS:
                values[k] = (op.value or {}).get(k)
        elif len(rest) == 1:
            values[rest[0]] = None if op.value is None else str(op.value)
        else:
            raise InvalidField(op.path, "invalid_pointer")
    return _written(await update_policies(session, values, **_kw(ctx)))


async def _restore_links(
    session: AsyncSession, view: Mapping[str, Any] | None, ctx: WriteContext
) -> SectionWritten:
    target = list((view or {}).get("links") or [])
    return _written(await put_links(session, target, **_kw(ctx)))


async def _apply_links(
    session: AsyncSession, ops: Sequence[Op], ctx: WriteContext
) -> SectionWritten:
    current = (await client_spec.section_view(session, "links"))["links"]
    for op in ops:
        key, rest = client_spec.split_pointer(op.path)
        if key != "links":
            raise InvalidField(op.path, "invalid_pointer")
        if op.op == "add" and rest == ["-"]:
            current.append(dict(op.value or {}))
        elif op.op == "archive" and len(rest) == 1:
            current = [x for x in current if x.get("id") != rest[0]]
        else:
            raise InvalidField(op.path, "invalid_pointer")
    return _written(await put_links(session, current, **_kw(ctx)))


register_section_adapter("basics", restore=_restore_basics, apply=_apply_basics)
register_section_adapter("policies", restore=_restore_policies, apply=_apply_policies)
register_section_adapter("links", restore=_restore_links, apply=_apply_links)


__all__ = [
    "BASICS_FIELDS",
    "POLICY_KEYS",
    "BagCurrencyLocked",
    "Edited",
    "InvalidField",
    "NoBusinessProfile",
    "NothingWritten",
    "put_links",
    "update_basics",
    "update_policies",
]
