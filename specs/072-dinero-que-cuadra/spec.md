# Especificación: Dinero que cuadra

**Rama**: `072-dinero-que-cuadra` · **Creada**: 2026-11-21 · **Estado**: Borrador, pendiente de las decisiones del owner (P1–P4) y de la revisión de Luis

**Entrada**: el owner pidió escribir la spec del lote 4 del roadmap de la consola (`[[nexus/UX-CONSOLA-PARTNERS-2026-11-20]]`) mientras avanza el lote 3: «Escribe la spec 072 del lote 4 mientra siguen el lote 3 avanza». El lote dice:
- Consumo con el gráfico primero;
- Meta como una cifra más;
- barras que se llenan con lo que queda;
- USD en todas partes.

El estudio lo resume en una frase: cada cifra dice su periodo y quién la paga, y las barras se llenan con lo que queda, como dice su texto.

**Depende de la spec 071** (lote 3, `071-lo-que-te-necesita`). Esta spec se programa **encima de la 071 ya fusionada**, porque las dos tocan Consumo y el Panel. De la 071 se toman, sin repetirlos aquí:
- la regla única (`GET /console/attention`) y sus códigos (`low_balance`, `account_low`, `build_cap_warning`…);
- los avisos de dinero al final de Consumo;
- «Saldo bajo» en la tabla de clientes;
- la línea del tope de construcción en el Panel a partir del 80 %.

## Encabezado Auphere *(obligatorio)*

| Campo | Valor |
|---|---|
| **Superficie de confianza** | `0`: la consola de partners y la API de la consola, que ya existen. No se abre ninguna superficie. |
| **Garantías de aislamiento tocadas** | **Ninguna nueva.** El único cambio de servidor es qué partes entran en el gasto del mes del Panel (§3), y sale de las mismas lecturas del partner que pregunta. No hay lecturas nuevas de otro partner ni de otro cliente. |
| **Nota de KB que la justifica** | `[[nexus/UX-CONSOLA-PARTNERS-2026-11-20]]`, lote 4. Hallazgos del recorrido de staging del 2026-11-20: P01 (el gasto que no cuadra), C01 (la barra al revés), U01 (el tope escondido), K02 (USD y US$), e3-03 (Asignar saldo), e6-01 (Consumo). |
| **Qué se mide** | **Nada nuevo.** No llama a modelos ni a herramientas de pago. |

## Qué hay hoy (2026-11-21, `develop` en d4a605c6)

### 1. El dinero se escribe de dos maneras

Hay dos formateadores, y cada pantalla usa uno:
- `@nexus/ui` `formatMoney` (`packages/ui/src/components/money.tsx`, spec 047 R45.9): `es-ES` fijo y el código detrás. Escribe «60,00 USD».
- `lib/amount.ts` `formatAmount` (spec 056, requisito 13, D9): Intl en el idioma de la persona. Escribe «10,00 US$» en español y «$10.00» en inglés. `lib/money.ts` (el saldo del partner) delega aquí.

Por eso Facturación enseña «49,68 USD» y «20,00 US$» en la misma página, y Auditoría «10,00 US$» (hallazgo K02).

### 2. Las barras de saldo se llenan con lo gastado

- **Clientes** (`clients-list-v2.tsx`, `bagBar` en `client-v2-model.ts`): la barra se llena con `pct_spent`, y se pone ámbar al 80 % gastado. Lo que dice su texto, en cambio, es lo que queda. En staging: «Quedan 23,91 de 28,12» (85 %) junto a una barra llena al 15 %. De un vistazo se lee «casi vacía» cuando está casi llena (C01).
- **Ficha del cliente, Panel** (`client-panel.tsx`): una barra apilada por agente con lo consumido sobre lo asignado, y el texto «Consumido 4,21 de 28,12 · 15 %».
- **El tono no sale de la regla.** La API ya manda `state: "low"` en la bolsa. `bagBar` lo ignora y calcula su propio umbral, sin los 7 días. Una bolsa puede salir «Saldo bajo» en la lista de avisos de la 071 y verde en su barra.
- **Panel, «Saldo disponible»** (`partner-panel.tsx`): debajo de la cifra de lo disponible, la barra pinta lo que está **en bolsas**.

### 3. El gasto del mes del Panel no cuadra

