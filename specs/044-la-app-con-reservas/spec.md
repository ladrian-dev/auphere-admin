# Especificación: La app con Reservas

**Rama**: `044-la-app-con-reservas` · **Creada**: 2026-10-22 · **Estado**: Borrador

**Entrada**: descripción del usuario: "044 «La app con Reservas» en apps/mobile
(Auphere Customers, Expo SDK 58), encima de la spec 042. Alcance: las 10
propuestas del lienzo móvil de Claude Design (KB
research/2026-10-22-reservas-y-consola-customers) con el contenido nuevo del
diseño y las formas de la 042; Reservas en los dos modos (Servicios y Aforo)
según las reglas de la nota, con el botón flotante «+» de «Llegada sin reserva»
en Aforo/Día de hoy; avisos agrupados por módulo y silencio fuera del horario
del negocio; estados honestos (carga, vacío, error, parcial, sin red), modo
oscuro y texto grande. Sin «Comprar saldo» (saldo de solo lectura). Solo
WhatsApp por Meta. Datos de ejemplo chilenos. La API la construye la spec
043/045 (sesión consolas-web); la app construye contra su contrato. Builds
1.1.0: iOS staging a TestFlight, Android por Play pista interna + Firebase."

## Encabezado Auphere *(obligatorio)*

| Campo | Valor |
|---|---|
| **Superficie de confianza** | `0`, la API de la consola (`/console/lite/*`), la misma que ya abre la 031. La app no tiene reglas de negocio propias: lee y escribe por las rutas que añaden las specs 043 (Reservas) y 045 (mejoras), con el mismo `ClientPrincipal` que la web. No se abre ninguna superficie nueva desde el teléfono. |
| **Garantías de aislamiento tocadas** | Ninguna **en la app**. La agenda de todo el negocio y los avisos de Reservas son superficie nueva **de la API**, y su barrido en `tests/isolation/` es de la spec 043. La app solo sigue sus reglas de siempre: lo de los clientes finales vive en memoria, nunca en disco (031), y el aviso muestra lo que la API envía. |
| **Nota de KB que la justifica** | `[[research/2026-10-22-reservas-y-consola-customers]]` (decisiones del owner, reglas de producto, reparto y orden de fusión) · `[[research/2026-10-19-consola-lite-movil]]` · `[[decisions/ADR-042-la-consola-lite-en-el-telefono]]` |
| **Qué se mide** | Nada. Ni modelo, ni máquina, ni herramienta de pago. Lo que gaste el agente al confirmar o avisar por WhatsApp lo mide la 043. |

## Origen

Luis lo pidió el 2026-10-22: crear el módulo de Reservas diseñado en Claude
Design y aplicar las mejoras de las vistas, con una versión de iOS y otra de
Android para seguir probando al final de la jornada. El trabajo va en dos
frentes: la API y las consolas web (specs 043 y 045, sesión `consolas-web`) y
esta app (spec 044).

El diseño está en la KB
(`research/2026-10-22-reservas-y-consola-customers/diseno/`): `Customers App`
(los dos teléfonos, los dos modos) y el lienzo con **diez propuestas**. Su
lectura contra el código está en `lecturas/app-movil.md` y el dominio de
Reservas en `lecturas/reservas-dominio.md`.

**El diseño parte de la app anterior a la 042** y reintroduce cosas que la 042
quitó (tarjetas de cifras, la insignia junto a la atención, Ajustes apilado, la
búsqueda dentro del contenido). Regla de esta spec, acordada en la KB: **el
contenido nuevo del diseño, con las formas de la 042.** Lo que el diseño
cambia de la 042 y se acepta queda escrito aquí como enmienda; lo que no, en
«Decisiones».

**Decisiones del owner que esta spec cumple:**

1. Saldo de solo lectura: no hay «Comprar saldo» en ninguna pantalla.
2. Solo WhatsApp por Meta: ni Instagram, ni Messenger, ni «Reserve with
   Google» como canal u origen.
3. Datos de ejemplo del piloto chileno (CLP, +56).
4. Android por Play (pista interna) y Firebase; Luis crea la app y el proyecto.

## Clarifications

### Session 2026-10-22

Luis delegó estas decisiones («decide tú con criterio y déjalo escrito»). Cada
una lleva su razón.

- Q: ¿Se pueden cambiar desde el teléfono los ajustes de Reservas (aforo, tiempo
  de mesa, lista de espera, antelación, confirmación, bloqueos) o solo verse? →
  A: Lo mismo que la consola customers, por las mismas rutas: lo que el contrato
  de la 043 deje cambiar a la persona, se cambia; lo que no, se ve en solo
  lectura. La app no añade permisos ni reglas (es la superficie `0` de siempre).
- Q: ¿Cancelar una reserva pide confirmación y avisa siempre al cliente final? →
  A: Sí a las dos. Cancelar afecta a un tercero y le llega un WhatsApp, así que
  hay una alerta que lo dice («Le avisamos por WhatsApp») y solo cancela al
  confirmar. «Llegó», «No vino» y «Marcar confirmada» no la piden: se deshacen
  desde el aviso breve.
