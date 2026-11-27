# Especificación: el informe del piloto

**Carpeta**: `specs/083-informe-del-piloto` · **Creada**: 2026-11-26 · **Enmendada**: 2026-11-27 (las cifras pasan a la pantalla Métricas, antes Consumo; ver «Enmienda 2026-11-27») · **Estado**: Lista para implementar (definiciones aceptadas por Luis el 2026-11-26; el resto, decidido en la spec y pendiente de su revisión final)

**Entrada**: Neliana (partner Autprod) cierra el piloto de Jemma's Hair hacia el 7 de diciembre y necesita un informe que enseñar al cliente para anclar el precio. Luis pidió dejar listos y probados los P0 y P1 de la beta; esta es la P1 «informe del piloto». Sirve para cualquier partner y cualquier cliente.

## Encabezado Auphere *(obligatorio)*

| Campo | Valor |
|---|---|
| **Superficie de confianza** | `0` · la API de la consola de partners. Una lectura nueva bajo `/console/clients/{ref}/…` y una página de la consola que la pinta. No abre ninguna superficie. |
| **Garantías de aislamiento tocadas** | **Garantía 1** (la RLS separa negocios): la lectura junta datos de un cliente y tiene que quedarse dentro de él. Y el alcance de la consola (CP-04, C8): un partner solo ve sus clientes, y ninguna respuesta lleva palabras ni datos de un cliente final. La garantía 8 no se toca: no hay turno ni cliente final que resolver. |
| **Nota de KB que la justifica** | `/Users/lmatos/Work/Auphere/nexus/research/2026-11-26-beta-jemma-p0-p1.md`, sección «083: informe del piloto». |
| **Qué se mide** | **Nada.** Lee filas que ya existen; no gasta modelo, reloj de máquina ni herramientas. |

## Por qué

El piloto de Jemma termina y Neliana tiene que decir con cifras qué hizo el agente: cuántas conversaciones atendió, qué parte resolvió sin que interviniera nadie, lo rápido que contestó, qué hizo en la agenda y cuánto costó. Hoy esas cifras están repartidas (el Panel del cliente, la página Rendimiento del agente, Consumo), cada una con su ventana y su regla, y dos de esas reglas dan una cifra equivocada:

- «Pasada a una persona» mira el **estado actual** de la conversación (`services/improvement/performance.py`, `handed_to_person`). Una conversación que una persona tomó y devolvió al agente cuenta como resuelta sin persona.
- Los días se agrupan en **UTC**. Para un negocio de Caracas, lo que entra a las 21:00 cuenta en el día siguiente.

Además, una fila de `conversations` es un contacto en un número, y se reabre cada vez que vuelve a escribir: contar filas no es contar conversaciones.

## Clarifications

### Session 2026-11-26 (Luis: «Me queda claro»)

- Q: ¿Qué es una conversación? → A: Un ciclo: de que se abre a que se resuelve o se cierra por inactividad.
- Q: ¿Cuándo está resuelta «sin persona»? → A: Cuando en ese ciclo no hubo takeover, ni escalado, ni freno.
- Q: ¿Qué es una incidencia? → A: Cada escalado, con su motivo, o cada freno. Se da por resuelta cuando se resuelve la conversación.
- Q: ¿Desde dónde y hasta dónde se mide la primera respuesta? → A: Desde el primer mensaje entrante del ciclo hasta el primer envío del agente. Incluye los 3 s de agrupación.
- Q: ¿Cómo se exporta? → A: Una vista imprimible.

### Decidido en la spec, sin Luis (lo revisa al final)

Luis no aprueba pasos intermedios. Estas decisiones se tomaron con el código delante; cada una dice por qué.

