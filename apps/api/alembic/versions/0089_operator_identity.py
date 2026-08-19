"""Esquema ``operator_auth`` — la identidad del panel de operador se muda a la API.

ADR-034. Gemela de 0088 (``console_auth``) y por el mismo motivo, que el
corte a AWS del 2026-08-19 hizo imposible seguir ignorando: el panel
resolvía la sesión con Better Auth y Drizzle contra Postgres, y
``nexus-prod-aurora`` es privada. Una función de Vercel no la alcanza y no
la va a alcanzar. El 500 de ``admin.auphere.com`` no era un despiste de
variables sino un componente del lado equivocado de ADR-032.

Dos tablas de PLATAFORMA (sin ``tenant_id``, sin RLS — mismo modelo de
confianza que ``partners``):

- ``operator_auth.principals``          — la persona de Auphere
- ``operator_auth.principal_sessions``  — su sesión, por hash del token

**Por qué un esquema propio y no reutilizar ``console_auth``.** Los
principals de la consola son gente de los partners; los de aquí son
personal de Auphere con acceso transversal a todos los tenants.
Compartir tabla convierte un error de etiquetado —una fila con el flag
equivocado— en una escalada de privilegios. Con dos esquemas, el
verificador de cada superficie consulta el suyo y la confusión no es
improbable: es imposible.

Sobre ``role``: **no es una rejilla de permisos nueva, es la que ya
existía**. ``auth.user.role`` (better-auth) gatea hoy el QA Playground —
``apps/admin/src/lib/qa-access.ts`` deja pasar sólo a ``admin`` y
``qa_operator``, y devuelve 403 a ``viewer``. Perder esa columna al mudar
la identidad habría sido quitar un control de acceso de tapadillo, así que
viaja tal cual, con los mismos tres valores y el mismo default. Para todo
lo demás el panel sigue siendo god-mode por ADR-009: el rol NO decide qué
se puede tocar en ``/admin/*``.

``disabled_at`` es otra cosa y por eso es otra columna: revoca a quien se
va, sin borrar la fila, para que el rastro de ``audit_log`` siga apuntando
a un principal que existe.

Lo que esta migración NO trae, a propósito:

- **No se migran las contraseñas.** Better Auth y scrypt derivan distinto;
  no hay conversión posible. Las cuentas se recrean por invitación o con
  ``--set-password``, y todo el mundo entra de nuevo. Las filas de
  ``auth.user`` / ``auth.account`` se quedan donde están: son el registro
  de qué correos había.

**Consecuencia que hay que tener presente**: ``qa.*`` aísla por
``app.operator_id``, que es TEXT porque guardaba el id cuid de Better Auth
(ver ``core/operator_context.py``). Los principals nuevos son UUID, así que
un operador migrado **deja de ver sus hilos viejos del QA Playground**. Las
filas no se borran ni se tocan; simplemente pertenecen a un id anterior.
Para hilos de prueba del Playground es un coste asumible, pero es un
cambio silencioso y por eso queda escrito aquí.

Revision ID: 0089_operator_identity
Revises: 0088_console_identity
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import INET, UUID

from alembic import op

revision: str = "0089_operator_identity"
down_revision: str | Sequence[str] | None = "0088_console_identity"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

SCHEMA = "operator_auth"


def upgrade() -> None:
    op.execute(f"CREATE SCHEMA IF NOT EXISTS {SCHEMA}")

    op.create_table(
        "principals",
        sa.Column(
            "id",
            UUID(as_uuid=True),
            primary_key=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column("email", sa.String(255), nullable=False),
        # ``scrypt$n$r$p$<salt_b64>$<hash_b64>`` — ver services/identity.py.
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("display_name", sa.String(255), nullable=True),
        sa.Column("locale", sa.String(5), nullable=False, server_default="es"),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column("last_login_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("failed_attempts", sa.Integer(), nullable=False, server_default="0"),
        # El rol que hoy vive en ``auth.user.role``. CHECK y no ENUM: añadir
        # un valor a un ENUM de Postgres es una migración con bloqueo, y esta
        # lista se va a mover.
        sa.Column("role", sa.String(32), nullable=False, server_default="qa_operator"),
        sa.CheckConstraint(
            "role IN ('admin', 'qa_operator', 'viewer')",
            name="ck_operator_principals_role",
        ),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        # Revocación sin borrado: la fila sobrevive para que el rastro de
        # auditoría siga resolviendo, pero no abre sesión ni la mantiene.
        sa.Column("disabled_at", sa.DateTime(timezone=True), nullable=True),
        schema=SCHEMA,
    )
    # Unicidad case-insensitive sin ``citext`` — misma razón que en 0088:
    # la extensión no está instalada en la base local y crearla en Aurora
    # exige ``rds_superuser``.
    op.create_index(
        "uq_operator_principals_email",
        "principals",
        [sa.text("lower(email)")],
        unique=True,
        schema=SCHEMA,
    )

    op.create_table(
        "principal_sessions",
        # La PK es el hash del token: buscar una sesión es un índice único
        # sobre 64 caracteres, y un volcado de la tabla no permite entrar en
        # ninguna cuenta (mismo patrón que ``api_keys``).
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column(
            "principal_id",
            UUID(as_uuid=True),
            sa.ForeignKey(f"{SCHEMA}.principals.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "last_used_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.text("now()"),
        ),
        sa.Column("ip", INET(), nullable=True),
        sa.Column("user_agent", sa.String(255), nullable=True),
        schema=SCHEMA,
    )
    op.create_index(
        "ix_operator_sessions_principal", "principal_sessions", ["principal_id"], schema=SCHEMA
    )
    # Lo usa el barrido oportunista de sesiones caducadas al crear una nueva.
    op.create_index(
        "ix_operator_sessions_expires", "principal_sessions", ["expires_at"], schema=SCHEMA
    )

    # **Sin grant a ``nexus_app``**, igual que 0088: estas tablas solo las
    # toca la API con el rol dueño, en endpoints que no cambian de rol. El
    # rol degradado del runtime no tiene por qué ver contraseñas.


def downgrade() -> None:
    # A diferencia de 0088, aquí SÍ se borra el esquema: lo crea esta misma
    # migración y no puede contener nada anterior. El de la consola convivía
    # con las tablas viejas de better-auth y por eso se dejaba en pie.
    op.execute(f"DROP SCHEMA IF EXISTS {SCHEMA} CASCADE")
