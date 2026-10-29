from fastapi import APIRouter

from nexus_api.api.admin import (
    agent_configs,
    agents,
    audit,
    auphere_channels,
    auth,
    backchannel_owners,
    billing,
    budget_policies,
    certifications,
    channel_signup_links,
    channels_overview,
    client_access,
    client_controls,
    connectors,
    conversations,
    cost,
    evals,
    impersonate,
    integrations,
    isolation,
    meta_signup,
    meta_social,
    model_bindings,
    models_catalog,
    overview,
    partner_access,
    partner_billing,
    partner_knowledge,
    partner_llm,
    partner_models,
    partner_money,
    partner_wallet,
    partners,
    prompt_library,
    receipts,
    router_policies,
    screenshots,
    sector_tests,
    signups,
    skills,
    tenant_capabilities,
    tenant_payments,
    tenants,
    tenants_health,
    tickets,
    tiktok_authorize,
    tool_catalog,
    unlimited_consumption,
    usage_overview,
    whatsapp_login_beta,
    whatsapp_pin,
    whatsapp_templates,
)

router = APIRouter(prefix="/admin", tags=["admin"])
# Primero la identidad: es lo único que un panel sin sesión puede llamar.
router.include_router(auth.router)
router.include_router(tenants.router)
# Spec 030: el acceso del cliente a su consola lite.
router.include_router(client_access.router)
# La mensualidad de un cliente cobrada fuera del proveedor de pagos.
router.include_router(tenant_payments.router)
router.include_router(unlimited_consumption.router)
router.include_router(agent_configs.router)
# Spec 030: los agentes de un cliente.
router.include_router(agents.router)
# Spec 049: erase one person's Instagram / Messenger data.
router.include_router(meta_social.router)
router.include_router(conversations.router)
router.include_router(tool_catalog.router)
router.include_router(integrations.router)
router.include_router(connectors.router)
router.include_router(screenshots.router)
router.include_router(isolation.router)
router.include_router(evals.router)
router.include_router(prompt_library.router)
router.include_router(meta_signup.router)
# Spec 050: rotate a number's two-step PIN.
router.include_router(whatsapp_pin.router)
router.include_router(tiktok_authorize.router)
router.include_router(skills.router)
router.include_router(audit.router)
router.include_router(auphere_channels.router)
router.include_router(backchannel_owners.router)
router.include_router(whatsapp_templates.router)
router.include_router(partners.router)
router.include_router(channels_overview.router)
router.include_router(tenants_health.router)
router.include_router(tenant_capabilities.router)
router.include_router(usage_overview.router)
router.include_router(channel_signup_links.router)
router.include_router(partner_billing.router)
router.include_router(partner_access.router)
router.include_router(overview.router)
router.include_router(overview.instance_router)
router.include_router(signups.router)
router.include_router(tickets.router)
router.include_router(impersonate.router)
router.include_router(partner_wallet.router)
router.include_router(partner_models.router)
router.include_router(partner_knowledge.router)
router.include_router(partner_llm.router)
router.include_router(receipts.router)
router.include_router(billing.router)
router.include_router(model_bindings.router)
router.include_router(budget_policies.router)
router.include_router(cost.router)
# Spec 047 (T150): el catálogo de despliegues, la política del router y las
# certificaciones, sin tocar la base a mano (historia 30).
router.include_router(models_catalog.router)
router.include_router(router_policies.router)
router.include_router(certifications.router)
router.include_router(sector_tests.router)
router.include_router(sector_tests.calibration_router)
router.include_router(sector_tests.eval_router)
# Spec 047 (T117): la beta «WhatsApp login» por país; nunca la UE ni el EEE.
router.include_router(whatsapp_login_beta.router)
# Spec 047 (T158): el tope de construcción y la moneda de la cuenta.
router.include_router(partner_money.router)
# Spec 047 (T180): el ensayo y la activación de la consola nueva.
# Spec 047 (T172): la restricción soberana y las conciliaciones.
router.include_router(client_controls.router)
