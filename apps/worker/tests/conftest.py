"""Worker unit fixtures."""

from __future__ import annotations

import json
import uuid

import pytest
from nexus_api.core.llm_proxy import bind_llm_proxy_partner, reset_llm_proxy_partner

TEST_PROXY_PARTNER = uuid.UUID("00000000-0000-0000-0000-00000000a001")
TEST_PROXY_BASE = "http://litellm.test.invalid"
TEST_PROXY_KEY = "sk-vk-test-a001"


@pytest.fixture
def litellm_proxy_partner(monkeypatch: pytest.MonkeyPatch) -> uuid.UUID:
    monkeypatch.setenv("LITELLM_PROXY_API_BASE", TEST_PROXY_BASE)
    monkeypatch.setenv(
        "LITELLM_PROXY_VIRTUAL_KEYS",
        json.dumps({str(TEST_PROXY_PARTNER): TEST_PROXY_KEY}),
    )
    token = bind_llm_proxy_partner(TEST_PROXY_PARTNER)
    try:
        yield TEST_PROXY_PARTNER
    finally:
        reset_llm_proxy_partner(token)