`HomeSpend.shares` (`schemas_home_usage.py`, `kind: client | rest | line`) mete partidas que no paga el partner: «Construcción y pruebas» (la paga Auphere hasta el tope) y «Mensajes de Meta» (el negocio a Meta).

En staging el gasto del mes era 4,21 USD, y sus partes eran «Meta Review 100 % 4,21» y «Construcción y pruebas 100 % 52,09». Eso da dos 100 %, y una parte mayor que el total. Además, los nombres salen cortados: «Meta Revi…», «Construc…» (P01).

La 071 añade la línea del tope **solo a partir del 80 %**, pero no saca la construcción de las partes.

### 4. Consumo pone el gráfico tercero y reparte quién paga en tarjetas

El orden de `usage-v2.tsx` es:
1. tres cifras;
2. la tabla de clientes;
3. «Gasto por día»;
4. las partidas en tarjetas, con quién paga cada una (`usage-lines.tsx`);
5. el detalle técnico.

Lo que falla:
- «Gasto por día» es el `BlockChart` de `@nexus/ui`: una rejilla de celdas apiladas. Lleva tres filtros: el periodo, un desplegable de cliente y otro de partida.
- Las tres cifras de gasto visibles usan ventanas distintas y no lo dicen junto a la cifra: el mes en la tarjeta, 30 días en el gráfico y el mes de construcción en su tarjeta.
- «En bolsas de clientes» dice en su nota «49,68 USD sin asignar», y la cifra de al lado ya dice 49,68 disponible.
- «Mensajes de Meta» es una tarjeta más abajo, con «≈».

El mismo `BlockChart` pinta «Conversaciones por día» en el Panel, con un eje de 0 a 2 que enseña 0,5 y 1,5 conversaciones.

### 5. Asignar saldo y Comprar saldo eligen el importe distinto

Según el recorrido del 2026-11-20:
- **Asignar saldo** (`components/money/assign-dialog.tsx`):
  - abre con esqueleto y cambia de alto;
  - «Asignas» y «Sale de tu cuenta» repiten la misma cifra;
  - «Rellenar cada mes hasta…» lleva puntos suspensivos sin explicar.
- **Comprar saldo** (`components/billing/buy-credit-form.tsx`): los importes rápidos no se quedan elegidos. No se sabe si un clic compra o elige, y «Comprar» sigue apagado.

## La propuesta

**Cada cifra dice qué cuenta, de cuándo es y quién la paga. Cada barra se llena con lo que dice su texto.**

- **Un solo formato de dinero** para toda la consola, con el código «USD» y nunca «US$» (P1).
- **Barras con lo que queda**:
  - la barra de una bolsa se llena con lo que queda;
  - su texto dice cuánto queda y cuántos días dura a este ritmo;
  - su ámbar sale de la regla de la 071, no de un umbral propio.
- **El gasto del mes cuenta lo que paga el partner**:
  - las partes son sus clientes (y lo de su cuenta, P2), suman 100 % y llevan los nombres enteros;
  - Construcción sale de las partes y queda siempre en una línea propia, «la paga Auphere hasta el tope»;
  - Meta tampoco entra en las partes.
- **Consumo, de arriba abajo**:
  1. el gráfico de gasto por día;
  2. cuatro cifras en una fila, con Meta como una más;
  3. la tabla de clientes;
  4. los avisos de dinero (los de la 071);
  5. el detalle plegado.

  Las tarjetas de «quién paga qué» desaparecen. Cada cifra ya lo dice, y el tope vive en su línea y en su aviso.
- **Barras macizas**: un día es una barra, el eje va en pasos enteros y hoy se marca. Vale para los dos gráficos, Consumo y Panel.
- **Elegir un importe igual en todas partes**:
  - primero se elige el importe y queda marcado;
  - el botón dice lo que hace («Asignar 20,00 USD», «Comprar 50,00 USD»);
  - el recibo pone una línea por dato.

## Requisitos

### 1. Un solo formato de dinero

1.1 Toda la consola formatea el dinero con **una sola función**:
- `lib/amount.ts` y `@nexus/ui` `formatMoney` / `<Money>` dan el mismo texto para el mismo importe;
- una de las dos delega en la otra.

1.2 El dólar se escribe con su código, **«USD»**, nunca «US$» ni «$». El euro sigue con «€». Cómo queda en inglés, según P1.

1.3 Las monedas sin símbolo propio (CLP, COP…) no cambian: siguen con su código.

