# PLAN-CO-08 · Piloto, límites y escalado a soporte

> Agente E de la Ola 2. Ejecuta §4, §5, §6, §8, §9, §10, §11 y §12 de
> [`CONTRACT-V2.md`](CONTRACT-V2.md) sobre §25, §23.2 y §17 de la
> investigación.
>
> **El contrato manda.** Donde este plan y el contrato difieran, gana el
> contrato; lo que aquí se decide es lo que el contrato delegó
> explícitamente en E: el vocabulario de `topic` (§4.2), el mecanismo de
> alerta interna (§4.3), el mecanismo de métricas (§11) y el contenido de la
> migración (§9).

---

## 0. La forma del cambio en una pantalla

```
 el Companion topa con una pared
      │  console.get_capabilities        ← lectura, always_allow, GET /console/capabilities
      │   └─ docs/companion/capabilities.yaml, versionado, mantenido a mano
      ▼
 support.request_help / support.request_capability     ← "propose", always_ask
      │  NO escriben. Calculan {category, topic, client_ref, need,
      │  checked, alternative, bridge} y lo dejan en toolbelt.pending
      ▼
 nodo plan → hitl.requested → interrupt() → resume:confirm
      ▼
 nodo execute → console.apply      ← la ÚNICA "mutates". Sigue siéndolo (E4)
      │           POST /console/support/tickets
      │            ├─ nextval('console_support_ticket_seq') → AU-<n>
      │            ├─ console_notifications (info, email=True)
      │            ├─ aviso interno: log estructurado + correo a Auphere
      │            └─ audit_log (actor companion:<user_id>)
      ▼
 driver → support.ticket{action_id, ticket_ref, category, topic, sla}
      ▼
 nodo verify → verify.result


 el partner se pasa del tope mensual
      POST …/threads/{id}/runs   → 409 budget_paused {used, cap, period, resets_at}
      POST …/runs/{id}/resume    → 202, intacto                      (E5)
      GET  cualquiera            → 200, intacto
      al cruzarlo en un turno    → budget.paused + run.completed{status:"paused"}
                                   con historia, respuesta parcial y tokens  (E6)
                                   (por TURNO, no por llamada al modelo — ver D8)
```

---

## 1. Decisiones que el contrato delegó

### D1 · El vocabulario de `topic` (§4.2)

`topic` es la **clave de agregación** del §25.2. Sin un espacio de nombres
estable, *«siete partners han pedido Shopify este trimestre»* no se puede
consultar; con prosa del modelo, tampoco.

Forma: `<familia>.<slug>`, con `slug` en `[a-z0-9]+([-_][a-z0-9]+)*` y el
total ≤ 60 caracteres. Seis familias, cerradas:

| Familia | Qué agrupa | Semillas |
|---|---|---|
| `connector.*` | un conector concreto | `connector.shopify` · `connector.hubspot` · `connector.stripe` · `connector.google_calendar` |
| `channel.*` | un canal de conversación | `channel.instagram` · `channel.tiktok` · `channel.voice` · `channel.email` |
| `capability.*` | una capacidad de la plataforma | `capability.evals_console` · `capability.node_canvas` · `capability.custom_reports` · `capability.embed_widget` |
| `platform.*` | una incidencia nuestra | `platform.outage` · `platform.publish_failed` · `platform.wrong_data` · `platform.slow` |
| `quota.*` | un tope alcanzado | `quota.clients` · `quota.channels` · `quota.companion_tokens` · `quota.messages` |
| `permission.*` | algo que el rol no permite | `permission.role` · `permission.billing` · `permission.keys` |

**La lista de slugs es abierta a propósito; la de familias no.** Un `topic`
cuyo prefijo no sea una de las seis familias **no se rechaza**: se normaliza
a `other.<slug>`. Rechazar un ticket por una discusión de taxonomía sería
exactamente el "no" que §25 existe para evitar — y una fila en `other.*` es
un dato, mientras que un ticket no abierto no es nada.

### D2 · La expectativa de respuesta (`sla`) la decide el motor, no el modelo

§4.4 exige un **identificador estable**, así que no puede salir del modelo ni
de un argumento. Es un mapa cerrado sobre `(category, familia del topic)`:

| Caso | `sla` | Por qué |
|---|---|---|
| `help` + `platform` · `quota` · `permission` | `business_hours` | hay trabajo parado ahora mismo |
| `help` + cualquier otra familia | `next_business_day` | falta algo, pero no está roto |
| `capability` (siempre) | `best_effort` | una petición de hoja de ruta no tiene reloj, y prometer uno es mentir |

La interfaz traduce los tres a la frase que ve el usuario. El backend no
emite la frase (§1.4 de la v1.1).

### D3 · `checked` vacío ⟹ no hay ticket

§4.2: *«un ticket sin `checked` es un ticket sin expediente, y eso es lo que
§25.1 existe para evitar»*. Se convierte en una regla del **motor**:

- `checked` **no es un argumento del modelo**. Sale de
  `CompanionToolbelt.citations` — las etiquetas del catálogo de herramientas
  de las lecturas ya hechas en este turno. Es la misma procedencia que
  sostiene R1, y por eso el ticket no puede describir un expediente que no
  existió.
- Si no hay ni una lectura, la propuesta se **rechaza** con un `ToolError`
  que le dice al modelo que mire primero. Tiene test propio.

### D3.1 · Qué verifica un ticket, si no hay ticket que releer

El invariante del motor es que **todo `kind` tiene relectura** (hay test:
`set(VERIFY_READS) == set(ACTION_KINDS)`), y saltárselo dejaría un `kind`
pasando de largo con la tabla vacía en verde — que es peor que no verificar,
porque parece verificado.

No hay sistema de tickets que releer (§25.1 lo prohíbe explícitamente), pero
sí hay algo que se prometió y se puede comprobar: **que la fila aterrizó en
el centro de notificaciones del partner**. La relectura es
`GET /console/notifications` y la comprobación es `ticket_visible`, contra
el `ticket_ref` que quedó en `companion.actions.result`. Verifica
exactamente lo que este `kind` hace de verdad.

### D4 · El documento de capacidades bloquea dos tickets imposibles

El §5.2 dice qué autoriza cada `status` a decir. Dos de esas frases se
aplican en el motor, no en el prompt, porque son las dos que producen una
promesa rota:

- `status: out_of_scope` + `category: capability` → **rechazo**, con el
  `note` de la entrada como motivo que el modelo repite en voz alta. Pedir
  como funcionalidad algo que se decidió no hacer llena la cola de ruido.
- `status: available` + `category: capability` → **rechazo**: ya existe, y el
  camino es usarlo, no pedirlo.

`absent`, `planned` y `retired` sí abren ticket. `help` nunca se bloquea:
una incidencia sobre algo fuera de alcance sigue siendo una incidencia.

### D5 · El mecanismo de alerta interna (§4.3)

Tres capas, de más a menos fiable:

1. **Una línea de log estructurada**, siempre:
   `console.support.ticket_opened` con `ticket_ref`, `category`, `topic`,
   `partner_id`, `client_ref` y `sla`. Es la que alimenta la agregación del
   §25.2 y la única que no puede fallar.
2. **La fila de `console_notifications`** para el partner, severidad `info`
   (§4.3.1) y `email=True` **explícito**. El parámetro ya existe en
   `services/console_notifications.emit`, y es justo para esto: la fila se
   queda en `info` —un ticket abierto no es una advertencia para quien lo
   abrió— y el acuse por correo sale igual.
3. **Un correo a Auphere**, a la dirección de `support_alert_email`
   (ajuste nuevo, vacío por defecto). Sin dirección configurada no se manda
   nada y **no falla**: el ticket existe, está en la auditoría, está en el
   log y está en la notificación del partner. Lo que no hay es empujón.

La capa 2 es del partner y la 3 es nuestra. Confundirlas —mandar el aviso
interno por el camino de las notificaciones del partner— haría que subir la
severidad para que nos llegue a nosotros pintara una alerta roja en la
consola de quien solo pidió ayuda.

### D6 · El mecanismo de métricas (§11)

Dos mitades, y el reparto no es arbitrario: **lo que ya está en una tabla se
consulta; lo que solo existe en el momento en que pasa, se cuenta.**

