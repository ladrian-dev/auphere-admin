"""La audiencia del agente pasa a cada canal — spec 047, T116 (requisitos 55.1 y
32.10).

Para cada número que no está desconectado, con las políticas del agente que lo
atiende (el suyo o, si no tiene, el agente por defecto): las de su versión activa
o, sin ella, las de su última versión:

- ``admin_access.admin_only`` con números: «Solo mi equipo», con esos números de
  prueba (los que pueden coincidir con un remitente, en E.164 y sin duplicados).
  Sin ninguno utilizable, «Solo mi equipo» sin números: no responde a nadie,
  igual que antes;
- sin ``admin_only``: «A todos», sin excepciones (antes no existían);
- un agente sin publicar también: el número responde como respondía al publicarse
  (sin cambiar lo que responde), no «Sin configurar»; ese estado queda para los
  números que se conecten a partir de ahora (32.9).

Solo toca los canales en ``unset``: volver a correrla no pisa lo que una persona
ya eligió. Los permisos del equipo (``admins[]``) ya pasaron a ``team_access`` en
la 0189 y siguen en el agente (32.10). Las políticas del agente no se tocan: la API
de partners las sigue leyendo y escribiendo.

Revision ID: 0192_audience_to_channels
Revises: 0191_channel_config
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa

from alembic import op

revision: str = "0192_audience_to_channels"
down_revision: str | Sequence[str] | None = "0191_channel_config"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_E164 = re.compile(r"^\+[1-9]\d{6,14}$")


def numbers_of(policies: dict[str, Any] | None) -> list[str] | None:
    """Los números de prueba de un agente de antes, o ``None`` si respondía a
    todos. Misma regla que ``core.admin_gate.usable_admin_phones`` (7 cifras o
    más) y que ``to_e164``."""
    access = (policies or {}).get("admin_access")
    if not (isinstance(access, dict) and access.get("admin_only")):
        return None
    out: list[str] = []
    for raw in access.get("admin_phones") or []:
        digits = re.sub(r"\D", "", str(raw or ""))
        e164 = f"+{digits}"
        if len(digits) >= 7 and _E164.match(e164) and e164 not in out:
            out.append(e164)
    return out


_CHANNELS = sa.text(
    """
    SELECT c.id, c.tenant_id,
           (SELECT v.policies FROM agent_configs v
             WHERE v.tenant_id = c.tenant_id
               AND v.agent_id = COALESCE(
                     c.agent_id,
                     (SELECT g.id FROM agents g
                       WHERE g.tenant_id = c.tenant_id AND g.lifecycle <> 'archived'
                       ORDER BY g.is_default DESC, g.created_at, g.id LIMIT 1))
             ORDER BY (v.status = 'active') DESC, v.version DESC LIMIT 1) AS policies
      FROM channels c
     WHERE c.status <> 'disconnected' AND c.audience_mode = 'unset'
       AND c.provider <> 'qa_playground'
    """
)


def upgrade() -> None:
    bind = op.get_bind()
    # La migración corre como dueña de las tablas: la RLS no la filtra.
    for channel_id, tenant_id, policies in bind.execute(_CHANNELS).all():
        numbers = numbers_of(policies)
        mode = "everyone" if numbers is None else "team_only"
        bind.execute(
            sa.text("UPDATE channels SET audience_mode = :m WHERE id = :c"),
            {"m": mode, "c": channel_id},
        )
        for phone in numbers or []:
            bind.execute(
                sa.text(
                    "INSERT INTO channel_audience_numbers (tenant_id, channel_id, kind, phone_e164) "
                    "VALUES (:t, :c, 'test', :p) ON CONFLICT DO NOTHING"
                ),
                {"t": tenant_id, "c": channel_id, "p": phone},
            )


def downgrade() -> None:
    op.execute("DELETE FROM channel_audience_numbers")
    op.execute("UPDATE channels SET audience_mode = 'unset'")