- **D1. Dónde va la página.** Como una pestaña más del cliente, «Informe», después de «Anuncios». La lectura es de un cliente, como la de Anuncios, que ya es el precedente de un informe por cliente con su periodo. El filtro de cliente es un selector en la propia página que lleva al informe de otro cliente con las mismas fechas. Una entrada propia en la barra lateral chocaba con el design system (la barra lleva solo Panel, Clientes, Consumo y Auditoría) y con la prueba de paridad de `nav.ts` con la app de escritorio.
- **D2. Qué ciclo cuenta.** Un ciclo cuenta como conversación solo si el contacto escribió en él. Su día es el del primer mensaje del contacto, en la zona del cliente. Un ciclo que abrió un aviso del negocio (un recordatorio) y que nadie contestó no es una conversación atendida: ya cuenta en Recordatorios.
- **D3. Reabrir a mano.** Si una persona reabre a mano una conversación resuelta, deshace la resolución (spec 064, requisito 4.4): sigue el mismo ciclo. Si la reabre el contacto o un aviso, empieza un ciclo nuevo.
- **D4. Las tres vías de una persona.** Cuentan como takeover: tomarla desde la Bandeja, tomarla desde el panel de operador de Auphere y que una persona del negocio escriba en ella (desde la Bandeja, desde el panel o desde la app de WhatsApp Business en coexistencia). La Bandeja deja un evento y una línea de auditoría del mismo acto: es un solo takeover.
- **D5. El freno corregido también cuenta.** Un freno en el que el agente rehízo la respuesta y no pasó la conversación a nadie hace que ese ciclo no cuente como «sin persona». Es la definición aceptada («ni freno») y es la lectura prudente: algo paró al agente.
- **D6. El freno que pasa la conversación es una incidencia, no dos.** Ese freno deja su línea de auditoría y además un escalado del sistema con el motivo «reserva sin registrar». Se cuenta una vez, con ese motivo.
- **D7. El motivo es un código.** El motivo que escribe el agente al pedir una persona es texto libre del modelo y puede repetir lo que dijo el cliente. La consola de partners no sirve palabras de un cliente final (C8), así que el informe da el motivo como un código cerrado: «el agente pidió una persona», «sin saldo», «reserva sin registrar»… El encargo pedía «cada escalado con su motivo»; gana C8, y el motivo es la categoría.
- **D8. La primera respuesta, con qué reloj.** El primer envío del agente es la hora a la que el proveedor aceptó su primer mensaje del ciclo: la hora de creación del mensaje más `latency_ms`. `latency_ms` sí se escribe, en contra de lo que decía el encargo, pero es el tiempo de entrega (de crear la fila a que el proveedor la acepta, `outbound.py:855`), no el de respuesta. Sin él, vale la hora de creación. `delivered_at` no sirve: depende del teléfono del cliente. Solo cuentan los mensajes del agente; no las plantillas del sistema ni lo que escriba una persona. La hora del entrante es la de la plataforma al guardarlo, antes de agrupar: los 3 s de agrupación entran.
- **D9. Ciclos sin respuesta del agente.** Si en un ciclo el agente no llegó a enviar nada (lo tomó una persona, una puerta no lo dejó contestar), ese ciclo no entra en el porcentaje de ≤60 s. El informe dice cuántos son, al lado.
- **D10. La agenda y el actor «sistema».** Las cancelaciones del sistema son reservas sin confirmar que se liberaron solas: van aparte, como «liberadas». Las altas del sistema son la importación «Paso a Reservas»: no son operaciones del periodo y no se cuentan.
- **D11. Las cancelaciones del agente antes de la 080.** Hoy el agente cancela con el actor «cliente» (`reservas/tools.py:696`); lo corrige la spec 080. Una cancelación de «cliente» solo tiene dos orígenes: el agente al cancelar, o el cliente que contesta «no» a la confirmación, que deja antes, en la misma transacción, un evento «contestó que no». La regla: una cancelación de «cliente» sin ese evento es del agente. Vale antes y después del arreglo.
- **D12. El gasto, solo el total.** Es la misma cifra que la fila del cliente en Consumo: lo que pagó su bolsa (conversaciones y pruebas a su cargo), en la moneda de la cuenta del partner. La estimación de Meta va aparte y con «aprox.». Consumo agrupa sus días en UTC, así que el informe da el total del periodo exacto y no una serie por día.
- **D13. El periodo, como mucho 92 días.** Un trimestre cubre cualquier piloto; más largo, la lectura se encarece sin que nadie lo haya pedido.
- **D14. La página Rendimiento del agente usa los mismos ciclos.** Un solo constructor de ciclos alimenta el informe y Rendimiento: las dos dicen lo mismo de las conversaciones del agente. El Panel del cliente conserva su regla de hoy (fuera de alcance).
- **D15. El eco lleva la hora de Meta.** *(Decidido en la implementación, 2026-11-26.)* El eco de la app de WhatsApp Business guarda la hora a la que Meta dice que se envió; la fila que crea, o la reapertura que provoca, lleva la hora de la plataforma, segundos después. Sin una regla, una persona que escribe primero desde la app a un contacto nuevo (o a una conversación resuelta) dejaría su mensaje fuera del ciclo, y ese ciclo contaría «sin persona». La regla: una señal de persona que cae hasta **10 minutos antes** de que empiece un ciclo, y fuera del anterior, es de ese ciclo. Más atrás, no: un takeover sobre una conversación resuelta que el contacto reabre días después no cuenta, porque la reapertura devuelve la conversación al agente.

