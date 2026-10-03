# Fase 0 — investigación

Seis decisiones, medidas contra el código el 2026-09-30. Ninguna depende de
nada fuera del repositorio.

---

## D0 · Lo que ya existe y no hay que rehacer

| Pieza | Dónde | Estado |
|---|---|---|
| El modo «solo administradores»: `policies.admin_access.admin_only` + `admin_phones` (+ `admins` con nombre y rol) | `core/admin_gate.py` (`admin_only_suppresses`, `sender_is_admin`, `usable_admin_phones`, comparación por los últimos 10 dígitos, mínimo 7) | existe; **es el mecanismo** |
| El agente calla con quien no está en la lista y el mensaje entrante se guarda | `apps/worker/.../runtime/dispatcher.py` (`pipeline.skipped.not_admin`, después de persistir el entrante) | existe |
| El webhook no marca como leído lo que el agente no va a responder | `api/webhooks/meta.py` (`read_receipt_suppressed_not_admin`) | existe |
| Fijar la lista y promover una versión nueva al momento | `AgentConfigService.set_admin_access` → `PUT /v2/partners/clients/{ref}/admins` (clave de API con permiso «aprovisionar») | existe; **sin pantalla** |
| El asistente de alta pide los números cuando la plantilla es de solo administradores | `api/console/seed_templates.py` (`policies.admin_access.admin_phones` obligatorio si el seed trae `admin_only`) | existe |
| Ajustes del agente en la consola | `api/console/agent_settings.py` (GET/PUT sobre el borrador, `ensure_draft`), `services/agent_console_policy.py` (`ConsolePolicy`, solo `policies.console`), `components/agent-tools/agent-settings-form.tsx` + `settings-schema.ts` (zod espejo) | existe; la consola **nunca** toca `admin_access` |
| Estado del cliente en cabecera y lista | `ClientSummaryOut` / `ClientOut` (`setup`, `serving_since`), `components/clients/client-header-model.ts`, `clients-table.tsx`, `status-badge.tsx` | existe |
| Conversaciones en la consola | `api/console/conversations.py`: **lista con agregados** (entrantes, salientes, fallidos) y estadísticas; no hay vista por mensaje | existe; la señal de «sin respuesta» tiene que caber en la lista |
| El Companion lee la ficha del cliente | `companion/tools/catalog.py` → `console.get_client` sobre el mismo endpoint que la pantalla | existe; lee lo que la API devuelva |
| Normalizar teléfonos | `to_e164` (el que usa la API de partners) | existe |

---

## D1 · La lista vive donde el runtime la lee: `policies.admin_access`

**Alternativas**: (a) un bloque nuevo `policies.console.audience` que la
API traduzca a `admin_access` al guardar; (b) que la consola lea y escriba
`admin_access` directamente, presentado como «audiencia». Se descarta (a):
dos copias del mismo dato se desfasan (la API de partners seguiría
escribiendo solo `admin_access`).

**Decisión**: (b). `admin_access` sigue siendo la única verdad y el runtime
no cambia. La consola lo enseña como `audience` en `AgentSettingsOut` y lo
recibe en `AgentSettingsIn`:

```json
{"audience": {"mode": "everyone" | "list",
              "numbers": [{"phone": "+56991919125", "name": "Daniel, ventas"}],
              "locked": false}}
```

- **GET**: `audience` se deriva del `admin_access` de la versión que se
  edita (borrador si hay, si no la activa): `admin_only` → `list`, sin él →
  `everyone`; `numbers` sale de `admins` (nombre) y `admin_phones`.
- **PUT**: además de `merge_console_policy` para `policies.console`, la API
  escribe `admin_access` en el borrador: `admin_only = (mode == "list")`,
  `admin_phones` normalizados con `to_e164` y sin duplicados, `admins` con
  nombre y `role: "full"`. Con `mode == "everyone"` se escribe
  `admin_only = false` y se conservan los números guardados (volver a la
  lista no obliga a reescribirla).
- **Validación** (422 con el número que falla): un teléfono que `to_e164`
  no acepte o que `usable_admin_phones` descarte (menos de siete cifras);
  `mode == "list"` con cero números útiles.
- **Bloqueo** (Historia 3): `locked = true` cuando la plantilla del cliente
  (`seed_template_ref` → `load_seed_template(...).policies_default.admin_access.admin_only`)
  es de solo administradores; un PUT con `mode == "everyone"` sobre un
  cliente bloqueado responde 409 `audience_locked`.
