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