### Enmienda 2026-11-27 (Luis, antes de fusionar el PR 73)

Luis vio la pestaña y la descartó: «Informe» suena hecho por IA, y no tiene sentido elegir otro cliente desde la ficha de un cliente. Su encargo: quitar la pestaña, llevar las cifras a la pantalla Consumo con otro nombre, y que la vista sirva para ver patrones y decidir con números, sin enseñar cosas ni contestar preguntas que no hacen falta.

Lo que se mantiene: las definiciones de arriba (ciclo, sin persona, incidencia, primera respuesta), los requisitos 2–7, 9 y 10, y la API. Lo que cambia, decidido sin Luis (lo revisa al final):

- **D16. El nombre: «Métricas»** (en inglés, «Metrics»). Es lo que la pantalla enseña, el dinero y las conversaciones, y es como se llama esta vista en cualquier consola. No promete un relato. La ruta sigue siendo `/usage`, para no romper los enlaces, la paleta ni la app de escritorio. Cambian las etiquetas que llevan a la pantalla del partner: la navegación, el título, el buscador, la paleta y la sección de la app de escritorio. La consola del cliente (Acceso y lite) y la membresía siguen diciendo «Consumo», porque allí solo hay consumo.
- **D17. Qué ve cada rol.** La pantalla, como hoy, con `usage:read`. La sección «Conversaciones», además con `conversations:read`: owner, admin, builder y analyst. Billing ve solo el dinero, y para él la sección no existe. Así lo pedía la pestaña (1.6) y así lo exige la API.
- **D18. Un solo filtro.** El cliente y el periodo de la pantalla (`?client=&days=`, 7, 30 o 90 días) mandan en todas las secciones. Se suben encima de todo, y el gasto por día deja de llevar su propio selector. Las conversaciones son de un cliente, porque la lectura es por cliente. Sin cliente elegido, la sección pide que se elija uno y no enseña cifras. Sumar todos los clientes de un partner queda fuera de alcance.
- **D19. El periodo.** Los últimos N días hasta hoy en la zona del cliente, comparados con los N días justo anteriores: dos lecturas del mismo endpoint. Desaparecen las fechas a mano y su validación en pantalla; la API la conserva.
- **D20. Lo que se queda y lo que se va.** Cada bloque se queda solo si ayuda a decidir algo:
  - Se quedan:
    - **Arriba, con su diferencia** frente al periodo anterior: conversaciones; resueltas sin persona frente al 70 %; respondidas en 60 s o menos frente al 95 %; mediana de la primera respuesta; incidencias; coste por conversación.
    - **Por día**, sin persona y con persona: la tendencia.
    - **Por hora del día y por día de la semana**, sin persona y con persona: cuándo cubrir con personas.
    - **Incidencias por motivo**, con su parte y su diferencia: qué arreglar en el agente o en el canal.
    - **Agenda por quién**: cuánto trabajo quita el agente.
    - **Recordatorios fallidos u omitidos**.
    - **Freno de reservas**: cuántas veces se equivocó el agente con una cita.
  - Se van:
    - La lista de las incidencias recientes: son horas sueltas y no deciden nada.
    - El encabezado «Informe del periodo».
    - El gasto del informe. El dinero ya tiene su sección; del informe solo queda el coste por conversación.
    - Las definiciones en párrafo bajo cada bloque, que pasan a un solo bloque plegado, «Cómo se cuenta».
- **D21. Imprimir.** Se mantiene (la vista imprimible fue decisión de Luis), pero solo la sección de conversaciones del cliente elegido, con su encabezado. Nunca el dinero del partner: el saldo y las bolsas de otros clientes no se enseñan a un cliente.
- **D22. La pestaña se va.** La ficha del cliente deja de tener «Informe». `/clients/{ref}/report` lleva a `/usage?client={ref}`, para no romper enlaces.
- **D23. La API.** El mismo endpoint, con dos desgloses más: `conversations.by_hour` (24 filas, la hora local del primer mensaje del contacto) y `conversations.by_weekday` (7 filas, del lunes al domingo), cada fila partida en sin persona y con persona. La prueba de aislamiento de la ruta lo sigue cubriendo.

