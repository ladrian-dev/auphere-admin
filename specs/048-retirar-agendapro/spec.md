# Especificación: retirar AgendaPro y dejar Reservas como la única agenda de los agentes

**Rama**: `047-lista-para-staging` (va junto con la enmienda del 2026-10-29 de la spec 047, y se fusiona antes que sus tareas de guías del sector) · **Creada**: 2026-10-29 · **Estado**: Borrador. Decidido por el owner el 2026-10-29; sin marcas abiertas. **Enmendada el 2026-10-29 (tarde)**: el paso a Reservas es automático (requisito 3).

**Entrada**: decisión del owner del 2026-10-29, en la conversación de la auditoría del constructor: «Elimina AgendaPro del todo porque no lo estamos usando y no es requerido por ahora; cualquier cliente que necesite agenda utilizará el módulo de agenda que construimos de forma nativa. Así el agente podrá usar los endpoints internos de la agenda cuando se requiera algo.»

## Encabezado Auphere *(obligatorio)*

| Campo | Valor |
|---|---|
| **Superficie de confianza** | `0` — API de la consola. No se abre nada: se cierran dos rutas (`PATCH /admin/tenants/{id}/integrations/agendapro/public-url` y `PUT /console/clients/{ref}/integrations/agendapro/public-url`) y desaparece un navegador remoto (Browserbase con Stagehand) que el worker lanzaba contra la web pública de AgendaPro |
| **Garantías de aislamiento tocadas** | **1** RLS: la migración borra filas y una columna de tablas de cliente, y pasar a Reservas escribe en tablas de cliente, siempre bajo la RLS del cliente. **2** Lista blanca: las herramientas `booking.*` dejan de ofrecerse y las versiones nuevas llevan `reservas.*`; la lista que ve el runtime sigue siendo la de la versión, sin globales. **5** Prompt: la versión preparada se compila igual que cualquier otra. **9** Agente dentro del cliente: cada agente recibe su propia versión preparada |
| **Nota de KB que la justifica** | `[[research/2026-10-29-auditoria-del-constructor/_index]]` · `[[decisions/ADR-049-la-fabrica-de-agentes]]` §Enmiendas (2026-10-29) |
| **Qué se mide** | Nada nuevo. Se deja de pagar Browserbase (herramienta de pago) |

## Origen

AgendaPro llegó en las specs 008 a 022 como conector «de navegador»: un servidor MCP en Node con Stagehand abría la página pública de reservas del negocio en Browserbase, y el worker reservaba en segundo plano (`async_booking_cron`). El owner confirma que ningún cliente lo usa. Sigue en el código: 96 archivos fuera de las pruebas y 44 de pruebas (inventario del 2026-10-29), una etapa de Node en la imagen del worker, dos crons (uno ya muerto), una columna en `tenants`, un conector que `release.sh` vuelve a sembrar en cada despliegue y dos filas `agendapro.*` en el catálogo que la migración 0021 olvidó borrar.

Además hay **dos agendas propias**:

- `booking.*` escribe en `appointments`. Es la de antes; el negocio no la ve en Reservas. La usan 9 de las 13 plantillas (aesthetic_clinic, barbershop, beauty_salon, clinica, dental, medspa, nail_studio, restaurante y spa), y leen de `appointments` `client.get_history` y `commission.*`.
- `reservas.*` escribe en `reservations`. Es Reservas (spec 043), «la agenda que el negocio ve», con su consola, su app y sus avisos. Ya existe el camino para pasar un cliente: activar el módulo Reservas desde el panel de operador prepara, por cada agente activo, una versión sin `booking.*` y con `reservas.*` (`services/reservations/admin.py`).

## Clarifications

### Session 2026-10-29