- Q: ¿Los datos de ejemplo de Reservas pueden ir en un build interno (preview o
  staging, TestFlight) para enseñarlo antes de que la API llegue a staging? →
  A: No. Solo en el build de desarrollo y si se pide al compilar, con la marca
  «Datos de ejemplo» a la vista. Un build que alguien prueba como real no enseña
  datos que no existen (constitución §V); Reservas aparece en TestFlight cuando
  la 043 esté en staging.
- Q: ¿Cómo se distinguen los dos «+» de Reservas en Aforo («Nueva reserva» y
  «Llegada sin reserva»)? → A: El «+» flotante es solo «Llegada sin reserva»
  (regla de producto del diseño). «Nueva reserva» es, en iOS, un botón de barra
  con un calendario con «+»; en Android, el botón flotante extendido con su
  texto, y en Aforo·Día·hoy el «+» pequeño de la llegada va apilado encima, como
  en el diseño. Los dos llevan nombre accesible distinto.
- Q: ¿Qué acciones confirman con un aviso breve (toast)? → A: Las que no dejan
  su resultado a la vista: las de Reservas, lista de espera, bloqueos y «Nota
  guardada». Tomar el control y devolver cambian el pie a la vista: ahí no hay
  aviso breve, sigue la vibración de la 042 y el lector de pantalla lo anuncia.
  El aviso breve se lee con el lector de pantalla y dura lo bastante para tocar
  «Deshacer».

## Escenarios de usuario y pruebas *(obligatorio)*

### Historia 1 — El día de hoy en Reservas, en los dos modos (Prioridad: P1)

Una persona del negocio abre la pestaña Reservas y ve el día de hoy. En una
barbería (modo Servicios) ve las citas por hora, con quién y qué servicio, y
cuáles faltan por confirmar. En un restaurante (modo Aforo) ve cuánta gente hay
dentro, quién llega en la próxima hora y marca «Llegó» o «No vino».

**Por qué esta prioridad**: es lo que se mira cada mañana y en la puerta; sin
esto el módulo no existe en el teléfono.

**Prueba independiente**: con un cliente en Servicios y otro en Aforo, se abre
Reservas en cada uno y se recorre el día; en Aforo se marca una llegada.

**Escenarios de aceptación**:

1. **Dado** un cliente con Reservas en modo Servicios, **cuando** la persona
   abre la pestaña, **entonces** ve el día de hoy en lista, con la línea
   «Ahora», las pasadas atenuadas y cada reserva con su hora, duración,
   nombre, «servicio · profesional» y estado.
2. **Dado** ese cliente, **cuando** cambia a «Cuadrícula», **entonces** ve una
   columna por profesional con los bloques a la altura de su duración.
3. **Dado** un cliente en modo Aforo, **cuando** abre la pestaña, **entonces**
   ve «Dentro ahora X de N», «Próxima hora» y «Sin confirmar», la tira de
   franjas con lo que hay dentro, y las reservas agrupadas por hora.
4. **Dado** una reserva de hoy en Aforo que llega en menos de media hora,
   **cuando** toca «Llegó», **entonces** la reserva pasa a «Llegó a las HH:MM»
   y la cuenta de «Dentro ahora» sube.
5. **Dado** un día cerrado en el horario del negocio, **cuando** lo elige,
   **entonces** ve «Cerrado este día. Viene del horario del negocio.» y
   ninguna acción de reservar.

---

### Historia 2 — Una reserva: verla, confirmarla, cancelarla (Prioridad: P1)

Toca una reserva y se abre su hoja: cuándo, con quién o cuántos, por dónde
llegó, su estado y su historial. Puede marcarla confirmada, marcar que llegó o
que no vino, o cancelarla.

**Por qué esta prioridad**: el agente reserva solo; la persona supervisa y
corrige. Sin la hoja no hay forma de corregir.

**Prueba independiente**: se abre una reserva sin confirmar, se marca
confirmada; se abre otra futura y se cancela.

**Escenarios de aceptación**:

1. **Dado** una reserva sin confirmar, **cuando** toca «Marcar confirmada»,
   **entonces** el estado cambia y un aviso breve lo confirma.
2. **Dado** una reserva futura y abierta, **cuando** toca «Cancelar»,
   **entonces** la app pide confirmación diciendo que el cliente recibirá un
   WhatsApp, y solo al confirmar la cancela.
3. **Dado** que marcó «No vino» por error hoy, **cuando** toca «Deshacer» en el
   aviso breve, **entonces** la reserva vuelve a «Confirmada».
4. **Dado** que la API rechaza la acción (ya cambió, hueco ocupado),
   **cuando** ocurre, **entonces** la app lo dice en una frase y relee la
   reserva, sin dejar el estado anterior pintado como si nada.

---

### Historia 3 — Llegada sin reserva en Aforo (Prioridad: P1)

En la puerta de un restaurante llega un grupo sin reservar. En Reservas, Día,
hoy, la persona toca el botón flotante «+», elige cuántos son y registra la
llegada; si no caben, los apunta en la lista de espera.

**Por qué esta prioridad**: es la regla de producto del diseño para el
teléfono, y es la acción más frecuente en la puerta.

**Prueba independiente**: en Aforo, hoy, «+» → 4 comensales → «Registrar
llegada»; la cuenta de dentro sube en 4.

**Escenarios de aceptación**:

