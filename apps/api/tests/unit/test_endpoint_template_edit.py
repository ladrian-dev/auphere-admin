"""Spec 075 — editar una plantilla desde la consola y desde el panel.

Meta se simula con ``respx`` sobre Graph: la lista de la cuenta (dos
lecturas: antes de editar y después, sin caché) y ``POST /{template_id}``.
"""

from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

import httpx
import pytest
import pytest_asyncio
import respx
import sqlalchemy as sa
from nexus_channels.whatsapp_meta.credentials import MetaCredentials
from nexus_channels.whatsapp_meta.meta_client import META_GRAPH_BASE_URL
from structlog.testing import capture_logs

from nexus_api.db.models import (
    AuditLog,
    Message,
    MessageDirection,
    MessageStatus,
    TenantCredentials,
)
from nexus_api.db.models.conversation import WhatsAppTemplateStatus
from nexus_api.services import operator_identity
from nexus_api.services import whatsapp_template_edit as rules
from nexus_api.services.whatsapp_templates import TemplateOut, invalidate_template_cache
from tests.conftest import add_console_member, make_inbox

pytestmark = pytest.mark.asyncio

_ADMIN = {"Authorization": "Bearer test-admin-token"}
WABA = "WABA_E"
TPL_ID = "9001"


# ── Meta, con la forma de su lista ──────────────────────────────────────────


def _raw(
    *,
    name: str = "cita_recordatorio",
    language: str = "es",
    status: str = "REJECTED",
    category: str = "UTILITY",
    body: str = "Hola {{nombre}}, te esperamos.",
    examples: dict[str, str] | None = None,
    footer: str | None = "Barbería Centro",
    header: dict[str, Any] | None = None,
    tpl_id: str = TPL_ID,
) -> dict[str, Any]:
    examples = {"nombre": "Camila"} if examples is None else examples
    comps: list[dict[str, Any]] = []
    if header is not None:
        comps.append(header)
    b: dict[str, Any] = {"type": "BODY", "text": body}
    names = (
        list(dict.fromkeys(rules.BODY_VAR_RE.findall(body)))
        if hasattr(rules, "BODY_VAR_RE")
        else []
    )
    if examples:
        b["example"] = {
            "body_text_named_params": [
                {"param_name": n, "example": examples[n]} for n in names or examples
            ]
        }
    comps.append(b)
    if footer:
        comps.append({"type": "FOOTER", "text": footer})
    return {
        "id": tpl_id,
        "name": name,
        "language": language,
        "status": status,
        "category": category,
        "components": comps,
    }


def _list(*raws: dict[str, Any]) -> httpx.Response:
    return httpx.Response(200, json={"data": list(raws)})


def _version(raw: dict[str, Any]) -> str:
    return rules.template_version(
        TemplateOut(
            id=raw["id"],
            name=raw["name"],
            language=raw["language"],
            category=raw["category"],
            status=raw["status"],
            components=raw["components"],
        )
    )


def _edit_body(raw: dict[str, Any], **over: Any) -> dict[str, Any]:
    body: dict[str, Any] = {
        "version": _version(raw),
        "body_text": "Hola {{nombre}}, te esperamos con gusto.",
        "footer_text": "Barbería Centro",
        "examples": {"nombre": "Camila"},
    }
    body.update(over)
    return body


async def _seed_creds(db_session, tenant_id: uuid.UUID, *, waba_id: str = WABA) -> None:
    creds = MetaCredentials(
        bisuat=f"EAA-{waba_id}",
        waba_id=waba_id,
        phone_number_id=f"PN_{waba_id}",
        business_id="BIZ",
        display_phone_number="+34600000001",
        verify_token="v" * 32,
    )
    async with db_session.begin():
        await db_session.execute(
            sa.text("SELECT set_config('app.tenant_id', :t, true)"), {"t": str(tenant_id)}
        )
        await db_session.execute(sa.text("SET LOCAL ROLE nexus_app"))
        db_session.add(
            TenantCredentials(
                tenant_id=tenant_id,
                integration="meta_whatsapp",
                encrypted_payload=creds.to_payload(),
                needs_reauth=False,
            )
        )


