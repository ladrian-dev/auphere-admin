"""Spec 075 — las reglas puras de editar una plantilla.

Las plantillas de estas pruebas tienen la forma de la lista de Meta
(``GET /{waba}/message_templates``): una sola fuente para la consola y el
panel (9.3) que decide qué se puede editar y cómo se arma lo que se manda.
"""

from __future__ import annotations

import copy
from typing import Any

import pytest

from nexus_api.schemas.whatsapp_templates import TemplateContentIn
from nexus_api.services import whatsapp_template_edit as rules
from nexus_api.services.reservations import templates as reservas
from nexus_api.services.whatsapp_templates import TemplateOut


def _tpl(
    *,
    status: str = "REJECTED",
    category: str = "UTILITY",
    components: list[dict[str, Any]] | None = None,
    name: str = "cita_recordatorio",
    language: str = "es",
) -> TemplateOut:
    return TemplateOut(
        id="1234567890",
        name=name,
        language=language,
        category=category,
        status=status,
        components=components if components is not None else _full(),
    )


def _full() -> list[dict[str, Any]]:
    """Todo lo que el editor sabe pintar, como lo lista Meta."""
    return [
        {"type": "HEADER", "format": "TEXT", "text": "Tu cita"},
        {
            "type": "BODY",
            "text": "Hola {{nombre}}, te esperamos {{cuando}}.",
            "example": {
                "body_text_named_params": [
                    {"param_name": "nombre", "example": "Camila"},
                    {"param_name": "cuando", "example": "el jueves"},
                ]
            },
        },
        {"type": "FOOTER", "text": "Barbería Centro"},
        {
            "type": "BUTTONS",
            "buttons": [
                {"type": "QUICK_REPLY", "text": "Confirmo"},
                {"type": "URL", "text": "Ver cita", "url": "https://example.com/cita"},
                {"type": "PHONE_NUMBER", "text": "Llamar", "phone_number": "+34600000000"},
            ],
        },
    ]


def _positional() -> list[dict[str, Any]]:
    return [
        {
            "type": "BODY",
            "text": "Hola {{1}}, tu cita es {{2}}.",
            "example": {"body_text": [["Camila", "el jueves"]]},
        }
    ]


# ── edit_blocker (3.1, 3.2) ─────────────────────────────────────────────────


@pytest.mark.parametrize("status", ["APPROVED", "REJECTED", "PAUSED"])
def test_editable_statuses_without_blocker(status: str) -> None:
    assert rules.edit_blocker(_tpl(status=status)) is None


@pytest.mark.parametrize("status", ["PENDING", "IN_APPEAL", "DISABLED", "PENDING_DELETION", ""])
def test_other_statuses_block_with_status(status: str) -> None:
    assert rules.edit_blocker(_tpl(status=status)) == "status"


def test_authentication_category_blocks() -> None:
    assert rules.edit_blocker(_tpl(category="AUTHENTICATION")) == "authentication"


@pytest.mark.parametrize("fmt", ["IMAGE", "VIDEO", "DOCUMENT", "LOCATION"])
def test_media_header_blocks(fmt: str) -> None:
    comps = _full()
    comps[0] = {
        "type": "HEADER",
        "format": fmt,
        "example": {"header_handle": ["https://scontent.example/x"]},
    }
    assert rules.edit_blocker(_tpl(components=comps)) == "media_header"


def test_header_with_variable_blocks() -> None:
    comps = _full()
    comps[0] = {
        "type": "HEADER",
        "format": "TEXT",
        "text": "Hola {{1}}",
        "example": {"header_text": ["Camila"]},
    }
    assert rules.edit_blocker(_tpl(components=comps)) == "header_variable"


@pytest.mark.parametrize(
    "button_type", ["OTP", "COPY_CODE", "CATALOG", "FLOW", "MPM", "VOICE_CALL"]
)
def test_unsupported_buttons_block(button_type: str) -> None:
    comps = _full()
    comps[3] = {"type": "BUTTONS", "buttons": [{"type": button_type, "text": "x"}]}
    assert rules.edit_blocker(_tpl(components=comps)) == "unsupported_button"


