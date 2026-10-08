"""``/console/lite/*`` — la consola del cliente final (spec 030).

Todas las rutas de aquí se autorizan con
:func:`nexus_api.core.client_auth.require_client_principal`: solo las alcanza
la persona de un cliente, y ninguna lleva ``ref``, ``tenant_id`` ni
``partner_id``. La Bandeja (``/console/lite/inbox/*``) es la única parte de la
consola que puede devolver cuerpos de mensaje (C8, plan D5).
"""

from __future__ import annotations

from fastapi import APIRouter

from . import home, inbox, inbox_media, inbox_stream, me, notifications, usage

router = APIRouter(prefix="/lite", tags=["console-lite"])
router.include_router(me.router)
router.include_router(home.router)
router.include_router(usage.router)
# La Bandeja: las únicas rutas de la consola con cuerpos de mensaje (C8).
router.include_router(inbox_stream.router)
router.include_router(inbox_media.router)
router.include_router(inbox.router)
router.include_router(notifications.router)

__all__ = ["router"]
