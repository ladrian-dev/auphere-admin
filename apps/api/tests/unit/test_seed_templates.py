"""Unit tests for the seed_template loader (Block J)."""

from __future__ import annotations

import pytest

from nexus_api.services.templating import (
    SeedTemplateNotFound,
    SeedTemplatePlaceholderMissing,
    list_seed_templates,
    load_seed_template,
    render_seed_template,
)

pytestmark = pytest.mark.unit


def test_list_seed_templates_includes_barbershop() -> None:
    names = list_seed_templates()
    assert "barbershop_v1" in names


def test_load_unknown_template_raises() -> None:
    with pytest.raises(SeedTemplateNotFound):
        load_seed_template("nonexistent_v9")


def test_barbershop_v1_loads_with_expected_shape() -> None:
    tpl = load_seed_template("barbershop_v1")
    assert tpl.version == "1.0.0"
    assert "Barbería" in tpl.display_name
    assert tpl.agent_defaults["name"] == "Alex"
    assert tpl.agent_defaults["language"] == "es"
    assert "booking.check_availability" in tpl.tools_required
    assert "agendapro.create_appointment" not in tpl.tools_required  # internal-only
    assert tpl.policies_default["cancellation"]["free_hours_before"] == 24


def test_render_resolves_placeholders_and_uses_defaults() -> None:
    tpl = load_seed_template("barbershop_v1")
    rendered = render_seed_template(
        tpl,
        placeholders={
            "tenant.name": "Cultor Barber",
            "tenant.address": "Av. Apoquindo 1234, Las Condes",
            "tenant.timezone": "America/Santiago",
            "tenant.business_hours_label": "Lun-Sáb 10-19",
        },
    )
    assert rendered.seed_template_ref == "barbershop_v1"
    assert "Cultor Barber" in rendered.system_prompt
    assert "Av. Apoquindo 1234" in rendered.system_prompt
    assert "America/Santiago" in rendered.system_prompt
    # agent.* defaults applied
    assert "Alex" in rendered.system_prompt
    assert "casual" in rendered.system_prompt
    # policies.* defaults applied
    assert "<24h" in rendered.system_prompt
    assert "fee de 50%" in rendered.system_prompt
    assert "100% del servicio" in rendered.system_prompt
    assert "15 min" in rendered.system_prompt
    # Tools whitelist passed through
    assert "booking.create_appointment" in rendered.tools
    # Policies merged
    assert rendered.policies["cancellation"]["free_hours_before"] == 24


def test_render_overrides_placeholder_value() -> None:
    tpl = load_seed_template("barbershop_v1")
    rendered = render_seed_template(
        tpl,
        placeholders={
            "tenant.name": "Cultor Barber",
            "tenant.address": "Av. Apoquindo 1234",
            "tenant.timezone": "America/Santiago",
            "tenant.business_hours_label": "Lun-Sáb 10-19",
            "agent.name": "Cultor Bot",
            "policies.no_show.fee_pct": 75,
        },
    )
    assert "Cultor Bot" in rendered.system_prompt
    assert "Alex" not in rendered.system_prompt
    assert "75% del servicio" in rendered.system_prompt
    assert rendered.policies["no_show"]["fee_pct"] == 75
    # Other policies stay at default
    assert rendered.policies["no_show"]["grace_min"] == 15


def test_render_fails_fast_when_required_placeholder_missing() -> None:
    tpl = load_seed_template("barbershop_v1")
    with pytest.raises(SeedTemplatePlaceholderMissing) as excinfo:
        render_seed_template(
            tpl,
            placeholders={
                "tenant.name": "Cultor Barber",
                # missing tenant.address, tenant.timezone, tenant.business_hours_label
            },
        )
    # The message must name the offending key so the operator can fix it.
    assert (
        "tenant.address" in str(excinfo.value)
        or "tenant.timezone" in str(excinfo.value)
        or "tenant.business_hours_label" in str(excinfo.value)
    )


# ---------------------------------------------------------------------------
# aesthetic_clinic_v1 (ADR-025) — vertical híbrido medspa + cirugía estética
# ---------------------------------------------------------------------------


_AESTHETIC_PLACEHOLDERS_BOREAL: dict[str, object] = {
    "tenant.name": "Clínica Boreal",
    "tenant.address": "Av. Principal de Las Mercedes, Edificio Atlantic, Piso 4. Caracas",
    "tenant.timezone": "America/Caracas",
    "tenant.business_hours_label": "Lun-Vie 9-18, Sáb 9-14",
    "tenant.saturday_label": "sábados 09:00-14:00, solo consultas pre-op — NO inyectables",
    "tenant.instagram_handle": "@clinicaboreal",
    "tenant.surgery_referral_hospital": "Centro Médico Docente La Trinidad (CMDLT)",
    "tenant.surgery_referral_phone": "+58 212-949-6411",
    "tenant.consultation_price_label": "USD 80, acreditable al procedimiento",
    "tenant.pricing_table_label": (
        "rinoplastia USD 4.800-6.500 · mamoplastia USD 5.500-7.200 · "
        "BBL USD 5.000-6.800"
    ),
    "tenant.payment_methods_label": (
        "Zelle, transferencia internacional o Pago Móvil al cambio del día"
    ),
    "clinical.titular_name": "Dra. Valentina Hurtado",
    "clinical.titular_credential": "Cirujana plástica, miembro titular SVCPREM",
}


