"""Spec 030 — la sesión distingue a la persona de un cliente (R2.6, R2.7).

La consola resuelve quién está detrás de la cookie con
``load_principal_view``. Con la spec 030 esa respuesta tiene dos formas: la de
siempre para un miembro del partner y una nueva, ``kind = "client"``, para la
persona de un cliente. El login funciona en todos los casos; lo que cambia es
lo que la consola pinta.
"""

from __future__ import annotations

import uuid

import pytest
import sqlalchemy as sa
from sqlalchemy.ext.asyncio import async_sessionmaker

from nexus_api.api.console.auth import principal_out
from nexus_api.db.models import ClientAccess, ClientMembership
from nexus_api.services import console_identity
from tests.conftest import make_client_access

pytestmark = pytest.mark.asyncio


async def _account_with_client_membership(test_engine, w, *, status="active"):
    factory = async_sessionmaker(bind=test_engine, expire_on_commit=False)
    async with factory() as session, session.begin():
        account = await console_identity.create_account(
            session,
            email=f"valeria-{uuid.uuid4().hex[:6]}@minegocio.test",
            password="una-clave-larga-y-segura-2026",
            display_name="Valeria Ríos",
        )
        session.add(
            ClientMembership(
                partner_id=w["partner_id"],
                tenant_id=w["tenant_id"],
                user_id=str(account.id),
                email=account.email,
                display_name="Valeria Ríos",
                status=status,
                invited_by="operator:tests@auphere.com",
            )
        )
    return account


async def _view(test_engine, account):
    factory = async_sessionmaker(bind=test_engine, expire_on_commit=False)
    async with factory() as session, session.begin():
        return principal_out(await console_identity.load_principal_view(session, account))


async def test_client_account_resolves_as_client(db_session, console_world, test_engine) -> None:
    w = console_world["a"]
    await make_client_access(
        db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"], modules=("panel", "usage")
    )
    account = await _account_with_client_membership(test_engine, w)
    out = await _view(test_engine, account)
    assert out.access == "ok"
    assert out.kind == "client"
    assert out.role == "client"
    assert out.partner_id == w["partner_id"]
    assert out.partner_name == "Console Partner A"
    assert out.client_name == "Client A One"
    assert out.modules == ["panel", "usage"]
    # Ningún permiso del partner viaja a la consola de un cliente.
    assert out.permissions == []


async def test_access_switched_off_reads_as_disabled(
    db_session, console_world, test_engine
) -> None:
    w = console_world["a"]
    await make_client_access(
        db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"], enabled=False
    )
    account = await _account_with_client_membership(test_engine, w)
    out = await _view(test_engine, account)
    assert out.access == "disabled"
    assert out.kind == "client"
    assert out.modules == []


async def test_revoked_person_reads_as_suspended(db_session, console_world, test_engine) -> None:
    w = console_world["a"]
    await make_client_access(db_session, partner_id=w["partner_id"], tenant_id=w["tenant_id"])
    account = await _account_with_client_membership(test_engine, w, status="revoked")
    out = await _view(test_engine, account)
    assert out.access == "suspended"


async def test_partner_member_is_unchanged(db_session, console_world, test_engine) -> None:
    w = console_world["a"]
    factory = async_sessionmaker(bind=test_engine, expire_on_commit=False)
    async with factory() as session, session.begin():
        account = await console_identity.create_account(
            session,
            email=f"owner-{uuid.uuid4().hex[:6]}@partner.test",
            password="una-clave-larga-y-segura-2026",
        )
        await session.execute(
            sa.text("UPDATE partner_memberships SET user_id = :uid WHERE id = :mid"),
            {"uid": str(account.id), "mid": w["membership_id"]},
        )
    out = await _view(test_engine, account)
    assert out.access == "ok"
    assert out.kind == "partner"
    assert out.role == "owner"
    assert out.client_name is None
    assert out.modules == []
    assert "partner:read" in out.permissions


async def test_access_row_missing_reads_as_disabled(db_session, console_world, test_engine) -> None:
    """Una membresía sin fila de acceso es un acceso que nunca se encendió."""
    w = console_world["a"]
    account = await _account_with_client_membership(test_engine, w)
    await db_session.execute(sa.delete(ClientAccess))
    await db_session.commit()
    out = await _view(test_engine, account)
    assert out.access == "disabled"