- Q: ¿Se retira AgendaPro? → A: **Sí, del todo** (owner). La agenda de cualquier cliente es Reservas.
- Q: ¿Se retira también `booking.*`? → A: **Sí** (recomendación aceptada por el owner el 2026-10-29). Escribe en una tabla que el negocio no ve. Se retira en dos pasos: primero deja de ofrecerse y los agentes que la usan pasan a Reservas; después se borra, solo cuando ninguna versión la nombre.
- Q: ¿Qué pasa si algún cliente tiene AgendaPro configurado al desplegar? → A: **La migración se niega** y dice qué clientes. Borrar la configuración de un cliente en silencio rompería su agente; el operador la quita antes, a sabiendas.
- Q: ¿Se importan las citas de `appointments` a Reservas? → A: **Sí, las futuras**, al pasar el cliente a Reservas, cuando su servicio y su persona casan con los de Reservas. Las que no casan se listan en el informe y no se pierden: siguen en `appointments` hasta el borrado final.
- Q: ¿El paso a Reservas lo hace el operador desde una pantalla del panel? → A: **No, es automático** (owner, 2026-10-29: «No, hazlo automáticamente. Nadie está usando AgendaPro»). Corre en cada despliegue, después de las migraciones, y publica solo la versión con `reservas.*`. La pantalla y sus rutas se quitan.
- Q: ¿Qué hace el paso con un cliente que tiene agentes con `booking.*` y no tiene Reservas? → A: **Le activa Reservas** (owner, 2026-10-29): en aforo si el negocio es un restaurante y en citas por persona en cualquier otro caso. Reservas empieza vacía: hasta que se carguen servicios y personas, el agente no encuentra huecos y pasa la petición al equipo.

## Escenarios de usuario y pruebas *(obligatorio)*

### Historia 1 — AgendaPro deja de existir (Prioridad: P1)

Un operador o un partner ya no ve AgendaPro en ningún catálogo, asistente ni plantilla. El worker arranca sin la etapa de Node ni los crons de AgendaPro, y su imagen pesa lo que pesaba sin Stagehand.

**Por qué esta prioridad**: es lo que pidió el owner y quita una superficie (un navegador remoto) que nadie usa.

**Prueba independiente**: el catálogo de conectores, el de herramientas y las plantillas no contienen AgendaPro; las rutas responden 404; el contrato de nombres de crons del worker no los nombra.

**Escenarios de aceptación**:

1. **Dado** un despliegue sin ningún cliente con AgendaPro, **cuando** corre la migración, **entonces** desaparecen el conector, sus filas del catálogo, la columna `tenants.agendapro_public_url` y el estado de reserva asíncrona de `appointments`.
2. **Dado** un cliente con la URL pública de AgendaPro puesta, **cuando** corre la migración, **entonces** falla con un mensaje que nombra el cliente, y no cambia nada.
3. **Dado** el siguiente despliegue, **cuando** `release.sh` siembra los conectores, **entonces** AgendaPro no vuelve.

### Historia 2 — Los agentes reservan solo con Reservas (Prioridad: P1)

El constructor, las plantillas y «Empezar desde una plantilla» dan a un agente de citas las herramientas de Reservas. Nadie puede añadir `booking.*` a un agente nuevo o editado.

**Prueba independiente**: un borrador generado para una barbería lleva `reservas.*`; el validador rechaza `booking.*` en una versión nueva con un arreglo que propone `reservas.*`.

**Escenarios de aceptación**:

1. **Dado** la plantilla de barbería, **cuando** se crea un agente desde ella, **entonces** sus herramientas y su texto nombran `reservas.*` y ninguna `booking.*`.
2. **Dado** un borrador que añade `booking.create_appointment`, **cuando** se valida, **entonces** se rechaza con el código `tool_retired` y la herramienta de Reservas que la sustituye.

### Historia 3 — Los agentes con `booking.*` pasan solos a Reservas al desplegar (Prioridad: P1)

*(Enmendada el 2026-10-29: era una acción del operador; ahora es automática.)* Nadie tiene que hacer nada. En cada despliegue, después de las migraciones, el sistema busca los agentes que aún nombran `booking.*`. Si su cliente no tiene Reservas, se lo activa. Después publica para cada agente una versión igual a la activa, con `reservas.*` en lugar de `booking.*`, e importa las citas futuras. Si el partner tenía un borrador, también se reescribe, pero no se publica.

