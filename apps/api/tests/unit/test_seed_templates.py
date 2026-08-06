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
    "tenant.front_desk_phone_label": "+58 212-555-0100",
    "tenant.consultation_price_label": "USD 80, acreditable al procedimiento",
    "tenant.pricing_table_label": (
        "rinoplastia USD 4.800-6.500 · mamoplastia USD 5.500-7.200 · BBL USD 5.000-6.800"
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


# ── woocommerce_sales_v1 — agente de ventas sobre una tienda WooCommerce ──


def test_list_seed_templates_includes_woocommerce_sales() -> None:
    assert "woocommerce_sales_v1" in list_seed_templates()


def test_woocommerce_sales_v1_loads_with_expected_shape() -> None:
    tpl = load_seed_template("woocommerce_sales_v1")
    assert tpl.version == "1.0.0"
    assert "ventas" in tpl.display_name.lower()
    assert tpl.agent_defaults["name"] == "Nico"
    assert tpl.agent_defaults["language"] == "es"

    # Whitelist: lecturas de catálogo/pedidos + link de pago + escalado +
    # interactive. El agente de ventas es SOLO LECTURA sobre órdenes: las
    # escrituras (create/update/add_note) NO están habilitadas (F-2/F-3);
    # cualquier cambio se deriva a un humano con escalate.escalate_to_human.
    reads = {
        "woocommerce.list_products",
        "woocommerce.get_product",
        "woocommerce.list_product_variations",
        "woocommerce.list_categories",
        "woocommerce.list_orders",
        "woocommerce.get_order",
    }
    order_writes = {
        "woocommerce.create_order",
        "woocommerce.update_order_status",
        "woocommerce.update_order",
        "woocommerce.add_order_note",
    }
    assert reads.issubset(tpl.tools_required)
    assert "woocommerce.build_checkout_link" in tpl.tools_required
    assert "escalate.escalate_to_human" in tpl.tools_required
    assert "response.send_interactive" in tpl.tools_required
    # Ninguna escritura destructiva de órdenes está en el whitelist.
    assert order_writes.isdisjoint(tpl.tools_required)
    # No filtra tools de otros verticales (booking / billing).
    assert "booking.create_appointment" not in tpl.tools_required
    assert "billing.create_account" not in tpl.tools_required

    assert tpl.policies_default["store"]["currency"] == "CLP"


def test_woocommerce_sales_v1_renders_with_store_data() -> None:
    tpl = load_seed_template("woocommerce_sales_v1")
    rendered = render_seed_template(
        tpl,
        placeholders={
            "tenant.name": "Barber Supply Chile",
            "tenant.timezone": "America/Santiago",
        },
    )
    assert rendered.seed_template_ref == "woocommerce_sales_v1"
    assert "Barber Supply Chile" in rendered.system_prompt
    assert "Nico" in rendered.system_prompt
    assert "CLP" in rendered.system_prompt
    # Anclas de comportamiento clave llegan al prompt final.
    assert "grounding" in rendered.system_prompt.lower()
    assert "confirmaci" in rendered.system_prompt.lower()  # protocolo de pedido
    # El cierre de venta se hace con build_checkout_link (no create_order).
    assert "build_checkout_link" in rendered.system_prompt
    # El agente NO crea órdenes: create_order no está en el whitelist.
    assert "woocommerce.create_order" not in rendered.tools
    assert "woocommerce.build_checkout_link" in rendered.tools
    assert rendered.policies["store"]["currency"] == "CLP"


def test_woocommerce_sales_v1_override_currency() -> None:
    tpl = load_seed_template("woocommerce_sales_v1")
    rendered = render_seed_template(
        tpl,
        placeholders={
            "tenant.name": "X",
            "tenant.timezone": "America/Santiago",
            "policies.store.currency": "USD",
        },
    )
    assert rendered.policies["store"]["currency"] == "USD"
    assert "USD" in rendered.system_prompt