1. **Dado** Aforo, vista Día y el día de hoy, **cuando** abre la pestaña,
   **entonces** ve el botón flotante «+» de «Llegada sin reserva»; en otro día,
   en Semana o en Mes, no lo ve.
2. **Dado** la hoja abierta, **cuando** cambia el número de comensales,
   **entonces** la hoja dice en vivo si caben («Cabe. Después quedarán N libres
   hasta las HH:MM.»), si no («No cabe ahora. Puedes apuntarlo en la lista de
   espera.») o si no hay servicio a esa hora.
3. **Dado** que caben, **cuando** toca «Registrar llegada», **entonces** la
   llegada queda como «Sin reserva · Llegó» en la franja en curso y un aviso
   breve lo confirma.

---

### Historia 4 — Nueva reserva desde el teléfono (Prioridad: P2)

Alguien llama por teléfono. La persona abre «Nueva reserva»: en Servicios elige
servicio, profesional (o cualquiera), día y uno de los huecos reales; en Aforo,
cuántos y una hora con lo que queda libre. Escribe el nombre y, si lo tiene, el
teléfono; guarda.

**Escenarios de aceptación**:

1. **Dado** Servicios, **cuando** elige servicio, «Cualquiera» y mañana,
   **entonces** ve solo los huecos reales, cada uno con el profesional que lo
   haría.
2. **Dado** Aforo, **cuando** elige 6 comensales, **entonces** cada hora dice
   «quedan N» o «completo», y una hora completa no se puede elegir.
3. **Dado** un nombre y una hora, **cuando** guarda con teléfono, **entonces**
   el aviso breve dice que le llega la confirmación por WhatsApp.
4. **Dado** que el hueco se ocupó mientras elegía, **cuando** guarda,
   **entonces** la app lo dice, relee los huecos y no pierde lo escrito.

---

### Historia 5 — Lo urgente de todos los módulos, en Inicio (Prioridad: P2)

Inicio dice lo que necesita a una persona en toda la app: conversaciones que
esperan, reservas de hoy sin confirmar y el saldo si se agota. Cada dato lleva a
su pantalla, y una tarjeta resume «Hoy en Reservas».

**Escenarios de aceptación**:

1. **Dado** tres reservas de hoy sin confirmar, **cuando** abre Inicio,
   **entonces** «Necesita tu atención» dice «3 reservas de hoy sin confirmar.
   El agente ya les escribió.» con «Ver reservas», que lleva a Reservas, Día,
   hoy.
2. **Dado** un cliente con Reservas, **cuando** abre Inicio, **entonces** ve
   «Hoy en Reservas» con el resumen de su modo y las tres siguientes.
3. **Dado** Inicio, **cuando** toca el bloque de conversaciones o el saldo,
   **entonces** llega a la Bandeja o a Consumo.

---

### Historia 6 — Atender: quién espera, por qué y desde cuándo (Prioridad: P2)

En la Bandeja, las conversaciones que esperan a una persona van fijas arriba con
el motivo del agente y cuánto llevan esperando. En la conversación, la tarjeta
dice desde cuándo y quién lo pidió; con el control tomado, «Devolver» queda a un
toque y las respuestas guardadas a la vista.

**Escenarios de aceptación**:

1. **Dado** dos conversaciones esperando, **cuando** abre la Bandeja con
   «Todas» y sin buscar, **entonces** ve «Esperan a una persona · 2» arriba, con
   el motivo como vista previa y «hace N min».
2. **Dado** una conversación en espera, **cuando** la abre, **entonces** la
   tarjeta dice «Espera hace N min · lo pidió el agente de X» antes de «Tomar el
   control».
3. **Dado** que tomó el control y el borrador está vacío, **cuando** mira el
   pie, **entonces** ve «Atiendes tú · el agente de X está en pausa», el botón
   «Devolver» y sus respuestas guardadas como chips.

---

### Historia 7 — El contacto con su próxima reserva (Prioridad: P3)

En la ficha de un contacto se ve su próxima reserva y se llega a ella sin
cambiar de pestaña a mano.

**Escenarios de aceptación**:

1. **Dado** un contacto con una reserva mañana a las 17:00, **cuando** abre su
   ficha, **entonces** ve «Próxima reserva · Mañana a las 17:00 · Corte con
   Marcos», y al tocarla llega a Reservas en ese día con la reserva abierta.

---

### Historia 8 — Consumo: primero la respuesta (Prioridad: P3)

Consumo empieza por la respuesta a «¿hasta cuándo me alcanza?»: «Te alcanza
hasta el sábado 17», y dice a quién pedir más.

**Escenarios de aceptación**:

1. **Dado** saldo y gasto en los últimos 7 días, **cuando** abre Consumo,
   **entonces** lo primero es «Te alcanza hasta el <día> <n>» y «Para recargar,
   habla con <quien gestiona el saldo>».
2. **Dado** saldo sin gasto, sin saldo asignado o agotado, **cuando** abre
   Consumo, **entonces** la frase dice cada caso, sin fecha inventada.

---

### Historia 9 — Lista de espera y ajustes en el teléfono (Prioridad: P3)