**Prueba independiente**: un cliente sin Reservas, con citas futuras en `appointments` y un agente con `booking.*` en su versión activa y en un borrador. Tras el paso:
- Reservas está activado.
- La versión activa nueva no nombra `booking.*`.
- El borrador tampoco la nombra y sigue sin publicar.
- Las citas que casan están en `reservations` y el informe nombra las demás.

**Escenarios de aceptación**:

1. **Dado** un agente con `booking.*` en `tools`, `spec.tools`, un procedimiento y su texto, **cuando** corre el paso, **entonces** la versión activa nueva lleva `reservas.*` en los cuatro sitios y lo demás igual.
2. **Dado** un cliente sin Reservas cuyo negocio es un restaurante, **cuando** corre el paso, **entonces** Reservas queda activado en aforo. Si es una barbería, queda en citas por persona.
3. **Dado** un borrador del partner con otros cambios, **cuando** corre el paso, **entonces** el borrador pasa a nombrar `reservas.*` y sus otros cambios no se publican.
4. **Dado** tres citas futuras, una con un servicio que Reservas no tiene, **cuando** corre el paso, **entonces** dos pasan a `reservations` y el informe nombra la tercera con su motivo.
5. **Dado** un segundo despliegue, **cuando** corre otra vez, **entonces** no encuentra a nadie y no duplica citas ni versiones.
6. **Dado** un cliente cuyo paso falla, **cuando** corre el paso, **entonces** ese cliente queda como estaba, el error queda registrado con su nombre, los demás pasan y el despliegue sigue.

### Historia 4 — El historial y las comisiones leen Reservas (Prioridad: P2)

`client.get_history` y `commission.*` leen las citas de Reservas, y también las de `appointments` anteriores al paso, para que el historial de un cliente final no se corte.

### Historia 5 — `booking.*` y `appointments` se borran cuando nadie los nombra (Prioridad: P3)

Cuando ninguna versión de ningún agente nombra `booking.*`, una migración borra el servidor, sus filas del catálogo y la tabla `appointments`. Si alguna versión la nombra, la migración se niega y dice cuáles.

### Casos límite

- Un cliente con AgendaPro en un entorno y no en otro: la migración se niega solo en el que lo tiene.
- Un agente con `booking.*` en una versión archivada: no bloquea el borrado final; uno con versión activa o borrador, sí.
- Las filas de `scheduled_jobs` de tipo `no_show_scrape` y `async_booking` que estén pendientes se cancelan. Los valores del enum de Postgres se quedan: quitarlos exige rehacer el tipo y no aporta nada.
- Un cliente que ya tiene Reservas activado y además agentes con `booking.*`: el paso automático no cambia su modo; solo publica las versiones e importa las citas.
- Un cliente cuyas personas no tienen abierto el acceso a la app: activar Reservas no lo abre ni invita a nadie. El agente reserva igual; la agenda la verá el negocio cuando se le abra el acceso (la vista del partner queda fuera, `plan.md`, decisión 24).

## Requisitos *(obligatorio)*

### Requisito 1 — AgendaPro desaparece del producto

**Historia de usuario:** Como Auphere, quiero que AgendaPro no exista en ninguna pantalla, catálogo, imagen ni cron, para no mantener ni pagar lo que nadie usa.

#### Criterios de aceptación

