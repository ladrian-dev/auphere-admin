# Especificación: el Inicio le dice al partner qué hacer hoy

**Rama**: `026-inicio-del-partner` · **Creada**: 2026-10-02 · **Estado**: Borrador

**Entrada**: descripción del owner y plan aprobado el 2026-10-01: ver §Origen.

## Encabezado Auphere *(obligatorio)*

| Campo | Valor |
|---|---|
| **Superficie de confianza** | `0` — lecturas de la consola sobre datos que la plataforma ya guarda. No entra nada nuevo de fuera |
| **Garantías de aislamiento tocadas** | Ninguna nueva. Todo lo que enseña el Inicio es de los clientes del partner de la sesión. La tabla diaria nueva es por cliente, con RLS, y solo la lee el rol de informes filtrando por los clientes del partner |
| **Nota de KB que la justifica** | `[[AUDITORIA-UX-CONSOLA-2026-09-22]]` §3.2 Inicio · `[[PLAN-CONSOLE-V1]]` CP-08 |
| **Qué se mide** | Nada nuevo. El Inicio no llama al modelo ni envía mensajes |

## Origen

El Inicio de la consola enseña hoy cinco cifras sueltas: clientes activos,
conversaciones del mes, mensajes del mes, agentes con incidencia y acciones
pendientes, más «Calculado en X ms». Con Auphere Internal Partner sale
«0 · 0 · 44 · 0 · 0». No dice nada, no invita a nada y no responde a lo que
un partner viene a preguntar.

Un partner es una agencia que vende agentes de WhatsApp a negocios y responde
ante ellos. Abre la consola con cinco preguntas, en este orden:

1. ¿Algún cliente está fallando ahora?
2. ¿Qué espera a una persona?
3. ¿Cuánto valor están generando mis agentes?
4. ¿Cuánto crédito me queda y para cuánto me alcanza?
5. ¿Cómo va cada cliente?

Y una sexta de contexto: ¿qué ha pasado desde la última vez?

Medido en el código el 2026-10-01:

1. Ya existen a medias las incidencias por cliente: número degradado o
   desconectado, sin agente activo, mensajes fallidos en 24 horas y sin
   crédito. Faltan la calidad roja del número, la plantilla rechazada, la
   reautenticación pendiente, el agente con cambios sin publicar y el alta sin
   terminar.
2. Las conversaciones escaladas, los pagos por revisar (spec 025) y los
   mensajes sin responder por número no permitido (spec 024) solo se leen
   cliente por cliente.
3. No hay serie diaria de conversaciones de toda la cartera, ni una medida de
   «resuelto sin intervención humana». Los datos para calcularla sí existen
   (quién respondió cada mensaje, tomas de control, escalados).
4. Las ventas atribuidas a WhatsApp se guardan, pero la consola no las lee.
5. El ritmo de gasto de crédito solo lo lee el panel de Auphere.
6. Dos avisos están definidos y nadie los envía: número degradado y plantilla
   rechazada.
7. El cálculo del Inicio recorre los clientes uno a uno. Su propio código dice
   que con muchos clientes hay que precalcularlo.

## Clarifications

### Session 2026-10-01

- Q: ¿Dónde se trabaja? → A: **En desarrollo** (owner: «necesito que lo trabajemos en la consola de dev»). Se construye en la rama, se enseña en la consola local con datos sembrados y en staging, y llega a producción solo cuando el owner promueve.

## Escenarios de usuario y pruebas *(obligatorio)*

### Historia 1 — Lo que falla, arriba y con el arreglo a un clic (Prioridad: P1)

Al abrir la consola, si algún cliente tiene un problema que le impide atender,
lo primero que ve el partner es un bloque «Necesita tu atención» con una fila
por problema: el cliente, qué pasa dicho en una frase y un botón que lleva al
sitio donde se arregla. Si no hay ninguno, una línea tranquila dice que todos
los clientes están atendiendo.

**Por qué esta prioridad**: un agente mudo es el peor incidente de un partner:
su cliente pierde ventas y se entera antes que él.

