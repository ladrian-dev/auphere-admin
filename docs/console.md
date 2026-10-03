# La consola de partners — spec viva

> Qué existe hoy en `apps/console` y en `/console/*` de `apps/api`, en línea
> con `kb/Auphere/nexus/architecture/console-map.md` (el mapa pantalla →
> acción → endpoint → tabla vive allí; aquí, las reglas). Se actualiza en el
> mismo commit que cambia el comportamiento (constitución §IX).

## Qué es

Una aplicación Next.js (App Router, BFF sin base de datos) donde un
**partner** —una agencia o integrador— opera a sus **clientes**: crea el
cliente, le asigna cupo, configura y publica su agente, conecta sus canales e
integraciones y observa lo que pasa. La API decide; la consola pinta y dice
«no puedes» antes del viaje con el mismo mapa de permisos
(`src/lib/permissions.ts` ↔ `core/console_auth.py`).

## El círculo que cierra (spec 016)

1. **Crear cliente** (`/clients/new`): cuatro etapas separadas —crear, generar
   el agente desde la plantilla, publicar, activar— cada una con su reintento.
   Publicar es `agents:write`; activar es `clients:write`. La ficha aterriza en
   `#setup` con lo que falta y su acción a un clic (`components/clients/health.ts`).
2. **Cupo** (`/usage`): la unidad es **créditos**. «Sin cupo» significa lo
   mismo en la ficha, la lista, la portada y el aviso que en la puerta del canal
   (`metering/wallet.py::quota_state`). Cuando un turno se salta por falta de
   cupo, el partner recibe `client.out_of_quota` (campana + correo, uno por
   cliente y día); el cliente final no recibe nada distinto. Mover cupo es
   **una** llamada transaccional (`POST /console/wallet/allocations/move`).
3. **Agente**: ajustes estructurados, herramientas, habilidades, conocimiento y
   la tarjeta **Modelo** (`GET /console/models` con `relative_cost`, «×N
   créditos»). Cambiar el modelo se aplica en el siguiente turno y se audita
   (`console.model.update`); si el plan deja de incluirlo, el binding se borra
   y llega `client.model_reset`.
4. **Canales**: «Conectar WhatsApp» es el Embedded Signup real cuando el entorno
   tiene `NEXUS_META_APP_ID` y un `NEXUS_META_CONFIG_ID_*`; sin ellos, la nota
   «lo conecta Auphere» (sin botón). Al volver, el cliente se activa si puede
   operar y la respuesta trae `client_status` y `health`. Un número de otro
   cliente es 409 `number_in_use`; cualquier fallo deja el signup sin rastro.
5. **Integraciones**: AgendaPro se **enlaza por su agenda pública**
   (`PUT …/integrations/agendapro/public-url`, solo `https` en `agendapro.com`);
   nunca se piden credenciales desde la consola. Un conector por clave de API
   se guarda **y** sincroniza en la misma llamada; la respuesta dice qué pasó
   (`last_sync`), y las etiquetas de sus campos van en el idioma del partner
   (`connectors.field.{slug}.{campo}`).

## Reglas que no se negocian

- **Ningún cuerpo lleva `partner_id` ni `tenant_id`**: salen del principal y del
  `ref`. Un cliente ajeno es el mismo 404 opaco que uno inexistente
  (`tests/isolation/test_console_scope.py`).
- **Toda acción de servidor comprueba su rol** con el permiso exacto que la API
  exige, y tiene su test permitido/denegado con el arnés `src/test/actions.ts`
  (una carpeta, un `__tests__/actions.test.ts`). La única sin `can()` es aceptar
  una invitación: todavía no hay principal.
- **Sin permiso, el control no existe** —no se muestra deshabilitado.
- **La pantalla no miente** (§V): un estado que la API no puede leer se pinta
  como error o ausencia, nunca como «todo bien» ni como «agotado».
- **Las acciones nuevas se auditan** con vocabulario sembrado
  (`console_audit_vocabulary`; migración de datos por spec) y sin secretos en
  `after_json` (`tests/unit/test_console_audit_vocab_016.py`).

## Cómo se comprueba

```bash
cd apps/console && pnpm typecheck && pnpm lint && pnpm test   # Node ≥ 22.12
cd apps/api && uv run pytest tests/isolation -q               # bloquea el merge
./scripts/verify.sh                                           # todo, antes de fusionar
```

## Lo que queda fuera (y dónde está)

- Rediseño por flujo (ficha en tres grupos, capacidades dinámicas, tema claro y
  oscuro): spec 017, KB `PLAN-ACCION-CONSOLA-2026-09-22.md` bloque D.
- WhatsApp solo se puede probar de punta a punta en staging con las claves de
  Meta; en local se prueba la ausencia diseñada.
