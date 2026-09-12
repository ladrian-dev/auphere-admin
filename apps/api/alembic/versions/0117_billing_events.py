"""El registro de avisos del proveedor y la caducidad del saldo (spec 005).

Se separa de la 0116 a propósito, contra la regla 3 de PLAN-CONSOLE-V1, y la
razón está en el Complexity Tracking del plan: **la 0116 es desplegable sola y
no cobra nada.** Fija los topes de los niveles y se puede revertir sin que
ningún dinero se haya movido. Esta segunda toca el camino del dinero. Unirlas
obligaría a desplegar y revertir las dos mitades juntas.

**``provider_event_id`` es UNIQUE, y esa restricción ES la idempotencia.** El
quinto reenvío del mismo pago choca contra ella y no acredita nada. La
alternativa —consultar antes de insertar— la ganan dos entregas simultáneas,
que ocurren.

**``partner_id`` NO tiene clave foránea**, y eso es deliberado. Un aviso que
llega antes de que exista el partner, o de una cuenta que no reconocemos, tiene
que poder registrarse igual: perder el rastro de un aviso de dinero por una
restricción de integridad es peor que tener una fila huérfana. La fila huérfana
se investiga; el aviso perdido no deja nada que investigar.

**``purchased_expires_at`` es NULL mientras la cuenta viva.** La invariante que
hay que preservar es «el crédito comprado no caduca mientras la cuenta viva», y
expresarla como ausencia de fecha la hace imposible de violar por accidente: no
hay nada que comparar. Se rellena al cancelar, con doce meses; vuelve a NULL si
el partner reactiva. Un DEFAULT aquí le pondría fecha de caducidad a todo el
mundo a la vez, en silencio.

Revision ID: 0117_billing_events
Revises: 0116_membership_tiers
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

#: Vocabulario de auditoría de las acciones de facturación. Cada acción que
#: escribe ``audit_log`` con prefijo ``console.`` necesita su fila, y hay un
#: test estructural que lo vigila: sin ella, la pantalla de actividad del
#: partner enseñaría un identificador en vez de una frase.
#:
#: La redacción nombra a la persona —``{actor}``— porque §IV pide que el
#: rastro diga quién decidió. El aviso del proveedor CONFIRMA lo que una
#: persona ya decidió; no aparece aquí como sujeto de nada.
AUDIT_VOCABULARY: tuple[tuple[str, str, str, str, str], ...] = (
    (
        "console.billing.checkout_opened",
        "billing",
        "info",
        "{actor} inició la contratación del plan {tier}.",
        "{actor} started contracting the {tier} plan.",
    ),
    (
        "console.billing.credit_opened",
        "billing",
        "info",
        "{actor} inició una compra de crédito.",
        "{actor} started a credit purchase.",
    ),
)

revision: str = "0117_billing_events"
down_revision: str | Sequence[str] | None = "0116_membership_tiers"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE billing_events (
            id                  uuid         PRIMARY KEY,
            provider_event_id   varchar(80)  NOT NULL UNIQUE,
            event_type          varchar(80)  NOT NULL,
            checkout_session_id varchar(80),
            partner_id          uuid,
            status              varchar(20)  NOT NULL DEFAULT 'received',
            payload             jsonb        NOT NULL,
            error               text,
            received_at         timestamptz  NOT NULL DEFAULT now(),
            processed_at        timestamptz,
            CONSTRAINT ck_billing_events_status
                CHECK (status IN ('received', 'processed', 'failed', 'ignored'))
        )
        """
    )
    # La segunda ancla de idempotencia. ``checkout.session.completed`` y
    # ``checkout.session.async_payment_succeeded`` son eventos DISTINTOS que
    # pueden llegar los dos para la misma compra, así que el UNIQUE de arriba
    # no los detiene: lo que los detiene es mirar si esa sesión ya se cumplió.
    op.execute(
        "CREATE INDEX ix_billing_events_checkout_session "
        "ON billing_events (checkout_session_id) "
        "WHERE checkout_session_id IS NOT NULL"
    )
    # Lo que consulta la alerta de operador: avisos que quedaron sin procesar.
    op.execute(
        "CREATE INDEX ix_billing_events_status_received "
        "ON billing_events (status, received_at DESC)"
    )
    # De plataforma, sin RLS: es nuestro rastro de integración, no dato de un
    # partner, y una fila puede no tener partner resuelto.
    op.execute("GRANT SELECT, INSERT, UPDATE ON billing_events TO nexus_app")

    op.execute(
        """
        ALTER TABLE partner_wallets
          ADD COLUMN IF NOT EXISTS purchased_expires_at timestamptz
        """
    )

    bind = op.get_bind()
    for action, category, severity, summary_es, summary_en in AUDIT_VOCABULARY:
        bind.execute(
            sa.text(
                """
                INSERT INTO console_audit_vocabulary
                    (action, category, severity, summary_es, summary_en)
                SELECT
                    CAST(:action AS VARCHAR(80)),
                    CAST(:category AS VARCHAR(40)),
                    CAST(:severity AS VARCHAR(10)),
                    CAST(:summary_es AS TEXT),
                    CAST(:summary_en AS TEXT)
                WHERE NOT EXISTS (
                    SELECT 1 FROM console_audit_vocabulary
                    WHERE action = CAST(:action AS VARCHAR(80))
                )
                """
            ),
            {
                "action": action,
                "category": category,
                "severity": severity,
                "summary_es": summary_es,
                "summary_en": summary_en,
            },
        )


def downgrade() -> None:
    bind = op.get_bind()
    for action, *_ in AUDIT_VOCABULARY:
        bind.execute(
            sa.text(
                "DELETE FROM console_audit_vocabulary "
                "WHERE action = CAST(:action AS VARCHAR(80))"
            ),
            {"action": action},
        )
    op.execute("ALTER TABLE partner_wallets DROP COLUMN IF EXISTS purchased_expires_at")
    op.execute("DROP TABLE IF EXISTS billing_events")
