"""Spec 024 (Requisitos 1.2, 1.3, 2.3, 4.1, 5.3): ``admin_access`` ↔ «audience».

One translation for everyone: what the console writes, the partner API
reads unchanged, and the gate compares the same way.
"""

from __future__ import annotations

import pytest

from nexus_api.services.agent_audience import (
    AudienceEmpty,
    AudienceInvalidPhone,
    AudienceLocked,
    AudienceNumber,
    apply_audience,
    audience_of,
    count_of,
    is_locked_template,
)


def test_no_admin_access_reads_as_everyone() -> None:
    a = audience_of({})
    assert a.mode == "everyone" and a.numbers == [] and a.locked is False


def test_admin_only_reads_as_list_with_names() -> None:
    policies = {
        "admin_access": {
            "admin_only": True,
            "admin_phones": ["+56991919125", "+34666261967"],
            "admins": [{"phone": "+56991919125", "name": "Daniel, ventas", "role": "full"}],
        }
    }
    a = audience_of(policies, locked=True)
    assert a.mode == "list" and a.locked is True
    assert [(n.phone, n.name) for n in a.numbers] == [
        ("+56991919125", "Daniel, ventas"),
        ("+34666261967", None),
    ]


def test_writing_a_list_normalises_and_deduplicates() -> None:
    out = apply_audience(
        {"console": {"objective": "vender"}},
        mode="list",
        numbers=[
            AudienceNumber("+56 9 9191 9125", "Daniel, ventas"),
            AudienceNumber("56991919125", None),  # the same number, other format
            AudienceNumber("+34 666 261 967", "  "),
        ],
    )
    access = out["admin_access"]
    assert access["admin_only"] is True
    assert access["admin_phones"] == ["+56991919125", "+34666261967"]
    assert access["admins"] == [
        {"phone": "+56991919125", "name": "Daniel, ventas", "role": "full"},
        {"phone": "+34666261967", "name": None, "role": "full"},
    ]
    assert out["console"] == {"objective": "vender"}  # untouched


def test_a_readonly_role_set_by_the_partner_api_survives_a_console_rewrite() -> None:
    policies = {
        "admin_access": {
            "admin_only": True,
            "admin_phones": ["+56991919125"],
            "admins": [{"phone": "+56991919125", "name": "Ana", "role": "readonly"}],
        }
    }
    out = apply_audience(policies, mode="list", numbers=[AudienceNumber("+56991919125", "Ana")])
    assert out["admin_access"]["admins"][0]["role"] == "readonly"


def test_everyone_turns_the_mode_off_but_keeps_the_numbers() -> None:
    policies = {
        "admin_access": {"admin_only": True, "admin_phones": ["+56991919125"], "admins": []}
    }
    out = apply_audience(policies, mode="everyone", numbers=[])
    assert out["admin_access"]["admin_only"] is False
    assert out["admin_access"]["admin_phones"] == ["+56991919125"]


@pytest.mark.parametrize("bad", ["", "   ", "12345", "+34 1", "abc"])
def test_a_phone_that_could_never_match_is_refused_by_name(bad: str) -> None:
    with pytest.raises(AudienceInvalidPhone) as exc:
        apply_audience({}, mode="list", numbers=[AudienceNumber(bad)])
    assert exc.value.phone == bad.strip()
    assert exc.value.code == "audience_invalid_phone"


def test_a_list_without_numbers_is_refused() -> None:
    with pytest.raises(AudienceEmpty):
        apply_audience({}, mode="list", numbers=[])


def test_a_locked_agent_cannot_be_opened_but_its_list_can_change() -> None:
    with pytest.raises(AudienceLocked):
        apply_audience({}, mode="everyone", numbers=[], locked=True)
    out = apply_audience({}, mode="list", numbers=[AudienceNumber("+34666261967")], locked=True)
    assert out["admin_access"]["admin_phones"] == ["+34666261967"]


def test_count_reads_only_usable_numbers_of_an_active_list() -> None:
    assert count_of({}) == ("everyone", 0)
    assert count_of({"admin_access": {"admin_only": False, "admin_phones": ["+1"]}}) == (
        "everyone",
        0,
    )
    assert count_of(
        {"admin_access": {"admin_only": True, "admin_phones": ["+56991919125", "123"]}}
    ) == ("list", 1)


def test_locked_comes_from_the_template() -> None:
    assert is_locked_template("cobranza_v1") is True
    assert is_locked_template("cobranza") is True
    assert is_locked_template("woocommerce_sales_v1") is False
    assert is_locked_template(None) is False
    assert is_locked_template("no_such_template") is False
