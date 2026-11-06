"""Spec 055, Requisito 1: «recuperar» con una invitación sin aceptar.

La cuenta nace al aceptar. Sin cuenta, pedir recuperar no enviaba nada; ahora se
reenvía la invitación viva más reciente, con un enlace nuevo, y la respuesta
sigue siendo la misma byte a byte para cualquier dirección (R1.6).
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import pytest
import sqlalchemy as sa

from nexus_api.db.models import AuditLog, ClientInvitation, Partner, PartnerInvitation
from nexus_api.repositories.partner_membership import PartnerInvitationRepository
from nexus_api.services import client_access, operator_identity
from nexus_api.services.email_catalog import EmailKind
from nexus_api.services.invitation_reissue import ACTOR
from tests.conftest import console_headers, make_client_access

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


def _svc() -> dict[str, str]:
    return console_headers(user_id="console-bff", partner_id=None, service=True)


def _address(prefix: str = "invitada") -> str:
    return f"{prefix}-{uuid.uuid4().hex[:8]}@negocio.com"


def _sink(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Los correos, en vez de mandarlos: el de equipo y propietario sale por
    ``send_template`` y el de cliente por ``send_localized``."""
    sent: list[dict[str, Any]] = []

    async def template(kind: EmailKind, **kwargs: Any) -> bool:
        sent.append({"kind": kind, **kwargs})
        return True

    async def localized(kind: EmailKind, *, to: Any, compose: Any, **kwargs: Any) -> bool:
        subject, variables = compose("es")
        sent.append({"kind": kind, "to": to, "subject": subject, "variables": dict(variables)})
        return True

    monkeypatch.setattr("nexus_api.services.email.send_template", template)
    monkeypatch.setattr("nexus_api.services.owner_invitation.send_template", template)
    monkeypatch.setattr("nexus_api.services.email.send_localized", localized)
    return sent


async def _ask(client: Any, email: str) -> Any:
    return await client.post("/console/password-reset", json={"email": email}, headers=_svc())


def _token(sent: dict[str, Any]) -> str:
    url: str = sent["variables"]["ACCEPT_URL"]
    return url.rsplit("/", 1)[-1]


@pytest.fixture
async def op_headers(db_session: Any, admin_headers: dict[str, str]) -> dict[str, str]:
    account = await operator_identity.create_account(
        db_session,
        email=f"op-{uuid.uuid4().hex[:8]}@auphere.test",
        password="operator-password-1",
        role="admin",
    )
    await db_session.commit()
    op = SimpleNamespace(id=account.id)
    return {**admin_headers, "X-Operator-Id": str(op.id)}


async def _pending(db_session: Any, email: str) -> list[PartnerInvitation]:
    db_session.expire_all()
    rows = await db_session.scalars(
        sa.select(PartnerInvitation).where(
            PartnerInvitation.email == email, PartnerInvitation.status == "pending"
        )
    )
    return list(rows)


