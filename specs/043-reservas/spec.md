# Especificación: Reservas — el agente reserva y el negocio lo ve, en dos modos

**Rama**: `043-reservas` · **Creada**: 2026-10-22 · **Estado**: Aclarada (decisiones del 2026-10-22 en §Clarifications)

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
- **Calendario de la persona** (P3): qué calendario de Google es suyo y su
  sincronización.

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
