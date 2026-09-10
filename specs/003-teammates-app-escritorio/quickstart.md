# Quickstart — validar la 003 de punta a punta

Prerrequisitos: la 002 funcionando (máquina emparejada, cliente vinculado con
directorio), API en `:8000`, consola en `:3110`, Redis y Postgres del
`docker-compose`, Python 3.11 con `uv`, Node 22 con `pnpm`.

## 1. Plataforma

```bash
cd apps/api && uv run alembic upgrade head
uv run pytest tests/isolation/test_31_teammate_roster_scope.py tests/isolation/test_32_teammate_thread_two_axes.py tests/isolation/test_33_teammate_catalog_is_subset.py tests/isolation/test_34_local_policy_cannot_widen.py -x
uv run pytest tests/integration/test_teammates_*.py tests/integration/test_local_dispatch.py -x
uv run pytest tests/isolation/ -x   # CE-011: 001 y 002 siguen en verde
```

Esperado: verde. `test_console_scope` recoge solas las rutas nuevas de
`/console/teammates/*`.

## 2. Paquete compartido y consola

```bash
pnpm -F @nexus/companion-ui test
pnpm -F @nexus/console test && pnpm -F @nexus/console typecheck && pnpm -F @nexus/console lint
```

Esperado: los 12 tests del Companion pasan desde el paquete; el cajón de la
consola sigue igual; la página de equipo muestra el techo de ejecución local
para owner/admin y nada de teammates en ninguna otra página.

## 3. Escritorio

```bash
cd apps/desktop && pnpm test          # app-ipc, no-credentials-over-ipc, sse, app-state, notifications-policy, session-isolation (+auphere-app)
pnpm build                            # tsc + vite (dist/app) + preloads
AUPHERE_CONSOLE_URL=http://localhost:3110 AUPHERE_API_URL=http://127.0.0.1:8000 NODE_ENV=development ./node_modules/.bin/electron .
```

## 4. El recorrido (CE-002, CE-003, CE-004, CE-008)

1. Abrir la app: se ve el roster (vacío → «crea el primero»). Crear «Sofía ·
   Atención al cliente» con `read` y `contact`; crear «Nilo · Desarrollo» con
   `write` y ejecución local.
2. Escribir a Nilo: «lista los ficheros del directorio de cultor y crea
   NOTAS.md con la fecha». La tarjeta de ejecución enseña `ls`/`touch` (o el
   ejecutable en lista blanca del cliente), argumentos y directorio; elegir
   *una vez*. Ver `exec.dispatched` → la app ejecuta → `exec.completed`; el
   fichero existe **dentro** del `workdir` y no fuera.
3. Repetir con *siempre*: no vuelve a preguntar. En la consola, poner el techo
   del partner en `preguntar siempre`: en la app, Cuenta muestra la preferencia
   acotada y la tarjeta vuelve a preguntar.
4. Pedir un ejecutable fuera de la lista blanca: denegado sin tarjeta, con
   estado en el hilo y fila en `/workstation/executions`.
5. Encargar a Sofía algo que proponga un cambio; **cerrar la app**; esperar > 15
   min; abrir: aviso del SO «Sofía espera una decisión», Pendientes lo lista,
   la tarea está `esperándote`, la acción **no** caducó. Aprobar en Pendientes:
   la tarjeta del hilo se marca en < 2 s.
6. Con una segunda persona del partner: ve los dos teammates y **no** ve los
   hilos de la primera.
7. Cuenta: el número de consumo coincide con `/usage` de la consola.

## 5. Auditorías de UI (CE-010)

`ui-states-checklist`, `a11y-audit`, `responsive-audit`, `design-tokens` sobre
`apps/desktop/src/app` y `packages/companion-ui`: sin 🔴.