async def _mirror(db_session, **values: Any) -> None:
    db_session.add(WhatsAppTemplateStatus(waba_id=WABA, language="es", **values))
    await db_session.commit()


async def _mirror_row(db_session, name: str, language: str = "es", *, waba_id: str = WABA):
    db_session.expire_all()
    return (
        await db_session.execute(
            sa.select(WhatsAppTemplateStatus).where(
                WhatsAppTemplateStatus.waba_id == waba_id,
                WhatsAppTemplateStatus.template_name == name,
                WhatsAppTemplateStatus.language == language,
            )
        )
    ).scalar_one_or_none()


async def _edit_audits(db_session, action: str = "console.template.edit") -> list[AuditLog]:
    db_session.expire_all()
    rows = await db_session.execute(sa.select(AuditLog).where(AuditLog.action == action))
    return list(rows.scalars())


@pytest.fixture(autouse=True)
def _fresh_cache():
    invalidate_template_cache()
    yield
    invalidate_template_cache()


@pytest_asyncio.fixture
async def world(client, console_world, db_session) -> dict[str, Any]:
    a = console_world["a"]
    await _seed_creds(db_session, a["tenant_id"])
    a["url"] = f"/console/clients/{a['ref']}/channels/whatsapp/templates"
    return a


def _put(world: dict[str, Any], name: str = "cita_recordatorio", language: str = "es") -> str:
    return f"{world['url']}/{name}/{language}"


# ── la lista (T011) ─────────────────────────────────────────────────────────


async def test_list_rows_carry_blocker_draft_version_and_system_variables(client, world) -> None:
    rejected = _raw()
    image = _raw(
        name="promo_imagen",
        tpl_id="9002",
        header={"type": "HEADER", "format": "IMAGE", "example": {"header_handle": ["x"]}},
    )
    reserva = _raw(
        name="reserva_recordatorio",
        tpl_id="9003",
        status="APPROVED",
        body="Hola {{nombre}}",
    )
    async with respx.mock(base_url=META_GRAPH_BASE_URL, assert_all_called=False) as mock:
        mock.get(f"/{WABA}/message_templates").mock(return_value=_list(rejected, image, reserva))
        r = await client.get(world["url"], headers=world["headers"]())
    assert r.status_code == 200, r.text
    rows = {row["name"]: row for row in r.json()["items"]}
    assert rows["cita_recordatorio"]["edit_blocker"] is None
    assert rows["cita_recordatorio"]["draft"]["body_text"] == "Hola {{nombre}}, te esperamos."
    assert rows["cita_recordatorio"]["version"] == _version(rejected)
    assert rows["cita_recordatorio"]["system_variables"] is None
    assert rows["promo_imagen"]["edit_blocker"] == "media_header"
    assert rows["promo_imagen"]["draft"] is None
    assert rows["reserva_recordatorio"]["system_variables"]["mode"] == "exact"


# ── editar una rechazada (T011, US1) ────────────────────────────────────────


