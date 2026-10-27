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
| `builder` | «Propuesto por el constructor» |
| `inbox_correction` | «Corregido desde la Bandeja» |

**«Es correcto»** (13.2, `POST …/business/sections/{section}/confirm`): lo leído
pendiente de la sección pasa a escrito por quien confirma y la sección deja de
salir como pendiente. No cambia ningún dato ni sube la revisión.

Aceptar una propuesta conserva lo que dice de dónde vino: lo del constructor
queda «Propuesto por el constructor», lo importado «Importado» y lo leído pasa a
ser de quien lo aceptó. Editar antes de aceptar lo deja escrito por esa persona.

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
- **Volver a leer**: a mano, y cada semana el cron `source-reread-cron`
  (`wk/streams/source_reread_cron.py` → `sources.reread_due`) relee las webs
  leídas hace más de 7 días y la web y las redes del propio cliente. Los
  archivos no se releen solos. Nunca dos lecturas de la misma fuente a la vez.
  Los cambios llegan como propuestas.

La tarjeta de lectura del Panel solo sigue la lectura de la web y las redes del
cliente (`sources.latest_site_read`), no la de cada fuente.

## Redes

`PUT …/business/links` con `If-Match` (la revisión de `links`): la lista entera,
normalizada como en el alta (`links.link_from_choice`). Instagram y Facebook
están siempre en la consola; TikTok, LinkedIn, YouTube, X y Threads se añaden.
Lo que ya estaba conserva su id y su procedencia; la web del negocio sigue a la
primera web de la lista.

## La lectura de la web (el alta)

`services/business/reader.py` (T049): al crear un cliente con web o redes se
lanza un `client_read` que lee hasta 25 páginas del mismo dominio con
`robots.txt`, o los perfiles públicos de sus redes. Lo que no choca se aplica
marcado «Leído de la web · revísalo»; lo que contradice un dato escrito por una
persona queda como propuesta al lado. Lo leído es dato, nunca instrucción
(§III). Avisa a quien la lanzó al terminar o al fallar.

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
| `GET /console/clients/{ref}/business/read` · `POST …/read` | La tarjeta de lectura |

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
