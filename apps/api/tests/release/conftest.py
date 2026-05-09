"""Shared fixtures for the release smoke suite.

These tests are skipped unless ``NEXUS_RELEASE_API_URL`` is set in the
environment, which keeps them out of CI by default. They are meant to
be run by Lee from a laptop after a deploy:

    NEXUS_RELEASE_API_URL=https://api.auphere.com \\
    NEXUS_RELEASE_ADMIN_TOKEN=<bearer> \\
    NEXUS_RELEASE_CANARY_SLUG=auphere-canary \\
    uv run pytest apps/api/tests/release -v

Block J adds a wizard-driven onboarding test; for now Block I covers
``/health``, ``/admin/tenants``, ``/admin/tenants/:id/isolation/metrics``
and a YCloud webhook ack.
"""

from __future__ import annotations

import os

import pytest


def _release_url() -> str | None:
    return os.environ.get("NEXUS_RELEASE_API_URL")


@pytest.fixture(scope="session")
def release_api_url() -> str:
    url = _release_url()
    if not url:
        pytest.skip("set NEXUS_RELEASE_API_URL to run release smoke tests")
    return url.rstrip("/")


@pytest.fixture(scope="session")
def release_admin_token() -> str:
    token = os.environ.get("NEXUS_RELEASE_ADMIN_TOKEN")
    if not token:
        pytest.skip("set NEXUS_RELEASE_ADMIN_TOKEN to run release smoke tests")
    return token


@pytest.fixture(scope="session")
def canary_slug() -> str:
    return os.environ.get("NEXUS_RELEASE_CANARY_SLUG", "auphere-canary")
