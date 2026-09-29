"""Cuántos números vivos quedan en una cuenta de WhatsApp Business (spec 021).

Desuscribir nuestra aplicación es **por cuenta** (WABA), no por número: hacerlo
con otro número vivo bajo la misma cuenta lo dejaría mudo. La spec preguntaba
«¿queda otro vivo en esta cuenta **en este cliente**?», y la premisa —una
cuenta por cliente— es falsa en producción: los números propios de Auphere
(«conectar número propio») comparten cuenta entre clientes. La pregunta tiene
que hacerse a toda la plataforma.

La sesión de la consola está scopeada por tenant y la RLS de ``channels`` no
deja ver las filas ajenas. Esta función lee con ``row_security = off`` y
devuelve **solo un número**: cuántos canales no desvinculados tienen esa
``waba_id`` aparte del que se está soltando. No dice de quién son ni cuáles;
es el mismo patrón que ``resolve_channel_tenant`` (migración 0002).

Revision ID: 0133_waba_live_count
Revises: 0132_number_unique_when_live
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0133_waba_live_count"
down_revision: str | Sequence[str] | None = "0132_number_unique_when_live"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE OR REPLACE FUNCTION count_live_channels_for_waba(
            p_waba_id text,
            p_except_channel uuid
        )
        RETURNS integer
        LANGUAGE plpgsql
        SECURITY DEFINER
        SET row_security = off
        AS $$
        DECLARE
            v_n integer;
        BEGIN
            SELECT count(*) INTO v_n
            FROM channels
            WHERE config->>'waba_id' = p_waba_id
              AND status <> 'disconnected'
              AND id <> p_except_channel;
            RETURN v_n;
        END;
        $$;
        """
    )


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS count_live_channels_for_waba(text, uuid)")
