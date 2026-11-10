"""Spec 052, requisito 7 — operating one partner never touches the one next door.

Partners, people and invitations are platform tables, with no RLS: the console
gate reads them before any scope exists. So the wall here is the path and the
operator, one level above the tenant rule, and it is proved by **sweeping the
routes**, not by listing them (constitution §I): every write route under
``/admin/`` that names an invitation or whose handler touches the invitation
code is collected from the app itself. A new route is covered the moment it is
mounted; one with a body field this sweep cannot fill turns it red until
someone teaches it.
"""

from __future__ import annotations

import inspect
import json
import re
import secrets
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from types import SimpleNamespace
from typing import Any

import pytest
import sqlalchemy as sa
import structlog
from fastapi.routing import APIRoute
from sqlalchemy import event

from nexus_api.config import get_settings
from nexus_api.core.partner_keys import generate_api_key
from nexus_api.db.base import get_engine
from nexus_api.db.models import (
    AuditLog,
    EmbedAuditLog,
    OperatorAccount,
    Partner,
    PartnerInvitation,
    PartnerMembership,
)
from nexus_api.main import app
from nexus_api.services import console_identity, operator_identity, owner_invitation
from nexus_api.services.device_credential import issue_device_token
from tests.conftest import add_client_member, console_headers, mint_console_token

pytestmark = [pytest.mark.isolation]

WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
#: What a handler has to mention for the sweep to consider that it writes
#: invitations, whatever its path says.
TOUCHES_INVITATIONS = re.compile(r"owner_invitation\.|PartnerInvitation")
FORBIDDEN_PARAMS = {"tenant_id", "partner_id", "tenantid", "partnerid", "tenant", "partner"}


def _invitation_write_routes() -> list[APIRoute]:
    found: list[APIRoute] = []
    for route in app.routes:
        if not isinstance(route, APIRoute) or not route.path.startswith("/admin/"):
            continue
        if not (route.methods or set()) & WRITE_METHODS:
            continue
        names_one = "invitation" in route.path
        # Partner invitations, not a client's: those live under /admin/tenants
        # and have their own suite (``test_lite_route_scope``).
        if route.path.startswith("/admin/tenants/"):
            continue
        if names_one or TOUCHES_INVITATIONS.search(inspect.getsource(route.endpoint)):
            found.append(route)
    return found


ROUTES = _invitation_write_routes()
ROUTE_IDS = [f"{sorted(r.methods or set())[0]} {r.path}" for r in ROUTES]
INVITATION_ROUTES = [r for r in ROUTES if "{invitation_id}" in r.path]


def _method(route: APIRoute) -> str:
    return sorted(route.methods or set())[0]


def _body_model(route: APIRoute) -> Any:
    return None if route.body_field is None else route.body_field.field_info.annotation


def _body_for(route: APIRoute) -> dict[str, Any]:
    """A valid body for whatever the route declares. A field nobody taught this
    function is a failure: the sweep must not silently stop exercising a route."""
    model = _body_model(route)
    if model is None:
        return {}
    filled: dict[str, Any] = {}
    for name, field in model.model_fields.items():
        if not field.is_required():
            continue
        if name in {"email", "owner_email"}:
            filled[name] = f"sweep-{uuid.uuid4().hex[:8]}@negocio.test"
        elif name == "name":
            filled[name] = "Barrido"
        elif name == "slug":
            filled[name] = f"sweep-{uuid.uuid4().hex[:10]}"
        else:
            pytest.fail(f"{route.path}: the sweep does not know how to fill {name!r}")
    return filled


def _url(route: APIRoute, partner_id: Any, invitation_id: Any = None) -> str:
    url = route.path.replace("{partner_id}", str(partner_id))
    return url.replace("{invitation_id}", str(invitation_id or uuid.uuid4()))


async def _operator(db_session) -> SimpleNamespace:
    account = await operator_identity.create_account(
        db_session,
        email=f"op-{uuid.uuid4().hex[:8]}@auphere.test",
        password="operator-password-1",
        role="admin",
    )
    await db_session.commit()
    # Plain values: ``_snapshot`` expires the session.
    return SimpleNamespace(id=account.id, email=account.email)


async def _partner_with_invitation(
    client, db_session, op_headers, *, contact: str | None = None
) -> tuple[uuid.UUID, dict[str, Any]]:
    pid = uuid.uuid4()
    db_session.add(
        Partner(
            id=pid,
            name=f"Partner {pid.hex[:6]}",
            slug=f"scope-{pid.hex[:8]}",
            console_enabled=True,
            contact_email=contact,
        )
    )
    await db_session.commit()
    res = await client.post(
        f"/admin/partners/{pid}/invitations",
        headers=op_headers,
        json={"email": f"duena-{pid.hex[:6]}@negocio.test"},
    )
    assert res.status_code == 201, res.text
    return pid, res.json()


