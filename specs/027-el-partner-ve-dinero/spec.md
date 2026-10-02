# Especificación: el partner ve, asigna y gasta dinero

**Rama**: `develop` (decisión del owner, sin rama de feature) · **Creada**: 2026-10-02 · **Estado**: Borrador

**Entrada**: decisión del owner del 2026-10-02: «el cliente (partner o usuario) no medirá el dinero en tokens sino en consumo, lo que se consume será el dinero y el partner le asignará dinero, no consumo. Internamente nosotros sí necesitamos medir cuánto consumo es esa cantidad de dinero».

## Encabezado Auphere *(obligatorio)*

| Campo | Valor |
|---|---|
| **Superficie de confianza** | `0`. Cambia la unidad en que el partner lee y escribe cifras que la plataforma ya guarda. No entra nada nuevo de fuera |
| **Garantías de aislamiento tocadas** | Ninguna nueva. Saldo, reparto y gasto siguen siendo del partner de la sesión |
| **Nota de KB que la justifica** | Decisión del owner 2026-10-02 · `[[AUDITORIA-UX-CONSOLA-2026-09-22]]` §Consumo («una unidad visible con equivalencia en USD») |
| **Qué se mide** | Nada nuevo. El libro sigue en créditos. Cambia cómo se presenta y cómo se pide |

## Origen

Hoy la consola habla en «créditos», una unidad interna de consumo: un dólar son
100.000 créditos. El partner ve «Crédito 50.000», «Quedan 31.400 de 50.000
créditos», «Compra 5.000.000 unidades de consumo» o «Créditos a mover», y
tiene que traducir de cabeza cuánto dinero es eso. Al Companion se le dice
literalmente «son tokens de cuota, nunca euros».

Un partner es una agencia que revende agentes. Piensa en dinero: cuánto le
queda, cuánto le da a cada cliente, cuánto se ha gastado. El crédito es un
detalle de Auphere.

Medido en el código el 2026-10-02:

1. Ya está en dinero: la compra de crédito (importe en dólares), la membresía,
   los recibos y el «Gasto del mes» del Inicio.
2. Está en créditos y lo ve el partner: el saldo de Consumo (incluido, comprado,
   reserva), la tabla de reparto (tope y restante), el formulario de tope, el
   diálogo de mover, el «Crédito disponible» del Inicio, la ficha del cliente
   (paso de crédito, medidor, gastado), la columna de crédito de la lista de
   clientes, la confirmación de compra («Compra N unidades»), el Companion
   (leer saldo, proponer tope) y el aviso de cliente sin crédito.
3. Las entradas del partner (tope, cantidad a mover) solo aceptan enteros de
   créditos.
4. La tasa de conversión está escrita dos veces: en el servidor y copiada en la
   consola. Hay dos conversiones sueltas en el servidor, una en cada sentido.
5. Hay un error que ya existe: la ficha dice «acabará el mes en N créditos» con
   una proyección que en realidad son mensajes de canal.

## Clarifications

### Session 2026-10-02

- Q: ¿Dónde se trabaja? → A: En `develop`, como la spec 026 (owner: «seguiremos trabajando en develop»).
- Q: ¿El saldo incluido de la membresía también pasa a dinero, aunque la spec 005 prohíbe publicar el tamaño absoluto de la bolsa? → A: **Sí, todo en dinero.** Se levanta esa prohibición para la pantalla de Consumo y el Inicio. La pantalla de planes sigue describiendo los niveles por su múltiplo de consumo (spec 005 R1.8), que no es objeto de esta spec.
- Q: ¿En qué moneda? → A: **Dólares (US$) para todos los partners**, como la compra de saldo, la membresía y los recibos. Sin tipo de cambio.

## Escenarios de usuario y pruebas *(obligatorio)*

### Historia 1 — Mi saldo, en dinero (Prioridad: P1)

Como partner, quiero ver cuánto dinero tengo para gastar, para saber si me
alcanza sin hacer cuentas.

**Por qué esta prioridad**: es la primera cifra que se mira y hoy no se entiende.

**Prueba independiente**: con un saldo conocido, Consumo y el Inicio enseñan el
mismo importe en dólares con dos decimales, y ninguna pantalla del partner dice
«créditos», «unidades», «tokens» ni «cupo» al hablar del saldo.

**Escenarios de aceptación**:

1. **Dado** un partner con saldo comprado de 1.234.567 créditos, **cuando** abre
   Consumo, **entonces** lee «12,35 US$» comprados.
2. **Dado** el mismo partner, **cuando** abre el Inicio, **entonces** «Crédito
   disponible» muestra el disponible en dólares y coincide con Consumo.
3. **Dado** un partner con saldo cero, **cuando** abre Consumo, **entonces** lee
   «0,00 US$» y el aviso de saldo agotado, sin cifras en créditos.

---

### Historia 2 — Asignar dinero a un cliente (Prioridad: P1)