async def test_edit_rejected_reaches_meta_updates_mirror_and_audits(
    client, world, db_session
) -> None:
    before = _raw()
    after = {**_raw(status="PENDING", body="Hola {{nombre}}, te esperamos con gusto.")}
    await _mirror(
        db_session,
        template_name="cita_recordatorio",
        status="REJECTED",
        reason="INVALID_FORMAT",
        tenant_id=world["tenant_id"],
        last_event_at=datetime.now(UTC) - timedelta(hours=1),
    )
    async with respx.mock(base_url=META_GRAPH_BASE_URL, assert_all_called=False) as mock:
        listing = mock.get(f"/{WABA}/message_templates").mock(
            side_effect=[_list(before), _list(after)]
        )
        edit = mock.post(f"/{TPL_ID}").respond(200, json={"success": True})
        r = await client.put(_put(world), headers=world["headers"](), json=_edit_body(before))
    assert r.status_code == 200, r.text
    assert r.json() == {
        "name": "cita_recordatorio",
        "language": "es",
        "changed": True,
        "status": "PENDING",
        "category": "UTILITY",
    }
    assert listing.call_count == 2  # antes y después, sin caché
    # 5.2: el próximo envío (difusiones, cobros, Reservas) lee la versión
    # nueva: la caché de la cuenta queda vacía tras editar.
    from nexus_api.services import whatsapp_templates as wt

    assert WABA not in wt._template_cache
    sent = json.loads(edit.calls.last.request.content)
    assert "name" not in sent and "language" not in sent
    assert sent["components"] == after["components"]
    assert sent["parameter_format"] == "NAMED"
    assert "category" not in sent  # no cambió

    row = await _mirror_row(db_session, "cita_recordatorio")
    assert row is not None
    assert row.status.upper() == "PENDING"
    assert row.reason is None

    audits = await _edit_audits(db_session)
    assert len(audits) == 1
    audit = audits[0]
    assert audit.actor.startswith("console:")
    assert audit.target == "template:cita_recordatorio:es"
    assert audit.before_json["components"] == before["components"]
    assert audit.after_json["components"] == after["components"]
    assert audit.after_json["meta_status"] == "PENDING"
    # 8.4: the template and its language travel with the row, so the console's
    # audit sentence names the template (``{template}``), not «unknown».
    assert (audit.after_json["name"], audit.after_json["language"]) == ("cita_recordatorio", "es")
    from nexus_api.api.console import audit as audit_module

    row_copy = AuditLog(
        actor=audit.actor,
        action=audit.action,
        target=audit.target,
        before_json=dict(audit.before_json),
        after_json=dict(audit.after_json),
    )
    await db_session.rollback()  # the vocabulary is read in a transaction of its own
    audit_module.reset_vocabulary_cache_for_tests()
    vocab = await audit_module.load_vocabulary(db_session, force=True)
    sentence = audit_module.summarise(
        row_copy, "Demo", vocab, "es", names_by_ref={}, connector_names={}, partner_name="Demo"
    )
    assert "editó la plantilla cita_recordatorio" in sentence, sentence


async def test_a_newer_webhook_verdict_is_not_overwritten(client, world, db_session) -> None:
    before = _raw()
    after = _raw(status="PENDING", body="Hola {{nombre}}, te esperamos con gusto.")
    await _mirror(
        db_session,
        template_name="cita_recordatorio",
        status="APPROVED",
        tenant_id=world["tenant_id"],
        last_event_at=datetime.now(UTC) + timedelta(minutes=5),
    )
    async with respx.mock(base_url=META_GRAPH_BASE_URL, assert_all_called=False) as mock:
        mock.get(f"/{WABA}/message_templates").mock(side_effect=[_list(before), _list(after)])
        mock.post(f"/{TPL_ID}").respond(200, json={"success": True})
        r = await client.put(_put(world), headers=world["headers"](), json=_edit_body(before))
    assert r.status_code == 200, r.text
    row = await _mirror_row(db_session, "cita_recordatorio")
    assert row is not None and row.status.upper() == "APPROVED"


async def test_paused_template_can_change_category(client, world) -> None:
    before = _raw(status="PAUSED")
    after = _raw(status="PENDING", category="MARKETING")
    async with respx.mock(base_url=META_GRAPH_BASE_URL, assert_all_called=False) as mock:
        mock.get(f"/{WABA}/message_templates").mock(side_effect=[_list(before), _list(after)])
        edit = mock.post(f"/{TPL_ID}").respond(200, json={"success": True})
        r = await client.put(
            _put(world),
            headers=world["headers"](),
            json=_edit_body(
                before,
                category="MARKETING",
                body_text="Hola {{nombre}}, te esperamos.",
            ),
        )
    assert r.status_code == 200, r.text
    assert json.loads(edit.calls.last.request.content)["category"] == "MARKETING"