## Escenarios de usuario y pruebas *(obligatorio)*

### Historia 1 — Neliana enseña el piloto a su cliente (Prioridad: P1)

Neliana abre el cliente Jemma's Hair, va a «Informe», elige del 10 de noviembre al 7 de diciembre y ve, arriba, las conversaciones atendidas, el porcentaje resuelto sin persona frente a su objetivo del 70 %, la primera respuesta frente al 95 % en un minuto y el gasto del periodo. Debajo, la gráfica por día, la agenda, los recordatorios y las incidencias. Pulsa «Imprimir» y obtiene un documento limpio que puede enseñar o guardar en PDF.

**Por qué esta prioridad**: es el encargo. Sin esto, Neliana llega al cierre sin cifras.

**Prueba independiente**: con un cliente con datos sembrados (ciclos, escalados, freno, reservas, recordatorios y gasto), la página y su lectura dan las cifras que la siembra fija.

**Escenarios de aceptación**:

1. **Dado** un cliente con 10 ciclos del contacto en el periodo, 3 con escalado, takeover o freno, **cuando** se abre el informe, **entonces** dice 10 conversaciones, 7 resueltas sin persona y 70 %.
2. **Dado** un ciclo en el que una persona tomó la conversación y la devolvió al agente, **cuando** se cuenta, **entonces** es «con persona», aunque hoy la conversación esté con el agente.
3. **Dado** un cliente de Caracas con un mensaje a las 23:30 hora local del día 12, **cuando** se agrupa por día, **entonces** cuenta en el 12, no en el 13.
4. **Dado** el periodo elegido, **cuando** se pulsa «Imprimir», **entonces** salen solo el informe y su encabezado (cliente, periodo, zona horaria), sin la navegación ni los filtros, en tema claro y con las barras de la gráfica visibles.

---

### Historia 2 — Las cifras se pueden defender (Prioridad: P1)

Si el cliente pregunta «¿qué es una incidencia?» o «¿desde cuándo cuenta el minuto?», cada cifra lleva su definición corta en la propia página, la misma que esta spec.

**Por qué esta prioridad**: un informe para anclar un precio que no se puede explicar no sirve.

**Prueba independiente**: cada bloque de la página tiene su nota de definición, y la de la agenda y el freno dicen sus límites.

**Escenarios de aceptación**:

1. **Dado** el bloque de freno de reservas, **cuando** se lee, **entonces** dice que no detecta una cita confirmada a mano fuera de la agenda.
2. **Dado** un cliente que no cierra conversaciones por inactividad, **cuando** se abre el informe, **entonces** una nota dice que una conversación que sigue abierta cuenta una sola vez.

---

### Historia 3 — La página Rendimiento del agente dice lo mismo (Prioridad: P2)

La página Rendimiento de un agente cuenta con los mismos ciclos, el mismo «con persona» por historial y los días en la zona del cliente.

**Por qué esta prioridad**: dos páginas con cifras distintas de lo mismo restan credibilidad a las dos.

**Prueba independiente**: con la misma siembra, Rendimiento del agente principal da las mismas conversaciones y resueltas sin persona que el informe.

**Escenarios de aceptación**:

1. **Dado** un ciclo tomado y devuelto, **cuando** se lee Rendimiento, **entonces** cuenta como «pasada a una persona».
2. **Dado** un mensaje a las 23:30 hora de Caracas, **cuando** se lee la serie de Rendimiento, **entonces** cuenta en su día local.
3. **Dado** la lista de conversaciones del agente, **cuando** una se tomó y se devolvió, **entonces** su resultado es «pasada a una persona» con el motivo que dejó su historial.

---

### Casos límite