Como partner, quiero decidir cuánto dinero puede gastar cada cliente, para
controlar mi margen con cada uno.

**Por qué esta prioridad**: es la acción que el partner hace cada mes con cada
cliente.

**Prueba independiente**: fijar un tope de 25,50 US$ a un cliente deja ese
cliente con 2.550.000 créditos de tope internos y la pantalla vuelve a enseñar
25,50 US$.

**Escenarios de aceptación**:

1. **Dado** un cliente sin tope, **cuando** el partner escribe «25,50» y guarda,
   **entonces** el tope queda en 25,50 US$ y el libro interno guarda el
   equivalente exacto en créditos.
2. **Dado** un importe con más de dos decimales o negativo, **cuando** intenta
   guardarlo, **entonces** la pantalla lo rechaza y dice el formato válido.
3. **Dado** un tope que superaría el saldo del partner, **cuando** intenta
   guardarlo, **entonces** se rechaza diciendo en dólares cuánto puede asignar
   como máximo.
4. **Dado** la tabla de reparto, **cuando** la mira, **entonces** cada cliente
   enseña tope y restante en dólares.

---

### Historia 3 — Mover dinero entre clientes (Prioridad: P2)

Como partner, quiero pasar dinero del tope de un cliente a otro, para atender
al que se está quedando sin saldo sin comprar más.

**Prueba independiente**: mover 10,00 US$ de A a B baja el tope de A y sube el
de B exactamente 10,00 US$ cada uno.

**Escenarios de aceptación**:

1. **Dado** A con tope de 30,00 US$, **cuando** mueve 10,00 US$ a B,
   **entonces** A queda en 20,00 US$, B sube 10,00 US$ y la confirmación lo dice
   en dólares.
2. **Dado** A con 5,00 US$ de tope, **cuando** intenta mover 8,00 US$,
   **entonces** se rechaza diciendo «A solo tiene 5,00 US$ de tope».

---

### Historia 4 — Cuánto ha gastado cada cliente (Prioridad: P2)

Como partner, quiero ver en la ficha y en la lista de clientes cuánto dinero
ha gastado y le queda a cada cliente, para cobrarle o avisarle.

**Prueba independiente**: un cliente con tope 50,00 US$ y 18,60 US$ gastados
enseña «Quedan 31,40 US$ de 50,00 US$» en la ficha y en la lista.

**Escenarios de aceptación**:

1. **Dado** un cliente con tope y gasto, **cuando** se abre su ficha,
   **entonces** el paso de crédito, el medidor y «gastado» están en dólares.
2. **Dado** la ficha, **cuando** muestra una proyección, **entonces** es una
   proyección de gasto en dólares o no aparece. Nunca una proyección de mensajes
   con la palabra «créditos».
3. **Dado** la lista de clientes, **cuando** se mira la columna de crédito,
   **entonces** está en dólares.

---

### Historia 5 — Comprar dinero, no unidades (Prioridad: P2)

Como partner, quiero comprar saldo diciendo cuánto dinero pago y ver que ese
dinero es lo que recibo.

**Prueba independiente**: comprar 50 US$ confirma «Recibirás 50,00 US$ de saldo»
y no menciona unidades.

---

### Historia 6 — El Companion habla en dinero (Prioridad: P3)

Como partner, quiero preguntarle al Companion cuánto me queda o pedirle que
suba el tope de un cliente en dólares.

**Prueba independiente**: «¿cuánto saldo me queda?» responde en dólares, y
«sube el tope de Flor y Encanto a 40 dólares» propone 40,00 US$ y, aprobado,
deja el tope en 40,00 US$.

---

### Historia 7 — Auphere sigue midiendo en créditos (Prioridad: P1)

Como Auphere, quiero que el libro, el débito por turno y los pesos por modelo
sigan en créditos, y saber para cualquier importe cuántos créditos son y para
cualquier consumo cuánto dinero es, con una sola tasa.

**Prueba independiente**: una tabla de importes y créditos pasa por la
conversión en ambos sentidos y da siempre el mismo resultado en el servidor,
en la consola y en el Companion.

### Casos límite

- Un restante en créditos que no es múltiplo de un céntimo (1 céntimo = 1.000
  créditos): se enseña redondeado al céntimo, y la regla de redondeo es la misma
  en todas las pantallas.
- Un restante de menos de medio céntimo pero mayor que cero: se enseña
  «0,00 US$» y el cliente sigue pudiendo atender hasta llegar a cero. Que el
  cliente atienda con «0,00 US$» a la vista no puede contradecir el aviso de
  «sin crédito», que solo sale al llegar a cero real.
- Un tope escrito con coma o con punto decimal («25,5» o «25.5»): ambos valen.
- Un importe enorme (por encima del saldo del partner) se rechaza con el máximo
  asignable en dólares.
- Si Auphere cambia algún día la tasa, los topes ya asignados en créditos no
  cambian. Lo que cambia es su equivalente en dólares, y eso se decide fuera de
  esta spec.
