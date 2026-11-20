"""Spec 065 (T003; requisitos 1.1, 1.2, 1.3, 1.7, 5.2): la oferta de seis modelos y su puerta.

- La puerta por entorno (research.md §D11): ``respond_enabled_at``, ``respond_enabled_by`` y
  ``respond_enabled_note`` en ``model_profiles``. Un modelo solo se puede elegir para
  responder cuando Auphere lo habilita desde el panel, en cada entorno, con la pasada de la
  batería anotada. Sol, Terra y Luna, que ya se ofrecían, quedan habilitados; los de
  Anthropic, no.
- Claude Opus 5.5 y Claude Sonnet 5.5 entran en el catálogo, copiados de la fila de Claude
  Haiku 5.5 (patrón de la 0221), con sus tarifas y sus pesos por carril (research.md §D1):
  sin pesos, un turno con ellos se mediría pero no se cobraría.
- ``offer_label`` para los tres de Anthropic, con el nombre que enseña la consola.
- Los tres de Anthropic en la lista de cada partner, y los partners nuevos nacen con los
  seis (Luis, 2026-11-19: los seis para todos; Auphere restringe desde la ficha).

Revision ID: 0238_respond_offer_claude_55
Revises: 0237_agent_respond_model
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0238_respond_offer_claude_55"
down_revision: str | Sequence[str] | None = "0237_agent_respond_model"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SOURCE = "https://platform.claude.com/docs/en/about-claude/pricing"
HAIKU = "anthropic/claude-haiku-5-5"

#: Ya se ofrecían antes de esta spec: quedan habilitados en todos los entornos.
OPENAI = ("openai/gpt-5.6-sol", "openai/gpt-5.6-terra", "openai/gpt-5.6-luna")

#: model_id → (nombre, entrada, lectura, escritura 5 min, salida, peso legado,
#: peso entrada, peso lectura, peso salida). Pesos = tarifa por 2,2 entre 10 (0120).
NEW: dict[str, tuple[str, str, str, str, str, str, str, str, str]] = {
    "anthropic/claude-opus-5-5": (
        "Claude Opus 5.5",
        "4.000000",
        "0.200000",
        "5.000000",
        "20.000000",
        "1.840",
        "0.880000",
        "0.044000",
        "4.400000",
    ),
    "anthropic/claude-sonnet-5-5": (
        "Claude Sonnet 5.5",
        "2.000000",
        "0.100000",
        "2.500000",
        "10.000000",
        "0.920",
        "0.440000",
        "0.022000",
        "2.200000",
    ),
}

LABELS = {
    "anthropic/claude-opus-5-5": "Claude Opus 5.5",
    "anthropic/claude-sonnet-5-5": "Claude Sonnet 5.5",
    HAIKU: "Claude Haiku 5.5",
}

SIX = (*OPENAI, *LABELS)


def _seed_function(models: Sequence[str]) -> str:
    values = ",\n                ".join(f"(NEW.id, '{m}')" for m in models)
    return f"""
        CREATE OR REPLACE FUNCTION partner_model_allowlist_on_partner()
        RETURNS trigger
        LANGUAGE plpgsql
        AS $$
        BEGIN
            PERFORM set_config('app.partner_id', NEW.id::text, true);
            INSERT INTO partner_model_allowlist (partner_id, model_id)
            VALUES
                {values}
            ON CONFLICT DO NOTHING;
            RETURN NEW;
        END;
        $$
        """


def upgrade() -> None:
    op.add_column(
        "model_profiles",
        sa.Column("respond_enabled_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("model_profiles", sa.Column("respond_enabled_by", sa.Text(), nullable=True))
    op.add_column("model_profiles", sa.Column("respond_enabled_note", sa.Text(), nullable=True))
    op.create_check_constraint(
        "ck_model_profiles_respond_enabled_by",
        "model_profiles",
        "(respond_enabled_at IS NULL) = (respond_enabled_by IS NULL)",
    )

    bind = op.get_bind()
    bind.execute(
        sa.text(
            """
            UPDATE model_profiles
               SET respond_enabled_at = now(),
                   respond_enabled_by = 'migration:0238',
                   respond_enabled_note = 'ofrecidos antes de la spec 065'
             WHERE model_id = ANY(:ids)
            """
        ),
        {"ids": list(OPENAI)},
    )

    for model_id, (name, inp, read, write, out, legacy, w_in, w_read, w_out) in NEW.items():
        bind.execute(
            sa.text(
                """
                INSERT INTO model_profiles (
                    provider, model_id, display_name,
                    price_input_per_mtok, price_output_per_mtok,
                    price_cache_read_per_mtok, price_cache_write_per_mtok,
                    max_context, cache_min_tokens, supports_tools, supports_vision, status,
                    quota_weight, quota_weight_input, quota_weight_cache_read,
                    quota_weight_output,
                    route, family, residency, zero_retention, contract_dpa,
                    subprocessor_listed, capabilities, quota
                )
                SELECT
                    provider, :model_id, :name,
                    CAST(:inp AS numeric), CAST(:out AS numeric),
                    CAST(:read AS numeric), CAST(:write AS numeric),
                    1000000, cache_min_tokens, supports_tools, supports_vision, 'active',
                    CAST(:legacy AS numeric), CAST(:w_in AS numeric), CAST(:w_read AS numeric),
                    CAST(:w_out AS numeric),
                    :model_id, family, residency, zero_retention, contract_dpa,
                    subprocessor_listed, capabilities, quota
                FROM model_profiles
                WHERE model_id = :haiku
                ON CONFLICT (model_id) DO NOTHING
                """
            ),
            {
                "model_id": model_id,
                "name": name,
                "inp": inp,
                "out": out,
                "read": read,
                "write": write,
                "legacy": legacy,
                "w_in": w_in,
                "w_read": w_read,
                "w_out": w_out,
                "haiku": HAIKU,
            },
        )
        bind.execute(
            sa.text(
                """
                INSERT INTO model_prices (
                    deployment_id, valid_from, input, cache_read, cache_write, output,
                    surcharge, source_url, currency, unit
                )
                SELECT id, CURRENT_DATE, CAST(:inp AS numeric), CAST(:read AS numeric),
                       CAST(:write AS numeric), CAST(:out AS numeric),
                       NULL, :source, 'USD', 'per_million_tokens'
                FROM model_profiles
                WHERE model_id = :model_id
                ON CONFLICT DO NOTHING
                """
            ),
            {
                "model_id": model_id,
                "inp": inp,
                "read": read,
                "write": write,
                "out": out,
                "source": SOURCE,
            },
        )

    for model_id, label in LABELS.items():
        bind.execute(
            sa.text("UPDATE model_profiles SET offer_label = :label WHERE model_id = :model_id"),
            {"label": label, "model_id": model_id},
        )

    # La lista de cada partner es dato de partner (RLS forzada por ``app.partner_id``): fuera
    # de la RLS dentro del bloque, que falla en vez de escribir 0 filas si no se puede (0229).
    anthropic = ", ".join(f"('{m}')" for m in LABELS)
    op.execute(
        "DO $$ BEGIN "
        "SET LOCAL row_security = off; "
        "INSERT INTO partner_model_allowlist (partner_id, model_id) "
        f"SELECT p.id, m.model_id FROM partners p CROSS JOIN (VALUES {anthropic}) AS m(model_id) "
        "ON CONFLICT DO NOTHING; "
        "END $$"
    )
    op.execute(_seed_function(SIX))


def downgrade() -> None:
    op.execute(_seed_function(OPENAI))
    anthropic = ", ".join(f"'{m}'" for m in LABELS)
    op.execute(
        "DO $$ BEGIN "
        "SET LOCAL row_security = off; "
        f"DELETE FROM partner_model_allowlist WHERE model_id IN ({anthropic}); "
        "END $$"
    )
    bind = op.get_bind()
    bind.execute(
        sa.text("UPDATE model_profiles SET offer_label = NULL WHERE model_id = ANY(:ids)"),
        {"ids": list(LABELS)},
    )
    bind.execute(
        sa.text(
            "DELETE FROM model_prices WHERE deployment_id IN "
            "(SELECT id FROM model_profiles WHERE model_id = ANY(:ids))"
        ),
        {"ids": list(NEW)},
    )
    bind.execute(
        sa.text("DELETE FROM model_profiles WHERE model_id = ANY(:ids)"), {"ids": list(NEW)}
    )
    op.drop_constraint("ck_model_profiles_respond_enabled_by", "model_profiles", type_="check")
    op.drop_column("model_profiles", "respond_enabled_note")
    op.drop_column("model_profiles", "respond_enabled_by")
    op.drop_column("model_profiles", "respond_enabled_at")
