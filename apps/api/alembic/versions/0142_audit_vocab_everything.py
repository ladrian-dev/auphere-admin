"""Spec 029: every action written to ``audit_log`` has a sentence.

With real data, the partner's audit trail still had lines like «Auphere ·
connector.disconnect · connector:googlesheets»: 60 actions written by the
API and the worker had no row here, and the renderer fell back to the code.
This seeds all of them, in both languages; ``test_console_audit_words``
now fails if the code writes an action without a sentence.

Revision ID: 0142_audit_vocab_everything
Revises: 0141_audit_actor_no_secret
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0142_audit_vocab_everything"
down_revision: str | Sequence[str] | None = "0141_audit_actor_no_secret"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

# action, category, severity, es, en
ROWS: tuple[tuple[str, str, str, str, str], ...] = (
    # ── agents ──────────────────────────────────────────────────────────
    (
        "agent_config.promote.override",
        "agents",
        "warning",
        "{actor} publicó la versión {v} del agente de {client} sin pasar la revisión.",
        "{actor} published agent version {v} for {client} without the review.",
    ),
    (
        "agent_config.runtime.update",
        "agents",
        "info",
        "{actor} cambió la configuración técnica del agente de {client}.",
        "{actor} changed the technical settings of {client}'s agent.",
    ),
    (
        "async_booking.escalation",
        "agents",
        "warning",
        "El agente de {client} no pudo confirmar una cita y la pasó al equipo: {service}, {when}.",
        "{client}'s agent could not confirm a booking and passed it to the team: {service}, {when}.",
    ),
    (
        "conversation.release",
        "agents",
        "info",
        "{actor} devolvió al agente una conversación de {client}.",
        "{actor} handed a conversation of {client} back to the agent.",
    ),
    (
        "operator.message_sent",
        "agents",
        "info",
        "{actor} escribió en una conversación de {client}.",
        "{actor} wrote in a conversation of {client}.",
    ),
    (
        "integration.agendapro.public_url",
        "agents",
        "info",
        "{actor} cambió la agenda de AgendaPro de {client}.",
        "{actor} changed {client}'s AgendaPro booking page.",
    ),
    (
        "llm.block",
        "agents",
        "critical",
        "{actor} bloqueó el uso del modelo en {partner}.",
        "{actor} blocked model usage for {partner}.",
    ),
    (
        "partner_models.set",
        "agents",
        "info",
        "{actor} cambió los modelos disponibles: {models}.",
        "{actor} changed the available models: {models}.",
    ),
    (
        "platform.turn_error_burst",
        "agents",
        "warning",
        "El agente de {client} falló varias veces seguidas.",
        "{client}'s agent failed several times in a row.",
    ),
    # ── integrations (connectors) ──────────────────────────────────────
    (
        "connector.connect_initiated",
        "agents",
        "info",
        "{actor} empezó a conectar {connector} en {client}.",
        "{actor} started connecting {connector} for {client}.",
    ),
    (
        "connector.connect_completed",
        "agents",
        "info",
        "{connector} quedó conectado en {client}.",
        "{connector} is now connected for {client}.",
    ),
    (
        "connector.consent_reissued",
        "agents",
        "info",
        "{actor} volvió a pedir el permiso de {connector} en {client}.",
        "{actor} asked again for {connector}'s permission for {client}.",
    ),
    (
        "connector.disconnect",
        "agents",
        "warning",
        "{actor} desconectó {connector} en {client}.",
        "{actor} disconnected {connector} from {client}.",
    ),
    (
        "connector.error",
        "agents",
        "warning",
        "{connector} dio un error en {client}.",
        "{connector} failed for {client}.",
    ),
    (
        "connector.needs_reauth",
        "agents",
        "warning",
        "{connector} pide volver a iniciar sesión en {client}.",
        "{connector} needs signing in again for {client}.",
    ),
    (
        "connector.pause",
        "agents",
        "info",
        "{actor} pausó {connector} en {client}.",
        "{actor} paused {connector} for {client}.",
    ),
    (
        "connector.resume",
        "agents",
        "info",
        "{actor} reanudó {connector} en {client}.",
        "{actor} resumed {connector} for {client}.",
    ),
    (
        "connector.override_upsert",
        "agents",
        "info",
        "{actor} cambió la herramienta {tool} de {client}: {change}.",
        "{actor} changed {client}'s tool {tool}: {change}.",
    ),
    (
        "connector.override_delete",
        "agents",
        "info",
        "{actor} devolvió la herramienta {tool} de {client} a como viene por defecto.",
        "{actor} put {client}'s tool {tool} back to default.",
    ),
    (
        "connector.tools.synced",
        "agents",
        "info",
        "{connector} puso al día sus herramientas en {client} ({count} nuevas).",
        "{connector} updated its tools for {client} ({count} new).",
    ),
    (
        "connector.tools_auto_enabled",
        "agents",
        "info",
        "Se activaron {count} herramientas de {connector} en {client}.",
        "{count} tools of {connector} were turned on for {client}.",
    ),
    (
        "connector.webhook_unhandled_status",
        "agents",
        "info",
        "{connector} avisó de un estado que no se esperaba en {client}.",
        "{connector} reported an unexpected state for {client}.",
    ),
    # ── channels ───────────────────────────────────────────────────────
    (
        "channel.role_changed",
        "channels",
        "info",
        "{actor} cambió el rol de un número de {client} a {role}.",
        "{actor} changed the role of a number of {client} to {role}.",
    ),
    (
        "channel.whatsapp.meta_signup",
        "channels",
        "warning",
        "{actor} conectó el WhatsApp {phone} en {client} {wa_mode}.",
        "{actor} connected WhatsApp {phone} for {client} {wa_mode}.",
    ),
    (
        "channel.whatsapp.partner_signup",
        "channels",
        "warning",
        "{actor} conectó el WhatsApp {phone} en {client} {wa_mode}.",
        "{actor} connected WhatsApp {phone} for {client} {wa_mode}.",
    ),
    (
        "channel.whatsapp.meta_connect_owned",
        "channels",
        "warning",
        "{actor} conectó el WhatsApp {phone} en {client} {wa_mode}.",
        "{actor} connected WhatsApp {phone} for {client} {wa_mode}.",
    ),
    (
        "channel.whatsapp.meta_test_send",
        "channels",
        "info",
        "{actor} envió un mensaje de prueba a {to} desde el WhatsApp de {client}.",
        "{actor} sent a test message to {to} from {client}'s WhatsApp.",
    ),
    (
        "channel.whatsapp.quality_rating_changed",
        "channels",
        "warning",
        "La calidad del WhatsApp de {client} pasó de {from_quality} a {to_quality}.",
        "The quality of {client}'s WhatsApp went from {from_quality} to {to_quality}.",
    ),
    (
        "channel.whatsapp.template_created",
        "channels",
        "info",
        "{actor} creó la plantilla {template} de {client}.",
        "{actor} created the template {template} for {client}.",
    ),
    (
        "channel.whatsapp.template_deleted",
        "channels",
        "warning",
        "{actor} eliminó la plantilla {template} de {client}.",
        "{actor} deleted the template {template} of {client}.",
    ),
    (
        "channel.tiktok.authorize",
        "channels",
        "warning",
        "Se conectó la cuenta de TikTok {account} en {client}.",
        "The TikTok account {account} was connected for {client}.",
    ),
    (
        "channel.tiktok.disconnect",
        "channels",
        "warning",
        "{actor} desconectó TikTok en {client}.",
        "{actor} disconnected TikTok from {client}.",
    ),
    (
        "channel.tiktok.token_refresh_failed",
        "channels",
        "warning",
        "TikTok dejó de responder en {client}: hay que volver a conectarlo.",
        "TikTok stopped answering for {client}: it needs connecting again.",
    ),
    (
        "backchannel_owner.registered",
        "channels",
        "info",
        "{actor} registró {phone} como número del dueño de {client}.",
        "{actor} registered {phone} as the owner's number of {client}.",
    ),
    (
        "backchannel_owner.updated",
        "channels",
        "info",
        "{actor} cambió el número del dueño de {client} ({phone}).",
        "{actor} changed the owner's number of {client} ({phone}).",
    ),
    (
        "backchannel_owner.deregistered",
        "channels",
        "warning",
        "{actor} quitó {phone} como número del dueño de {client}.",
        "{actor} removed {phone} as the owner's number of {client}.",
    ),
    (
        "auphere_channel.created",
        "channels",
        "info",
        "{actor} añadió el número de Auphere {phone}.",
        "{actor} added the Auphere number {phone}.",
    ),
    (
        "auphere_channel.updated",
        "channels",
        "info",
        "{actor} cambió el número de Auphere {phone}.",
        "{actor} changed the Auphere number {phone}.",
    ),
    (
        "auphere_channel.deactivated",
        "channels",
        "warning",
        "{actor} desactivó el número de Auphere {phone}.",
        "{actor} turned off the Auphere number {phone}.",
    ),
    # ── knowledge ──────────────────────────────────────────────────────
    (
        "knowledge.upload",
        "knowledge",
        "info",
        "{actor} subió el documento {document} a {client}.",
        "{actor} uploaded the document {document} to {client}.",
    ),
    (
        "knowledge.add_url",
        "knowledge",
        "info",
        "{actor} añadió la página {document} a {client}.",
        "{actor} added the page {document} to {client}.",
    ),
    (
        "knowledge.reindex",
        "knowledge",
        "info",
        "{actor} volvió a leer el documento {document} de {client}.",
        "{actor} re-read the document {document} of {client}.",
    ),
    (
        "knowledge.delete",
        "knowledge",
        "warning",
        "{actor} eliminó el documento {document} de {client}.",
        "{actor} deleted the document {document} of {client}.",
    ),
    (
        "playbook.upload",
        "knowledge",
        "info",
        "{actor} subió el documento {document} a la guía del partner.",
        "{actor} uploaded the document {document} to the partner guide.",
    ),
    (
        "playbook.add_url",
        "knowledge",
        "info",
        "{actor} añadió la página {document} a la guía del partner.",
        "{actor} added the page {document} to the partner guide.",
    ),
    (
        "playbook.reindex",
        "knowledge",
        "info",
        "{actor} volvió a leer el documento {document} de la guía del partner.",
        "{actor} re-read the document {document} of the partner guide.",
    ),
    (
        "playbook.delete",
        "knowledge",
        "warning",
        "{actor} eliminó el documento {document} de la guía del partner.",
        "{actor} deleted the document {document} from the partner guide.",
    ),
    # ── usage and billing ──────────────────────────────────────────────
    (
        "cost.daily_threshold_exceeded",
        "usage",
        "warning",
        "{client} gastó {cost} el {day}, por encima del aviso de {threshold}.",
        "{client} spent {cost} on {day}, above the {threshold} warning.",
    ),
    (
        "budget_policy.upsert",
        "usage",
        "info",
        "{actor} cambió un límite de gasto.",
        "{actor} changed a spending limit.",
    ),
    (
        "budget_policy.delete",
        "usage",
        "warning",
        "{actor} quitó un límite de gasto.",
        "{actor} removed a spending limit.",
    ),
    (
        "wallet.admin_purchased",
        "billing",
        "info",
        "{actor} añadió {amount} de saldo.",
        "{actor} added {amount} of balance.",
    ),
    (
        "budget.hard_limit_reached",
        "usage",
        "warning",
        "{client} llegó a su límite de gasto ({cost} de {threshold}) y el agente pasó la conversación al equipo.",
        "{client} reached its spending limit ({cost} of {threshold}) and the agent handed the conversation to the team.",
    ),
    (
        "isolation.violation_detected",
        "admin",
        "critical",
        "Auphere detectó una alerta de aislamiento en {client}.",
        "Auphere detected an isolation alert for {client}.",
    ),
    # ── clients, keys and the account ──────────────────────────────────
    (
        "tenant.create",
        "clients",
        "info",
        "{actor} creó el cliente {client}.",
        "{actor} created the client {client}.",
    ),
    (
        "key.rotate",
        "keys",
        "warning",
        "{actor} rotó la clave de API {key}.",
        "{actor} rotated the API key {key}.",
    ),
    (
        "key.revoke",
        "keys",
        "critical",
        "{actor} revocó la clave de API {key}.",
        "{actor} revoked the API key {key}.",
    ),
    (
        "partner.create",
        "team",
        "info",
        "{actor} creó la cuenta de {partner}.",
        "{actor} created the {partner} account.",
    ),
    (
        "partner.update",
        "team",
        "info",
        "{actor} actualizó la cuenta de {partner}.",
        "{actor} updated the {partner} account.",
    ),
    (
        "partner.signup.completed",
        "team",
        "info",
        "{actor} creó la cuenta de {partner}.",
        "{actor} created the {partner} account.",
    ),
    (
        "signup.resend",
        "team",
        "info",
        "{actor} volvió a enviar la invitación de alta a {email}.",
        "{actor} resent the sign-up invitation to {email}.",
    ),
)


def upgrade() -> None:
    bind = op.get_bind()
    for action, category, severity, summary_es, summary_en in ROWS:
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
    for action, *_ in ROWS:
        bind.execute(
            sa.text("DELETE FROM console_audit_vocabulary WHERE action = :action"),
            {"action": action},
        )
