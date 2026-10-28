"""``/console/lite/*`` — la consola del cliente final (spec 030).

Todas las rutas de aquí se autorizan con
:func:`nexus_api.core.client_auth.require_client_principal`: solo las alcanza
la persona de un cliente, y ninguna lleva ``ref``, ``tenant_id`` ni
``partner_id``. La Bandeja (``/console/lite/inbox/*``) es la única parte de la
consola que puede devolver cuerpos de mensaje (C8, plan D5).
"""

from __future__ import annotations

from fastapi import APIRouter

from . import (
    agents,
    business,
    corrections,
    home,
    inbox,
    inbox_media,
    inbox_stream,
    me,
    notifications,
    phones,
    reservas,
    usage,
)

router = APIRouter(prefix="/lite", tags=["console-lite"])
router.include_router(me.router)
router.include_router(home.router)
router.include_router(usage.router)
# La Bandeja: las únicas rutas de la consola con cuerpos de mensaje (C8).
router.include_router(inbox_stream.router)
router.include_router(inbox_media.router)
router.include_router(inbox.router)
router.include_router(notifications.router)
# Spec 031: los teléfonos de la persona y lo que solo hace la app.
router.include_router(phones.router)
# Spec 043: la agenda del negocio (módulo ``reservas``).
router.include_router(reservas.router)
# Spec 047: sus agentes y su ficha (módulos ``agents`` y ``business``), y
# «Corregir esta respuesta» desde la Bandeja (módulo ``inbox``).
router.include_router(agents.router)
router.include_router(business.router)
router.include_router(corrections.router)

__all__ = ["router"]
