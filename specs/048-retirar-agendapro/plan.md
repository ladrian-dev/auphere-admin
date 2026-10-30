# Plan de implementación: 048 — Retirar AgendaPro y dejar Reservas como la única agenda

**Rama**: `047-lista-para-staging` · **Spec**: [spec.md](spec.md) · **Inventario**: 2026-10-29 (96 archivos fuera de pruebas, 44 de pruebas)

## Resumen

Se borra AgendaPro entero (servidor Node y Python, transporte por subprocesos,
etapa de Node del worker, crons, rutas, columna, conector, catálogo, panel,
consola, plantillas, secretos de Browserbase y documentación). `booking.*` se
retira en dos pasos: ahora deja de ofrecerse y los clientes que la usan pasan a
Reservas con sus citas futuras; el borrado del servidor y de `appointments`
queda para cuando nadie la nombre en producción (requisito 5, otra entrega).

## Contexto técnico

- **Migración** `0205_retire_agendapro` sobre la cabeza `0204_console_v2_for_all`.
  Comprueba primero (falla y nombra clientes si alguno tiene AgendaPro); después
  borra `tenant_connectors` del conector y el conector (precedente: `0014`), las
  filas `agendapro.*` de `tool_catalog` (incluidas las dos que `0021` olvidó),
  `tenants.agendapro_public_url`, `appointments.public_booking_status` con
  `ix_appointments_public_pending` y su CHECK, y cancela los `scheduled_jobs`
  pendientes de tipo `no_show_scrape` y `async_booking`. Marca `booking.*` como
  retiradas en el catálogo. El `downgrade` vuelve a crear las columnas, no los
  datos.
- **Worker**: `bootstrap.py` sin `agendapro_public_pool` ni los dos crons;
  `SCHEDULER_TASK_NAMES` y `ALL_EXPECTED` de `test_bootstrap_split.py` cambian en
  el mismo commit (lección de las specs 003 y 005). Dockerfile sin la etapa
  `node-build` ni `NEXUS_AGENDAPRO_PUBLIC_NODE_CMD`/`_CWD`.
- **MCP**: fuera `servers/agendapro_public/`, `subprocess_tool.py` y
  `transports/{stdio,pool}.py` (solo los usa AgendaPro), y su registro interno.
  `test_registry_unit.py` fija el conjunto interno vacío y el total nuevo.
- **Pasar a Reservas**: se amplía `services/reservations/admin.py::prepare_agent_versions`
  para reescribir también el AgentSpec (`tools`, `procedures[].tools`) y el texto
  de las instrucciones con un mapa fijo `booking.* → reservas.*`
  (`check_availability → find_slots`, `create_appointment → create`,
  `modify_appointment → reschedule`, `cancel_appointment → cancel`,
  `get_appointments → list_mine`). Con la 047, la versión preparada es el borrador
  único del agente y se publica por la puerta. La importación de citas casa el
  servicio por nombre normalizado con `reservation_services` y la persona (nodo
  del KG) con `reservation_staff` por nombre; lo que no casa va al informe.
- **Lectores de `appointments`**: `servers/client/tools.py:get_history` y
  `servers/commission/tools.py` leen las dos tablas, sin duplicar lo importado
  (la cita importada guarda su `appointment_id` de origen).

## Constitution Check

| # | Principio | ¿Cumple? | Prueba / justificación |
|---|---|---|---|
| I | Aislamiento | ☑ | El paso a Reservas corre bajo la RLS del cliente (`as_tenant`), en una transacción. Las tablas tocadas ya tienen RLS FORCE. `test_43` sigue en verde; `appointments` sale de su inventario solo en el requisito 5 |
| II | Superficie | ☑ | Se **cierra** superficie: dos rutas y el navegador remoto de Browserbase |
| III | Lo leído es dato | ☑ | Sin cambios |
| IV | Acción `mutates` | ☑ | La versión preparada no se promueve sola; pasa la puerta. **Enmienda del 2026-10-29**: el paso automático publica sin la puerta un cambio 1:1 que decide Auphere, desde la versión activa y nunca desde el borrador del partner, firmado (`platform:reservas-pass`) y con su motivo en la versión y en la auditoría (decisiones 12 y 17) |
| V | Estados honestos | ☑ | La migración no borra en silencio la configuración de un cliente: se niega y lo dice. Las citas no importadas se listan |
| VI | Por API | ☑ | **Enmienda del 2026-10-29**: el paso a Reservas ya no es una acción; corre en la tarea de migración (decisión 11). Activar Reservas sigue siendo `PUT /admin/tenants/{id}/client-access` |
| VII | Test primero | ☑ | Fase 1 de `tasks.md` |
| VIII | Licencias | ☑ | Ninguna dependencia nueva; salen las de Node (Stagehand, Browserbase) |
| IX | KB | ☑ | `[[research/2026-10-29-auditoria-del-constructor/_index]]` |

