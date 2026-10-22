# Bug Verification: el LISTEN del dispatcher de salida no conecta nunca en producción

- **Slug**: listener-de-salida-no-conecta
- **Tested**: 2026-10-22 (local)
- **Assessment**: ./assessment.md
- **Fix**: ./fix.md
- **Result**: verified en local; sin desplegar

## Red before the fix

Reproducción contra asyncpg real, con contraseñas que RDS puede generar:

| Contraseña | DSN a asyncpg (antes) | SQLAlchemy |
|---|---|---|
| `ab[cd`, `ab]cd` | `ValueError: Invalid IPv6 URL` | intacta |
| `a[b]c` | `ValueError: … does not appear to be an IPv4 or IPv6 address` | intacta |
| `x#y` | `ValueError: invalid literal for int()` | intacta |
| `x?y` | `ValueError: bad query field` | intacta |

`test_outbound_listen_dsn.py` reescrito: 8 en rojo antes del arreglo.

## Green after the fix

`test_outbound_listen_dsn.py`: 8 passed — entre ellas una que llama a
`asyncpg.connect` de verdad con `ab[cd` y llega a abrir el socket (`OSError`
contra el puerto 1 de loopback) en vez de morir al parsear.

## Not covered

La contraseña real de Aurora no se ha leído.
