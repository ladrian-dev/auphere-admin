"""Spec 063, requisito 4 — ni el constructor ni la plantilla se caen por un nombre.

La guarda de la garantía 5 (047, 15.4) mira si el borrador nombra a otro cliente del
mismo partner. Miraba también lo que el propio cliente dio al constructor, así que un
cliente llamado como una palabra corriente («Peluquería») tumbaba los borradores de
los demás. Ahora no cuenta lo que este cliente dio (nombre, descripción, ficha, guía),
y lo que el constructor escribe por su cuenta y nombra a otro se quita trozo a trozo.
"""

from __future__ import annotations

from typing import Any

import pytest
from structlog.testing import capture_logs

from nexus_api.services.agent_spec.validator import Context, ToolInfo
from nexus_api.services.builder.agent_draft import (
    BuilderUnavailable,
    DraftRequest,
    offline_output,
    sanitize,
)
from nexus_api.services.builder.guides.catalog import auphere_guide
from nexus_api.services.builder.guides.resolve import ResolvedGuide
from nexus_api.services.builder.guides.schema import label_key
from nexus_api.services.business.compilation import Facts

TOOLS = {"escalate.escalate_to_human": ToolInfo("escalate.escalate_to_human")}
OTHER = "Ferretería Olmo"
DESCRIPTION = "Atiende el WhatsApp del negocio: informa servicios y precios."


def _ctx(*foreign: str) -> Context:
    return Context(tools=TOOLS, foreign_names=foreign)


def _raw(**changes: Any) -> dict[str, Any]:
    raw: dict[str, Any] = {
        "voice": {"languages": ["es"]},
        "goal": "Que cada cliente salga atendido.",
        "instructions": [
            {"title": "Cómo atiendes", "body": "Responde con la ficha del negocio."},
            {"title": "Precios", "body": "Da los precios de la ficha."},
        ],
        "tools": ["escalate.escalate_to_human"],
        "rules": ["No ofrezcas descuentos."],
    }
    raw.update(changes)
    return raw


def _sanitize(raw: dict[str, Any], ctx: Context, *, description: str = DESCRIPTION, **kw: Any):  # type: ignore[no-untyped-def]
    request = DraftRequest.clean("Recepción", description)
    return sanitize(
        raw, request, ctx, kw.pop("facts", Facts(name="Salón Rita")), model_policy=None, **kw
    )


def _texts(spec: Any) -> str:
    return spec.model_dump_json()


# ── lo que el cliente dio no es de otro cliente (4.1) ──────────────────────


@pytest.mark.parametrize(
    ("label", "facts", "foreign", "description"),
    [
        ("same name as another client", Facts(name="Fulano"), ("Fulano",), DESCRIPTION),
        (
            "another client's name is a common word",
            Facts(name="Salón Rita"),
            ("Peluquería",),
            "Atiende el WhatsApp de la peluquería: informa servicios y precios.",
        ),
        (
            "own name contains another's",
            Facts(name="Estetica & Spa demo"),
            ("Estetica & Spa",),
            DESCRIPTION,
        ),
        ("unrelated names", Facts(name="Fulano"), ("Mengano",), DESCRIPTION),
    ],
)
def test_the_four_cases_of_the_research_give_a_draft(
    label: str, facts: Facts, foreign: tuple[str, ...], description: str
) -> None:
    request = DraftRequest.clean("Recepción", description)
    ctx = _ctx(*foreign)
    sanitize(offline_output(request, facts, ctx), request, ctx, facts, model_policy=None)


def test_a_name_in_the_description_is_not_a_leak() -> None:
    raw = _raw(instructions=[{"title": "Marcas", "body": f"Trabajamos con {OTHER}."}])
    draft = _sanitize(
        raw, _ctx(OTHER), description=f"Atiende el WhatsApp. Somos distribuidores de {OTHER}."
    )
    assert OTHER in _texts(draft.spec)


def test_a_name_in_the_business_profile_is_not_a_leak() -> None:
    raw = _raw(rules=[f"Recomienda {OTHER} para las herramientas."])
    draft = _sanitize(raw, _ctx(OTHER), facts=Facts(name="Salón Rita", info=f"Socios de {OTHER}."))
    assert OTHER in _texts(draft.spec)


def test_a_word_of_the_sector_guide_is_not_a_leak() -> None:
    found = auphere_guide("barberia_peluqueria")
    assert found is not None
    guide = ResolvedGuide(
        source="template", label=found.label, label_key=label_key(found.label), guide=found.guide
    )
    raw = _raw(instructions=[{"title": "Peluquería", "body": "Corte, color y peinado."}])
    draft = _sanitize(raw, _ctx("Peluquería"), guide=guide)
    assert "Peluquería" in _texts(draft.spec)


# ── lo que escribe el constructor por su cuenta se quita (4.2, 4.3) ────────


@pytest.mark.parametrize(
    ("field", "changes"),
    [
        (
            "section",
            {
                "instructions": [
                    {"title": "Cómo atiendes", "body": "Responde con la ficha del negocio."},
                    {"title": "Proveedor", "body": f"Pide el material a {OTHER}."},
                ]
            },
        ),
        (
            "rule",
            {"rules": ["No ofrezcas descuentos.", f"Deriva a {OTHER} si piden herramientas."]},
        ),
        ("goal", {"goal": f"Vender tanto como {OTHER}."}),
        (
            "procedure",
            {
                "procedures": [
                    {
                        "id": "pedir",
                        "title": "Pedir",
                        "when": "Si falta material",
                        "steps": f"Llama a {OTHER}.",
                        "tools": [],
                    },
                ]
            },
        ),
    ],
)
def test_what_the_builder_wrote_with_another_clients_name_is_removed(
    field: str, changes: dict[str, Any]
) -> None:
    with capture_logs() as logs:
        draft = _sanitize(_raw(**changes), _ctx(OTHER))
    assert OTHER not in _texts(draft.spec), field
    assert "Responde con la ficha del negocio." in _texts(draft.spec)
    (problems,) = [e for e in logs if e["event"] == "builder.draft.problems"]
    assert "foreign_text" in problems["codes"] and problems["pointers"]
    assert OTHER not in repr(logs)


def test_if_what_fails_cannot_be_removed_it_fails_with_a_name(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """4.3: lo que no se puede quitar (aquí, un problema en la descripción que escribió
    la persona) deja el borrador sin validar, y el fallo tiene nombre."""
    from nexus_api.services.agent_spec.validator import Problem
    from nexus_api.services.builder import agent_draft

    stuck = [Problem("/identity/description", "foreign_text", "x")]
    monkeypatch.setattr(agent_draft, "validate_spec", lambda doc, ctx, **kw: (None, stuck))
    with pytest.raises(BuilderUnavailable) as raised:
        _sanitize(_raw(), _ctx(OTHER))
    assert str(raised.value) == "invalid_draft"