- **Ciclo abierto.** Cuenta con lo que pasó hasta ahora. Si el periodo acaba hoy, el informe llega hasta ahora mismo.
- **Ciclo que empezó antes del periodo.** Si el primer mensaje del contacto en ese ciclo es anterior al periodo, el ciclo no es del periodo, aunque el contacto vuelva a escribir dentro.
- **Cliente sin cierre por inactividad.** Un contacto que escribe de vez en cuando y nadie resuelve es un solo ciclo durante meses. El informe lo dice (Historia 2, escenario 2).
- **Datos de antes de la Bandeja (spec 030).** Antes de la migración 0149 no había eventos de conversación: lo de entonces es un ciclo por fila. El piloto es posterior.
- **Freno antes de la 0225.** La línea de auditoría del freno existe desde la spec 056. Antes, un freno no deja rastro y no cuenta.
- **Un mensaje del agente que falló.** No es un envío: no cuenta como primera respuesta.
- **Mensajes importados del historial** (coexistencia). No son del periodo ni abren ciclo.
- **El Playground.** No es tráfico de clientes: sus conversaciones no cuentan (`console_traffic`).
- **Cliente sin Reservas.** No hay bloque de agenda ni de recordatorios (§V: la ausencia se diseña).
- **Gasto que no se pudo leer.** El resto del informe sale; el bloque de gasto dice que no se pudo leer y deja reintentar (estado parcial).
- **Periodo sin nada.** El informe sale entero, con ceros y un estado vacío que explica que no hubo conversaciones en esas fechas.
- **Fechas imposibles** (el final antes del principio, más de 92 días, o el futuro). La página no las pide: los campos lo impiden y la API contesta 422.
- **Texto largo.** El nombre del cliente o de un motivo en alemán, o con 40 caracteres, no rompe las tarjetas.

## Requisitos *(obligatorio)*

### Requisito 1 — Una página de informe por cliente

**Historia de usuario:** Como partner, quiero un informe de un cliente para unas fechas, para enseñarle lo que hizo su agente.

#### Criterios de aceptación

1. ~~El sistema DEBE ofrecer el informe como una pestaña del cliente, «Informe», después de «Anuncios», en la consola nueva.~~ *Enmendado el 2026-11-27: las cifras van en la pantalla Métricas (requisito 11).*
2. ~~El informe DEBE tener dos filtros: el cliente (un selector con los clientes del partner, que lleva al informe del elegido con las mismas fechas) y el periodo (desde y hasta, en días del calendario del cliente).~~ *Enmendado el 2026-11-27: el filtro es el de la pantalla, cliente y 7, 30 o 90 días (11.5 y 11.6).*
3. El periodo DEBE viajar en la dirección de la página, para que recargarla o compartirla dé el mismo informe.
4. Sin periodo, el informe DEBE abrir con los últimos 30 días, hoy incluido.
5. IF el periodo acaba antes de empezar, pasa de 92 días o acaba después de hoy THEN la API DEBE contestar 422 con un código, y la página NO DEBE permitir pedirlo. *Desde la enmienda, la pantalla solo pide 7, 30 o 90 días.*
6. El informe DEBE pedir los permisos de leer conversaciones y consumo. Quien no los tenga NO DEBE ver la pestaña.
7. Los días DEBEN ser los de la zona horaria del cliente, y el informe DEBE decir cuál es.

### Requisito 2 — Conversaciones atendidas

**Historia de usuario:** Como partner, quiero saber cuántas conversaciones atendió el agente, contadas como las cuenta una persona.

#### Criterios de aceptación

1. Un ciclo DEBE empezar cuando se crea la conversación o cuando el contacto o un aviso la reabren, y DEBE acabar cuando se resuelve, a mano o por inactividad.
2. WHEN una persona reabre a mano una conversación resuelta THEN el sistema DEBE tratarlo como el mismo ciclo (D3).
3. Un ciclo DEBE contar como conversación solo si el contacto escribió en él. Su día DEBE ser el del primer mensaje del contacto en el ciclo, en la zona del cliente (D2).
4. Un ciclo DEBE ser del periodo cuando su primer mensaje del contacto cae dentro del periodo.
5. Las conversaciones del Playground y los mensajes importados del historial NO DEBEN contar.
6. El informe DEBE dar el total del periodo y la serie por día, con cada día partido en «resueltas sin persona» y «con persona».

### Requisito 3 — Resuelta sin persona, por historial

**Historia de usuario:** Como partner, quiero saber qué parte resolvió el agente solo, sin que eso dependa de cómo está la conversación hoy.

#### Criterios de aceptación

1. Un ciclo DEBE contar como «con persona» si entre su principio y su final (o ahora, si sigue abierto) hubo cualquiera de estos: un escalado (lo pidiera el agente o lo abriera una puerta), un takeover por cualquiera de las vías de D4, o un freno de reservas, corregido o no (D5).
2. Cualquier otro ciclo DEBE contar como «resuelto sin persona».
3. El informe DEBE dar el porcentaje resuelto sin persona frente al objetivo del 70 %. Sin conversaciones NO DEBE dar un porcentaje.
4. La regla DEBE salir del historial de la conversación, no de su estado actual.

