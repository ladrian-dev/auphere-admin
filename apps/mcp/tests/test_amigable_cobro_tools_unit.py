"""Unit tests for the Amigable Cobro (billing.*) MCP tools.

DB-free: tools use the ``set_test_client`` hook to bypass credential
resolution. Each test injects a FakeAmigableClient returning canned
accounts. The ``get_my_debt`` happy path (resolving the current
customer's phone from a DB row) is covered by the QA Playground
integration; here we assert its security guard (no customer in context
⇒ no data) which short-circuits before any DB access.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
from nexus_api.core.tenant_context import customer_context, tenant_context

from nexus_mcp.servers.amigable_cobro.client import AmigableCobroClient
from nexus_mcp.servers.amigable_cobro.schemas import (
    GetDebtorByPhoneInput,
    GetMyDebtInput,
    ListOverdueInput,
)
from nexus_mcp.servers.amigable_cobro.tools import (
    AMIGABLE_COBRO_TOOLS,
    GetDebtorByPhone,
    GetMyDebt,
    ListOverdue,
    _phone_matches,
    _to_record,
    set_test_client,
)

pytestmark = [pytest.mark.unit]


# ── fake client ──────────────────────────────────────────────────────────


class FakeAmigableClient(AmigableCobroClient):
    """Bypasses real HTTP. Serves ``pages`` of canned accounts."""

    def __init__(self, pages: list[list[dict[str, Any]]]) -> None:
        # Skip the parent __init__ (no credential validation for a fake).
        self.pages = pages
        self.calls: list[int] = []

    async def list_cuentas(  # type: ignore[override]
        self,
        *,
        page: int = 1,
        start_date: str | None = None,
        end_date: str | None = None,
    ) -> tuple[list[dict[str, Any]], dict[str, Any]]:
        self.calls.append(page)
        last = len(self.pages)
        records = self.pages[page - 1] if 1 <= page <= last else []
        return records, {
            "total": sum(len(p) for p in self.pages),
            "current_page": page,
            "last_page": last,
        }


def _account(**over: Any) -> dict[str, Any]:
    base = {
        "id": 1,
        "client_name": "Juan Pérez",
        "client_phone": "+584241234567",
        "client_document": "V-12345678",
        "total_amount": 100.0,
        "paid_amount": 40.0,
        "status": "PENDING",
        "due_date": None,
        "created_at": "2026-06-01T00:00:00Z",
    }
    base.update(over)
    return base


# ── fixtures ─────────────────────────────────────────────────────────────


_TENANT = uuid.UUID("00000000-0000-0000-0000-000000000001")


@pytest.fixture
def tenant_ctx() -> Any:
    with tenant_context(_TENANT):
        yield _TENANT


def _use(pages: list[list[dict[str, Any]]]) -> FakeAmigableClient:
    c = FakeAmigableClient(pages)
    set_test_client(c)
    return c


@pytest.fixture(autouse=True)
def _reset_client() -> Any:
    yield
    set_test_client(None)


# ── catalog / contract ───────────────────────────────────────────────────


def test_catalog_has_three_tools() -> None:
    names = {cls.name for cls in AMIGABLE_COBRO_TOOLS}
    assert names == {
        "billing.get_my_debt",
        "billing.get_debtor_by_phone",
        "billing.list_overdue",
    }


def test_tools_are_read_only_no_side_effects() -> None:
    # Empty side_effects is what lets the QA Playground (dry_run) actually
    # execute these reads instead of intercepting them.
    for cls in AMIGABLE_COBRO_TOOLS:
        assert cls.side_effects == (), cls.name


@pytest.mark.parametrize(
    ("a", "b", "expected"),
    [
        ("+584241234567", "04241234567", True),
        ("+584241234567", "424-123-4567", True),
        ("+584241234567", "+584249999999", False),
        ("123", "123", False),  # too short
        (None, "+584241234567", False),
    ],
)
def test_phone_matches(a: str | None, b: str | None, expected: bool) -> None:
    assert _phone_matches(a, b) is expected


def test_to_record_computes_balance() -> None:
    rec = _to_record(_account(total_amount=100, paid_amount=30))
    assert rec.balance == 70.0


# ── list_overdue ─────────────────────────────────────────────────────────


async def test_list_overdue_only_with_balance(tenant_ctx: Any) -> None:
    _use([[_account(id=1, paid_amount=40), _account(id=2, paid_amount=100)]])
    out = await ListOverdue().run(ListOverdueInput(page=1, only_with_balance=True))
    ids = {d.id for d in out.items}
    assert ids == {1}  # id=2 fully paid (balance 0) is filtered out


async def test_list_overdue_status_filter(tenant_ctx: Any) -> None:
    _use([[_account(id=1, status="PENDING"), _account(id=2, status="PAID", paid_amount=10)]])
    out = await ListOverdue().run(ListOverdueInput(page=1, only_with_balance=False, status="paid"))
    assert {d.id for d in out.items} == {2}


# ── get_debtor_by_phone (admin tool) ─────────────────────────────────────


async def test_get_debtor_by_phone_matches(tenant_ctx: Any) -> None:
    _use(
        [
            [
                _account(id=1, client_phone="+584241234567"),
                _account(id=2, client_phone="+584249999999"),
            ]
        ]
    )
    out = await GetDebtorByPhone().run(GetDebtorByPhoneInput(phone="0424-123-4567"))
    assert out.found is True
    assert {d.id for d in out.debts} == {1}
    assert out.total_balance == 60.0


async def test_get_debtor_by_phone_no_match(tenant_ctx: Any) -> None:
    _use([[_account(id=1, client_phone="+584241234567")]])
    out = await GetDebtorByPhone().run(GetDebtorByPhoneInput(phone="+584240000000"))
    assert out.found is False
    assert out.debts == []


# ── get_my_debt (debtor tool) — security guard ───────────────────────────


async def test_get_my_debt_requires_customer_context(tenant_ctx: Any) -> None:
    # No customer in the turn context ⇒ cannot resolve identity ⇒ empty,
    # and it never reaches the API or any other customer's data.
    _use([[_account(id=1)]])
    with customer_context(None):
        out = await GetMyDebt().run(GetMyDebtInput())
    assert out.found is False
    assert out.debts == []
    assert out.total_balance == 0.0
