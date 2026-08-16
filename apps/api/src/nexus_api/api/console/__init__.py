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
    agent_settings,
    agents,
    audit,
    auth,
    billing,
    channels,
    conversations,
    diagnostics,
    home,
    invitations,
    keys,
    knowledge,
    me,
    notifications,
    onboarding,
    playground,
    seed_templates,
    skills,
    team,
    templates,
    tenants,
    tools,
    usage,
    whatsapp,
)

router = APIRouter(prefix="/console", tags=["console"])
# Identidad de la consola (login/sesión/logout). Token de SERVICIO, no
# principal: son las llamadas pre-sesión del BFF.
router.include_router(auth.router)
router.include_router(me.router)
router.include_router(tenants.router)
router.include_router(agents.router)
router.include_router(channels.router)
router.include_router(conversations.router)
router.include_router(usage.router)
router.include_router(audit.router)
router.include_router(team.router)
router.include_router(invitations.router)
router.include_router(keys.router)
router.include_router(billing.router)
router.include_router(playground.router)
router.include_router(whatsapp.router)
router.include_router(templates.router)
router.include_router(diagnostics.router)
# lane agent-tools (CP-11/13/14/15/31)
router.include_router(agent_settings.router)
router.include_router(tools.router)
router.include_router(skills.router)
router.include_router(knowledge.router)
router.include_router(seed_templates.router)
router.include_router(notifications.router)
router.include_router(onboarding.router)
router.include_router(home.router)
