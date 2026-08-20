"""Seed the Clínica Boreal pilot tenant (vertical aesthetic_clinic_v1).

Cliente piloto interno descrito en
``Auphere/nexus/decisions/ADR-025-aesthetic-clinic-vertical.md`` y
``Auphere/nexus/clients/clinica-boreal.md``.

Idempotente: si el tenant ``clinica-boreal`` ya existe por slug, el
script lo recupera y rellena solamente las piezas que falten. Ejecutable
contra dev local o contra prod via ``NEXUS_DATABASE_URL``. NUNCA crea
canales — la instalación de WhatsApp Meta + AgendaPro pasa por la UI
admin (requiere OAuth consent del operador).

Uso típico (dev):

    NEXUS_DATABASE_URL=postgresql+asyncpg://nexus:nexus@localhost:5432/nexus \\
      uv run python apps/api/scripts/seed_clinica_boreal.py

Lo que crea:

1. ``tenants`` row con plan=internal, eval_required=true, idioma+TZ
   de Venezuela.
2. ``agent_configs`` v1 STAGED (no ACTIVE — promotion gate exige
   pasar el eval dataset antes de ir a producción):
     - system_prompt renderizado desde el seed ``aesthetic_clinic_v1``
       con los placeholders de Boreal.
     - tools whitelist (15 entradas — las recomendadas por el seed).
     - policies del seed con los defaults venezolanos.
     - seed_template_ref = "aesthetic_clinic_v1".
     - runtime_memory_tool = TRUE.
     - runtime_outcome_grader = TRUE.
     - runtime_skills = los skill_ids de uploaded.json (las que están
       subidas; las pendientes se omiten con warning).
3. ``eval_datasets`` row + ``eval_cases`` (30 cases) cargados desde
   ``services/evals/seed_datasets/aesthetic_clinic_v1.json``.

Tras correr este script, el operador todavía tiene que:
- Instalar el conector WhatsApp Meta (Embedded Signup) en la UI.
- Instalar el conector AgendaPro en la UI.
- Correr el eval dataset → si pasa ≥0.92 → promote v1 a ACTIVE.
"""

from __future__ import annotations

import asyncio
import json
import sys
import uuid
from decimal import Decimal
from pathlib import Path

# Make ``nexus_api`` importable when the script is executed via plain
# ``python`` rather than ``uv run`` from inside the apps/api package.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import sqlalchemy as sa
from sqlalchemy.ext.asyncio import async_sessionmaker

from nexus_api.core.tenant_context import tenant_scoped_session
from nexus_api.db.base import get_engine
from nexus_api.db.models.agent import AgentConfig, AgentConfigStatus
from nexus_api.db.models.tenant import Tenant, TenantPlan, TenantStatus
from nexus_api.services.evals.seed_loader import (
    load_seed_dataset,
    resolve_seed_payload,
)
from nexus_api.services.templating import (
    load_seed_template,
    render_seed_template,
)

BOREAL_SLUG = "clinica-boreal"
BOREAL_NAME = "Clínica Boreal"
BOREAL_TIMEZONE = "America/Caracas"
BOREAL_MARKET = "VE"
BOREAL_BUSINESS_HOURS = {
    "monday":    {"open": "09:00", "close": "18:00"},
    "tuesday":   {"open": "09:00", "close": "18:00"},
    "wednesday": {"open": "09:00", "close": "18:00"},
    "thursday":  {"open": "09:00", "close": "18:00"},
    "friday":    {"open": "09:00", "close": "18:00"},
    "saturday":  {"open": "09:00", "close": "14:00"},
    "sunday":    None,
}

# Placeholders ficticios pero verosímiles — coherentes con la ficha
# en ``clients/clinica-boreal.md``. Si algún día Boreal se reemplaza
# por un tenant real, este bloque pasa a ser data de onboarding.
BOREAL_PLACEHOLDERS: dict[str, object] = {
    "tenant.name": BOREAL_NAME,
    "tenant.address": (
        "Av. Principal de Las Mercedes, Edificio Atlantic, Piso 4. "
        "Caracas 1080, Distrito Capital"
    ),
    "tenant.timezone": BOREAL_TIMEZONE,
    "tenant.business_hours_label": "Lun-Vie 9-18, Sáb 9-14 (solo consultas)",
    "tenant.saturday_label": (
        "sábados 09:00-14:00, solo consultas pre-op — NO se aplican "
        "inyectables, láser ni aparatología"
    ),
    "tenant.instagram_handle": "@clinicaboreal",
    "tenant.surgery_referral_hospital": "Centro Médico Docente La Trinidad (CMDLT)",
    "tenant.surgery_referral_phone": "+58 212-949-6411",
    "tenant.front_desk_phone_label": "+58 212-555-0100 (recepción de Clínica Boreal)",
    "tenant.consultation_price_label": (
        "USD 80, acreditable al procedimiento si la paciente lo concreta"
    ),
    "tenant.pricing_table_label": (
        "rinoplastia USD 4.800-6.500 · mamoplastia aumentativa USD "
        "5.500-7.200 · BBL USD 5.000-6.800 · abdominoplastia USD "
        "5.800-7.500 · liposucción USD 3.500-5.500 · blefaroplastia "
        "USD 2.200-3.200 · Botox desde USD 280 · ácido hialurónico "
        "labios desde USD 380 · láser CO2 fraccionado desde USD 450"
    ),
    "tenant.payment_methods_label": (
        "Zelle (USD), transferencia internacional (USD) o Pago Móvil en "
        "bolívares al equivalente del cambio oficial del día"
    ),
    "clinical.titular_name": "Dra. Valentina Hurtado",
    "clinical.titular_credential": (
        "Cirujana plástica, miembro titular de SVCPREM (Sociedad Venezolana "
        "de Cirugía Plástica Reconstructiva, Estética y Maxilofacial)"
    ),
}

