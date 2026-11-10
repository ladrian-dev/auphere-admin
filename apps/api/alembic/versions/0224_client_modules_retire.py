"""Agentes y Negocio salen de la consola del cliente — spec 056, T003 (requisitos 2.1 y 2.2).

Lo que la 0198 abrió a la persona de un cliente (``agents`` y ``business``) se
retira: el estado de los agentes y la ficha del negocio son del partner.

- Quita ``agents`` y ``business`` de ``client_access.modules`` y firma el cambio
  (``updated_by = 'system:spec_056'``).
- Apaga el acceso que se queda sin ningún módulo: encendido exige al menos uno
  (``services.client_access.set_access``, ``no_modules``).
- Rehace ``ck_client_access_modules`` con ``panel``, ``inbox``, ``reservas`` y
  ``usage``, como la 0198.

El usuario de migraciones es superusuario: el ``FORCE ROW LEVEL SECURITY`` de
``client_access`` no le estorba.

**La bajada no devuelve los módulos quitados ni enciende lo que se apagó**: no
queda constancia de quién los tenía. Solo vuelve a admitir los seis en el CHECK.

Revision ID: 0224_client_modules_retire
Revises: 0223_booking_unbacked_reason
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0224_client_modules_retire"
down_revision: str | Sequence[str] | None = "0223_booking_unbacked_reason"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

ACTOR = "system:spec_056"
_MODULES_BEFORE = "'panel', 'inbox', 'usage', 'reservas', 'agents', 'business'"
_MODULES_AFTER = "'panel', 'inbox', 'usage', 'reservas'"


def _modules(condition: str) -> None:
    op.drop_constraint("ck_client_access_modules", "client_access", type_="check")
    op.create_check_constraint("ck_client_access_modules", "client_access", condition)


def upgrade() -> None:
    op.execute(
        "UPDATE client_access "
        "SET modules = array_remove(array_remove(modules, 'agents'), 'business'), "
        f"updated_at = now(), updated_by = '{ACTOR}' "
        "WHERE modules && ARRAY['agents', 'business']::varchar[]"
    )
    op.execute(
        f"UPDATE client_access SET enabled = false, updated_at = now(), updated_by = '{ACTOR}' "
        "WHERE enabled AND modules = '{}'::varchar[]"
    )
    _modules(f"modules <@ ARRAY[{_MODULES_AFTER}]::varchar[]")


def downgrade() -> None:
    _modules(f"modules <@ ARRAY[{_MODULES_BEFORE}]::varchar[]")