def test_url_with_variable_blocks() -> None:
    comps = _full()
    comps[3] = {
        "type": "BUTTONS",
        "buttons": [
            {
                "type": "URL",
                "text": "Ver",
                "url": "https://example.com/{{1}}",
                "example": ["https://example.com/abc"],
            }
        ],
    }
    assert rules.edit_blocker(_tpl(components=comps)) == "url_variable"


def test_four_buttons_block() -> None:
    comps = _full()
    comps[3] = {
        "type": "BUTTONS",
        "buttons": [{"type": "QUICK_REPLY", "text": f"b{i}"} for i in range(4)],
    }
    assert rules.edit_blocker(_tpl(components=comps)) == "too_many_buttons"


@pytest.mark.parametrize(
    "ctype", ["CAROUSEL", "LIMITED_TIME_OFFER", "CALL_PERMISSION_REQUEST", "SOMETHING_NEW"]
)
def test_unknown_components_block(ctype: str) -> None:
    comps = [*_full(), {"type": ctype, "cards": []}]
    assert rules.edit_blocker(_tpl(components=comps)) == "unsupported_component"


def test_unknown_key_in_a_known_component_blocks() -> None:
    """Lo que el viaje de ida y vuelta no reproduce se perdería al editar
    (3.3): bloquea, aunque sea una clave nueva de Meta en un cuerpo."""
    comps = _full()
    comps[1] = {**comps[1], "add_security_recommendation": True}
    assert rules.edit_blocker(_tpl(components=comps)) == "unsupported_component"


def test_status_wins_over_content() -> None:
    comps = _full()
    comps[0] = {"type": "HEADER", "format": "IMAGE"}
    assert rules.edit_blocker(_tpl(status="PENDING", components=comps)) == "status"


# ── draft_of / build: ida y vuelta (3.3) ────────────────────────────────────


@pytest.mark.parametrize("components", [_full(), _positional(), [_full()[1]]])
def test_round_trip_reproduces_meta(components: list[dict[str, Any]]) -> None:
    tpl = _tpl(components=components)
    draft = rules.draft_of(tpl)
    assert draft is not None
    built = rules.build(TemplateContentIn(**draft.model_dump()))
    assert rules.normalize(built) == rules.normalize(components)


def test_draft_splits_the_parts() -> None:
    draft = rules.draft_of(_tpl())
    assert draft is not None
    assert draft.header_text == "Tu cita"
    assert draft.body_text.startswith("Hola {{nombre}}")
    assert draft.footer_text == "Barbería Centro"
    assert [b.type for b in draft.buttons] == ["QUICK_REPLY", "URL", "PHONE_NUMBER"]
    assert draft.examples == {"nombre": "Camila", "cuando": "el jueves"}
    assert draft.category == "UTILITY"


def test_draft_is_none_when_content_blocks() -> None:
    comps = _full()
    comps[0] = {"type": "HEADER", "format": "IMAGE"}
    assert rules.draft_of(_tpl(components=comps)) is None


def test_normalize_orders_components_and_ignores_key_order() -> None:
    a = _full()
    b = list(reversed(copy.deepcopy(a)))
    b[0] = dict(reversed(list(b[0].items())))
    assert rules.normalize(a) == rules.normalize(b)


# ── version (7.1) ───────────────────────────────────────────────────────────


def test_version_is_16_chars_and_stable() -> None:
    a = rules.template_version(_tpl())
    shuffled = [dict(reversed(list(c.items()))) for c in _full()]
    b = rules.template_version(_tpl(components=shuffled))
    assert len(a) == 16 and a == b


def test_version_changes_with_one_character() -> None:
    comps = _full()
    comps[1] = {**comps[1], "text": comps[1]["text"] + "!"}
    assert rules.template_version(_tpl()) != rules.template_version(_tpl(components=comps))