# Skills locales que el agente de Boreal usa. El runtime las consume
# por ``skill_id`` (no por nombre local) — el seed script lee
# ``apps/worker/skills/uploaded.json`` para resolver el id de cada una.
#
# Anthropic limita ``container.skills`` a 8 por request. Curamos a 6
# manteniendo solo las skills que aportan CONOCIMIENTO denso o mecánica
# de canal que no cabe bien en el system_prompt. Las 4 que eran reglas
# cortas de conversación se quitaron porque YA viven como reglas duras
# en el system_prompt renderizado (aesthetic_clinic_v1.yaml):
#   - medical-claims-discipline  → reglas 1-4 (sin dosis/promesa/marca/off-label)
#   - anti-hallucination-booking → regla 10 (no confirmar sin tool result)
#   - escalation-policy          → reglas 13/14/18 + sección ESCALACIÓN
#   - before-after-photos        → regla 8 (política de fotos)
# Tenerlas como skill además del prompt gastaba slots del límite de 8
# sin aportar contenido nuevo. Decisión 2026-05-28.
BOREAL_SKILL_NAMES: list[str] = [
    # Conocimiento denso — no cabría en el prompt, progressive disclosure.
    "aesthetic-procedures-kb",
    "post-op-symptom-triage",
    "pre-op-screening",
    # Compliance técnico — qué redactar antes de escribir a memory tool.
    "phi-redaction",
    # Mecánica del canal WhatsApp — no es regla de dominio.
    "whatsapp-native-components",
    "whatsapp-24h-window",
]

# Eval dataset seedeado al tenant (idempotente: re-load reemplaza
# los cases). El threshold del payload (0.920) viaja con el JSON.
BOREAL_EVAL_DATASET = "aesthetic_clinic_v1"

_SKILLS_MANIFEST = (
    Path(__file__).resolve().parents[2] / "worker" / "skills" / "uploaded.json"
)


def _resolve_runtime_skills() -> list[dict[str, str]]:
    """Read ``apps/worker/skills/uploaded.json`` and return the list
    of ``{skill_id, version}`` dicts that this tenant should attach.

    Skills referenced in :data:`BOREAL_SKILL_NAMES` that are NOT yet
    uploaded are skipped with a printed warning — the operator can
    re-run this script after uploading the missing skills and the
    new entries will appear in the next promote.
    """
    if not _SKILLS_MANIFEST.is_file():
        print(
            f"boreal: WARN no skills manifest at {_SKILLS_MANIFEST} — "
            "agent_config will be created without runtime_skills"
        )
        return []
    manifest = json.loads(_SKILLS_MANIFEST.read_text(encoding="utf-8"))
    uploaded = manifest.get("skills") or {}
    out: list[dict[str, str]] = []
    missing: list[str] = []
    for name in BOREAL_SKILL_NAMES:
        entry = uploaded.get(name)
        if not entry:
            missing.append(name)
            continue
        out.append({"skill_id": entry["skill_id"], "version": entry["version"]})
    if missing:
        print(
            "boreal: WARN skills not yet uploaded (omitted from runtime_skills): "
            + ", ".join(missing)
        )
        print(
            "boreal:      run apps/worker/scripts/upload_skill.py --skill <name> --create"
        )
        print(
            "boreal:      then re-run this script — it will pick up the new ids."
        )
    return out


