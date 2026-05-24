"""Unit tests for ``_build_operator_briefing`` — the helper that formats
the operator-intervention context the dispatcher prepends to
``user_message`` on the first turn after the operator resumes the agent.

The helper is pure (no IO) so the tests stay unit-level. The
integration with the dispatcher's tenant-scoped session + DB read of
``actor_kind='operator'`` messages is exercised by the API integration
test suite (``tests/integration/test_dispatcher_tenant_lifecycle.py``).
"""

from __future__ import annotations

from nexus_worker.runtime.dispatcher import _build_operator_briefing


class TestBuildOperatorBriefing:
    def test_includes_all_fields_when_present(self) -> None:
        out = _build_operator_briefing(
            reason="queja",
            notes="cliente enojado",
            started_at="2026-05-25T10:00:00+00:00",
            operator_id="luis1234",
            operator_messages=["mensaje uno", "mensaje dos"],
        )
        assert "[Contexto interno" in out
        assert "[Fin del contexto interno]" in out
        assert "Razón: queja" in out
        assert "Notas: cliente enojado" in out
        assert "Pausa iniciada: 2026-05-25T10:00:00+00:00" in out
        assert "Operador: luis1234" in out
        assert "1. mensaje uno" in out
        assert "2. mensaje dos" in out

    def test_omits_missing_fields(self) -> None:
        out = _build_operator_briefing(
            reason=None,
            notes=None,
            started_at=None,
            operator_id=None,
            operator_messages=[],
        )
        assert "[Contexto interno" in out
        assert "Razón:" not in out
        assert "Notas:" not in out
        assert "Pausa iniciada:" not in out
        assert "Operador:" not in out
        # Explicit sentinel when no operator messages — keeps the LLM
        # from inferring a long silent intervention.
        assert "El operador no envió mensajes durante la pausa" in out

    def test_only_reason_set(self) -> None:
        out = _build_operator_briefing(
            reason="manual",
            notes=None,
            started_at=None,
            operator_id=None,
            operator_messages=[],
        )
        assert "Razón: manual" in out
        assert "Notas:" not in out

    def test_long_message_list_preserves_order(self) -> None:
        msgs = [f"m{i}" for i in range(5)]
        out = _build_operator_briefing(
            reason=None,
            notes=None,
            started_at=None,
            operator_id=None,
            operator_messages=msgs,
        )
        for i, m in enumerate(msgs, start=1):
            assert f"{i}. {m}" in out
        # And the order is preserved (m0 appears before m4).
        assert out.index("1. m0") < out.index("5. m4")
