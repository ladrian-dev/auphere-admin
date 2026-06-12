from fastapi import APIRouter

from nexus_api.api.admin import (
    agent_configs,
    audit,
    auphere_channels,
    backchannel_owners,
    connectors,
    conversations,
    evals,
    integrations,
    isolation,
    meta_signup,
    prompt_library,
    screenshots,
    skills,
    tenants,
    tool_catalog,
    whatsapp_templates,
)

router = APIRouter(prefix="/admin", tags=["admin"])
router.include_router(tenants.router)
router.include_router(agent_configs.router)
router.include_router(conversations.router)
router.include_router(tool_catalog.router)
router.include_router(integrations.router)
router.include_router(connectors.router)
router.include_router(screenshots.router)
router.include_router(isolation.router)
router.include_router(evals.router)
router.include_router(prompt_library.router)
router.include_router(meta_signup.router)
router.include_router(skills.router)
router.include_router(audit.router)
router.include_router(auphere_channels.router)
router.include_router(backchannel_owners.router)
router.include_router(whatsapp_templates.router)
