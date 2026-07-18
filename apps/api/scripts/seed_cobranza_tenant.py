"""Provision a COBRANZA tenant (Amigable Cobro business) from cobranza_v1.

REPLICABLE BY DESIGN — everything that differs between businesses is an env
var, so onboarding a new Amigable Cobro client needs **no code change**:

    NEXUS_COBRANZA_SLUG            # url-safe id, e.g. "barberia-lopez"
    NEXUS_COBRANZA_NAME            # display name, e.g. "Barbería López"
    NEXUS_COBRANZA_TIMEZONE        # e.g. "America/Caracas"
    NEXUS_COBRANZA_MARKET          # e.g. "VE"
    NEXUS_COBRANZA_ADMIN_PHONES    # comma-separated E.164 admin whitelist
    NEXUS_COBRANZA_PAYMENT_JSON    # {"policies.payment.pago_movil.banco": "...", ...}

(The legacy ``NEXUS_MOUNA_*`` names still work for the first tenant.)

Full onboarding checklist for a NEW business:
 1. Run this script with the env vars above → tenant + agent_config ACTIVE.
 2. Connect its **amigable_cobro** connector (its own ``business_uuid`` +
    token) so ``billing.*`` reads/writes that business's accounts.
 3. Connect its WhatsApp line (Meta embedded signup or owned-number connect).
 4. Approve the two reminder templates in THAT line's WABA
    (``recordatorio_pago_proximo`` / ``recordatorio_pago_vencido``,
    category UTILITY, named vars: cliente, negocio, monto, fecha).
 5. Done — the cobranza due-date sweep picks the tenant up automatically and
    starts sending reminders; ``{{negocio}}`` is filled with the tenant name.

Idempotent: re-running picks up the existing tenant by ``slug`` and only
creates the agent_config if there isn't an ACTIVE one yet.

Phase A scope (this script):
  - Tenant ``mouna`` (plan PRO, market VE, America/Caracas).
  - agent_config v1 ACTIVE rendered from cobranza_v1, with the EXISTING
    notification.*/escalate.* tools. The billing.* tools (Mouna API) land
    in Phase B and get added to a new config version then.

The bank details below are PLACEHOLDERS until Mouna provides the real
account. They live in ``policies.payment.*`` so the rendered system_prompt
and the runtime both read them from one place.

Usage:

    NEXUS_DATABASE_URL=postgresql+asyncpg://... \\
      uv run python apps/api/scripts/seed_cobranza_tenant.py
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import uuid
from pathlib import Path

# Make ``nexus_api`` importable when run via plain ``python``.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from nexus_api.db.base import get_engine
from nexus_api.db.models.agent import AgentConfig, AgentConfigStatus
from nexus_api.db.models.tenant import Tenant, TenantPlan, TenantStatus
from nexus_api.services.templating.seed_templates import (
    load_seed_template,
    render_seed_template,
)

# Slug stays "mouna" (internal id, referenced by scripts/queries). The
# display name is "Amigable Cobro" — the agent/tenant IS Amigable Cobro;
# "Mouna" turned out to be one of Amigable Cobro's own clients, not the tenant.
MOUNA_SLUG = os.environ.get("NEXUS_COBRANZA_SLUG") or os.environ.get("NEXUS_MOUNA_SLUG", "mouna")
MOUNA_NAME = os.environ.get("NEXUS_COBRANZA_NAME") or os.environ.get("NEXUS_MOUNA_NAME", "Amigable Cobro")
MOUNA_TIMEZONE = os.environ.get("NEXUS_COBRANZA_TIMEZONE") or os.environ.get("NEXUS_MOUNA_TIMEZONE", "America/Caracas")
MOUNA_MARKET = os.environ.get("NEXUS_COBRANZA_MARKET") or os.environ.get("NEXUS_MOUNA_MARKET", "VE")

# Datos bancarios de Mouna — PLACEHOLDER hasta tener los reales.
# Overridean policies.payment.* del seed cobranza_v1.
# Datos de pago reales de Mouna — overridean policies.payment.<metodo>.<campo>
# del seed cobranza_v1. Rellenar cuando Mouna los provea; lo vacío usa el
# default placeholder del YAML. Claves esperadas (ver cobranza_v1.yaml):
#   pago_movil.{banco,telefono,cedula}
#   transferencia.{banco,numero_cuenta,tipo,titular,cedula_rif}
#   binance.{pay_id}
#   zelle.{email,titular,banco}
# NOTA: datos de EJEMPLO (Venezuela). Reemplazar por los reales de Mouna.
_DEFAULT_PAYMENT_DATA: dict[str, str] = {
    # Pago móvil
    "policies.payment.pago_movil.banco": "0134 - Banesco",
    "policies.payment.pago_movil.telefono": "0414-1234567",
    "policies.payment.pago_movil.cedula": "V-12.345.678",
    # Transferencia bancaria
    "policies.payment.transferencia.banco": "Banesco",
    "policies.payment.transferencia.numero_cuenta": "0134 0123 45 6789012345",
    "policies.payment.transferencia.tipo": "corriente",
    "policies.payment.transferencia.titular": "Mouna, C.A.",
    "policies.payment.transferencia.cedula_rif": "J-40123456-7",
    # Binance
    "policies.payment.binance.pay_id": "pagos.mouna@gmail.com",
}


def _env_json(name: str, default: dict[str, str]) -> dict[str, str]:
    """Per-business payment data as a JSON env var (keys = policy paths)."""
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    return {str(k): str(v) for k, v in json.loads(raw).items()}


def _env_list(name: str, default: list[str]) -> list[str]:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    return [p.strip() for p in raw.split(",") if p.strip()]


PAYMENT_DATA: dict[str, str] = _env_json("NEXUS_COBRANZA_PAYMENT_JSON", _DEFAULT_PAYMENT_DATA)

# Teléfonos ADMIN de Mouna (E.164) — los ÚNICOS números a los que el
# agente responde (gate en el dispatcher: policies.admin_access). Todo
# otro remitente queda registrado pero sin respuesta.
#
# NOTA: +34672138367 es la LÍNEA del agente (la WABA en Meta, modo
# coexistence), por eso NO está aquí — un número no puede escribirse a sí
# mismo por WhatsApp. Los admins le escriben a esa línea desde estos
# teléfonos. (+34632719028 fue el candidato inicial de línea pero quedó
# atascado en un WABA viejo; ahora se usa como teléfono admin de pruebas.)
ADMIN_PHONES: list[str] = _env_list(
    "NEXUS_COBRANZA_ADMIN_PHONES",
    [
        "+34610777570",
        "+584249125716",
        "+584244095405",
        "+34632719028",
    ],
)


async def _amain() -> int:
    engine = get_engine()
    Session = async_sessionmaker(engine, expire_on_commit=False)

    template = load_seed_template("cobranza_v1")
    rendered = render_seed_template(
        template,
        placeholders={
            "tenant.name": MOUNA_NAME,
            "tenant.timezone": MOUNA_TIMEZONE,
            **PAYMENT_DATA,
            # Whitelist admin — se mergea en policies.admin_access.admin_phones.
            "policies.admin_access.admin_phones": ADMIN_PHONES,
        },
    )

    async with Session() as session:
        existing = (
            await session.execute(select(Tenant).where(Tenant.slug == MOUNA_SLUG))
        ).scalar_one_or_none()

        if existing:
            tenant_id = existing.id
            print(f"mouna: tenant exists slug={MOUNA_SLUG} id={tenant_id}")
        else:
            tenant = Tenant(
                id=uuid.uuid4(),
                name=MOUNA_NAME,
                slug=MOUNA_SLUG,
                plan=TenantPlan.PRO,
                status=TenantStatus.ACTIVE,
                market=MOUNA_MARKET,
                timezone=MOUNA_TIMEZONE,
            )
            session.add(tenant)
            await session.flush()
            tenant_id = tenant.id
            print(f"mouna: created tenant slug={MOUNA_SLUG} id={tenant_id}")

        config = (
            await session.execute(
                select(AgentConfig)
                .where(AgentConfig.tenant_id == tenant_id)
                .where(AgentConfig.status == AgentConfigStatus.ACTIVE)
            )
        ).scalar_one_or_none()

        if config:
            # Local dev: re-render the active config in place so iterating on
            # the cobranza_v1 template is one command. PROD stages a new
            # version instead (AgentConfigService.stage_new_version + promote).
            config.system_prompt_rendered = rendered.system_prompt
            config.tools = rendered.tools
            config.policies = rendered.policies
            config.seed_template_ref = rendered.seed_template_ref
            print(f"mouna: re-rendered agent_config v{config.version} from seed (local dev)")
        else:
            config = AgentConfig(
                tenant_id=tenant_id,
                version=1,
                status=AgentConfigStatus.ACTIVE,
                system_prompt_rendered=rendered.system_prompt,
                channels=[],  # WhatsApp se cablea cuando el WABA esté conectado
                tools=rendered.tools,
                policies=rendered.policies,
                seed_template_ref=rendered.seed_template_ref,
                created_by="seed_cobranza_tenant.py",
            )
            session.add(config)
            print(
                f"mouna: created agent_config v1 (active, seed={rendered.seed_template_ref}, "
                f"{len(rendered.tools)} tools)"
            )

        await session.commit()

    print(f"mouna: ok slug={MOUNA_SLUG} id={tenant_id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_amain()))