Desde el menú de Reservas la persona ve la lista de espera, ofrece un hueco o
quita a alguien, y revisa los ajustes: aforo, tiempo de mesa, máximo por
reserva, plazas guardadas, lista de espera, antelación, confirmación y
bloqueos.

**Escenarios de aceptación**:

1. **Dado** alguien en la lista que cabe, **cuando** toca «Ofrecer ahora»,
   **entonces** la tarjeta pasa a «Ofrecida · N min para responder» con su
   cuenta atrás.
2. **Dado** Aforo, **cuando** bloquea el turno de cena de mañana con un
   motivo, **entonces** el bloqueo aparece en la lista y la franja sale rayada.

---

### Historia 10 — Avisos por módulo y fuera de horario (Prioridad: P3)

En Ajustes los avisos se agrupan por Bandeja, Reservas y Saldo; hay tres de
Reservas y un interruptor «Silenciar fuera del horario del negocio». Lo urgente
(alguien espera a una persona) sigue llegando.

**Escenarios de aceptación**:

1. **Dado** un cliente con Reservas, **cuando** abre Ajustes, **entonces** ve
   los avisos en tres grupos, con «Alguien de la lista de espera aceptó»
   apagado de partida.
2. **Dado** el silencio encendido, **cuando** mira su pista, **entonces** lee
   el horario del negocio y que lo urgente sigue llegando.
3. **Dado** un aviso de una reserva, **cuando** lo toca, **entonces** la app
   abre esa reserva.

---

### Casos límite

- **Sin el módulo Reservas**: no hay pestaña, ni tarjeta en Inicio, ni fila en
  la ficha del contacto, ni avisos de Reservas. Nada apagado ni explicado
  (constitución §V).
- **El admin cambia el modo** mientras la persona mira: al volver a leer la
  configuración, la pestaña pasa a la vista del otro modo, sin mezclar datos.
- **Sin red**: se ve lo último leído, marcado como no actualizado, y no se
  ofrece ninguna acción que escriba (031).
- **Parcial**: si una parte no llega (la ocupación sí, la lista de espera no),
  se pinta lo que llegó y se dice qué falta.
- **La hora del teléfono no es la del negocio**: las horas de las reservas y
  «ahora» son las del negocio.
- **Un grupo por encima del máximo por reserva** en Aforo: la persona puede
  reservarlo; la hoja avisa de que el agente no acepta grupos así.
- **Reservas a la vez**: dos personas toman el mismo hueco; la segunda recibe
  «Ese hueco ya no está libre» y los huecos releídos.
- **Texto al máximo**: la cuadrícula de Servicios no se vuelve ilegible; la
  lista sigue siendo la vista que lo cuenta todo.
- **Nombre largo** (un nombre de 32 caracteres o más): se corta con elipsis en
  las filas y se lee entero en la hoja.
- **Mientras la API de Reservas no exista**: en desarrollo, la app puede
  enseñar datos de ejemplo, siempre con la marca «Datos de ejemplo»; nunca en
  un build interno ni de tienda. En TestFlight y Play, sin la API en staging, no
  hay pestaña Reservas.
- **Un ajuste que la API no deja cambiar**: se ve en solo lectura, sin un
  control apagado.

## Requisitos *(obligatorio)*

### Requisito 1 — La pestaña Reservas y su modo

**Historia de usuario:** Como persona de un negocio con Reservas, quiero una
pestaña Reservas que hable el idioma de mi modo, para ver solo lo que me sirve.

#### Criterios de aceptación

1. WHERE el cliente tiene el módulo `reservas` en su navegación EL sistema DEBE
   enseñar la pestaña «Reservas» en el orden que dé la API, con el icono de
   calendario de cada plataforma.
2. IF el cliente no tiene el módulo THEN el sistema NO DEBE enseñar la pestaña,
   la tarjeta de Inicio, la fila del contacto ni los avisos de Reservas.
3. El sistema DEBE enseñar solo la vista del modo que diga la API (Servicios o
   Aforo), y NO DEBE ofrecer cambiar de modo desde el teléfono.
4. WHEN el modo cambia en la API THEN el sistema DEBE pasar a la vista del modo
   nuevo en la siguiente lectura, sin mezclar datos del anterior.
5. El sistema DEBE pintar las horas de las reservas y «ahora» en la zona horaria
   del negocio que dé la API.

### Requisito 2 — Reservas · Día

**Historia de usuario:** Como persona del negocio, quiero ver un día de un
vistazo, para saber quién viene y qué falta.

#### Criterios de aceptación

1. WHEN abre la pestaña THEN el sistema DEBE enseñar el periodo Día y el día de
   hoy.
2. El sistema DEBE ofrecer el periodo Día, Semana o Mes en un control
   segmentado, y una tira de días desplazable con el día elegido marcado, hoy
   señalado y los días cerrados atenuados.
3. WHILE el día elegido no es hoy el sistema DEBE ofrecer «Hoy» para volver.
4. WHERE el modo es Servicios EL sistema DEBE ofrecer «Lista» o «Cuadrícula»
   en el periodo Día, y un filtro por profesional («Todo el equipo» y cada
   persona).
5. WHERE el modo es Servicios y la vista es Lista EL sistema DEBE enseñar el
   resumen «N reservas · N sin confirmar» y una fila por reserva con hora,
   duración, nombre, «servicio · profesional» y estado; la línea «Ahora» entre
   filas si es hoy, y las pasadas atenuadas.
