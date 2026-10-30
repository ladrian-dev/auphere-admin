# La ficha del negocio

> Spec 047 (ola 2: historias 3, 4, 14 a 17; requisitos 4 a 14). La ficha es la
> **fuente única** de lo que el negocio es: la leen todos sus agentes, Reservas,
> la consola de partners, la consola lite y la app. Este documento cuenta cómo
> está hecha, cómo se escribe, de dónde viene cada dato y cómo se deshace.

## Qué es y dónde vive

La ficha son **tablas por cliente** (research D3), todas con `tenant_id`, RLS
`FORCE` y claves foráneas compuestas `(tenant_id, …)` (garantía 1):

| Tabla | Qué guarda |
|---|---|
| `business_profiles` | 1:1 con el cliente: nicho, información (dato no confiable, §III), web, país, zona IANA, moneda de los precios, «Solo UE», `sovereign` (solo el admin), políticas y `content_rev` |
| `business_sections` | Una fila por sección: su `revision` (para `If-Match`) y su estado (`complete`, `read_pending`, `pending`, `optional`) |
| `business_locations`, `business_schedules`, `business_shifts`, `business_special_dates`, `business_special_shifts`, `business_faqs` | Sedes, horario, fechas especiales y preguntas frecuentes (ver «Horarios y servicios») |
| `reservation_services` + `agent_services` | Los servicios, los de Reservas, con quién los ofrece |
| `business_links` | La web y las redes, con su enlace y su usuario |
| `knowledge_documents` | «Documentos y webs» (la capa del negocio; la propia de cada agente llega con la ola 5) |
| `business_field_provenance` | La procedencia **vigente** de cada dato, por su puntero en el ClientSpec |
| `business_changes` | El historial: antes y después de cada escritura, quién, desde dónde, y el deshacer |
| `business_suggestions` | Lo que no se aplicó solo: lo leído que choca con lo escrito por una persona, lo sugerido por el constructor y lo importado |

El nombre del cliente vive en `tenants` (y en `partner_tenants.client_name`); la
zona horaria, en los dos sitios a la vez. La moneda de la bolsa es la del
partner (US$) hasta la ola 7.

Las nueve secciones son `basics`, `locations`, `hours`, `special_dates`,
`services`, `policies`, `faqs`, `sources` y `links`. Un cliente nuevo nace con
`basics` completa; horario, servicios, sedes, documentos y redes pendientes (son
lo que el Panel dice que falta, en ese orden); lo demás, opcional.

Un cliente de antes de la 047 estrena su ficha la primera vez que alguien la
abre o la edita (`hours.ensure_profile`), con lo que ya se sabe de él y marcada
«Migrado».

## El ClientSpec

`services/business/client_spec.py`. Es la **vista tipada** de la ficha: no es
una fuente, se deriva de las tablas cada vez. Tres usos:

- lo lee el constructor;
- es el formato de **exportar** (`GET /console/clients/{ref}/business/export`) e
  **importar** (`POST …/business/import?dry_run=`);
- es la base de los **parches** que se proponen (`$defs.patch`).

El modelo Pydantic (`ClientSpec`, `extra="forbid"`) es **igual** a
`specs/047-la-fabrica-de-agentes/contracts/client-spec.schema.json`. Lo comprueba
`apps/api/tests/unit/test_client_spec_contract.py`: los dos esquemas,
normalizados, son idénticos (campos, obligatorios, límites, patrones,
vocabularios, solo lectura) y los mismos documentos valen o fallan en los dos.
Los límites de un campo opcional van dentro del tipo (`Annotated[...]`): puestos
en el `Field` de una unión, Pydantic no los aplica.

**El validador sin modelo** (`validate_document`, `validate_value`) dice lo que el
esquema no puede: una zona que no es IANA, turnos que se pisan o de más de 24 h,
una fecha especial al revés o cerrada con turnos, una duración que no va de 5 en
5, ids repetidos, redes duplicadas. Corre antes de proponer y otra vez al
aplicar.

Los punteros (RFC 6901) usan **el id de cada elemento** como clave en las listas
(`/services/{id}/price`, `/links/{id}`) para que una propuesta siga apuntando al
mismo dato aunque cambie el orden; `/x/-` es «añadir».

**Importar no escribe nada.** `diff_ops` compara el documento con la ficha y cada
cambio queda como una propuesta (`business_suggestions`, `source = import`) que
una persona acepta, edita o descarta. Importar nunca borra: lo que falta en el
documento se queda como está. `dry_run=true` devuelve las operaciones sin crear
nada; un documento que no valida responde `422 invalid_document` con sus
problemas.