### Requisito 4 — Primera respuesta en un minuto

**Historia de usuario:** Como partner, quiero saber cuántas veces el agente contestó en menos de un minuto.

#### Criterios de aceptación

1. Para cada conversación del periodo, la primera respuesta DEBE medirse desde el primer mensaje del contacto del ciclo hasta el primer envío del agente en ese ciclo, con el reloj de D8.
2. Solo DEBEN contar los mensajes que escribió el agente y que el proveedor aceptó.
3. El informe DEBE dar el porcentaje de conversaciones respondidas en 60 s o menos frente al objetivo del 95 %, la mediana y el percentil 90.
4. Las conversaciones sin ningún envío del agente NO DEBEN entrar en el porcentaje, y el informe DEBE decir cuántas son (D9).
5. El cálculo DEBE salir de las horas guardadas, también para los mensajes de antes de esta spec: no depende de una columna nueva.

### Requisito 5 — Incidencias y freno de reservas

**Historia de usuario:** Como partner, quiero ver qué hizo que una conversación necesitara a alguien y si se cerró.

#### Criterios de aceptación

1. Cada escalado del periodo DEBE ser una incidencia, con su motivo como código cerrado (D7).
2. Cada freno de reservas del periodo que no pasó la conversación a nadie DEBE ser una incidencia con el motivo «freno de reservas». El que la pasó DEBE ser una sola incidencia, la de su escalado (D6).
3. Una incidencia DEBE darse por resuelta cuando se resuelve la conversación en el ciclo en que ocurrió. Si no, sigue abierta.
4. El informe DEBE dar el total, cuántas están resueltas y cuántas abiertas, el recuento por motivo y la lista de las más recientes con su hora local, su motivo y cuándo se resolvió. *Enmendado el 2026-11-27: la API sigue dando la lista, pero la pantalla no la enseña (13.4).*
5. El informe NO DEBE dar el texto del motivo que escribió el agente, ni nada que identifique al cliente final.
6. El bloque de freno DEBE decir cuántas veces paró una respuesta, cuántas lo corrigió el agente y cuántas pasó la conversación a una persona.
7. El bloque de freno DEBE decir que es una aproximación a «ninguna cita sin registrar»: no detecta una cita confirmada a mano sin pasar por la agenda.

### Requisito 6 — Agenda y recordatorios

**Historia de usuario:** Como partner, quiero saber qué hizo el agente en la agenda y cuántos recordatorios salieron.

#### Criterios de aceptación

1. WHERE el cliente tiene Reservas, el informe DEBE dar las reservas creadas, movidas y canceladas del periodo, contadas por la fecha de la operación y por quién: el agente, una persona o el cliente.
2. Las cancelaciones automáticas DEBEN ir aparte, como «liberadas sin confirmar», y las altas por importación NO DEBEN contar (D10).
3. Una cancelación de «cliente» sin un «contestó que no» de la misma reserva en la misma operación DEBE contar como del agente (D11).
4. WHERE el cliente tiene Reservas, el informe DEBE dar los recordatorios y las peticiones de confirmación del periodo: enviados, fallidos y omitidos.
5. IF el cliente no tiene Reservas THEN el informe NO DEBE pintar esos bloques, ni vacíos ni con una explicación.

### Requisito 7 — El gasto del periodo

**Historia de usuario:** Como partner, quiero ver cuánto costó el agente en el periodo, para hablar de precio.

#### Criterios de aceptación

1. El informe DEBE dar lo que pagó la bolsa del cliente en el periodo con la misma regla que Consumo (D12), en la moneda de la cuenta.
2. El informe DEBE dar aparte la estimación de los mensajes de Meta, marcada «aprox.».
3. El informe DEBE dar el gasto por conversación atendida. Sin conversaciones, NO DEBE darlo.
4. IF no se pudo leer el gasto THEN el resto del informe DEBE salir y el bloque de gasto DEBE decirlo, con la opción de reintentar.

### Requisito 8 — Una página que se presenta

**Historia de usuario:** Como partner, quiero una página que pueda enseñar o imprimir sin retocar.

#### Criterios de aceptación