**Prueba independiente**: con un cliente sin crédito y otro con el número
desconectado, abrir el Inicio y llegar al arreglo de cada uno en un clic.

**Escenarios de aceptación**:

1. **Dado** un cliente sin crédito, **cuando** el partner abre el Inicio,
   **entonces** ve «Flor y Encanto · sin crédito, el agente no responde» y un
   botón «Asignar crédito» que lleva a Consumo con ese cliente elegido.
2. **Dado** un número desconectado, con calidad roja o pendiente de volver a
   autorizar, **cuando** abre el Inicio, **entonces** ve la fila con el botón
   que lleva a Canales de ese cliente.
3. **Dado** un agente con cambios sin publicar desde hace más de un día,
   **cuando** abre el Inicio, **entonces** ve la fila con el botón que lleva a
   revisar y publicar.
4. **Dado** que ningún cliente tiene problemas, **cuando** abre el Inicio,
   **entonces** ve «Todos tus clientes están atendiendo» y ningún bloque vacío.
5. **Dado** un cliente con varios problemas, **cuando** abre el Inicio,
   **entonces** los ve ordenados por gravedad: primero lo que deja al agente
   mudo.

---

### Historia 2 — Lo que espera a una persona (Prioridad: P1)

Un bloque «Por revisar ahora» cuenta, para toda la cartera, las conversaciones
escaladas que nadie ha atendido, los pagos por revisar y los mensajes sin
responder de números no permitidos. Cada cifra lleva a la lista filtrada.

**Por qué esta prioridad**: es la bandeja de trabajo del día del equipo.

**Prueba independiente**: con dos conversaciones escaladas en dos clientes y
un pago pendiente, abrir el Inicio y ver «2» y «1» con su enlace.

**Escenarios de aceptación**:

1. **Dado** conversaciones escaladas abiertas en varios clientes, **cuando**
   el partner abre el Inicio, **entonces** ve el total y, al pulsar, la lista
   de conversaciones escaladas de su cartera.
2. **Dado** un pago pendiente de revisión, **cuando** abre el Inicio,
   **entonces** ve «1 pago por revisar» con el cliente.
3. **Dado** que no hay nada por revisar, **cuando** abre el Inicio,
   **entonces** el bloque dice que no hay nada pendiente.

---

### Historia 3 — El valor que generan los agentes (Prioridad: P2)

Cuatro tarjetas con valor, variación contra el periodo anterior y una
tendencia pequeña: conversaciones atendidas, porcentaje resuelto sin
intervención humana, ventas atribuidas a WhatsApp y tiempo de respuesta. Un
selector cambia el periodo entre Hoy, 7 días y 30 días. Debajo, una gráfica de
conversaciones por día, apiladas por cliente.

**Por qué esta prioridad**: es lo que el partner enseña a sus clientes para
renovar y crecer. Va después de lo urgente porque no se pierde nada si se mira
mañana.

**Prueba independiente**: con 7 días de actividad sembrada en tres clientes,
cambiar el periodo y comprobar que tarjetas, variación y gráfica cambian.

**Escenarios de aceptación**:

1. **Dado** actividad en el periodo y en el anterior, **cuando** el partner
   mira las tarjetas, **entonces** cada una dice su valor y cuánto subió o
   bajó, en porcentaje o en puntos.
2. **Dado** ventas en dos monedas, **cuando** mira «Ventas por WhatsApp»,
   **entonces** ve un importe por moneda, nunca una suma de monedas distintas.
3. **Dado** un periodo sin actividad anterior, **cuando** mira una tarjeta,
   **entonces** no ve una variación inventada sino «sin datos del periodo
   anterior».
4. **Dado** la gráfica diaria, **cuando** pasa el cursor sobre un día,
   **entonces** ve cuántas conversaciones tuvo cada cliente ese día.

---

### Historia 4 — Crédito y autonomía (Prioridad: P2)

Una tarjeta dice el crédito disponible y para cuántos días alcanza al ritmo de
los últimos 7 días, y nombra los clientes que se quedarán sin crédito antes de
fin de mes.