## Escribir: una sola vía

Toda escritura pasa por `services/business/writes.write_section`, dentro de la
transacción del llamante y con el cliente puesto. El servicio de cada sección
valida su dominio, escribe sus filas y llama aquí con la vista de la sección
antes y después. `write_section`:

1. **Concurrencia por sección** (13.4): con `expected_revision` distinta de la
   actual, `SectionRevisionConflict` con lo que cambió desde entonces. La ruta
   responde `412 {code: "revision_conflict", section, current, changes}` con
   `ETag`. Dos personas en secciones distintas no chocan.
2. **Historial** (13.3): una fila de `business_changes` con su hora de sentencia
   (`clock_timestamp()`: dos cambios de la misma transacción no empatan).
3. **Procedencia** (13.1) de los punteros escritos.
4. **Revisión** de la sección y `content_rev` de la ficha, y el **estado**: una
   sección que queda con algo leído sin revisar sigue «Leída · revísala».
5. **Recompilación** de la versión activa de cada agente
   (`compilation.recompile_active_versions`, research D4): el agente usa el dato
   nuevo desde el siguiente mensaje, sin publicar.
6. **Quién edita** (13.5): el constructor nunca escribe directamente
   (`BuilderWritesOnlyByProposal`); escribe la persona que acepta su propuesta.
7. **Auditoría** con quién y desde dónde (`business.section_updated`,
   `business.section_undone`, `business.read_applied`,
   `business.correction_applied`; las fuentes, `source.added` y
   `source.removed`).
8. **El aviso al partner** (13.6): si escribe una persona del cliente (consola
   lite o app), `client.business_changed` en la campana del partner, **después de
   confirmar** (`writes.after_commit`) y uno por cliente y hora: los cambios
   siguientes de esa hora se suman a sus secciones. Dice qué sección y quién,
   nunca el dato.
9. **Las pruebas afectadas** (13.7): cada agente publicado del cliente queda con
   sus pruebas desactualizadas. Hasta la fase 9 no hay suites que correr: queda
   **un** trabajo `tests` terminado por agente con
   `{stale: true, runs: 0, sections: [...]}`, que se va completando. La fase 9
   lo cambia por la pasada de verdad (y el aviso `agent.tests.failing`).

**Los adaptadores de sección.** Deshacer y aplicar una propuesta escriben por el
servicio de la sección, no a mano. Cada servicio registra el suyo con
`writes.register_section_adapter(section, restore=…, apply=…)`; `restore` recibe
la vista guardada en `before` y `apply` operaciones `Op(op, path, value)`. Los
dos reciben un `WriteContext` (autor, fuente, tipo de cambio, revisión pendiente
o no, `undo_of`) y llaman a `write_section`. Datos básicos, políticas y redes:
`profile_edits.py`; sedes, horario, fechas especiales, servicios y preguntas:
sus servicios. Una sección sin adaptador responde `409 section_not_writable` o
`undo_not_available`.

## La procedencia

Cada dato tiene su procedencia **vigente** (`business_field_provenance`): fuente
(`person`, `web`, `document`, `social`, `migrated`, `builder`,
`inbox_correction`, `import`), autor, origen (`console`, `lite_web`, `app`,
`admin`, `api`, `system`), fecha, la URL leída, el idioma si se tradujo y si está
pendiente de revisar. La consola la escribe así:

| Procedencia | Texto |
|---|---|
| `person`, quien mira | «Escrito por ti» |
| `person`, desde la app | «Editado por Marta desde la app · hace 2 h» |
| `web` pendiente | «Leído de la web · revísalo» |
| `migrated` pendiente | «Migrado · revísalo» |
| `builder` | «Propuesto a partir de la ficha» (la interfaz no nombra al constructor) |
| `inbox_correction` | «Corregido desde la Bandeja» |

**«Es correcto»** (13.2, `POST …/business/sections/{section}/confirm`): lo leído
pendiente de la sección pasa a escrito por quien confirma y la sección deja de
salir como pendiente. No cambia ningún dato ni sube la revisión.

Aceptar una propuesta conserva lo que dice de dónde vino: lo del constructor
queda con su procedencia `builder`, lo importado «Importado» y lo leído pasa a
ser de quien lo aceptó. Editar antes de aceptar lo deja escrito por esa persona.

