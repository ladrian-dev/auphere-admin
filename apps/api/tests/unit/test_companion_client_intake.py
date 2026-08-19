"""El alta de cliente pregunta lo que pide la plantilla ANTES de proponer.

Encontrado en la prueba manual de la Ola 2, contra el proveedor real: el alta
se confirmaba y **después** fallaba con
``422 missing placeholder: tenant.address``. Es el peor momento posible para
descubrirlo — la persona ya había dicho que sí a un alta irreversible.

Y el primer intento de arreglo trajo el fallo gemelo: la propuesta pedía
``intake_required`` en bucle porque el mensaje que le llega al modelo llevaba
las **etiquetas** de los campos y no sus **claves**, así que no había forma de
devolverlas. Los dos casos están fijados aquí.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from nexus_api.companion.tools.proposals import IntakeRequired, ProposalBuilder

TEMPLATE = {
    "name": "aesthetic_clinic_v1",
    "display_name": "Clínica estética",
    "version": "1",
    "vertical": "aesthetic_clinic",
    "tools_count": 4,
    "placeholders": [
        {"key": "tenant.address", "label": "Dirección", "required": True, "example": "Av. 1"},
        {"key": "agent.tone", "label": "Tono", "required": False, "example": "cercano"},
    ],
}

BASE_ARGS: dict[str, Any] = {
    "client_ref": "boreal",
    "name": "Clínica Boreal",
    "timezone": "America/Caracas",
    "language": "es",
    "vertical": "aesthetic_clinic_v1",
    "forbidden_behaviour": "No dar precios por WhatsApp",
}


class _Response:
    def __init__(self, payload: Any) -> None:
        self.status_code = 200
        self._payload = payload

    def json(self) -> Any:
        return self._payload

    @property
    def text(self) -> str:
        return json.dumps(self._payload)


def _reader(*, clients: list[dict[str, Any]] | None = None) -> Any:
    async def read(path: str, params: dict[str, Any] | None = None) -> _Response:
        if path == "/console/me":
            return _Response({"quota": {"used_clients": 1, "max_clients": 10}})
        if path == "/console/clients":
            return _Response({"clients": clients or []})
        if path == "/console/seed-templates":
            return _Response([TEMPLATE])
        raise AssertionError(f"lectura inesperada: {path}")

    return read


@pytest.mark.asyncio
async def test_the_template_fields_are_asked_before_proposing() -> None:
    """No se propone un alta que va a fallar al aplicarse."""
    builder = ProposalBuilder(read=_reader())
    with pytest.raises(IntakeRequired) as raised:
        await builder.build("client", dict(BASE_ARGS))

    slots = raised.value.slots
    assert [s["key"] for s in slots] == ["tenant.address"]
    assert slots[0]["label"] == "Dirección"
    assert slots[0]["examples"] == ["Av. 1"]
    assert slots[0]["required"] is True


@pytest.mark.asyncio
async def test_an_optional_placeholder_is_never_asked() -> None:
    """Preguntar un deducible es ruido, y el ruido gasta la disposición de la
    persona a contestar lo que sí importa (§7.1)."""
    builder = ProposalBuilder(read=_reader())
    with pytest.raises(IntakeRequired) as raised:
        await builder.build("client", dict(BASE_ARGS))
    assert "agent.tone" not in {s["key"] for s in raised.value.slots}


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "fields",
    [
        "tenant.address=Av. Principal 45",
        "address=Av. Principal 45",
        "tenant.address=Av. Principal 45\nagent.tone=cercano",
    ],
    ids=["clave-completa", "clave-corta", "con-un-opcional-de-regalo"],
)
async def test_the_answer_is_accepted_in_either_form(fields: str) -> None:
    """El modelo ve ``tenant.address`` en el mensaje de intake y es lo que
    suele devolver, pero también escribe ``address`` a secas. Aceptar las dos
    cuesta una línea y evita el bucle."""
    builder = ProposalBuilder(read=_reader())
    proposal = await builder.build("client", {**BASE_ARGS, "template_fields": fields})
    assert proposal.kind == "client"
    assert proposal.apply_body is not None
    assert proposal.apply_body["placeholders"]["tenant.address"] == "Av. Principal 45"
    # Los cinco fijos siguen viajando con el alta.
    assert proposal.apply_body["placeholders"]["forbidden_behaviour"]


@pytest.mark.asyncio
async def test_a_value_with_an_equals_sign_survives() -> None:
    """Se parte por el PRIMER ``=``: una dirección puede llevar más."""
    builder = ProposalBuilder(read=_reader())
    proposal = await builder.build(
        "client", {**BASE_ARGS, "template_fields": "tenant.address=Calle A=B, 12"}
    )
    assert proposal.apply_body is not None
    assert proposal.apply_body["placeholders"]["tenant.address"] == "Calle A=B, 12"


@pytest.mark.asyncio
async def test_a_vertical_without_a_template_is_not_blocked() -> None:
    """Un alta sin plantilla es válida: no puede bloquearse por no encontrar
    una lista de placeholders que no existe."""
    builder = ProposalBuilder(read=_reader())
    proposal = await builder.build("client", {**BASE_ARGS, "vertical": "peluquería de barrio"})
    assert proposal.apply_body is not None
    assert "seed_template" not in proposal.apply_body