def test_version_changes_with_category() -> None:
    assert rules.template_version(_tpl()) != rules.template_version(_tpl(category="MARKETING"))


# ── is_noop (3.4) ───────────────────────────────────────────────────────────


def _content_of(tpl: TemplateOut, **over: Any) -> TemplateContentIn:
    draft = rules.draft_of(tpl)
    assert draft is not None
    return TemplateContentIn(**{**draft.model_dump(), **over})


def test_same_content_is_noop() -> None:
    tpl = _tpl()
    assert rules.is_noop(tpl, _content_of(tpl)) is True


def test_missing_category_means_keep_it() -> None:
    tpl = _tpl()
    assert rules.is_noop(tpl, _content_of(tpl, category=None)) is True


def test_other_category_is_not_noop() -> None:
    tpl = _tpl()
    assert rules.is_noop(tpl, _content_of(tpl, category="MARKETING")) is False


def test_other_text_is_not_noop() -> None:
    tpl = _tpl()
    assert rules.is_noop(tpl, _content_of(tpl, footer_text="Otra")) is False


# ── plantillas de sistema (4.1, 4.2, 4.3) ───────────────────────────────────


def test_registry_has_the_six_of_reservas_and_the_two_of_cobros() -> None:
    for name in reservas.NAMES:
        system = rules.SYSTEM_TEMPLATES[name]
        assert system.mode == "exact"
        assert system.variables == tuple(reservas.VARIABLES[name])
    for name in (rules.COBROS_PROXIMO, rules.COBROS_VENCIDO):
        system = rules.SYSTEM_TEMPLATES[name]
        assert system.mode == "subset_keep"
        assert set(system.variables) == {"cliente", "negocio", "monto", "fecha"}


def test_system_templates_only_apply_in_spanish() -> None:
    assert rules.system_template_for("reserva_recordatorio", "es") is not None
    assert rules.system_template_for("reserva_recordatorio", "es_ES") is not None
    assert rules.system_template_for("reserva_recordatorio", "en_US") is None
    assert rules.system_template_for("cita_recordatorio", "es") is None


def test_exact_reports_missing_and_extra() -> None:
    system = rules.SYSTEM_TEMPLATES["reserva_recordatorio"]
    wanted = list(system.variables)
    missing, extra = rules.check_system_variables(system, current=wanted, new=[*wanted[1:], "otra"])
    assert missing == [wanted[0]]
    assert extra == ["otra"]
    assert rules.check_system_variables(system, current=wanted, new=wanted) == ([], [])


def test_subset_keep_rejects_outsiders_and_losses() -> None:
    system = rules.SYSTEM_TEMPLATES[rules.COBROS_VENCIDO]
    current = ["cliente", "negocio", "monto"]
    assert rules.check_system_variables(system, current=current, new=[*current, "iban"]) == (
        [],
        ["iban"],
    )
    assert rules.check_system_variables(system, current=current, new=["cliente", "negocio"]) == (
        ["monto"],
        [],
    )
    assert rules.check_system_variables(system, current=current, new=[*current, "fecha"]) == (
        [],
        [],
    )


def test_trimmed_text_and_phone_format_are_still_noop() -> None:
    """El editor recorta y quita espacios y guiones del teléfono: si Meta
    lista el valor con otro formato, sigue sin haber nada que mandar (3.4)."""
    comps = _full()
    comps[1] = {**comps[1], "text": comps[1]["text"] + "  "}
    comps[3] = {
        "type": "BUTTONS",
        "buttons": [{"type": "PHONE_NUMBER", "text": "Llamar", "phone_number": "+34 600-000-000"}],
    }
    tpl = _tpl(components=comps)
    draft = rules.draft_of(tpl)
    assert draft is not None
    trimmed = draft.model_dump()
    trimmed["body_text"] = trimmed["body_text"].strip()
    trimmed["buttons"][0]["phone_number"] = "+34600000000"
    assert rules.is_noop(tpl, TemplateContentIn(**trimmed)) is True