async def _snapshot(db_session) -> tuple[Any, ...]:
    """Everything these routes could have changed."""
    db_session.expire_all()
    invitations = (
        await db_session.execute(
            sa.select(
                PartnerInvitation.id,
                PartnerInvitation.status,
                PartnerInvitation.token_hash,
                PartnerInvitation.expires_at,
                PartnerInvitation.last_sent_at,
            ).order_by(PartnerInvitation.id)
        )
    ).all()
    partners = (
        await db_session.execute(
            sa.select(Partner.id, Partner.contact_email, Partner.console_enabled).order_by(
                Partner.id
            )
        )
    ).all()
    audit = await db_session.scalar(sa.select(sa.func.count()).select_from(AuditLog))
    return (tuple(invitations), tuple(partners), audit)


class Sink:
    def __init__(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self.calls = 0
        monkeypatch.setattr(owner_invitation, "send_template", self)

    async def __call__(self, *_: Any, **__: Any) -> bool:
        self.calls += 1
        return True


# ── the sweep itself ──────────────────────────────────────────────────────────


def test_the_sweep_finds_the_routes() -> None:
    """If it finds nothing it is not sweeping: it is broken."""
    found = {(_method(r), r.path) for r in ROUTES}
    assert {
        ("POST", "/admin/partners"),
        ("POST", "/admin/partners/{partner_id}/invitations"),
        ("POST", "/admin/partners/{partner_id}/invitations/{invitation_id}/resend"),
        ("POST", "/admin/partners/{partner_id}/invitations/{invitation_id}/revoke"),
    } <= found


def test_the_sweep_sees_a_route_by_what_its_handler_does() -> None:
    """A route that writes invitations under an innocent path still counts."""

    async def innocent() -> None:
        await owner_invitation.invite(None, None, email="x", actor="y")  # type: ignore[arg-type]

    assert TOUCHES_INVITATIONS.search(inspect.getsource(innocent))


# ── R7.3 · who may knock ──────────────────────────────────────────────────────


def _foreign_credentials(console_world: dict[str, Any]) -> dict[str, str]:
    a = console_world["a"]
    return {
        "console_token": mint_console_token(
            user_id=a["user_id"], partner_id=a["partner_id"], role="owner"
        ),
        "service_token": mint_console_token(user_id="console-bff", partner_id=None, service=True),
        "partner_key": generate_api_key().plaintext,
        "device_token": issue_device_token(
            device_id=uuid.uuid4(), partner_id=a["partner_id"], generation=1
        ),
        "nonsense": secrets.token_urlsafe(32),
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("route", ROUTES, ids=ROUTE_IDS)
async def test_only_the_panel_token_gets_in(
    client, db_session, console_world, admin_headers, monkeypatch, route
) -> None:
    sink = Sink(monkeypatch)
    op = await _operator(db_session)
    a = console_world["a"]
    before = await _snapshot(db_session)

    missing = await client.request(
        _method(route), _url(route, a["partner_id"]), json=_body_for(route)
    )
    assert missing.status_code == 401

    for name, credential in _foreign_credentials(console_world).items():
        res = await client.request(
            _method(route),
            _url(route, a["partner_id"]),
            headers={"Authorization": f"Bearer {credential}", "X-Operator-Id": str(op.id)},
            json=_body_for(route),
        )
        assert res.status_code == 401, f"{name} got {res.status_code}"

    assert await _snapshot(db_session) == before
    assert sink.calls == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("route", ROUTES, ids=ROUTE_IDS)
async def test_the_panel_token_alone_is_not_a_person(
    client, db_session, console_world, admin_headers, monkeypatch, route
) -> None:
    """R6.3: «no un prefijo del token». Nobody, nobody real, nobody still active."""
    sink = Sink(monkeypatch)
    a = console_world["a"]
    disabled = await _operator(db_session)
    await db_session.execute(
        sa.update(OperatorAccount)
        .where(OperatorAccount.id == disabled.id)
        .values(disabled_at=sa.func.now())
    )
    await db_session.commit()
    before = await _snapshot(db_session)

    for operator_id in (None, "no-es-un-uuid", str(uuid.uuid4()), str(disabled.id)):
        headers = dict(admin_headers)
        if operator_id is not None:
            headers["X-Operator-Id"] = operator_id
        res = await client.request(
            _method(route), _url(route, a["partner_id"]), headers=headers, json=_body_for(route)
        )
        assert res.status_code == 400, f"{operator_id!r} got {res.status_code}"

    assert await _snapshot(db_session) == before
    assert sink.calls == 0


# ── R7.1, R7.2 · one partner's invitation through another's route ─────────────


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "route", INVITATION_ROUTES, ids=[f"{_method(r)} {r.path}" for r in INVITATION_ROUTES]
)
async def test_another_partners_invitation_is_the_same_as_none_byte_for_byte(
    client, db_session, admin_headers, monkeypatch, route
) -> None:
    op = await _operator(db_session)
    op_headers = {**admin_headers, "X-Operator-Id": str(op.id)}
    _, invitation = await _partner_with_invitation(client, db_session, op_headers)
    pid_b, _ = await _partner_with_invitation(client, db_session, op_headers)
    sink = Sink(monkeypatch)
    before = await _snapshot(db_session)

    crossed = await client.request(
        _method(route),
        _url(route, pid_b, invitation["id"]),
        headers=op_headers,
        json=_body_for(route),
    )
    invented = await client.request(
        _method(route),
        _url(route, pid_b, uuid.uuid4()),
        headers=op_headers,
        json=_body_for(route),
    )
    assert crossed.status_code == 404
    assert (crossed.status_code, crossed.content) == (invented.status_code, invented.content)
    assert await _snapshot(db_session) == before
    assert sink.calls == 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "route", INVITATION_ROUTES, ids=[f"{_method(r)} {r.path}" for r in INVITATION_ROUTES]
)
async def test_the_answer_for_nothing_does_not_depend_on_the_state_of_the_route_partner(
    client, db_session, admin_headers, monkeypatch, route
) -> None:
    """Suspended, console off or with an owner: still the same 404, so the
    state of the partner in the path says nothing about the invitation."""
    op = await _operator(db_session)
    op_headers = {**admin_headers, "X-Operator-Id": str(op.id)}
    _, invitation = await _partner_with_invitation(client, db_session, op_headers)
    pid_b, _ = await _partner_with_invitation(client, db_session, op_headers)
    Sink(monkeypatch)
    partner_b = await db_session.get(Partner, pid_b)
    partner_b.status = "suspended"
    partner_b.console_enabled = False
    await db_session.commit()

    crossed = await client.request(
        _method(route),
        _url(route, pid_b, invitation["id"]),
        headers=op_headers,
        json=_body_for(route),
    )
    invented = await client.request(
        _method(route), _url(route, pid_b, uuid.uuid4()), headers=op_headers, json=_body_for(route)
    )
    assert crossed.status_code == 404
    assert crossed.content == invented.content


