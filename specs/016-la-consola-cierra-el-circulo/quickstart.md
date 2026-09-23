# Quickstart de validación — spec 016

Cómo demostrar que el círculo cierra. Local para todo menos WhatsApp; staging para WhatsApp.

## Requisitos

- Stack local (`preview_start api` / `preview_start console`, o `docker compose up -d` + `uv --directory apps/api run uvicorn nexus_api.main:app --port 8000` + `pnpm --dir apps/console dev`), partner `demo-audit` con owner (ver `apps/console/README.md`).
- Node ≥ 22.12 o `NODE_OPTIONS=--experimental-require-module` para Vitest.
- Para la historia 1: staging con `NEXUS_META_APP_ID` y los `CONFIG_ID` en Vercel, y un número de prueba de Meta.

## Suites automáticas (criterios de aceptación)

```bash
# API: cupo, salud, avisos, modelo, AgendaPro, conectores
cd apps/api && uv run pytest tests/integration/test_console_wallet.py tests/integration/test_wallet_alerts.py \
  tests/integration/test_console_models.py tests/unit/test_endpoint_console_channels.py \
  tests/unit/test_endpoint_console_home_usage.py tests/unit/test_endpoint_console_tools.py -q
# Aislamiento (bloquea el merge)
cd apps/api && uv run pytest tests/isolation -q
# Worker: turno saltado → aviso
cd apps/worker && uv run --directory ../api pytest tests/unit -k "out_of_quota or dispatcher" -q
# Consola: acciones de servidor (permitido/denegado), wizard, reductor, render
cd apps/console && NODE_OPTIONS=--experimental-require-module pnpm exec vitest run
# Accesibilidad y responsive sobre la app real
cd apps/console && E2E_EMAIL=… E2E_PASSWORD=… pnpm exec playwright test
```

## Recorridos manuales

1. **Sin cupo (Historia 2)** — en `/usage`, bajar el tope de `panaderia-la-espiga` a 0 → enviar un mensaje por el canal (o simular el turno saltado con el test del worker) → en menos de un minuto: ficha «Falta: cupo», lista con el punto, portada con la incidencia, campana con el aviso; `select kind, dedupe_key from console_notifications` muestra una fila `client.out_of_quota` de hoy; un segundo turno no crea otra. Asignar cupo → los tres estados desaparecen.
2. **Mover cupo (Historia 2)** — con dos clientes, mover 20.000: ambos topes cambian a la vez; `select sum(cap) from partner_allocations where partner_id=…` no cambia. Repetir con `qty > cap` → 422 legible y suma intacta. Test de fallo inyectado: `test_move_allocation_is_atomic` fuerza el fallo tras bajar el origen y comprueba que no queda rebajado.
3. **Alta por etapas (Historia 3)** — `/clients/new`: cuatro etapas; con el test `wizard-state` se fuerza el fallo en «Activar» y se comprueba que «Publicar» no se repite; en la ficha, «Falta: WhatsApp» enlaza a Canales.
4. **Modelo (Historia 4)** — `/clients/{ref}/agent/settings`: tarjeta Modelo con «×N créditos»; elegir otro, guardar, enviar un turno en el Playground → el inspector muestra el modelo nuevo; `select action from audit_log order by created_at desc limit 1` = `console.model.update`.
5. **AgendaPro (Historia 5, R6 según la investigación)** — `/clients/{ref}/tools`: «Enlazar la agenda» con una URL pública de AgendaPro → conector conectado, herramientas `booking.*` activables; la auditoría registra `console.integration.agendapro_url`; ninguna credencial en ninguna parte.
6. **Conector por clave (Historia 5)** — WooCommerce con una clave de prueba: al guardar, la tarjeta muestra «Conectado · N herramientas» sin pulsar nada más; con una clave inválida, «Guardado, pero no se pudo sincronizar: credenciales rechazadas · Reintentar».
7. **WhatsApp (Historia 1, staging)** — Canales → Conectar → Meta → volver: número activo, ficha «Listo», onboarding «Conecta un canal» hecho, `tenants.status = active`. En local (sin claves): la nota «lo conecta Auphere», sin botón.

## Qué tiene que salir

- CE-001…CE-008 de la spec, cada uno con la prueba que lo demuestra en `tasks.md`.
- `./scripts/verify.sh` en verde y `pnpm check` en verde antes de fusionar a `develop`.