| Métrica | Cómo |
|---|---|
| `companion.hitl.proposed` / `companion.hitl.cancelled` | contador **y** consulta: `companion.actions` los tiene en `status`. Se cuentan igual para que la serie exista sin acceso a la base |
| `companion.thread.opened` | contador en `POST /companion/threads` |
| `companion.task.completed` | contador en el driver, al ver `verify.result` con `ok: true` |
| `companion.verify.total` / `companion.verify.failed` | contador en el driver, al ver `verify.result` |
| `companion.turn.total` / `companion.turn.unsupported` | contador en `_run_with_lifecycle`, donde se escribe `run.completed` — el único punto que se ejecuta **siempre**, también si el turno falló. Un run aparcado no cuenta: no ha terminado |
| Coste por trabajo | consulta sobre `usage_records` con `source='companion'` |

Los instrumentos viven en `core/otel_metrics.py`, que es el módulo que ya
declara *«un solo sitio para el nombre, la unidad y el juego de etiquetas»*.
Los nombres son los del §11, literales.

**Sin etiquetas, a propósito.** Ni `partner`, ni `role`, ni `kind`. La
campaña de carga WP-15 dejó la lección escrita: una dimensión de más en
CloudWatch parte la serie y deja ciega la alarma que la usaba. El corte por
partner sale de la consulta agregada, que es donde tiene sentido mirarlo —
una vez al final del piloto, no cada minuto.

La consulta agregada es `scripts/companion_pilot_metrics.py`: imprime las
cinco razones del §17 sobre una ventana de días, con el ratio de
confirmaciones canceladas primero porque es la que manda. **No se abre un
endpoint público de métricas** (§11).

### D7 · Dónde se emite `support.ticket`, y por qué ahí

§4.5 lo fija: en `execute`, **después** del 2xx de `console.apply` y
**antes** de `verify.result`. El nodo `execute` es del Agente D y no se toca,
así que el punto de emisión es el **driver** del run — el relevo secuencial
que ya convierte los eventos del grafo en el log durable.

Mecánica, sin adivinar nada:

1. `POST /console/support/tickets` devuelve `{ticket_ref, category, topic,
   sla, opened_at}`. `apply_action` guarda en `companion.actions.result` las
   claves que declare `APPLY_ECHO` **por `kind`** — una lista blanca cerrada,
   no el cuerpo entero de la respuesta. Hoy solo los dos `kind` de soporte
   tienen entrada, y sus claves son un identificador y tres enums: ninguna
   puede llevar texto de un cliente final (C8).
2. `POST …/resume` ya tiene la acción cargada, así que le pasa al driver el
   `action_id` **solo si el `kind` es de soporte y la decisión fue
   `confirm`**. Un turno normal no paga ni una consulta más.
3. El driver, al ver pasar `verify.result`, lee esa fila una vez, emite
   `support.ticket` y **después** relanza `verify.result`. El bucle es
   secuencial, así que el orden del contrato se cumple por construcción y no
   por suerte.

Si la aplicación falla, el grafo se salta la verificación y no hay
`verify.result`: tampoco hay `support.ticket`, que es lo correcto — no se
anuncia un identificador que no se llegó a asignar.

### D7.1 · El `ticket_ref` también vive en Postgres (§19.4, v2.3)

`support.ticket` viaja por el log de Redis y el log **rota** (24 h, 10.000
entradas). Si `hitl.requested` rotó y el evento del ticket no, la interfaz se
queda sin tarjeta a la que atarlo y el usuario pierde en silencio el
identificador del ticket que acaba de abrir.

`CompanionActionOut` gana `ticket_ref` y `sla`, los dos opcionales y nulos
para todo `kind` que no sea de soporte. Salen de `companion.actions.result`,
donde ya los dejó `APPLY_ECHO`: **cero persistencia nueva**, solo servir lo
que ya estaba guardado. Es el mismo arreglo que la v1.1 hizo para la tarjeta
pendiente y por la misma razón — un dato que solo vive en un log que caduca
no es un dato, es una ventana.

### D8 · La pausa por presupuesto se cierra sin tocar el grafo — con un límite real

§6.3 pide *«una puerta antes de cada llamada al modelo»*. El bucle del
modelo es de D, así que la puerta se pone donde E puede ponerla: en el
driver, cada vez que llega `cost.updated`.

**Y aquí hay que ser exacto, porque el contrato dice una cosa y el código
permite otra.** `cost.updated` **no** se emite por llamada al modelo: lo
emite el nodo `respond` de `runtime/companion/graph.py`, **una sola vez por
turno**, con los totales acumulados. Nada del turno reporta tokens antes de
eso. Consecuencia medida, no supuesta:

- lo que el §6.2 promete se cumple **entero** — 409 al trabajo nuevo, 202 al
  cierre, 200 a las lecturas, `budget.paused`, `run.completed{status:"paused"}`
  y la historia, la respuesta parcial y los tokens conservados (E5 y E6);
- lo que **no** se cumple es el «como mucho una llamada de más» del §6.3: el
  turno que cruza el tope llega hasta el final, así que el exceso puede ser
  un turno entero (hasta 25 herramientas y sus llamadas al modelo).

La puerta por llamada tiene que vivir donde se llama al proveedor, que es la
zona del grafo. El bucle del driver ya está escrito para aprovecharla sin
cambios el día que `cost.updated` se emita por llamada: la condición es la
misma, solo se dispara antes. Queda anotado para el orquestador — **con un
aviso**: el driver acumula con `+=` sobre un payload que hoy trae los
**totales del turno**. Emitirlo por llamada sin cambiar eso a `=` inflaría
el gasto medido, y el tope saltaría antes de tiempo.

Al tripar:

1. se emite `budget.paused` con la instantánea;
2. se cierra el generador de `astream_events` **explícitamente**
   (`contextlib.aclosing`), no por recolección de basura: un generador que
   se cierra cuando le toca al recolector es un turno que sigue gastando un
   rato más;
3. `_run_with_lifecycle` escribe `run.completed{status:"paused"}`;
4. `_finalise_run` cierra la fila con `ended_at`, y guarda tokens y
   respuesta parcial — el mismo camino de siempre, sin `parked`.

`paused` entra en `TERMINAL_RUN_STATUSES`, así que el tope de concurrencia
(que cuenta `running`) no lo ve, el reaper no lo toca y el lector del stream
sale. **No se confunde con el run aparcado del HITL**: aquel sigue en
`running` y no publica `run.completed` (PLAN-CO-04 D4). La precedencia es
explícita — si un turno cruzara el tope y además tuviera una acción
esperando, manda `paused`, porque el trabajo se paró de verdad.

### D9 · La bandera apaga la escritura, nunca la historia (§10)

`companion:use` **Y** `partners.companion_enabled`. Dos dependencias:

- `companion_caller()` — sin bandera, **403** `{"code": "companion_disabled"}`.
  La usan `POST /threads`, `PATCH /threads/{id}`, `POST /threads/{id}/runs`
  y `POST /runs/{id}/resume`.
- `companion_reader()` — solo `companion:use`. La usan todos los `GET` y
  el `DELETE /runs/{id}`.

**El `DELETE` (parar un run) queda fuera de la puerta a propósito.** Si la
bandera se apaga con un turno en vuelo, el botón *Detener* tiene que seguir
funcionando: un interruptor de emergencia que no se puede pulsar es peor que
no tenerlo.

`GET /console/me` gana `companion_enabled: bool` (§10) — es lo que decide si
la burbuja se monta, y la burbuja apagada es **ausencia**, no un botón gris
con un tooltip.

### D10 · El cabo 3 se resuelve por la membresía, no por `companion.actions`

§12 dice que `_human_actor` resuelva `companion:<user_id>` *«recuperando el
dato de `companion.actions.decided_by`»*. **Eso no se puede hacer desde la
página de auditoría**, y conviene dejar escrito por qué: `companion.actions`
tiene **RLS por principal**, así que una consulta desde la sesión de quien
mira la auditoría solo vería sus **propias** acciones. El resultado sería
que la escritura del Companion de un compañero se seguiría pintando como
*Companion* a secas — justo lo que el cabo pide arreglar.

Lo que sí cumple la intención y la restricción (*«solo dentro del partner
del llamante»*) es resolver el `user_id` contra `partner_memberships` del
partner del principal: por construcción no puede devolver el correo de otro
partner, y es **una** consulta por petición (el equipo de un partner es
pequeño y acotado), no una por fila.

Sin fila de membresía —un miembro expulsado— cae a *Companion* a secas.
**Nunca al uuid crudo**, que en una página de auditoría no le dice nada a
nadie.

### D11 · Contenido de la migración `0092`, con `down_revision = "0091"`