**Dónde se deciden las propuestas** (enmienda del 2026-10-29, requisitos 57.3 y
60.5). Cada propuesta pendiente sale en la sección de Negocio a la que apunta, al
lado de lo que hay, marcada «Sugerido · confirma» y con su procedencia
(«Propuesto a partir de la ficha», «Leído de la web», «Leído de un documento»,
«Leído de sus redes», «Importado»), con «Aceptar», «Editar» y «Descartar»:

| Puntero | Sección | Qué se ve |
|---|---|---|
| `/policies/{cancellation\|payments\|deposit\|no_show}` | Políticas | Debajo del valor de esa política, con «Ahora: …» si ya había uno |
| `/faqs/-` | Preguntas frecuentes | En «Por confirmar», la pregunta y su respuesta |
| `/business/sector` | Datos básicos | «Propuesto: {sector}» al lado del sector, solo «Aceptar» y «Descartar» |

Una pregunta guardada con `suggested: true` (sugerida, fuera del prompt) también
sale en «Por confirmar»: aceptarla es `PATCH …/faqs/{id}` con `suggested: false`
y descartarla, archivarla. Nada sugerido entra en el prompt de un agente hasta que
una persona lo acepta (60.7).

## El historial y el deshacer

`GET …/business/history?section=` devuelve los cambios del más nuevo al más
viejo, con antes y después, quién (con nombre) y desde dónde, y si se puede
deshacer. `POST …/business/history/{id}/undo` deshace **el último** cambio de una
sección aplicando su `before` por el adaptador de la sección (`kind = undo`,
`undo_of`) y lo marca deshecho. Si alguien escribió la sección después,
`412` con lo que cambió: no se pisa a nadie. Lo ya deshecho responde
`409 already_undone`; un cambio sin `before` (lo primero que leyó la web) no se
puede deshacer, salvo las redes que la lectura añadió, que se quitan.

## Documentos y webs

`services/business/sources.py`, rutas en `api/console/business_records.py`.

- **Subir** un archivo de hasta 10 MB (PDF, Word, fotos de cartas, TXT, MD y
  HTML) o **añadir una web**: la fuente queda «Leyendo» y responde `202` con el
  trabajo. El archivo se guarda en el almacén de medios (`s3_key`).
- **Indexar es un trabajo**, no la petición: un `client_read` con
  `{source_id, action}` en su `progress`. El manejador del worker
  (`jobs/handlers/business_sources.py`, desde `client_read`) llama a
  `sources.index_source`: saca el texto sobre `knowledge_indexer` (sus guardas
  de direcciones públicas y de tamaño), Word sin dependencias nuevas y las
  fotos con un modelo con visión (rol `vision`); deja la fuente `indexed` o
  `failed` con su motivo (`unreachable`, `no_text`, `too_large`); y pasa el
  texto, vallado, por el extractor de la lectura (`read_source`) y por
  `reader.apply_extraction`. Los **servicios con precio** de un documento
  quedan propuestos y pendientes de revisar, sin tocar los que hay (12.5).
- Todo lo que gasta un modelo corre en el turno de uso del lector
  (`source = reader`): la partida «Construcción y pruebas», nunca la bolsa.
- **Quitar** borra la fila (el siguiente turno ya no la ve) y guarda su copia en
  el historial de `sources`; durante **10 minutos** `POST …/restore` la devuelve
  tal cual. Pasado el plazo, `409 undo_window_closed`.
- **Volver a leer**: a mano. **No hay relectura periódica** (enmienda del
  2026-10-29, requisito 59.6, D48 y D63): la web y las redes del cliente se
  vuelven a leer cuando una persona pone una web distinta en Datos básicos o añade
  una red (`profile_edits`, nunca por lo que escribe el propio lector), y una
  fuente se lee al añadirla. Quitar una red no lee nada. Nunca dos lecturas de la
  misma fuente a la vez. Los cambios llegan como propuestas.

La tarjeta de lectura del Panel solo sigue la lectura de la web y las redes del
cliente (`sources.latest_site_read`), no la de cada fuente. Con la enmienda del
2026-10-29 (59.7) se queda en el Panel al terminar: qué se leyó, qué se encontró,
cuánto falta revisar y, por red, la que no deja leer perfiles sin cuenta
(`blocked_by_network`, que no cuenta como fallo, 59.4) y la que falló con su
motivo.

## Redes

