"""El vocabulario de Auditoría de la consola nueva — spec 047, T164 (requisito 49.1;
``contracts/events.md`` §4).

Cada acción nueva que la 047 escribe en ``audit_log`` se lee en la Auditoría del
partner en su idioma, con su categoría (Negocio, Integraciones, Constructor y
Mejora son nuevas) y su gravedad: ``critical`` marca lo sensible (borrar un
cliente, desconectar un canal o una integración para todos, una publicación que
se salta la puerta, un modelo que deja de estar disponible). Las frases solo usan
``{actor}`` y ``{client}``, que ``audit_words`` siempre rellena.

Revision ID: 0197_audit_vocabulary_047
Revises: 0196_usage_lines_reporting
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0197_audit_vocabulary_047"
down_revision: str | Sequence[str] | None = "0196_usage_lines_reporting"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

#: (acción, categoría, gravedad, español, inglés)
ROWS: tuple[tuple[str, str, str, str, str], ...] = (
    # Negocio (la ficha)
    ("business.section_updated", "business", "info",
     "{actor} cambió la ficha de {client}.", "{actor} changed the business profile of {client}."),
    ("business.section_undone", "business", "info",
     "{actor} deshizo un cambio de la ficha de {client}.",
     "{actor} undid a change to the business profile of {client}."),
    ("business.read_applied", "business", "info",
     "La lectura de la web completó la ficha de {client}.",
     "Reading the website filled in the business profile of {client}."),
    ("business.correction_applied", "business", "info",
     "{actor} corrigió la ficha de {client} desde una conversación.",
     "{actor} corrected the business profile of {client} from a conversation."),
    # Agentes
    ("agent.publish", "agents", "info",
     "{actor} publicó un agente de {client}.", "{actor} published an agent of {client}."),
    ("agent.publish_undone", "agents", "info",
     "{actor} deshizo la publicación de un agente de {client}.",
     "{actor} undid the publication of an agent of {client}."),
    ("agent.paused", "agents", "info",
     "{actor} pausó un agente de {client}.", "{actor} paused an agent of {client}."),
    ("agent.resumed", "agents", "info",
     "{actor} reanudó un agente de {client}.", "{actor} resumed an agent of {client}."),
    ("agent.restored", "agents", "info",
     "{actor} restauró un agente de {client}.", "{actor} restored an agent of {client}."),
    ("agent.default_changed", "agents", "info",
     "{actor} cambió el agente por defecto de {client}.",
     "{actor} changed the default agent of {client}."),
    ("agent.quality_changed", "agents", "info",
     "{actor} cambió la calidad de un agente de {client}.",
     "{actor} changed the quality of an agent of {client}."),
    ("agent.cap_changed", "usage", "info",
     "{actor} cambió el tope mensual de un agente de {client}.",
     "{actor} changed the monthly cap of an agent of {client}."),
    # Canales
    ("channel.connected", "channels", "info",
     "Se conectó un canal de {client}.", "A channel of {client} was connected."),
    ("channel.config_changed", "channels", "info",
     "{actor} cambió la configuración de un canal de {client}.",
     "{actor} changed the settings of a channel of {client}."),
    ("channel.config_undone", "channels", "info",
     "{actor} deshizo un cambio de un canal de {client}.",
     "{actor} undid a change to a channel of {client}."),
    ("channel.moved", "channels", "info",
     "{actor} pasó un canal de {client} a otro agente.",
     "{actor} moved a channel of {client} to another agent."),
    ("channel.paused", "channels", "info",
     "{actor} pausó un canal de {client}.", "{actor} paused a channel of {client}."),
    ("channel.resumed", "channels", "info",
     "{actor} reanudó un canal de {client}.", "{actor} resumed a channel of {client}."),
    ("channel.problem", "channels", "warning",
     "Un canal de {client} tiene un problema.", "A channel of {client} has a problem."),
    # Integraciones
    ("integration.activated", "integrations", "info",
     "{actor} activó una integración en un agente de {client}.",
     "{actor} turned on an integration for an agent of {client}."),
    ("integration.deactivated", "integrations", "critical",
     "{actor} desconectó una integración de {client}.",
     "{actor} disconnected an integration of {client}."),
    ("integration.reauth_required", "integrations", "warning",
     "Una integración de {client} hay que volver a autorizarla.",
     "An integration of {client} needs to be authorized again."),
    # Conocimiento
    ("knowledge.taught", "knowledge", "info",
     "{actor} enseñó algo nuevo a un agente de {client}.",
     "{actor} taught something new to an agent of {client}."),
    ("knowledge.restore", "knowledge", "info",
     "{actor} recuperó un documento de {client}.", "{actor} restored a document of {client}."),
    # Consumo
    ("wallet.assigned", "usage", "info",
     "{actor} asignó saldo a {client}.", "{actor} assigned balance to {client}."),
    ("wallet.lowered", "usage", "info",
     "{actor} devolvió a la cuenta saldo de {client}.",
     "{actor} returned balance of {client} to the account."),
    ("wallet.moved", "usage", "info",
     "{actor} movió saldo entre bolsas de clientes.",
     "{actor} moved balance between client wallets."),
    ("wallet.refill_set", "usage", "info",
     "{actor} cambió el relleno mensual de {client}.",
     "{actor} changed the monthly refill of {client}."),
    ("wallet.currency_changed", "usage", "info",
     "{actor} cambió la moneda de la bolsa de {client}.",
     "{actor} changed the wallet currency of {client}."),
    ("balance.requested", "usage", "info",
     "{actor} pidió saldo para {client}.", "{actor} asked for balance for {client}."),
    ("build_budget.extension_requested", "usage", "info",
     "{actor} pidió ampliar «Construcción y pruebas».",
     "{actor} asked to raise «Building and testing»."),
    # Operador
    ("deployment.created", "admin", "info",
     "Auphere añadió un modelo al catálogo.", "Auphere added a model to the catalog."),
    ("deployment.activated", "admin", "info",
     "Auphere activó un modelo del catálogo.", "Auphere turned on a model of the catalog."),
    ("deployment.retired", "admin", "warning",
     "Auphere retiró un modelo del catálogo.", "Auphere retired a model of the catalog."),
    ("deployment.unavailable", "admin", "critical",
     "Un modelo del catálogo dejó de estar disponible.",
     "A model of the catalog became unavailable."),
    ("router.policy_changed", "admin", "info",
     "Auphere cambió cómo se eligen los modelos.", "Auphere changed how models are chosen."),
    ("admin.partner.build_budget", "admin", "info",
     "Auphere cambió el tope de «Construcción y pruebas».",
     "Auphere changed the «Building and testing» cap."),
    ("admin.partner.account_currency", "admin", "info",
     "Auphere cambió la moneda de tu cuenta.", "Auphere changed your account currency."),
)  # fmt: skip


def upgrade() -> None:
    vocabulary = sa.table(
        "console_audit_vocabulary",
        sa.column("action", sa.String),
        sa.column("category", sa.String),
        sa.column("severity", sa.String),
        sa.column("summary_es", sa.Text),
        sa.column("summary_en", sa.Text),
    )
    for action, category, severity, es, en in ROWS:
        op.execute(
            sa.dialects.postgresql.insert(vocabulary)
            .values(
                action=action, category=category, severity=severity, summary_es=es, summary_en=en
            )
            .on_conflict_do_nothing(index_elements=["action"])
        )


def downgrade() -> None:
    actions = ", ".join(f"'{row[0]}'" for row in ROWS)
    op.execute(f"DELETE FROM console_audit_vocabulary WHERE action IN ({actions})")
