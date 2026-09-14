"""Solicitudes de alta — spec 006, Requisito 1.

Del token se guarda **sólo** el SHA-256. El claro se devuelve una vez, va
dentro del enlace del correo, y no se escribe en ningún registro ni traza.
Mismo patrón que ``partner_invitations`` y ``console_auth.principal_sessions``:
un volcado de esta tabla no permite completar ningún alta.

**Una pendiente por correo.** Pedir el alta dos veces no crea dos solicitudes:
revoca la anterior y emite una nueva. Si no, un enlace viejo seguiría abriendo
la puerta después de que su dueño pidiera otro — y el motivo habitual para
pedir otro es sospechar del primero.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid
from datetime import UTC, datetime, timedelta

import sqlalchemy as sa
from sqlalchemy.engine import CursorResult
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.db.models import SignupRequest, SignupStatus


def hash_signup_token(plaintext: str) -> str:
    """SHA-256 hex. Sin sal: el token ya es aleatorio de 256 bits, así que no
    hay diccionario que precomputar — la sal protege secretos con poca entropía,
    que no es el caso."""
    return hashlib.sha256(plaintext.encode("utf-8")).hexdigest()


def hash_ip(ip: str | None) -> str | None:
    """La IP, hasheada. Sirve para correlacionar un abuso, que es para lo único
    que se quiere, y deja de ser un dato personal en claro en la base."""
    return None if ip is None else hashlib.sha256(ip.encode("utf-8")).hexdigest()


def _now() -> datetime:
    return datetime.now(UTC)


class SignupRequestRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        email: str,
        ttl_hours: int,
        provider: str | None = None,
        ip: str | None = None,
    ) -> tuple[SignupRequest, str]:
        """Emite una solicitud. Devuelve ``(fila, token_en_claro)``; el claro
        **no se almacena** y es lo único que abre el enlace."""
        normalised = email.strip().lower()
        await self.revoke_pending_for(normalised)
        plaintext = secrets.token_urlsafe(32)
        row = SignupRequest(
            id=uuid.uuid4(),
            email=normalised,
            token_hash=hash_signup_token(plaintext),
            status=SignupStatus.PENDING.value,
            expires_at=_now() + timedelta(hours=ttl_hours),
            provider=provider,
            created_ip_hash=hash_ip(ip),
        )
        self._session.add(row)
        await self._session.flush()
        return row, plaintext

    async def revoke_pending_for(self, email: str) -> int:
        """Revoca las pendientes de ese correo. Devuelve cuántas."""
        result: CursorResult[None] = await self._session.execute(  # type: ignore[assignment]
            sa.update(SignupRequest)
            .where(
                sa.func.lower(SignupRequest.email) == email.strip().lower(),
                SignupRequest.status == SignupStatus.PENDING.value,
            )
            .values(status=SignupStatus.REVOKED.value)
        )
        await self._session.flush()
        return int(result.rowcount or 0)

    async def get_pending_by_email(self, email: str) -> SignupRequest | None:
        """La pendiente viva de ese correo, si la hay. Sólo puede haber una:
        ``create`` revoca las anteriores."""
        return (
            await self._session.execute(
                sa.select(SignupRequest)
                .where(
                    sa.func.lower(SignupRequest.email) == email.strip().lower(),
                    SignupRequest.status == SignupStatus.PENDING.value,
                )
                .limit(1)
            )
        ).scalar_one_or_none()

    async def get_pending_by_token(self, plaintext: str) -> SignupRequest | None:
        """La solicitud detrás de un enlace.

        Devuelve ``None`` para inexistente, caducada, ya usada y revocada —
        **los cuatro casos son el mismo desde fuera**, que es lo que impide
        enumerar. La caducidad se marca aquí, perezosamente, para que el cron
        no sea la única forma de que un estado sea verdad.
        """
        row = (
            await self._session.execute(
                sa.select(SignupRequest)
                .where(SignupRequest.token_hash == hash_signup_token(plaintext))
                .limit(1)
            )
        ).scalar_one_or_none()
        if row is None or row.status != SignupStatus.PENDING.value:
            return None
        if row.expires_at <= _now():
            row.status = SignupStatus.EXPIRED.value
            await self._session.flush()
            return None
        return row

    async def expire_overdue(self) -> int:
        """Lo que barre el cron. Devuelve cuántas se marcaron."""
        result: CursorResult[None] = await self._session.execute(  # type: ignore[assignment]
            sa.update(SignupRequest)
            .where(
                SignupRequest.status == SignupStatus.PENDING.value,
                SignupRequest.expires_at <= _now(),
            )
            .values(status=SignupStatus.EXPIRED.value)
        )
        await self._session.flush()
        return int(result.rowcount or 0)
