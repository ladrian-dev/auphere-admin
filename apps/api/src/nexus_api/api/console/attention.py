"""``GET /console/attention`` — «Lo que te necesita» (spec 071, requisito 1;
``contracts/api.md``).

La lista viva del partner, de peor a mejor: lo suyo (el tope de construcción, la cuenta,
el cobro) y lo de cada cliente, cada fila con su arreglo. Es la misma que el Panel
(``/console/home`` → ``panel.attention``): las dos salen de
``attention_live.live_attention`` con la puerta de quien mira. La lee la campana
(«Ahora») y Consumo.

Ni el partner ni los clientes llegan del llamante: el partner es el principal y los
clientes, los suyos de ``partner_tenants``.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from nexus_api.core.console_auth import ConsolePrincipal, require_console_principal
from nexus_api.services.attention import AttentionItem
from nexus_api.services.attention_live import Gate, live_attention

from .schemas_home_usage import AttentionListOut, PanelAttentionOut

router = APIRouter()


def attention_out(item: AttentionItem) -> PanelAttentionOut:
    return PanelAttentionOut(
        scope=item.scope,  # type: ignore[arg-type]
        severity=item.severity,  # type: ignore[arg-type]
        code=item.code,  # type: ignore[arg-type]
        external_client_ref=item.ref,
        client_name=item.name,
        count=item.count,
        action=item.action,  # type: ignore[arg-type]
        href=item.href,
        data=dict(item.data),
    )


@router.get("/attention", response_model=AttentionListOut)
async def get_attention(
    principal: ConsolePrincipal = Depends(require_console_principal("partner:read")),
) -> AttentionListOut:
    listed = await live_attention(principal.partner.id, gate=Gate.of(principal))
    return AttentionListOut(
        items=[attention_out(item) for item in listed.items], errors=listed.errors
    )


__all__ = ["attention_out", "router"]
