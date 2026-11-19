# Research — spec 064

Lo que hay hoy, leído en `develop` (`1acfd8b5`) el 2026-11-18, y la decisión de
diseño de cada punto. La parte de producto está en la nota de la KB
`research/2026-11-18-reservas-y-ciclo-de-conversacion.md`.

## D1 · La antelación del agente (requisito 1)

**Hoy.** `reservation_settings.agent_min_notice_minutes` (60 por defecto,
`settings.apply_defaults`). `settings.apply_patch` acepta cualquier entero de 0 a
1440 en `agent.min_notice_minutes`. La consola lo valida en
`reservas/actions.ts` (`patchSchema`), pero ningún componente lo envía. Lo
aplican `core._agent_window` (crear y mover con `as_agent`), el `not_before` de
`create_booking` y `move_booking`, y `reservas.find_slots` (`tools._notice`).
Las rutas de la consola usan `not_before = now`.

**Decisión.**
- La API solo acepta los siete valores del requisito 1.2: `NOTICE_MINUTES = (0,
  15, 30, 60, 120, 240, 1440)`. Otro valor da 422 con el campo.
- El valor por defecto no cambia y no hay migración (decisión de Luis).
- La consola añade una sección «Citas que da el agente» en
  `settings/shared-sections.tsx`, montada en Servicios y en Aforo, con un
  `NativeSelect` como el de la lista de espera. Guarda al cambiar, con la
  versión (`useSettingsPatch`).
- `reservas.find_slots` calcula los huecos con `not_before = now` una sola vez y
  los parte en dos: los que el agente puede dar (`slots`) y los que solo quedan
  fuera por la antelación (`too_soon`, una lista de horas). `first_fit` de Aforo
  sigue contando desde la antelación.
- La descripción de la herramienta dice qué hacer con `too_soon`: no ofrecerlas
  ni reservarlas, decir que esa hora la confirma el negocio y ofrecer pasar la
  conversación. `reservas.create` y `reservas.reschedule` ya devuelven
  `too_soon` cuando se intenta, y su descripción dice lo mismo.

**La descripción que lee el modelo es la de la clase.** `ToolBase.to_tool_def`
arma la definición con `cls.description` y el esquema de Pydantic. La fila de
`tool_catalog` de las herramientas nativas (instantánea `0173`) es la del
catálogo del panel, y ya no coincidía con la clase desde la spec 057, sin prueba
de paridad. Por eso no hace falta migración para que `too_soon` llegue al agente.

**Alternativas descartadas.**
- *Dos llamadas a `services_free`* (con y sin antelación): el doble de lecturas
  para el mismo resultado.
- *Una regla en el prompt de cada agente*: obligaría a volver a publicar. La
  descripción de la herramienta la lee el modelo en cada turno, sin publicar.

**Un valor fuera de la lista ya guardado** (alguien lo fijó por la API): se
conserva. La consola lo enseña como una opción más hasta que se cambie.

## D2 · «Atendida» se corrige y se ve sola (requisito 2)

**Hoy.** `automation.mark_done` cierra cada minuto. `core.allowed_actions` da
`noshow` solo con la reserva abierta, hoy y pasada su hora de inicio, y `undo`
solo desde `arrived` o `noshow`, hoy. `core.transition("undo")` deja
`confirmed`. La consola pinta los botones de `allowed`
(`booking-detail.tsx`) y adelanta el estado con un mapa fijo (`undo` →
`confirmed`). La pantalla es un Server Component: lee al entrar y con
`router.refresh()` tras cada acción. `useNow` mueve el reloj cada 30 s, no los
datos.

**Decisión.**
- `CORRECTION_WINDOW = 7 días`, contados desde `ends_at`.
- `allowed_actions` añade, solo en Servicios:
  - `noshow` sobre `done` dentro de la ventana;
  - `undo` sobre un `noshow` cuya hora de fin ya pasó, dentro de la ventana
    (hoy solo se ofrece el mismo día).
- `transition("undo")` deja `done`, no `confirmed`, cuando la reserva es de
  Servicios y su hora de fin ya pasó. Así nunca se ve «Confirmada» una cita
  pasada, ni depende del cron para volver a cerrarse.
- El evento del historial es el de siempre (`noshow`, `undone`) con la persona.
  No se encola ningún aviso: `transition` nunca avisaba.
- El resumen del mes se calcula del estado, así que no cambia de código.
- La consola: el estado adelantado de `undo` es `done` si la cita ya terminó.
- **Relectura.** Un gancho `useAutoRefresh` en `reservas-view.tsx`: cada 45 s,
  con la pestaña visible, llama a `router.refresh()` fuera de la transición que
  atenúa la pantalla. Al volver a ser visible, relee si la última lectura tiene
  más de 15 s. `router.refresh()` conserva el estado de los componentes de
  cliente, así que un diálogo abierto y lo escrito siguen ahí.