### Las tres puertas

| Puerta | Respuesta | Tarea |
|---|---|---|
| Aislamiento | Garantías 1, 2, 5 y 9; ninguna se debilita | T006, T024 |
| Licencias | Sin dependencias nuevas | — |
| Medidor | Nada nuevo; se deja de usar Browserbase | — |

## Documentación (mismo commit)

| Documento | Cambio |
|---|---|
| `RUNBOOK.md` | Fuera las secciones de AgendaPro y Browserbase |
| `docs/console.md` | Sin AgendaPro en Conectores |
| `docs/reservas.md` | Reservas es la única agenda; «Pasar a Reservas» y su informe |
| `docs/companion/capabilities.yaml` | Sin AgendaPro |
| `apps/mcp/README.md` | Sin el servidor de AgendaPro |

## Decisiones de la implementación (2026-10-29)

Las que el plan no dejaba escritas, decididas con criterio:

1. **«Retirada» es `deprecated`, no un valor nuevo de `tool_status`.** El enum
   tiene `active`, `deprecated`, `experimental` e `internal`, y `deprecated` ya
   significa exactamente lo que pide el requisito 2.2: el repositorio, la
   consola, las capacidades, el panel y el constructor no lo listan, y
   `AgentConfigService` lo sigue aceptando en una versión que ya lo tiene; el
   runtime no mira el estado. Añadir `retired` exigía un `ALTER TYPE … ADD
   VALUE` (que no se puede usar en la misma transacción) para no ganar nada.
2. **La retirada la decide el código, no solo el catálogo.**
   `services/agent_spec/retired.py` tiene el mapa fijo; el validador rechaza
   `booking.*` **por nombre** con `tool_retired` y `replacement` (en
   `problems_out` y en los hallazgos de la puerta), aunque un entorno no haya
   corrido la 0205. El constructor la descarta (`why: tool_retired`) y no la
   enseña al modelo; `PUT /console/…/tools` rechaza **añadirla** (422
   `tool_retired` con `replacements`) y deja estar la que el agente ya tenía.
3. **La 0205 también comprueba credenciales.** Además de la URL pública y las
   conexiones, una fila de `tenant_credentials` con `integration='agendapro'`
   cuenta como «AgendaPro configurado». Una conexión `disconnected` no bloquea
   (es el estado terminal) y se borra con el conector. Corre con
   `row_security = off`: con el rol de migraciones no cambia nada; con uno que
   no saltara la RLS la guarda fallaría en voz alta en lugar de no ver a nadie.
   Compara `kind::text` porque en una base nueva Alembic corre todo en una
   transacción y el valor `async_booking` (0022) no se puede usar como literal.
   Siembra la frase de auditoría `reservations.passed`.
4. **El borrador preparado es el único del agente.** «Pasar a Reservas» y la
   activación escriben con `AgentConfigService.open_draft`/`finish_draft` (la
   revisión se mueve y queda `agent_config.stage` con los campos), copian el
   AgentSpec reescrito (un borrador nuevo no lo hereda de la versión de partida)
   y marcan sus pruebas como desactualizadas. Si el borrador ya dice lo que tiene
   que decir, no se toca: repetir no crea revisiones.
5. **Qué gana el agente.** Las nueve `reservas.*` en `tools` y en `spec.tools`
   (como ya hacía la activación de la 043), y el cambio uno a uno en los
   procedimientos y en el texto. Si `spec.tools` rozara su máximo (60), solo el
   cambio uno a uno.
6. **La importación casa por nombre** (sin tildes, mayúsculas ni espacios de
   más): el servicio con un servicio de Reservas no archivado y el barbero (el
   nodo `Barber` del grafo) con una persona del equipo que pueda hacer ese
   servicio; si esa persona ya tiene una reserva viva que se solapa, no se pisa.
   La reserva importada nace **confirmada**, con origen `agent` y canal
   `whatsapp`, la duración y el precio de la cita, **sin mensajes** a nadie, y
   guarda la cita de origen en su clave (`appointment:<id>`): así no hace falta
   columna nueva y los lectores no cuentan dos veces. En **Aforo** no se importa
   nada (`capacity_mode`): una cita no dice para cuántas personas.