1. El sistema NO DEBE ofrecer AgendaPro en el catálogo de conectores, en las plantillas (`connectors.recommended`), en el panel de operador ni en la consola.
2. Las rutas `PATCH /admin/tenants/{id}/integrations/agendapro/public-url` y `PUT /console/clients/{ref}/integrations/agendapro/public-url` DEBEN dejar de existir.
3. El worker NO DEBE arrancar el grupo de procesos de AgendaPro, `async_booking_cron` ni `no_show_scrape_cron`, y su contrato de nombres de tareas NO DEBE nombrarlos. Su imagen NO DEBE llevar Node ni el servidor MCP de AgendaPro.
4. La fachada de `booking.*` NO DEBE tener rama de reserva asíncrona.
5. WHEN corre la migración THEN DEBE borrar el conector `agendapro` (y antes sus `tenant_connectors`), las filas `agendapro.*` del catálogo de herramientas (incluidas `agendapro.get_today_appointments` y `agendapro.scrape_no_shows`), la columna `tenants.agendapro_public_url`, la columna `appointments.public_booking_status` con su índice y su restricción, y cancelar los `scheduled_jobs` pendientes de tipo `no_show_scrape` y `async_booking`.
6. IF algún cliente tiene la URL pública de AgendaPro puesta o una conexión de AgendaPro sin borrar THEN la migración DEBE fallar sin cambiar nada y nombrar esos clientes.
7. `release.sh` NO DEBE volver a sembrar AgendaPro.
8. Los secretos de Browserbase DEBEN salir de las definiciones de tareas de Terraform.
9. La revisión del constructor NO DEBE contar `agendapro.` entre las herramientas que cumplen una promesa de reservar.

### Requisito 2 — La agenda de los agentes es Reservas

**Historia de usuario:** Como partner, quiero que un agente de citas reserve en la agenda que el negocio ve, para que nadie tenga que mirar dos sitios.

#### Criterios de aceptación

1. Las 9 plantillas que usan `booking.*` DEBEN usar las herramientas de Reservas equivalentes, en su lista de herramientas y en su texto.
2. Las herramientas `booking.*` DEBEN quedar en el catálogo como retiradas: el runtime las sigue ejecutando para las versiones que ya las tienen, pero el constructor, el copiloto y el validador NO DEBEN ofrecerlas.
3. WHEN un borrador nuevo o editado incluye una herramienta `booking.*` THEN el validador DEBE rechazarlo con el código `tool_retired` y proponer su sustituta de Reservas.
4. La revisión del constructor DEBE seguir reconociendo `booking.*` en las versiones que ya la tienen, para no marcar como incoherente un agente que todavía reserva con ella.

### Requisito 3 — Pasar solos a Reservas a quien usa `booking.*`

*(Enmendado el 2026-10-29 por decisión del owner: el paso es automático. Sustituye a la versión con pantalla del operador.)*

**Historia de usuario:** Como Auphere, quiero que los agentes que reservan con `booking.*` pasen solos a Reservas al desplegar, sin trabajo manual y sin perder citas, para retirar la agenda vieja.

#### Criterios de aceptación

1. WHEN termina `alembic upgrade head` en un despliegue THEN `release.sh` DEBE ejecutar el paso automático sobre cada cliente con algún agente activo cuya versión activa o cuyo borrador nombre `booking.*`.
2. IF el cliente no tiene Reservas activado THEN el paso DEBE activarlo primero, con los valores de partida del modo. El modo es aforo, de tipo restaurante, si el negocio es un restaurante; se mira el sector guardado (spec 047, requisito 57) o, si no lo hay, la plantilla de la que viene su agente. En cualquier otro caso, citas por persona.
   - El agente DEBE poder reservar con `reservas.*`. Una vista de la agenda para el partner en su consola no existe y queda fuera de esta spec (`plan.md`, decisión 24): la agenda la ve el negocio, en la consola lite y en la app, cuando se le abra el acceso.
   - El paso NO DEBE abrir el acceso de las personas del cliente ni mandar invitaciones si no estaban.
3. WHEN la versión activa de un agente nombra `booking.*` THEN el paso DEBE publicar una versión nueva, igual a la activa salvo una cosa: `booking.*` cambia a `reservas.*` en `tools`, en el AgentSpec (`tools` y procedimientos) y en el texto, con el mapa fijo de `agent_spec.retired`.
   - Es un cambio de la plataforma, no del partner. Se publica sin la puerta de pruebas y queda en la auditoría del cliente como de Auphere, con su motivo.
   - Las pruebas del agente DEBEN quedar desactualizadas.