1. `companion.runs`: el CHECK de `status` gana `'paused'`.
2. `console_support_ticket_seq`: secuencia, `START 1`, con
   `GRANT USAGE, SELECT … TO nexus_app` (defensivo: el endpoint corre con el
   rol por defecto, pero una llamada futura bajo `SET LOCAL ROLE nexus_app`
   fallaría en silencio sin el GRANT).
3. `partners.companion_enabled boolean NOT NULL DEFAULT false`.
4. Dos filas de `console_audit_vocabulary` para las acciones nuevas.
5. **Los `kind` de notificación NO necesitan nada.**
   `console_notifications.kind` es `varchar(60)` sin CHECK que los enumere
   —comprobado en la 0086 y en el modelo—, y `companion.cap_reached` de
   CO-01 ya usa un valor fuera de `NotificationKind`. Se anota en el
   docstring de la migración para que nadie vuelva a buscarlo.

No se aplica a *staging* ni a producción.

### D12 · La página de auditoría de la consola no cambia

Está en la zona de E y se revisó: pinta `item.actor` y `item.summary` tal y
como los manda el backend, así que el cabo 3 llega solo. El filtro por
cliente no tiene control en la interfaz (`AuditControls` expone actor,
acción y fechas), de modo que el 404 nuevo solo es alcanzable escribiendo
`?client=` a mano — y ahí el 404 opaco **es** la respuesta correcta.

---

## 2. Archivos

| Archivo | Qué hace |
|---|---|
| `docs/companion/capabilities.yaml` | **nuevo** — el documento versionado del §5 |
| `companion/tools/support.py` | **nuevo** — el constructor de los dos `kind` de soporte, el vocabulario de `topic`, el mapa de `sla` y el cargador de `capabilities.yaml` |
| `companion/tools/catalog.py` | 3 filas: `console.get_capabilities` (read) y las dos `propose` de soporte |
| `companion/tools/proposals.py` | 2 entradas en `APPLY_ROUTES`, `checked` en el `ProposalBuilder`, 2 métodos que delegan en `support.py` |
| `companion/tools/actions.py` | `APPLY_ECHO` (lista blanca por `kind`) y las dos entradas de `VERIFY_READS` |
| `alembic/versions/0092_companion_pilot.py` | D11 |
| `apps/api/Dockerfile` | una línea: `capabilities.yaml` viaja en la imagen |
| `companion/tools/runner.py` | una línea: el builder recibe las etiquetas de las lecturas del turno |
| `api/console/capabilities.py` | **nuevo** — `GET /console/capabilities` |
| `api/console/support.py` | **nuevo** — `POST /console/support/tickets` |
| `api/console/companion.py` | 409 `budget_paused`, la puerta de presupuesto del driver, la bandera, `support.ticket`, contadores |
| `api/companion_streaming.py` | las **cuatro** ediciones del catálogo (§8). Dueño único |
| `api/console/audit.py` | cabo 2 (404 por `client`) y cabo 3 (`_human_actor` con correos) |
| `api/console/me.py` + `schemas.py` | `companion_enabled` |
| `api/console/schemas_companion.py` | §19.4 — `CompanionActionOut.ticket_ref` y `.sla` |
| `apps/console/src/lib/backend.ts` | una línea: `Me.companion_enabled`, para que F pueda montar la burbuja |
| `core/otel_metrics.py` | los ocho contadores del §11 |
| `core/config.py` | `support_alert_email`, `console_support_tickets_per_minute` |
| `db/models/partner.py` | `companion_enabled` |
| `db/models/companion.py` | `RUN_PAUSED` |
| `alembic/versions/0092_companion_pilot.py` | D11 |
| `scripts/companion_pilot_metrics.py` | la consulta agregada del piloto |

### 2.1. Lo que se toca fuera de la zona literal del §14, y por qué

El §14 del contrato reparte archivos para que dos worktrees no se pisen. Su
lista no cubre once archivos que el propio contrato exige cambiar. Ninguno
lo toca D (`apps/worker/runtime/companion/**`) ni F
(`apps/console/src/components/companion/**`), así que el riesgo de choque
es cero; se anota aquí y en el informe porque la regla es "para y pregunta",
y la respuesta a la pregunta es la misma en todos los casos:

| Archivo | Lo exige |
|---|---|
| `db/models/companion.py` | §6.3: `paused` es *«valor nuevo de `RUN_STATUSES`»*, y `RUN_STATUSES` vive ahí |
| `apps/api/Dockerfile` | `docs/` **no** se copia a la imagen, así que `GET /console/capabilities` fallaría en producción. Una línea, y el fichero sigue viviendo donde el §5.2 dice |
| `core/otel_metrics.py` | §11 delega el mecanismo en E, y ese módulo declara «un solo sitio para el nombre, la unidad y el juego de etiquetas» |
| `tests/conftest.py` | `console_world` tiene que encender la bandera nueva, o las suites del Companion se caen enteras con 403 |
| `apps/console/src/lib/backend.ts` | el tipo `Me` es un espejo escrito a mano del modelo de la API, y §10 dice que la interfaz mira `companion_enabled`. No es zona de F (que tiene `components/companion/**`), y sin el campo F no puede montar la burbuja |
| `tests/unit/test_companion_tools_catalog.py`, `tests/isolation/test_companion_action_guarantees.py`, `tests/isolation/test_console_isolation.py`, `tests/integration/test_companion_endpoints.py`, `tests/integration/test_companion_action_resume.py` | listas y aserciones escritas a mano que el trabajo amplía o retira: 18→19 lecturas, 9→11 `kind`, el 200-vacío de la auditoría que pasa a 404, y el 429 del tope que pasa a 409 |
| `services/evals/companion/dataset/known_answer.json` | el dataset de CO-07 tiene un test que exige **un caso por herramienta del catálogo**. Tres filas nuevas o el gate de CI se queda rojo |
| `db/models/partner.py` | §10: la columna nueva necesita su atributo en el modelo |
| `companion/tools/proposals.py` | §4.1: *«registrado en `APPLY_ROUTES`»*, que vive ahí |
| `companion/tools/actions.py` | el `ticket_ref` tiene que sobrevivir de la aplicación al evento |
| `companion/tools/runner.py` | §4.2: `checked` sale de las citas del turno, que las tiene el toolbelt |
| `api/console/schemas.py`, `api/console/__init__.py` | `MeOut` y el montaje de dos routers nuevos |

---

## 3. Orden de construcción

1. Migración 0092 y los dos atributos de modelo (sin ellos nada persiste).
2. `capabilities.yaml` + `support.py` + `GET /console/capabilities`.
3. `POST /console/support/tickets`.
4. Catálogo de herramientas, `APPLY_ROUTES`, `checked`, `APPLY_ECHO`.
5. Las cuatro ediciones de `COMPANION_EVENTS`.
6. La pausa por presupuesto (409, puerta del driver, `paused`).
7. La bandera y `GET /console/me`.
8. Cabos 2 y 3 de la auditoría.
9. Contadores y consulta agregada.
10. Tests, en el orden de las garantías: E4 → E5 → E6 → E7 → E8.

## 4. Lo que este plan NO hace

- `verify.result.trial` **no se emite**: la clave entra en el catálogo (§8,
  edición 2) para que F construya contra el contrato; quien la emite es
  CO-05, en la Fase 2 del orquestador.
- `intake.missing.work_kind` **no se produce**: la clave entra en el
  catálogo (§8, edición 1); el nodo que la rellena es de D.
- El expediente persistido (CO-06), el panel de la prueba en playground y la
  interfaz del estado de pausa (F).
- Ningún `kind` de la lista prohibida del §6.5. Las dos herramientas nuevas
  **proponen**; `console.apply` sigue siendo la única `mutates`.
- Ningún endpoint público de métricas (§11).
- La línea de i18n del centro de notificaciones para los dos `kind` nuevos:
  cae en la consola (`i18n/lanes/onboarding.ts`), fuera de la zona de E, y
  hoy degrada a `notif.kind.unknown`. Queda anotado para la Fase 2.
- La **puerta de presupuesto por llamada al modelo** (ver D8): hoy es por
  turno porque `cost.updated` es por turno. Necesita un cambio en la zona
  del grafo.
- La página de auditoría de la consola no gana un selector de cliente, así
  que el 404 nuevo solo es alcanzable escribiendo `?client=` a mano. Si
  alguna vez se añade el filtro, hará falta un estado vacío para el 404.