1. ~~La página DEBE abrir con las cifras (conversaciones, resueltas sin persona, primera respuesta y gasto) y, debajo, la gráfica, la agenda, los recordatorios y las incidencias.~~ *Enmendado el 2026-11-27:* la sección DEBE abrir con las cifras de D20 con su diferencia (12.1) y, debajo, por día, por hora y día de la semana, las incidencias por motivo, la agenda, los recordatorios y el freno.
2. Las cifras DEBEN ir en números tabulares y los importes con el código detrás («412,80 USD»).
3. La gráfica DEBE ser de barras macizas con las dos series en los dos verdes del sistema, distinguidos por luminosidad.
4. El ámbar DEBE usarse solo para avisos reales. Un objetivo no alcanzado se dice con la palabra, no con ámbar.
5. ~~Cada bloque DEBE llevar su definición corta.~~ *Enmendado el 2026-11-27:* las definiciones DEBEN estar en un solo bloque plegado, «Cómo se cuenta» (13.4).
6. La página DEBE tener sus cinco estados: cargando (del tamaño final), vacío, error con reintento, parcial e ideal.
7. WHEN se imprime THEN DEBE salir solo la sección de conversaciones del cliente elegido con su encabezado (cliente, periodo, zona horaria y fecha de generación), sin navegación, filtros ni nada del dinero del partner (D21), en tema claro y con los colores de las gráficas.
8. La página DEBE cumplir WCAG 2.2 AA y funcionar de 360 px a escritorio.

### Requisito 9 — Rendimiento del agente con la misma regla

**Historia de usuario:** Como partner, quiero que Rendimiento del agente y el informe digan lo mismo.

#### Criterios de aceptación

1. Rendimiento del agente DEBE contar conversaciones con los ciclos del requisito 2 y «pasadas a una persona» con la regla del requisito 3.
2. Rendimiento del agente DEBE agrupar los días en la zona del cliente.
3. La lista de conversaciones del agente DEBE dar su resultado por historial: «pasada a una persona» si alguna vez la tuvo una persona, con el motivo de su último escalado o, si no hubo, «la tomó una persona».

### Requisito 10 — Cada partner ve solo lo suyo

**Historia de usuario:** Como Auphere, quiero que el informe de un cliente no enseñe nada de otro.

#### Criterios de aceptación

1. IF un partner pide el informe de un cliente de otro partner THEN la API DEBE contestar el mismo 404 que para un cliente que no existe.
2. El informe de un cliente NO DEBE contar nada de otro cliente, aunque los dos sean del mismo partner.
3. La lectura NO DEBE aceptar un identificador de tenant ni de partner, y su respuesta NO DEBE llevar ninguno.
4. La respuesta NO DEBE llevar cuerpos de mensaje, nombres ni teléfonos de clientes finales, ni el texto libre de un escalado.

### Requisito 11 — Las cifras viven en Métricas *(enmienda 2026-11-27)*

**Historia de usuario:** Como partner, quiero las cifras de conversaciones de un cliente junto a su consumo, en una sola pantalla, para decidir con números.

#### Criterios de aceptación

1. La pantalla de partner `/usage` DEBE llamarse «Métricas» en la navegación, en su título, en el buscador, en la paleta y en la app de escritorio (D16).
2. WHEN el partner tiene `conversations:read` y `usage:read` y hay un cliente elegido THEN la pantalla DEBE enseñar la sección «Conversaciones» de ese cliente, con el periodo de la pantalla.
3. IF el partner no tiene `conversations:read` THEN la sección «Conversaciones» NO DEBE existir (D17).
4. WHEN no hay un cliente elegido THEN la sección DEBE pedir que se elija uno y NO DEBE enseñar cifras (D18).
5. El cliente y el periodo (7, 30 o 90 días) DEBEN ser un solo filtro para toda la pantalla, encima de todas las secciones, y DEBEN viajar en la dirección (`?client=&days=`).
6. El periodo DEBE ser los últimos N días hasta hoy en la zona del cliente; el anterior, los N días justo antes (D19).
7. La ficha del cliente NO DEBE tener la pestaña «Informe» (D22).
8. WHEN se abre `/clients/{ref}/report` THEN el sistema DEBE llevar a `/usage?client={ref}`.

### Requisito 12 — Frente al periodo anterior *(enmienda 2026-11-27)*

**Historia de usuario:** Como partner, quiero ver si cada cifra mejora o empeora, para saber dónde actuar.

#### Criterios de aceptación

