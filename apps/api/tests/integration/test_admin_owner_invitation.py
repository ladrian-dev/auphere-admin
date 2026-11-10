"""Spec 052 — creating a partner from the panel invites its owner.

``POST /admin/partners`` and ``/admin/partners/{id}/invitations…``. What this
file pins, requirement by requirement: the transaction and what happens after
it, the operator's result, inviting, resending, revoking, and the audit.

No test sends a real e-mail: the default mode here is ``log`` (nothing leaves),
and the ones that exercise the provider put ``respx`` in front of Resend.
"""

from __future__ import annotations

import asyncio
import json
import pathlib
import time
import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
import respx
import sqlalchemy as sa
import structlog
from alembic.config import Config
from alembic.script import ScriptDirectory

from nexus_api.config import get_settings
from nexus_api.db.base import get_sessionmaker
from nexus_api.db.models import (
    INVITATION_TTL,
    PARTNER_NAV_MODULES,
    AuditLog,
    InvitationStatus,
    Partner,
    PartnerInvitation,
    PartnerMembership,
)
from nexus_api.repositories.partner_membership import (
    hash_invitation_token,
    invitation_is_live_clause,
)
from nexus_api.services import console_identity, operator_identity, owner_invitation
from nexus_api.services.email import RESEND_URL
from nexus_api.services.email_catalog import EmailKind, console_link, format_day
from tests.conftest import add_client_member, console_headers

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

PASSWORD = "una-clave-larga-y-segura-2026"
API_ROOT = pathlib.Path(__file__).resolve().parents[2]


# ── helpers ───────────────────────────────────────────────────────────────────


@pytest.fixture
async def operator(db_session) -> Any:
    account = await operator_identity.create_account(
        db_session,
        email=f"op-{uuid.uuid4().hex[:8]}@auphere.test",
        password="operator-password-1",
        role="admin",
    )
    await db_session.commit()
    # Plain values: the helpers below expire the session, and a detached read of
    # an expired row is a MissingGreenlet in the test, not a finding.
    return SimpleNamespace(id=account.id, email=account.email)


@pytest.fixture
def op_headers(admin_headers, operator) -> dict[str, str]:
    return {**admin_headers, "X-Operator-Id": str(operator.id)}


def _slug() -> str:
    return f"p-{uuid.uuid4().hex[:10]}"


def _address() -> str:
    return f"duena-{uuid.uuid4().hex[:8]}@negocio.test"


def _token(accept_url: str) -> str:
    return accept_url.rsplit("/", 1)[-1]


def _svc() -> dict[str, str]:
    return console_headers(user_id="console-bff", partner_id=None, service=True)


async def _create(client, headers, *, email=None, slug=None, name="Acme") -> httpx.Response:
    return await client.post(
        "/admin/partners",
        headers=headers,
        json={"name": name, "slug": slug or _slug(), "owner_email": email or _address()},
    )


async def _bare_partner(
    db_session,
    *,
    console: bool = True,
    status: str = "active",
    contact: str | None = None,
    name: str = "Existente",
) -> uuid.UUID:
    """A partner from before this spec: nobody invited, nobody inside."""
    pid = uuid.uuid4()
    db_session.add(
        Partner(
            id=pid,
            name=name,
            slug=f"bare-{pid.hex[:8]}",
            status=status,
            console_enabled=console,
            contact_email=contact,
        )
    )
    await db_session.commit()
    return pid


async def _invite(client, headers, pid, email=None) -> httpx.Response:
    return await client.post(
        f"/admin/partners/{pid}/invitations",
        headers=headers,
        json={"email": email or _address()},
    )


def _resend_url(pid, iid) -> str:
    return f"/admin/partners/{pid}/invitations/{iid}/resend"


def _revoke_url(pid, iid) -> str:
    return f"/admin/partners/{pid}/invitations/{iid}/revoke"


async def _members(client, headers, pid) -> dict[str, Any]:
    res = await client.get(f"/admin/partners/{pid}/members", headers=headers)
    assert res.status_code == 200, res.text
    return res.json()


async def _row(db_session, iid) -> PartnerInvitation:
    db_session.expire_all()
    row = await db_session.get(PartnerInvitation, uuid.UUID(str(iid)))
    assert row is not None
    return row


async def _old_invitation(
    db_session,
    pid,
    *,
    email: str | None = None,
    role: str = "owner",
    status: str = "pending",
    expired: bool = False,
    invited_by: uuid.UUID | None = None,
) -> PartnerInvitation:
    row = PartnerInvitation(
        id=uuid.uuid4(),
        partner_id=pid,
        email=email or _address(),
        role=role,
        token_hash=uuid.uuid4().hex + uuid.uuid4().hex,
        invited_by=invited_by,
        status=status,
        expires_at=datetime.now(UTC) + (timedelta(days=-2) if expired else timedelta(days=9)),
    )
    db_session.add(row)
    await db_session.commit()
    return row


async def _audit(db_session, pid, action: str) -> list[AuditLog]:
    db_session.expire_all()
    rows = await db_session.scalars(
        sa.select(AuditLog)
        .where(AuditLog.target == f"partner:{pid}", AuditLog.action == action)
        .order_by(AuditLog.created_at)
    )
    return list(rows)