`PUT …/business/links` con `If-Match` (la revisión de `links`): la lista entera,
normalizada como en el alta (`links.link_from_choice`). Instagram y Facebook
están siempre en la consola; TikTok, LinkedIn, YouTube, X y Threads se añaden.
Lo que ya estaba conserva su id y su procedencia; la web del negocio sigue a la
primera web de la lista.

## La lectura de la web (el alta)

`services/business/reader.py` (T049): al crear un cliente con web o redes se
lanza un `client_read` que lee hasta 25 páginas del mismo dominio con
`robots.txt`, y los perfiles públicos de sus redes. Lo que no choca se aplica
marcado «Leído de la web · revísalo»; lo que contradice un dato escrito por una
persona queda como propuesta al lado. Lo leído es dato, nunca instrucción
(§III). Avisa a quien la lanzó al terminar o al fallar.

Desde la enmienda del 2026-10-29 (requisito 59, D49, D50 y D69):

- **Datos estructurados primero, sin modelo** (`services/business/structured.py`):
  el JSON-LD y los microdatos de schema.org (nombre, dirección, teléfono, horario,
  servicios con precio y preguntas frecuentes) se pasan a la misma forma que pide
  el modelo y por la misma validación (solo datos del negocio). Al mezclarlos con
  lo que extrae el modelo, **mandan**: sus sedes, su horario, sus servicios y sus
  preguntas van primero. El resultado dice `structured: true`. La procedencia
  guardada sigue siendo `web`.
- **El `sitemap.xml`** (el que diga `robots.txt` o `/sitemap.xml`, con su índice;
  1 MB, 3 sitemaps y 200 direcciones como mucho, sin entidades XML) elige las
  páginas, junto con los enlaces que suenan a servicios, precios, horario o
  contacto.
- **Cuatro páginas a la vez** como mucho (`CONCURRENCY`), sin pasar de 25 páginas,
  40 intentos ni 3 minutos.
- **Solo la red pública, y sin rebinding** (T217, revisión de seguridad del
  2026-10-30): el cliente HTTP del worker (`core/public_http.public_client`, el
  mismo que usa `fetch_url`) resuelve cada nombre una sola vez, valida todas sus
  direcciones con la tabla del renderer (`core/public_addresses.py`, una copia de
  `apps/renderer/.../addresses.py`; una prueba exige que coincidan) y conecta a la
  validada, con el `Host` y el SNI del nombre, y solo por 80 y 443.
  `assert_public_url` usa esa misma tabla y esos puertos: también rechaza NAT64 y
  la multidifusión, que `is_global` aceptaba. Un bloque JSON-LD anidado hasta
  tumbar `json.loads` (`RecursionError`) se salta; los demás se leen.
- **«Volver a leer» gasta de «Construcción y pruebas»**: agotada, `402
  build_budget_exhausted` (T217).
- **Las redes también con web** (59.3). Instagram, Facebook, LinkedIn y X no dejan
  leer perfiles sin cuenta: no se piden y salen como `blocked_by_network` en
  `networks` del resultado, igual que una red cuyo `robots.txt` lo prohíbe; no son
  un fallo (59.4). Si solo hay redes de esas, la lectura termina sin nada que
  proponer, no fallida.
- **La extracción que no es JSON se reintenta una vez**, con el error (59.5). Si
  vuelve a fallar y no hay datos estructurados, la lectura falla con
  `extract_failed` («Sin datos útiles»); con datos estructurados, se aplican esos.
- **El navegador de respaldo** (`docs/renderer.md`): solo para una página con poco
  texto y si está configurado.

El resultado del trabajo añade `networks: [{network, status: read |
blocked_by_network | failed, reason?}]`, `structured` y `extraction_retried`.

## El sector

Enmienda del 2026-10-29 (requisito 57, research D46, D58 y D59). `business.sector`
(`business_profiles.sector`, migración 0206) guarda la clave de una guía de
Auphere (u `otro`), la etiqueta (1 a 40), la confianza, de dónde salió (`niche`,
`info`, `web`, `person`, `fallback`) y quién lo decidió. Lo identifica el sistema
en segundo plano; `null` mientras tanto.

- **Leerlo desde el servidor**: `services/business/sector.stored(session)` (el
  objeto) o `sector.sector_key(session)` (la clave), con el cliente puesto. Nadie
  lo vuelve a clasificar del nicho (57.6): las pruebas del sector y el constructor
  del cliente leen el guardado, y si aún no lo hay lo dejan guardado una vez con
  la regla de respaldo (`sector.ensure_stored`).
