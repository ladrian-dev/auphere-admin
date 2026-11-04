# Validación: Invitar al propietario

## Pruebas (sin proveedor real)

```bash
export NEXUS_DATABASE_URL=postgresql+asyncpg://nexus:nexus@localhost:5433/nexus_test_052
export NEXUS_REDIS_URL=redis://localhost:6379/14
cd apps/api
uv run pytest tests/integration/test_admin_owner_invitation.py tests/isolation/test_owner_invitation_scope.py tests/isolation/test_console_scope.py tests/isolation/test_55_email_owner_tagging.py -q
```

```bash
cd apps/admin
pnpm vitest run "src/app/(dashboard)/partners"
```

## En local, de punta a punta

`NEXUS_EMAIL_DELIVERY` sin definir: en local el modo es `log`, no sale nada y el enlace queda en `email.suppressed`, `links.ACCEPT_URL`.

| Paso | Resultado esperado |
|---|---|
| Crear un partner en `/partners/new` | Vista «Invitación enviada», misma URL, con dirección, fecha y enlace |
| Abrir el enlace en la consola | Pide contraseña; al aceptar, dentro como propietaria |
| Equipo | La persona activa, sin formulario |

## En staging (CE-001), solo con una dirección de prueba propia

En staging una invitación es un correo de acceso y **sale de verdad**, a la dirección que se escriba.

1. Crear un partner en `/partners/new` con un buzón propio. Se ve «Invitación enviada», la fecha y el enlace, en la misma URL.
2. Sin hacer nada más, llega el correo en español, con «Auphere» de quien invita.
3. Abrir el enlace, elegir contraseña y entrar: consola del partner, con rol de propietaria, sin «sin acceso».
4. En la ficha: Equipo muestra a la persona activa y ni formulario ni cabecera de «Sin propietario activo». Auditoría da las frases con el correo del operador; la de la consola, con «Auphere».
5. Otro partner: reenviar, y el enlace viejo da «no encontrado». Revocar, y ninguno abre. Invitar a otra dirección, y el contacto cambia con ella.
6. En CloudWatch, `/console/invitations/` sale con `[token]`.
