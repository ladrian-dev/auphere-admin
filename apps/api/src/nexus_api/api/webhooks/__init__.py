from fastapi import APIRouter

from nexus_api.api.webhooks import meta, tiktok

router = APIRouter(prefix="/webhook", tags=["webhooks"])
router.include_router(meta.router)
router.include_router(tiktok.router)
