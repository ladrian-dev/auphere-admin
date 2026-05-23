"""Unit tests for the Memory tool path validator.

The validator is pure (no DB, no IO), so it lives with worker unit tests
even though the rest of the memory backend needs a Postgres + RLS round
trip (integration suite in apps/api/tests/).
"""

from __future__ import annotations

import uuid

import pytest

from nexus_worker.memory.path_validator import (
    PathValidationError,
    validate_and_resolve_path,
)

CUSTOMER_A = uuid.uuid4()
CUSTOMER_B = uuid.uuid4()


class TestPrefixRules:
    def test_root_listing_is_allowed(self) -> None:
        assert validate_and_resolve_path("/memories", customer_id=CUSTOMER_A) == "/memories"

    def test_root_with_trailing_slash_normalised(self) -> None:
        assert validate_and_resolve_path("/memories/", customer_id=CUSTOMER_A) == "/memories"

    def test_empty_path_rejected(self) -> None:
        with pytest.raises(PathValidationError, match="non-empty"):
            validate_and_resolve_path("", customer_id=CUSTOMER_A)

    @pytest.mark.parametrize(
        "bad",
        [
            "/etc/passwd",
            "memories/foo",  # missing leading slash
            "/foo",
            "/memorias/x",  # close-but-wrong prefix
        ],
    )
    def test_non_memories_prefixes_rejected(self, bad: str) -> None:
        with pytest.raises(PathValidationError, match="must start with /memories/"):
            validate_and_resolve_path(bad, customer_id=CUSTOMER_A)

    def test_tenant_prefix_allowed_without_customer(self) -> None:
        # Tenant-wide memories don't need a customer in scope.
        assert (
            validate_and_resolve_path("/memories/tenant/policies.md", customer_id=None)
            == "/memories/tenant/policies.md"
        )


class TestTraversal:
    @pytest.mark.parametrize(
        "raw",
        [
            "/memories/customer/me/../../etc/passwd",
            "/memories/tenant/../tenant/x",
            "/memories/customer/me/%2e%2e/escape",
            "/memories/customer/me/..\\windows",
            "/memories/./customer/me/x",
        ],
    )
    def test_traversal_blocked(self, raw: str) -> None:
        with pytest.raises(PathValidationError, match="traversal"):
            validate_and_resolve_path(raw, customer_id=CUSTOMER_A)


class TestMeAliasResolution:
    def test_me_resolves_to_current_customer(self) -> None:
        out = validate_and_resolve_path(
            "/memories/customer/me/preferences.md", customer_id=CUSTOMER_A
        )
        assert out == f"/memories/customer/{CUSTOMER_A}/preferences.md"

    def test_me_with_just_prefix_resolves(self) -> None:
        out = validate_and_resolve_path("/memories/customer/me", customer_id=CUSTOMER_A)
        assert out == f"/memories/customer/{CUSTOMER_A}"

    def test_me_without_customer_in_scope_errors(self) -> None:
        with pytest.raises(PathValidationError, match=r"me.*requires a customer"):
            validate_and_resolve_path(
                "/memories/customer/me/preferences.md", customer_id=None
            )


class TestCrossCustomerProbing:
    """Critical: writing an explicit other-customer UUID must read as
    "does not exist" — never as "permission denied" — so the LLM cannot
    enumerate the existence of other customers."""

    def test_other_customer_uuid_reads_as_not_exists(self) -> None:
        with pytest.raises(PathValidationError, match="does not exist"):
            validate_and_resolve_path(
                f"/memories/customer/{CUSTOMER_B}/preferences.md",
                customer_id=CUSTOMER_A,
            )

    def test_own_customer_uuid_passes_through(self) -> None:
        out = validate_and_resolve_path(
            f"/memories/customer/{CUSTOMER_A}/preferences.md", customer_id=CUSTOMER_A
        )
        assert out == f"/memories/customer/{CUSTOMER_A}/preferences.md"

    def test_non_uuid_customer_id_errors_clearly(self) -> None:
        with pytest.raises(PathValidationError, match="UUID"):
            validate_and_resolve_path(
                "/memories/customer/not-a-uuid/x.md", customer_id=CUSTOMER_A
            )

    def test_missing_customer_id_segment_errors(self) -> None:
        with pytest.raises(PathValidationError, match="missing customer identifier"):
            validate_and_resolve_path("/memories/customer/", customer_id=CUSTOMER_A)


class TestNormalisation:
    def test_trailing_slash_stripped(self) -> None:
        out = validate_and_resolve_path(
            "/memories/tenant/policies/", customer_id=None
        )
        assert out == "/memories/tenant/policies"

    def test_no_trailing_slash_preserved(self) -> None:
        out = validate_and_resolve_path("/memories/tenant/x.md", customer_id=None)
        assert out == "/memories/tenant/x.md"