7. **El historial y las comisiones** leen las dos agendas
   (`nexus_mcp/_agenda.py`). Una reserva cuenta si está `confirmed`, `arrived` o
   `done`; el barbero de una reserva es el nodo `Barber` con el mismo nombre que
   la persona del equipo (si no hay, sale con su nombre y sin `barber_id`).
   `client.get_history` añade `source` y `staff_name`.
8. **Lo que se queda**: el mecanismo `dispatch_internal` (vacío), la ruta de
   capturas de pantalla del panel (para filas viejas), las frases de auditoría de
   la URL de AgendaPro (para leer filas viejas), los valores del enum de
   `scheduled_jobs`. `booking_status` sale de la salida de
   `booking.create_appointment`: ya no hay reserva asíncrona.
9. **El texto de las plantillas** se reescribió a mano donde describía
   AgendaPro (el «modelo asíncrono» de la barbería, el email de relleno, escalar
   cancelaciones porque el flujo público no las hacía). En los agentes que pasan,
   la reescritura es solo de nombres: un párrafo así heredado de la plantilla lo
   revisa el partner antes de publicar.
10. **La pantalla del panel** (T022, la parte de interfaz). **Retirada por la enmienda del 2026-10-29 (decisión 11)**: se borra con sus rutas en T027. Se deja escrita como historia:
    - **Dónde.** `/tenants/legacy-booking`, «Clientes › Pasar a Reservas», con un
      botón en la cabecera de Clientes. Es una lista de clientes, así que cuelga de
      Clientes como `/tenants/new`. No va en la barra lateral, porque dura hasta el
      requisito 5, y su estado vacío en producción es la señal que ese borrado espera.
    - **Sin Reservas, no hay paso.** Un cliente con `reservas_enabled = false` no
      ofrece «Pasar a Reservas», que daría 409. Ofrece «Activar en Acceso», porque
      activarlo ya hace el paso. El 409 se trata igual (aviso con el enlace a Acceso)
      por si alguien lo apaga con la página abierta.
    - **Las horas del informe**, en la zona del negocio (`tenants.timezone`, de
      `GET /admin/tenants`, que la página ya pide para nombrar a los ilegibles). Si
      no se conoce, en UTC y lo dice.
    - **El informe vive en la pantalla** hasta que se cierra o se recarga. El
      duradero es el de la auditoría (`reservations.passed`), y el informe enlaza a
      ella.

## Enmienda del 2026-10-29 (tarde): el paso es automático

Decisión del owner: «No, hazlo automáticamente. Nadie está usando AgendaPro». Y, para los clientes sin Reservas: «Activar Reservas solo». Cambia el requisito 3 de `spec.md`. Lo demás sigue igual.

11. **Dónde corre.** Hay un guion nuevo, `apps/api/scripts/pass_booking_to_reservas.py`. `release.sh` lo llama después de `alembic upgrade head` y del sembrado de conectores, que es lo que ejecuta la tarea de migración de AWS (`infra/terraform/20-services/migrate.tf`).
    - Va a la base directa, como Alembic.
    - Recorre los clientes con el rol de migraciones. Cada uno pasa en su propia transacción, dentro de `admin.as_tenant`, bajo su RLS.
    - Un cliente que falla se deshace solo y deja el evento `reservations.auto_pass_failed`, con `tenant_id` y el motivo. El guion sale con 0: el despliegue no se para por un cliente, y el borrado final (T030) es el que se niega en voz alta si queda alguien.
    - Al terminar escribe una línea con el resumen, `reservations.auto_pass_done`, con los clientes pasados, los fallidos y las citas importadas y no importadas. Es la señal que espera T030.
12. **Publicar sin la puerta.** Es un cambio 1:1 de herramientas que decide Auphere. La versión nueva nace de la **activa**, nunca del borrador, y se promueve con el actor `platform:reservas-pass` y su motivo.
    - Si el agente tiene borrador, también se reescribe, sin publicarlo, y se conserva su revisión. Con un solo borrador por agente, hay que crear y promover una versión mientras ese borrador existe; cómo se hace lo decide la implementación sobre `AgentConfigService`, y se escribe aquí.
    - Las pruebas del agente pasan a desactualizadas con `mark_stale`.
