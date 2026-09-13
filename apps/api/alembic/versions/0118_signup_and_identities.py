"""El registro autónomo de partners (spec 006, R1 y R5).

Dos tablas, en dos esquemas, porque responden a dos cosas distintas:

- ``public.signup_requests`` — un correo que **pidió** cuenta y todavía no la
  tiene. Es lo único que existe antes de verificar, y se extingue al
  completarse el alta o al caducar.
- ``console_auth.principal_identities`` — el vínculo entre una cuenta de
  consola y el identificador que un proveedor externo emite para esa persona.

**Por qué ``signup_requests`` no lleva ``partner_id``.** No puede llevarlo: el
partner **no existe** hasta que alguien completa el alta. Ésa es toda la razón
por la que esto es una tabla y no una columna en otra.

**Por qué el TTL es de 24 h y no los 21 días de una invitación.** Una
invitación la manda alguien que te conoce y puede esperar tres semanas. Una
solicitud de alta la pide un desconocido y el correo está en su bandeja ahora
mismo. Cuanto más corta la ventana, menos vale un buzón comprometido. El número
lo pone la aplicación (``signup_token_ttl_hours``); aquí solo se guarda la
fecha resultante.

**Por qué el ancla del proveedor es ``subject`` y no el correo.** Un correo
cambia de dueño: se libera y se reasigna, y en Workspace eso pasa cada vez que
alguien deja una empresa. Anclar al correo haría que quien hereda una dirección
herede la cuenta. El ``sub`` de Google no se reasigna nunca.
``email_at_link`` existe **solo** para poder responder «¿con qué correo se
vinculó esto?» en una auditoría; ninguna consulta del producto la usa como
criterio de búsqueda.

**Ningún token de proveedor se guarda.** No hay columna para ellos y es
deliberado: el ``id_token`` ya trae ``sub`` y ``email_verified``, y no se pide
``refresh_token`` porque hoy no hay ámbito que refrescar. La columna se añadirá
con la spec que los use. Guardarlos ahora sería una credencial almacenada sin
lector — la misma figura que ``NEXUS_WEBHOOK_HMAC_SECRET``.

**Grants, y la asimetría es la de 0088.** ``signup_requests`` es ``public`` y la
toca ``nexus_app``. ``console_auth.*`` **no lleva grant**: ese esquema solo lo
toca la API con el rol propietario, igual que ``principals``.

Revision ID: 0118_signup_and_identities
Revises: 0117_billing_events
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision: str = "0118_signup_and_identities"
down_revision: str | Sequence[str] | None = "0117_billing_events"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CONSOLE_AUTH = "console_auth"


def upgrade() -> None:
    op.create_table(
        "signup_requests",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        # Siempre en minúsculas: lo normaliza el servicio, y el índice parcial
        # de abajo lo impone para la regla de "una pendiente por correo".
        sa.Column("email", sa.String(255), nullable=False),
        # SHA-256 hex del token. El claro se enseña UNA vez, en el enlace, y no
        # se escribe en ningún registro ni traza. Mismo patrón que
        # ``partner_invitations`` y ``console_auth.principal_sessions``.
        sa.Column("token_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(20), nullable=False, server_default="pending"),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True), nullable=True),
        # ``google`` cuando la solicitud nace de un alta con proveedor; NULL si
        # es por contraseña. Es la "vía de entrada" que el operador ve.
        sa.Column("provider", sa.String(20), nullable=True),
        # SHA-256 de la IP: permite investigar un abuso sin guardar un dato
        # personal en claro.
        sa.Column("created_ip_hash", sa.String(64), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.CheckConstraint(
            "status IN ('pending', 'consumed', 'expired', 'revoked')",
            name="ck_signup_requests_status",
        ),
        sa.CheckConstraint(
            "provider IS NULL OR provider IN ('google')",
            name="ck_signup_requests_provider",
        ),
    )
    # Buscar una solicitud es un índice único sobre 64 caracteres, y un volcado
    # de la tabla no permite completar ningún alta.
    op.create_index("uq_signup_requests_token_hash", "signup_requests", ["token_hash"], unique=True)
    # Parcial: solo las pendientes. Es el que hace barata la regla de "una
    # pendiente por correo" sin estorbar a las ya consumidas.
    op.create_index(
        "ix_signup_requests_email_pending",
        "signup_requests",
        [sa.text("lower(email)")],
        postgresql_where=sa.text("status = 'pending'"),
    )
    # La caducidad la barre un cron; sin este índice, barrer es un seq scan.
    op.create_index(
        "ix_signup_requests_expires",
        "signup_requests",
        ["expires_at"],
        postgresql_where=sa.text("status = 'pending'"),
    )
    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON signup_requests TO nexus_app")

    op.create_table(
        "principal_identities",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "principal_id",
            UUID(as_uuid=True),
            sa.ForeignKey(f"{CONSOLE_AUTH}.principals.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("provider", sa.String(20), nullable=False),
        # El ``sub`` del proveedor: opaco y estable.
        sa.Column("subject", sa.String(255), nullable=False),
        # Instantánea para auditoría. NUNCA criterio de búsqueda.
        sa.Column("email_at_link", sa.String(255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("provider IN ('google')", name="ck_principal_identities_provider"),
        schema=CONSOLE_AUTH,
    )
    # Un identificador de proveedor pertenece a UNA sola cuenta. Sin esto, dos
    # cuentas podrían reclamar el mismo ``sub`` y el login sería ambiguo.
    op.create_index(
        "uq_principal_identities_provider_subject",
        "principal_identities",
        ["provider", "subject"],
        unique=True,
        schema=CONSOLE_AUTH,
    )
    op.create_index(
        "ix_principal_identities_principal",
        "principal_identities",
        ["principal_id"],
        schema=CONSOLE_AUTH,
    )


def downgrade() -> None:
    op.drop_index("ix_principal_identities_principal", "principal_identities", schema=CONSOLE_AUTH)
    op.drop_index(
        "uq_principal_identities_provider_subject",
        "principal_identities",
        schema=CONSOLE_AUTH,
    )
    op.drop_table("principal_identities", schema=CONSOLE_AUTH)

    op.drop_index("ix_signup_requests_expires", "signup_requests")
    op.drop_index("ix_signup_requests_email_pending", "signup_requests")
    op.drop_index("uq_signup_requests_token_hash", "signup_requests")
    op.drop_table("signup_requests")
