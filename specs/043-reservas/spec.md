# Especificación: Reservas — el agente reserva y el negocio lo ve, en dos modos

**Rama**: `043-reservas` · **Creada**: 2026-10-22 · **Estado**: Aclarada (decisiones del 2026-10-22 en §Clarifications) · **Enmendada el 2026-11-04**: Reservas manda y cada profesional conecta su calendario (requisitos 11 a 14)

**Entrada**: diseño de Claude Design (proyecto `e443cbee-f802-4f49-8ec6-422e1d8d97e6`,
descargado el 2026-10-22): «Consola Customers.dc.html» (Reservas en modo
Servicios), «Reservas Aforo.dc.html», «Reservas - Investigacion.dc.html» y las
«Notas para Claude Code». Decisiones del owner del mismo día.

## Encabezado Auphere *(obligatorio)*

| Campo | Valor |
|---|---|
| **Superficie de confianza** | `0` — API de la consola. Las personas del cliente (web y app) y el agente operan la agenda por la API y por herramientas; el cliente final sigue llegando por el WhatsApp ya conectado. La historia P3 (Google Calendar) usa el proveedor de consentimientos que ya existe (spec 023): no abre superficie nueva |
| **Garantías de aislamiento tocadas** | **1** (RLS: siete tablas nuevas por cliente, FORCE, y toda referencia entre ellas con clave foránea compuesta `(tenant_id, id)`) · **2** (la lista blanca: activar Reservas prepara una versión del agente con `reservas.*` y sin `booking.*`; nunca la promueve sola) · **8** (cliente final dentro del negocio: ninguna herramienta nueva acepta cliente; el agente solo ve y toca las reservas de la persona del turno). **Superficie nueva**: la agenda de **todo** el negocio, para la persona del cliente con el módulo. Cada eje lleva su test de barrido |
| **Nota de KB que la justifica** | `[[research/2026-10-22-reservas-y-consola-customers/_index]]` (sustituye, para Reservas, a `[[research/2026-10-19-consola-lite-movil]]` §5 puntos 4 y 5) |
| **Qué se mide** | Los mensajes que el sistema envía por Reservas (confirmación, recordatorio, avisos de cambio, ofertas de la lista de espera) entran en el medidor de mensajes enviados del cliente, como cualquier saliente. Los turnos del agente que reserva se miden como hoy. Ningún modelo nuevo |

> La superficie es la que ya está abierta (`0`): la agenda vive en la API de la
> consola y el agente la toca con herramientas propias, sin navegador.

## Origen

Hoy un agente de barbería o restaurante «reserva» escribiendo en
`appointments` con `booking.*`, y nadie del negocio lo ve: no hay pantalla, ni
endpoint, ni avisos. Medido en el código el 2026-10-22:

1. **No hay agenda.** Ningún endpoint lista `appointments` fuera de las
   herramientas del agente. La spec 031 dejó Reservas fuera.
2. **Doble reserva posible.** `booking.create_appointment` no revalida el hueco:
   dos turnos simultáneos pueden reservar la misma hora.
3. **El profesional es un nodo del grafo** (`barber_id → kg_nodes`, clave de una
   columna) y el servicio, texto libre: el modelo pone duración y precio.
4. **No hay aforo**, ni grupos (`party_size`), ni lista de espera (lo que hay,
   `queue.*`, es la cola de una barbería), ni bloqueos, ni confirmación
   automática. Nadie escribe `confirmed`, `completed` ni `no_show`.
5. **El horario** estaba en tres formas (bug `horario-del-negocio-en-tres-formas`,
   arreglado) y el recordatorio programado no salía (bug
   `el-recordatorio-programado-no-sale`, arreglado).
6. **Google Calendar** está en el proveedor de consentimientos con todas sus
   herramientas bloqueadas (spec 023).

El diseño propone **un módulo, dos formas de reservar**: **Servicios** (una cita
con una persona del equipo: peluquería, clínica, asesoría) y **Aforo** (sitio
para N personas a una hora, sin mesas: restaurante, bar, clases, tours, salas,
spa). El admin de Auphere elige el modo; la consola y la app enseñan solo ese.

## Clarifications

### Session 2026-10-22

Luis no está para aprobar pasos intermedios; las decisiones son de esta sesión,
con su razón, y se revisan al final. Las 16 dudas de
`lecturas/reservas-dominio.md` §8 quedan resueltas aquí.

**Módulo y modo**

- Q: ¿Dónde vive el módulo y el modo? → A: `reservas` es un **módulo de cliente**
  más (`client_access.modules`, junto a `panel`, `inbox`, `usage`). El modo y
  los ajustes viven en `reservation_settings`, una fila por cliente. **Solo el
  admin escribe el modo**, en la pestaña Acceso, en la misma llamada que activa
  el módulo: activar `reservas` sin modo es un 422.
- Q: ¿Qué pasa al cambiar de modo con reservas vivas? → A: **nada silencioso.**
  Si hay reservas futuras vivas (sin confirmar, confirmadas), el cambio responde
  409 `live_reservations` con cuántas son. El admin elige: **«Cancelarlas y
  avisar»** (se cancelan, cada cliente con teléfono recibe el aviso por WhatsApp
  y la reserva guarda por qué) o no cambiar. Nunca conviven dos modos en una
  agenda: las cuentas del aforo no saben qué hacer con una cita de un
  profesional, ni la agenda por profesional con un grupo de seis.
- Q: ¿El vocabulario de Aforo (comensales, personas, plazas; «tiempo máximo de
  mesa», «duración de la sesión»…)? → A: lo elige el **admin con el modo**, como
  **tipo de negocio** (`restaurant`, `bar`, `classes`, `tours`, `rooms`, `spa`);
  trae las palabras y los valores de partida de la tabla del diseño. El negocio
  cambia los números, no el tipo. Servicios no tiene tipo.
- Q: ¿Desactivar el módulo? → A: oculta la pantalla y deja de ofrecer huecos;
  las reservas y los ajustes se conservan (si se reactiva, vuelven). Las
  reservas futuras siguen recibiendo sus recordatorios: el negocio se
  comprometió con esas personas.

**El agente**

- Q: ¿Activar el módulo cambia lo que el agente puede hacer? → A: **prepara**,
  para cada agente activo del cliente, una versión nueva (no activa) con las
  herramientas `reservas.*` y **sin** `booking.*` (escribirían en la tabla vieja,
  que la consola no ve). Promoverla es de una persona (constitución §IV): la
  pestaña Acceso lo dice y enlaza. Desactivar el módulo prepara la versión sin
  `reservas.*`.
- Q: ¿Herramientas? → A: `reservas.find_slots`, `reservas.create`,
  `reservas.list_mine`, `reservas.reschedule`, `reservas.cancel`,
  `reservas.confirm_attendance`, `reservas.join_waitlist`,
  `reservas.answer_offer` y `reservas.services` (catálogo de Servicios).
  **Ninguna acepta cliente**: la persona sale del turno (spec 014). Las
  escrituras **revalidan el hueco dentro de la transacción**, con un candado por
  profesional (Servicios) o por día (Aforo): dos turnos a la vez no pueden
  quedarse la misma hora.
