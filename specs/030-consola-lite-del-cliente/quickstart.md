# Quickstart: comprobar la consola lite de punta a punta

## Preparación

```bash
docker compose up -d                                  # Postgres, Redis, Mailhog, API
cd apps/api && uv run alembic upgrade head            # hasta 0153
uv run python scripts/dev_seed_console_volume.py      # partner con clientes y actividad
uv run python scripts/dev_seed_client_access.py \
  --client flor-y-encanto --modules panel,inbox,usage \
  --email valeria@minegocio.test                      # acceso + invitación (imprime el enlace)
```

Consola en `http://localhost:3110`, admin en su puerto habitual. Los correos
llegan a Mailhog (`http://localhost:8025`).

## Iteración 1 — la puerta y lo que ya existe

1. **Admin → Tenants → Flor y Encanto → Acceso.** Activar con Panel y Consumo e
   invitar un correo. Esperado: invitación pendiente; Bandeja no elegible si el
   tenant no tiene WhatsApp; la Auditoría dice el operador.
2. **Abrir el enlace del correo**, crear contraseña, entrar. Esperado: barra
   con Panel y Consumo, insignia «lite», al pie la persona y el negocio.
3. **Probar la frontera:** escribir a mano `/clients`, `/audit`, `/team`,
   `/billing`. Esperado: vuelve al Panel, sin pantalla de explicación.
4. **Comparar cifras:** entrar como owner del partner en otra ventana y abrir
   Consumo con ese cliente elegido. Esperado: gasto del mes, saldo y gasto por
   día idénticos al céntimo (CE-003).
5. **Revocar** a la persona en el admin y recargar la consola del cliente.
   Esperado: página de sin acceso.

```bash
cd apps/api && uv run pytest tests/isolation/test_lite_route_scope.py tests/isolation/test_lite_client_vs_client.py -x
```

## Iteración 2 — la Bandeja

1. Activar Bandeja (el tenant necesita un canal de WhatsApp conectado; en local,
   `scripts/dev_seed_console_volume.py` crea uno simulado).
2. Simular un mensaje entrante:
   `uv run python scripts/dev_inbound_message.py --client flor-y-encanto --from +5491140932275 --text "Hola"`.
   Esperado: aparece arriba en la Bandeja, sin leer, en < 5 s, sin recargar.
3. Hacer escalar al agente (mensaje que pida un reembolso, o
   `scripts/dev_inbound_message.py --escalate "reembolso"`). Esperado: aviso en
   el hilo con el motivo, «Necesita humano», campana y correo en Mailhog; el
   agente no responde al siguiente mensaje, que llega al mismo hilo.
4. «Tomar el control», escribir y enviar. Esperado: el mensaje sale con estado;
   en una segunda ventana con otra persona, la acción con estado viejo recibe el
   estado real (412).
5. Devolver al agente y simular otro mensaje. Esperado: responde sin volver a
   saludar.
6. Resolver; simular un mensaje del contacto. Esperado: se reabre y responde el
   agente.
7. Simular un mensaje con más de 24 h. Esperado: el cuadro dice que la ventana
   está cerrada y no deja enviar.

```bash
cd apps/api && uv run pytest tests/isolation/test_lite_bodies_only_in_inbox.py tests/isolation/test_contact_notes_never_reach_agent.py -x
```

## Iteración 3 — varios agentes

1. Consola del partner → el cliente → Agente → «Nuevo agente» («Agente de
   ventas», plantilla), publicar. En Canales, asignar el segundo número a ventas.
2. Simular un mensaje a cada número. Esperado: responde el agente de cada uno;
   la Bandeja del cliente enseña la etiqueta de agente y el filtro por agente.
3. Consumo lite: tabla de gasto por agente y filtro en la gráfica; la suma de
   agentes es el total.
4. Un cliente con un solo agente: nada de la consola habla de agentes en plural,
   y su batería de evaluación da lo mismo que antes (CE-006).

```bash
cd apps/api && uv run pytest tests/isolation/test_agent_scope_within_tenant.py -x
```

## Antes de fusionar

```bash
./scripts/verify.sh
cd apps/console && pnpm exec playwright test e2e/lite.spec.ts    # a11y 360/1920, ES/EN, como cliente
```
