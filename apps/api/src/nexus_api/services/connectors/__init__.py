"""Connectors module — unified integrations layer (Block L / ADR-011).

Submodules:

- ``seed_loader``    — load + validate YAML seeds.
- ``seed_runner``    — apply seeds to the database (idempotent).
- ``consent_token``  — HMAC-signed single-use tokens for the consent flow.
- ``composio_client`` — wrapper around the Composio Python SDK v3.
- ``gating``         — resolve always/blocked/needs_approval per (tenant, tool).
- ``tools_sync``     — sync tools/list from a connector into tool_catalog.
- ``service``        — orchestration entry points used by API endpoints.

See [[architecture/connectors]] for the spec and
[[architecture/connectors-testing]] for the test plan.
"""

from __future__ import annotations