- Los roles por número no se enseñan (Requisito 5.3): la consola escribe
  siempre `full`; si la API de partners puso `readonly`, la consola lo
  conserva al reescribir la lista para ese mismo número.

---

## D2 · Se aplica al publicar, y viaja con las versiones

Clarificación del owner (opción A). El borrador lleva `admin_access` como
lleva `policies.console`; publicar lo aplica en el siguiente turno (el
promote ya avisa al worker). Revertir a una versión anterior devuelve la
lista de esa versión, como todo lo demás.

**Convivencia con la API de partners**: `set_admin_access` clona la activa,
cambia `admin_access` y promueve al momento. Si en ese momento existe un
borrador de consola, el borrador conserva la lista anterior y, cuando se
publique, la reemplazará: «el último que guarda gana» (Requisito 5.1). La
pantalla lo hace visible porque `audience` se lee de la versión que se
edita y la barra de borrador ya dice qué cambia («Cambia: Ajustes»).

---

## D3 · La pantalla dice «responde solo a N números»

**Decisión**: `ClientSummaryOut` y `ClientOut` ganan
`audience: {"mode": "everyone"|"list", "count": N}` leído de la versión
**activa** (lo que atiende de verdad), una vez por página en la lista (una
consulta sobre `agent_configs` activas de los tenants del partner, como ya
se hace con `setup`).

- Cabecera de la ficha: bajo «Atendiendo desde…», la línea «Responde solo
  a 5 números» con enlace a Ajustes del agente.
- Lista de clientes: insignia «Solo 5 números» (tono info) junto al estado.
- El Companion lo lee por `console.get_client` sin cambio propio
  (Requisito 3.3).

---

## D4 · Conversaciones enseña el motivo: un campo nuevo en el mensaje

Hoy el entrante suprimido se guarda igual que cualquier otro; nada lo
distingue de un mensaje que el agente aún no ha respondido.

**Decisión**: columna `messages.skipped_reason` (`varchar(40)`, nula;
migración `0136_message_skipped_reason`). El dispatcher la rellena con
`not_admin` en el entrante que acaba de persistir cuando el gate suprime
(y queda lista para `send_only_channel` u otros motivos, fuera de esta
spec). La lista de Conversaciones gana `unanswered: {"count": N, "reason":
"not_admin"}` por conversación y en las estadísticas; la fila dice
«3 sin responder · número no permitido». Sin vista por mensaje no hace
falta más (D0).

**Alternativa descartada**: deducirlo cruzando `admin_access` con los
entrantes sin saliente. Falla en cuanto la lista cambia: un mensaje
suprimido ayer parecería «pendiente» hoy.

---

## D5 · La sección en el formulario

En `agent-settings-form.tsx`, después de «Escalado a humano» y antes de
«Aviso de IA»: sección **«A quién responde»** con dos opciones de radio
(*A todo el mundo* / *Solo a estos números*) y, con la segunda, un área de
texto donde cada línea es `+56 9 9191 9125 · Daniel, ventas` (el nombre es
opcional; también valen comas entre números). El espejo zod
(`settings-schema.ts`) parsea el texto a `numbers[]`, normaliza y señala la
línea que falla; el servidor valida otra vez (D1). Con `locked`, las radios
van deshabilitadas y una línea explica: «Este agente es el asistente del
negocio, no atiende a clientes finales; edita la lista, no el modo». Quien
solo mira ve todo deshabilitado, como el resto del formulario.

La auditoría existente «{actor} cambió los ajustes del agente de {client}»
cubre el guardado; publicar ya audita. Sin vocabulario nuevo.

---

## D6 · Aislamiento, licencias, medidor

- **Aislamiento**: ninguna garantía cambia. La lista es parte de
  `agent_configs` del tenant (RLS); el remitente lo pone el webhook a partir
  del canal, nunca la petición. Test de aislamiento: el PUT de A con
  `audience` no cambia el `admin_access` de B, y el barrido por OpenAPI de
  la ruta de ajustes no acepta `tenant_id` ni `sender`.
- **Licencias**: ninguna dependencia nueva.
- **Medidor**: nada nuevo; un mensaje suprimido no llega al modelo, como
  hoy.