13. **Activar Reservas sin preguntar el modo.**
    - Es aforo de tipo restaurante si el sector guardado (spec 047, requisito 57) es restaurante. Si no hay sector guardado, se mira la plantilla de la que viene el agente (`restaurante_v1`).
    - En cualquier otro caso es citas por persona.
    - Se usa `apply_choice` con los valores de partida del modo.
    - Lo justo para que el agente reserve y el partner vea la agenda en su consola: no abre el acceso de las personas del cliente ni invita a nadie. Si `reservas_enabled` exige el acceso abierto, la implementación separa las dos cosas y lo escribe aquí.
14. **Las citas de un cliente recién activado** casi nunca se importan: Reservas empieza sin servicios ni personas, así que salen en el informe como `service_missing` y se quedan en `appointments`, donde no se pierden (requisito 5). El owner confirma que nadie usaba AgendaPro, así que se espera que haya pocas o ninguna.
15. **«Pasar a Reservas» a mano desaparece**:
    - la pantalla `/tenants/legacy-booking` y su botón;
    - `lib/backend-reservas.ts` y sus pruebas;
    - la miga;
    - `api/admin/reservas_pass.py` con sus dos rutas y su registro;
    - la sección de `docs/admin.md`.

    `passing.py` se queda: lo usan el guion y la activación desde Acceso. `legacy_client` también, porque lo usan el guion y la guarda de T030.

### Decisiones de la implementación de la enmienda (2026-10-30)

16. **Reservas encendido no es el acceso de las personas.** `reservas_enabled` exigía `client_access.enabled`, y también lo exigían la puerta de las herramientas `reservas.*` (`nexus_mcp/servers/reservas/tools.py: _ctx`) y las ofertas del worker (`reservations_cron._offers_on`). Activar Reservas sin abrir el acceso (decisión 13) no habría dejado reservar al agente. Se separan:
    - **Reservas está encendido** si `reservas` está en `client_access.modules` y hay `reservation_settings` (`ClientAccess.reservas_on`). Lo miran las herramientas del agente, las ofertas del worker, `passing.reservas_enabled` y la pestaña Acceso (`set_access`: `had_reservas` y `wants_reservas` ya no miran `enabled`).
    - `enabled` solo dice si las personas del cliente pueden entrar (consola lite y app), como hasta ahora.
    - Consecuencias: apagar el acceso ya no apaga Reservas ni prepara borradores sin `reservas.*`; un cliente que hoy tenga el acceso apagado y `reservas` en la lista vuelve a tener Reservas en su agente al desplegar; marcar Reservas con el acceso apagado pide el modo la primera vez (422 `reservas_mode_required`), como con el acceso encendido. Antes de desplegar conviene mirar en producción `SELECT tenant_id FROM client_access WHERE NOT enabled AND 'reservas' = ANY(modules)`.

17. **Publicar sin la puerta**, sobre `AgentConfigService` (lo que la decisión 12 dejaba a la implementación). `publish_platform_copy` publica una copia de la versión **activa** con las herramientas, el AgentSpec y el texto reescritos, con `AgentConfigRepository.publish_copy` (el mismo camino que ya usan `set_admin_access` y el retiro de modelos para publicar mientras hay un borrador pendiente; gana los parámetros `tools`, `system_prompt_rendered` y `spec`).
    - Bloquea la fila del agente como cualquier escritor de su borrador; no mueve la revisión del borrador.
    - La versión nueva lleva `created_by`, `promoted_by` y `published_by` = `platform:reservas-pass`, la nota «Paso automático a Reservas» y el motivo en `override_reason`; sin `gate` y **sin ventana de deshacer** (deshacer volvería a `booking.*`).
    - En la auditoría del cliente: `agent_config.promote` (con el motivo) y `agent.publish` con `origin: platform` y `override_reason`, como cualquier publicación. Después, `sync_reception_flag` y `mark_stale`.

18. **«Se conserva su revisión»** se lee como que el borrador del partner sigue siendo el mismo (la misma fila, con sus otros cambios, sin publicar ni descartar). Su revisión **avanza una vez** al reescribirlo, como con cualquier escritura (spec 047, requisito 3): una pestaña que lo estaba editando recibe el 412 con el cambio de Auphere en lugar de pisarlo. Un agente sin borrador no recibe uno (`prepare_agent_versions(drafts_only=True)`).

