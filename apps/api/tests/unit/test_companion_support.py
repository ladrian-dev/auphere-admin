"""El constructor del ticket de soporte, sin base de datos (CO-08, §4).

Aquí viven los rechazos, que son la parte que decide si el escalado sirve o
solo hace ruido:

- un ticket **sin expediente** no se abre (§25.1);
- una **capacidad fuera de alcance** no se pide como funcionalidad (§5.2) —
  se explica por qué no está;
- una capacidad que **ya existe** no se pide: se usa;
- un **puente sin describir** no es un puente, es una promesa vacía (§25.4).

Lo que sí se abre pasa por ``propose→confirm`` como cualquier escritura; eso
se prueba de punta a punta en ``tests/integration/test_companion_pilot.py``.
"""

from __future__ import annotations

import pytest

from nexus_api.companion.tools.support import (
    CHECKED_MAX,
    SupportRefused,
    build_support_draft,
    load_capabilities,
    normalise_topic,
)

pytestmark = pytest.mark.unit

CHECKED = ("Clientes del partner", "Qué existe y qué no en Auphere")


def _doc():
    return load_capabilities(force=True)


def _draft(kind: str = "support_help", **args):
    return build_support_draft(
        kind,
        {"topic": "connector.shopify", "need": "Sincronizar pedidos", **args},
        checked=CHECKED,
        document=_doc(),
        client_ref=None,
    )


def test_a_help_ticket_carries_the_file_and_a_stable_expectation() -> None:
    draft = _draft()
    assert draft.category == "help"
    assert draft.topic == "connector.shopify"
    assert draft.sla == "next_business_day"
    assert draft.checked == CHECKED
    preview = draft.as_preview()
    assert set(preview) == {
        "category",
        "topic",
        "client_ref",
        "need",
        "checked",
        "alternative",
        "bridge",
    }
    # El cuerpo que se aplica NO lleva ``sla``: la expectativa la decide el
    # motor al abrir, no el llamante. Si viajara, el modelo prometería
    # plazos que Auphere no ha dado.
    assert "sla" not in draft.as_body()


def test_without_a_single_read_there_is_no_ticket() -> None:
    """§25.1: un ticket sin expediente es lo que este mecanismo existe para
    evitar. Y el motivo tiene que decirle al modelo qué hacer."""
    with pytest.raises(SupportRefused) as exc:
        build_support_draft(
            "support_help",
            {"topic": "connector.shopify", "need": "x"},
            checked=(),
            document=_doc(),
            client_ref=None,
        )
    assert exc.value.error.code == "no_evidence"
    assert "lee" in exc.value.error.message.lower() or "mira" in exc.value.error.message.lower()


def test_an_out_of_scope_capability_is_refused_with_its_reason() -> None:
    """§5.2: ``out_of_scope`` autoriza a decir que no está **y por qué**, y
    NO a abrir un ticket de capacidad. Pedir como funcionalidad algo que se
    decidió no hacer llena la cola de ruido."""
    with pytest.raises(SupportRefused) as exc:
        _draft(kind="support_capability", topic="channel.tiktok")
    assert exc.value.error.code == "out_of_scope"
    # El motivo del documento viaja al modelo para que lo diga en voz alta.
    assert "consola" in exc.value.error.message.lower()


def test_an_available_capability_is_refused_as_already_there() -> None:
    with pytest.raises(SupportRefused) as exc:
        _draft(kind="support_capability", topic="connector.whatsapp_meta")
    assert exc.value.error.code == "already_available"


def test_out_of_scope_still_accepts_an_incident() -> None:
    """Una incidencia sobre algo fuera de alcance sigue siendo una
    incidencia. ``help`` nunca se bloquea por el documento."""
    draft = _draft(topic="channel.tiktok")
    assert draft.category == "help"
    assert draft.topic == "channel.tiktok"


def test_a_planned_or_absent_capability_does_open_a_request() -> None:
    for topic in ("connector.stripe", "connector.shopify", "capability.custom_reports"):
        draft = _draft(kind="support_capability", topic=topic)
        assert draft.category == "capability"
        # Una petición de hoja de ruta no tiene reloj.
        assert draft.sla == "best_effort"


def test_a_bridge_without_a_description_is_refused() -> None:
    """§25.4: el puente se etiqueta Y el ticket se abre igual — pero un
    puente que no se puede evaluar no se puede etiquetar."""
    with pytest.raises(SupportRefused) as exc:
        _draft(bridge=True)
    assert exc.value.error.code == "bad_arguments"

    draft = _draft(bridge=True, alternative="Clave de API y un webhook; sin catálogo en vivo.")
    assert draft.bridge is True
    assert draft.alternative


def test_an_empty_need_is_refused() -> None:
    with pytest.raises(SupportRefused) as exc:
        _draft(need="   ")
    assert exc.value.error.code == "bad_arguments"


def test_the_file_is_deduplicated_and_capped() -> None:
    """El expediente viaja a la tarjeta y al correo de soporte: repetido o
    infinito deja de ser legible, que es lo único que lo hace útil."""
    draft = build_support_draft(
        "support_help",
        {"topic": "quota.clients", "need": "subir la cuota"},
        checked=("A", "A", "B", *[f"L{i}" for i in range(30)]),
        document=_doc(),
        client_ref=None,
    )
    assert len(draft.checked) == CHECKED_MAX
    assert draft.checked[:3] == ("A", "B", "L0")
    # ``quota.*`` es de las familias donde hay trabajo parado ahora mismo.
    assert draft.sla == "business_hours"


def test_the_topic_is_normalised_and_never_refused() -> None:
    draft = _draft(topic="Connector.SHOPIFY")
    assert draft.topic == "connector.shopify"
    assert normalise_topic("x" * 200).startswith("other.")
    assert len(normalise_topic("x" * 200)) <= 60