**Por qué esta prioridad**: quedarse sin crédito es la causa más común de un
agente mudo, y se puede ver venir.

**Prueba independiente**: con un gasto diario conocido, comprobar los días de
autonomía.

**Escenarios de aceptación**:

1. **Dado** un saldo y un gasto medio diario, **cuando** el partner mira la
   tarjeta, **entonces** ve «alcanza para N días».
2. **Dado** un cliente cuyo tope se agotará antes de fin de mes al ritmo
   actual, **cuando** mira la tarjeta, **entonces** lo ve nombrado con un
   enlace para darle más crédito.
3. **Dado** que no hubo gasto en 7 días, **cuando** mira la tarjeta,
   **entonces** no ve días de autonomía inventados.

---

### Historia 5 — La cartera de un vistazo (Prioridad: P2)

Una tabla «Tus clientes» con una fila por cliente: estado, conversaciones de
los últimos 7 días con su tendencia, porcentaje resuelto por el agente,
crédito restante y última actividad. Pulsar una fila abre el cliente.

**Prueba independiente**: con tres clientes, ver sus filas y ordenarlas por
actividad.

**Escenarios de aceptación**:

1. **Dado** varios clientes, **cuando** el partner mira la tabla,
   **entonces** ve cada uno con su estado, tendencia de 7 días, resueltas,
   crédito y última actividad.
2. **Dado** un cliente en alta, **cuando** mira la tabla, **entonces** su
   fila dice qué paso le falta.

---

### Historia 6 — Lo que ha pasado (Prioridad: P3)

Una lista «Actividad reciente» con los últimos hechos relevantes de la
cartera: versiones publicadas, números conectados o desconectados, plantillas
aprobadas o rechazadas, pagos confirmados o rechazados, clientes creados.

**Prueba independiente**: publicar una versión y confirmar un pago, y verlos
arriba de la lista.

**Escenarios de aceptación**:

1. **Dado** hechos recientes, **cuando** el partner abre el Inicio,
   **entonces** ve los últimos ocho, con quién, qué cliente y hace cuánto.

---

### Casos límite

- **Partner sin clientes**: el Inicio enseña «Ponte en marcha» y una llamada a
  crear el primer cliente; no hay tarjetas a cero ni gráficas vacías.
- **Cliente nuevo sin actividad**: aparece en la cartera, no en las
  variaciones.
- **Una parte del Inicio falla al cargar**: las demás se enseñan; la que falla
  dice que no se pudo cargar y deja reintentar, sin nombres técnicos.
- **Miembro con permisos limitados** (por ejemplo, solo facturación): ve solo
  los bloques de lo que puede ver, sin huecos.
- **Cientos de clientes**: el Inicio sigue cargando en menos de un segundo.
- **Ventas de un cliente que aún no tiene tienda conectada**: la tarjeta de
  ventas no aparece si ningún cliente tiene ventas que contar.
- **Conversaciones del Playground**: no cuentan en ninguna cifra.

## Requisitos *(obligatorio)*

### Requisito 1 — Necesita tu atención

1. El sistema DEBE enseñar, encima de todo lo demás, los problemas que
   impiden atender a un cliente, uno por fila, con el cliente, una frase y un
   enlace al arreglo.
2. Los problemas DEBEN incluir: sin crédito, número desconectado o degradado,
   calidad del número en rojo, autorización de Meta caducada, sin agente
   publicado, cambios sin publicar desde hace más de un día, mensajes fallidos
   en las últimas 24 horas, plantilla rechazada y alta sin terminar.
3. Las filas DEBEN ir ordenadas por gravedad: primero las que dejan al agente
   sin responder.
4. Sin problemas, el sistema DEBE decirlo en una línea.

### Requisito 2 — Por revisar ahora

1. El sistema DEBE contar, para toda la cartera, las conversaciones escaladas
   abiertas, los pagos por revisar y los mensajes sin responder por número no
   permitido de los últimos 7 días.
2. Cada cifra DEBE llevar a una lista donde actuar.

### Requisito 3 — Valor y tendencia

