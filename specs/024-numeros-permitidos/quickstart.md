# Quickstart — spec 024

## Prerrequisitos

- Stack local (`preview_start api` y `preview_start console`), partner
  `demo-audit`, un cliente con versión activa (sirve `panaderia-la-espiga`)
  y otro creado con `cobranza_v1` para la Historia 3.
- Migrar la base local: `uv run --directory apps/api alembic upgrade head`
  (añade `messages.skipped_reason`).

## En local — la suite

```bash
uv run --directory apps/api pytest \
  tests/unit/test_agent_audience.py \
  tests/unit/test_endpoint_console_agent_settings_audience.py \
  tests/unit/test_endpoint_console_clients_audience.py \
  tests/unit/test_endpoint_console_conversations_unanswered.py \
  tests/isolation/test_console_agent_settings_audience.py -q
uv run --directory apps/api pytest /Users/matos/workspace/Auphere/auphere-admin/apps/worker/tests/unit/test_dispatcher_admin_gate.py -q
cd apps/console && pnpm test -- agent-settings audience-lines clients-table client-header
```

| Test | Criterio |
|---|---|
| `test_agent_audience` | `admin_access` ↔ `audience` en los dos sentidos; normaliza, deduplica, conserva `role`; `everyone` apaga `admin_only` y guarda los números; `locked` sale de la plantilla |
| `test_endpoint_console_agent_settings_audience` | GET/PUT de ida y vuelta; 422 con el teléfono que falla; 422 con lista vacía; 409 bloqueado; PUT sin `audience` no toca `admin_access`; lo que escribe la consola lo lee `GET /v2/partners/clients/{ref}/admins` igual (CE-004) |
| `test_endpoint_console_clients_audience` | lista y ficha con `audience` de la versión activa; nulo sin activa; una sola consulta por página |
| `test_endpoint_console_conversations_unanswered` | conteo por conversación y en stats a partir de `skipped_reason` |
| `test_console_agent_settings_audience` (aislamiento) | el PUT de A no cambia el `admin_access` de B; la ruta no acepta `tenant_id` ni `sender` |
| `test_dispatcher_admin_gate` | el entrante suprimido queda con `skipped_reason = not_admin`; el permitido, nulo; cero eventos de consumo (T-MET) |
| consola | el parseo de líneas; la sección guarda y enseña errores por línea; bloqueado deshabilita el modo; la tabla y la cabecera dicen «solo N números» |

## En la consola local — Historia 1 de punta a punta

1. Cliente → Agente → Ajustes del agente → «A quién responde» → *Solo a
   estos números* → dos líneas → Guardar borrador → Publicar.
2. Cabecera: «Responde solo a 2 números». Lista de clientes: insignia.
3. Playground: no aplica (no hay remitente). El gate se prueba con el test
   del worker y en staging.

## En staging — con número real (CE-002)

1. En un cliente con número conectado, activar la lista con el número del
   owner y publicar.
2. Escribir desde el número del owner: responde. Escribir desde otro
   número: no responde, el mensaje no queda en leído, y en Conversaciones
   la fila dice «1 sin responder · número no permitido».
3. Volver a *A todo el mundo*, publicar, escribir desde el otro número:
   responde.
4. Capturas de cabecera, lista y Conversaciones en `evidence/`.