async def test_nothing_changed_does_not_call_meta(client, world, db_session) -> None:
    before = _raw()
    async with respx.mock(base_url=META_GRAPH_BASE_URL, assert_all_called=False) as mock:
        mock.get(f"/{WABA}/message_templates").mock(return_value=_list(before))
        edit = mock.post(f"/{TPL_ID}").respond(200, json={"success": True})
        r = await client.put(
            _put(world),
            headers=world["headers"](),
            json=_edit_body(before, body_text="Hola {{nombre}}, te esperamos."),
        )
    assert r.status_code == 200, r.text
    assert r.json()["changed"] is False
    assert edit.call_count == 0
    assert await _edit_audits(db_session) == []


@pytest.mark.parametrize(
    ("raw", "path", "body_over", "status_code", "code"),
    [
        (_raw(), ("cita_recordatorio", "en"), {}, 404, "template_not_found"),
        (_raw(), ("otra_plantilla", "es"), {}, 404, "template_not_found"),
        (_raw(), ("cita_recordatorio", "es"), {"version": "0" * 16}, 409, "template_changed"),
        (_raw(status="PENDING"), ("cita_recordatorio", "es"), {}, 409, "not_editable"),
        (
            _raw(header={"type": "HEADER", "format": "IMAGE", "example": {"header_handle": ["x"]}}),
            ("cita_recordatorio", "es"),
            {},
            409,
            "not_editable",
        ),
        (
            _raw(),
            ("cita_recordatorio", "es"),
            {"body_text": "Hola {{nombre}} y {{nuevo}}", "examples": {"nombre": "Ana"}},
            422,
            "missing_examples",
        ),
    ],
)
async def test_refusals_never_reach_meta(
    client, world, raw, path, body_over, status_code, code
) -> None:
    async with respx.mock(base_url=META_GRAPH_BASE_URL, assert_all_called=False) as mock:
        mock.get(f"/{WABA}/message_templates").mock(return_value=_list(raw))
        edit = mock.post(f"/{TPL_ID}").respond(200, json={"success": True})
        r = await client.put(
            _put(world, *path), headers=world["headers"](), json=_edit_body(raw, **body_over)
        )
    assert r.status_code == status_code, r.text
    assert r.json()["detail"]["code"] == code
    assert edit.call_count == 0


async def test_not_editable_says_which_blocker(client, world) -> None:
    raw = _raw(status="DISABLED")
    async with respx.mock(base_url=META_GRAPH_BASE_URL, assert_all_called=False) as mock:
        mock.get(f"/{WABA}/message_templates").mock(return_value=_list(raw))
        r = await client.put(_put(world), headers=world["headers"](), json=_edit_body(raw))
    assert r.json()["detail"] == {"code": "not_editable", "blocker": "status"}


async def test_body_refuses_meta_ids_and_bad_names(client, world) -> None:
    raw = _raw()
    r = await client.put(
        _put(world),
        headers=world["headers"](),
        json={**_edit_body(raw), "template_id": "123", "waba_id": "WABA_X"},
    )
    assert r.status_code == 422
    r = await client.put(_put(world, "Bad-Name"), headers=world["headers"](), json=_edit_body(raw))
    assert r.status_code == 400


async def test_meta_refusal_goes_to_the_screen_not_to_the_logs(client, world, db_session) -> None:
    raw = _raw()
    secret = "Texto de Meta que no puede acabar en un registro"
    async with respx.mock(base_url=META_GRAPH_BASE_URL, assert_all_called=False) as mock:
        mock.get(f"/{WABA}/message_templates").mock(return_value=_list(raw))
        mock.post(f"/{TPL_ID}").respond(
            400,
            json={
                "error": {
                    "message": secret,
                    "code": 100,
                    "error_subcode": 2388299,
                    "error_user_msg": secret,
                }
            },
        )
        with capture_logs() as logs:
            r = await client.put(_put(world), headers=world["headers"](), json=_edit_body(raw))
    assert r.status_code == 422, r.text
    assert r.json()["detail"] == {
        "code": "meta_rejected",
        "meta_code": 100,
        "meta_subcode": 2388299,
        "user_message": secret,
    }
    assert secret not in json.dumps(logs, default=str)
    assert await _edit_audits(db_session) == []


