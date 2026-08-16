"""CP-28 · vocabulario de eventos de la consola en ``audit_log`` (carril D).

Tres cosas, todas al servicio de la página de auditoría del partner
(``GET /console/audit``):

1. **``console_audit_vocabulary``** — una fila por ``audit_log.action`` que
   la consola escribe o muestra: categoría, resumen humano en ES y EN
   (plantilla con ``{actor}``, ``{client}``, ``{v}``, ``{email}``,
   ``{role}``, ``{status}``, ``{key}``, ``{channel}``, ``{template}``,
   ``{document}``, ``{percent}``) y severidad. Hasta ahora las plantillas
   vivían en un dict de Python solo en inglés; con el vocabulario en base
   de datos la consola renderiza en el idioma pedido y un operador puede
   corregir un texto sin desplegar. La API cachea la tabla en proceso y,
   para una acción que no esté, cae a "{actor} · {action} · {target}".
   ``tests/unit/test_endpoint_console_home_usage.py`` comprueba que TODA
   acción ``console.*`` escrita en ``api/console/**`` está sembrada: un
   carril que añada una acción sin vocabulario rompe la suite.

2. **Índice parcial** ``ix_audit_log_console_recent`` sobre
   ``(created_at DESC, id)`` filtrado a filas de la consola: la página
   pagina por cursor ``(created_at, id)`` y filtra por acción/actor; el
   índice cubre exactamente ese barrido sin cargar la tabla entera de
   auditoría del runtime.

3. **Lectura de ``audit_log`` por encima del tenant para la consola.**
   ``audit_log`` tiene ``FORCE ROW LEVEL SECURITY`` (0002/0040): sin
   ``app.tenant_id`` solo se ven las filas de plataforma (``tenant_id IS
   NULL``), también para el dueño de la tabla en Aurora (que no es
   superusuario). La consola muestra en una sola lista la actividad de
   TODOS los clientes del partner (``tenant_id = ANY(partner_tenants)``) y
   por tanto necesita leer por encima del tenant: se hace con el rol de
   solo lectura ``nexus_reporting`` (0078) — ``GRANT SELECT`` sobre la
   tabla + policy permisiva ``FOR SELECT`` — y la API pone ``SET LOCAL ROLE
   nexus_reporting`` en esa transacción, con el filtro de tenants
   construido desde el principal. Mismo patrón que ``usage_records`` en
   0078/0083. La aislación del runtime (``nexus_app``) no cambia.

Revision ID: 0084_console_audit_events
Revises: 0083_usage_media_units
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0084_console_audit_events"
down_revision: str | Sequence[str] | None = "0083_usage_media_units"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

REPORTING_ROLE = "nexus_reporting"

# (action, category, severity, summary_es, summary_en)
VOCABULARY: tuple[tuple[str, str, str, str, str], ...] = (
    # clients
    (
        "console.client.create",
        "clients",
        "info",
        "{actor} creó el cliente {client}",
        "{actor} created client {client}",
    ),
    (
        "console.client.update",
        "clients",
        "info",
        "{actor} actualizó el cliente {client}",
        "{actor} updated client {client}",
    ),
    (
        "console.client.status",
        "clients",
        "warning",
        "{actor} cambió {client} a {status}",
        "{actor} changed {client} to {status}",
    ),
    ("tenant.update", "clients", "info", "{actor} actualizó {client}", "{actor} updated {client}"),
    (
        "tenant.delete",
        "clients",
        "critical",
        "{actor} eliminó el cliente {client}",
        "{actor} deleted client {client}",
    ),
    # agent versions (written by agent_config_service with actor console:*)
    (
        "agent_config.stage",
        "agents",
        "info",
        "{actor} guardó un borrador (versión {v}) de {client}",
        "{actor} saved a draft (version {v}) for {client}",
    ),
    (
        "agent_config.promote",
        "agents",
        "warning",
        "{actor} publicó la versión {v} del agente de {client}",
        "{actor} published agent version {v} for {client}",
    ),
    (
        "agent_config.rollback",
        "agents",
        "warning",
        "{actor} devolvió el agente de {client} a la versión {v}",
        "{actor} rolled {client}'s agent back to version {v}",
    ),
    (
        "console.agent.settings",
        "agents",
        "info",
        "{actor} cambió los ajustes del agente de {client}",
        "{actor} changed the agent settings of {client}",
    ),
    (
        "console.tools.update",
        "agents",
        "info",
        "{actor} cambió las herramientas del agente de {client}",
        "{actor} changed the agent tools of {client}",
    ),
    (
        "console.skills.update",
        "agents",
        "info",
        "{actor} cambió las habilidades del agente de {client}",
        "{actor} changed the agent skills of {client}",
    ),
    (
        "console.playground.run",
        "agents",
        "info",
        "{actor} probó el agente de {client} en el playground",
        "{actor} tested {client}'s agent in the playground",
    ),
    # channels & templates
    (
        "console.channel.connect",
        "channels",
        "warning",
        "{actor} conectó WhatsApp en {client}",
        "{actor} connected WhatsApp for {client}",
    ),
    (
        "console.channel.role",
        "channels",
        "info",
        "{actor} cambió el rol del canal {channel} de {client}",
        "{actor} changed the role of channel {channel} of {client}",
    ),
    (
        "console.channel.test_send",
        "channels",
        "info",
        "{actor} envió una prueba desde el canal de {client}",
        "{actor} sent a test message from {client}'s channel",
    ),
    (
        "console.template.create",
        "channels",
        "info",
        "{actor} creó la plantilla {template} de {client}",
        "{actor} created template {template} for {client}",
    ),
    (
        "console.template.delete",
        "channels",
        "warning",
        "{actor} eliminó la plantilla {template} de {client}",
        "{actor} deleted template {template} of {client}",
    ),
    # knowledge
    (
        "console.knowledge.upload",
        "knowledge",
        "info",
        "{actor} subió el documento {document} a {client}",
        "{actor} uploaded document {document} to {client}",
    ),
    (
        "console.knowledge.delete",
        "knowledge",
        "warning",
        "{actor} eliminó el documento {document} de {client}",
        "{actor} deleted document {document} from {client}",
    ),
    # team
    (
        "console.member.invite",
        "team",
        "info",
        "{actor} invitó a {email} como {role}",
        "{actor} invited {email} as {role}",
    ),
    (
        "console.member.role",
        "team",
        "warning",
        "{actor} cambió el rol de {email} a {role}",
        "{actor} changed {email}'s role to {role}",
    ),
    (
        "console.member.status",
        "team",
        "warning",
        "{actor} puso a {email} en {status}",
        "{actor} set {email} to {status}",
    ),
    (
        "console.member.remove",
        "team",
        "critical",
        "{actor} quitó a {email} del equipo",
        "{actor} removed {email} from the team",
    ),
    (
        "console.invitation.revoke",
        "team",
        "info",
        "{actor} revocó la invitación de {email}",
        "{actor} revoked the invitation for {email}",
    ),
    (
        "console.invitation.accept",
        "team",
        "info",
        "{email} se unió como {role}",
        "{email} joined as {role}",
    ),
    # keys
    (
        "console.key.create",
        "keys",
        "warning",
        "{actor} creó la clave de API {key}",
        "{actor} created API key {key}",
    ),
    (
        "console.key.rotate",
        "keys",
        "warning",
        "{actor} rotó la clave de API {key}",
        "{actor} rotated API key {key}",
    ),
    (
        "console.key.revoke",
        "keys",
        "critical",
        "{actor} revocó la clave de API {key}",
        "{actor} revoked API key {key}",
    ),
    # usage & notifications
    (
        "console.usage.alerts_update",
        "usage",
        "info",
        "{actor} cambió las alertas de consumo (tope {cap})",
        "{actor} changed the usage alerts (cap {cap})",
    ),
    (
        "console.notification.read",
        "notifications",
        "info",
        "{actor} marcó una notificación como leída",
        "{actor} marked a notification as read",
    ),
)


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE console_audit_vocabulary (
            action      varchar(80) PRIMARY KEY,
            category    varchar(40) NOT NULL,
            severity    varchar(10) NOT NULL DEFAULT 'info'
                        CHECK (severity IN ('info', 'warning', 'critical')),
            summary_es  text NOT NULL,
            summary_en  text NOT NULL,
            updated_at  timestamptz NOT NULL DEFAULT now()
        )
        """
    )
    for action, category, severity, es, en in VOCABULARY:
        es_q = es.replace("'", "''")
        en_q = en.replace("'", "''")
        op.execute(
            "INSERT INTO console_audit_vocabulary (action, category, severity, summary_es, summary_en) "
            f"VALUES ('{action}', '{category}', '{severity}', '{es_q}', '{en_q}') "
            "ON CONFLICT (action) DO UPDATE SET category = EXCLUDED.category, "
            "severity = EXCLUDED.severity, summary_es = EXCLUDED.summary_es, "
            "summary_en = EXCLUDED.summary_en, updated_at = now()"
        )
    op.execute(
        "CREATE INDEX ix_audit_log_console_recent ON audit_log (created_at DESC, id) "
        "WHERE action LIKE 'console.%' OR actor LIKE 'console:%'"
    )
    op.execute(f"GRANT SELECT ON audit_log TO {REPORTING_ROLE}")
    op.execute(
        f"CREATE POLICY audit_log_reporting_read ON audit_log "
        f"AS PERMISSIVE FOR SELECT TO {REPORTING_ROLE} USING (true)"
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS audit_log_reporting_read ON audit_log")
    op.execute(f"REVOKE SELECT ON audit_log FROM {REPORTING_ROLE}")
    op.execute("DROP INDEX IF EXISTS ix_audit_log_console_recent")
    op.execute("DROP TABLE IF EXISTS console_audit_vocabulary")