1.4 Un barrido de tests recorre las pantallas de dinero (Panel, Clientes, ficha, Consumo, Facturación, Asignar saldo, Auditoría) y falla si aparece «US$».

### 2. Barras con lo que queda

2.1 La barra de una bolsa se llena con **lo que queda**:
- su ancho es lo que queda sobre lo asignado: `pct_left` en la ficha y en Clientes, y en Consumo, que no lo trae, lo restante sobre la bolsa;
- su texto empieza por lo que queda: «23,91 USD · quedan de 28,12 USD»;
- vale en la lista de Clientes, en la ficha del cliente y en la tabla de Consumo.

2.2 Debajo de la barra, una línea dice cuánto dura a este ritmo: «Unos 79 días a este ritmo», con `days_left` redondeado.
- Sin datos para estimarlo, la línea dice qué falta: «Aún no hay gasto para calcular cuánto dura».
- No se usa un «Aún no hay datos para estimarlo» que no dice qué se estima.

2.3 El tono de la barra viene de la regla, no de un umbral propio:
- **ámbar**, con `state: "low"` (el mismo criterio que `low_balance` de la 071: menos del 20 % o menos de 7 días). Su línea dice «Unos 2 días»;
- **rojo**, con «Sin saldo».

El ámbar va solo en la barra, el icono y el texto, nunca de relleno de fila (reglas visuales del owner, 2026-11-20).

2.4 La ficha del cliente:
- lleva la barra de lo que queda (2.1);
- el reparto por agente se queda en su lista con barras de ranking, como hoy;
- la barra apilada por agente desaparece del bloque de saldo.

2.5 En el Panel, la barra bajo «Saldo disponible» se llena con lo disponible y no con lo que está en bolsas. Su nota sigue diciendo cuánto está en bolsas.

2.6 Las barras tienen nombre accesible con el mismo texto que se ve: lo que queda, de cuánto y los días.

### 3. El gasto del mes del Panel

3.1 `HomeSpend.shares` (bloque `panel` de `/console/home`) solo lleva lo que paga el partner:
- las bolsas de sus clientes;
- y, según P2, lo de su cuenta (Companion y teammates).

Ni `build` ni `meta` entran en las partes.

3.2 Las partes suman el total y sus porcentajes suman 100 %. Un test lo comprueba con los datos de staging del estudio: 4,21 USD y una sola parte.

3.3 Los nombres de cliente salen enteros:
- pasan de línea si hace falta;
- si no caben, se cortan con su nombre completo en `title` y en el nombre accesible;
- ninguna parte se queda en «Construc…».

3.4 Construcción y pruebas va en una línea propia bajo las partes, **siempre**: «Construcción y pruebas: 12,40 de 62,00 USD · la paga Auphere hasta el tope».
- Por debajo del 80 % es neutra.
- Desde el 80 % es la línea de la 071 (4.3), con su barra en ámbar y «Pedir ampliación».

3.5 La cifra dice su periodo: «Gasto del mes · 1–21 nov». Ya existe `panel-period`, y se mantiene.

### 4. Consumo

4.1 **El orden de la página** es:
1. «Gasto por día»;
2. las cuatro cifras;
3. la tabla de clientes;
4. «Avisos» (071, 5.1);
5. el detalle técnico plegado, con «Descargar CSV».

4.2 **«Gasto por día»**:
- el periodo, 7, 30 o 90 días, en la cápsula de vidrio (`SegmentedControl`, ya existe);
- el filtro de cliente al lado;
- la partida, según P3.

Los filtros siguen siendo la URL. El título dice su ventana: «Gasto por día · últimos 30 días».

4.3 **Las cuatro cifras**, en una fila en escritorio y dos por fila en el teléfono:
- **Saldo disponible**: lo que se puede asignar;
- **En bolsas de clientes**: su nota dice cuántos clientes tienen bolsa, no lo disponible otra vez;
- **Gasto del mes**: lo que paga el partner, con su periodo y la proyección al ritmo de 7 días, como hoy;
- **Mensajes de Meta**: con la marca de Meta y la cifra sin «≈». Su nota dice que es una estimación que el negocio paga a Meta, aparte del saldo.

4.4 **Las tarjetas de partidas desaparecen** (`usage-lines.tsx`):
- el tope de construcción vive en la línea del Panel (3.4) y en el aviso de Consumo (071);
- Meta vive en su cifra (4.3);
- Companion, según P2.

