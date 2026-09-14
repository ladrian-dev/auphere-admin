"""El partner que nació de cada solicitud (spec 006, R8.1).

**Por qué una columna en ``signup_requests`` y no una en ``partners``.**

El requisito pide que el panel diga de cada partner su fecha, su *vía de
entrada* y su nivel. La vía de entrada ya está: es ``signup_requests.provider``
—nula para contraseña, ``google`` para Google—. Lo que faltaba era saber **qué
partner salió de qué solicitud**, y eso es una relación, no un atributo del
partner.

Se podría haber añadido ``partners.created_via``. No se hace por lo mismo que
no se añade un tercer valor a ``partners.status``: esa tabla la lee media
plataforma, y cada columna nueva es una que alguien tendrá que interpretar en
sitios que hoy ni se sospechan. Aquí la información vive donde nació, en una
tabla que sólo conoce el alta, y el partner no se entera.

``ON DELETE SET NULL`` y no ``CASCADE``: borrar un partner no debe borrar el
rastro de que alguien se registró. Queda la solicitud, huérfana y legible, que
es justo lo que un operador querría ver.
"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0119_signup_partner_link"
down_revision = "0118_signup_and_identities"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "signup_requests",
        sa.Column("partner_id", sa.UUID(as_uuid=True), nullable=True),
        schema="public",
    )
    op.create_foreign_key(
        "fk_signup_requests_partner",
        "signup_requests",
        "partners",
        ["partner_id"],
        ["id"],
        source_schema="public",
        referent_schema="public",
        ondelete="SET NULL",
    )
    # El panel pregunta «¿de qué solicitud salió este partner?». Sin índice eso
    # es un recorrido de la tabla por cada fila que se pinte.
    op.create_index(
        "ix_signup_requests_partner_id",
        "signup_requests",
        ["partner_id"],
        schema="public",
        postgresql_where=sa.text("partner_id IS NOT NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_signup_requests_partner_id", table_name="signup_requests", schema="public")
    op.drop_constraint(
        "fk_signup_requests_partner", "signup_requests", schema="public", type_="foreignkey"
    )
    op.drop_column("signup_requests", "partner_id", schema="public")