1. Cada cifra de arriba DEBE llevar su diferencia frente al periodo anterior: en porcentaje para los recuentos, en puntos para los porcentajes y en segundos para los tiempos.
2. IF el periodo anterior no tiene conversaciones, o la cifra no existe en uno de los dos, THEN esa diferencia NO DEBE darse.
3. IF la lectura del periodo anterior falla THEN las cifras DEBEN salir sin diferencia y la sección DEBE decir que no se pudo comparar (estado parcial).
4. La diferencia DEBE decirse con su signo y su número, sin rojo ni verde: si es buena o mala lo dice el objetivo con palabras (8.4).

### Requisito 13 — Desgloses para actuar *(enmienda 2026-11-27)*

**Historia de usuario:** Como partner, quiero ver cuándo y por qué el agente necesita a una persona, para cubrir esas horas o corregir el agente.

#### Criterios de aceptación

1. La API DEBE dar las conversaciones del periodo por hora local del primer mensaje del contacto (24 filas) y por día de la semana (7 filas, del lunes al domingo), cada fila partida en sin persona y con persona (D23).
2. La sección DEBE enseñar las conversaciones por hora del día y por día de la semana.
3. La sección DEBE enseñar las incidencias por motivo, cada una con su parte del total y su diferencia frente al periodo anterior.
4. La sección NO DEBE enseñar la lista de incidencias recientes ni definiciones en párrafo bajo cada bloque. Las definiciones DEBEN estar en un solo bloque plegado, «Cómo se cuenta» (D20).

### Entidades clave

- **Conversación (ciclo)**: el tramo de una fila de `conversations` entre su apertura (o reapertura por el contacto o un aviso) y su resolución. Se cuenta si el contacto escribió en él.
- **Señal de persona**: un escalado, un takeover (tres vías) o un freno dentro de un ciclo.
- **Incidencia**: un escalado o un freno que no pasó la conversación, con su motivo como código y si se resolvió.
- **Operación de agenda**: una creación, un cambio o una cancelación de una reserva, con su autor.
- **Recordatorio**: un aviso de Reservas (recordatorio o petición de confirmación) con su resultado.

## Criterios de éxito *(obligatorio)*

- **CE-001**: con la siembra de las pruebas, el informe da exactamente las cifras que la siembra fija en cada bloque.
- **CE-002**: un ciclo tomado y devuelto nunca cuenta como resuelto sin persona, ni en el informe ni en Rendimiento.
- **CE-003**: un mensaje a las 23:30 hora local cuenta en su día local en el informe y en Rendimiento.
- **CE-004**: el informe impreso de un periodo de 30 días cabe en dos páginas A4 o menos, sin navegación ni filtros.
- **CE-005**: la prueba de alcance de la consola cubre la ruta nueva sin tocarla, y una prueba propia demuestra que no se cruzan clientes ni partners.
- **CE-006**: el informe de 92 días de un cliente con 2 000 conversaciones contesta en menos de 2 s en local.

## Fuera de alcance

- **El Panel del cliente** (`client_overview.month_conversations`) sigue con su regla de hoy: cuenta filas y mira el estado actual. Pasarlo a ciclos e historial es otra spec; mientras, su cifra puede diferir de la del informe.
- **Arreglar la autoría de las cancelaciones del agente**: es de la spec 080. El informe lee bien los datos de antes y de después (D11).
- **Exportar a CSV o a PDF desde el servidor.** La vista imprimible basta (decisión de Luis).
- **Comparar con otros clientes, o sumar todos los clientes de un partner.** Comparar con el periodo anterior sí entra desde la enmienda del 2026-11-27 (requisito 12).
- **Medir la entrega en el teléfono del cliente** de un recordatorio: «enviado» es que el canal lo aceptó.
- **Detectar citas cerradas fuera de la agenda.** El freno es la aproximación; detectar lo demás necesitaría leer conversaciones.

## Supuestos

- `conversation_events` registra toda resolución y reapertura desde la Bandeja (spec 030) y el cierre por inactividad (spec 064).
- La zona horaria del cliente es `tenants.timezone`, la que ya usan sus horarios y su agenda.
- El freno de reservas deja su línea de auditoría `agent.booking_brake` en cada turno de canal en que actúa (spec 056).
- El objetivo del 70 % sin persona y el del 95 % en un minuto son los del piloto de Jemma y valen como referencia para cualquier cliente.