Antes de borrar `UsageLines`, «Pedir ampliación» (`requestBuildExtensionAction`) tiene que seguir disponible desde la línea del Panel y desde el aviso.

4.5 Si la lectura de una cifra falla, esa cifra lo dice y no pinta un cero. Es la regla 46.7 de hoy y no cambia.

### 5. Barras macizas

5.1 El gráfico de Consumo y «Conversaciones por día» del Panel pintan **una barra maciza por día**, en lugar de la rejilla de celdas. `BlockChart` (`packages/ui/src/components/block-chart.tsx`) solo lo usa la consola, así que cambiarlo no toca el Admin.

5.2 El eje va en pasos enteros de su unidad:
- conversaciones enteras, nunca 0,5 ni 1,5;
- dinero en pasos redondos («0 · 5 · 10 USD»).

5.3 Hoy se marca con un borde, y su barra dice «hoy» en el nombre accesible.

5.4 Las barras crecen al entrar. Con «Reducir movimiento» salen quietas.

5.5 La tabla para lectores de pantalla que ya existe se mantiene.

### 6. Elegir un importe

6.1 Asignar saldo y Comprar saldo eligen el importe igual:
- los importes rápidos se eligen, y el elegido queda marcado con un tinte, no con un segundo botón principal;
- el campo libre sigue disponible;
- el botón dice el importe: «Asignar 20,00 USD», «Comprar 50,00 USD».

6.2 Sin importe, o sin saldo suficiente, el botón sigue apagado y una línea dice por qué: «Te quedan 12,00 USD en tu cuenta».

6.3 El recibo de Asignar saldo pone una línea por dato:
- su saldo ahora;
- asignas;
- su nuevo saldo;
- te queda en el tuyo.

Ninguna cifra sale repetida con otro nombre.

6.4 El diálogo de Asignar saldo tiene su alto final desde el primer fotograma. El esqueleto ocupa lo mismo que el contenido.

6.5 «Rellenar cada mes hasta…» pasa a un interruptor que dice el importe: «Rellenar cada mes hasta 28,12 USD».

### 7. Comprobación

7.1 Los tests de unidad cubren:
- el formateador único (1.1–1.3);
- `bagBar`, con lo que queda y el tono desde `state` (2.1, 2.3);
- las partes del gasto (3.1, 3.2).

7.2 El e2e del marco (`e2e/shell.spec.ts`) sigue verde. Se añade un e2e de Consumo con axe (serious/critical) sobre la página entera, en claro y en oscuro.

7.3 Se comprueba en staging, contra el recorrido del estudio, antes de pasar al lote 5.

## Preguntas para el owner

- **P1 · Cómo se escribe el dólar en inglés.** En español es «10,00 USD». En inglés hay dos opciones:
  - «USD 10.00», el formato de Intl con código;
  - «10.00 USD», que se lee igual que en español.

  **Propuesta:** «USD 10.00». Es lo que da el idioma y no hay que forzarlo.

  Esta decisión cambia la D9 de la 056, que había elegido «US$» con Intl.
- **P2 · Companion y teammates en el gasto del mes.** Lo paga la cuenta del partner, así que es dinero suyo.
  - **Propuesta:** que entre como una parte más, «Tu cuenta (Companion)», para que el gasto del mes sea todo lo que sale de su dinero.
  - La otra opción es dejarlo solo en el detalle de Consumo.
- **P3 · El filtro de partida en «Gasto por día».** La demo aprobada solo lleva el periodo y el cliente.
  - **Propuesta:** quitar el desplegable de partida. Con Meta y Construcción fuera del gasto, la partida casi siempre es «Conversaciones».
  - Lo que quede por partida se ve en el detalle plegado.
- **P4 · Construcción por debajo del 80 % en Consumo.**
  - **Propuesta:** solo en la línea del Panel (3.4). En Consumo aparece cuando hay aviso, como en la demo.
  - La otra opción es poner también una línea neutra bajo las cuatro cifras.

## Fuera de alcance

- La regla, los avisos y la campana: son de la spec 071.
- La app móvil: tiene sus propias barras y su propia spec (069).
- Clientes en el teléfono: hoy esconde el saldo y el menú ⋯. Es del lote 6 (cierre).
- La tipografía y la escala (Helvena 400–600): son de la spec 068 (base visual).
- Cambiar umbrales de saldo bajo o del tope.