async def test_readers_cannot_edit(client, world, db_session) -> None:
    analyst = await add_console_member(db_session, partner_id=world["partner_id"], role="analyst")
    raw = _raw()
    r = await client.put(_put(world), headers=analyst["headers"](), json=_edit_body(raw))
    assert r.status_code == 403


# ── el panel (T012) ─────────────────────────────────────────────────────────


@pytest_asyncio.fixture
async def operator(db_session):
    async with db_session.begin():
        account = await operator_identity.create_account(
            db_session,
            email=f"ops-075-{uuid.uuid4().hex[:8]}@auphere.test",
            password="operator-password-1",
            display_name="Ops",
        )
    return account


async def test_panel_needs_the_operator(client, world) -> None:
    raw = _raw()
    r = await client.put(
        f"/admin/tenants/{world['tenant_id']}/whatsapp/templates/cita_recordatorio/es",
        headers=_ADMIN,
        json=_edit_body(raw),
    )
    assert r.status_code == 400


async def test_panel_edits_with_the_same_rules_and_names_the_operator(
    client, world, db_session, operator
) -> None:
    email = operator.email  # leído antes de que una consulta lo expire
    before = _raw()
    after = _raw(status="PENDING", body="Hola {{nombre}}, te esperamos con gusto.")
    url = f"/admin/tenants/{world['tenant_id']}/whatsapp/templates"
    ops = {**_ADMIN, "X-Operator-Id": str(operator.id)}
    async with respx.mock(base_url=META_GRAPH_BASE_URL, assert_all_called=False) as mock:
        mock.get(f"/{WABA}/message_templates").mock(
            side_effect=[_list(before), _list(before), _list(after)]
        )
        mock.post(f"/{TPL_ID}").respond(200, json={"success": True})
        listed = await client.get(url, headers=_ADMIN)
        assert listed.status_code == 200, listed.text
        row = next(t for t in listed.json()["templates"] if t["name"] == "cita_recordatorio")
        assert row["edit_blocker"] is None and row["version"] == _version(before)
        r = await client.put(f"{url}/cita_recordatorio/es", headers=ops, json=_edit_body(before))
    assert r.status_code == 200, r.text
    audits = await _edit_audits(db_session, "admin.template.edit")
    assert [a.actor for a in audits] == [f"operator:{email}"]


# ── US2: aprobadas ──────────────────────────────────────────────────────────


async def test_approved_needs_confirmation_first(client, world) -> None:
    before = _raw(status="APPROVED")
    after = _raw(status="PENDING", body="Hola {{nombre}}, te esperamos con gusto.")
    async with respx.mock(base_url=META_GRAPH_BASE_URL, assert_all_called=False) as mock:
        mock.get(f"/{WABA}/message_templates").mock(
            side_effect=[_list(before), _list(before), _list(after)]
        )
        edit = mock.post(f"/{TPL_ID}").respond(200, json={"success": True})
        r = await client.put(_put(world), headers=world["headers"](), json=_edit_body(before))
        assert r.status_code == 409, r.text
        assert r.json()["detail"] == {
            "code": "confirmation_required",
            "reasons": [{"kind": "approved"}],
        }
        assert edit.call_count == 0
        r = await client.put(
            _put(world), headers=world["headers"](), json=_edit_body(before, confirm=True)
        )
    assert r.status_code == 200, r.text
    assert edit.call_count == 1


async def test_approved_keeps_its_category(client, world) -> None:
    raw = _raw(status="APPROVED")
    async with respx.mock(base_url=META_GRAPH_BASE_URL, assert_all_called=False) as mock:
        mock.get(f"/{WABA}/message_templates").mock(return_value=_list(raw))
        edit = mock.post(f"/{TPL_ID}").respond(200, json={"success": True})
        r = await client.put(
            _put(world),
            headers=world["headers"](),
            json=_edit_body(raw, category="MARKETING", confirm=True),
        )
    assert r.status_code == 422, r.text
    assert r.json()["detail"]["code"] == "category_locked"
    assert edit.call_count == 0


