"""Los niveles de membresía y el estado de la suscripción (spec 005, R1 y R5).

Dos tablas, y cada una responde a una pregunta distinta: ``membership_tiers``
dice **qué se vende**, ``partner_subscriptions`` dice **en qué punto está cada
partner**.

**Por qué no se reutiliza ``billing_plans``.** Esa tabla ya existe y es otra
cosa: el precio mensual del servicio gestionado que se le cobra a un *tenant*
(``tenants.billing_plan_id``). Es la relación Auphere ↔ cliente final del
partner. Meter aquí la membresía del partner mezclaría dos relaciones
comerciales en una tabla, y el día que un partner tenga las dos —su membresía y
sus clientes facturados— la consulta no sabría cuál es cuál.

**Por qué no se reutiliza ``partners.status``.** Solo admite ``active`` y
``suspended``, y significa otra cosa: si el partner está operativo. Un partner
impagado **sigue estando operativo** para leer su historia; meterlo en
``suspended`` lo apagaría entero, que es exactamente lo que ADR-037 D6 quiere
evitar.

**``stripe_price_id``, ``stripe_customer_id`` y ``stripe_subscription_id`` son
referencias, no claves.** Anulables, sin UNIQUE y sin FK, a propósito. La
cuenta de Stripe pertenece hoy a un socio de Auphere mientras se completa el
registro fiscal de la empresa, y **se va a migrar**. Stripe no traspasa
clientes ni suscripciones entre cuentas: se recrean. Con estos identificadores
como referencias, migrar es un ``UPDATE … SET … = NULL`` que deja el sistema en
un estado válido —el partner conserva nivel, pool y saldo— en vez de una
reconstrucción. Hay un test que lo vigila
(``tests/integration/test_migration_0116.py``).

**Los tamaños de pool son provisionales** (ADR-037) y por eso son datos. Las
proporciones entre niveles sí importan: la pantalla de planes publica un
múltiplo calculado —«4x el de Pro»— y nunca la cifra absoluta, porque un número
en una tabla de precios convierte cada ajuste de capacidad en un recorte o un
regalo visible.

Revision ID: 0116_membership_tiers
Revises: 0115_weekly_pool_and_weight
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0116_membership_tiers"
down_revision: str | Sequence[str] | None = "0115_weekly_pool_and_weight"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PARTNER = "(NULLIF(current_setting('app.partner_id', true), ''))::uuid"

#: code, display_name, price (cents), weekly pool, teammates, members, order.
#: Pro es el nivel base del que cuelga el múltiplo publicado: Team 4x,
#: Business 12x. Si estas proporciones dejan de ser enteras, la pantalla de
#: planes empieza a decir "3,7x" y hay que decidir qué se hace.
_TIERS: list[tuple[str, str, int, int, int, int, int]] = [
    ("free", "Free", 0, 100_000, 0, 1, 10),
    ("pro", "Pro", 2_000, 500_000, 2, 1, 20),
    ("team", "Team", 6_000, 2_000_000, 6, 3, 30),
    ("business", "Business", 15_000, 6_000_000, 12, 8, 40),
]


def upgrade() -> None:
    op.execute(
        """
        CREATE TABLE membership_tiers (
            code                varchar(20)  PRIMARY KEY,
            display_name        varchar(40)  NOT NULL,
            monthly_price_cents integer      NOT NULL,
            weekly_pool_tokens  bigint       NOT NULL,
            max_teammates       integer      NOT NULL,
            max_members         integer      NOT NULL,
            stripe_price_id     varchar(64),
            sort_order          smallint     NOT NULL,
            is_public           boolean      NOT NULL DEFAULT true,
            created_at          timestamptz  NOT NULL DEFAULT now(),
            updated_at          timestamptz  NOT NULL DEFAULT now(),
            CONSTRAINT ck_membership_tiers_code
                CHECK (code IN ('free', 'pro', 'team', 'business')),
            CONSTRAINT ck_membership_tiers_price_nonneg
                CHECK (monthly_price_cents >= 0),
            CONSTRAINT ck_membership_tiers_pool_nonneg
                CHECK (weekly_pool_tokens >= 0),
            CONSTRAINT ck_membership_tiers_teammates_nonneg
                CHECK (max_teammates >= 0),
            CONSTRAINT ck_membership_tiers_members_min
                CHECK (max_members >= 1)
        )
        """
    )
    for code, name, price, pool, teammates, members, order in _TIERS:
        op.execute(
            f"""
            INSERT INTO membership_tiers (
                code, display_name, monthly_price_cents, weekly_pool_tokens,
                max_teammates, max_members, sort_order
            ) VALUES (
                '{code}', '{name}', {price}, {pool}, {teammates}, {members}, {order}
            )
            """
        )

    op.execute(
        """
        CREATE TABLE partner_subscriptions (
            partner_id             uuid        PRIMARY KEY
                REFERENCES partners(id) ON DELETE CASCADE,
            tier_code              varchar(20) NOT NULL DEFAULT 'free'
                REFERENCES membership_tiers(code),
            state                  varchar(20) NOT NULL DEFAULT 'current',
            current_period_end     timestamptz,
            pending_tier_code      varchar(20)
                REFERENCES membership_tiers(code),
            stripe_customer_id     varchar(64),
            stripe_subscription_id varchar(64),
            state_changed_at       timestamptz NOT NULL DEFAULT now(),
            created_at             timestamptz NOT NULL DEFAULT now(),
            updated_at             timestamptz NOT NULL DEFAULT now(),
            CONSTRAINT ck_partner_subscriptions_state
                CHECK (state IN ('current', 'payment_failed', 'unpaid', 'canceled'))
        )
        """
    )
    # Índice, NO unicidad. El webhook resuelve el partner desde el propio aviso
    # (``client_reference_id``); esto solo acelera la reconciliación manual.
    op.execute(
        "CREATE INDEX ix_partner_subscriptions_stripe_customer "
        "ON partner_subscriptions (stripe_customer_id) "
        "WHERE stripe_customer_id IS NOT NULL"
    )

    op.execute("ALTER TABLE partner_subscriptions ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE partner_subscriptions FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY partner_subscriptions_partner_isolation ON partner_subscriptions
        USING (partner_id = {_PARTNER})
        WITH CHECK (partner_id = {_PARTNER})
        """
    )
    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON partner_subscriptions TO nexus_app"
    )
    # El catálogo es de plataforma: igual para todos y sin RLS. Sólo lectura
    # desde la aplicación — quien lo cambia es una migración o un operador.
    op.execute("GRANT SELECT ON membership_tiers TO nexus_app")

    # Un partner NUEVO sin fila es Free, y eso es correcto: la ausencia es un
    # estado válido y se diseña (principio V).
    #
    # Los partners que YA EXISTEN son otra cosa. Sin esta siembra, el día del
    # despliegue todos pasarían a Free —cero teammates— y dejarían de poder
    # crear ninguno. Es exactamente el modo de fallo del 31 de agosto que la
    # Spec A ya arregló una vez: clientes que nacen mudos porque una cuenta
    # nueva empieza sin nada. Cobrar no puede quitarle a nadie lo que ya tenía.
    #
    # Se les siembra en el nivel de pago MÁS PEQUEÑO que cubre lo que ya usan,
    # mirando teammates y personas. Un partner que hoy tiene 4 teammates entra
    # en Team, no en Pro. Nadie se queda corto y nadie sube más de lo necesario.
    op.execute(
        """
        INSERT INTO partner_subscriptions (partner_id, tier_code, state)
        SELECT p.id,
               (
                 SELECT t.code
                   FROM membership_tiers t
                  WHERE t.max_teammates >= COALESCE(u.teammates, 0)
                    AND t.max_members   >= GREATEST(COALESCE(u.members, 0), 1)
                  ORDER BY t.sort_order
                  LIMIT 1
               ),
               'current'
          FROM partners p
          LEFT JOIN (
                SELECT partner_id,
                       count(*) FILTER (WHERE src = 'tm') AS teammates,
                       count(*) FILTER (WHERE src = 'pm') AS members
                  FROM (
                        SELECT partner_id, 'tm' AS src FROM teammates
                         WHERE status <> 'archived'
                        UNION ALL
                        SELECT partner_id, 'pm' AS src FROM partner_memberships
                         WHERE status = 'active'
                  ) x
                 GROUP BY partner_id
          ) u ON u.partner_id = p.id
        ON CONFLICT (partner_id) DO NOTHING
        """
    )
    # Si algún partner usa MÁS de lo que admite el nivel más alto, la
    # subconsulta devuelve NULL y la fila no entra — el partner se queda sin
    # fila, es decir en Free, que es justo lo que no queremos. Se sube al nivel
    # más alto y se deja constancia: por encima del tope pero sin perder nada,
    # que es lo que R1.6 pide para cualquier partner que se pase.
    op.execute(
        """
        INSERT INTO partner_subscriptions (partner_id, tier_code, state)
        SELECT p.id, 'business', 'current'
          FROM partners p
         WHERE NOT EXISTS (
               SELECT 1 FROM partner_subscriptions s WHERE s.partner_id = p.id
         )
        ON CONFLICT (partner_id) DO NOTHING
        """
    )


def downgrade() -> None:
    op.execute("DROP TABLE IF EXISTS partner_subscriptions")
    op.execute("DROP TABLE IF EXISTS membership_tiers")
