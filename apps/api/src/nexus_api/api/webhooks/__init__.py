from fastapi import APIRouter

from nexus_api.api.webhooks import ycloud

router = APIRouter(prefix="/webhook", tags=["webhooks"])
router.include_router(ycloud.router)
