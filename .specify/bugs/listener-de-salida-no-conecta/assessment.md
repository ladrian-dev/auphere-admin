# Bug Assessment: el LISTEN del dispatcher de salida no conecta nunca en producción

- **Slug**: listener-de-salida-no-conecta
- **Created**: 2026-10-22
- **Source**: logs de `/nexus/prod/egress`; ya anotado en `PLAN-PENDIENTE-CORTE-2026-09-08` (KB) como ruido
- **Verdict**: valid
- **Severity**: medium — la entrega no se pierde, pero cada respuesta espera al barrido

## Symptom

`outbound.listener.reconnecting` con `error: "Invalid IPv6 URL"` cada 2 s:
**43 167 al día**, todos los días de los 30 que guarda CloudWatch. El dispatcher
nunca recibe el `NOTIFY` y vive del barrido de 30 s. Ejemplo: la respuesta de
`demo-lorenzo` se generó a las 12:21:40 y salió a las 12:21:55.

## Reproduction

```python
asyncpg.connect("postgresql://nexus:ab[cd@host:5432/nexus")
# ValueError: Invalid IPv6 URL
```

asyncpg parsea el DSN con `urllib`, que toma un `[` o `]` sin pareja en la
contraseña por una IPv6 mal formada. La contraseña de Aurora la genera RDS
(`manage_master_user_password = true`), que puede incluir corchetes. SQLAlchemy
parsea el mismo URL sin problema, y por eso el resto de la aplicación conecta.
No se ha leído el secreto para comprobarlo: el mensaje solo puede salir de ese
caso, y la reproducción lo confirma.

## Root cause

`_asyncpg_dsn()` pasa el URL como cadena a `asyncpg.connect`. Desde que el
LISTEN se movió a `database_url_direct` (Aurora, 2026-08-19), ese URL lleva la
contraseña generada por RDS.

## Suspected Code Paths

- `apps/worker/src/nexus_worker/streams/outbound.py` — `_asyncpg_dsn`, `_run_listener`.

## Possible Remediation

Descomponer el URL con `sqlalchemy.engine.make_url` y pasar argumentos con
nombre a `asyncpg.connect`.