1. El sistema DEBE enseñar conversaciones atendidas, porcentaje resuelto sin
   intervención humana, ventas atribuidas a WhatsApp y tiempo de respuesta
   mediano, cada uno con la variación contra el periodo anterior de igual
   duración y una tendencia diaria.
2. Una conversación cuenta como **resuelta sin intervención humana** si en el
   periodo tuvo mensajes del cliente, ninguna respuesta de una persona del
   equipo, no se escaló y el agente no se apartó.
3. Las ventas DEBEN agruparse por moneda.
4. El selector de periodo DEBE ofrecer Hoy, 7 días y 30 días, y 7 días DEBE
   ser el de partida.
5. El sistema DEBE enseñar una gráfica de conversaciones por día del periodo,
   apiladas por cliente, con los cinco clientes de más actividad y el resto
   juntos.

### Requisito 4 — Crédito

1. El sistema DEBE enseñar el crédito disponible y los días que alcanza al
   gasto medio de los últimos 7 días.
2. El sistema DEBE nombrar los clientes cuyo tope se agotará antes de fin de
   mes al ritmo actual.

### Requisito 5 — Cartera

1. El sistema DEBE enseñar una fila por cliente con estado, conversaciones de
   7 días y su tendencia, porcentaje resuelto, crédito restante y última
   actividad, ordenable por cada columna.

### Requisito 6 — Actividad reciente

1. El sistema DEBE enseñar los ocho hechos más recientes de la cartera con
   quién, cliente y hace cuánto, tomados de la auditoría.

### Requisito 7 — Lo que deja de estar

1. «Calculado en X ms» NO DEBE enseñarse.
2. Ninguna cifra DEBE aparecer sin variación o sin enlace a una acción.
3. «Ponte en marcha» DEBE desaparecer al completarse.

### Requisito 8 — Avisos que hoy no salen

1. El sistema DEBE enviar el aviso de número degradado y el de plantilla
   rechazada a la campana de la consola, con el mismo texto que la fila del
   Inicio.

### Requisito 9 — Rendimiento y permisos

1. El Inicio DEBE cargar en menos de un segundo con cientos de clientes.
2. Cada bloque DEBE respetar el permiso del miembro que lo mira.
3. El Inicio NO DEBE enseñar costes internos de Auphere ni identificadores
   internos.

### Entidades clave

- **Actividad diaria por cliente**: un resumen por cliente y día con
  conversaciones, mensajes, resueltas sin persona, escaladas, fallidos, tiempo
  de respuesta mediano, ventas por moneda y pagos revisados. Precalculado para
  que la cartera entera se lea de una vez.
- **Problema de un cliente**: tipo, gravedad, frase y dónde se arregla.

## Criterios de éxito *(obligatorio)*

- **CE-001**: un partner con un cliente sin crédito llega al arreglo en un
  clic desde el Inicio.
- **CE-002**: el Inicio carga en menos de un segundo con 24 clientes y con
  200.
- **CE-003**: cada cifra del Inicio coincide con la misma cifra en la pantalla
  del cliente o de Consumo.
- **CE-004**: ninguna tarjeta enseña una variación sin periodo anterior que la
  respalde, ni suma importes en monedas distintas.
- **CE-005**: un miembro de facturación ve solo el crédito y la actividad que
  le corresponde, sin huecos ni errores.

## Fuera de alcance

- Exportar el Inicio o enviarlo por correo.
- Personalizar qué bloques se ven.
- Objetivos o metas por cliente.
- Comparar clientes entre partners.

## Supuestos

- La gravedad de los problemas sigue este orden: sin crédito, sin agente,
  número desconectado o con autorización caducada, calidad roja, mensajes
  fallidos, plantilla rechazada, cambios sin publicar, alta sin terminar.
- El tiempo de respuesta es la mediana entre un mensaje del cliente y la
  respuesta del agente.
- Las ventas son las que la tienda del cliente atribuye a WhatsApp, con el
  retraso del sondeo actual (hasta 6 horas).
- El trabajo se hace en desarrollo y staging; producción solo al promover.
