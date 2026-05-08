"""Garantía 7 — LLM stateless per tenant.

LiteLLM is wired in block C. Block B encodes the contract that no batching
spans tenants. Until LiteLLM lands, this is a structural test asserting that
the planned config (a function returning the kwargs we'll hand to LiteLLM)
never enables cross-tenant batching.

When block C lands, this file gets a runtime test that fires two concurrent
calls with different tenants and asserts two distinct HTTP requests.
"""

from __future__ import annotations

import pytest

pytestmark = [pytest.mark.isolation]


def litellm_kwargs_contract() -> dict:
    """The contract block C must satisfy when initialising LiteLLM.

    Centralised here so any change requires updating both the contract and the
    isolation test in the same PR.
    """
    return {
        "enable_batching": False,
        "group_by": None,
    }


def test_batching_is_disabled():
    cfg = litellm_kwargs_contract()
    assert cfg["enable_batching"] is False


def test_no_global_grouping_key():
    cfg = litellm_kwargs_contract()
    assert cfg["group_by"] is None or cfg["group_by"] == "tenant_id"


def test_contract_is_stable():
    """Lock the keys present so a renaming surfaces here."""
    keys = set(litellm_kwargs_contract())
    assert keys == {"enable_batching", "group_by"}