@pytest.mark.asyncio
async def test_inviting_through_b_only_changes_b(client, db_session, admin_headers) -> None:
    op = await _operator(db_session)
    op_headers = {**admin_headers, "X-Operator-Id": str(op.id)}
    pid_a, _ = await _partner_with_invitation(
        client, db_session, op_headers, contact="contacto-a@negocio.test"
    )
    pid_b = uuid.uuid4()
    db_session.add(Partner(id=pid_b, name="B", slug=f"scope-{pid_b.hex[:8]}", console_enabled=True))
    await db_session.commit()

    res = await client.post(
        f"/admin/partners/{pid_b}/invitations",
        headers=op_headers,
        json={"email": "persona-de-be@negocio.test"},
    )
    assert res.status_code == 201, res.text

    db_session.expire_all()
    assert (await db_session.get(Partner, pid_a)).contact_email == "contacto-a@negocio.test"
    team_a = (await client.get(f"/admin/partners/{pid_a}/members", headers=admin_headers)).json()
    team_b = (await client.get(f"/admin/partners/{pid_b}/members", headers=admin_headers)).json()
    assert "persona-de-be@negocio.test" not in json.dumps(team_a)
    assert [i["email"] for i in team_b["invitations"]] == ["persona-de-be@negocio.test"]


# ── R7.1, garantía 1 · nothing of the caller decides the partner ──────────────


def _params_of(route: APIRoute) -> set[str]:
    dependant = route.dependant
    names: set[str] = set()
    stack = [dependant]
    while stack:
        current = stack.pop()
        for group in (current.query_params, current.header_params, current.cookie_params):
            names.update(p.name.lower() for p in group)
        stack.extend(current.dependencies)
    return names