19. **La versión publicada gana las nueve `reservas.*`** (la decisión 5 también vale para ella), además del cambio uno a uno en procedimientos y texto. Con solo las cinco sustitutas el agente no podría reservar en Servicios: `reservas.find_slots` y `reservas.create` piden el id del servicio, que da `reservas.services`.

20. **El modo, en detalle.** Sector guardado `restaurante` → Aforo de tipo `restaurant`; cualquier otro sector → citas por persona, sin mirar la plantilla. Sin sector: la plantilla (`seed_template_ref` de la versión activa o, si no, del borrador) del agente activo **más antiguo** que nombra `booking.*` y viene de una, pasada por `builder.sectors.TEMPLATE_SECTOR` (`restaurante_v1` → `restaurante`). Sin nada de eso, citas por persona. El informe dice de dónde salió (`activated.from`: `sector`, `template`, `default`, o `existing` si ya tenía ajustes y solo faltaba el módulo; `null` si ya tenía Reservas, cuyo modo nunca cambia).

21. **La activación, en detalle.** Si el cliente no tiene fila en `client_access`, se crea con `enabled = false` y `modules = ['reservas']`, colgada de su partner. El partner se lee como la plataforma antes de entrar en la RLS del cliente (`client_access.partner_of`; `partner_tenants` va por partner y la RLS del cliente lo escondería). Un cliente sin partner no puede tener `client_access`: falla con `no_partner` y queda en el registro. Los ajustes, con `admin.apply_choice(prepare_agents=False)`: el paso publica las versiones él mismo. Si cambian los módulos, también `client_access.updated` con `automatic: true`.

22. **A quién recorre.** Todos los clientes, en cualquier estado (también archivados): la guarda del borrado final (T030) cuenta todas las versiones activas y borradores. La lista sale de `tenants` con el rol de migraciones, por fecha de alta; quién nombra `booking.*` lo decide `passing.legacy_client`, ya bajo la RLS del cliente.

23. **Los registros.** Además de `reservations.auto_pass_failed` y `reservations.auto_pass_done` (decisión 11): `reservations.auto_passed` por cliente pasado y `reservations.auto_pass_crashed` si el guion no llega a recorrer los clientes (sale con 1 y `release.sh` sigue igual). El motivo de un fallo es el tipo de error sin datos de nadie (`automation.error_text`) y el que haya debajo. Un fallo no deja fila en la auditoría del cliente: su transacción se deshace entera.

24. **«El partner ve la agenda del cliente en su consola»** (requisito 3.2) **choca con el código**: la consola de partners no tiene una vista de Reservas. La agenda solo existe en la consola lite y la app (`/console/lite/reservas/*`, para las personas del cliente con el módulo), y `test_reservas_client_vs_client.py` exige 403 al partner. No se construye aquí: es superficie nueva y pide su propia spec o una enmienda. Mientras tanto, lo que reserva el agente de un cliente sin personas con acceso solo se ve si se abre ese acceso.

25. **Sin migración.** La cabeza sigue en `0206_sector_guides_builder`: las frases de auditoría que se usan ya existen (`reservations.passed` en la `0205`; `client_access.updated`, `agent.publish` y `agent_config.promote`, de antes).

### Revisión de seguridad (2026-10-30, spec 047 T217)

26. **El paso da el mapa fijo, no las nueve.** El requisito 3.3 dice «con el mapa fijo de `agent_spec.retired`», y el paso publica sin la puerta: con las nueve, un agente que solo tenía `booking.check_availability` salía pudiendo reservar, cancelar y mover citas (`reservas.create`, `reservas.cancel`, `reservas.reschedule`) sin que nadie lo decidiera. Ahora la versión publicada y el borrador reescrito llevan el cambio uno a uno de `booking.*` en `tools`, en el AgentSpec y en el texto, y además **solo** `reservas.services`, que es lo único que justifica la decisión 19 (sin los ids de servicio, `reservas.find_slots` y `reservas.create` no reservan en Servicios); y la añade solo si alguna `booking.*` cambió (`passing.MAP_EXTRA`). **Sustituye a la 19 y, para el paso, a la 5.** Activar Reservas desde Acceso (requisito 3.9, `every_agent`) sigue dando las nueve: es una decisión de una persona y su borrador pasa la puerta. Prueba: `tests/integration/reservations/test_auto_pass.py::test_the_pass_follows_the_fixed_map_and_grants_nothing_else`.
