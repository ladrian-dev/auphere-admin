"""Partner console surface — ``/console/*`` (PLAN-CONSOLE-V1, CP-04).

Consumed ONLY by the console BFF (``apps/console``), authenticated with a
60-second EdDSA JWT (``core/console_auth.py``). Unversioned on purpose:
the BFF and the API deploy together, and mounting under ``/v1`` would put
the console inside the frozen public partner contract
(``tests/unit/test_v1_contract.py``) and its deprecation headers.

Every router here follows the same three rules, pinned by
``tests/isolation/test_console_*``:

1. no endpoint accepts ``tenant_id`` or ``partner_id`` from the caller —
   the partner is the principal, the tenant is ``{ref}`` → ``partner_tenants``;
2. responses never carry internal tenant ids;
3. responses never carry message bodies (C8).
"""

from __future__ import annotations

from fastapi import APIRouter

from nexus_api.api.console import (
    agent_builder,
    agent_copilot,
    agent_draft_routes,
    agent_improvement,
    agent_integrations,
    agent_knowledge,
    agent_lifecycle_routes,
    agent_playground,
    agent_publish,
    agent_quality,
    agent_review,
    agent_settings,
    agent_tests,
    agents,
    agents_list,
    audit,
    auth,
    auth_google,
    billing,
    business,
    business_records,
    capabilities,
    capabilities_client,
    channel_config,
    channel_signup,
    channels,
    client_bags,
    client_builder,
    companion,
    conversations,
    diagnostics,
    home,
    invitations,
    jobs,
    keys,
    knowledge,
    lite,
    me,
    meta_social,
    models,
    notifications,
    onboarding,
    password_reset,
    playbook,
    playground,
    search,
    sectors,
    seed_templates,
    session_catalog,
    session_codes,
    signup,
    skills,
    suggested_agents,
    support,
    team,
    teammates,
    templates,
    tenants,
    tools,
    usage,
    usage_lines,
    wallet,
    whatsapp,
    workflow,
    workstation,
    workstation_partner,
)

router = APIRouter(prefix="/console", tags=["console"])
# Identidad de la consola (login/sesión/logout). Token de SERVICIO, no
# principal: son las llamadas pre-sesión del BFF.
router.include_router(auth.router)
router.include_router(me.router)
# Spec 030: la consola del cliente final. Su propia dependencia de
# autorización; ninguna persona del partner alcanza estas rutas.
router.include_router(lite.router)
router.include_router(tenants.router)
router.include_router(agents.router)
# Spec 030: los agentes de un cliente y qué agente contesta en cada número.
# Spec 047 (T080): before ``agents_list`` so ``agents/draft-options`` is not an agent id.
router.include_router(agent_builder.router)
router.include_router(agent_lifecycle_routes.router)
router.include_router(agent_playground.router)
router.include_router(agent_tests.router)
router.include_router(agent_review.router)
router.include_router(agent_publish.router)
router.include_router(client_builder.router)
router.include_router(agent_copilot.router)
router.include_router(agents_list.router)
# Spec 049: before ``channels`` so ``/{kind}/connect`` is never read as a channel id.
router.include_router(meta_social.router)
router.include_router(channels.router)
# Spec 047 (T112, T114): la página de cada canal y su menú, después de las
# rutas fijas de ``channels/…`` (``overview``, ``diagnostics``): ``{channel_id}``
# las capturaría con un 422.
router.include_router(diagnostics.router)
router.include_router(channel_config.router)
router.include_router(conversations.router)
router.include_router(usage.router)
# Spec 047 (T158): Consumo por partidas, junto a lo de hoy.
router.include_router(usage_lines.router)
router.include_router(wallet.router)
router.include_router(models.router)
router.include_router(audit.router)
router.include_router(team.router)
router.include_router(invitations.router)
router.include_router(signup.router)
router.include_router(auth_google.router)
router.include_router(session_codes.router)
# Spec 011 — recuperar la contraseña. Pre-sesión, token de SERVICIO, y la
# respuesta de pedir es la misma exista o no la cuenta.
router.include_router(password_reset.router)
router.include_router(channel_signup.router)
router.include_router(keys.router)
router.include_router(billing.router)
router.include_router(playground.router)
# CO-01: el Companion. Log de runs durable en Redis; el run no muere con la
# conexión del navegador.
router.include_router(companion.router)
# Spec 003 — el roster y los hilos de teammates (la consola solo los proxea).
router.include_router(teammates.router)
# CO-08: qué existe y qué no (documento versionado, §5 de CONTRACT-V2) y
# el escalado con expediente (§4). El ticket lo aplica ``console.apply``
# tras una confirmación humana, como cualquier otra escritura.
router.include_router(capabilities.router)
router.include_router(support.router)
router.include_router(whatsapp.router)
router.include_router(templates.router)
# lane agent-tools (CP-11/13/14/15/31)
router.include_router(agent_settings.router)
router.include_router(tools.router)
router.include_router(skills.router)
# Spec 017 (R5): herramientas y habilidades, en una sola lectura.
router.include_router(capabilities_client.router)
router.include_router(knowledge.router)
# Spec 047 (T133): la capa de conocimiento de cada agente y «Enseñar».
router.include_router(agent_knowledge.router)
# Spec 047 (T128): autorizar una vez por cliente, activar por agente.
router.include_router(agent_integrations.router)
# Spec 047 (T147): la pantalla Calidad (perfiles, modelo fijado y su comprobación).
router.include_router(agent_quality.router)
# Spec 047 (T174): rendimiento, conversaciones solo con metadatos y las sugerencias.
router.include_router(agent_improvement.router)
# Spec 047 (T158): las bolsas de los clientes, el tope del agente y la partida
# «Construcción y pruebas».
router.include_router(client_bags.router)
router.include_router(playbook.router)
router.include_router(seed_templates.router)
router.include_router(notifications.router)
router.include_router(onboarding.router)
router.include_router(home.router)
router.include_router(workflow.router)
router.include_router(workstation.router)
router.include_router(workstation_partner.router)
router.include_router(session_catalog.router)
# Spec 047 (ola 0): el estado de los trabajos largos. La ruta solo recibe el id;
# ``job_tenant`` da el cliente y la pertenencia al partner se comprueba antes de
# abrir la transacción con él.
router.include_router(jobs.router)
# Spec 047 (R47.2): ⌘K. Pantallas y acciones como claves; los agentes de cada
# cliente se leen con su cliente puesto (RLS), nunca sin ``app.tenant_id``.
router.include_router(search.router)
# Spec 047 (requisito 3): el único borrador de cada agente, con If-Match, y su historial.
router.include_router(agent_draft_routes.router)
# Spec 047 (T057, T058): las secciones de Negocio que escribe la persona.
router.include_router(business.router)
# Spec 047 (de la T069 a la T072): la ficha entera, su procedencia, su historial, sus
# propuestas, sus fuentes y el ClientSpec.
router.include_router(business_records.router)
# Spec 047, enmienda del 2026-10-29: los sectores con guía (57.5) y los agentes que
# sugiere el constructor del cliente (60.6).
router.include_router(sectors.router)
router.include_router(suggested_agents.router)
