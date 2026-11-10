"""Lo común de las pruebas unitarias del worker."""

from __future__ import annotations

import uuid
from collections.abc import Iterator

import pytest


@pytest.fixture(autouse=True)
def _agenda_ready_unless_said(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Spec 057 (requisito 4): el manejador lee en cada turno si la agenda del
    cliente está lista. Una prueba unitaria no lee la base: si la hay a mano (la de
    otra suite), la lectura daría «no lista» para un cliente inventado y quitaría
    ``reservas.*`` a pruebas que no tratan de eso. Lista, salvo que la prueba diga
    otra cosa (``test_057_*``)."""
    from nexus_worker.runtime import pipeline

    async def ready(_tenant_id: uuid.UUID) -> bool:
        return True

    monkeypatch.setattr(pipeline, "_load_agenda_ready", ready, raising=False)
    yield