class Sink:
    """Stands in for ``send_template``. ``result`` is what the provider said."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, result: bool = True) -> None:
        self.calls: list[dict[str, Any]] = []
        self.result = result
        self.on_call: Any = None
        monkeypatch.setattr(owner_invitation, "send_template", self)

    async def __call__(self, kind: EmailKind, **kwargs: Any) -> bool:
        self.calls.append({"kind": kind, **kwargs})
        if self.on_call is not None:
            await self.on_call(kwargs)
        return self.result


@pytest.fixture
def real_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "email_delivery", "resend", raising=False)
    monkeypatch.setattr(settings, "resend_api_key", "re_not_a_real_key", raising=False)


# ── T002 · foundations ────────────────────────────────────────────────────────


async def test_last_sent_at_is_a_nullable_timestamptz(db_session) -> None:
    row = (
        await db_session.execute(
            sa.text(
                "SELECT data_type, is_nullable FROM information_schema.columns "
                "WHERE table_name = 'partner_invitations' AND column_name = 'last_sent_at'"
            )
        )
    ).one()
    assert row.data_type == "timestamp with time zone"
    assert row.is_nullable == "YES"


async def test_the_live_clause_leaves_a_pending_expired_row_out(db_session) -> None:
    pid = await _bare_partner(db_session)
    live = await _old_invitation(db_session, pid)
    await _old_invitation(db_session, pid, expired=True)
    await _old_invitation(db_session, pid, status="revoked")
    rows = await db_session.scalars(
        sa.select(PartnerInvitation.id).where(
            PartnerInvitation.partner_id == pid, invitation_is_live_clause(datetime.now(UTC))
        )
    )
    assert list(rows) == [live.id]


async def test_migrations_keep_a_single_head() -> None:
    config = Config(str(API_ROOT / "alembic.ini"))
    config.set_main_option("script_location", str(API_ROOT / "alembic"))
    assert len(ScriptDirectory.from_config(config).get_heads()) == 1


async def test_the_three_actions_have_their_sentence(db_session) -> None:
    rows = await db_session.execute(
        sa.text(
            "SELECT action, summary_es, summary_en FROM console_audit_vocabulary "
            "WHERE action IN ('partner.owner_invited', 'partner.owner_invitation_resent', "
            "'partner.owner_invitation_revoked')"
        )
    )
    found = {r.action: (r.summary_es, r.summary_en) for r in rows}
    assert set(found) == {
        "partner.owner_invited",
        "partner.owner_invitation_resent",
        "partner.owner_invitation_revoked",
    }
    for es, en in found.values():
        for sentence in (es, en):
            assert "{actor}" in sentence and "{email}" in sentence and "{partner}" in sentence


# ── T008 · Requisito 1, the partner is born and its owner invited ─────────────


async def test_creating_gives_console_on_invitation_and_contact(
    client, db_session, op_headers
) -> None:
    email = _address()
    res = await _create(client, op_headers, email=email)
    assert res.status_code == 201, res.text
    body = res.json()

    assert body["console_enabled"] is True
    assert body["console_modules"] == list(PARTNER_NAV_MODULES)
    assert body["status"] == "active"
    assert body["contact_email"] == email

    invitation = body["invitation"]
    assert invitation["email"] == email
    assert invitation["role"] == "owner"
    assert invitation["status"] == "pending"
    assert invitation["email_sent"] is True
    assert invitation["last_sent_at"] is not None

    row = await _row(db_session, invitation["id"])
    assert row.partner_id == uuid.UUID(body["id"])
    assert row.role == "owner"
    assert row.invited_by is None
    # Only the hash is kept; the plaintext is the link.
    assert row.token_hash == hash_invitation_token(_token(invitation["accept_url"]))
    lifetime = row.expires_at - datetime.now(UTC)
    assert INVITATION_TTL - timedelta(minutes=1) < lifetime <= INVITATION_TTL


@pytest.mark.parametrize(
    "owner_email",
    ["", "   ", "no-es-un-correo", "sin@punto", "dos espacios@negocio.test", "@negocio.test"],
)
async def test_a_bad_address_creates_nothing(client, db_session, op_headers, owner_email) -> None:
    slug = _slug()
    res = await client.post(
        "/admin/partners",
        headers=op_headers,
        json={"name": "Acme", "slug": slug, "owner_email": owner_email},
    )
    assert res.status_code == 422, res.text
    assert await db_session.scalar(sa.select(Partner).where(Partner.slug == slug)) is None


async def test_a_missing_address_creates_nothing(client, db_session, op_headers) -> None:
    slug = _slug()
    res = await client.post(
        "/admin/partners", headers=op_headers, json={"name": "Acme", "slug": slug}
    )
    assert res.status_code == 422
    assert await db_session.scalar(sa.select(Partner).where(Partner.slug == slug)) is None


@pytest.mark.parametrize("extra", [{"contact_email": "c@negocio.test"}, {"role": "admin"}])
async def test_the_contact_field_is_gone_and_the_role_cannot_be_chosen(
    client, op_headers, extra
) -> None:
    res = await client.post(
        "/admin/partners",
        headers=op_headers,
        json={"name": "Acme", "slug": _slug(), "owner_email": _address(), **extra},
    )
    assert res.status_code == 422


async def test_the_address_is_trimmed_and_lowercased(client, op_headers) -> None:
    res = await _create(client, op_headers, email="  Ana.Maria@NEGOCIO.test ")
    assert res.status_code == 201, res.text
    assert res.json()["invitation"]["email"] == "ana.maria@negocio.test"
    assert res.json()["contact_email"] == "ana.maria@negocio.test"


async def test_a_used_slug_creates_nothing_and_sends_nothing(
    client, db_session, op_headers, monkeypatch
) -> None:
    slug = _slug()
    first = await _create(client, op_headers, slug=slug)
    assert first.status_code == 201
    sink = Sink(monkeypatch)
    email = _address()
    second = await _create(client, op_headers, slug=slug, email=email)
    assert second.status_code == 409
    assert second.json()["detail"]["code"] == "slug_taken"
    assert sink.calls == []
    assert (
        await db_session.scalar(
            sa.select(PartnerInvitation).where(PartnerInvitation.email == email)
        )
        is None
    )


@pytest.mark.parametrize("member_status", ["active", "suspended"])
async def test_an_address_of_another_partner_is_refused(
    client, db_session, op_headers, console_world, monkeypatch, member_status
) -> None:
    a = console_world["a"]
    member = await db_session.get(PartnerMembership, a["membership_id"])
    member.status = member_status
    await db_session.commit()
    sink = Sink(monkeypatch)
    slug = _slug()
    res = await _create(client, op_headers, email=member.email, slug=slug)
    assert res.status_code == 409, res.text
    assert res.json()["detail"]["code"] == "address_has_own_console"
    assert await db_session.scalar(sa.select(Partner).where(Partner.slug == slug)) is None
    assert sink.calls == []


async def test_an_account_whose_membership_kept_an_old_address_is_refused(
    client, db_session, op_headers, console_world
) -> None:
    """``accept`` looks at the account, not at the copy of the address."""
    account = await console_identity.create_account(
        db_session, email="renombrada@negocio.test", password=PASSWORD
    )
    member = await db_session.get(PartnerMembership, console_world["a"]["membership_id"])
    member.user_id = str(account.id)
    await db_session.commit()
    res = await _create(client, op_headers, email="renombrada@negocio.test")
    assert res.status_code == 409
    assert res.json()["detail"]["code"] == "address_has_own_console"


@pytest.mark.parametrize("member_status", ["active", "revoked"])
async def test_an_address_of_a_client_is_refused(
    client, db_session, op_headers, console_world, member_status
) -> None:
    a = console_world["a"]
    await add_client_member(
        db_session,
        partner_id=a["partner_id"],
        tenant_id=a["tenant_id"],
        status=member_status,
        email="persona@cliente.test",
    )
    res = await _create(client, op_headers, email="persona@cliente.test")
    assert res.status_code == 409
    assert res.json()["detail"]["code"] == "address_has_own_console"


async def test_an_account_with_no_membership_can_be_invited(client, db_session, op_headers) -> None:
    await console_identity.create_account(db_session, email="salio@negocio.test", password=PASSWORD)
    await db_session.commit()
    res = await _create(client, op_headers, email="salio@negocio.test")
    assert res.status_code == 201, res.text


async def test_a_failure_in_the_transaction_leaves_nothing_and_sends_nothing(
    client, db_session, op_headers, monkeypatch
) -> None:
    sink = Sink(monkeypatch)

    async def boom(self: Any, **_: Any) -> None:
        raise RuntimeError("the audit fell over")

    monkeypatch.setattr(owner_invitation.AuditRepository, "record", boom)
    slug = _slug()
    with pytest.raises(RuntimeError):
        await _create(client, op_headers, slug=slug)
    assert await db_session.scalar(sa.select(Partner).where(Partner.slug == slug)) is None
    assert sink.calls == []


async def test_the_mail_goes_out_after_the_transaction_committed(
    client, op_headers, monkeypatch
) -> None:
    sink = Sink(monkeypatch)
    committed: dict[str, Any] = {}

    async def look_from_another_connection(kwargs: dict[str, Any]) -> None:
        async with get_sessionmaker()() as other:
            partner = await other.get(Partner, kwargs["partner_id"])
            committed["partner"] = partner is not None
            committed["invitation"] = (
                await other.scalar(
                    sa.select(PartnerInvitation).where(
                        PartnerInvitation.partner_id == kwargs["partner_id"]
                    )
                )
            ) is not None

    sink.on_call = look_from_another_connection
    res = await _create(client, op_headers)
    assert res.status_code == 201, res.text
    assert committed == {"partner": True, "invitation": True}


async def test_a_failed_send_undoes_nothing(client, db_session, op_headers, monkeypatch) -> None:
    Sink(monkeypatch, result=False)
    res = await _create(client, op_headers)
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["invitation"]["email_sent"] is False
    assert body["invitation"]["last_sent_at"] is None
    assert body["invitation"]["accept_url"]
    assert await db_session.get(Partner, uuid.UUID(body["id"])) is not None
    assert (await _row(db_session, body["invitation"]["id"])).status == "pending"


async def test_the_mail_is_the_team_invite_from_auphere(client, op_headers, monkeypatch) -> None:
    sink = Sink(monkeypatch)
    email = _address()
    res = await _create(client, op_headers, email=email, name="Barbería & Co")
    assert res.status_code == 201, res.text
    body = res.json()
    [mail] = sink.calls
    assert mail["kind"] is EmailKind.TEAM_INVITE
    assert mail["to"] == email
    assert mail["locale"] == "es"
    assert str(mail["partner_id"]) == body["id"]
    variables = mail["variables"]
    assert variables["INVITER"] == "Auphere"
    assert variables["PARTNER_NAME"] == "Barbería & Co"
    assert variables["ROLE_LABEL"] == "Propietario"
    expires = datetime.fromisoformat(body["invitation"]["expires_at"])
    assert variables["EXPIRES_ON"] == format_day(expires.date(), "es")
    # Absolute, and the very link the operator was shown.
    token = _token(body["invitation"]["accept_url"])
    assert variables["ACCEPT_URL"] == console_link(f"/invite/{token}")
    assert body["invitation"]["accept_url"] == variables["ACCEPT_URL"]
    assert body["invitation"]["accept_url"].startswith(get_settings().console_base_url)
    # «Auphere te ha invitado a unirte a Barbería & Co», not «…en Auphere».
    assert mail["subject"] == "Auphere te ha invitado a unirte a Barbería & Co"


async def test_the_mail_follows_the_language_of_the_account(
    client, db_session, op_headers, monkeypatch
) -> None:
    sink = Sink(monkeypatch)
    account = await console_identity.create_account(
        db_session, email="english@negocio.test", password=PASSWORD
    )
    account.locale = "en"
    await db_session.commit()
    res = await _create(client, op_headers, email="english@negocio.test", name="Acme")
    assert res.status_code == 201, res.text
    [mail] = sink.calls
    assert mail["locale"] == "en"
    assert mail["variables"]["ROLE_LABEL"] == "Owner"
    assert mail["subject"] == "Auphere invited you to join Acme"


async def test_whoever_accepts_is_the_owner_and_reaches_the_console(
    client, db_session, op_headers, admin_headers
) -> None:
    """Historia 1, escenario 4; CE-006: nunca una pantalla de «sin acceso»."""
    res = await _create(client, op_headers)
    body = res.json()
    token = _token(body["invitation"]["accept_url"])
    accepted = await client.post(
        f"/console/invitations/{token}/accept", headers=_svc(), json={"password": PASSWORD}
    )
    assert accepted.status_code == 200, accepted.text
    assert accepted.json()["role"] == "owner"

    pid = uuid.UUID(body["id"])
    member = await db_session.scalar(
        sa.select(PartnerMembership).where(PartnerMembership.partner_id == pid)
    )
    assert member is not None and member.role == "owner" and member.status == "active"
    me = await client.get(
        "/console/me", headers=console_headers(user_id=member.user_id, partner_id=pid)
    )
    assert me.status_code == 200, me.text
    assert me.json()["modules"]

    team = await _members(client, admin_headers, pid)
    assert [m["status"] for m in team["members"]] == ["active"]
    assert team["invitations"] == []
    assert team["owner"]["has_active_owner"] is True
    assert team["owner"]["can_invite"] is False


async def test_create_is_audited_by_the_person_with_the_console_on(
    client, db_session, op_headers, operator
) -> None:
    email = _address()
    res = await _create(client, op_headers, email=email)
    pid = res.json()["id"]
    [created] = await _audit(db_session, pid, "partner.create")
    assert created.actor == f"operator:{operator.email}"
    assert created.tenant_id is None
    assert created.after_json["console_enabled"] is True
    assert created.after_json["console_modules"] == list(PARTNER_NAV_MODULES)
    [invited] = await _audit(db_session, pid, "partner.owner_invited")
    assert invited.actor == f"operator:{operator.email}"
    assert invited.after_json["email"] == email
    assert invited.after_json["role"] == "owner"
    # R1.10: the contact changed, and it says so.
    assert invited.after_json["contact_email"] == email
    assert invited.before_json == {"contact_email": None}


async def test_no_operator_no_partner(client, db_session, admin_headers) -> None:
    slug = _slug()
    res = await _create(client, admin_headers, slug=slug)
    assert res.status_code == 400
    assert await db_session.scalar(sa.select(Partner).where(Partner.slug == slug)) is None


# ── T015 · Requisito 2, what the operator learns about the send ───────────────


def _no_token_in(logs: list[dict[str, Any]], token: str) -> None:
    assert token not in json.dumps(logs, default=str)


@respx.mock
async def test_accepted_by_the_provider_is_recorded(
    client, db_session, op_headers, real_provider
) -> None:
    route = respx.post(RESEND_URL).mock(return_value=httpx.Response(200, json={"id": "mail-1"}))
    with structlog.testing.capture_logs() as logs:
        res = await _create(client, op_headers)
    assert res.status_code == 201, res.text
    invitation = res.json()["invitation"]
    assert route.called
    assert invitation["email_sent"] is True
    row = await _row(db_session, invitation["id"])
    assert row.last_sent_at is not None
    # Guarantee 6 and R6.5: the record of a real send names the partner and
    # carries no link.
    [sent] = [e for e in logs if e["event"] == "email.sent"]
    assert sent["partner_id"] == res.json()["id"]
    _no_token_in(logs, _token(invitation["accept_url"]))


@respx.mock
async def test_a_refusal_leaves_a_working_link_and_no_date(
    client, db_session, op_headers, real_provider
) -> None:
    def echo(request: httpx.Request) -> httpx.Response:
        # A provider that quotes back what it was sent must not put the link
        # in our records.
        sent = json.loads(request.content)
        return httpx.Response(422, json={"message": f"bad: {sent['template']['variables']}"})

    respx.post(RESEND_URL).mock(side_effect=echo)
    with structlog.testing.capture_logs() as logs:
        res = await _create(client, op_headers)
    assert res.status_code == 201, res.text
    invitation = res.json()["invitation"]
    token = _token(invitation["accept_url"])
    assert invitation["email_sent"] is False
    assert (await _row(db_session, invitation["id"])).last_sent_at is None
    assert any(e["event"] == "email.send_failed" for e in logs)
    _no_token_in(logs, token)
    # CE-003: the link it shows works.
    lookup = await client.get(f"/console/invitations/{token}", headers=_svc())
    assert lookup.status_code == 200, lookup.text


@respx.mock
async def test_a_provider_that_does_not_answer_is_a_failure(
    client, op_headers, real_provider
) -> None:
    respx.post(RESEND_URL).mock(side_effect=httpx.ReadTimeout("no answer"))
    res = await _create(client, op_headers)
    assert res.status_code == 201, res.text
    assert res.json()["invitation"]["email_sent"] is False


async def test_no_provider_configured_is_a_failure_and_the_partner_is_created(
    client, op_headers, monkeypatch
) -> None:
    settings = get_settings()
    monkeypatch.setattr(settings, "email_delivery", "resend", raising=False)
    monkeypatch.setattr(settings, "resend_api_key", "dev-resend-key-change-me", raising=False)
    res = await _create(client, op_headers)
    assert res.status_code == 201, res.text
    assert res.json()["invitation"]["email_sent"] is False


async def test_an_internal_error_while_sending_is_a_failure(
    client, op_headers, monkeypatch
) -> None:
    secret_in_the_error = "x" * 40

    async def boom(*_: Any, **__: Any) -> bool:
        raise RuntimeError(secret_in_the_error)

    monkeypatch.setattr(owner_invitation, "send_template", boom)
    with structlog.testing.capture_logs() as logs:
        res = await _create(client, op_headers)
    assert res.status_code == 201, res.text
    invitation = res.json()["invitation"]
    assert invitation["email_sent"] is False
    _no_token_in(logs, _token(invitation["accept_url"]))
    _no_token_in(logs, secret_in_the_error)


async def test_the_operator_is_answered_within_the_deadline(
    client, op_headers, monkeypatch
) -> None:
    """CE-002: ``httpx`` times out per phase; the service caps the whole send."""

    async def hangs(*_: Any, **__: Any) -> bool:
        await asyncio.sleep(30)
        return True

    monkeypatch.setattr(owner_invitation, "send_template", hangs)
    monkeypatch.setattr(owner_invitation, "SEND_DEADLINE_S", 0.1)
    started = time.monotonic()
    res = await _create(client, op_headers)
    assert time.monotonic() - started < 5
    assert res.status_code == 201, res.text
    assert res.json()["invitation"]["email_sent"] is False


async def test_the_real_deadline_answers_in_under_thirty_seconds() -> None:
    assert owner_invitation.SEND_DEADLINE_S <= 25


async def test_failing_to_record_the_date_does_not_lose_the_link(
    client, op_headers, monkeypatch
) -> None:
    async def boom(*_: Any, **__: Any) -> None:
        raise RuntimeError("the database went away")

    monkeypatch.setattr(owner_invitation, "_record_sent", boom)
    res = await _create(client, op_headers)
    assert res.status_code == 201, res.text
    invitation = res.json()["invitation"]
    assert invitation["email_sent"] is True
    assert invitation["last_sent_at"] is None
    assert invitation["accept_url"]


async def test_the_file_says_it_is_not_known_after_a_reload(
    client, admin_headers, op_headers, monkeypatch
) -> None:
    """Historia 2, escenario 4: otra operadora, otro día."""
    Sink(monkeypatch, result=False)
    created = (await _create(client, op_headers)).json()
    team = await _members(client, admin_headers, created["id"])
    [invitation] = team["invitations"]
    assert invitation["id"] == created["invitation"]["id"]
    assert invitation["last_sent_at"] is None
    assert invitation["from_auphere"] is True
    assert team["owner"]["can_resend"] is True


async def test_retrying_with_the_provider_healthy_clears_it(
    client, db_session, admin_headers, op_headers, monkeypatch
) -> None:
    sink = Sink(monkeypatch, result=False)
    created = (await _create(client, op_headers)).json()
    sink.result = True
    retried = await client.post(
        _resend_url(created["id"], created["invitation"]["id"]), headers=op_headers, json={}
    )
    assert retried.status_code == 201, retried.text
    assert retried.json()["email_sent"] is True
    team = await _members(client, admin_headers, created["id"])
    [invitation] = team["invitations"]
    assert invitation["last_sent_at"] is not None


# ── T019 · Requisito 6, the audit reads whole, without the link ───────────────


async def test_the_panel_reads_each_action_as_a_sentence_naming_the_operator(
    client, admin_headers, op_headers, operator
) -> None:
    created = (await _create(client, op_headers, name="Acme")).json()
    other = (await _create(client, op_headers, name="Ajena")).json()
    email = created["invitation"]["email"]
    resent = (
        await client.post(
            _resend_url(created["id"], created["invitation"]["id"]), headers=op_headers, json={}
        )
    ).json()
    await client.post(_revoke_url(created["id"], resent["id"]), headers=op_headers, json={})

    res = await client.get(f"/admin/partners/{created['id']}/audit-log", headers=admin_headers)
    assert res.status_code == 200, res.text
    lines = res.json()
    by_action = {line["action"]: line for line in lines}
    assert {
        "partner.create",
        "partner.owner_invited",
        "partner.owner_invitation_resent",
        "partner.owner_invitation_revoked",
    } <= set(by_action)
    for action in (
        "partner.owner_invited",
        "partner.owner_invitation_resent",
        "partner.owner_invitation_revoked",
    ):
        line = by_action[action]
        assert line["actor"] == operator.email
        assert operator.email in line["summary"] and email in line["summary"]
        assert "Acme" in line["summary"] and "?" not in line["summary"]
    assert "console_enabled" not in json.dumps(lines)
    # Only this partner's rows.
    assert other["invitation"]["email"] not in json.dumps(lines)


async def test_the_audit_read_refuses_an_unknown_partner(client, admin_headers) -> None:
    res = await client.get(f"/admin/partners/{uuid.uuid4()}/audit-log", headers=admin_headers)
    assert res.status_code == 404


async def test_the_partner_reads_the_same_action_signed_by_auphere(
    client, db_session, op_headers, operator
) -> None:
    created = (await _create(client, op_headers, name="Acme")).json()
    email = created["invitation"]["email"]
    token = _token(created["invitation"]["accept_url"])
    await client.post(
        f"/console/invitations/{token}/accept", headers=_svc(), json={"password": PASSWORD}
    )
    pid = uuid.UUID(created["id"])
    member = await db_session.scalar(
        sa.select(PartnerMembership).where(PartnerMembership.partner_id == pid)
    )
    res = await client.get(
        "/console/audit?lang=es",
        headers=console_headers(user_id=member.user_id, partner_id=pid),
    )
    assert res.status_code == 200, res.text
    [line] = [i for i in res.json()["items"] if i["action"] == "partner.owner_invited"]
    assert line["summary"].startswith("Auphere ")
    assert email in line["summary"] and "Acme" in line["summary"]
    assert operator.email not in json.dumps(res.json())


async def test_no_audit_row_ever_holds_the_token_or_the_link(
    client, db_session, op_headers
) -> None:
    created = (await _create(client, op_headers)).json()
    pid = created["id"]
    tokens = [_token(created["invitation"]["accept_url"])]
    resent = (
        await client.post(
            _resend_url(pid, created["invitation"]["id"]), headers=op_headers, json={}
        )
    ).json()
    tokens.append(_token(resent["accept_url"]))
    await client.post(_revoke_url(pid, resent["id"]), headers=op_headers, json={})
    invited = (await _invite(client, op_headers, pid)).json()
    tokens.append(_token(invited["accept_url"]))

    db_session.expire_all()
    rows = await db_session.scalars(sa.select(AuditLog).where(AuditLog.target == f"partner:{pid}"))
    dumped = json.dumps(
        [[r.actor, r.action, r.target, r.before_json, r.after_json] for r in rows], default=str
    )
    assert "invited" in dumped
    for token in tokens:
        assert token not in dumped
    assert "/invite/" not in dumped


# ── T022 · Requisito 3, inviting from the Team tab ────────────────────────────


async def test_an_existing_partner_is_invited_when_the_operator_presses(
    client, db_session, admin_headers, op_headers, monkeypatch
) -> None:
    sink = Sink(monkeypatch)
    pid = await _bare_partner(db_session, contact="contacto@negocio.test")

    before = await _members(client, admin_headers, pid)
    assert before["owner"]["can_invite"] is True
    assert before["owner"]["suggested_email"] == "contacto@negocio.test"
    # R3.2: reading it suggested something and sent nothing.
    assert sink.calls == []

    email = _address()
    res = await _invite(client, op_headers, pid, email)
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["email"] == email and body["role"] == "owner" and body["email_sent"] is True
    assert body["accept_url"].startswith(get_settings().console_base_url)
    assert len(sink.calls) == 1

    after = await _members(client, admin_headers, pid)
    assert after["owner"]["can_invite"] is False
    [invitation] = after["invitations"]
    assert invitation["from_auphere"] is True and invitation["last_sent_at"] is not None
    # R1.10: there was a contact and this does not replace an invitation.
    db_session.expire_all()
    partner = await db_session.get(Partner, pid)
    assert partner.contact_email == "contacto@negocio.test"


async def test_an_empty_contact_takes_the_invited_address(
    client, db_session, op_headers, operator
) -> None:
    pid = await _bare_partner(db_session, contact=None)
    email = _address()
    assert (await _invite(client, op_headers, pid, email)).status_code == 201
    db_session.expire_all()
    assert (await db_session.get(Partner, pid)).contact_email == email
    [row] = await _audit(db_session, pid, "partner.owner_invited")
    assert row.actor == f"operator:{operator.email}"
    assert row.after_json["contact_email"] == email


async def test_a_partner_with_an_active_owner_is_not_invited(
    client, admin_headers, op_headers, console_world
) -> None:
    a = console_world["a"]
    res = await _invite(client, op_headers, a["partner_id"])
    assert res.status_code == 409
    assert res.json()["detail"]["code"] == "has_active_owner"
    state = (await _members(client, admin_headers, a["partner_id"]))["owner"]
    assert state["has_active_owner"] is True
    assert state["can_invite"] is False


async def test_a_second_live_invitation_is_refused_to_any_address(
    client, db_session, op_headers
) -> None:
    pid = await _bare_partner(db_session)
    email = _address()
    assert (await _invite(client, op_headers, pid, email)).status_code == 201
    for address in (email, _address()):
        res = await _invite(client, op_headers, pid, address)
        assert res.status_code == 409
        assert res.json()["detail"]["code"] == "invitation_pending"


async def test_two_simultaneous_invitations_leave_one(client, db_session, op_headers) -> None:
    pid = await _bare_partner(db_session)
    first, second = await asyncio.gather(
        _invite(client, op_headers, pid), _invite(client, op_headers, pid)
    )
    assert sorted([first.status_code, second.status_code]) == [201, 409]
    db_session.expire_all()
    live = await db_session.scalars(
        sa.select(PartnerInvitation).where(
            PartnerInvitation.partner_id == pid, PartnerInvitation.status == "pending"
        )
    )
    assert len(list(live)) == 1


async def test_a_console_that_is_off_is_refused_and_says_so(
    client, db_session, admin_headers, op_headers
) -> None:
    pid = await _bare_partner(db_session, console=False)
    res = await _invite(client, op_headers, pid)
    assert res.status_code == 409
    assert res.json()["detail"]["code"] == "console_off"
    state = (await _members(client, admin_headers, pid))["owner"]
    assert state["can_invite"] is False
    assert state["block"] == "console_off"


async def test_a_suspended_partner_is_refused_and_says_so(
    client, db_session, admin_headers, op_headers
) -> None:
    pid = await _bare_partner(db_session, status="suspended")
    res = await _invite(client, op_headers, pid)
    assert res.status_code == 409
    assert res.json()["detail"]["code"] == "partner_suspended"
    state = (await _members(client, admin_headers, pid))["owner"]
    assert state["can_invite"] is False
    assert state["block"] == "suspended"


async def test_someone_of_this_team_is_refused(client, db_session, op_headers) -> None:
    pid = await _bare_partner(db_session)
    db_session.add(
        PartnerMembership(
            id=uuid.uuid4(),
            partner_id=pid,
            user_id=f"user_{uuid.uuid4().hex[:8]}",
            email="ya.dentro@negocio.test",
            role="analyst",
            status="active",
        )
    )
    await db_session.commit()
    res = await _invite(client, op_headers, pid, "Ya.Dentro@negocio.test")
    assert res.status_code == 409
    assert res.json()["detail"]["code"] == "already_in_team"


async def test_an_address_living_elsewhere_is_refused_when_inviting(
    client, db_session, op_headers, console_world
) -> None:
    pid = await _bare_partner(db_session)
    member = await db_session.get(PartnerMembership, console_world["a"]["membership_id"])
    res = await _invite(client, op_headers, pid, member.email)
    assert res.status_code == 409
    assert res.json()["detail"]["code"] == "address_has_own_console"


async def test_a_live_invitation_that_is_not_ours_is_shown_and_blocks_only_its_address(
    client, db_session, admin_headers, op_headers
) -> None:
    pid = await _bare_partner(db_session)
    theirs = await _old_invitation(db_session, pid, role="admin")
    team = await _members(client, admin_headers, pid)
    [listed] = team["invitations"]
    assert listed["id"] == str(theirs.id) and listed["from_auphere"] is False
    assert team["owner"]["can_invite"] is True

    res = await _invite(client, op_headers, pid, theirs.email)
    assert res.status_code == 409
    assert res.json()["detail"]["code"] == "address_already_invited"
    assert (await _invite(client, op_headers, pid)).status_code == 201


async def test_an_unknown_partner_cannot_be_invited(client, op_headers) -> None:
    res = await _invite(client, op_headers, uuid.uuid4())
    assert res.status_code == 404
    assert res.json()["detail"]["code"] == "partner_not_found"


async def test_an_expired_invitation_is_expired_everywhere(
    client, db_session, admin_headers, op_headers
) -> None:
    """R3.9, R3.10: nobody opened the link, so it still says ``pending``."""
    pid = await _bare_partner(db_session, contact="contacto@negocio.test")
    email = _address()
    old = await _old_invitation(db_session, pid, email=email, expired=True)

    team = await _members(client, admin_headers, pid)
    assert team["invitations"] == []
    state = team["owner"]
    assert state["can_invite"] is True
    assert state["expired_email"] == email
    assert datetime.fromisoformat(state["expired_at"]) == old.expires_at
    # Above the contact.
    assert state["suggested_email"] == email

    # It does not count as live, and its row does not stop the same address.
    res = await _invite(client, op_headers, pid, email)
    assert res.status_code == 201, res.text
    assert (await _row(db_session, old.id)).status == InvitationStatus.EXPIRED.value


async def test_an_expired_invitation_of_someone_else_does_not_count_as_ours(
    client, db_session, admin_headers
) -> None:
    pid = await _bare_partner(db_session)
    await _old_invitation(db_session, pid, role="admin", expired=True)
    state = (await _members(client, admin_headers, pid))["owner"]
    assert state["expired_email"] is None


async def test_with_an_owner_nothing_is_said_about_an_expired_invitation(
    client, db_session, admin_headers, console_world
) -> None:
    a = console_world["a"]
    await _old_invitation(db_session, a["partner_id"], expired=True)
    state = (await _members(client, admin_headers, a["partner_id"]))["owner"]
    assert state["expired_email"] is None


async def test_nothing_sends_itself(client, db_session, admin_headers, monkeypatch) -> None:
    """R3.11, Historia 4 escenario 5: ni la migración, ni leer, ni un proceso."""
    sink = Sink(monkeypatch)
    pid = await _bare_partner(db_session, contact="contacto@negocio.test")
    await _members(client, admin_headers, pid)
    await client.get(f"/admin/partners/{pid}", headers=admin_headers)
    assert sink.calls == []

    migration = (API_ROOT / "alembic/versions/0217_owner_invitation_sent_at.py").read_text()
    assert "send_template" not in migration and "services.email" not in migration
    worker = API_ROOT.parent / "worker" / "src"
    for path in worker.rglob("*.py"):
        assert "owner_invitation" not in path.read_text(), path


# ── T026 · Requisitos 4 y 5, resending and revoking ───────────────────────────


async def test_resending_kills_the_old_link_and_gives_a_full_term(
    client, db_session, op_headers
) -> None:
    created = (await _create(client, op_headers)).json()
    old = created["invitation"]
    old_row = await _row(db_session, old["id"])
    old_row.expires_at = datetime.now(UTC) + timedelta(days=1)
    await db_session.commit()

    res = await client.post(_resend_url(created["id"], old["id"]), headers=op_headers, json={})
    assert res.status_code == 201, res.text
    new = res.json()
    assert new["id"] != old["id"]
    assert new["email"] == old["email"] and new["role"] == "owner"
    assert new["accept_url"] != old["accept_url"]
    lifetime = datetime.fromisoformat(new["expires_at"]) - datetime.now(UTC)
    assert lifetime > INVITATION_TTL - timedelta(minutes=1)

    assert (await _row(db_session, old["id"])).status == "revoked"
    gone = await client.get(f"/console/invitations/{_token(old['accept_url'])}", headers=_svc())
    alive = await client.get(f"/console/invitations/{_token(new['accept_url'])}", headers=_svc())
    assert gone.status_code == 404
    assert alive.status_code == 200, alive.text


@pytest.mark.parametrize(
    ("change", "code"),
    [
        ({"status": "suspended"}, "partner_suspended"),
        ({"console_enabled": False}, "console_off"),
    ],
)
async def test_resending_is_refused_and_the_link_stays(
    client, db_session, admin_headers, op_headers, change, code
) -> None:
    created = (await _create(client, op_headers)).json()
    partner = await db_session.get(Partner, uuid.UUID(created["id"]))
    for field, value in change.items():
        setattr(partner, field, value)
    await db_session.commit()
    old = created["invitation"]

    res = await client.post(_resend_url(created["id"], old["id"]), headers=op_headers, json={})
    assert res.status_code == 409
    assert res.json()["detail"]["code"] == code
    assert (await _row(db_session, old["id"])).status == "pending"
    state = (await _members(client, admin_headers, created["id"]))["owner"]
    assert state["can_resend"] is False


async def test_resending_with_an_active_owner_is_refused_and_revoking_is_not(
    client, db_session, admin_headers, op_headers
) -> None:
    created = (await _create(client, op_headers)).json()
    pid = uuid.UUID(created["id"])
    db_session.add(
        PartnerMembership(
            id=uuid.uuid4(),
            partner_id=pid,
            user_id=f"user_{uuid.uuid4().hex[:8]}",
            email="otro.dueno@negocio.test",
            role="owner",
            status="active",
        )
    )
    await db_session.commit()
    iid = created["invitation"]["id"]

    res = await client.post(_resend_url(pid, iid), headers=op_headers, json={})
    assert res.status_code == 409
    assert res.json()["detail"]["code"] == "has_active_owner"
    assert (await _row(db_session, iid)).status == "pending"

    team = await _members(client, admin_headers, pid)
    assert team["owner"]["can_resend"] is False
    assert [i["from_auphere"] for i in team["invitations"]] == [True]

    revoked = await client.post(_revoke_url(pid, iid), headers=op_headers, json={})
    assert revoked.status_code == 200, revoked.text


async def test_resending_to_an_address_that_moved_elsewhere_is_refused(
    client, db_session, op_headers, console_world
) -> None:
    """Two live invitations in two partners are allowed, and the first to
    accept wins. Resending the loser would mail a link that fails on accept."""
    created = (await _create(client, op_headers)).json()
    member = await db_session.get(PartnerMembership, console_world["a"]["membership_id"])
    member.email = created["invitation"]["email"]
    await db_session.commit()
    iid = created["invitation"]["id"]
    res = await client.post(_resend_url(created["id"], iid), headers=op_headers, json={})
    assert res.status_code == 409
    assert res.json()["detail"]["code"] == "address_has_own_console"
    assert (await _row(db_session, iid)).status == "pending"


@pytest.mark.parametrize(
    ("status", "expired", "code"),
    [
        ("revoked", False, "invitation_revoked"),
        ("expired", True, "invitation_expired"),
        ("pending", True, "invitation_expired"),
    ],
)
async def test_resending_a_dead_invitation_says_which_death(
    client, db_session, op_headers, status, expired, code
) -> None:
    pid = await _bare_partner(db_session)
    row = await _old_invitation(db_session, pid, status=status, expired=expired)
    res = await client.post(_resend_url(pid, row.id), headers=op_headers, json={})
    assert res.status_code == 409
    assert res.json()["detail"]["code"] == code


async def test_resending_or_revoking_an_accepted_invitation_touches_nobody(
    client, db_session, op_headers
) -> None:
    """Historia 3, escenario 5."""
    created = (await _create(client, op_headers)).json()
    pid = uuid.UUID(created["id"])
    iid = created["invitation"]["id"]
    token = _token(created["invitation"]["accept_url"])
    accepted = await client.post(
        f"/console/invitations/{token}/accept", headers=_svc(), json={"password": PASSWORD}
    )
    assert accepted.status_code == 200, accepted.text

    for url in (_resend_url(pid, iid), _revoke_url(pid, iid)):
        res = await client.post(url, headers=op_headers, json={})
        assert res.status_code == 409, url
        assert res.json()["detail"]["code"] == "invitation_accepted"
    db_session.expire_all()
    member = await db_session.scalar(
        sa.select(PartnerMembership).where(PartnerMembership.partner_id == pid)
    )
    assert member is not None and member.status == "active"
    assert (await _row(db_session, iid)).status == "accepted"


@pytest.mark.parametrize(
    "state",
    [{}, {"status": "suspended"}, {"console_enabled": False}],
    ids=["healthy", "suspended", "console_off"],
)
async def test_revoking_kills_the_link_whatever_the_partner_state(
    client, db_session, op_headers, monkeypatch, state
) -> None:
    created = (await _create(client, op_headers)).json()
    pid = uuid.UUID(created["id"])
    partner = await db_session.get(Partner, pid)
    for field, value in state.items():
        setattr(partner, field, value)
    await db_session.commit()
    sink = Sink(monkeypatch)
    invitation = created["invitation"]

    res = await client.post(_revoke_url(pid, invitation["id"]), headers=op_headers, json={})
    assert res.status_code == 200, res.text
    assert res.json() == {
        "id": invitation["id"],
        "email": invitation["email"],
        "status": "revoked",
        "changed": True,
    }
    # R5.6: nobody is told.
    assert sink.calls == []
    # R5.3: the same as a link that does not exist.
    dead = await client.get(
        f"/console/invitations/{_token(invitation['accept_url'])}", headers=_svc()
    )
    unknown = await client.get(f"/console/invitations/{uuid.uuid4().hex}", headers=_svc())
    assert (dead.status_code, dead.content) == (unknown.status_code, unknown.content)
    assert dead.status_code == 404


async def test_revoking_twice_changes_nothing_and_audits_once(
    client, db_session, op_headers
) -> None:
    created = (await _create(client, op_headers)).json()
    pid, iid = created["id"], created["invitation"]["id"]
    first = await client.post(_revoke_url(pid, iid), headers=op_headers, json={})
    second = await client.post(_revoke_url(pid, iid), headers=op_headers, json={})
    assert first.status_code == second.status_code == 200
    assert second.json()["changed"] is False
    assert len(await _audit(db_session, pid, "partner.owner_invitation_revoked")) == 1


async def test_revoking_an_old_row_after_a_resend_does_not_touch_the_live_link(
    client, db_session, op_headers
) -> None:
    """Another operator resent while this tab was open: the old row is dead,
    the new link is not, and the answer has to let the screen say so."""
    created = (await _create(client, op_headers)).json()
    pid, old = created["id"], created["invitation"]
    new = (await client.post(_resend_url(pid, old["id"]), headers=op_headers, json={})).json()

    res = await client.post(_revoke_url(pid, old["id"]), headers=op_headers, json={})
    assert res.status_code == 200
    assert res.json()["changed"] is False
    assert (await _row(db_session, new["id"])).status == "pending"
    alive = await client.get(f"/console/invitations/{_token(new['accept_url'])}", headers=_svc())
    assert alive.status_code == 200


async def test_revoking_an_expired_invitation_changes_nothing(
    client, db_session, op_headers
) -> None:
    pid = await _bare_partner(db_session)
    row = await _old_invitation(db_session, pid, expired=True)
    res = await client.post(_revoke_url(pid, row.id), headers=op_headers, json={})
    assert res.status_code == 200
    assert res.json()["changed"] is False and res.json()["status"] == "expired"
    assert await _audit(db_session, pid, "partner.owner_invitation_revoked") == []


async def test_correcting_a_mistyped_address_moves_the_contact(
    client, db_session, admin_headers, op_headers
) -> None:
    """Historia 3, escenario 3."""
    wrong, right = "ana@negoci.test", "ana@negocio.test"
    created = (await _create(client, op_headers, email=wrong)).json()
    pid, iid = created["id"], created["invitation"]["id"]
    assert (
        await client.post(_revoke_url(pid, iid), headers=op_headers, json={})
    ).status_code == 200

    state = (await _members(client, admin_headers, pid))["owner"]
    assert state["can_invite"] is True
    # A revoked invitation is not offered back.
    assert state["expired_email"] is None

    res = await _invite(client, op_headers, pid, right)
    assert res.status_code == 201, res.text
    db_session.expire_all()
    assert (await db_session.get(Partner, uuid.UUID(pid))).contact_email == right
    rows = await _audit(db_session, pid, "partner.owner_invited")
    assert rows[-1].before_json == {"contact_email": wrong}
    assert rows[-1].after_json["contact_email"] == right


async def test_a_contact_edited_by_hand_stays(client, db_session, op_headers) -> None:
    created = (await _create(client, op_headers, email="ana@negoci.test")).json()
    pid, iid = created["id"], created["invitation"]["id"]
    partner = await db_session.get(Partner, uuid.UUID(pid))
    partner.contact_email = "facturas@negocio.test"
    await db_session.commit()
    await client.post(_revoke_url(pid, iid), headers=op_headers, json={})
    assert (await _invite(client, op_headers, pid, "ana@negocio.test")).status_code == 201
    db_session.expire_all()
    assert (await db_session.get(Partner, uuid.UUID(pid))).contact_email == "facturas@negocio.test"


async def test_an_accepted_invitation_is_not_replaced_when_it_comes_to_the_contact(
    client, db_session, op_headers
) -> None:
    """R1.10 speaks of the invitation being replaced. Someone who already went
    in and left did not leave their address up for replacement."""
    pid = await _bare_partner(db_session, contact="ana@negocio.test")
    await _old_invitation(db_session, pid, email="ana@negocio.test", status="accepted")
    assert (await _invite(client, op_headers, pid, "luis@negocio.test")).status_code == 201
    db_session.expire_all()
    assert (await db_session.get(Partner, pid)).contact_email == "ana@negocio.test"


async def test_revoke_and_accept_at_once_end_in_one_story(client, db_session, op_headers) -> None:
    """Whichever wins, what the operator read and what is in the base agree."""
    created = (await _create(client, op_headers)).json()
    pid = uuid.UUID(created["id"])
    invitation = created["invitation"]
    token = _token(invitation["accept_url"])
    revoked, accepted = await asyncio.gather(
        client.post(_revoke_url(pid, invitation["id"]), headers=op_headers, json={}),
        client.post(
            f"/console/invitations/{token}/accept", headers=_svc(), json={"password": PASSWORD}
        ),
    )
    db_session.expire_all()
    row = await _row(db_session, invitation["id"])
    member = await db_session.scalar(
        sa.select(PartnerMembership).where(PartnerMembership.partner_id == pid)
    )
    if accepted.status_code == 200:
        assert revoked.status_code == 409, revoked.text
        assert row.status == "accepted" and member is not None
    else:
        assert accepted.status_code == 404, accepted.text
        assert revoked.status_code == 200, revoked.text
        assert row.status == "revoked" and member is None


# ── what the independent review found ────────────────────────────────────────


@pytest.mark.parametrize(
    ("actor", "shown"),
    [
        ("console:ana@negocio.test", "ana@negocio.test"),
        ("admin:1a2b3c4d", "Auphere"),
    ],
)
async def test_the_panel_does_not_sign_a_partners_action_as_auphere(
    client, db_session, admin_headers, actor, shown
) -> None:
    pid = await _bare_partner(db_session)
    db_session.add(
        AuditLog(
            tenant_id=None,
            actor=actor,
            action="console.invitation.revoke",
            target=f"partner:{pid}",
            after_json={"email": "x@negocio.test"},
        )
    )
    await db_session.commit()
    res = await client.get(f"/admin/partners/{pid}/audit-log", headers=admin_headers)
    assert res.status_code == 200, res.text
    [line] = res.json()
    assert line["actor"] == shown
    assert line["summary"].startswith(f"{shown} ")


async def test_the_partner_finds_what_auphere_did_with_its_filter(
    client, db_session, op_headers
) -> None:
    """The console filters «Auphere» by ``admin:``, and an operator writes
    ``operator:``: ``partner.create`` used to be found, and would have stopped."""
    created = (await _create(client, op_headers, name="Acme")).json()
    token = _token(created["invitation"]["accept_url"])
    await client.post(
        f"/console/invitations/{token}/accept", headers=_svc(), json={"password": PASSWORD}
    )
    pid = uuid.UUID(created["id"])
    member = await db_session.scalar(
        sa.select(PartnerMembership).where(PartnerMembership.partner_id == pid)
    )
    res = await client.get(
        "/console/audit?lang=es&actor=admin:",
        headers=console_headers(user_id=member.user_id, partner_id=pid),
    )
    assert res.status_code == 200, res.text
    actions = {i["action"] for i in res.json()["items"]}
    assert {"partner.create", "partner.owner_invited"} <= actions
