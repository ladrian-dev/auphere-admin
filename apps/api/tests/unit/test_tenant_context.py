import uuid

import pytest

from nexus_api.core.errors import IsolationViolation
from nexus_api.core.tenant_context import (
    get_current_tenant,
    require_current_tenant,
    tenant_context,
)


def test_get_current_tenant_is_none_outside_context():
    assert get_current_tenant() is None


def test_require_current_tenant_raises_when_unset():
    with pytest.raises(IsolationViolation):
        require_current_tenant()


def test_tenant_context_sets_and_resets():
    tid = uuid.uuid4()
    with tenant_context(tid):
        assert get_current_tenant() == tid
        assert require_current_tenant() == tid
    assert get_current_tenant() is None


def test_tenant_context_nested_restores_outer():
    a = uuid.uuid4()
    b = uuid.uuid4()
    with tenant_context(a):
        with tenant_context(b):
            assert get_current_tenant() == b
        assert get_current_tenant() == a
    assert get_current_tenant() is None


def test_tenant_context_resets_on_exception():
    tid = uuid.uuid4()
    with pytest.raises(RuntimeError), tenant_context(tid):
        raise RuntimeError("boom")
    assert get_current_tenant() is None