@pytest.mark.parametrize("route", ROUTES, ids=ROUTE_IDS)
def test_no_route_takes_a_tenant_or_a_partner_from_the_caller(route: APIRoute) -> None:
    assert not (_params_of(route) & FORBIDDEN_PARAMS), route.path
    assert "{tenant_id}" not in route.path
    model = _body_model(route)
    assert model is not None, f"{route.path} needs a body model that forbids extras"
    assert model.model_config.get("extra") == "forbid", f"{model.__name__} must forbid extras"
    assert not (set(model.model_fields) & FORBIDDEN_PARAMS), model.__name__


@pytest.mark.asyncio
@pytest.mark.parametrize("route", ROUTES, ids=ROUTE_IDS)
async def test_a_tenant_or_partner_in_the_body_is_refused(
    client, db_session, console_world, admin_headers, route
) -> None:
    op = await _operator(db_session)
    a = console_world["a"]
    for field in ("tenant_id", "partner_id"):
        res = await client.request(
            _method(route),
            _url(route, a["partner_id"]),
            headers={**admin_headers, "X-Operator-Id": str(op.id)},
            json={**_body_for(route), field: str(uuid.uuid4())},
        )
        assert res.status_code == 422, f"{route.path} accepted {field}"


# ── R7.5, garantía 1 · no tenant table is read or written ─────────────────────


@contextmanager
def _statements() -> Iterator[list[str]]:
    seen: list[str] = []

    def capture(_conn: Any, _cursor: Any, statement: str, *_: Any) -> None:
        seen.append(statement)

    engine = get_engine().sync_engine
    event.listen(engine, "before_cursor_execute", capture)
    try:
        yield seen
    finally:
        event.remove(engine, "before_cursor_execute", capture)


async def _rls_tables(db_session) -> set[str]:
    """A tenant table is one with RLS on, by the catalog, not by a list. The one
    exception is the two audit logs: what is written there is a platform row
    (``tenant_id`` is null), proved by ``test_every_audit_row_is_a_platform_row``."""
    rows = await db_session.execute(
        sa.text(
            "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid = c.relnamespace "
            "WHERE c.relrowsecurity AND n.nspname = 'public' AND c.relkind IN ('r', 'p')"
        )
    )
    return {r[0] for r in rows} - {"audit_log", "embed_audit_log"}


_TABLE_REF = re.compile(r"(?:FROM|JOIN|UPDATE|INTO)\s+\"?([a-z_][a-z_0-9]*)\"?", re.IGNORECASE)


@pytest.mark.asyncio
async def test_the_actions_touch_no_tenant_table(
    client, db_session, admin_headers, monkeypatch
) -> None:
    op = await _operator(db_session)
    op_headers = {**admin_headers, "X-Operator-Id": str(op.id)}
    forbidden = await _rls_tables(db_session)
    assert "conversations" in forbidden and "messages" in forbidden
    Sink(monkeypatch)
    pid = uuid.uuid4()
    db_session.add(Partner(id=pid, name="P", slug=f"scope-{pid.hex[:8]}", console_enabled=True))
    await db_session.commit()

    with _statements() as seen:
        created = await client.post(
            "/admin/partners",
            headers=op_headers,
            json={
                "name": "N",
                "slug": f"s-{uuid.uuid4().hex[:8]}",
                "owner_email": "n@negocio.test",
            },
        )
        assert created.status_code == 201, created.text
        invited = await client.post(
            f"/admin/partners/{pid}/invitations",
            headers=op_headers,
            json={"email": "p@negocio.test"},
        )
        assert invited.status_code == 201, invited.text
        resent = await client.post(
            f"/admin/partners/{pid}/invitations/{invited.json()['id']}/resend",
            headers=op_headers,
            json={},
        )
        assert resent.status_code == 201, resent.text
        revoked = await client.post(
            f"/admin/partners/{pid}/invitations/{resent.json()['id']}/revoke",
            headers=op_headers,
            json={},
        )
        assert revoked.status_code == 200, revoked.text

    assert seen, "no statement captured: this test is not looking at the app's engine"
    touched = {m.lower() for stmt in seen for m in _TABLE_REF.findall(stmt)}
    assert "partner_invitations" in touched
    assert not (touched & forbidden), f"tenant tables touched: {touched & forbidden}"


