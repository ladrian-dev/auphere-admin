from fastapi import APIRouter

from nexus_api.api.webhooks import billing, meta, tiktok

router = APIRouter(prefix="/webhook", tags=["webhooks"])
router.include_router(billing.router)
router.include_router(meta.router)
router.include_router(tiktok.router)
