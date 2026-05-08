"""Extra: repositories must NOT accept a tenant_id parameter.

Architecture rule from CLAUDE.md:
  "Repos and tools never accept tenant_id from the caller — they pull it
  from the request context."

This test enforces the contract by introspection: every repository method
should derive tenant_id only from the contextvar / SET LOCAL, never from a
function argument.
"""

from __future__ import annotations

import inspect

import pytest

from nexus_api import repositories

pytestmark = [pytest.mark.isolation]


# TenantRepository is the one repository that crosses tenants by design — the
# admin endpoints list/get tenants. Every OTHER repository is tenant-scoped and
# must derive tenant_id from the contextvar / SET LOCAL.
GLOBAL_REPOS = {"TenantRepository"}


def test_no_scoped_repo_takes_tenant_id_argument():
    offenders: list[str] = []
    for repo_class_name in repositories.__all__:
        if repo_class_name in GLOBAL_REPOS:
            continue
        repo_class = getattr(repositories, repo_class_name)
        for method_name, method in inspect.getmembers(repo_class, predicate=inspect.isfunction):
            if method_name.startswith("_"):
                continue
            sig = inspect.signature(method)
            for param_name in sig.parameters:
                if param_name == "tenant_id":
                    offenders.append(f"{repo_class_name}.{method_name}")
    assert offenders == [], (
        "Tenant-scoped repository methods must derive tenant_id from context, "
        f"not args. Offenders: {offenders}"
    )
