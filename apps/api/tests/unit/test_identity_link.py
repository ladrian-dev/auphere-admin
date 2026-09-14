"""Vincular con un proveedor externo — spec 006, Requisitos 5.2 y 5.3."""

from __future__ import annotations

import uuid

import pytest

from nexus_api.services import console_identity
from nexus_api.services.identity_link import resolve_provider_identity

pytestmark = pytest.mark.asyncio


async def _cuenta(db_session, email: str):
    cuenta = await console_identity.create_account(
        db_session, email=email, password="una-contrasena-larga", display_name=None
    )
    await db_session.commit()
    return cuenta


class TestElAncla:
    async def test_el_correo_que_ya_tiene_cuenta_se_vincula_a_esa_misma_cuenta(
        self, db_session
    ) -> None:
        """Requisito 5.2: nunca una segunda cuenta."""
        email = f"link-{uuid.uuid4().hex[:8]}@agencia.com"
        cuenta = await _cuenta(db_session, email)

        out = await resolve_provider_identity(
            db_session, provider="google", subject="sub-123", email=email
        )
        await db_session.commit()
        assert out.kind == "attached"
        assert out.account is not None and out.account.id == cuenta.id

    async def test_el_subject_manda_sobre_el_correo(self, db_session) -> None:
        """Requisito 5.3, y es lo que protege de que un correo cambie de dueño.

        Segunda vuelta con el MISMO `sub` pero otro correo: tiene que seguir
        resolviendo a la misma cuenta. Si el ancla fuera el correo, esta
        persona sería otra — y quien heredase su vieja dirección sería ella.
        """
        email = f"movil-{uuid.uuid4().hex[:8]}@agencia.com"
        cuenta = await _cuenta(db_session, email)
        sub = f"sub-{uuid.uuid4().hex[:10]}"
        await resolve_provider_identity(db_session, provider="google", subject=sub, email=email)
        await db_session.commit()

        otra_direccion = f"nueva-{uuid.uuid4().hex[:8]}@otra.com"
        out = await resolve_provider_identity(
            db_session, provider="google", subject=sub, email=otra_direccion
        )
        await db_session.commit()
        assert out.kind == "linked"
        assert out.account is not None and out.account.id == cuenta.id

    async def test_un_subject_distinto_con_el_mismo_correo_no_secuestra(self, db_session) -> None:
        """El reverso: otro `sub` que dice tener el mismo correo se cuelga de
        la cuenta sólo porque el correo **ya fue verificado por el proveedor**.
        Lo que no puede es quedarse con el vínculo del primero."""
        email = f"dos-{uuid.uuid4().hex[:8]}@agencia.com"
        await _cuenta(db_session, email)
        a = await resolve_provider_identity(
            db_session, provider="google", subject="sub-A", email=email
        )
        await db_session.commit()
        b = await resolve_provider_identity(
            db_session, provider="google", subject="sub-B", email=email
        )
        await db_session.commit()
        assert a.account is not None and b.account is not None
        assert a.account.id == b.account.id, "misma persona, misma cuenta"


class TestCuandoNoHayCuenta:
    async def test_no_se_crea_nada_aqui(self, db_session) -> None:
        """Crear cuenta es parte del alta, con sus reglas: bandera, solicitud y
        nombre de empresa. Este módulo no las conoce y no debe saltárselas."""
        out = await resolve_provider_identity(
            db_session,
            provider="google",
            subject=f"sub-{uuid.uuid4().hex[:10]}",
            email=f"nadie-{uuid.uuid4().hex[:8]}@agencia.com",
        )
        assert out.kind == "unknown"
        assert out.account is None