class TestThePanelInvitesTheOwner:
    async def test_creating_a_partner_sends_the_invitation_and_its_link_lets_them_register(
        self, client: Any, op_headers: dict[str, str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sent = _sink(monkeypatch)
        email = _address("duena")
        resp = await client.post(
            "/admin/partners",
            headers=op_headers,
            json={"name": "Autprod", "slug": f"p-{uuid.uuid4().hex[:10]}", "owner_email": email},
        )
        assert resp.status_code == 201, resp.text
        assert resp.json()["invitation"]["email_sent"] is True
        assert [m["kind"] for m in sent] == [EmailKind.TEAM_INVITE] and sent[0]["to"] == email
        accepted = await client.post(
            f"/console/invitations/{_token(sent[0])}/accept",
            json={"password": "una-contrasena-larga", "display_name": "Neliana"},
            headers=_svc(),
        )
        assert accepted.status_code in (200, 201), accepted.text


class TestForgotResendsALiveInvitation:
    async def test_the_owner_gets_the_invitation_again_and_the_old_link_dies(
        self,
        client: Any,
        db_session: Any,
        op_headers: dict[str, str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        sent = _sink(monkeypatch)
        email = _address("duena")
        created = await client.post(
            "/admin/partners",
            headers=op_headers,
            json={"name": "Autprod", "slug": f"p-{uuid.uuid4().hex[:10]}", "owner_email": email},
        )
        assert created.status_code == 201, created.text
        partner_id = uuid.UUID(created.json()["id"])
        old = _token(sent[-1])

        assert (await _ask(client, email)).status_code == 202
        assert len(sent) == 2 and sent[-1]["kind"] is EmailKind.TEAM_INVITE
        new = _token(sent[-1])
        assert new != old
        repo = PartnerInvitationRepository(db_session)
        assert await repo.get_pending_by_token(old) is None
        fresh = await repo.get_pending_by_token(new)
        assert fresh is not None and fresh.partner_id == partner_id and fresh.role == "owner"
        assert fresh.invited_by is None

    async def test_a_team_invitation_keeps_its_role_and_who_invited(
        self,
        client: Any,
        db_session: Any,
        console_world: dict[str, Any],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        sent = _sink(monkeypatch)
        a = console_world["a"]
        email = _address("equipo")
        resp = await client.post(
            "/console/team/invitations",
            json={"email": email, "role": "builder"},
            headers=a["headers"](),
        )
        assert resp.status_code == 201, resp.text
        old = resp.json()["accept_path"].rsplit("/", 1)[-1]

        assert (await _ask(client, email)).status_code == 202
        assert sent[-1]["kind"] is EmailKind.TEAM_INVITE and sent[-1]["to"] == email
        pending = await _pending(db_session, email)
        assert len(pending) == 1
        assert pending[0].role == "builder" and pending[0].partner_id == a["partner_id"]
        assert pending[0].invited_by == a["membership_id"]
        assert await PartnerInvitationRepository(db_session).get_pending_by_token(old) is None
        audit = await db_session.scalar(
            sa.select(AuditLog).where(
                AuditLog.actor == ACTOR, AuditLog.target == f"partner:{a['partner_id']}"
            )
        )
        assert audit is not None and audit.after_json == {"email": email, "role": "builder"}

    async def test_a_client_invitation_is_sent_again(
        self,
        client: Any,
        db_session: Any,
        console_world: dict[str, Any],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from nexus_api.core.tenant_context import declare_tenant

        sent = _sink(monkeypatch)
        a = console_world["a"]
        await make_client_access(db_session, partner_id=a["partner_id"], tenant_id=a["tenant_id"])
        email = _address("cliente")
        async with db_session.begin():
            await declare_tenant(db_session, a["tenant_id"])
            first, _token_plain = await client_access.invite(
                db_session, a["tenant_id"], email=email, name="Ana", actor="operator:tests"
            )
            first_id = first.id

        assert (await _ask(client, email)).status_code == 202
        assert sent[-1]["kind"] is EmailKind.CLIENT_INVITE and sent[-1]["to"] == email
        db_session.expire_all()
        async with db_session.begin():
            await declare_tenant(db_session, a["tenant_id"])
            old = await db_session.get(ClientInvitation, first_id)
            live = await db_session.scalar(
                sa.select(ClientInvitation).where(
                    ClientInvitation.email == email, ClientInvitation.status == "pending"
                )
            )
        assert old is not None and old.status == "revoked"
        assert live is not None and live.tenant_id == a["tenant_id"]


class TestNothingToResend:
    async def test_without_account_or_invitation_nothing_is_sent(
        self, client: Any, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        sent = _sink(monkeypatch)
        assert (await _ask(client, _address("nadie"))).status_code == 202
        assert sent == []

    async def test_an_expired_invitation_is_not_sent(
        self,
        client: Any,
        db_session: Any,
        console_world: dict[str, Any],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        sent = _sink(monkeypatch)
        email = _address("vencida")
        async with db_session.begin():
            row, _ = await PartnerInvitationRepository(db_session).create(
                partner_id=console_world["a"]["partner_id"],
                email=email,
                role="builder",
                invited_by=None,
            )
            row.expires_at = datetime.now(UTC) - timedelta(minutes=1)
        assert (await _ask(client, email)).status_code == 202
        assert sent == []

    async def test_a_suspended_partner_sends_nothing_and_answers_the_same(
        self,
        client: Any,
        db_session: Any,
        console_world: dict[str, Any],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        sent = _sink(monkeypatch)
        a = console_world["a"]
        email = _address("suspendida")
        resp = await client.post(
            "/console/team/invitations",
            json={"email": email, "role": "builder"},
            headers=a["headers"](),
        )
        assert resp.status_code == 201, resp.text
        sent.clear()
        async with db_session.begin():
            partner = await db_session.get(Partner, a["partner_id"])
            assert partner is not None
            partner.status = "suspended"
        answer = await _ask(client, email)
        assert answer.status_code == 202 and sent == []
        assert len(await _pending(db_session, email)) == 1


class TestTheAnswerSaysNothing:
    async def test_same_answer_with_account_invitation_expired_or_nothing(
        self,
        client: Any,
        db_session: Any,
        console_world: dict[str, Any],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        from nexus_api.services import console_identity

        _sink(monkeypatch)
        account = await console_identity.create_account(
            db_session, email=_address("cuenta"), password="una-contrasena-larga", display_name="X"
        )
        await db_session.commit()
        invited = _address("invitada")
        await client.post(
            "/console/team/invitations",
            json={"email": invited, "role": "builder"},
            headers=console_world["a"]["headers"](),
        )
        expired = _address("vencida")
        async with db_session.begin():
            row, _ = await PartnerInvitationRepository(db_session).create(
                partner_id=console_world["a"]["partner_id"],
                email=expired,
                role="builder",
                invited_by=None,
            )
            row.expires_at = datetime.now(UTC) - timedelta(minutes=1)
        answers = [
            await _ask(client, address)
            for address in (account.email, invited, expired, _address("nadie"))
        ]
        assert {a.status_code for a in answers} == {202}
        assert len({a.content for a in answers}) == 1, "el cuerpo delata algún caso"