6. WHERE el modo es Servicios y la vista es Cuadrícula EL sistema DEBE enseñar
   una columna por profesional, las horas del horario, cada reserva con la
   altura de su duración y la línea de «ahora»; y cada bloque DEBE leerse con el
   lector de pantalla como la fila de la lista.
7. WHERE el modo es Aforo EL sistema DEBE enseñar tres cifras (hoy: «Dentro
   ahora X de N», «Próxima hora» y «Sin confirmar»; otro día: «Reservados»,
   «Reservas» y «Sin confirmar»), la tira de franjas con las personas dentro y
   su nivel de ocupación (las bloqueadas rayadas), y las reservas agrupadas por
   hora con «N reservas · N comensales» y «X de N».
8. WHEN toca una franja de la tira THEN el sistema DEBE filtrar a esa hora y
   ofrecer «Ver todo el día».
9. WHERE el modo es Aforo EL sistema DEBE ofrecer en cada fila «Llegó» si es
   hoy, la reserva está abierta y falta como mucho media hora, y «No vino» si ya
   pasó su hora; y DEBE marcar «Llega tarde · N min» pasados 15 minutos.
10. IF el día está cerrado THEN el sistema DEBE decir «Cerrado este día. Viene
    del horario del negocio.»; IF no hay reservas THEN «No hay reservas este
    día.».
11. WHEN toca una reserva THEN el sistema DEBE abrir su hoja (Requisito 4).

### Requisito 3 — Reservas · Semana y Mes

#### Criterios de aceptación

1. WHERE el modo es Servicios y el periodo es Semana EL sistema DEBE enseñar una
   tarjeta por día con «N reservas» o «Cerrado» y sus filas.
2. WHERE el modo es Aforo y el periodo es Semana EL sistema DEBE enseñar un mapa
   de calor de días por franjas con las personas dentro, en cinco niveles, las
   bloqueadas rayadas, y su leyenda; y tocar una celda DEBE llevar a ese día con
   la franja filtrada.
3. WHEN el periodo es Mes THEN el sistema DEBE enseñar la rejilla del mes,
   semana empezando en lunes, con la ocupación de cada día en barra y en «%» o
   «Cerrado»; y tocar un día DEBE llevar a ese día.
4. El sistema DEBE permitir pasar a la semana y al mes anterior y siguiente.

### Requisito 4 — La hoja de la reserva

#### Criterios de aceptación

1. WHEN abre una reserva THEN el sistema DEBE enseñarla en una hoja con:
   nombre; en Servicios «servicio · duración · precio» y «Con <profesional>»;
   en Aforo los comensales y el tiempo máximo de mesa; cuándo; el canal; el
   estado; el origen («La reservó el agente por WhatsApp», «La apuntó <persona>»,
   «Llegó sin reserva», «Desde la lista de espera») y el historial.
2. El sistema DEBE ofrecer solo las acciones que valen: «Llegó» y «No vino» hoy
   (y «Llegó» solo en Aforo); «Marcar confirmada» si está sin confirmar;
   «Cancelar» si está abierta y es futura.
3. WHEN toca «Cancelar» THEN el sistema DEBE pedir confirmación diciendo que el
   cliente recibirá un WhatsApp, y NO DEBE cancelar sin ella. «Llegó», «No
   vino» y «Marcar confirmada» NO DEBEN pedir confirmación.
4. WHEN una acción sale bien THEN el sistema DEBE confirmarlo con un aviso
   breve; tras «Llegó» o «No vino» el aviso DEBE ofrecer «Deshacer» mientras
   siga siendo hoy.
5. IF la API rechaza la acción THEN el sistema DEBE decirlo en una frase y
   releer la reserva.
6. WHILE no hay red el sistema NO DEBE ofrecer ninguna acción.

### Requisito 5 — Nueva reserva

#### Criterios de aceptación

1. El sistema DEBE ofrecer «Nueva reserva»: en iOS como botón de la barra con
   un icono de calendario con «+»; en Android como botón flotante extendido
   «Nueva reserva».
2. WHERE el modo es Servicios EL sistema DEBE pedir servicio, «Con»
   (Cualquiera o cada profesional), día (chips de los próximos días hábiles) y
   hora entre los huecos reales que dé la API, cada uno con el profesional que
   la haría si eligió «Cualquiera».
3. WHERE el modo es Aforo EL sistema DEBE pedir comensales (− N +), día y hora
   entre las franjas, cada una con «quedan N» o «completo»; una completa NO DEBE
   poder elegirse.
4. IF los comensales superan el máximo por reserva THEN el sistema DEBE avisar
   de que el agente no acepta grupos así, y DEBE dejar reservarlo.
5. El sistema DEBE pedir nombre (obligatorio) y teléfono (opcional, prefijo
   +56 por defecto), enseñar el resumen («Mañana a las 17:00 · Corte con
   Marcos») y activar «Guardar reserva» solo con nombre y hora.
6. WHEN guarda THEN el sistema DEBE enviar la reserva una sola vez aunque se
   repita el toque o se reintente, y confirmar con un aviso breve que dice si le
   llega la confirmación por WhatsApp.