async def _seed_tenant(session) -> uuid.UUID:
    existing = (
        await session.execute(sa.select(Tenant).where(Tenant.slug == BOREAL_SLUG))
    ).scalar_one_or_none()
    if existing:
        # Refresh editable fields in case the script changed them — but
        # keep ``id`` stable so children rows don't dangle.
        existing.name = BOREAL_NAME
        existing.plan = TenantPlan.INTERNAL
        existing.status = TenantStatus.ACTIVE
        existing.market = BOREAL_MARKET
        existing.timezone = BOREAL_TIMEZONE
        existing.business_hours = BOREAL_BUSINESS_HOURS
        existing.eval_required = True
        existing.cost_alert_threshold_usd_per_day = Decimal("5.00")
        print(f"boreal: tenant exists slug={BOREAL_SLUG} id={existing.id} — refreshed")
        return existing.id

    tenant = Tenant(
        id=uuid.uuid4(),
        name=BOREAL_NAME,
        slug=BOREAL_SLUG,
        plan=TenantPlan.INTERNAL,
        status=TenantStatus.ACTIVE,
        market=BOREAL_MARKET,
        timezone=BOREAL_TIMEZONE,
        business_hours=BOREAL_BUSINESS_HOURS,
        eval_required=True,
        cost_alert_threshold_usd_per_day=Decimal("5.00"),
    )
    session.add(tenant)
    await session.flush()
    print(f"boreal: created tenant slug={BOREAL_SLUG} id={tenant.id}")
    return tenant.id


async def _seed_agent_config(session, tenant_id: uuid.UUID) -> None:
    # Render the seed with Boreal data — fail fast if a placeholder is
    # missing, the operator must fix the data before persisting.
    template = load_seed_template("aesthetic_clinic_v1")
    rendered = render_seed_template(template, placeholders=BOREAL_PLACEHOLDERS)

    runtime_skills = _resolve_runtime_skills()

    existing = (
        await session.execute(
            sa.select(AgentConfig)
            .where(AgentConfig.tenant_id == tenant_id)
            .order_by(AgentConfig.version.desc())
            .limit(1)
        )
    ).scalar_one_or_none()

    if existing and existing.status != AgentConfigStatus.ARCHIVED:
        # Update the latest non-archived row instead of creating v2 —
        # that keeps the script genuinely idempotent (re-runs don't
        # accumulate STAGED versions).
        existing.system_prompt_rendered = rendered.system_prompt
        existing.tools = list(rendered.tools)
        existing.policies = dict(rendered.policies)
        existing.seed_template_ref = rendered.seed_template_ref
        existing.runtime_memory_tool = True
        existing.runtime_outcome_grader = True
        existing.runtime_skills = runtime_skills or None
        print(
            f"boreal: agent_config v{existing.version} {existing.status.value} "
            f"refreshed (runtime_skills={len(runtime_skills)})"
        )
        return

    config = AgentConfig(
        tenant_id=tenant_id,
        version=1,
        status=AgentConfigStatus.STAGED,
        system_prompt_rendered=rendered.system_prompt,
        channels=[],
        tools=list(rendered.tools),
        policies=dict(rendered.policies),
        seed_template_ref=rendered.seed_template_ref,
        created_by="seed_clinica_boreal.py",
        runtime_memory_tool=True,
        runtime_outcome_grader=True,
        runtime_skills=runtime_skills or None,
    )
    session.add(config)
    print(
        f"boreal: created agent_config v1 STAGED "
        f"(tools={len(config.tools)} skills={len(runtime_skills)})"
    )


async def _seed_eval_dataset(session, tenant_id: uuid.UUID) -> None:
    payload = resolve_seed_payload(BOREAL_EVAL_DATASET)
    # ``load_seed_dataset`` upserts by (tenant_id, name) and replaces
    # cases in full — safe to re-run.
    dataset = await load_seed_dataset(
        session,
        tenant_id=tenant_id,
        payload=payload,
    )
    print(
        f"boreal: eval dataset {BOREAL_EVAL_DATASET!r} loaded "
        f"({len(payload.get('cases') or [])} cases, "
        f"threshold={payload.get('pass_threshold')})"
    )


async def _amain() -> int:
    engine = get_engine()
    Session = async_sessionmaker(engine, expire_on_commit=False)

    async with Session() as session:
        tenant_id = await _seed_tenant(session)
        await _seed_agent_config(session, tenant_id)
        await session.commit()

    # The eval seed loader needs RLS scoping (``app.tenant_id`` set +
    # ``SET LOCAL ROLE nexus_app``) so the row-level policies accept
    # the dataset + cases writes. ``tenant_scoped_session`` opens its
    # own transaction, applies both, commits on success, rolls back
    # on exception.
    async with Session() as session, tenant_scoped_session(session, tenant_id):
        await _seed_eval_dataset(session, tenant_id)

    print(f"boreal: ok slug={BOREAL_SLUG} id={tenant_id}")
    print()
    print("Next steps for the operator:")
    print("  1. Upload pending skills if any were skipped (see warnings above).")
    print("  2. Install WhatsApp Meta connector via /tenants/<id>/connectors.")
    print("  3. Install AgendaPro connector via /tenants/<id>/connectors.")
    print("  4. Run eval dataset 'aesthetic_clinic_v1' in the sandbox.")
    print("  5. If pass_rate ≥ 0.92, promote agent_config v1 to ACTIVE.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_amain()))
