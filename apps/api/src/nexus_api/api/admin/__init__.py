from fastapi import APIRouter

from nexus_api.api.admin import (
    agent_configs,
    audit,
    auphere_channels,
    auth,
    backchannel_owners,
    billing,
    budget_policies,
    connectors,
    conversations,
    cost,
    evals,
    integrations,
    isolation,
    meta_signup,
    model_bindings,
    partner_knowledge,
    partner_llm,
    partner_models,
    partner_wallet,
    partners,
    prompt_library,
    receipts,
    screenshots,
    skills,
    tenants,
    tiktok_authorize,
    tool_catalog,
    whatsapp_templates,
)

router = APIRouter(prefix="/admin", tags=["admin"])
# Primero la identidad: es lo único que un panel sin sesión puede llamar.
router.include_router(auth.router)
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
router.include_router(tiktok_authorize.router)
router.include_router(skills.router)
router.include_router(audit.router)
router.include_router(auphere_channels.router)
router.include_router(backchannel_owners.router)
router.include_router(whatsapp_templates.router)
router.include_router(partners.router)
router.include_router(partner_wallet.router)
router.include_router(partner_models.router)
router.include_router(partner_knowledge.router)
router.include_router(partner_llm.router)
router.include_router(receipts.router)
router.include_router(billing.router)
router.include_router(model_bindings.router)
router.include_router(budget_policies.router)
router.include_router(cost.router)