4. IF el agente tiene un borrador que nombra `booking.*` THEN el paso DEBE reescribirlo igual y NO DEBE publicarlo. Los cambios del partner nunca se publican solos.
5. WHEN se pasa un cliente THEN el sistema DEBE importar a `reservations` las citas futuras de `appointments` cuyo servicio y cuya persona casan con los de Reservas. DEBE dar un informe con las importadas y las que no, con su motivo. Las que no se importan NO DEBEN borrarse.
6. Repetir el paso NO DEBE duplicar citas ni versiones. Un despliegue posterior no encuentra a nadie.
7. Cada cliente DEBE pasar en su propia transacción, bajo su RLS, y dejar el informe en su auditoría (`reservations.passed`, marcado como automático).
   - IF el paso de un cliente falla THEN DEBE deshacerse solo el de ese cliente. El error queda registrado con el cliente y los demás siguen.
   - El despliegue NO DEBE pararse: el runtime sigue ejecutando `booking.*` (requisito 5.3) y el borrado final se niega mientras alguien la nombre (requisito 5.2).
8. El panel de operador NO DEBE tener una pantalla ni rutas para pasar a un cliente a mano.
9. Activar Reservas desde Acceso DEBE seguir preparando, sin publicar, un borrador con `reservas.*` para cada agente activo, como hasta ahora.

### Requisito 4 — El historial y las comisiones leen Reservas

#### Criterios de aceptación

1. `client.get_history` DEBE devolver las citas de Reservas del cliente final y, antes de ellas, las de `appointments` que no se importaron, sin duplicar las importadas.
2. `commission.get_barber_earnings` y `commission.get_daily_report` DEBEN contar las citas de Reservas además de las de `appointments` anteriores al paso.

### Requisito 5 — El borrado final de `booking.*`

#### Criterios de aceptación

1. WHEN ninguna versión activa ni borrador de ningún agente nombra `booking.*` THEN una migración DEBE borrar el servidor `booking`, sus filas del catálogo y la tabla `appointments`, y quitarla del inventario de `test_43`.
2. IF alguna versión activa o borrador la nombra THEN esa migración DEBE fallar sin cambiar nada y nombrar los clientes y los agentes.
3. Hasta ese borrado, el runtime DEBE seguir ejecutando `booking.*` para quien la tenga.

### Entidades clave

- **Conector `agendapro`** y sus `tenant_connectors`: se borran.
- **`tool_catalog`**: las filas `agendapro.*` se borran; las `booking.*` pasan a `status = retired`.
- **`tenants.agendapro_public_url`**: se borra.
- **`appointments`** (por cliente, RLS FORCE por `tenant_id`): pierde `public_booking_status`; sus citas futuras pasan a `reservations` (por cliente, RLS FORCE); la tabla se borra en el requisito 5.
- **Informe del paso a Reservas**: por cliente, en la auditoría del cliente.

## Criterios de éxito *(obligatorio)*

- **CE-001**: ninguna búsqueda de «agendapro» en `apps/` y `packages/` da resultados fuera de las migraciones históricas y de la que lo borra.
- **CE-002**: la imagen del worker baja de tamaño al quitar la etapa de Node (se mide antes y después).
- **CE-003**: tras pasar un cliente a Reservas, el 100 % de sus citas futuras está en Reservas o en el informe, y ninguna se pierde.
- **CE-004**: ningún agente nuevo, desde el constructor o desde una plantilla, nace con `booking.*`.

## Fuera de alcance

- **Otros conectores de agenda** (Google Calendar, Calendly): no cambian.
- **Quitar los valores `no_show_scrape` y `async_booking` del enum de Postgres**: exige rehacer el tipo; quedan sin uso.
- **Reservas por sede**: sigue fuera, como en la 047.

## Supuestos

- Ningún cliente de producción tiene AgendaPro configurado (owner). Si alguno lo tiene, la migración lo dirá y el despliegue se para antes de cambiar nada.
- El requisito 5 va en un despliegue posterior al que lleva el paso automático. No puede ir en el mismo: Alembic corre antes que el paso, y su guarda pararía el despliegue. Se ejecuta cuando el registro del paso en producción diga que no quedó nadie.