def test_list_seed_templates_includes_aesthetic_clinic() -> None:
    names = list_seed_templates()
    assert "aesthetic_clinic_v1" in names


def test_aesthetic_clinic_v1_loads_with_expected_shape() -> None:
    tpl = load_seed_template("aesthetic_clinic_v1")
    assert tpl.version == "1.0.0"
    assert "estética" in tpl.display_name.lower()
    assert tpl.agent_defaults["name"] == "Luciana"
    assert tpl.agent_defaults["tone"] == "cálido-profesional"
    assert tpl.agent_defaults["language"] == "es"

    # Tools recomendadas — incluye las clínicas + interactive components
    # + operator consult (backchannel para casos fuera de scope).
    assert "booking.create_appointment" in tpl.tools_required
    assert "response.send_interactive" in tpl.tools_required
    assert "operator.consult_owner" in tpl.tools_required
    assert "escalate.escalate_to_human" in tpl.tools_required

    # Tools de otros verticales NO deben filtrarse — el seed es bespoke,
    # no un superset.
    assert "queue.join_queue" not in tpl.tools_required  # barbería walk-in
    assert "commission.calculate_commission" not in tpl.tools_required  # barbería

    # Policies específicas del vertical estético.
    assert tpl.policies_default["cancellation"]["free_hours_before"] == 24
    assert tpl.policies_default["surgery"]["deposit_pct"] == 30
    assert tpl.policies_default["minor"]["consent_required"] is True
    assert tpl.policies_default["privacy"]["retention_days"] == 90


def test_aesthetic_clinic_v1_renders_with_clinica_boreal_data() -> None:
    tpl = load_seed_template("aesthetic_clinic_v1")
    rendered = render_seed_template(
        tpl,
        placeholders=_AESTHETIC_PLACEHOLDERS_BOREAL,
    )

    assert rendered.seed_template_ref == "aesthetic_clinic_v1"

    # Identidad del tenant resuelta.
    assert "Clínica Boreal" in rendered.system_prompt
    assert "Av. Principal de Las Mercedes" in rendered.system_prompt
    assert "Dra. Valentina Hurtado" in rendered.system_prompt
    assert "SVCPREM" in rendered.system_prompt
    assert "@clinicaboreal" in rendered.system_prompt
    assert "Centro Médico Docente La Trinidad" in rendered.system_prompt
    assert "+58 212-949-6411" in rendered.system_prompt

    # Agent defaults aplicados.
    assert "Luciana" in rendered.system_prompt
    assert "cálido-profesional" in rendered.system_prompt

    # Policies defaults aplicados al texto del prompt.
    assert "24h" in rendered.system_prompt or "24 h" in rendered.system_prompt
    assert "30%" in rendered.system_prompt  # seña cirugía
    assert "15 min" in rendered.system_prompt  # no-show grace
    assert "100%" in rendered.system_prompt  # no-show fee

    # Reglas duras clave deben llegar al prompt final — no se pueden
    # perder porque son los anclajes regulatorios del vertical.
    assert "dosis" in rendered.system_prompt.lower()
    assert "embaraz" in rendered.system_prompt.lower()
    assert "queloid" in rendered.system_prompt.lower()
    assert "isotretino" in rendered.system_prompt.lower()
    assert "red flag" in rendered.system_prompt.lower()
    assert "anti-alucinación" in rendered.system_prompt.lower()

    # Tools whitelist y policies persistidas.
    assert "operator.consult_owner" in rendered.tools
    assert rendered.policies["surgery"]["deposit_pct"] == 30
    assert rendered.policies["minor"]["consent_required"] is True


def test_aesthetic_clinic_v1_fails_fast_on_missing_clinical_placeholder() -> None:
    tpl = load_seed_template("aesthetic_clinic_v1")
    missing_titular = dict(_AESTHETIC_PLACEHOLDERS_BOREAL)
    del missing_titular["clinical.titular_name"]
    with pytest.raises(SeedTemplatePlaceholderMissing) as excinfo:
        render_seed_template(tpl, placeholders=missing_titular)
    assert "clinical.titular_name" in str(excinfo.value)


def test_aesthetic_clinic_v1_fails_fast_on_missing_referral_hospital() -> None:
    tpl = load_seed_template("aesthetic_clinic_v1")
    missing_hospital = dict(_AESTHETIC_PLACEHOLDERS_BOREAL)
    del missing_hospital["tenant.surgery_referral_hospital"]
    with pytest.raises(SeedTemplatePlaceholderMissing) as excinfo:
        render_seed_template(tpl, placeholders=missing_hospital)
    assert "tenant.surgery_referral_hospital" in str(excinfo.value)


def test_aesthetic_clinic_v1_override_deposit_pct() -> None:
    """El operador puede afinar el % de seña sin re-editar el seed."""
    tpl = load_seed_template("aesthetic_clinic_v1")
    rendered = render_seed_template(
        tpl,
        placeholders={
            **_AESTHETIC_PLACEHOLDERS_BOREAL,
            "policies.surgery.deposit_pct": 40,
        },
    )
    assert "40%" in rendered.system_prompt
    assert rendered.policies["surgery"]["deposit_pct"] == 40
    # Otras policies quedan al default.
    assert rendered.policies["minor"]["consent_required"] is True
