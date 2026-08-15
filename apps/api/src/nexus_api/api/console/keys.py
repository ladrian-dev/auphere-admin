"""``/console/keys`` — the partner's API keys (CP-27 backend).

Same lifecycle as the backoffice (``api/admin/partners.py``): create
(plaintext shown once), rotate with a grace window, revoke immediately,
list with last use. Two console-specific rules:

- **Keys are created only here, never by API** (Anthropic's rule, copied):
  there is no ``/v2/partners/keys`` and there will not be one.
- **Partner-level scopes only.** A tenant-bound ``messages_send`` key is
  created from the client's page (later package), so a leaked
  provisioning key cannot message anyone's customers.

Every action leaves both an ``embed_audit_log`` event (the partner
platform's own trail, keyed by ``api_key_id``) and an ``audit_log`` row
the console's audit page can render.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from nexus_api.api.deps import get_db_session
from nexus_api.core.console_auth import ConsolePrincipal, require_console_principal
from nexus_api.core.partner_keys import generate_api_key
from nexus_api.db.models import AuditLog, PartnerApiKey
from nexus_api.repositories.partner import EmbedAuditRepository, PartnerApiKeyRepository

from .schemas import ApiKeyCreatedOut, ApiKeyCreateIn, ApiKeyOut, ApiKeyRotateIn

router = APIRouter(prefix="/keys")


def _audit(
    principal: ConsolePrincipal, action: str, key: PartnerApiKey, **extra: object
) -> AuditLog:
    return AuditLog(
        tenant_id=None,
        actor=principal.actor,
        action=action,
        target=f"partner:{principal.partner.id}",
        after_json={"prefix_snippet": key.prefix_snippet, "key_id": str(key.id), **extra},
    )


async def _own_key(
    session: AsyncSession, principal: ConsolePrincipal, key_id: uuid.UUID
) -> PartnerApiKey:
    key = await PartnerApiKeyRepository(session).get(key_id)
    if key is None or key.partner_id != principal.partner.id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="key not found")
    return key


@router.get("", response_model=list[ApiKeyOut])
async def list_keys(
    principal: ConsolePrincipal = Depends(require_console_principal("keys:read")),
    session: AsyncSession = Depends(get_db_session),
) -> list[ApiKeyOut]:
    async with session.begin():
        keys = await PartnerApiKeyRepository(session).list_for_partner(principal.partner.id)
        return [ApiKeyOut.model_validate(k) for k in keys]


@router.post("", response_model=ApiKeyCreatedOut, status_code=status.HTTP_201_CREATED)
async def create_key(
    body: ApiKeyCreateIn,
    principal: ConsolePrincipal = Depends(require_console_principal("keys:manage")),
    session: AsyncSession = Depends(get_db_session),
) -> ApiKeyCreatedOut:
    generated = generate_api_key(body.type)
    async with session.begin():
        key = await PartnerApiKeyRepository(session).create(
            PartnerApiKey(
                id=uuid.uuid4(),
                partner_id=principal.partner.id,
                type=body.type,
                prefix_snippet=generated.prefix_snippet,
                key_hash=generated.key_hash,
                scopes=list(body.scopes),
                allowed_origins=list(body.allowed_origins),
                expires_at=body.expires_at,
            )
        )
        await EmbedAuditRepository(session).record(
            event="key.created",
            partner_id=principal.partner.id,
            api_key_id=key.id,
            payload={"type": body.type, "scopes": list(body.scopes), "actor": principal.actor},
        )
        session.add(_audit(principal, "console.key.create", key, type=body.type))
        out = ApiKeyCreatedOut(
            plaintext=generated.plaintext, **ApiKeyOut.model_validate(key).model_dump()
        )
    return out


@router.post(
    "/{key_id}/rotate",
    response_model=ApiKeyCreatedOut,
    status_code=status.HTTP_201_CREATED,
    responses={409: {"description": "Key already revoked."}},
)
async def rotate_key(
    key_id: uuid.UUID,
    body: ApiKeyRotateIn,
    principal: ConsolePrincipal = Depends(require_console_principal("keys:manage")),
    session: AsyncSession = Depends(get_db_session),
) -> ApiKeyCreatedOut:
    async with session.begin():
        old = await _own_key(session, principal, key_id)
        if old.revoked_at is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="key is already revoked"
            )
        now = datetime.now(UTC)
        old.revoked_at = now
        old.grace_expires_at = now + timedelta(hours=body.grace_hours)
        generated = generate_api_key(old.type)
        new = await PartnerApiKeyRepository(session).create(
            PartnerApiKey(
                id=uuid.uuid4(),
                partner_id=principal.partner.id,
                type=old.type,
                prefix_snippet=generated.prefix_snippet,
                key_hash=generated.key_hash,
                scopes=list(old.scopes or []),
                allowed_origins=list(old.allowed_origins or []),
                expires_at=old.expires_at,
            )
        )
        await EmbedAuditRepository(session).record(
            event="key.rotated",
            partner_id=principal.partner.id,
            api_key_id=new.id,
            payload={
                "replaces": str(key_id),
                "grace_hours": body.grace_hours,
                "actor": principal.actor,
            },
        )
        session.add(_audit(principal, "console.key.rotate", new, replaces=old.prefix_snippet))
        out = ApiKeyCreatedOut(
            plaintext=generated.plaintext, **ApiKeyOut.model_validate(new).model_dump()
        )
    return out


@router.post("/{key_id}/revoke", response_model=ApiKeyOut)
async def revoke_key(
    key_id: uuid.UUID,
    principal: ConsolePrincipal = Depends(require_console_principal("keys:manage")),
    session: AsyncSession = Depends(get_db_session),
) -> ApiKeyOut:
    async with session.begin():
        key = await _own_key(session, principal, key_id)
        key.revoked_at = datetime.now(UTC)
        key.grace_expires_at = None
        await EmbedAuditRepository(session).record(
            event="key.revoked",
            partner_id=principal.partner.id,
            api_key_id=key.id,
            payload={"actor": principal.actor},
        )
        session.add(_audit(principal, "console.key.revoke", key))
        out = ApiKeyOut.model_validate(key)
    return out
