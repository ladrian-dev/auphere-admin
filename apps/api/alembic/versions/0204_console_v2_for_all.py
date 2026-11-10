"""La consola nueva para todos los partners (Andrés, 2026-10-29).

La spec 047 la activaba partner a partner desde el panel (research D38, 0175).
Ya no: será la consola de todos, y lo que el panel enciende o apaga por partner
son los módulos (spec 032). Para cada partner que seguía en la consola de antes,
esta migración hace lo mismo que hacía activarla (``services/console_v2.py``,
``activate``):

- a los números de sus clientes que todavía no tienen audiencia en el canal
  (``unset``) les escribe la de antes, con la regla de la 0192: «Solo mi equipo»
  con los números de prueba del agente, o «A todos». Sin esto, un número que hoy
  responde solo al equipo empezaría a responder a cualquiera;
- enciende la consola nueva (``console_v2_enabled_at``) con quién lo hizo, y deja
  la fila de auditoría de plataforma de siempre (``partner.console_v2_enabled``).

A un partner que ya estaba en la consola nueva no le toca nada: sus números
«Sin configurar» los eligió una persona (32.9). Los partners que nazcan después
ya nacen con ella (``services/console_v2.born_on_new_console``).

La bajada no devuelve a nadie a la consola de antes: no se sabe quién estaba en
cuál, y la consola de antes deja de ser una opción.

Revision ID: 0204_console_v2_for_all
Revises: 0203_audit_vocab_connectors
"""

from __future__ import annotations

import re
from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa

from alembic import op

revision: str = "0204_console_v2_for_all"
down_revision: str | Sequence[str] | None = "0203_audit_vocab_connectors"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ACTOR = "auphere:consola-nueva-para-todos"

_E164 = re.compile(r"^\+[1-9]\d{6,14}$")


def numbers_of(policies: dict[str, Any] | None) -> list[str] | None:
    """Los números de prueba de un agente de antes, o ``None`` si respondía a
    todos. La misma regla que la 0192 y que ``core.admin_gate``."""
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


# Los números sin audiencia de los clientes de partners que aún no estaban en la
# consola nueva, con las políticas del agente que los atiende (o del de por
# defecto): las de su versión activa o, sin ella, las de la última.
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
       AND EXISTS (SELECT 1 FROM partner_tenants pt
                     JOIN partners p ON p.id = pt.partner_id
                    WHERE pt.tenant_id = c.tenant_id AND p.console_v2_enabled_at IS NULL)
    """
)

_ENABLE = sa.text(
    """
    WITH turned AS (
        UPDATE partners
           SET console_v2_enabled_at = now(), console_v2_enabled_by = :actor
         WHERE console_v2_enabled_at IS NULL
     RETURNING id
    )
    INSERT INTO audit_log (id, tenant_id, actor, action, target, before_json, after_json)
    SELECT gen_random_uuid(), NULL, :actor, 'partner.console_v2_enabled', 'partner:' || id::text,
           '{"console_version": "v1"}'::jsonb,
           '{"console_version": "v2", "reason": "La consola nueva es la de todos los partners"}'::jsonb
      FROM turned
    """
)


def upgrade() -> None:
    bind = op.get_bind()
    # Corre como dueña de las tablas: la RLS no la filtra.
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
    bind.execute(_ENABLE, {"actor": ACTOR})


def downgrade() -> None:
    # Nada que deshacer con sentido: la consola de antes deja de ser una opción.
    pass