7. IF el hueco ya no está libre THEN el sistema DEBE decirlo, releer los huecos
   y conservar lo escrito.
8. IF no quedan huecos ese día THEN el sistema DEBE decir «No quedan huecos ese
   día. Prueba otro día o con otra persona.».

### Requisito 6 — Llegada sin reserva (Aforo)

#### Criterios de aceptación

1. WHERE el modo es Aforo, el periodo es Día y el día es hoy EL sistema DEBE
   enseñar un botón flotante con «+» que abre la hoja «Llegada sin reserva»; en
   cualquier otro caso NO DEBE enseñarlo. La acción DEBE estar también en el
   menú de Reservas.
2. La hoja DEBE pedir comensales (− N +) y un nombre opcional, y decir en vivo
   si caben con el aforo completo (las plazas guardadas sí cuentan), si no
   caben, o si no hay servicio ahora.
3. WHEN caben y toca «Registrar llegada» THEN el sistema DEBE registrarla en la
   franja en curso y confirmarlo con un aviso breve.
4. IF no caben THEN el sistema DEBE ofrecer «Apuntar en lista de espera» en su
   lugar.

### Requisito 7 — Lista de espera

#### Criterios de aceptación

1. El sistema DEBE ofrecer «Lista de espera» desde el menú de Reservas, como
   pantalla apilada, con la explicación de su modo arriba.
2. El sistema DEBE enseñar una tarjeta por persona con lo que pide, su estado
   («Ofrecida · N min para responder» con la cuenta atrás, «Aceptó ·
   reservada», «Cabe», «No cabe», «Esperando hueco») y quién la apuntó.
3. El sistema DEBE ofrecer «Ofrecer ahora» si cabe y «Quitar».
4. IF la lista está vacía THEN el sistema DEBE decir «Nadie en la lista
   todavía.».

### Requisito 8 — Ajustes de reservas y bloqueos

#### Criterios de aceptación

1. El sistema DEBE ofrecer «Ajustes de reservas» desde el menú, como pantalla
   apilada, que diga el modo y «Lo define Auphere desde el admin.».
2. WHERE el modo es Aforo EL sistema DEBE enseñar aforo máximo, tiempo máximo de
   mesa, máximo por reserva y plazas guardadas para llegadas sin reserva.
3. El sistema DEBE enseñar el horario del negocio con «Viene del perfil del
   negocio. Se edita en la web.».
4. WHERE el modo es Servicios EL sistema DEBE enseñar el equipo con el estado de
   su calendario (solo Google Calendar) y los servicios con duración y precio,
   en solo lectura.
5. El sistema DEBE enseñar la lista de espera (encendida o no) y la antelación
   mínima para avisar, y la confirmación por WhatsApp.
6. WHERE la API permite cambiar un ajuste desde la consola customers EL sistema
   DEBE dejar cambiarlo desde el teléfono; IF no lo permite THEN DEBE enseñarlo
   en solo lectura, sin controles apagados.
7. WHERE el modo es Aforo EL sistema DEBE enseñar los bloqueos con «Quitar» y
   ofrecer «Bloquear horas» (hoja: día, turno y motivo obligatorio), avisando de
   que las reservas que ya hay se mantienen.

### Requisito 9 — Inicio

#### Criterios de aceptación

1. WHERE el cliente tiene Reservas y hay reservas de hoy sin confirmar EL
   sistema DEBE sumar a «Necesita tu atención» «N reservas de hoy sin confirmar.
   El agente ya les escribió.» con «Ver reservas», que lleva a Reservas, Día,
   hoy.
2. El sistema DEBE mantener en la atención el saldo bajo o agotado (030 R4.5),
   y NO DEBE poner una insignia con número junto al título (042 H13).
3. El sistema DEBE llevar del bloque de conversaciones a la Bandeja y del saldo
   a Consumo, con la fila con chevrón de la 042.
4. WHERE el cliente tiene Reservas EL sistema DEBE enseñar «Hoy en Reservas»:
   en Servicios «N reservas hoy», «Próxima a las HH:MM · N sin confirmar» y las
   tres siguientes; en Aforo «X de N dentro ahora», «Llegan N comensales en la
   próxima hora · N en lista de espera» y las tres siguientes; y «Ver
   reservas».
5. El sistema DEBE seguir diciendo una sola vez cuántas conversaciones esperan
   (042 R5.1).

### Requisito 10 — Bandeja

#### Criterios de aceptación

1. WHILE el filtro es «Todas» y no hay búsqueda el sistema DEBE enseñar arriba el
   grupo «Esperan a una persona · N», con el motivo del agente como vista previa
   y «hace N min».
2. IF la API no da desde cuándo espera THEN el sistema DEBE enseñar el motivo
   sin el tiempo, y NO DEBE inventarlo.
3. El sistema DEBE enseñar al pie de la lista «Aquí solo están las
   conversaciones que atiende o atendió tu agente. El resto de chats de tu
   WhatsApp no aparece.».
4. WHERE la API dice quién escribió el último mensaje EL sistema DEBE ponerle
   «Tú:» o «Agente:» delante de la vista previa.
5. El sistema DEBE mantener la búsqueda nativa de la cabecera y el filtro por
   agente cuando hay más de uno (042 D6).

