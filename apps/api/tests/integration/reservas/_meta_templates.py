"""Spec 043, requisito 15 — Meta simulado para las plantillas de Reservas.

Hace de ``MetaClient`` en lo que usa la creación automática (listar y crear) y
apunta cada llamada con su WABA y su token: las pruebas de aislamiento miran
con qué credenciales se le habló. No hay red: nada sale a Meta.
"""

from __future__ import annotations

import uuid
from typing import Any

import sqlalchemy as sa
from nexus_channels.whatsapp_meta.credentials import MetaCredentials

from nexus_api.db.models import TenantCredentials, WhatsAppTemplateStatus

SIX = (
    "reserva_confirmada",
    "reserva_pide_confirmacion",
    "reserva_recordatorio",
    "reserva_cambiada",
    "reserva_cancelada",
    "reserva_hueco_libre",
)


def token_of(waba_id: str) -> str:
    return f"EAA-{waba_id}"


class FakeMeta:
    """Lo que Meta tiene en cada WABA y lo que se le pidió.

    ``fail_list`` / ``fail_create`` fallan a la carta (por WABA, o por WABA y
    plantilla); ``page_size`` parte el listado en páginas con cursor como Meta.
    """

    def __init__(self, *, page_size: int = 100) -> None:
        self.page_size = page_size
        self.wabas: dict[str, list[dict[str, Any]]] = {}
        self.calls: list[tuple[str, str, str, str | None]] = []
        self.created: list[dict[str, Any]] = []
        self.fail_list: dict[str, Exception] = {}
        self.fail_create: dict[tuple[str, str], Exception] = {}
        self.closed = False

    def has(self, waba_id: str, name: str, *, language: str = "es", status: str = "APPROVED"):
        self.wabas.setdefault(waba_id, []).append(
            {
                "id": f"meta-{waba_id}-{name}-{language}",
                "name": name,
                "language": language,
                "status": status,
                "category": "UTILITY",
            }
        )

    async def list_templates(
        self, *, waba_id: str, access_token: str, limit: int = 100, after: str | None = None
    ) -> dict[str, Any]:
        self.calls.append(("list", waba_id, access_token, after))
        if waba_id in self.fail_list:
            raise self.fail_list[waba_id]
        items = self.wabas.get(waba_id, [])
        start = int(after or 0)
        size = min(limit, self.page_size)
        out: dict[str, Any] = {"data": list(items[start : start + size])}
        if start + size < len(items):
            out["paging"] = {
                "cursors": {"before": str(start), "after": str(start + size)},
                "next": f"https://graph.facebook.com/v26.0/{waba_id}/message_templates?after={start + size}",
            }
        return out

    async def create_template(
        self,
        *,
        waba_id: str,
        access_token: str,
        name: str,
        language: str,
        category: str,
        components: list[dict[str, Any]],
        parameter_format: str | None = None,
    ) -> dict[str, Any]:
        self.calls.append(("create", waba_id, access_token, name))
        failure = self.fail_create.get((waba_id, name))
        if failure is not None:
            raise failure
        self.created.append(
            {
                "waba_id": waba_id,
                "name": name,
                "language": language,
                "category": category,
                "components": components,
                "parameter_format": parameter_format,
            }
        )
        meta_id = f"meta-{waba_id}-{name}"
        self.wabas.setdefault(waba_id, []).append(
            {"id": meta_id, "name": name, "language": language, "status": "PENDING"}
        )
        return {"id": meta_id, "status": "PENDING", "category": category}

    async def delete_template(self, **kw: Any) -> dict[str, Any]:  # pragma: no cover - never
        self.calls.append(("delete", kw.get("waba_id", ""), kw.get("access_token", ""), None))
        raise AssertionError("Reservas never deletes a template")

    async def close(self) -> None:
        self.closed = True

    def ops(self, op: str, waba_id: str | None = None) -> list[str | None]:
        return [n for o, w, _t, n in self.calls if o == op and (waba_id is None or w == waba_id)]


async def seed_creds(db_session, tenant_id: uuid.UUID, *, waba_id: str) -> None:
    """Las credenciales de Meta del cliente, escritas bajo su RLS."""
    creds = MetaCredentials(
        bisuat=token_of(waba_id),
        waba_id=waba_id,
        phone_number_id=f"PN-{waba_id}",
        business_id=f"BIZ-{waba_id}",
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


async def seed_mirror(
    db_session,
    *,
    waba_id: str,
    tenant_id: uuid.UUID | None,
    name: str,
    status: str,
    language: str = "es",
    reason: str | None = None,
) -> None:
    """Una fila del espejo, como la deja el webhook de Meta."""
    db_session.add(
        WhatsAppTemplateStatus(
            waba_id=waba_id,
            tenant_id=tenant_id,
            template_name=name,
            language=language,
            status=status,
            reason=reason,
            last_event_payload={},
        )
    )
    await db_session.commit()


async def mirror(db_session, waba_id: str) -> dict[str, WhatsAppTemplateStatus]:
    rows = await db_session.execute(
        sa.select(WhatsAppTemplateStatus).where(WhatsAppTemplateStatus.waba_id == waba_id)
    )
    out = {r.template_name: r for r in rows.scalars()}
    await db_session.commit()
    return out