async def _queue(db_session, world: dict[str, Any], *, name: str, language: str, n: int) -> None:
    if "conv_id" not in world:
        inbox = await make_inbox(
            db_session, partner_id=world["partner_id"], tenant_id=world["tenant_id"]
        )
        world["conv_id"] = inbox["conversations"][0]
    conv_id = world["conv_id"]
    for _ in range(n):
        db_session.add(
            Message(
                id=uuid.uuid4(),
                tenant_id=world["tenant_id"],
                conversation_id=conv_id,
                direction=MessageDirection.OUTBOUND,
                status=MessageStatus.PENDING,
                content=f"[template:{name}]",
                actor_kind="system",
                template_payload={"name": name, "language": language, "params": {"body": {}}},
            )
        )
    await db_session.commit()


async def test_renamed_variable_warns_about_queued_sends(
    client, world, console_world, db_session
) -> None:
    await _queue(db_session, world, name="cita_recordatorio", language="es", n=3)
    await _queue(db_session, world, name="cita_recordatorio", language="en", n=1)
    other = console_world["b"]
    await _queue(db_session, other, name="cita_recordatorio", language="es", n=2)
    raw = _raw()
    async with respx.mock(base_url=META_GRAPH_BASE_URL, assert_all_called=False) as mock:
        mock.get(f"/{WABA}/message_templates").mock(return_value=_list(raw))
        edit = mock.post(f"/{TPL_ID}").respond(200, json={"success": True})
        r = await client.put(
            _put(world),
            headers=world["headers"](),
            json=_edit_body(
                raw, body_text="Hola {{cliente}}, te esperamos.", examples={"cliente": "Ana"}
            ),
        )
    assert r.status_code == 409, r.text
    assert r.json()["detail"] == {
        "code": "confirmation_required",
        "reasons": [{"kind": "queued_sends", "count": 3}],
    }
    assert edit.call_count == 0


async def test_same_variables_do_not_mention_queued_sends(client, world, db_session) -> None:
    await _queue(db_session, world, name="cita_recordatorio", language="es", n=3)
    before = _raw()
    after = _raw(status="PENDING", body="Hola {{nombre}}, te esperamos con gusto.")
    async with respx.mock(base_url=META_GRAPH_BASE_URL, assert_all_called=False) as mock:
        mock.get(f"/{WABA}/message_templates").mock(side_effect=[_list(before), _list(after)])
        mock.post(f"/{TPL_ID}").respond(200, json={"success": True})
        r = await client.put(_put(world), headers=world["headers"](), json=_edit_body(before))
    assert r.status_code == 200, r.text


# ── US3: plantillas que Auphere manda por su nombre ─────────────────────────


async def test_reservas_template_keeps_exactly_its_variables(client, world) -> None:
    from nexus_api.services.reservations import templates as reservas

    wanted = list(reservas.VARIABLES["reserva_recordatorio"])
    body = " ".join(f"{{{{{v}}}}}" for v in wanted)
    raw = _raw(
        name="reserva_recordatorio",
        body=f"Hola {body}.",
        examples={v: "x" for v in wanted},
    )
    without_first = " ".join(f"{{{{{v}}}}}" for v in wanted[1:])
    async with respx.mock(base_url=META_GRAPH_BASE_URL, assert_all_called=False) as mock:
        mock.get(f"/{WABA}/message_templates").mock(return_value=_list(raw))
        edit = mock.post(f"/{TPL_ID}").respond(200, json={"success": True})
        r = await client.put(
            _put(world, "reserva_recordatorio"),
            headers=world["headers"](),
            json=_edit_body(
                raw,
                body_text=f"Hola {without_first} {{{{otra}}}}.",
                examples={**{v: "x" for v in wanted[1:]}, "otra": "y"},
            ),
        )
    assert r.status_code == 422, r.text
    assert r.json()["detail"] == {
        "code": "system_variables",
        "missing": [wanted[0]],
        "extra": ["otra"],
    }
    assert edit.call_count == 0