- **Cuándo se identifica**: el trabajo `sector_identify`
  (`wk/jobs/handlers/sector_identify.py` → `sector.identify_sector`) se encola al
  alta (sin retrasarla), al terminar la lectura de la web y las redes, cuando una
  persona cambia el nicho o la información, y al abrir Datos básicos sin sector o
  con el de respaldo (como mucho una vez por hora). Lo que lanza una persona al
  cambiar el nicho o la información también espera su hora (T217,
  `sector.request_after_edit`): una identificación por hora como mucho. Lo que
  cambia dentro de esa hora queda pendiente y lo identifica abrir Datos básicos
  pasada la hora (el nicho o la información se escribieron después de que la
  última identificación empezara a leer). Sin partida de «Construcción y
  pruebas», no se llama al modelo: vale la regla de respaldo.
- **Con modelo**: uno barato (`classify`, `NEXUS_LLM_SECTOR_MODEL`), con el nicho,
  la información y lo leído vallados; la respuesta se valida contra la lista
  cerrada y la etiqueta se limpia y se corta a 40 (57.7). **Sin modelo**, o si la
  respuesta no vale: la regla de palabras enteras de `builder/sectors.py`, con
  confianza 0,3, que no pisa a lo del modelo.
- **Quién manda**: lo del sistema se guarda directamente (no mueve la revisión de
  Datos básicos ni deja pruebas desactualizadas, D58). Lo que fija una persona va
  por `update_basics`, con historial y deshacer, y desde ahí el sistema solo
  propone (`/business/sector`).
- Se mide en «Construcción y pruebas» (`source = builder`, tarea `classify`). En Negocio, Datos básicos lo
enseña con «Con guía» o «Generada» (sin guía de Auphere, el constructor genera una
para este cliente, 58.4), y se corrige con los sectores de `GET /console/sectors`
o «Otro» con una etiqueta de hasta 40 caracteres (`PUT …/basics` con `sector:
{key, label}`; una clave fuera de la lista es `422 sector_unknown`). Fijado por una
persona, el sistema ya no lo cambia: lo propone (`/business/sector`).

## El constructor del cliente

Enmienda del 2026-10-29 (requisito 60, research D51, D60 y D61).
`services/builder/client_profile.py`, trabajo `client_builder`. **Se lanza solo**,
en segundo plano: al terminar `sector_identify` tras una lectura, cuando el sistema
cambia el sector y no hay una lectura en marcha, y cuando una persona cambia el
sector. Es idempotente por la huella de la ficha (el `state_hash` de su ClientSpec,
en `progress.input.fingerprint`): con la misma, no genera dos veces. Si el modelo no
responde, reintenta 3 veces (esperas de 2, 4 y 8 s) y queda `failed` con
`builder_unavailable`, sin bloquear nada. Sin saldo en «Construcción y pruebas» no
se lanza.

Sus propuestas de políticas y preguntas frecuentes son sugerencias de la ficha
(`source = "builder"`, `/policies/{clave}` y `/faqs/-`) que se deciden en su
sección; nada entra en el prompt hasta aceptarse. Los agentes que propone se
guardan en `suggested_agents` y la pestaña Agentes los enseña («Sugerido», «Crear
este agente» y «Descartar»). Lo descartado no vuelve.

## Políticas y preguntas frecuentes

Enmienda del 2026-10-29 (requisito 60.4). Lo que ya entraba en el prompt de todos
sus agentes tiene su sección en Negocio:

- **Políticas** (`GET`/`PUT …/business/policies`): cancelación, pagos, señal y no
  presentarse, hasta 1.000 caracteres cada una. `PUT` las sustituye las cuatro
  (lo vacío, `null`), con `If-Match`.
- **Preguntas frecuentes** (`GET`/`POST …/business/faqs`, `PATCH …/faqs/{id}`,
  `POST …/faqs/{id}/archive`): pregunta (≤ 300) y respuesta (≤ 2.000). Las
  sugeridas (`suggested: true`) no entran en el prompt hasta confirmarlas.

## La ficha en la API

