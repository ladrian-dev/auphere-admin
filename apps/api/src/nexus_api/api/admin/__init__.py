from fastapi import APIRouter

from nexus_api.api.admin import (
    agent_configs,
    conversations,
    integrations,
    isolation,
    screenshots,
    tenants,
    tool_catalog,
)

router = APIRouter(prefix="/admin", tags=["admin"])
router.include_router(tenants.router)
router.include_router(agent_configs.router)
router.include_router(conversations.router)
router.include_router(tool_catalog.router)
router.include_router(integrations.router)
router.include_router(screenshots.router)
router.include_router(isolation.router)