- El saldo incluido de la membresía se enseña en dólares, como el comprado. La
  regla de la spec 005 que lo escondía queda levantada para Consumo y el
  Inicio (clarificación del 2026-10-02).
- Todo importe está en dólares, sea cual sea el país del partner.

## Requisitos *(obligatorio)*

### Requisito 1 — Una sola tasa, una sola conversión

1. El sistema DEBE tener una única tasa entre dinero y créditos y una única
   conversión en cada sentido, en el servidor. La consola y el Companion NO
   DEBEN tener la tasa escrita.
2. De dinero a créditos la conversión DEBE ser exacta para cualquier importe con
   dos decimales.
3. De créditos a dinero el resultado DEBE redondearse al céntimo con una sola
   regla, la misma en todas las respuestas.
4. Toda cifra de saldo, tope, restante, gastado o disponible que el servidor
   entrega al partner DEBE ir en dinero, con la moneda indicada.

### Requisito 2 — Lo que el partner ve

1. Consumo, el Inicio, la ficha y la lista de clientes, el reparto, mover
   saldo, comprar saldo y los avisos de cliente sin saldo DEBEN enseñar
   importes en dinero.
2. Ningún texto del partner DEBE decir «créditos», «unidades de consumo»,
   «tokens de cuota» ni «cupo» para referirse al saldo. La palabra de interfaz
   es «saldo» para lo que tiene el partner y «tope» para lo que asigna a un
   cliente.
3. La proyección de la ficha DEBE ser de gasto en dinero o no aparecer.

### Requisito 3 — Lo que el partner escribe

1. Tope por cliente y cantidad a mover DEBEN aceptarse en dinero con hasta dos
   decimales, con coma o punto.
2. Los errores de validación DEBEN decir el límite en dinero («puedes asignar
   como máximo 120,00 US$», «A solo tiene 5,00 US$ de tope»).
3. El servidor DEBE convertir a créditos y guardar en créditos. La API NO DEBE
   aceptar créditos del partner.

### Requisito 4 — El Companion

1. Las herramientas del Companion que leen saldo o reparto DEBEN devolver
   dinero, y la que propone un tope DEBE recibirlo en dinero.
2. Sus descripciones y respuestas NO DEBEN hablar de tokens ni de cupo.
3. Los casos de evaluación del Companion que hablan de tokens DEBEN pasar a
   dinero.

### Requisito 5 — El saldo incluido

1. Consumo DEBE enseñar el saldo incluido restante en dólares, junto a su fecha
   de renovación, igual que el comprado. El porcentaje PUEDE seguir como dato
   secundario.
2. Esta spec levanta, para Consumo y el Inicio, la prohibición de la spec 005
   (R1.8) y de la spec A (R7.3) de publicar el tamaño absoluto de la bolsa. La
   pantalla de planes no cambia.

### Requisito 6 — Lo que no cambia

1. El libro, el débito por turno, los pesos por modelo, la renovación de la
   bolsa y el panel de Auphere DEBEN seguir en créditos. El panel PUEDE enseñar
   además el equivalente en dinero.
2. El tope de mensajes del mes, el presupuesto del Playground, el medidor del
   Companion y los multiplicadores de coste de los modelos NO cambian de unidad.

### Entidades clave

- **Saldo del partner**: lo que puede gastar entre todos sus clientes. Interno
  en créditos, visible en dinero.
- **Tope de un cliente**: lo que el partner le permite gastar. Interno en
  créditos, escrito y visible en dinero.
- **Tasa**: dólares por millón de créditos. Una sola, del lado de Auphere.

## Criterios de éxito *(obligatorio)*

- **CE-001**: Ninguna pantalla del partner ni respuesta del Companion sobre
  saldo, topes o gasto contiene las palabras «créditos», «unidades», «tokens» o
  «cupo».
- **CE-002**: Para cualquier importe con dos decimales, asignarlo como tope y
  volver a leerlo devuelve exactamente el mismo importe.
- **CE-003**: El mismo saldo se lee igual, al céntimo, en Consumo, en el Inicio y
  en el Companion.
- **CE-004**: Un partner fija el tope de un cliente en dólares en menos de
  30 segundos sin consultar ninguna ayuda.
- **CE-005**: La tasa aparece en un solo sitio del código.

## Fuera de alcance

- El tope de mensajes del mes y sus avisos: son mensajes de canal.
- El presupuesto del Playground: son tokens del modelo.
- Cambiar la tasa o el precio de la membresía.
- Facturar a los clientes del partner: el partner sigue cobrando a sus clientes
  por su cuenta.

## Supuestos

- La tasa vigente es la de la compra de crédito: 10 US$ por millón de créditos.
- La moneda es el dólar para todos los partners (clarificación).
- El dinero que el partner asigna es el que paga a Auphere, sin margen del
  partner encima.
- Auphere sigue recargando y viendo saldos en créditos en su panel.
