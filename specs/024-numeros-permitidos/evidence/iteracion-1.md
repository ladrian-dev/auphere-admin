# Iteración 1 — local, 2026-09-30 (rama `024-numeros-permitidos`)

Consola local (`localhost:3110`, partner `demo-audit`, cliente
`panaderia-la-espiga`) contra la API local con la migración 0136 aplicada.

## Historia 1 — el partner limita a quién responde

1. Agente → Ajustes del agente → sección **«A quién responde»** con dos
   tarjetas: «A todo el mundo» (Cualquier persona que escriba recibe
   respuesta) y «Solo a estos números» (Para probar con tu equipo…).
2. Con la lista: una fila por número (teléfono + nombre opcional), «Añadir
   número», quitar por fila, «2 en la lista». Se escribieron
   `+56 9 9191 9125 · Daniel, ventas` y `34 666 261 967 · Owner`; al salir
   del campo el teléfono queda normalizado (`+56991919125`, `+34666261967`).
3. «Guardar borrador» → toast «Borrador v3 actualizado». Recargando la
   página, la lista persiste normalizada (viene de `admin_access` del
   borrador).
4. «Revisar y publicar» → la hoja muestra la fila **A quién responde ·
   Antes: A todo el mundo · Ahora: Solo a 2 números** junto al resto de
   ajustes.
5. «Publicar la versión 3» → v3 activa.

Errores comprobados por test (`agent-settings-form.test.tsx`): lista vacía
→ «Hace falta al menos un número.»; teléfono `12345` → error bajo su fila
«“12345” no es un número válido…», sin llamar a la acción.

## Historia 2 — la pantalla lo dice (local)

- Cabecera de la ficha: enlace **«Responde solo a 2 números»** hacia Ajustes
  del agente, junto a «Atendiendo desde…».
- Lista de clientes: insignia **«Solo 2 números»** al lado de «Activo» en
  Panadería La Espiga.
- Conversaciones: columna «Sin responder» y métrica «Sin responder (número
  no permitido)»; con datos por test
  (`test_endpoint_console_conversations_unanswered.py`). Con número real:
  iteración 2 en staging (T022).

## Historia 3 — bloqueo por plantilla

Por test (`test_an_admin_only_template_is_locked`,
`agent-settings-form.test.tsx`): con `cobranza_v1` el GET devuelve
`locked: true`, el PUT «A todo el mundo» responde 409 `audience_locked`, y
en el formulario la tarjeta «A todo el mundo» está deshabilitada con la
explicación. Comprobación en producción con Mouna: T025.

## Suites

- API: `test_agent_audience` 14 · `test_endpoint_console_agent_settings_audience` 7 ·
  `test_endpoint_console_clients_audience` 4 · `test_endpoint_console_conversations_unanswered` 2 ·
  aislamiento 2 · `test_console_scope` y `test_endpoint_console_home_usage` sin regresión (579 en la tanda).
- Worker: `test_dispatcher_admin_gate` 15.
- Consola: `audience-lines`, `agent-settings-form`, `draft-setting-value`, `settings-schema`; `typecheck` y `lint` (incluida la guarda `no-orphan-keys`) limpios.