### Requisito 11 — Conversación

#### Criterios de aceptación

1. WHILE la conversación espera a una persona el sistema DEBE decir en la
   tarjeta «Espera hace N min · lo pidió el agente de X» antes de «Tomar el
   control».
2. El sistema DEBE decir bajo el nombre el estado: «Espera a una persona»,
   «Atiendes tú», «Resuelta» o «Atiende el agente de X».
3. WHILE atiende el agente el sistema DEBE decir «Responde el agente de X. Si
   entras, deja de responder.» con «Tomar el control».
4. WHILE la persona tiene el control el sistema DEBE enseñar «Atiendes tú · el
   agente de X está en pausa» y «Devolver» a un toque en el pie, además del
   menú.
5. WHILE tiene el control y el borrador está vacío el sistema DEBE enseñar sus
   respuestas guardadas como chips que rellenan el borrador, y DEBE mantener la
   hoja con todas.

### Requisito 12 — Contacto

#### Criterios de aceptación

1. WHERE el cliente tiene Reservas y el contacto tiene una próxima reserva EL
   sistema DEBE enseñar «Próxima reserva» con el día, la hora y «servicio con
   profesional» o los comensales.
2. WHEN la toca THEN el sistema DEBE llevar a Reservas en ese día con la hoja de
   esa reserva abierta.

### Requisito 13 — Consumo

#### Criterios de aceptación

1. El sistema DEBE empezar Consumo por «Saldo» y, grande, «Te alcanza hasta el
   <día de la semana> <número>», al ritmo de los últimos 7 días, con «Para
   recargar, habla con <quien gestiona el saldo>».
2. IF no hay gasto, no hay saldo asignado o el saldo está agotado THEN el
   sistema DEBE decir cada caso con su frase, y NO DEBE enseñar una fecha.
3. El sistema DEBE titular la gráfica «Gasto de los últimos N días» con el total.
4. El sistema NO DEBE ofrecer comprar ni recargar saldo.

### Requisito 14 — Avisos

#### Criterios de aceptación

1. El sistema DEBE agrupar los avisos de Ajustes en Bandeja, Reservas y Saldo, y
   enseñar Reservas solo con el módulo.
2. WHERE el cliente tiene Reservas EL sistema DEBE ofrecer tres avisos: «Reserva
   nueva o cambiada por el agente» (una vez por reserva), «Cancelaciones de hoy»
   y «Alguien de la lista de espera aceptó», este apagado de partida.
3. WHERE la API trae el silencio fuera de horario EL sistema DEBE ofrecer
   «Silenciar fuera del horario del negocio», encendido de partida, con el
   horario del negocio en su pista y «Lo urgente sigue llegando»; sin él, NO
   DEBE enseñar el interruptor.
4. La pantalla del permiso DEBE enseñar un aviso de ejemplo y los tipos por
   módulo, y DEBE dejar «Ahora no» a la vista sin desplazar en un iPhone de
   4,7″ (cierra 042 H15).
5. WHEN la persona toca un aviso de Reservas THEN el sistema DEBE abrir esa
   reserva, con la app abierta o cerrada.
6. El sistema DEBE tener un canal de Android y una categoría de iOS para los
   avisos de Reservas, privados en la pantalla bloqueada como los demás.

### Requisito 15 — Entrar

#### Criterios de aceptación

1. IF falla la entrada THEN el sistema DEBE decirlo en una sola frase, sin decir
   qué campo falla.
2. WHERE Google está disponible EL sistema DEBE decir bajo su botón «Usa la cuenta
   de Google del mismo correo. Si no tienes acceso, pídelo a quien gestiona tu
   negocio en Auphere.».

### Requisito 16 — Estados honestos y accesibilidad

#### Criterios de aceptación

1. Toda pantalla nueva DEBE tener carga (esqueleto con la forma final), vacío,
   error con «Reintentar», parcial y sin red.
2. Toda pantalla nueva DEBE leerse en claro y oscuro con los tokens de la app,
   sin un color escrito a mano.
3. Toda pantalla nueva DEBE crecer con el texto del sistema hasta el máximo sin
   perder lo esencial, y la barra de pestañas NO DEBE recortar sus etiquetas
   (042 H25).
4. Todo control nuevo DEBE tener nombre accesible y un objetivo táctil de al
   menos 44 × 44 pt.
5. WHILE «Reducir movimiento» está activo el sistema DEBE cambiar los
   movimientos nuevos por fundidos.
6. Las formas DEBEN ser las de la 042: listas agrupadas, cápsulas, hojas del
   sistema, vidrio solo en barras y controles flotantes, y nunca vidrio sobre
   vidrio.
7. El aviso breve DEBE usarse solo para acciones cuyo resultado no queda a la
   vista (Reservas, lista de espera, bloqueos, «Nota guardada»), DEBE leerse con
   el lector de pantalla y DEBE durar al menos 4 segundos cuando ofrece
   «Deshacer». Tomar el control y devolver NO DEBEN mostrar aviso breve.

### Requisito 17 — Frescura

#### Criterios de aceptación

1. WHEN la app vuelve al primer plano o llega un evento de cambio de Reservas
   THEN el sistema DEBE releer lo visible de Reservas.
