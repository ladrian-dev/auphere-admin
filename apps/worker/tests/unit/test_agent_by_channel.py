"""Spec 030 T091 — el cargador y la promoción con varios agentes por cliente.

- La caché va por ``(tenant, agente)``: dos agentes del mismo cliente nunca
  comparten entrada (garantías 2 y 4 de agent-isolation); ``agent_id = None``
  es el agente principal.
- Invalidar un tenant borra todos sus agentes (lo que publican hoy todos los
  sitios); invalidar ``tenant:agente`` borra ese agente y la entrada del
  principal, que puede ser él.
- ``prime`` (las evaluaciones fijan una versión) vale para el agente y para el
  principal, porque el pipeline de evaluación no siempre nombra agente.

La resolución del número a su agente en el despachador la prueba
``apps/api/tests/integration/test_dispatcher_agent_by_channel.py`` (necesita la base).
"""

from __future__ import annotations

import asyncio
import uuid

import pytest

from nexus_worker.runtime import promote_subscriber
from nexus_worker.runtime.agent_loader import AgentBundle, AgentLoader

pytestmark = [pytest.mark.unit]

T = uuid.uuid4()
A, B = uuid.uuid4(), uuid.uuid4()


def _bundle(agent: uuid.UUID | None, prompt: str) -> AgentBundle:
    return AgentBundle(
        tenant_id=T,
        agent_id=agent,
        version=1,
        version_id=uuid.uuid4(),
        system_prompt=prompt,
        tools=frozenset(),
    )


@pytest.fixture
def loader(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[AgentLoader, list[tuple[uuid.UUID, uuid.UUID | None]]]:
    fetched: list[tuple[uuid.UUID, uuid.UUID | None]] = []
    ldr = AgentLoader()

    async def _fetch(tenant_id: uuid.UUID, agent_id: uuid.UUID | None = None) -> AgentBundle:
        fetched.append((tenant_id, agent_id))
        return _bundle(agent_id or A, f"prompt of {agent_id or 'principal'}")

    monkeypatch.setattr(ldr, "_fetch", _fetch)
    return ldr, fetched


async def test_two_agents_of_one_client_never_share_an_entry(loader) -> None:
    ldr, fetched = loader
    a = await ldr.load(T, agent_id=A)
    b = await ldr.load(T, agent_id=B)
    assert a.system_prompt != b.system_prompt
    assert (await ldr.load(T, agent_id=B)) is b
    assert fetched == [(T, A), (T, B)]
    principal = await ldr.load(T)
    assert principal.agent_id == A
    assert fetched[-1] == (T, None)


async def test_invalidating_the_tenant_drops_all_its_agents(loader) -> None:
    ldr, _fetched = loader
    await ldr.load(T, agent_id=A)
    await ldr.load(T, agent_id=B)
    await ldr.load(T)
    await ldr.invalidate(T)
    assert ldr.cache_size() == 0


async def test_invalidating_one_agent_keeps_the_other(loader) -> None:
    ldr, fetched = loader
    await ldr.load(T, agent_id=A)
    await ldr.load(T, agent_id=B)
    await ldr.load(T)
    await ldr.invalidate(T, agent_id=B)
    # B's entry and the principal's (which might be B) go; A's stays.
    assert ldr.cache_size() == 1
    await ldr.load(T, agent_id=A)
    assert fetched.count((T, A)) == 1


async def test_a_primed_version_answers_for_its_agent_and_the_principal(loader) -> None:
    ldr, fetched = loader
    pinned = _bundle(B, "staged candidate")
    ldr.prime(pinned)
    assert (await ldr.load(T, agent_id=B)) is pinned
    assert (await ldr.load(T)) is pinned
    assert fetched == []


async def test_the_promotion_message_names_a_tenant_or_one_agent() -> None:
    calls: list[tuple[uuid.UUID, uuid.UUID | None]] = []

    class _Loader:
        async def invalidate(self, tenant_id: uuid.UUID, agent_id: uuid.UUID | None = None) -> None:
            calls.append((tenant_id, agent_id))

    class _PubSub:
        def __init__(self) -> None:
            self.queue = [f"{T}", f"{T}:{B}", "not-a-uuid", f"{T}:also-bad"]

        async def subscribe(self, channel: str) -> None:
            pass

        async def get_message(self, **_kw: object) -> dict[str, str] | None:
            if self.queue:
                return {"data": self.queue.pop(0)}
            stop.set()
            return None

        async def unsubscribe(self, channel: str) -> None:
            pass

        async def aclose(self) -> None:
            pass

    class _Redis:
        def pubsub(self) -> _PubSub:
            return _PubSub()

    stop = asyncio.Event()
    await promote_subscriber.run_promote_subscriber(_Redis(), _Loader(), stop=stop)  # type: ignore[arg-type]
    assert calls == [(T, None), (T, B)]
