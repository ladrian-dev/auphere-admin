"""Lectura del catálogo de Postgres que comparten los barridos de la spec 047.

``test_43`` (garantía 1) y ``test_44`` (garantía 9) preguntan lo mismo a
``pg_class``, ``pg_policy`` y ``pg_constraint``: qué tablas son de cliente, con
qué políticas y con qué claves foráneas. Vive aquí para que los dos lean el
catálogo con la **misma** consulta; dos copias parecidas son cómo un barrido
acaba mirando otra cosa que el otro.

No es un test (el nombre empieza por ``_``): pytest no lo recoge.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

import sqlalchemy as sa

#: Esquemas que no son de la aplicación. ``pg_temp_*`` son las tablas
#: temporales de otras sesiones: no son del esquema y cambian solas.
_SYSTEM_SCHEMAS = ("pg_catalog", "information_schema", "pg_toast")

#: La política de cliente canónica, tal como Postgres la devuelve con
#: ``pg_get_expr`` (sin espacios). Es la de ``data-model.md``: la columna contra
#: el GUC del contexto de petición, y ``NULLIF`` para que sin GUC no haya filas
#: (falla cerrada) en vez de un error de conversión.
CANONICAL_TENANT_EXPR = (
    "(tenant_id=(NULLIF(current_setting('app.tenant_id'::text,true),''::text))::uuid)"
)

#: Roles a los que una política tiene que aplicar para proteger al runtime:
#: ``PUBLIC`` (sin ``TO``) o el rol con el que corre la aplicación.
APP_ROLES = frozenset({"public", "nexus_app"})


def normalise(expr: str | None) -> str:
    return re.sub(r"\s+", "", expr or "")


@dataclass(frozen=True)
class Policy:
    name: str
    command: str  # '*' (ALL), 'r', 'a', 'w', 'd'
    permissive: bool
    roles: frozenset[str]
    using: str
    check: str

    @property
    def is_canonical_tenant_policy(self) -> bool:
        return (
            self.command == "*"
            and self.permissive
            and bool(self.roles & APP_ROLES)
            and normalise(self.using) == CANONICAL_TENANT_EXPR
            and normalise(self.check) == CANONICAL_TENANT_EXPR
        )


@dataclass(frozen=True)
class ForeignKey:
    name: str
    columns: tuple[str, ...]
    target: str
    target_columns: tuple[str, ...]

    @property
    def is_composite_by_tenant(self) -> bool:
        """``tenant_id`` en los dos lados, en la misma posición."""
        return any(
            col == "tenant_id" and ref == "tenant_id"
            for col, ref in zip(self.columns, self.target_columns, strict=True)
        )


@dataclass
class ClientTable:
    """Una tabla con ``tenant_id``, con lo que el catálogo dice de ella."""

    name: str
    rls_enabled: bool
    rls_forced: bool
    columns: frozenset[str]
    policies: list[Policy] = field(default_factory=list)
    foreign_keys: list[ForeignKey] = field(default_factory=list)


def qualified(schema: str, table: str) -> str:
    """``jobs`` en ``public``; ``qa.threads`` fuera de él."""
    return table if schema == "public" else f"{schema}.{table}"


_TABLES_SQL = sa.text(
    """
    SELECT c.oid, n.nspname, c.relname, c.relrowsecurity, c.relforcerowsecurity,
           ARRAY(SELECT a.attname::text FROM pg_attribute a
                  WHERE a.attrelid = c.oid AND a.attnum > 0 AND NOT a.attisdropped)
      FROM pg_class c
      JOIN pg_namespace n ON n.oid = c.relnamespace
     WHERE c.relkind IN ('r', 'p')
       AND NOT c.relispartition
       AND n.nspname <> ALL(:system)
       AND n.nspname NOT LIKE 'pg_temp%'
       AND n.nspname NOT LIKE 'pg_toast_temp%'
    """
)

_POLICIES_SQL = sa.text(
    """
    SELECT p.polrelid, p.polname, p.polcmd::text, p.polpermissive,
           ARRAY(SELECT CASE WHEN r = 0 THEN 'public' ELSE pg_get_userbyid(r)::text END
                   FROM unnest(p.polroles) AS r),
           pg_get_expr(p.polqual, p.polrelid),
           pg_get_expr(p.polwithcheck, p.polrelid)
      FROM pg_policy p
    """
)

# ``conparentid = 0``: las FK que una partición hereda de su tabla padre son
# copias de la del padre, que es la que se comprueba.
_FKS_SQL = sa.text(
    """
    SELECT con.conrelid, con.conname, con.confrelid,
           ARRAY(SELECT a.attname::text
                   FROM unnest(con.conkey) WITH ORDINALITY AS k(num, ord)
                   JOIN pg_attribute a ON a.attrelid = con.conrelid AND a.attnum = k.num
                  ORDER BY k.ord),
           ARRAY(SELECT a.attname::text
                   FROM unnest(con.confkey) WITH ORDINALITY AS k(num, ord)
                   JOIN pg_attribute a ON a.attrelid = con.confrelid AND a.attnum = k.num
                  ORDER BY k.ord)
      FROM pg_constraint con
     WHERE con.contype = 'f' AND con.conparentid = 0
    """
)


async def all_tables(session) -> dict[int, ClientTable]:
    """Todas las tablas de la aplicación (no solo las de cliente), por ``oid``."""
    rows = (await session.execute(_TABLES_SQL, {"system": list(_SYSTEM_SCHEMAS)})).all()
    tables = {
        oid: ClientTable(
            name=qualified(schema, rel),
            rls_enabled=enabled,
            rls_forced=forced,
            columns=frozenset(cols),
        )
        for oid, schema, rel, enabled, forced, cols in rows
    }
    for relid, name, cmd, permissive, roles, using, check in (
        await session.execute(_POLICIES_SQL)
    ).all():
        if relid in tables:
            tables[relid].policies.append(
                Policy(name, cmd, permissive, frozenset(roles), using or "", check or "")
            )
    for relid, name, target, cols, refs in (await session.execute(_FKS_SQL)).all():
        if relid in tables and target in tables:
            tables[relid].foreign_keys.append(
                ForeignKey(name, tuple(cols), tables[target].name, tuple(refs))
            )
    return tables


async def client_tables(session) -> dict[str, ClientTable]:
    """Las tablas con ``tenant_id``, por nombre. Las FK guardan su destino por
    nombre, así que una FK hacia una tabla de cliente se reconoce con
    ``fk.target in client_tables``."""
    return {t.name: t for t in (await all_tables(session)).values() if "tenant_id" in t.columns}
