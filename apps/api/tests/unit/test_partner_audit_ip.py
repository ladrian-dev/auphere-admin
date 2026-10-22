"""La pestaña de auditoría del partner no puede caer por la IP.

``embed_audit_log.ip`` es ``INET`` y asyncpg lo devuelve como
``ipaddress.IPv4Address`` (o ``IPv6Address``), no como texto. El esquema de
salida lo declaraba ``str``: en cuanto el partner tuvo una sola fila con IP,
``GET /admin/partners/{id}/audit`` respondió 500 (producción, 2026-10-22,
``Input should be a valid string … IPv4Address('10.40.7.158')``).
"""

from __future__ import annotations

import ipaddress
import uuid
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from nexus_api.schemas.partner import EmbedAuditEntryOut


def _row(ip: object) -> SimpleNamespace:
    return SimpleNamespace(
        id=1,
        partner_id=uuid.uuid4(),
        api_key_id=None,
        tenant_id=None,
        event="session.minted",
        payload={},
        ip=ip,
        origin=None,
        jti=None,
        created_at=datetime(2026, 10, 22, tzinfo=UTC),
    )


@pytest.mark.parametrize(
    ("ip", "expected"),
    [
        (ipaddress.IPv4Address("10.40.7.158"), "10.40.7.158"),
        (ipaddress.IPv6Address("2a05:d01c::1"), "2a05:d01c::1"),
        (ipaddress.IPv4Interface("10.40.7.0/24"), "10.40.7.0/24"),
        ("10.40.7.158", "10.40.7.158"),
        (None, None),
    ],
)
def test_la_ip_sale_como_texto_venga_como_venga(ip: object, expected: str | None) -> None:
    assert EmbedAuditEntryOut.model_validate(_row(ip)).ip == expected
