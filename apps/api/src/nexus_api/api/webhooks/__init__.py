from fastapi import APIRouter

from nexus_api.api.webhooks import owner_channel, ycloud

router = APIRouter(prefix="/webhook", tags=["webhooks"])
router.include_router(ycloud.router)
router.include_router(owner_channel.router)
