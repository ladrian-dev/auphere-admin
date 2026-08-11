"""El multimedia también se factura (arrastre de Fase 2, WP-19).

Test de CABLEADO, no de lógica. El ``MediaProcessor`` llama a LiteLLM por
su cuenta en vez de pasar por ``LiteLLMProvider``, así que se saltaba el
único punto donde se medía el consumo: una imagen quemaba tokens de Sonnet
y una nota de voz minutos de Whisper, y ninguno de los dos aparecía en
``usage_records``. El fallo era **silencioso** — no había excepción, ni
log, ni fila de menos que alguien echase en falta; solo un margen que
salía mejor de lo que era.

Por eso estos tests miran el buffer del turno y no el transcript ni el
resumen: lo que hay que fijar es que el hecho contable se emite, y que
sigue emitiéndose el día que alguien reordene el cuerpo de la función.

Los controles negativos son la mitad del valor: sin turno abierto no se
mide nada (evals y scripts usan el mismo procesador y no pueden ensuciar
la facturación) y sin duración en la respuesta no se inventa una.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest

from nexus_worker.metering import collector
from nexus_worker.multimodal.processor import LiveMediaProcessor, MediaProcessorError

pytestmark = pytest.mark.asyncio


class _FakeTranscription:
    def __init__(self, *, text: str = "hola quiero un turno", duration: Any = 42.0) -> None:
        self.text = text
        if duration is not None:
            self.duration = duration


class _FakeCompletion:
    """Respuesta de visión con la forma que devuelve LiteLLM."""

    def __init__(self, *, text: str = "una foto de un corte de pelo") -> None:
        self.choices = [type("_Choice", (), {"message": type("_Msg", (), {"content": text})()})()]
        self.usage = {"prompt_tokens": 1_500, "completion_tokens": 40}


@pytest.fixture
def litellm_stub(monkeypatch):
    """Sustituye el módulo ``litellm`` que el procesador importa dentro de
    la función. Guarda los kwargs para poder afirmar sobre ellos."""
    import sys
    import types

    calls: dict[str, dict[str, Any]] = {}
    module = types.ModuleType("litellm")

    async def _atranscription(**kwargs):
        calls["transcription"] = kwargs
        return module.transcription_response

    async def _acompletion(**kwargs):
        calls["completion"] = kwargs
        return module.completion_response

    module.atranscription = _atranscription  # type: ignore[attr-defined]
    module.acompletion = _acompletion  # type: ignore[attr-defined]
    module.transcription_response = _FakeTranscription()  # type: ignore[attr-defined]
    module.completion_response = _FakeCompletion()  # type: ignore[attr-defined]
    module.calls = calls  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "litellm", module)
    return module


async def test_a_voice_note_is_metered_in_minutes(litellm_stub) -> None:
    processor = LiveMediaProcessor()
    async with collector.usage_turn(tenant_id=uuid.uuid4(), turn_id=str(uuid.uuid4())):
        text = await processor._transcribe(b"fake-ogg", "audio/ogg")
        events = collector.drain_for_tests()

    assert text == "hola quiero un turno"
    # Whisper se factura por minuto: 42 s son 0,7 min. El medidor tiene que
    # ser ``voice.minutes`` y no un medidor de tokens, porque es el único
    # que ``pricing.py`` resuelve contra ``price_per_minute``.
    assert [e.meter for e in events] == ["voice.minutes"]
    assert events[0].quantity == pytest.approx(0.7)
    assert events[0].model == "openai/whisper-1"
    assert events[0].provider == "openai"


async def test_transcription_asks_for_the_only_format_that_carries_duration(
    litellm_stub,
) -> None:
    """Control del cableado con el proveedor: sin ``verbose_json`` la
    respuesta no trae ``duration`` y la medición desaparece sin ruido."""
    processor = LiveMediaProcessor()
    async with collector.usage_turn(tenant_id=uuid.uuid4(), turn_id=str(uuid.uuid4())):
        await processor._transcribe(b"fake-ogg", "audio/ogg")
        collector.drain_for_tests()

    assert litellm_stub.calls["transcription"]["response_format"] == "verbose_json"


async def test_a_response_without_duration_measures_nothing_rather_than_guessing(
    litellm_stub,
) -> None:
    litellm_stub.transcription_response = _FakeTranscription(duration=None)
    processor = LiveMediaProcessor()
    async with collector.usage_turn(tenant_id=uuid.uuid4(), turn_id=str(uuid.uuid4())):
        text = await processor._transcribe(b"fake-ogg", "audio/ogg")
        events = collector.drain_for_tests()

    # El turno sigue funcionando: la transcripción es lo que el cliente
    # necesita, la medición es lo que necesitamos nosotros.
    assert text == "hola quiero un turno"
    assert events == []


async def test_two_voice_notes_in_one_turn_get_distinct_idempotency_keys(
    litellm_stub,
) -> None:
    """Sin bump de ``call_seq`` las dos comparten clave y el consumidor
    descarta la segunda en su ``ON CONFLICT`` — se cobraría la mitad."""
    processor = LiveMediaProcessor()
    async with collector.usage_turn(tenant_id=uuid.uuid4(), turn_id="turno-1"):
        await processor._transcribe(b"fake-ogg", "audio/ogg")
        await processor._transcribe(b"fake-ogg", "audio/ogg")
        events = collector.drain_for_tests()

    assert len({e.idempotency_key for e in events}) == 2


async def test_vision_tokens_are_metered(litellm_stub) -> None:
    processor = LiveMediaProcessor()
    async with collector.usage_turn(tenant_id=uuid.uuid4(), turn_id=str(uuid.uuid4())):
        summary = await processor._vision(b"fake-jpeg", "image/jpeg")
        events = collector.drain_for_tests()

    assert summary == "una foto de un corte de pelo"
    by_meter = {e.meter: e.quantity for e in events}
    assert by_meter == {"llm.input_tokens": 1_500.0, "llm.output_tokens": 40.0}
    assert {e.model for e in events} == {"anthropic/claude-sonnet-4-6"}


async def test_vision_is_metered_even_when_the_response_is_unreadable(
    litellm_stub,
) -> None:
    """Los tokens se gastaron aunque la respuesta venga malformada. Medir
    después de parsear regalaría justo los turnos que peor van."""

    class _Malformed:
        def __init__(self) -> None:
            self.choices: list[Any] = []
            self.usage = {"prompt_tokens": 900}

    litellm_stub.completion_response = _Malformed()
    processor = LiveMediaProcessor()
    async with collector.usage_turn(tenant_id=uuid.uuid4(), turn_id=str(uuid.uuid4())):
        with pytest.raises(MediaProcessorError):
            await processor._vision(b"fake-jpeg", "image/jpeg")
        events = collector.drain_for_tests()

    assert [e.meter for e in events] == ["llm.input_tokens"]


async def test_outside_a_turn_nothing_is_metered(litellm_stub) -> None:
    """Evals y scripts usan el mismo procesador. Si midieran, meterían
    consumo sin tenant en la facturación de alguien."""
    processor = LiveMediaProcessor()
    await processor._transcribe(b"fake-ogg", "audio/ogg")
    await processor._vision(b"fake-jpeg", "image/jpeg")

    assert collector.drain_for_tests() == []
