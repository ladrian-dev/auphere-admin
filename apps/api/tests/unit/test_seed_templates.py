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

    # Policies: el defecto llega al **expediente**, no al texto.
    #
    # Hasta la spec 019 este test afirmaba lo contrario —que 24h, 30% y 100%
    # se escribían en el prompt— y eso era justo el fallo: Boreal nunca fijó
    # esas condiciones, y el agente las recitaba por WhatsApp como política de
    # la clínica. Ahora el prompt calla y deriva; el dato sigue donde lo leen
    # el motor y las herramientas (T036, owner 2026-09-28).
    assert rendered.policies["surgery"]["deposit_pct"] == 30
    assert rendered.policies["no_show"]["fee_pct"] == 100
    assert "30%" not in rendered.system_prompt
    assert "100%" not in rendered.system_prompt
    assert "La seña para fijar fecha de quirófano la fija la clínica" in rendered.system_prompt

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


def test_no_template_name_mixes_languages() -> None:
    """El nombre que ve el partner está en un solo idioma (spec 019, R9).

    El alta enseña trece nombres en una rejilla y son lo único que hay para
    decidir. Dos llegaban a medio traducir —«Spa (belleza y wellness)» y
    «Clínica estética (medspa + cirugía)»—, y una palabra suelta del otro
    idioma en una lista de trece obliga a traducir mentalmente justo donde
    hay que comparar.

    Lo que se prohíbe son palabras inglesas **de vocabulario**. Una marca no
    cuenta: «WooCommerce» es el nombre del producto, no una traducción
    pendiente, y «spa» está en el diccionario de la RAE.
    """
    prohibidas = {
        "wellness",
        "medspa",
        "beauty",
        "salon",
        "store",
        "sales",
        "clinic",
        "shop",
        "booking",
        "basic",
    }
    marcas = {"woocommerce"}
    culpables: list[tuple[str, str]] = []
    for name in list_seed_templates():
        display = load_seed_template(name).display_name
        palabras = {p.strip("()/+.,").lower() for p in display.replace("/", " ").split()}
        for mala in palabras & prohibidas:
            if mala in marcas:
                continue
            culpables.append((name, display))
    assert not culpables, f"nombres a medio traducir: {culpables}"


# ── T036 · el agente calla lo que nadie le dijo ──────────────────────────────
#
# Los campos opcionales traían defectos concretos —24 h de cancelación gratis,
# 30 % de seña de cirugía, 100 % de no-show— y el prompt los escribía como
# política de la casa. Una clínica que no configuraba nada tenía un agente
# comprometiendo cobros que su dueño no fijó: no un hueco vacío, sino una
# respuesta segura de sí misma y falsa. Decisión del owner (2026-09-28): si no
# se lo dijeron, no lo dice, y deriva al equipo.

_CLINICA_MINIMOS = {
    "tenant.name": "Clínica Boreal",
    "tenant.timezone": "America/Caracas",
    "tenant.address": "Av. X",
    "clinical.titular_name": "Dra. Ruiz",
    "tenant.surgery_referral_hospital": "Hospital Y",
    "tenant.surgery_referral_phone": "+58 000",
    "tenant.instagram_handle": "@boreal",
    "tenant.front_desk_phone_label": "+58 111",
    "tenant.business_hours_label": "Lunes a viernes 9:00 a 18:00",
}


def test_una_politica_no_dicha_no_se_afirma() -> None:
    tpl = load_seed_template("aesthetic_clinic_v1")
    prompt = render_seed_template(tpl, placeholders=dict(_CLINICA_MINIMOS)).system_prompt

    assert "seña del 30%" not in prompt
    assert "cargo del 100%" not in prompt
    assert "La seña para fijar fecha de quirófano la fija la clínica" in prompt
    assert "La política de cancelación la confirma el equipo" in prompt


def test_la_misma_politica_dicha_se_afirma() -> None:
    """La otra mitad: callar no puede ser el único comportamiento posible."""
    tpl = load_seed_template("aesthetic_clinic_v1")
    prompt = render_seed_template(
        tpl,
        placeholders={
            **_CLINICA_MINIMOS,
            "policies.surgery.deposit_pct": 40,
            "policies.no_show.fee_pct": 50,
            "policies.cancellation.late_fee_pct": 25,
        },
    ).system_prompt

    assert "seña del 40%" in prompt
    assert "cargo del 50%" in prompt
    assert "La seña para fijar fecha de quirófano la fija la clínica" not in prompt


def test_el_defecto_sigue_estando_en_el_dato() -> None:
    """Callar es cosa del prompt, no del expediente.

    ``policies`` lo lee el motor y las herramientas; si el defecto
    desapareciera de ahí, esto dejaría de ser «el agente no lo afirma» y
    pasaría a ser «la clínica no tiene política», que es otra cosa.
    """
    tpl = load_seed_template("aesthetic_clinic_v1")
    rendered = render_seed_template(tpl, placeholders=dict(_CLINICA_MINIMOS))
    assert rendered.policies["surgery"]["deposit_pct"] == 30
    assert rendered.policies["no_show"]["fee_pct"] == 100


def test_un_valor_en_blanco_no_cuenta_como_dicho() -> None:
    """Dejar el campo vacío no es fijar una política."""
    tpl = load_seed_template("aesthetic_clinic_v1")
    prompt = render_seed_template(
        tpl,
        placeholders={**_CLINICA_MINIMOS, "tenant.pricing_table_label": "   "},
    ).system_prompt
    assert "No tenés la tabla de precios de esta clínica" in prompt


def test_lo_que_no_se_afirma_no_se_exige_en_el_alta() -> None:
    """La consecuencia medible: la plantilla más pesada baja de 12 a 7.

    Los cinco que salen son exactamente los que el owner sacó del alta el
    2026-09-28, y salen **porque el prompt dejó de afirmarlos**, no porque
    alguien los tachara de una lista.
    """
    from nexus_api.api.console.seed_templates import describe_placeholders

    ph = describe_placeholders(load_seed_template("aesthetic_clinic_v1"))
    obligatorios = {p.key for p in ph if p.required}
    assert len(obligatorios) == 7
    for fuera in (
        "clinical.titular_credential",
        "tenant.saturday_label",
        "tenant.consultation_price_label",
        "tenant.pricing_table_label",
        "tenant.payment_methods_label",
    ):
        assert fuera not in obligatorios, f"{fuera} sigue pidiéndose en el alta"
        assert fuera in {p.key for p in ph}, f"{fuera} desapareció en vez de volverse opcional"


def test_las_trece_siguen_renderizando_con_lo_justo() -> None:
    """La guardia de la premisa que resultó falsa.

    T036 nació diciendo que sin estos campos el renderizador levantaría
    ``SeedTemplatePlaceholderMissing``. Se midió y no era cierto. Esto lo fija:
    si alguien añade mañana un token suelto fuera de un bloque, se ve aquí.
    """
    from nexus_api.api.console.seed_templates import describe_placeholders

    base = {"tenant.name": "X", "tenant.timezone": "Europe/Madrid"}
    for name in list_seed_templates():
        tpl = load_seed_template(name)
        ph = describe_placeholders(tpl)
        vals = {**base, **{p.key: ("1" if p.kind == "number" else "X") for p in ph if p.required}}
        render_seed_template(tpl, placeholders=vals)