- Q: ¿Estado inicial de lo que reserva el agente? → A: `pending` («sin
  confirmar») si el negocio pide confirmación; si no, `confirmed`. Lo que crea el
  negocio y lo que entra por la lista de espera nace `confirmed`.
- Q: ¿Grupos por encima del máximo (Aforo)? → A: el máximo por reserva de Ajustes
  es el umbral. El agente no los acepta: `reservas.create` responde
  `too_large` y el agente escala con la herramienta de siempre. El negocio sí
  puede reservarlos desde la consola.
- Q: ¿Antelación para reservar? → A: el agente reserva con al menos **60 min** de
  antelación y como mucho a **60 días** (ajustes, con esos valores por defecto).
  El negocio, desde la consola, cualquier hora futura; la llegada sin reserva, la
  franja en curso.
- Q: ¿Señas, recargos y ventana de cancelación? → A: **fuera de esta spec.** El
  diseño no los dibuja y Reservas no mueve dinero. `reservas.cancel` no cobra.

**Estados**

- Q: ¿Vocabulario de estados? → A: el común acordado para API, web y app:
  `pending` (Sin confirmar), `confirmed`, `arrived` (Llegó, **solo Aforo**),
  `done` (Vino / Atendida), `noshow`, `cancelled`. «Llega tarde» y «Choca con
  Google» se calculan, no se guardan.
- Q: ¿`done` se guarda o se calcula? → A: **se guarda**, lo escribe el worker: en
  Servicios, una reserva `pending` o `confirmed` cuya hora de fin pasó; en Aforo,
  una `arrived` cuya estancia terminó. En Aforo, una reserva confirmada que nunca
  llegó **no** se marca sola: queda como estaba hasta que el negocio la marque
  (el diseño deja el «No vino» manual).
- Q: ¿Servicios necesita «Llegó»? → A: no (el diseño no lo tiene).

**Confirmación, recordatorios y avisos**

- Q: ¿Cuándo? → A: Servicios, recordatorio y petición de confirmación **24 h
  antes** (dos interruptores). Aforo, petición de confirmación **24 h antes, el
  mismo día a las 12:00 o 3 h antes**, y **«liberar si no confirman»**: sin
  respuesta 1 h antes, se cancela y el sitio pasa a la lista de espera.
  «Liberar» no existe en Servicios.
- Q: ¿Cómo sale un mensaje al cliente final fuera de la ventana de 24 h? → A:
  con una **plantilla aprobada** del número. Dentro de la ventana, texto. Si no
  hay plantilla aprobada y la ventana está cerrada, no sale, y la reserva lo dice
  en su historial («No se pudo avisar por WhatsApp») — nunca se da por avisado a
  quien no lo fue. Las plantillas que usa el módulo están en
  `contracts/plantillas.md`.
- Q: ¿Quién contesta «Sí, voy»? → A: el agente, que recibe la respuesta en la
  conversación y llama a `reservas.confirm_attendance`.
- Q: ¿Avisos al negocio? → A: tres tipos de push nuevos, **no urgentes**:
  «reserva nueva o cambiada por el agente» (una vez por reserva), «cancelación
  de hoy» y «alguien de la lista de espera aceptó» (apagado por defecto). Solo
  llegan a teléfonos de clientes con el módulo.

**Lista de espera**

- Q: ¿Cómo funciona? → A: como el diseño. Se avisa **solo si falta al menos la
  antelación mínima** (2 h por defecto; 1, 2, 4 o 24 h). Servicios: al cancelar,
  si el negocio lo pide (o el agente al cancelar el cliente), se ofrece el hueco
  **de uno en uno, 5 min cada uno, hasta 5** a quien encaja (mismo profesional o
  cualquiera, servicio que cabe, cita actual posterior). Aforo: cuando se libera
  sitio, a quien quepa por orden, **una oferta abierta por hora**, **15 min**
  para aceptar. Quien acepta tarde se queda el hueco si sigue libre; si no,
  sigue en la lista.
- Q: ¿Se encadena otro aviso cuando quien acepta deja libre su cita anterior? →
  A: **no** (un hueco liberado por una aceptación no dispara otra oferta: evita
  cascadas que el negocio no pidió).
- Q: ¿Caducan las entradas? → A: sí, cuando pasa el día que querían (o la semana,
  si querían «cualquier hueco esta semana»).
- Q: ¿Cómo acepta el cliente? → A: responde a la oferta por WhatsApp; el agente
  llama a `reservas.answer_offer` y el servidor resuelve **la oferta abierta de
  esa persona** (el modelo no nombra ninguna).

**Horario y huecos**

- Q: ¿«Perfil del negocio»? → A: `tenants.business_hours` en su forma canónica,
  y `tenants.timezone`. Lo edita el negocio desde Ajustes de Reservas en la web
  (y el admin); la app lo lee. Un día puede tener dos tramos.
- Q: ¿Negocio sin horario? → A: Reservas no ofrece huecos (ni el agente ni la
  agenda) y Ajustes pide el horario. Nada de inventar 10–19.
- Q: ¿Servicios: horario por persona y comida? → A: cada persona del equipo
  tiene **su** horario semanal (por defecto, el del negocio) con hasta dos tramos
  por día: la comida es el hueco entre tramos, y se pinta como «Pausa». Un hueco
  se ofrece si cabe entero en el horario del negocio **y** en el de la persona.
- Q: ¿Aforo con turnos? → A: turnos (nombre, de–a, llegadas cada X) o franjas (de
  A a B cada X), dentro del horario del negocio. La capacidad se comprueba en
  cada franja de `[t, t + estancia)` que exista; una reserva al final del turno
  no se valida más allá del turno (fuera de turno no se sirve).
- Q: ¿Cuadrícula de Aforo (2a/2b/2c)? → A: **Cuadrícula** = mapa de ocupación
  (2a, días × franjas); **Lista** = la del servicio de hoy (2b, por hora, con
  Llegó/No vino). La «curva» (2c) no entra. Por defecto, Cuadrícula · Semana en
  la web y Día en la app.

**Datos y aislamiento**

- Q: ¿Servicios y equipo en tablas o en el grafo? → A: **tablas**, con RLS FORCE
  y clave compuesta `(tenant_id, id)`. El grafo no tiene horario ni duración.
- Q: ¿Tabla nueva o `appointments`? → A: **`reservations`, nueva.**
  `appointments` la siguen usando el flujo de AgendaPro y las comisiones; cambiar
  sus estados rompería a sus lectores. Las dos no se mezclan: un cliente con el
  módulo usa `reservations` (por las herramientas `reservas.*`).
- Q: ¿Cliente final sin teléfono? → A: la reserva lleva nombre y, si hay,
  teléfono. Con teléfono se enlaza (o se crea) el contacto del negocio y se le
  escribe; sin él no se le escribe nada.

**Conexiones (P3)**

- Q: ¿Qué calendarios? → A: **solo Google Calendar** (decisión del owner). Ni
  Outlook, ni Calendly como «otro sistema manda», ni Cronofy/Nylas.