| Ruta | Qué hace |
|---|---|
| `GET /console/clients/{ref}/business` | El ClientSpec, el estado y la revisión de cada sección, la procedencia con nombres y las propuestas pendientes |
| `PUT …/links` | Redes y web, con `If-Match` |
| `POST …/sections/{section}/confirm` | «Es correcto» |
| `GET …/history` · `POST …/history/{id}/undo` | Historial y deshacer |
| `POST …/suggestions/{id}/decide` | `{decision: accept \| edit \| discard, value?}` |
| `GET …/sources` · `POST …/sources` · `POST …/sources/{id}/reread\|remove\|restore` | Documentos y webs |
| `GET …/export` · `POST …/import?dry_run=` | ClientSpec v1 |
| `GET /console/clients/{ref}/business/read` · `POST …/read` | La tarjeta de lectura; con la enmienda, `networks[]` con el estado de cada red y `structured` |
| `GET …/policies` · `PUT …/policies` · `GET …/faqs` · `POST …/faqs` · `PATCH …/faqs/{id}` · `POST …/faqs/{id}/archive` | Políticas y preguntas frecuentes |
| `GET /console/sectors` | Los sectores con guía, para el selector |
| `GET /console/clients/{ref}/suggested-agents` · `POST …/suggested-agents/{id}/dismiss` | Los agentes que sugiere el constructor del cliente (`agents:read` / `agents:write`) |

Las secciones con servicio propio (datos básicos, sedes, horario, fechas
especiales, servicios, políticas y preguntas) tienen sus rutas en
`api/console/business.py`. Ninguna respuesta lleva cuerpos de mensajes,
teléfonos de clientes finales ni costes; el teléfono de una sede es del propio
negocio.

## El cliente: editar, archivar, restaurar y eliminar

`api/console/tenants.py` y `services/tenant_lifecycle.py` (historia 14):

- **Editar** (`PATCH /console/clients/{ref}`, el modal del alta): con la consola
  nueva exige `If-Match` con la revisión de `basics` (`428` sin ella, `412` si
  cambió) y escribe por `profile_edits.update_basics`. La zona horaria se valida
  como IANA en el servidor. Si cambian el nombre o la zona, después de confirmar
  se avisa al runtime (`nexus:agent_config:promote`). La moneda de la bolsa no se
  cambia aquí (`409 bag_currency_locked`): con saldo dentro hay que convertirla,
  y eso es de Consumo (ola 7).
- **Archivar** (`POST …/archive`): el cliente pasa a `archived`, sus agentes
  quedan «Pausado · cliente archivado» (el turno no corre y la conversación va a
  la Bandeja con `archived_client`), su consola lite y su app se cierran, y lo
  que tenía cada agente queda en la auditoría. La respuesta trae
  `undo: "restore"`. Hasta el bloque E la pausa es la del cliente; con la
  columna de pausa del agente, archivar escribirá `pause_reason =
  client_archived` y `before_pause` en cada uno.
- **Restaurar** (`POST …/restore`): vuelve al estado que tenía al archivarse
  (activo o en pausa), y cada agente con él.
- **Eliminar** (`DELETE`): el borrado RGPD de hoy (research D40): `clients:delete`,
  archivado antes (`archive_first`), el nombre tecleado (`name_mismatch`) y `409
  legal_retention` si es una línea de factura o tiene pagos, con «déjalo
  archivado» como salida.

## La lista y el Panel del cliente

- `GET /console/clients?q=&filter=all|attention|active|archived` (historia 15):
  cada fila con su nicho, su estado con el motivo (la regla única de
  `services/attention.py`, la misma del Panel), sus agentes con su
  `visible_state`, su bolsa (lo que queda, los días y el porcentaje) y las
  acciones de esa persona; los contadores de cada filtro sobre lo buscado; el
  orden, primero lo que necesita algo y después menos días de saldo. Bolsas de
  monedas distintas se comparan por días y porcentaje, nunca por importe.
- `GET /console/clients/{ref}/panel` (historia 16): la bolsa (lo que queda, lo
  consumido y su porcentaje, los días al ritmo de los últimos 7 días completos
  —solo con 3 días o más de consumo—, el reparto por agente y los avisos del 80
  % y del 100 %), el mes (conversaciones, resueltas sin persona y pasadas a una),
  los 4 agentes que más consumen, lo primero que le falta a la ficha y la
  tarjeta de lectura. Las cifras salen de las mismas cuentas que la consola lite
  (`lite_home.balance_of`, `spend_block`, `split_cents`): cuadran al céntimo.
  Hasta la ola 7 la bolsa se lee de `partner_allocations`.

## Horarios y servicios

El horario, las sedes, las fechas especiales y los servicios (con quién los
ofrece) se cuentan en [`docs/reservas.md`](reservas.md): un solo horario con
turnos nocturnos y fechas especiales, la frase «Así lo dirá el agente» y los
servicios de Reservas con su precio y sus agentes.