async def test_cobros_template_cannot_lose_a_variable_or_gain_an_unknown_one(client, world) -> None:
    raw = _raw(
        name=rules.COBROS_VENCIDO,
        body="Hola {{cliente}}, debes {{monto}}.",
        examples={"cliente": "Ana", "monto": "50"},
    )
    cases = [
        ("Hola {{cliente}}, revisa tu cuenta.", {"cliente": "Ana"}, ["monto"], []),
        (
            "Hola {{cliente}}, debes {{monto}} en {{iban}}.",
            {"cliente": "Ana", "monto": "50", "iban": "ES00"},
            [],
            ["iban"],
        ),
    ]
    for body_text, examples, missing, extra in cases:
        async with respx.mock(base_url=META_GRAPH_BASE_URL, assert_all_called=False) as mock:
            mock.get(f"/{WABA}/message_templates").mock(return_value=_list(raw))
            r = await client.put(
                _put(world, rules.COBROS_VENCIDO),
                headers=world["headers"](),
                json=_edit_body(raw, body_text=body_text, examples=examples),
            )
        assert r.status_code == 422, r.text
        assert r.json()["detail"] == {
            "code": "system_variables",
            "missing": missing,
            "extra": extra,
        }


async def test_fixing_a_reservas_template_clears_it_for_the_lite_screen(
    client, world, db_session
) -> None:
    """4.4: la consola lite de Reservas lee el espejo; tras editar ya no sale
    como rechazada. 4.5: con su fila en el espejo, Reservas no la vuelve a
    pedir (``ensure_templates`` solo pide las que el espejo no tiene)."""
    from nexus_api.services.reservations import templates as reservas

    wanted = list(reservas.VARIABLES["reserva_recordatorio"])
    text = "Hola " + " ".join(f"{{{{{v}}}}}" for v in wanted) + "."
    before = _raw(name="reserva_recordatorio", body=text, examples={v: "x" for v in wanted})
    after = _raw(
        name="reserva_recordatorio",
        status="PENDING",
        body=text.replace("Hola", "Buenas"),
        examples={v: "x" for v in wanted},
    )
    await _mirror(
        db_session,
        template_name="reserva_recordatorio",
        status="REJECTED",
        reason="INVALID_FORMAT",
        tenant_id=world["tenant_id"],
        last_event_at=datetime.now(UTC) - timedelta(hours=1),
    )
    async with respx.mock(base_url=META_GRAPH_BASE_URL, assert_all_called=False) as mock:
        mock.get(f"/{WABA}/message_templates").mock(side_effect=[_list(before), _list(after)])
        mock.post(f"/{TPL_ID}").respond(200, json={"success": True})
        r = await client.put(
            _put(world, "reserva_recordatorio"),
            headers=world["headers"](),
            json=_edit_body(
                before,
                body_text=text.replace("Hola", "Buenas"),
                examples={v: "x" for v in wanted},
                footer_text="Barbería Centro",
            ),
        )
    assert r.status_code == 200, r.text
    row = await _mirror_row(db_session, "reserva_recordatorio")
    assert row is not None
    assert row.status.upper() == "PENDING"
    assert row.reason is None


async def test_panel_rows_carry_the_rejection_reason_and_what_to_fix(
    client, world, db_session
) -> None:
    """1.2 en el panel (9.1): el editor tiene a la vista el motivo de Meta y
    lo que se sugiere arreglar, igual que en la consola."""
    await _mirror(
        db_session,
        template_name="cita_recordatorio",
        status="REJECTED",
        reason="INVALID_FORMAT",
        tenant_id=world["tenant_id"],
        last_event_at=datetime.now(UTC),
    )
    async with respx.mock(base_url=META_GRAPH_BASE_URL, assert_all_called=False) as mock:
        mock.get(f"/{WABA}/message_templates").mock(return_value=_list(_raw()))
        r = await client.get(
            f"/admin/tenants/{world['tenant_id']}/whatsapp/templates", headers=_ADMIN
        )
    assert r.status_code == 200, r.text
    row = r.json()["templates"][0]
    assert row["rejection_reason"] == "INVALID_FORMAT"
    assert row["suggested_action"] == "fix_format"
