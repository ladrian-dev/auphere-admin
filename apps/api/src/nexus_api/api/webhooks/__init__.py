from fastapi import APIRouter

from nexus_api.api.webhooks import meta, owner_channel, ycloud

router = APIRouter(prefix="/webhook", tags=["webhooks"])
router.include_router(ycloud.router)
router.include_router(owner_channel.router)
router.include_router(meta.router)
