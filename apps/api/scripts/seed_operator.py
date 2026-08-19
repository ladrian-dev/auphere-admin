"""Alta de un operador del panel (ADR-034).

Sustituye al ``pnpm seed:admin`` de ``apps/admin``, que creaba el usuario
con Better Auth y Drizzle. Esa identidad ya no existe: vive en
``operator_auth.principals``, dentro de la API.

Idempotente en lo que importa: si el correo ya tiene principal **no le
reescribe la contraseña** (lo dice y sigue), y se limita a ajustar el rol
si se pidió uno distinto. Para cambiar una contraseña hay que pedirlo
explícitamente con ``--force-password``, que es la clase de cosa que no
debe pasar por descuido al re-ejecutar un script de alta.

Uso (lee ``NEXUS_DATABASE_URL`` del entorno):

    python scripts/seed_operator.py \\
        --email contacto@auphere.com --display-name "Auphere" --role admin

Sin ``--password`` genera una y la imprime UNA vez. Es lo razonable para el
alta inicial de un panel interno: no hay flujo de invitación por correo
—``email_enabled`` está apagado en producción— y teclear la contraseña de
otra persona en una línea de comandos deja el secreto en el historial del
shell y en los logs de la task.

Roles (sólo gatean el QA Playground, ver ``services/operator_identity.py``):
``admin`` · ``qa_operator`` (por defecto) · ``viewer``.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import secrets
import sys
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from nexus_api.services import operator_identity


async def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--email", required=True)
    ap.add_argument("--display-name", default=None)
    ap.add_argument(
        "--role",
        default=operator_identity.DEFAULT_ROLE,
        choices=["admin", "qa_operator", "viewer"],
    )
    ap.add_argument(
        "--password",
        default=None,
        help="si no se pasa, se genera una y se imprime una sola vez",
    )
    ap.add_argument(
        "--force-password",
        action="store_true",
        help="reescribe la contraseña de una cuenta que ya existe",
    )
    ap.add_argument(
        "--disable",
        action="store_true",
        help="revoca el acceso sin borrar la fila (deja el rastro de auditoría)",
    )
    args = ap.parse_args()

    url = os.environ.get("NEXUS_DATABASE_URL")
    if not url:
        print("NEXUS_DATABASE_URL is not set", file=sys.stderr)
        return 2
    # Los gestores de secretos guardan la forma ``postgresql://`` (que es la
    # que quieren psql y pgbouncer); el stack async necesita el driver
    # deletreado o SQLAlchemy va a buscar psycopg2, que no está en la imagen.
    if url.startswith("postgresql://"):
        url = url.replace("postgresql://", "postgresql+asyncpg://", 1)

    engine = create_async_engine(url)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    generated: str | None = None
    try:
        async with factory() as session, session.begin():
            existing = await operator_identity.get_by_email(session, args.email)

            if existing is None:
                password = args.password or secrets.token_urlsafe(18)
                generated = None if args.password else password
                account = await operator_identity.create_account(
                    session,
                    email=args.email,
                    password=password,
                    display_name=args.display_name,
                    role=args.role,
                )
                print(f"✓ operador creado {account.email} ({account.id}) rol={args.role}")
            else:
                account = existing
                print(f"· el operador {account.email} ({account.id}) ya existía")
                if args.role != account.role:
                    account.role = args.role
                    print(f"  rol actualizado a {args.role}")
                if args.password or args.force_password:
                    if not args.force_password:
                        print(
                            "  NO se reescribe la contraseña: añade --force-password "
                            "si de verdad quieres cambiarla"
                        )
                    else:
                        password = args.password or secrets.token_urlsafe(18)
                        generated = None if args.password else password
                        await operator_identity.set_password(session, account, password)
                        print("  contraseña reescrita")

            if args.disable:
                account.disabled_at = datetime.now(UTC)
                print("  cuenta DESHABILITADA (la fila se conserva)")
            elif account.disabled_at is not None:
                account.disabled_at = None
                print("  cuenta rehabilitada")
    finally:
        await engine.dispose()

    if generated:
        print()
        print("  contraseña generada (no se vuelve a mostrar):")
        print(f"    {generated}")
        print()
        print("  Entra en el panel y cámbiala si vas a usarla más de una vez.")
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
