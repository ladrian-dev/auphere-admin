"""P5 / C5: nativos de caché en OTel y en ``companion.runs``.

Sin ``record_llm_call`` el ratio de caché del canal no ve al Companion.
Sin columnas en la fila, el panel P5 miente. Los dos tienen que fallar
si alguien los quita.
"""

from __future__ import annotations

import inspect

from nexus_worker.runtime.llm import InMemoryProvider, LiteLLMProvider

from nexus_api.api.console import companion as companion_api
from nexus_api.db.models.companion import CompanionRun


def test_companion_runs_has_native_cache_columns() -> None:
    cols = set(CompanionRun.__table__.c.keys())
    assert {"cache_read", "cache_write"} <= cols, cols


def test_finalise_run_writes_the_cache_columns() -> None:
    src = inspect.getsource(companion_api._finalise_run)
    assert "run.cache_read" in src
    assert "run.cache_write" in src
    params = inspect.signature(companion_api._finalise_run).parameters
    assert "cache_read" in params and "cache_write" in params


def test_on_complete_passes_run_level_cache_sums() -> None:
    src = inspect.getsource(companion_api._make_on_complete)
    assert "cache_read=handle.total_cache_read" in src
    assert "cache_write=handle.total_cache_write" in src
    assert "record_companion_turn" in src
    # Por llamada, no al cierre: el ratio de ``llm_tokens_total`` tiene
    # que ser real.
    assert "record_llm_call" not in src


def test_alembic_0093_follows_current_head() -> None:
    import importlib.util
    from pathlib import Path

    rev = (
        Path(__file__).resolve().parents[2] / "alembic" / "versions" / "0093_companion_run_cache.py"
    )
    spec = importlib.util.spec_from_file_location("rev_0093", rev)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    assert mod.revision == "0093_companion_run_cache"
    assert mod.down_revision == "0092_companion_pilot"
    src = rev.read_text()
    assert "cache_read" in src and "cache_write" in src


def test_inmemory_and_litellm_both_call_record_llm_call() -> None:
    """Si el canal registra por llamada, el Companion (y su doble) también."""
    assert "record_llm_call" in inspect.getsource(InMemoryProvider)
    assert "record_llm_call" in inspect.getsource(LiteLLMProvider._record_call)