2. WHEN la persona cambia algo de una reserva THEN el sistema DEBE releer el día,
   Inicio y la ficha del contacto afectados.

### Requisito 18 — Datos de ejemplo mientras la API no exista

#### Criterios de aceptación

1. WHERE el build es de desarrollo y se pidió al compilar EL sistema DEBE poder
   enseñar Reservas con datos de ejemplo chilenos en el modo pedido, con la
   marca «Datos de ejemplo» a la vista en cada pantalla de Reservas.
2. El sistema NO DEBE incluir los datos de ejemplo en ningún build que no sea de
   desarrollo (preview, staging ni producción).

### Requisito 19 — Versión 1.1.0 y builds

#### Criterios de aceptación

1. La app DEBE llevar la versión 1.1.0 y la versión de ejecución 1.1.0, para que
   ninguna actualización por aire llegue a la 1.0.0.
2. El perfil `staging` DEBE poder subirse a TestFlight y a la pista interna de
   Play, y el de Android DEBE leer el `google-services.json` de Firebase de una
   variable de EAS.
3. La documentación DEBE decir qué tiene que crear Luis para Android (Play y
   Firebase) y los comandos exactos.

### Entidades clave

Todas son del cliente (tenant) que entra en la app; las alcanza la RLS de la API
por su `tenant_id` y las sirve la spec 043. La app no guarda ninguna en disco.

- **Reserva**: día y hora de llegada, fin, estado (`pending`, `confirmed`,
  `arrived`, `done`, `noshow`, `cancelled`), cliente final (nombre y teléfono),
  origen, canal (WhatsApp, Teléfono, En el local), quién la apuntó, historial;
  en Servicios, servicio y profesional; en Aforo, comensales y hora de llegada
  real.
- **Profesional** (Servicios): nombre y estado de su calendario.
- **Servicio** (Servicios): nombre, duración y precio en CLP.
- **Franja** (Aforo): hora, personas dentro, aforo, bloqueada o no.
- **Bloqueo** (Aforo): día, turno o franjas y motivo.
- **Entrada de la lista de espera**: quién, qué pide, estado y plazo de la oferta.
- **Ajustes de reservas**: modo, aforo, tiempo de mesa, máximo por reserva,
  plazas guardadas, lista de espera, antelación, confirmación.
- **Horario del negocio**: días y horas hábiles, zona horaria.

## Criterios de éxito *(obligatorio)*

- **CE-001**: Desde Inicio, las reservas de hoy sin confirmar están a un toque
  («Ver reservas»).
- **CE-002**: Una llegada sin reserva se registra en 3 toques desde la pestaña
  Reservas (botón «+», ajustar comensales, «Registrar llegada»).
- **CE-003**: Una reserva nueva en Servicios se guarda en 6 toques más escribir
  el nombre.
- **CE-004**: Cada pantalla de Reservas tiene captura en iOS y en Android en sus
  estados ideal, vacío, carga, error y sin red, en claro y oscuro, y con el
  texto grande.
- **CE-005**: Ninguna cifra de Reservas, Inicio o Consumo difiere de la consola
  web en el mismo momento. Se comprueba contra la API de la 043/045 (T047); con
  datos de ejemplo no se puede, y la evidencia lo dice.
- **CE-006**: Una revisión heurística de las capturas no encuentra ningún
  problema de severidad 3 o 4.
- **CE-007**: Tocar un aviso de Reservas abre la reserva en un toque.
- **CE-008**: Hay un build 1.1.0 de iOS para TestFlight y uno de Android para la
  pista interna listos para lanzarse con un comando.

## Fuera de alcance

- **Mover o editar una reserva** — el diseño de hoy no lo tiene; se cancela y se
  vuelve a crear, o lo hace el agente.
- **Ir de la reserva a su conversación** — el diseño lo quitó; vuelve cuando la
  API dé la conversación de la reserva.
- **Cambiar el modo o activar Reservas** — es del admin (spec 043).
- **Editar el horario, el equipo o los servicios** — se hace en la web.
- **Outlook, Calendly y otros calendarios** — solo entra Google Calendar
  (decisión del owner), y su conexión es de la 043.
- **Comprar o recargar saldo** — saldo de solo lectura (decisión del owner).
- **Instagram, Messenger y «Reserve with Google»** — solo WhatsApp por Meta.
- **Papeles dentro del cliente («Propietaria», «recepción»)** — la 030 los
  descartó y la API no los da.
- **Pasar una conversación a otro agente** — descartado en la 030.

## Supuestos

- La API de Reservas y los campos de las mejoras los construyen las specs 043 y
  045, con su contrato congelado en sus carpetas `contracts/`. Mientras no
  existan, la app se construye contra ese contrato con datos de ejemplo
  (Requisito 18) y lo dice.
- La API decide qué acciones valen (estados, plazos, aforo) y la app solo las
  ofrece y las pinta; donde la app calcula algo para enseñarlo (llega tarde,
  «ahora»), usa la hora del negocio.
- Los avisos de Reservas los envía la API (043) con la misma regla de destino y
  de contenido mínimo que los de la 031.
- El build de desarrollo instalado en los simuladores sirve: esta spec no añade
  módulos nativos.
