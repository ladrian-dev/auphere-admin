# Quickstart: comprobar la edición de plantillas (075)

## Requisitos previos

- `develop` con la 075 desplegada en staging, o la pila local (`docker compose up -d`) con un cliente que tenga WhatsApp conectado por Meta.
- Una plantilla desechable en la cuenta de pruebas de Meta (`Test WhatsApp Business Account`), o en la cuenta del cliente de staging.

## En local

```bash
./scripts/verify.sh lint
cd apps/api && uv run pytest tests/unit/test_template_edit_rules.py tests/unit/test_endpoint_template_edit.py -x
cd apps/api && uv run pytest tests/unit/test_authentication_templates.py tests/unit/test_endpoint_admin_template_create.py -x
cd apps/api && uv run pytest tests/isolation/test_template_edit_scope.py tests/isolation/test_console_scope.py -x
cd apps/channels && uv run pytest tests/test_meta_client.py -x
cd apps/worker && uv run pytest tests/ -k "cobranza" -x
pnpm --filter @nexus/ui test -- template-editor template-rules
pnpm --filter console test -- templates-section template-composer
pnpm --filter admin test -- whatsapp-templates
pnpm --filter @nexus/ui build && pnpm --filter console build && pnpm --filter admin build
```

Las suites completas solo corren de camino a `main`. Aquí, lint y lo que se toca. Se añaden el worker, porque los nombres de cobros cambian de sitio, y el `next build` de la consola y del panel, porque el editor cambia de paquete. Son los dos olvidos que ya rompieron la tubería.

## En staging (consola de partners)

1. **Rechazada o pausada (historia 1).** Abrir un cliente → Canales → WhatsApp → Plantillas. En una rechazada, pulsar «Editar».
   - Se ve el contenido actual y lo que se sugiere arreglar.
   - El nombre y el idioma salen como título.
   - Cambiar el texto y guardar.
   - **Esperado:** la fila enseña el estado que devuelve Meta y ya no el motivo de rechazo. En la auditoría hay `console.template.edit` con el antes y el después.
2. **Aprobada (historia 2).** Editar una aprobada.
   - **Esperado:** antes de mandar sale el aviso de 2.2, y la categoría no se ofrece como campo. Al confirmar, la fila enseña el estado de Meta.
3. **Bloqueada.** Con una plantilla que lleve imagen en la cabecera: no aparece «Editar», y el detalle dice por qué.
4. **Reservas (historia 3).** En `reserva_recordatorio`, quitar `{{nombre}}` y guardar.
   - **Esperado:** no deja guardar y nombra la variable.
   - Corregir sin tocar las variables: la pantalla de Reservas de la consola lite enseña el estado nuevo.
5. **Cambio ajeno.** Abrir el editor, cambiar la plantilla en WhatsApp Manager y guardar en la consola.
   - **Esperado:** aviso de que cambió y opción de recargar.
6. **Crear una de autenticación (requisito 10).** «Nueva plantilla» → Autenticación.
   - **Esperado:** en lugar del mensaje y los botones se piden el botón, la caducidad y el aviso. La vista previa es el texto fijo de Meta en español, y con otro idioma dice que Meta lo pone en ese idioma.
   - Mandarla: Meta la recibe con el formato de autenticación y sale en la lista «En revisión».
7. **«Duplicar» una de autenticación rechazada.**
   - **Esperado:** el editor se abre en Autenticación con su botón, su caducidad y su aviso, y el nombre `<nombre>_v2`.

## En staging (panel de operador)

Repetir 1, 2 y 3 desde Clientes → integraciones → Plantillas de WhatsApp. El editor es el mismo y la auditoría dice `admin.template.edit`.

8. **Crear desde el panel (requisito 10.5).** «Nueva plantilla» abre el mismo editor que la consola.
   - Crear una de Utilidad con cabecera, `{{nombre}}` con su ejemplo y un botón.
   - **Esperado:** Meta la recibe con `parameter_format: NAMED`, que el panel antes no mandaba. La auditoría dice `channel.whatsapp.template_created`.
   - Crear una de Autenticación, como en el paso 6.
9. **Cliente de solo envío (requisito 10.6).** En un cliente de solo envío, ir a «Puesta en marcha» → «Plantilla de código» → canales → el número → Plantillas.
   - **Esperado:** el mismo diálogo y el mismo editor. Crear la de autenticación y ver que el paso pasa a «en revisión».