- **Desactualizado.** `initial.nowIso` es el instante de la última lectura del
  servidor. Si con la pestaña visible esa lectura tiene más de 150 s, o si la
  relectura llega sin datos o con partes en error, la pantalla conserva la última
  lectura buena del mismo periodo y enseña «Puede que esto no esté al día» con
  «Reintentar».
- Cierre a lo sumo 60 s tras el fin, más 45 s de relectura: menos de 2 minutos.

**Alternativas descartadas.**
- *Tiempo real por SSE como en la Bandeja*: Reservas no publica eventos, y
  montarlo es otra spec. Releer cada 45 s cumple el requisito.
- *Una acción de servidor que traiga solo las reservas*: duplicaría el cargador
  de la página y sus partes.
- *Deshacer a `confirmed` y dejar que el cron cierre*: la cita se vería
  «Confirmada» hasta un minuto.

**La app móvil (2.12).** `apps/mobile/src/api/reservas.ts` traduce `allowed`
por nombre (`ACTION_IN`) y ya conoce `noshow` y `undo`, y `sheet.tsx` pinta lo
que la API permite. Así que **la app de hoy ofrecerá la corrección** en cuanto
se despliegue la API, sin tocar su código: «No vino» sobre una cita atendida y
«Deshacer» sobre un no-show pasado.

El código de `apps/mobile` no se toca. Sí se regeneran tres archivos suyos,
porque la tubería exige que estén al día con esta rama: `src/api/openapi.json` y
`src/api/schema.gen.ts` (las dos rutas nuevas de ajustes de la Bandeja) y
`src/i18n/lite.gen.ts` (los textos nuevos de la Bandeja, que salen de la
consola).

## D3 · El teléfono en la consola (requisito 3)

**Hoy.** `ContactIn.phone` es opcional en la API. La consola valida
`^\+?[0-9 ()-]{6,24}$` y lo deja vacío (`PHONE_RE`, `actions.ts`). Los diálogos
son `services/booking-dialog.tsx` y `capacity/capacity-booking-dialog.tsx`. La
llegada sin reserva va por otra acción con `phone: null`.
`core.contact_customer` enlaza la reserva al contacto cuyo `identifier` es
exactamente los dígitos, con o sin `+`.

**Decisión.**
- Una función `validPhone` en `components/reservas/model/phone.ts`: empieza por
  `+` y tiene de 8 a 15 dígitos, sin contar espacios, guiones ni paréntesis.
- Los dos diálogos de reserva la exigen al crear. Al mover no se toca.
- `createSchema` de `actions.ts` exige el teléfono con la misma regla: la acción
  de servidor es la que manda, no solo el formulario.
- La lista de espera conserva la regla de antes (`PHONE_RE`, opcional).
- **La API no cambia.** La app móvil sigue mandando el teléfono vacío (3.5), y
  una prueba lo fija.
- Prueba de aislamiento nueva en `tests/isolation/test_reservas_customer_axis.py`.

**Alternativa descartada.** *Exigirlo en `ContactIn`*: rompería la app de hoy,
que Luis dejó fuera.

## D4 · Una conversación resuelta empieza de cero (requisito 4)

**Hoy.** `pipeline._load_recent_history` lee los últimos 20 mensajes desde
`conversations.attended_at`, que solo mueven «Vaciar» y «Eliminar».
`inbox_lifecycle.resolve` pone `CLOSED` y `closed_at`. `reopen` lo deshace, y lo
llaman la ruta de la Bandeja (una persona) y
`persistence.messages.upsert_conversation_for_customer` (el contacto, o `system`
cuando sale un aviso). Los avisos de Reservas y de cobranza se guardan como
`Message` salientes con `actor_kind = "system"`, y `reservation_outbox.message_id`
los une a su reserva u oferta.

**Decisión.** Dos columnas en `conversations`:

- `context_from`: desde cuándo lee el agente. `NULL` = desde `attended_at`.
- `cut_on_reopen`: lo pone `resolve`. Dice que la próxima reapertura por el
  contacto o por el sistema corta.

Reglas:

1. `resolve` pone `cut_on_reopen = true`.
2. `reopen` por una persona lo apaga y no toca `context_from`: el contexto sigue
   (4.4).
3. `reopen` por el contacto o por el sistema, con `cut_on_reopen`, fija
   `context_from` en el punto de corte y lo apaga.
4. El punto de corte es `closed_at`, adelantado al aviso de sistema más antiguo
   que siga sin respuesta y vigente (4.6): un saliente con `actor_kind =
   "system"` posterior al último entrante y anterior a `closed_at`. Vigente:
   - con fila en `reservation_outbox` y reserva: la cita no ha pasado;
   - con fila y oferta: la oferta sigue `running`;
   - sin fila, pero enviado por plantilla (cobranza, envío directo): hace menos
     de 7 días.

   El texto de espera que sale cuando una puerta no deja contestar también lleva
   `actor_kind = "system"`, pero es una respuesta a lo que el contacto escribió:
   no es un aviso y no adelanta el corte.