- Q: ¿Cómo? → A: por el conector de Google Calendar que el cliente ya puede
  conectar en el proveedor de consentimientos (spec 023). Cada persona del equipo
  se asocia a **un calendario** de esa cuenta. Entra su «ocupado» (bloquea
  huecos y marca choques); sale cada reserva como **«Ocupado», sin cliente ni
  servicio**. Lo hace el sistema, no el agente: las herramientas de Google
  Calendar siguen bloqueadas para el agente. Es una historia independiente: la
  043 se fusiona sin ella.

### Session 2026-11-04 (enmienda: Reservas manda)

Decisión de Luis tras leer el estudio de staging
(https://claude.ai/artifact/FFiwsCpcV27E7DNTbPp4FR): «el calendario nativo de
auphere debe ser la fuente de la verdad y conectar otros calendarios debe hacerse
desde el mismo panel ya que cada profesional tiene su propio calendario con sus
propias horas». **Sustituye a la decisión «owner, 2026-11-03»** de los commits
`b45a86c7`, `d0a83763` y `82ff213c`, que hacían reservar al agente solo en Google.
Requisitos 11 a 14. Luis no está para aprobar pasos intermedios: lo demás son
decisiones de esta sesión, con su razón.

- Q: ¿Qué agenda manda? → A: **Reservas, siempre.** La cita del agente nace en
  Reservas, lleva sus recordatorios y sale al calendario del profesional como
  «Ocupado». Google es un espejo y una fuente de «ocupado», nunca el sitio donde
  se reserva.
- Q: ¿Las herramientas de Google Calendar del agente? → A: **Ninguna**, ni para
  leer: los títulos nombran a otros clientes y, con horas de Google a la vista,
  el agente podría ofrecer un hueco que Reservas no da. `GOOGLECALENDAR_CREATE_EVENT`
  y `GOOGLECALENDAR_FIND_FREE_SLOTS` quedan **retiradas** con su sustituta, como
  `booking.*` (spec 048), y el paso automático de cada despliegue las cambia: el
  mismo mecanismo, no uno nuevo. Quien ya pasó no las toca aunque su versión las nombre;
  quien aún no puede reservar sigue como estaba (sesión del 2026-11-05).
- Q: ¿Y Calendly? → A: con **Reservas encendido, tampoco**: conectarlo no da
  herramientas de reservar, y encender Reservas se las quita al borrador. **Sin
  Reservas, Calendly sigue como lo dejó Andrés**: es un negocio que no tiene
  agenda aquí, y Luis no decidió sobre él. Abierto para Luis.
- Q: ¿Una cuenta de Google por negocio o una por profesional? → A: **por
  profesional.** Cada uno tiene su cuenta y sus horas, así que cada uno autoriza
  la suya: una identidad distinta en el proveedor por profesional
  (`tenant_<slug>_staff_<id>`). Una cuenta compartida también vale: se autoriza en
  cada profesional y se elige un calendario distinto. La conexión de Google del
  negocio (spec 023) ya no recibe nada y solo se lee, hasta que cada uno conecte el suyo
  (sesión del 2026-11-05).
- Q: ¿Cómo se evita mezclar calendarios? → A: un calendario, un profesional
  (`calendar_in_use`, también en la base) y la fila dice qué cuenta quedó conectada,
  para que se vea si Lucía quedó con la cuenta de quien pulsó el botón.
- Q: ¿Quién conecta, si el profesional no entra en la consola? → A: cualquiera con
  el módulo, desde Ajustes. **«Conectar»** lleva a Google en ese navegador y
  **«Copiar enlace»** da uno para enviárselo. El enlace es el del proveedor y caduca
  solo; lo que no se completa en una hora vuelve a como estaba.
- Q: ¿«Solo leer»? → A: en el panel no se ofrece. La sincronización lee el ocupado
  y escribe «Ocupado», y la pantalla lo dice antes de ir a Google. El permiso real
  lo fija la configuración de autorización del proveedor, no un botón nuestro.
- Q: ¿Un cambio hecho en Google? → A: **Reservas manda.** Un evento de la persona
  bloquea y, si pisa una reserva, sale como choque. Nuestro «Ocupado» borrado o
  movido a mano se vuelve a escribir donde dice la reserva: mover la cita de un
  cliente sin avisarle no se hace desde otro calendario. Una invitación rechazada
  no bloquea.
- Q: ¿Excepciones por persona (vacaciones, un día libre)? → A: siguen fuera de esta
  enmienda: las cubre su propio calendario (un evento de todo el día bloquea). Sin
  calendario conectado, hoy no hay forma de cerrar un día a una sola persona. Queda
  anotado como trabajo aparte.

### Session 2026-11-05 (revisión independiente de la enmienda)

Una revisión encontró lo que las pruebas no cubrían. Luis dormía y pidió que nada quedara a
medias, así que estas decisiones las tomó la sesión que coordina o esta, con su razón. **Las dos
primeras son de la sesión que coordina y se le deben decir a Luis.**

- Q: ¿Se publica el agente de un cliente que todavía no puede reservar? → A: **No**. Publicarlo
  dejaría a un negocio que reservaba con Google respondiendo que no hay agenda, y el partner no
  tiene panel de Reservas para arreglarlo. El agente sigue como está hasta que esté listo, se
  registra `reservations.auto_pass_not_ready`, se avisa al partner y se ve en el panel de operador.
  Los clientes que solo usan `booking.*` siguen el flujo de la spec 048: `booking.*` deja de existir
  y no hay nada a lo que volver.
- Q: ¿Calendly se publica solo? → A: **No**. El paso automático publica lo retirado; Calendly, no,
  y queda en borrador como dice R11.5.
- Q: ¿Qué pasa con las citas que ya están en el Google del negocio? → A: **No se importan** (un
  evento no dice de qué cliente es), pero esa hora no se vuelve a dar: siguen bloqueando a quien aún
  no conectó el suyo. No tienen recordatorio ni se pueden cancelar desde Reservas.
- Q: ¿Un evento de todo el día? → A: **Bloquea**, salvo cumpleaños y similares (`birthday`,
  `workingLocation`), aunque Google lo marque como disponible: nace así, y es la forma de cerrar un
  día. Uno con hora y marcado como disponible, no.
- Q: ¿Apagar el módulo suelta los calendarios? → A: **No**. Sus reservas por venir y sus avisos
  siguen vivos, y borrarlas de Google le quitaría esa cita a la persona. Salir de Servicios sí los
  suelta: en Aforo no hay profesionales ni panel desde el que hacerlo.
- Q: ¿Se puede editar un agente que espera a que su cliente pueda reservar? → A: **Sí**. La consola
  manda la ficha entera y no sabe quitar una herramienta: si el validador rechaza la que ya tiene,
  no se podría cambiar ni el tono. Lo que ya está en su versión activa o en su borrador sigue hasta
  que pase a Reservas; una nueva, no.
- Q: ¿Y si a ese agente le caduca la conexión de Google? → A: **Se puede renovar.** R11.2 y R11.8
  chocaban: sin renovarla se queda sin agenda, justo el motivo de no publicarlo. Uno nuevo se sigue
  conectando por profesional; uno de antes, si se cayó, se renueva desde las integraciones del
  cliente, y sigue sin darle herramientas a nadie.
- Q: ¿Lo leído del Google del negocio caduca si no se puede leer? → A: **No.** «Con datos viejos no
  se bloquea» vale para el ocupado de una persona, que puede estar libre. Esto son citas que ya se
  dieron: si se liberan, esa hora se vuelve a dar. Solo deja de bloquear al quitar la conexión o
  cuando la persona conecta el suyo.
- Q: ¿Se decide por cliente o por agente? → A: **Por agente.** Uno con Google que espera no retiene a
  otro con `booking.*`, que se retira de todas formas (spec 048).

**Lo que el diseño trae y no entra**

- Canales Instagram, Messenger, «Reserve with Google» y «Web»: no existen (solo
  WhatsApp por Meta). Orígenes: `agent`, `person`, `waitlist`, `walkin`; canales:
  `whatsapp`, `phone`, `in_person`.
- Papeles dentro del cliente («Propietaria», «recepción»): spec 030 los descartó.
  `by` es la persona que la apuntó, por su nombre.
- Mesas (dirección 1c): descartadas por el diseño.
- Datos de ejemplo: del piloto chileno (CLP, +56).

## Escenarios de usuario y pruebas *(obligatorio)*

### Historia 1 — El admin activa Reservas y elige el modo (Prioridad: P1)

En la pestaña Acceso del panel de operador, el admin marca «Reservas», elige
Servicios o Aforo (y en Aforo el tipo de negocio) y guarda. El negocio ve la
pantalla de Reservas de ese modo; el agente tiene preparada su versión con las
herramientas de Reservas.

**Prueba independiente**: activar con modo, ver `reservas` en `/me.nav` y en
`/reservas/settings` el modo; cambiar de modo con reservas vivas da 409 hasta
que se elige cancelarlas.

**Escenarios de aceptación**:

1. **Dado** un cliente sin el módulo, **cuando** el admin lo activa en modo
   Aforo, tipo restaurante, **entonces** el cliente ve Reservas y los ajustes
   traen 64 comensales, 1 h 30 de mesa, 10 por reserva y 6 guardadas.
2. **Dado** 3 reservas futuras vivas, **cuando** el admin pide cambiar a
   Servicios, **entonces** recibe 409 con «3»; si confirma «Cancelarlas y
   avisar», se cancelan con su motivo y el cambio se aplica.
3. **Dado** que se activa, **entonces** cada agente activo del cliente tiene una
   versión preparada con `reservas.*` y sin `booking.*`, y la activa no cambia.

---

### Historia 2 — El negocio lleva su agenda en Servicios (Prioridad: P1)

Valeria da de alta a su equipo y sus servicios, ve la agenda del día por
profesional, crea, mueve, cancela, confirma y marca «No asistió».

**Prueba independiente**: con el equipo y los servicios dados de alta, una
reserva nueva solo se puede poner en huecos libres reales, y dos a la vez no se
quedan la misma hora.

**Escenarios de aceptación**:

1. **Dado** Lucía con horario 9–14 y 15–19, **cuando** busco huecos de 45 min,
   **entonces** no aparece ninguno que pise 14–15 ni una reserva viva.
2. **Dado** dos peticiones simultáneas para la misma hora con Lucía, **entonces**
   una crea y la otra recibe 409 `slot_taken`.
3. **Dado** una reserva con teléfono, **cuando** la muevo con «avisar»,
   **entonces** queda en su historial «Movida por Valeria… Se le avisó por
   WhatsApp» (o «No se pudo avisar» si no salió).
4. **Dado** una cancelación con 3 h de margen y gente en la lista que encaja,
   **cuando** elijo ofrecer el hueco, **entonces** se escribe a la primera y
   arranca su cuenta atrás de 5 min.

---

### Historia 3 — El negocio lleva su ocupación en Aforo (Prioridad: P1)

En el restaurante, la vista dice cuántos hay dentro y cuánto queda por hora;
se reserva por número de personas, se registran llegadas sin reserva, se
marcan «Llegó» y «No vino», y se bloquean horas para un evento.

**Prueba independiente**: con aforo 64, 6 guardadas y estancia 90 min, una
reserva de 10 a las 21:00 cabe solo si en 21:00, 21:30 y 22:00 quedan 10.

**Escenarios de aceptación**:

1. **Dado** 50 personas dentro a las 21:00, **cuando** reservo 10 a las 21:00,
   **entonces** no cabe (64 − 6 − 50 = 8) y el sistema propone el primer hueco
   para 10.
2. **Dado** el mismo momento, **cuando** llega alguien sin reserva con 10,
   **entonces** cabe (las guardadas son para esto: 64 − 50 = 14).
3. **Dado** un bloqueo de 20:00 a 22:00, **entonces** el agente no ofrece esas
   horas y las reservas que ya había se mantienen.
4. **Dado** una reserva confirmada de hoy, **cuando** marco «Llegó» y luego
   «Deshacer», **entonces** vuelve a confirmada.

---

### Historia 4 — El agente reserva sin pisar a nadie (Prioridad: P1)

El cliente final escribe por WhatsApp; el agente ofrece huecos reales y reserva,
mueve o cancela **sus** reservas. Nunca ve ni toca las de otro.

**Prueba independiente**: con dos clientes finales del mismo negocio, el agente
de uno no lista, mueve ni cancela la reserva del otro; dos turnos simultáneos no
reservan el mismo hueco.

**Escenarios de aceptación**:

1. **Dado** un turno sin cliente resuelto, **cuando** el agente intenta reservar,
   **entonces** se niega.
2. **Dado** un grupo de 14 con máximo 10, **entonces** `reservas.create` responde
   `too_large` y no crea nada.
3. **Dado** un día cerrado del horario, **entonces** `reservas.find_slots` no da
   huecos y lo dice.

---

### Historia 5 — Lo automático: confirmar, recordar, liberar, cerrar (Prioridad: P2)

El sistema pide la confirmación y recuerda a su hora, libera en Aforo lo que no
se confirmó, cierra como «Atendida»/«Vino» lo que terminó y avisa al teléfono del
negocio de lo que hizo el agente.

**Prueba independiente**: con el reloj adelantado, cada proceso hace lo suyo
una sola vez.

**Escenarios de aceptación**:

1. **Dado** una reserva de Aforo sin confirmar, **cuando** falta 1 h y «liberar»
   está encendido, **entonces** pasa a cancelada por el sistema y el sitio vuelve
   a contar.
2. **Dado** que el recordatorio ya salió, **cuando** el proceso vuelve a pasar,
   **entonces** no sale otro.

---

### Historia 6 — La lista de espera ofrece lo que se libera (Prioridad: P2)

**Escenarios de aceptación**:

1. **Dado** una oferta en curso, **cuando** el candidato no responde en 5 min
   (Servicios), **entonces** se escribe al siguiente.
2. **Dado** un candidato que responde tarde y el hueco sigue libre, **entonces**
   se lo queda; si ya es de otro, sigue en la lista.
3. **Dado** que faltan menos de 2 h, **entonces** no se ofrece nada.

---

### Historia 7 — Google Calendar del equipo (Prioridad: P3, independiente)

El negocio conecta Google Calendar y asocia un calendario a cada persona del
equipo: su «ocupado» bloquea huecos y las reservas salen como «Ocupado».

**Escenarios de aceptación**:

1. **Dado** un «ocupado» de 16:00 a 17:00 en el calendario de Lucía, **entonces**
   no se ofrece ese hueco y una reserva ya hecha que lo pisa sale «Choca con
   Google · 16:00».
2. **Dado** una reserva nueva con Lucía, **entonces** su calendario recibe un
   evento «Ocupado» sin nombre ni servicio.

---

### Casos límite

- **Sin horario del negocio**: no hay huecos; Ajustes lo pide; el agente dice que
  no puede reservar y escala.
- **Servicios sin equipo o sin servicios**: la agenda enseña cómo empezar (no un
  calendario vacío que parece roto).
- **Cambio de horario con reservas fuera de él**: se mantienen; la agenda las
  pinta y no ofrece huecos nuevos fuera.
- **Archivar una persona del equipo con reservas futuras**: 409 con cuántas; hay
  que moverlas o cancelarlas antes.
- **Bajar el aforo por debajo de lo reservado**: se permite; las horas pasadas de
  aforo salen «Completo» y no se ofrecen; lo ya reservado se mantiene.
- **Cliente final sin teléfono**: nada sale por WhatsApp; el historial lo dice.
- **Módulo desactivado**: 403 opaco en `/reservas/*`; la pantalla no existe.
- **Zona horaria**: toda hora de negocio se interpreta en `tenants.timezone`;
  los límites de día también (no UTC).

## Requisitos *(obligatorio)*

### Requisito 1 — Activar Reservas y elegir el modo (admin)

**Historia de usuario:** Como admin de Auphere, quiero activar Reservas para un
cliente en un modo, para que su consola y su agente trabajen de esa forma.

#### Criterios de aceptación

1. El sistema DEBE aceptar `reservas` como módulo de cliente (enumeración,
   restricción de base de datos y espejos de la consola, el admin y la app).
2. WHEN el admin activa `reservas` THEN DEBE indicar el modo (`services` o
   `capacity`, y en `capacity` el tipo de negocio); IF no lo indica y el cliente
   no tenía ajustes THEN el sistema DEBE responder 422 `reservas_mode_required`.
3. WHEN se activa por primera vez THEN el sistema DEBE crear los ajustes con los
   valores por defecto del modo (y del tipo, en Aforo).
4. IF se pide cambiar el modo y hay reservas futuras vivas THEN el sistema DEBE
   responder 409 `live_reservations` con su número, y NO DEBE cambiar nada.
5. WHEN el admin confirma el cambio con `on_live = cancel_and_notify` THEN el
   sistema DEBE cancelar esas reservas (origen del cambio: `mode_change`),
   encolar el aviso a cada cliente con teléfono y aplicar el modo, en una
   transacción.
6. WHEN se activa o desactiva el módulo THEN el sistema DEBE preparar, para cada
   agente activo, una versión no activa con (o sin) `reservas.*` y sin
   `booking.*`, y NO DEBE promoverla.
7. Toda escritura del admin DEBE quedar en la auditoría con la persona
   (`X-Operator-Id`).

### Requisito 2 — Ajustes del negocio

#### Criterios de aceptación

1. El negocio DEBE poder leer y cambiar sus ajustes salvo el modo y el tipo.
2. El negocio DEBE poder cambiar el horario del negocio (hasta dos tramos por
   día); se guarda en la forma canónica.
3. IF el negocio no tiene horario THEN el sistema NO DEBE ofrecer huecos, y los
   ajustes DEBEN decirlo (`hours_missing`).
4. En Aforo, el negocio DEBE poder cambiar aforo, estancia, máximo por reserva,
   plazas guardadas, el horario de reservas (turnos o franjas, con su paso),
   confirmación (cuándo) y «liberar si no confirman».
5. En Servicios, DEBE poder cambiar recordatorio 24 h y pedir confirmación.
6. En los dos, lista de espera (sí/no) y antelación mínima para avisar (60, 120,
   240 o 1440 min).
7. Valores fuera de rango (aforo ≤ 0, guardadas > aforo/2, paso que no divide el
   turno…) DEBEN dar 422 con el campo.

### Requisito 3 — Equipo y servicios (Servicios)

#### Criterios de aceptación

1. El negocio DEBE poder crear, editar y archivar personas del equipo (nombre,
   correo opcional, horario semanal con hasta dos tramos por día).
2. El negocio DEBE poder crear, editar y archivar servicios (nombre, duración de
   15 a 480 min en pasos de 15, precio opcional en la moneda del negocio, y quién
   lo hace: todo el equipo o una lista).
3. IF se archiva una persona con reservas futuras vivas THEN el sistema DEBE
   responder 409 con su número.
4. Archivar NO DEBE borrar: las reservas pasadas siguen nombrando a la persona y
   al servicio.

### Requisito 4 — Disponibilidad

#### Criterios de aceptación

1. El sistema DEBE ofrecer huecos solo dentro del horario del negocio, en su zona
   horaria, nunca en el pasado y respetando la antelación del agente cuando
   pregunta el agente.
2. Servicios: un hueco DEBE caber entero en el horario de la persona y no pisar
   ninguna reserva viva suya, ningún hueco retenido por una oferta en curso ni
   ningún «ocupado» de su calendario (P3). Pasos de 30 min (ajustable a 15 o
   60) desde el inicio de cada tramo, como el diseño.
3. Aforo: las franjas son las horas de llegada del turno o de la franja, con la
   última incluida (13:00–15:00 cada 30 = 13:00…15:00). Un grupo de `n` cabe a
   la hora `t` si `t` es una franja, no está
   bloqueada y, en cada franja de `[t, t + estancia)`, `aforo − guardadas −
   presencia ≥ n`; la llegada sin reserva usa el aforo entero.
4. Presencia a la hora `t` DEBE ser la suma de personas de las reservas vivas o
   llegadas con `inicio ≤ t < fin`.
5. WHEN no cabe THEN el sistema DEBE decir por qué (`closed`, `blocked`, `past`,
   `full`, `too_large`) y, en Aforo, la primera franja del día en que cabe.

### Requisito 5 — Reservas desde la consola y la app

#### Criterios de aceptación

1. El negocio DEBE poder listar las reservas de un rango (día, semana, mes) con
   filtros (estado, origen, persona del equipo) y abrir una con su historial.
2. WHEN el negocio crea una reserva THEN el sistema DEBE revalidar el hueco con
   candado en la misma transacción; IF ya no cabe THEN DEBE responder 409
   `slot_taken` y NO DEBE crearla.
3. Toda escritura DEBE aceptar `Idempotency-Key`; repetirla DEBE devolver lo
   mismo sin duplicar.
4. Acciones: confirmar, mover/cambiar (revalida), cancelar (con «avisar» y, en
   Servicios, «ofrecer el hueco»), «No vino»/«No asistió», «Llegó» y «Deshacer»
   (Aforo), cada una solo cuando el diseño la permite; fuera de eso, 409
   `invalid_transition`.
5. Toda acción DEBE dejar un evento en el historial con quién la hizo (la
   persona por su nombre, el agente o el sistema).
6. WHEN una acción cambia algo que el cliente final debe saber y la reserva tiene
   teléfono THEN el sistema DEBE encolar el aviso por WhatsApp (salvo que el
   negocio desmarque «avisar») y dejar en el historial si salió o no.
7. Aforo: llegada sin reserva (nombre opcional, nace `arrived`, franja en curso)
   y bloqueos (día, desde, hasta, etiqueta obligatoria) que no tocan lo ya
   reservado.
8. Las escrituras concurrentes sobre la misma reserva DEBEN detectarse (versión);
   la segunda recibe 412 `stale`.
9. El resumen para el Panel y la tarjeta «Hoy en Reservas» de la app DEBEN salir
   de una ruta (`/reservas/summary`).
10. El contacto de la Bandeja DEBE traer su próxima reserva viva (si el cliente
    tiene el módulo).

### Requisito 6 — Herramientas del agente

#### Criterios de aceptación

1. Ninguna herramienta `reservas.*` DEBE aceptar un campo de cliente
   (`customer_id`, teléfono, nombre de otra persona…).
2. `reservas.create` DEBE revalidar con candado, ser idempotente por clave, dejar
   la reserva con origen `agent`, canal `whatsapp`, la conversación y el agente, y
   negarse sin cliente resuelto.
3. `reservas.list_mine`, `reschedule`, `cancel`, `confirm_attendance` DEBEN
   tocar solo reservas de la persona del turno; una reserva ajena DEBE leerse
   igual que una inexistente.
4. `reservas.answer_offer` DEBE resolver la oferta abierta de la persona del turno
   sin que el modelo la nombre.
5. Las herramientas DEBEN registrarse en el catálogo en la misma migración, con
   nombre de negocio en Capacidades, y entrar en la intención de reservar.
6. IF el cliente no tiene el módulo activo THEN las herramientas DEBEN negarse
   («Reservas no está activo»).

### Requisito 7 — Procesos del worker

#### Criterios de aceptación

1. Un proceso DEBE pedir la confirmación y enviar el recordatorio a su hora, una
   sola vez por reserva y tipo.
2. Aforo: IF una reserva sigue sin confirmar 1 h antes y «liberar» está encendido
   THEN el proceso DEBE cancelarla (fuente `system`) y abrir la oferta de la
   lista de espera si toca.
3. El proceso DEBE pasar a `done` lo que terminó (Servicios: `pending`/`confirmed`
   tras su fin; Aforo: `arrived` tras su estancia).
4. El motor de ofertas DEBE avanzar candidatos al vencer el plazo, cerrar la
   oferta al aceptar y no ofrecer con menos antelación que la mínima.
5. Las entradas de la lista caducan al pasar su fecha.
6. Los avisos al cliente final DEBEN salir por plantilla aprobada fuera de la
   ventana de 24 h, por texto dentro; si no pueden salir, el historial lo dice.
7. Los avisos al negocio DEBEN encolarse como push de los tipos nuevos, con la
   regla del módulo y del silencio fuera de horario (spec 045).
8. Cada proceso DEBE declararse en el contrato de nombres de crons del worker.

### Requisito 8 — Pantallas de Reservas (consola customers)

#### Criterios de aceptación

1. La consola DEBE enseñar la pantalla Reservas solo con el módulo, en el modo del
   cliente, con sus pestañas (Agenda u Ocupación · Lista de espera · Ajustes).
2. Vista (Cuadrícula o Lista) y periodo (Día, Semana, Mes) DEBEN ser dos controles
   separados.
3. Cada vista DEBE pintar cargando (esqueleto con las medidas finales), vacío,
   error, parcial e ideal, y cumplir WCAG 2.2 AA, a 360 px y a 1920 px, en claro y
   oscuro, con los tokens de `@nexus/ui`.
4. El Panel DEBE enseñar el bloque de Reservas del modo (cifras y próximas de hoy)
   y la fila de atención «N reservas de hoy sin confirmar».

### Requisito 9 — Lo mínimo en el panel de operador y la consola de partners

#### Criterios de aceptación

1. La pestaña Acceso DEBE ofrecer Reservas con el modo (y el tipo), el aviso de
   cambio con reservas vivas, y el enlace a promover la versión del agente.
2. La consola de partners DEBE nombrar las herramientas nuevas en Capacidades
   (grupo Citas). Nada más.

### Requisito 10 — Google Calendar (P3, independiente)

#### Criterios de aceptación

1. WHERE el cliente tiene Google Calendar conectado, el negocio DEBE poder asociar
   un calendario a cada persona del equipo.
2. El sistema DEBE leer el «ocupado» de esos calendarios (sin títulos ni
   asistentes) y tratarlo como no disponible.
3. El sistema DEBE escribir cada reserva viva como un evento «Ocupado» sin datos
   del cliente ni del servicio, y moverlo o borrarlo con la reserva.
4. Una reserva viva que pisa un «ocupado» DEBE salir marcada como choque.
5. Las herramientas de Google Calendar del agente DEBEN seguir bloqueadas.

> **Enmienda del 2026-11-04.** R10.1 cambia: ya no hay una cuenta por negocio, cada
> profesional conecta la suya (requisito 12). R10.5 pasa de ser el modo con el que
> nace la herramienta a una garantía en cada capa (requisito 11).

### Requisito 11 — Reservas es la única agenda (enmienda del 2026-11-04)

**Historia de usuario:** Como negocio, quiero que toda cita que tome el agente esté
en Reservas, para verla, que lleve sus recordatorios y que nadie ocupe esa hora.

#### Criterios de aceptación

1. Conectar Google Calendar NO DEBE añadir ninguna herramienta a un agente ni a su
   borrador, ni al completar la autorización, ni al activar la conexión, ni al
   sincronizar.
2. El turno de un agente cuya versión activa tiene `reservas.*` NO DEBE ver ni ejecutar ninguna
   herramienta del conector Google Calendar, aunque su versión la nombre y la conexión esté
   activada. El de un agente que aún no pasó DEBE seguir como estaba: quitársela sin darle
   Reservas lo dejaría sin agenda.
3. El validador del AgentSpec y la lista de herramientas de la consola DEBEN rechazar toda
   herramienta `GOOGLECALENDAR_*` con `tool_retired` y su sustituta si la tiene: crear
   (`reservas.create`), ver huecos (`reservas.find_slots`), mover (`reservas.reschedule`),
   borrar (`reservas.cancel`) y buscar eventos (`reservas.list_mine`). Lo que ese agente ya nombra
   en su versión activa o en su borrador NO DEBE impedir editarlo ni publicarlo hasta que pase a
   Reservas; lo que nombra otro agente del cliente no cuenta.
4. WHEN corre el paso automático de un despliegue IF una versión activa nombra una
   herramienta de Google Calendar THEN, si el cliente puede tomar una cita, DEBE publicar una copia
   sin ella, con su sustituta si la tiene, en `tools`, el AgentSpec y el texto (incluidos los pasos
   de sus procedimientos), y sin pedir conectar Google ni Calendly; un borrador que la nombra se
   reescribe igual y no se publica. IF el cliente no puede tomarla (`reservas_off`, `hours_missing`,
   `no_staff`, `no_services`, `no_bookable_service`, `no_capacity`) THEN NO DEBE encender nada por
   ese agente ni tocarlo: DEBE registrar `reservations.auto_pass_not_ready` con las razones, avisar
   al partner (`reservas.pass_not_ready`) y enseñarlo en el panel de operador
   (`reservas_pending_pass`). Se decide agente por agente: otro del mismo cliente con `booking.*`
   DEBE pasar igual, como pide la spec 048. IF el paso falla THEN el agente DEBE seguir funcionando como estaba,
   y DEBE quedar en la auditoría (`reservations.pass_failed`, sin el texto del error) y en un aviso
   al partner. El despliegue NO DEBE pararse por ello.
5. WHEN se enciende Reservas THEN el borrador de cada agente activo DEBE ganar
   `reservas.*` y perder lo que reserva en un conector, sin publicarse; y mientras su
   versión activa siga reservando en un conector, la pestaña Acceso DEBE decirlo. El paso automático
   DEBE dejar en un borrador, sin publicarlo, lo que reserva en un conector. IF alguien descartó ese
   borrador THEN NO DEBE volver, ni repetirse el paso, mientras siga la misma versión activa.
6. WHERE Reservas está encendido, conectar o activar un conector que reserva NO DEBE
   añadir sus herramientas de reservar.
7. WHERE Reservas está apagado, conectar Calendly DEBE seguir como hasta ahora.
8. Las integraciones que se ofrecen a un agente NO DEBEN incluir Google Calendar, tampoco si el
   cliente lo tenía conectado. En las integraciones del cliente, una conexión de antes DEBE poder
   renovarse si se cayó, y quitarse, con un texto que diga dónde se conecta uno nuevo. Conectar uno
   nuevo DEBE responder 409 `connect_from_reservas`. Renovarla NO DEBE añadir herramientas.
9. La revisión de lo que promete un agente NO DEBE contar Google Calendar como algo
   que reserva.

### Requisito 12 — Cada profesional conecta su calendario (enmienda del 2026-11-04)

**Historia de usuario:** Como negocio con varios profesionales, quiero conectar el
calendario de cada uno desde Reservas, para que cada uno vea sus citas y sus horas
ocupadas cuenten, sin que se mezclen.

#### Criterios de aceptación

1. Ajustes de Reservas DEBE enseñar, por cada profesional, uno de estos estados con
   su salida: sin conectar, esperando la autorización, conectado, elegir calendario,
   permiso perdido, error.
2. WHEN se pide conectar a un profesional THEN el sistema DEBE crear el enlace de
   autorización con una identidad propia de ese profesional, nunca la del negocio ni
   la de otro, y devolverlo solo a quien lo pidió.
3. WHEN la autorización se completa THEN, al volver al panel o en la pasada siguiente,
   la fila DEBE quedar conectada, con el calendario principal de esa cuenta si se puede
   escribir en él y nadie más del negocio lo usa, y DEBE decir qué cuenta es; si no,
   DEBE pedir que se elija uno.
4. IF se elige un calendario que ya usa otro profesional del negocio THEN el sistema
   DEBE responder 409 `calendar_in_use` con su nombre. La base DEBE impedirlo también.
5. IF se elige un calendario que no es de la cuenta de ese profesional THEN DEBE
   responder 422 `unknown_calendar`.
6. Cada pasada DEBE leer y escribir con la conexión del profesional del calendario. Una
   reserva movida a otro profesional DEBE borrar su evento con la conexión del primero.
7. IF Google rechaza el permiso o la conexión deja de valer THEN la fila DEBE pasar a
   permiso perdido, su ocupado DEBE dejar de bloquear en esa pasada, y los demás
   profesionales NO DEBEN notarlo. «Volver a conectar» DEBE conservar el calendario, y
   DEBE poder hacerse ante cualquier fallo, no solo ante un permiso perdido.
8. WHEN se desconecta a un profesional THEN su ocupado DEBE dejar de bloquear al momento
   y la fila DEBE decir sin conectar; la pasada siguiente DEBE quitar de su calendario
   los eventos de sus reservas por venir y revocar la conexión, y si ya no puede
   borrarlos DEBE revocarla igual y no volver a intentarlo.
   WHEN se borra el cliente THEN la conexión de cada profesional DEBE revocarse al
   confirmarse el borrado: la cuenta de Google es de esa persona.
9. IF un enlace no se completa en una hora o el proveedor lo da por fallido THEN la fila
   DEBE volver a como estaba: con la conexión que funcionaba, si la tenía; si no, sin conectar o, si
   tenía calendario, permiso perdido. IF autorizó y Google no le deja leer THEN DEBE pasar a permiso
   perdido o, si tenía una conexión que funcionaba, seguir con ella y decir que la nueva no entró
   (`new_account_refused`, durante esa hora). IF Google o el proveedor no contestan THEN DEBE
   esperar, y no más de esa hora.
10. IF el proveedor no responde o no tiene configurada la autorización THEN conectar
    DEBE responder 409 `calendar_unavailable` y la pantalla DEBE decirlo.
11. Un profesional de otro cliente DEBE dar el mismo 404 que uno inventado en toda ruta
    de calendario, y la identidad del proveedor NO DEBE salir por la API.
12. Las llamadas al SDK del proveedor NO DEBEN correr en el bucle de eventos, ni reintentarse
    solas: tras un timeout, repetir una escritura la hace dos veces.
13. WHERE el cliente está en Servicios y su conexión de Google del negocio (spec 023) sigue en pie,
    cada pasada del cron DEBE leer de ella el ocupado futuro y hacerlo bloquear a cada profesional
    que aún no sincroniza el suyo: el calendario que dice su fila de antes o, sin ella, el principal
    y el que un agente tuviera elegido. Lo que escribimos nosotros NO DEBE contar. WHEN todos
    sincronizan, o la conexión se quita, NO DEBE leerse ni bloquear más. Nunca se escribe en ella.
    IF la lectura falla, se rechaza el permiso o la conexión se cae THEN lo leído DEBE seguir
    bloqueando: son citas ya dadas, y dejar de leerlas no las cancela. La fila de esa persona DEBE
    decirlo.
14. WHEN se conecta otra cuenta THEN la conexión anterior DEBE seguir hasta que la nueva funcione.
    Entonces, cada reserva por venir de esa persona DEBE quedar en su calendario: el evento que está
    en un calendario al que la cuenta nueva no llega DEBE borrarse con la conexión anterior, si la
    hay, y escribirse de nuevo, y solo después DEBE revocarse la anterior.
15. WHEN el cliente deja de estar en Servicios THEN DEBE desconectarse a todos sus profesionales.
    WHEN se apaga el módulo THEN los calendarios DEBEN seguir sincronizando: las reservas por venir y
    sus avisos siguen vivos.
16. Conectar, cambiar de calendario y desconectar DEBEN dejar `AuditLog` con quién y de qué
    profesional, sin la cuenta de nadie.
17. La página de vuelta del proveedor NO DEBE decir que está conectado si la autorización falló, si
    el enlace caducó o si no lo sabe.
18. Una pasada NO DEBE esperarse a sí misma: lo que escribe en `reservations` DEBE ir en una
    transacción propia y con `lock_timeout`, y cada cliente del cron y cada `refresh` DEBEN tener un
    tiempo máximo. IF un dueño no tiene conexión usable o el permiso se perdió THEN la referencia
    de su evento DEBE soltarse para escribir el nuevo: lo de uno NO DEBE tocar a los demás. IF el
    fallo al borrar es otro THEN DEBE esperarse, para no duplicar, y no más de una hora en una reserva
    viva. Lo que quede atrás DEBE reconocerse por su marca y quitarse (13.6).

### Requisito 13 — Lo que cambia en Google vuelve bien (enmienda del 2026-11-04)

#### Criterios de aceptación

1. WHEN aparece en el calendario de un profesional un evento que no es nuestro THEN
   DEBE contar como ocupado para sus huecos y, si pisa una reserva viva, marcarla como
   choque.
2. IF nuestro «Ocupado» de una reserva viva ya no está en su calendario THEN la pasada
   siguiente DEBE borrarlo por si sigue allí y volver a escribirlo: si es el listado el que
   no lo trae, NO DEBEN acumularse eventos.
3. IF nuestro «Ocupado» está a otra hora que su reserva THEN la pasada siguiente DEBE
   borrarlo y escribirlo a la hora de la reserva. La reserva NO DEBE moverse.
4. Un evento rechazado por el profesional, un cumpleaños (`birthday`) o un lugar de trabajo
   (`workingLocation`) NO DEBEN bloquear, ni uno con hora marcado como disponible. Uno de todo el
   día DEBE bloquear aunque Google lo marque como disponible: nace así, y es la forma de cerrar un día.
5. Un evento recién escrito en esta pasada NO DEBE volver a escribirse aunque la lectura
   de esa misma pasada aún no lo traiga.
6. Lo nuestro DEBE reconocerse por el id que guarda la reserva y, si se perdió, por su marca: la
   descripción `auphere:reserva:<id>` de un evento que organiza la propia cuenta y de una reserva que
   existe en este cliente. Nunca DEBE contar como ocupado. IF es la cita de esa persona, a esa hora, y
   aún no tiene evento THEN DEBE adoptarse; si no, DEBE borrarse. Una marca de otro cliente, de una
   reserva que no existe o en una invitación de fuera DEBE leerse como ocupado normal.

### Requisito 14 — Los datos que dejan reservar (enmienda del 2026-11-04)

**Historia de usuario:** Como negocio, quiero saber qué en mis datos impide reservar,
para no descubrirlo por un cliente al que el agente no supo atender.

#### Criterios de aceptación

1. IF un servicio reservable no lo hace nadie en activo THEN `reservas.services` NO DEBE
   ofrecerlo como reservable sin decirlo, `reservas.find_slots` y `reservas.create`
   DEBEN responder `no_staff`, y Ajustes DEBE avisarlo en ese servicio.
2. IF un servicio no cabe en ningún tramo del horario de quienes lo hacen THEN Ajustes
   DEBE avisarlo en ese servicio y crear una reserva DEBE responder `slot_taken`.
3. Un profesional sin horario propio DEBE usar el del negocio. Uno con una semana
   propia sin ningún tramo NO DEBE tener huecos, y Ajustes DEBE avisarlo.
4. Un servicio con una lista de profesionales DEBE ofrecer huecos solo de esa lista;
   pedir otro profesional DEBE dar 404 en la consola y `not_offered` en el agente.
5. Un profesional archivado NO DEBE ofrecer huecos ni contar en un servicio, ni aparecer en su
   lista, ni en Reservas ni en la ficha del negocio, y ninguna de las dos DEBE aceptarlo: archivarlo
   DEBE quitarlo de ella, y un servicio DEBE poder seguir editándose.
6. Una fecha especial del negocio DEBE mandar sobre el horario de cada profesional:
   un festivo cerrado no da huecos a nadie.

### Entidades clave

Todas por cliente (`tenant_id`, RLS FORCE); toda referencia entre ellas, clave
compuesta `(tenant_id, x_id)`.

- **Ajustes de reservas**: modo, tipo, interruptores y números. Una fila por
  cliente.
- **Persona del equipo** (Servicios): nombre, correo, horario, archivada.
- **Servicio** (Servicios): nombre, duración, precio, quién lo hace.
- **Reserva**: cuándo, cuánto dura, para cuántos, con quién, qué servicio, de
  quién (contacto), estado, origen, canal, quién la apuntó, nota, versión.
- **Evento de reserva**: el historial, sin texto libre (tipo, actor, datos).
- **Bloqueo** (Aforo): de cuándo a cuándo y una etiqueta.
- **Entrada de la lista de espera** y **oferta** con sus candidatos.
- **Calendario de la persona** (P3): su conexión con el proveedor, qué calendario
  de esa cuenta es suyo y su sincronización.

## Criterios de éxito *(obligatorio)*

- **CE-001**: ninguna prueba de concurrencia consigue dos reservas vivas que se
  pisen (Servicios) ni una hora por encima del aforo (Aforo) por el agente o la
  API.
- **CE-002**: el barrido de aislamiento da 404 idéntico para toda reserva,
  persona, servicio, bloqueo, entrada y oferta de otro cliente del mismo partner.
- **CE-003**: el agente nunca lista, mueve ni cancela una reserva de otra persona
  del mismo negocio.
- **CE-004**: las pantallas de los dos modos pasan axe y no desbordan a 360 y
  1920 px, en claro y oscuro, en español e inglés.
- **CE-005**: cada proceso automático actúa una sola vez por reserva y tipo, con
  el reloj adelantado.

## Fuera de alcance

- Señas, depósitos, recargos de cancelación — Reservas no mueve dinero.
- Outlook, Calendly como «otro sistema manda», Cal.com, AgendaPro por API,
  Cronofy/Nylas, Reserve with Google — decisión del owner.
- Excepciones por persona sin calendario conectado (un día libre, vacaciones) — anotado en
  la enmienda del 2026-11-04, para otra entrega.
- Mesas — descartadas por el diseño.
- Papeles dentro del cliente — spec 030.
- La app — spec 044 (consume `contracts/`).
- Migrar las `appointments` existentes — siguen con su flujo.

## Supuestos

- Las plantillas de `contracts/plantillas.md` las aprueba Meta en el número de
  cada cliente (las crea el partner o Auphere); sin ellas, solo sale lo que cabe
  en la ventana de 24 h.
- El negocio tiene un solo horario semanal; las excepciones de un día se hacen
  con bloqueos (Aforo) o archivando huecos a mano (Servicios).
