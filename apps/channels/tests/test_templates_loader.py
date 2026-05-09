"""Verify the YAML templates ship correctly and the loader validates them."""

from __future__ import annotations

import pytest

from nexus_channels.whatsapp_ycloud.templates_loader import (
    list_templates,
    load_template,
    render_body_params,
)


def test_cultor_barber_templates_load():
    """All 6 Phase 1 templates for Cultor Barber must parse cleanly."""
    templates = list_templates(tenant_slug="cultor_barber")
    names = {t.name for t in templates}
    expected = {
        "reminder_24h",
        "reminder_1h",
        "no_show_followup",
        "welcome_cl_es",
        "alert_escalation_v1",
        "alert_needs_reauth_v1",
    }
    assert expected.issubset(names), f"missing: {expected - names}"


def test_load_named_template():
    tpl = load_template("reminder_24h", tenant_slug="cultor_barber")
    assert tpl.name == "reminder_24h"
    assert tpl.language == "es_CL"
    assert tpl.category == "UTILITY"
    assert tpl.params == ["customer_name", "date_label", "time_label", "barber_name"]


def test_render_body_params_in_declared_order():
    tpl = load_template("reminder_24h", tenant_slug="cultor_barber")
    rendered = render_body_params(
        tpl,
        {
            "barber_name": "Luis",
            "customer_name": "Juan",
            "date_label": "viernes 10",
            "time_label": "15:00",
        },
    )
    assert rendered == ["Juan", "viernes 10", "15:00", "Luis"]


def test_render_body_params_rejects_missing():
    tpl = load_template("reminder_24h", tenant_slug="cultor_barber")
    with pytest.raises(KeyError, match="missing params"):
        render_body_params(tpl, {"customer_name": "Juan"})


def test_load_unknown_template_raises():
    with pytest.raises(KeyError):
        load_template("does_not_exist", tenant_slug="cultor_barber")


def test_alert_template_takes_no_params():
    tpl = load_template("alert_needs_reauth_v1", tenant_slug="cultor_barber")
    assert tpl.params == []
    assert render_body_params(tpl, {}) == []
