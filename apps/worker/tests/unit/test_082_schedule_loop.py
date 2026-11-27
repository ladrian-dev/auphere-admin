"""El bucle de un turno de rutina — spec 082, T015 (requisitos 4.1, 4.6, 4.7 y 5.3).

Sin modelo y sin base: un proveedor y un registro de mentira, para poder probar
lo que de verdad decide el bucle.

Lo que se fija aquí:

- la instrucción del partner viaja como **mensaje de operador**, nunca mezclada
  con lo que devuelven las herramientas (constitución §III);
- el resultado de cada herramienta vuelve al modelo **tal cual**, que es lo que
  separa una herramienta de verdad de una decorativa;
- la última vuelta va **sin herramientas**, para que el modelo tenga que
  escribir en vez de pedir una llamada más;
- una ejecución a la que le faltó una herramienta sale **parcial**, no hecha;
- el turno nunca ofrece una herramienta que no esté en su lista.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from nexus_worker.runtime.llm import LLMResponse, ToolCall
from nexus_worker.runtime.schedule_turn import RoutineTools, Withheld, run_loop

TENANT = uuid.uuid4()


class _Provider:
    """Devuelve las respuestas que se le den, y guarda lo que recibió."""

    def __init__(self, *answers: LLMResponse) -> None:
        self._answers = list(answers)
        self.calls: list[dict[str, Any]] = []

    async def acomplete_with_tools(self, **kwargs: Any) -> LLMResponse:
        self.calls.append(kwargs)
        return self._answers.pop(0) if self._answers else LLMResponse(text="se acabó")


class _Registry:
    def __init__(self, results: dict[str, Any] | None = None) -> None:
        self.results = results or {}
        self.dispatched: list[tuple[str, dict[str, Any]]] = []

    def get_openai_tools(self, whitelist: Any) -> list[dict[str, Any]]:
        return [{"type": "function", "function": {"name": n}} for n in sorted(whitelist)]

    async def dispatch(self, name: str, args: dict[str, Any], *, whitelist: Any) -> Any:
        self.dispatched.append((name, args))
        if name not in set(whitelist):
            raise RuntimeError(f"{name} no está en la lista")
        return self.results.get(name, {"status": "ok", "result": {}})


def _chosen(*names: str, withheld: tuple[Withheld, ...] = ()) -> RoutineTools:
    return RoutineTools(names=tuple(names), withheld=withheld)


async def _run(provider: _Provider, registry: _Registry, chosen: RoutineTools, **over: Any):
    return await run_loop(
        provider=provider,
        model="un-modelo",
        tenant_id=TENANT,
        system="Eres el agente de Muna.",
        instruction="Dime cuántos pedidos entraron ayer.",
        registry=registry,
        chosen=chosen,
        **over,
    )


pytestmark = pytest.mark.asyncio


async def test_an_answer_without_tools_comes_back_as_it_is() -> None:
    provider = _Provider(LLMResponse(text="Ayer entraron 14 pedidos."))
    out = await _run(provider, _Registry(), _chosen("inventory.check_stock"))
    assert out.text == "Ayer entraron 14 pedidos."
    assert out.tools_used == ()
    assert out.partial is False


async def test_the_instruction_travels_as_an_operator_message() -> None:
    """Constitución §III: lo que se lee es dato, la instrucción es instrucción."""
    provider = _Provider(LLMResponse(text="hecho"))
    await _run(provider, _Registry(), _chosen())
    messages = provider.calls[0]["messages"]
    assert messages[0]["role"] == "system"
    assert messages[0]["content"] == "Eres el agente de Muna."
    assert messages[1]["role"] == "user"
    assert "pedidos" in messages[1]["content"]


async def test_the_tool_result_goes_back_to_the_model() -> None:
    provider = _Provider(
        LLMResponse(
            text="",
            tool_calls=(ToolCall(id="1", name="inventory.check_stock", arguments={"sku": "x"}),),
        ),
        LLMResponse(text="Quedan 3 unidades."),
    )
    registry = _Registry({"inventory.check_stock": {"status": "ok", "result": {"units": 3}}})
    out = await _run(provider, registry, _chosen("inventory.check_stock"))

    assert registry.dispatched == [("inventory.check_stock", {"sku": "x"})]
    assert out.text == "Quedan 3 unidades."
    assert out.tools_used == ("inventory.check_stock",)
    # La segunda llamada lleva el resultado de verdad, no un resumen.
    second = provider.calls[1]["messages"]
    assert second[-1]["role"] == "tool"
    assert "3" in second[-1]["content"]


async def test_the_last_round_goes_without_tools() -> None:
    """Si no, el bucle se queda pidiendo herramientas y no escribe nada."""
    asking = LLMResponse(
        text="", tool_calls=(ToolCall(id="1", name="inventory.check_stock", arguments={}),)
    )
    provider = _Provider(asking, asking, LLMResponse(text="Al final, esto."))
    out = await _run(provider, _Registry(), _chosen("inventory.check_stock"), max_iterations=3)
    assert out.text == "Al final, esto."
    assert provider.calls[-1]["tools"] == []
    assert provider.calls[0]["tools"] != []


async def test_a_tool_that_fails_does_not_kill_the_turn() -> None:
    """El error vuelve al modelo como resultado, que es lo que le deja decir qué
    no pudo hacer en vez de callarse."""
    provider = _Provider(
        LLMResponse(
            text="", tool_calls=(ToolCall(id="1", name="inventory.check_stock", arguments={}),)
        ),
        LLMResponse(text="No pude leer el inventario."),
    )

    class _Boom(_Registry):
        async def dispatch(self, name, args, *, whitelist):  # type: ignore[no-untyped-def]
            raise RuntimeError("el proveedor no contestó")

    out = await _run(provider, _Boom(), _chosen("inventory.check_stock"))
    assert out.text == "No pude leer el inventario."
    assert out.partial is True


async def test_a_withheld_tool_makes_the_run_partial() -> None:
    provider = _Provider(LLMResponse(text="Esto es lo que vi."))
    out = await _run(
        provider,
        _Registry(),
        _chosen(
            "inventory.check_stock",
            withheld=(Withheld("inventory.mark_out_of_stock", "needs_approval"),),
        ),
    )
    assert out.partial is True
    assert out.withheld[0].why == "needs_approval"


async def test_a_conversation_tool_left_out_does_not_make_it_partial() -> None:
    """Esas no son de una rutina: su ausencia no deja el trabajo a medias."""
    provider = _Provider(LLMResponse(text="Listo."))
    out = await _run(
        provider,
        _Registry(),
        _chosen(
            "inventory.check_stock",
            withheld=(Withheld("escalate.escalate_to_human", "needs_a_conversation"),),
        ),
    )
    assert out.partial is False


async def test_the_model_never_gets_a_tool_outside_its_list() -> None:
    provider = _Provider(LLMResponse(text="ya"))
    await _run(provider, _Registry(), _chosen("inventory.check_stock"))
    offered = {t["function"]["name"] for t in provider.calls[0]["tools"]}
    assert offered == {"inventory.check_stock"}


async def test_with_no_tools_at_all_it_still_answers() -> None:
    provider = _Provider(LLMResponse(text="Sin herramientas, esto es lo que sé."))
    out = await _run(provider, _Registry(), _chosen())
    assert out.text.startswith("Sin herramientas")
    assert provider.calls[0]["tools"] == []
