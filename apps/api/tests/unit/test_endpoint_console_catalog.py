"""El catálogo en el número (spec 022, Historia 1).

Meta se simula por la costura ``build_meta_client`` del router, como en la
spec 021. Lo que se prueba es el contrato de ``contracts/catalog.md`` y la
conciliación de research D3: la tarjeta dice la verdad de Meta.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
import sqlalchemy as sa
from nexus_channels.whatsapp_meta.exceptions import MetaAPIError, MetaTransientError

from nexus_api.api.console import channels as ch_router
from nexus_api.db.models import AuditLog, Channel, ChannelStatus
from tests.conftest import add_console_member
from tests.unit.test_endpoint_console_channels import (
    _channel,
    _reload,
    _seed_channel_creds,
)

pytestmark = pytest.mark.asyncio

FLORES = {"id": "CAT_FLORES", "name": "Flores y ramos", "product_count": 12}
PLANTAS = {"id": "CAT_PLANTAS", "name": "Plantas", "product_count": 4}


class _CatalogSim:
    """Meta simulado para el catálogo: registra cada llamada y su token."""

    def __init__(
        self,
        *,
        catalogs: list[dict[str, Any]] | None = None,
        linked: dict[str, Any] | None = None,
        fail: dict[str, Exception] | None = None,
    ) -> None:
        self.catalogs = list(catalogs or [])
        self.linked = linked
        self.fail = fail or {}
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def _hit(self, name: str, kw: dict[str, Any]) -> None:
        self.calls.append((name, kw))
        if name in self.fail:
            raise self.fail[name]

    async def list_catalogs(self, **kw: Any) -> list[dict[str, Any]]:
        self._hit("list_catalogs", kw)
        return list(self.catalogs)

    async def get_linked_catalog(self, **kw: Any) -> dict[str, Any] | None:
        self._hit("get_linked_catalog", kw)
        return self.linked

    async def link_catalog(self, **kw: Any) -> dict[str, Any]:
        self._hit("link_catalog", kw)
        self.linked = next(c for c in self.catalogs if c["id"] == kw["catalog_id"])
        return {"success": True}

    async def unlink_catalog(self, **kw: Any) -> dict[str, Any]:
        self._hit("unlink_catalog", kw)
        self.linked = None
        return {"success": True}

    async def close(self) -> None:
        pass

    def names(self) -> list[str]:
        return [c[0] for c in self.calls]


def _sim(monkeypatch, **kw: Any) -> _CatalogSim:
    sim = _CatalogSim(**kw)
    monkeypatch.setattr(ch_router, "build_meta_client", lambda: sim)
    return sim


def _permission() -> MetaAPIError:
    return MetaAPIError("(#10) Permission denied", status_code=403, code=10)


async def _canal(db_session, tenant_id, **cfg):
    canal = _channel(tenant_id, waba_id="W-1", business_id="BIZ-1", **cfg)
    await _seed_channel_creds(db_session, canal, waba_id="W-1")
    db_session.add(canal)
    await db_session.commit()
    return canal


def _url(who: dict, canal: Channel, tail: str) -> str:
    return f"/console/clients/{who['ref']}/channels/{canal.id}/{tail}"


# ── T010 · listar ────────────────────────────────────────────────────────


async def test_lists_the_business_catalogs_and_which_one_is_linked(
    client, console_world, db_session, monkeypatch
) -> None:
    a = console_world["a"]
    sim = _sim(monkeypatch, catalogs=[FLORES, PLANTAS])
    canal = await _canal(db_session, a["tenant_id"], catalog_id="CAT_PLANTAS")
    r = await client.get(_url(a, canal, "catalogs"), headers=a["headers"]())
    assert r.status_code == 200, r.text
    body = r.json()
    assert [i["id"] for i in body["items"]] == ["CAT_FLORES", "CAT_PLANTAS"]
    assert body["items"][0]["name"] == "Flores y ramos"
    assert body["linked_id"] == "CAT_PLANTAS"
    assert sim.calls[0][1]["business_id"] == "BIZ-1"
    assert sim.calls[0][1]["access_token"] == "EAA-canal"


async def test_without_credentials_nothing_is_asked(
    client, console_world, db_session, monkeypatch
) -> None:
    a = console_world["a"]
    sim = _sim(monkeypatch, catalogs=[FLORES])
    canal = _channel(a["tenant_id"], waba_id="W-1", business_id="BIZ-1")
    db_session.add(canal)
    await db_session.commit()
    r = await client.get(_url(a, canal, "catalogs"), headers=a["headers"]())
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "channel_has_no_credentials"
    assert sim.calls == []


async def test_permission_and_outage_have_their_own_codes(
    client, console_world, db_session, monkeypatch
) -> None:
    a = console_world["a"]
    canal = await _canal(db_session, a["tenant_id"])
    _sim(monkeypatch, fail={"list_catalogs": _permission()})
    r = await client.get(_url(a, canal, "catalogs"), headers=a["headers"]())
    assert r.status_code == 409 and r.json()["detail"]["code"] == "catalog_permission_missing"

    _sim(monkeypatch, fail={"list_catalogs": MetaTransientError("down", status_code=503)})
    r = await client.get(_url(a, canal, "catalogs"), headers=a["headers"]())
    assert r.status_code == 503 and r.json()["detail"]["code"] == "meta_unavailable"


# ── T011 · enlazar y cambiar ─────────────────────────────────────────────


async def test_linking_stores_id_and_name_and_audits_who(
    client, console_world, db_session, monkeypatch
) -> None:
    a = console_world["a"]
    sim = _sim(monkeypatch, catalogs=[FLORES])
    canal = await _canal(db_session, a["tenant_id"])
    r = await client.put(
        _url(a, canal, "catalog"), json={"catalog_id": "CAT_FLORES"}, headers=a["headers"]()
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["catalog"] == {
        "id": "CAT_FLORES",
        "name": "Flores y ramos",
        "checked_at": body["catalog"]["checked_at"],
    }
    assert body["catalog_state"] == "linked"
    assert sim.names() == ["list_catalogs", "link_catalog"]
    assert sim.calls[1][1]["waba_id"] == "W-1"

    fila = await _reload(db_session, canal.id)
    assert fila.config["catalog_id"] == "CAT_FLORES"
    assert fila.config["catalog_name"] == "Flores y ramos"
    audit = await db_session.scalar(
        sa.select(AuditLog)
        .where(AuditLog.action == "console.channel.catalog")
        .order_by(AuditLog.created_at.desc())
    )
    assert audit is not None
    assert audit.after_json["catalog"]["id"] == "CAT_FLORES"
    assert audit.after_json["meta"] == {"linked": "CAT_FLORES"}
    assert audit.before_json == {"catalog": None}


async def test_changing_unlinks_the_old_one_first(
    client, console_world, db_session, monkeypatch
) -> None:
    a = console_world["a"]
    sim = _sim(monkeypatch, catalogs=[FLORES, PLANTAS], linked=PLANTAS)
    canal = await _canal(
        db_session, a["tenant_id"], catalog_id="CAT_PLANTAS", catalog_name="Plantas"
    )
    r = await client.put(
        _url(a, canal, "catalog"), json={"catalog_id": "CAT_FLORES"}, headers=a["headers"]()
    )
    assert r.status_code == 200, r.text
    assert r.json()["catalog"]["id"] == "CAT_FLORES"
    assert sim.names() == ["list_catalogs", "unlink_catalog", "link_catalog"]
    assert sim.calls[1][1]["catalog_id"] == "CAT_PLANTAS"
    audit = await db_session.scalar(
        sa.select(AuditLog)
        .where(AuditLog.action == "console.channel.catalog")
        .order_by(AuditLog.created_at.desc())
    )
    assert audit is not None
    assert audit.after_json["meta"] == {"unlinked": "CAT_PLANTAS", "linked": "CAT_FLORES"}


async def test_when_the_new_one_fails_after_unlinking_the_card_says_so(
    client, console_world, db_session, monkeypatch
) -> None:
    """Honesto y reversible: sin catálogo y con el motivo, no fingiendo que el
    viejo sigue."""
    a = console_world["a"]
    _sim(
        monkeypatch,
        catalogs=[FLORES, PLANTAS],
        linked=PLANTAS,
        fail={"link_catalog": MetaAPIError("(#100) Invalid parameter", status_code=400, code=100)},
    )
    canal = await _canal(db_session, a["tenant_id"], catalog_id="CAT_PLANTAS")
    r = await client.put(
        _url(a, canal, "catalog"), json={"catalog_id": "CAT_FLORES"}, headers=a["headers"]()
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["catalog"] is None
    assert body["catalog_state"] == "none"
    assert body["catalog_error"]["code"] == "catalog_meta_rejected"
    assert "Invalid parameter" in body["catalog_error"]["message"]


async def test_a_catalog_of_another_business_is_refused_and_nothing_changes(
    client, console_world, db_session, monkeypatch
) -> None:
    a = console_world["a"]
    sim = _sim(monkeypatch, catalogs=[FLORES])
    canal = await _canal(db_session, a["tenant_id"])
    r = await client.put(
        _url(a, canal, "catalog"), json={"catalog_id": "CAT_AJENO"}, headers=a["headers"]()
    )
    assert r.status_code == 409
    assert r.json()["detail"]["code"] == "catalog_not_owned"
    assert sim.names() == ["list_catalogs"]
    fila = await _reload(db_session, canal.id)
    assert "catalog_id" not in fila.config


# ── T012 · desconectar ───────────────────────────────────────────────────


async def test_clearing_unlinks_and_forgets(
    client, console_world, db_session, monkeypatch, fake_redis
) -> None:
    a = console_world["a"]
    sim = _sim(monkeypatch, linked=FLORES)
    canal = await _canal(
        db_session, a["tenant_id"], catalog_id="CAT_FLORES", catalog_name="Flores y ramos"
    )
    await fake_redis.set("nexus:catalog:waba:W-1", "{}")
    r = await client.delete(_url(a, canal, "catalog"), headers=a["headers"]())
    assert r.status_code == 200, r.text
    assert r.json()["catalog"] is None and r.json()["catalog_state"] == "none"
    assert sim.names() == ["unlink_catalog"]
    fila = await _reload(db_session, canal.id)
    assert "catalog_id" not in fila.config and "catalog_name" not in fila.config
    assert await fake_redis.get("nexus:catalog:waba:W-1") is None, "la caché no se invalidó"


async def test_clearing_without_a_catalog_does_not_call_meta(
    client, console_world, db_session, monkeypatch
) -> None:
    a = console_world["a"]
    sim = _sim(monkeypatch)
    canal = await _canal(db_session, a["tenant_id"])
    r = await client.delete(_url(a, canal, "catalog"), headers=a["headers"]())
    assert r.status_code == 200
    assert sim.calls == []


async def test_if_meta_refuses_to_unlink_the_catalog_stays_and_says_why(
    client, console_world, db_session, monkeypatch
) -> None:
    a = console_world["a"]
    _sim(monkeypatch, linked=FLORES, fail={"unlink_catalog": _permission()})
    canal = await _canal(
        db_session, a["tenant_id"], catalog_id="CAT_FLORES", catalog_name="Flores y ramos"
    )
    r = await client.delete(_url(a, canal, "catalog"), headers=a["headers"]())
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["catalog"]["id"] == "CAT_FLORES"
    assert body["catalog_error"]["code"] == "catalog_permission_missing"


# ── T013 · permisos ──────────────────────────────────────────────────────


async def test_reading_needs_read_and_writing_needs_write(
    client, console_world, db_session, monkeypatch
) -> None:
    a = console_world["a"]
    _sim(monkeypatch, catalogs=[FLORES])
    canal = await _canal(db_session, a["tenant_id"])
    analista = await add_console_member(db_session, partner_id=a["partner_id"], role="analyst")
    r = await client.get(_url(a, canal, "catalogs"), headers=analista["headers"]())
    assert r.status_code == 200, r.text
    r = await client.put(
        _url(a, canal, "catalog"), json={"catalog_id": "CAT_FLORES"}, headers=analista["headers"]()
    )
    assert r.status_code == 403
    r = await client.delete(_url(a, canal, "catalog"), headers=analista["headers"]())
    assert r.status_code == 403


# ── T009 · la conciliación al listar (research D3) ───────────────────────


async def _overview(client, who):
    r = await client.get(
        f"/console/clients/{who['ref']}/channels/overview", headers=who["headers"]()
    )
    assert r.status_code == 200, r.text
    return r.json()


async def test_the_card_adopts_what_meta_has(
    client, console_world, db_session, monkeypatch
) -> None:
    a = console_world["a"]
    sim = _sim(monkeypatch, linked=FLORES)
    canal = await _canal(db_session, a["tenant_id"])  # sin catálogo guardado
    body = await _overview(client, a)
    (ch,) = [c for c in body["channels"] if c["id"] == str(canal.id)]
    assert ch["catalog"]["id"] == "CAT_FLORES" and ch["catalog"]["name"] == "Flores y ramos"
    assert ch["catalog_state"] == "linked"
    assert sim.names() == ["get_linked_catalog"]
    fila = await _reload(db_session, canal.id)
    assert fila.config["catalog_id"] == "CAT_FLORES"


async def test_metas_truth_replaces_ours_and_absence_erases(
    client, console_world, db_session, monkeypatch
) -> None:
    a = console_world["a"]
    _sim(monkeypatch, linked=PLANTAS)
    canal = await _canal(
        db_session, a["tenant_id"], catalog_id="CAT_FLORES", catalog_name="Flores y ramos"
    )
    body = await _overview(client, a)
    (ch,) = [c for c in body["channels"] if c["id"] == str(canal.id)]
    assert ch["catalog"]["id"] == "CAT_PLANTAS"

    _sim(monkeypatch, linked=None)
    # La caché de la WABA aún dice PLANTAS: la conciliación la respeta 5 min.
    body = await _overview(client, a)
    (ch,) = [c for c in body["channels"] if c["id"] == str(canal.id)]
    assert ch["catalog"]["id"] == "CAT_PLANTAS"


async def test_a_check_that_fails_keeps_ours_and_says_unchecked(
    client, console_world, db_session, monkeypatch
) -> None:
    a = console_world["a"]
    sim = _sim(
        monkeypatch, fail={"get_linked_catalog": MetaTransientError("down", status_code=503)}
    )
    canal = await _canal(
        db_session, a["tenant_id"], catalog_id="CAT_FLORES", catalog_name="Flores y ramos"
    )
    body = await _overview(client, a)
    (ch,) = [c for c in body["channels"] if c["id"] == str(canal.id)]
    assert ch["catalog"]["id"] == "CAT_FLORES"
    assert ch["catalog_state"] == "unchecked"
    assert sim.names() == ["get_linked_catalog"]
    fila = await _reload(db_session, canal.id)
    assert fila.config["catalog_id"] == "CAT_FLORES", "borró lo guardado sin saber"


async def test_permission_missing_is_a_state_not_an_error(
    client, console_world, db_session, monkeypatch
) -> None:
    a = console_world["a"]
    _sim(monkeypatch, fail={"get_linked_catalog": _permission()})
    canal = await _canal(db_session, a["tenant_id"])
    body = await _overview(client, a)
    (ch,) = [c for c in body["channels"] if c["id"] == str(canal.id)]
    assert ch["catalog_state"] == "permission_missing"
    assert ch["catalog"] is None


async def test_one_call_per_waba_and_none_without_credentials(
    client, console_world, db_session, monkeypatch
) -> None:
    a = console_world["a"]
    sim = _sim(monkeypatch, linked=FLORES)
    uno = await _canal(db_session, a["tenant_id"])
    dos = _channel(a["tenant_id"], waba_id="W-1", business_id="BIZ-1")
    suelto = _channel(a["tenant_id"], waba_id="W-2")  # sin credencial de canal ni de tenant
    suelto.status = ChannelStatus.DISCONNECTED
    db_session.add_all([dos, suelto])
    await db_session.commit()
    body = await _overview(client, a)
    ids = {c["id"]: c for c in body["channels"]}
    assert sim.names() == ["get_linked_catalog"], "una cuenta, una llamada"
    assert ids[str(uno.id)]["catalog"]["id"] == "CAT_FLORES"
    assert ids[str(dos.id)]["catalog"]["id"] == "CAT_FLORES", (
        "dos números de la misma cuenta comparten catálogo"
    )
    assert ids[str(suelto.id)]["catalog_state"] == "none"


# ── T003 · el medidor no ve nada ─────────────────────────────────────────


async def test_the_catalog_costs_nothing_the_meter_sees(
    client, console_world, db_session, monkeypatch
) -> None:
    a = console_world["a"]
    _sim(monkeypatch, catalogs=[FLORES], linked=None)
    canal = await _canal(db_session, a["tenant_id"])

    async def eventos() -> int:
        return int(
            await db_session.scalar(
                sa.text("SELECT count(*) FROM usage_events WHERE tenant_id = :t"),
                {"t": str(a["tenant_id"])},
            )
            or 0
        )

    antes = await eventos()
    await client.get(_url(a, canal, "catalogs"), headers=a["headers"]())
    await client.put(
        _url(a, canal, "catalog"), json={"catalog_id": "CAT_FLORES"}, headers=a["headers"]()
    )
    await client.delete(_url(a, canal, "catalog"), headers=a["headers"]())
    assert await eventos() == antes


def _unused() -> None:  # pragma: no cover — mantiene el import si se poda un test
    _ = uuid


# ── Coexistencia (2026-10-01): la app del teléfono tiene el catálogo ─────


def _smb() -> MetaAPIError:
    return MetaAPIError(
        "(#10) This operation can not be performed on SMB business type",
        status_code=400,
        code=10,
    )


async def test_a_coexistence_number_is_not_asked_and_keeps_its_catalog(
    client, console_world, db_session, monkeypatch
) -> None:
    a = console_world["a"]
    sim = _sim(monkeypatch, catalogs=[FLORES], linked=None)
    canal = await _canal(db_session, a["tenant_id"], mode="coexistence", catalog_id="CAT_FLORES")
    r = await client.get(f"/console/clients/{a['ref']}/channels/overview", headers=a["headers"]())
    assert r.status_code == 200, r.text
    row = next(c for c in r.json()["channels"] if c["id"] == str(canal.id))
    assert row["catalog_state"] == "coexistence"
    assert row["catalog"]["id"] == "CAT_FLORES"
    assert sim.names() == []


async def test_meta_refusing_by_smb_teaches_the_mode_instead_of_blaming_a_permission(
    client, console_world, db_session, monkeypatch
) -> None:
    a = console_world["a"]
    _sim(monkeypatch, fail={"get_linked_catalog": _smb()})
    canal = await _canal(db_session, a["tenant_id"], catalog_id="CAT_FLORES")
    r = await client.get(f"/console/clients/{a['ref']}/channels/overview", headers=a["headers"]())
    row = next(c for c in r.json()["channels"] if c["id"] == str(canal.id))
    assert row["catalog_state"] == "coexistence"
    assert row["catalog"]["id"] == "CAT_FLORES"
    fila = await _reload(db_session, canal.id)
    assert fila.config["mode"] == "coexistence"


async def test_on_a_coexistence_number_the_catalog_is_declared_not_linked(
    client, console_world, db_session, monkeypatch
) -> None:
    a = console_world["a"]
    sim = _sim(monkeypatch, catalogs=[FLORES, PLANTAS], linked=None)
    canal = await _canal(db_session, a["tenant_id"], mode="coexistence")
    r = await client.put(
        _url(a, canal, "catalog"), json={"catalog_id": "CAT_FLORES"}, headers=a["headers"]()
    )
    assert r.status_code == 200, r.text
    assert r.json()["catalog_state"] == "coexistence"
    assert r.json()["catalog"]["name"] == "Flores y ramos"
    assert sim.names() == ["list_catalogs"]  # ni link ni unlink
    fila = await _reload(db_session, canal.id)
    assert fila.config["catalog_id"] == "CAT_FLORES"

    # Sigue exigiendo que el catálogo sea del negocio.
    bad = await client.put(
        _url(a, canal, "catalog"), json={"catalog_id": "CAT_OTRO"}, headers=a["headers"]()
    )
    assert bad.status_code == 409 and bad.json()["detail"]["code"] == "catalog_not_owned"

    gone = await client.delete(_url(a, canal, "catalog"), headers=a["headers"]())
    assert gone.status_code == 200 and gone.json()["catalog"] is None
    assert gone.json()["catalog_state"] == "coexistence"
    assert "unlink_catalog" not in sim.names()


async def test_linking_that_meta_refuses_by_smb_declares_and_learns(
    client, console_world, db_session, monkeypatch
) -> None:
    a = console_world["a"]
    sim = _sim(monkeypatch, catalogs=[FLORES], linked=None, fail={"link_catalog": _smb()})
    canal = await _canal(db_session, a["tenant_id"])
    r = await client.put(
        _url(a, canal, "catalog"), json={"catalog_id": "CAT_FLORES"}, headers=a["headers"]()
    )
    assert r.status_code == 200, r.text
    assert r.json()["catalog_state"] == "coexistence"
    assert r.json()["catalog_error"] is None
    fila = await _reload(db_session, canal.id)
    assert fila.config["mode"] == "coexistence"
    assert fila.config["catalog_id"] == "CAT_FLORES"
    assert sim.names() == ["list_catalogs", "link_catalog"]