5. Un aviso que reabre (4.5) se guarda después de `reopen`, así que queda dentro.
6. El worker lee desde `greatest(attended_at, context_from)`.
7. Con `context_from` puesto, el historial lleva al final una nota de sistema con
   el nombre del contacto y con que ya es un contacto del negocio (4.2).

Una conversación resuelta antes del despliegue tiene `cut_on_reopen = false`, así
que no corta hasta que se vuelva a resolver (4.8). La Bandeja sigue leyendo desde
`attended_at`: no ve la diferencia (4.3).

**El nombre es dato, no instrucción (constitución §III).** Viene del perfil de
WhatsApp, que escribe el cliente final. Se normaliza (NFKC), se queda en letras de
cualquier alfabeto, espacios y `.'-`, sin los rellenos invisibles ni las letras que
imitan `<`, `>` y `/`, y con 3 palabras y 30 caracteres como mucho: un nombre, no
una frase que pase por una orden. Entra con el vallado común del proyecto
(`core/guardrails/untrusted.fence`, etiqueta `<client_name>`, cubierto por su prueba
de paridad) y la advertencia de que nunca es una instrucción. Si no queda nada, la
nota no lo nombra. (Revisión de seguridad del 2026-11-19, hallazgo medio.)

**Lo que no se toca.**
- `booking_brake.load_conversation_backing` sigue leyendo desde `attended_at`.
  No le da memoria al modelo: comprueba que una frase «tu cita está reservada»
  tiene una reserva detrás. Con menos historia frenaría de más.
- El estado del hilo de LangGraph: `history` se vacía en cada turno
  (`checkpoint_shrink_update`).

**Alternativas descartadas.**
- *Mover `attended_at` al resolver*: vaciaría la Bandeja, que es lo que hace
  «Vaciar».
- *Una fila de conversación nueva por cada resolución*: rompe D11 de la 030 (un
  hilo por contacto y número) y todo lo que cuelga de `conversation_id`.
- *Un resumen de lo anterior hecho por el modelo*: fuera de alcance, y gasta.

## D5 · Cierre por inactividad (requisito 5)

**Hoy.** No existe. No hay ajustes de la Bandeja ni ruta para ellos. Los crons
de Reservas recorren los clientes desde `tenants` (sin RLS) y miran cada uno en
su sesión acotada, porque `client_access` lleva RLS FORCE.

**Decisión.**
- `client_access.inbox_autoclose_hours`: `NULL` (nunca), 24, 72, 168 o 720, con
  su `CHECK`. Va en `client_access` porque es la fila que ya dice si el cliente
  tiene Bandeja, una por cliente y con RLS.
- `GET` y `PATCH /console/lite/inbox/settings`, con `lite_scope("inbox")`.
- `inbox_lifecycle.close_inactive(session, hours, now)`: resuelve como `system`,
  con `{"reason": "inactivity"}` en el evento, las conversaciones `OPEN`, con el
  agente activo, sin persona asignada, sin motivo de espera, visibles en la
  Bandeja (`attended_at`) y con `last_message_at` anterior al plazo. Hasta 200
  por pasada.
- Cron nuevo `inbox-autoclose-cron` en el planificador, cada 5 minutos, con el
  bucle de `reservations_cron.pass_over_tenants`. Publica el evento de tiempo
  real de cada conversación cerrada, tras el commit.
- La consola: un botón «Ajustes» en la cabecera de la Bandeja abre un diálogo con
  el desplegable. El hilo dice «Se cerró por inactividad» (`event-text.ts`).

**El nombre del cron va en tres sitios** de `bootstrap.py` (la lista del
planificador, `_spawn` y `ALL_EXPECTED`) y en
`tests/unit/test_bootstrap_split.py`. Olvidarlo ha roto la tubería dos veces
(spec 003 y spec 005).

**Alternativas descartadas.**
- *Calcular «resuelta» al leer, sin cron*: el contacto que vuelve a escribir
  tiene que encontrar la conversación cerrada para que corte, y la lista por
  defecto tiene que dejar de enseñarla.
- *Una tabla de ajustes de la Bandeja*: un solo valor no la justifica.

## Pruebas: dónde corren

- Base propia: `NEXUS_DATABASE_URL=…/nexus_test_064` y otro índice de Redis, para
  no pisar a otras sesiones.
- Las del worker van aparte de las de la API (choque de `tests.conftest`).
- `test_consumer_coalesce` del worker necesita `uv run --with lupa` en local.
- Desde 2026-11-03 la tubería solo corre de camino a `main`: lo que se corre
  aquí es lo único que mira el código antes de `develop`.