@pytest.mark.asyncio
async def test_every_audit_row_is_a_platform_row(client, db_session, admin_headers) -> None:
    op = await _operator(db_session)
    op_headers = {**admin_headers, "X-Operator-Id": str(op.id)}
    pid, invitation = await _partner_with_invitation(client, db_session, op_headers)
    await client.post(
        f"/admin/partners/{pid}/invitations/{invitation['id']}/revoke", headers=op_headers, json={}
    )
    db_session.expire_all()
    rows = list(
        await db_session.scalars(sa.select(AuditLog).where(AuditLog.target == f"partner:{pid}"))
    )
    assert len(rows) == 2
    assert {r.tenant_id for r in rows} == {None}

    created = await client.post(
        "/admin/partners",
        headers=op_headers,
        json={"name": "N", "slug": f"s-{uuid.uuid4().hex[:8]}", "owner_email": "n@negocio.test"},
    )
    assert created.status_code == 201, created.text
    pid_created = uuid.UUID(created.json()["id"])
    db_session.expire_all()
    audit = list(
        await db_session.scalars(
            sa.select(AuditLog).where(AuditLog.target == f"partner:{pid_created}")
        )
    )
    assert {r.action for r in audit} == {"partner.create", "partner.owner_invited"}
    assert {r.tenant_id for r in audit} == {None}
    embed = list(
        await db_session.scalars(
            sa.select(EmbedAuditLog).where(EmbedAuditLog.partner_id == pid_created)
        )
    )
    assert [r.event for r in embed] == ["partner.created"]
    assert {r.tenant_id for r in embed} == {None}


# ── R7.4, garantía 6 · each mail's record says whose it is ────────────────────


@pytest.mark.asyncio
async def test_the_record_of_a_retained_mail_names_the_partner(
    client, db_session, admin_headers, monkeypatch
) -> None:
    monkeypatch.setattr(get_settings(), "email_delivery", "log", raising=False)
    op = await _operator(db_session)
    op_headers = {**admin_headers, "X-Operator-Id": str(op.id)}
    pid = uuid.uuid4()
    db_session.add(Partner(id=pid, name="P", slug=f"scope-{pid.hex[:8]}", console_enabled=True))
    await db_session.commit()
    with structlog.testing.capture_logs() as logs:
        res = await client.post(
            f"/admin/partners/{pid}/invitations",
            headers=op_headers,
            json={"email": "p@negocio.test"},
        )
    assert res.status_code == 201, res.text
    [event_] = [e for e in logs if e["event"] == "email.suppressed"]
    assert event_["partner_id"] == str(pid)
    assert event_["owner"] == "partner"
    assert event_["kind"] == "team_invite"


# ── R7.6 · an account still belongs to one place ──────────────────────────────


@pytest.mark.asyncio
async def test_accepting_still_respects_one_account_one_place(
    client, db_session, console_world, admin_headers
) -> None:
    """The invitation was fine when it was issued; by the time it is accepted
    the account lives elsewhere. Accepting does not relax that."""
    op = await _operator(db_session)
    op_headers = {**admin_headers, "X-Operator-Id": str(op.id)}
    password = "una-clave-larga-y-segura-2026"
    pid, invitation = await _partner_with_invitation(client, db_session, op_headers)
    account = await console_identity.create_account(
        db_session, email=invitation["email"], password=password
    )
    a = console_world["a"]
    await add_client_member(
        db_session, partner_id=a["partner_id"], tenant_id=a["tenant_id"], email=invitation["email"]
    )
    client_row_user = await db_session.scalar(
        sa.text("SELECT user_id FROM client_memberships WHERE email = :e"),
        {"e": invitation["email"]},
    )
    await db_session.execute(
        sa.text("UPDATE client_memberships SET user_id = :u WHERE user_id = :o"),
        {"u": str(account.id), "o": client_row_user},
    )
    await db_session.commit()

    token = invitation["accept_url"].rsplit("/", 1)[-1]
    res = await client.post(
        f"/console/invitations/{token}/accept",
        headers=console_headers(user_id="console-bff", partner_id=None, service=True),
        json={"password": password},
    )
    assert res.status_code == 409, res.text
    db_session.expire_all()
    assert (
        await db_session.scalar(
            sa.select(PartnerMembership).where(PartnerMembership.partner_id == pid)
        )
    ) is None


# ── the read side stays inside its partner, and never carries a secret ────────


@pytest.mark.asyncio
async def test_the_team_read_never_carries_a_token_or_its_hash(
    client, db_session, admin_headers
) -> None:
    op = await _operator(db_session)
    op_headers = {**admin_headers, "X-Operator-Id": str(op.id)}
    pid, invitation = await _partner_with_invitation(client, db_session, op_headers)
    token = invitation["accept_url"].rsplit("/", 1)[-1]
    row = await db_session.get(PartnerInvitation, uuid.UUID(invitation["id"]))
    team = await client.get(f"/admin/partners/{pid}/members", headers=admin_headers)
    assert team.status_code == 200
    assert token not in team.text
    assert row.token_hash not in team.text
    assert "token" not in team.text
    assert "accept_url" not in team.text
