# Especificación: Liquid Glass en la app, y lo que la auditoría encontró

**Rama**: `042-liquid-glass-en-la-app` · **Creada**: 2026-10-20 · **Estado**: Borrador

**Entrada**: descripción del usuario: "Rediseño Liquid Glass de la app móvil
Auphere Customers (apps/mobile, Expo SDK 58). Parte de la auditoría de la KB
research/2026-10-20-liquid-glass-app-movil.md y de la dirección escrita en
apps/mobile/AGENTS.md («Dirección de diseño: Liquid Glass, con exigencia»). En
iOS 26 la capa de navegación y controles adopta Liquid Glass (primero el del
sistema; expo-glass-effect solo donde el sistema no llega); el contenido sigue
opaco; respaldo idéntico a hoy antes de iOS 26; Android en Material 3 Expressive
sin imitar el vidrio; accesibilidad (Reducir transparencia, Aumentar contraste,
Reducir movimiento, texto grande). Incluye corregir los hallazgos H1–H12 de la
auditoría (Inicio repetido, dinero duplicado entre Inicio y Consumo, rejillas de
tarjetas, panel de Tomar el control opaco, tres formas de navegar, formas de la
web, Ajustes, jerarquía al 200 %, escala tipográfica, textos). Concreta la D24
de la spec 031 sin sustituirla."

## Encabezado Auphere *(obligatorio)*

| Campo | Valor |
|---|---|
| **Superficie de confianza** | `0`, la API de la consola, sin cambios. Es un cambio de presentación de la app de la spec 031: no lee nada nuevo, no envía nada nuevo y no abre ningún camino. |
| **Garantías de aislamiento tocadas** | Ninguna. No cambian los datos, los permisos ni quién ve qué. |
| **Nota de KB que la justifica** | `[[research/2026-10-20-liquid-glass-app-movil]]` · `[[research/2026-10-19-consola-lite-movil]]` · `[[decisions/ADR-042-la-consola-lite-en-el-telefono]]` |
| **Qué se mide** | Nada. No hay modelo, máquina ni herramienta de pago nuevos. |

## Origen

Luis lo pidió el 2026-10-20 con dos encargos:
- la interfaz de iOS adopta Liquid Glass;
- cada pantalla se mira con exigencia de diseño y de usabilidad.

La auditoría de ese mismo día está en la KB
(`research/2026-10-20-liquid-glass-app-movil`). Se hizo sobre las capturas del
pase vivo de la 031 y sobre el código. Su veredicto:
- **La base es buena.** La estructura nativa ya está: pestañas, pila, hojas y
  los cinco estados.
- **Lo que la app dibuja por su cuenta, no.** Cabeceras de color sólido, un
  panel opaco al pie de la conversación, formas de la web y un Inicio que
  repite lo mismo.
- **Primero el contenido.** Poner vidrio sobre lo repetido sería pulir lo que
  sobra.

Al escribir esta spec apareció un hallazgo más, **H13**. La insignia del
bloque de atención de Inicio cuenta avisos, no conversaciones. Con dos
conversaciones esperando, enseña «1» al lado de «2 conversaciones esperan»
(`android-inicio-oscuro-texto-200.jpg`).

| Hallazgo | Severidad | Requisito |
|---|---|---|
| H1 · Inicio repite tres veces que alguien espera | 3 | R5.1–R5.3 |
| H2 · Inicio y Consumo duplican el dinero | 3 | R5.4 |
| H3 · Rejillas de tarjetas iguales | 2 | R5.5 |
| H4 · El panel de «Tomar el control» tapa el hilo | 2 | R2 |
| H5 · Tres maneras de ir a otro sitio | 2 | R6 |
| H6 · Formas de la web | 2 | R7.1, R7.2 |
| H7 · Ajustes junta cerrar sesión con borrar la cuenta | 2 | R8 |
| H8 · Con el texto grande, la jerarquía se invierte | 2 | R4.6 |
| H9 · Escala de texto de la consola | 1 | R7.3 |
| H10 · Consumo abre repitiendo su título | 1 | R9.1 |
| H11 · Gráfico vacío con selector de periodo | 1 | R9.2 |
| H12 · «Attend» en inglés | 1 | R9.3 |
| H13 · La insignia de atención cuenta otra cosa | 3 | R5.2 |

**Relación con la 031.** Esta spec **concreta** la D24 de la 031 (nativo
primero; la marca en el color, el contenido y la voz) para iOS 26. No la
sustituye.
- Los requisitos de la 031 siguen vigentes.
- Donde esta spec cambia cómo se enseña algo que la 031 pide, lo cita.
- El contenido de Inicio (031 R4.1) no cambia: cambia cómo se presenta.

## Escenarios de usuario y pruebas *(obligatorio)*

### Historia 1 — Atender con el hilo a la vista (Prioridad: P1)

Una persona del negocio abre una conversación que espera a una persona. A la
vez ve:
- los últimos mensajes;
- el motivo por el que el agente pidió ayuda;
- la acción «Tomar el control».

Toca «Tomar el control», el panel se convierte en el cuadro de escribir y
contesta. En iOS 26 los controles flotan en vidrio sobre el hilo, que sigue
viéndose por debajo.

**Por qué esta prioridad**:
- Atender es el trabajo principal de la app (Historia 3 de la 031).
- «Tomar el control» es la única coreografía que permite la D24.
- Hoy el panel es opaco y tapa casi una cuarta parte de la pantalla.

**Prueba independiente**: con solo esta historia hecha, se abre una
conversación en espera en iOS 26, en un iOS anterior y en Android. Se toma el
control y se envía un mensaje. Con eso queda demostrada la pieza central del
vidrio.

**Escenarios de aceptación**:

1. **Dado** una conversación que espera, en iOS 26 y con el texto al tamaño
   por defecto, **cuando** la persona la abre, **entonces**:
   - ve a la vez el último mensaje, el motivo y «Tomar el control»;
   - los controles flotan sobre el hilo, y el hilo se desplaza por debajo.
2. **Dado** ese mismo estado, **cuando** toca «Tomar el control», **entonces**
   el panel se convierte en el cuadro de escribir en una sola transición, con
   la vibración de éxito, y ya puede escribir.
3. **Dado** que «Reducir movimiento» está activo, **cuando** toma el control,
   **entonces** el cambio es un fundido, sin cambio de forma ni desplazamiento.
4. **Dado** un motivo que no cabe en dos líneas, **cuando** abre la
   conversación, **entonces**:
   - el panel enseña dos líneas;
   - el motivo se puede leer entero sin salir de la conversación.
5. **Dado** un iPhone con un iOS anterior a 26, **cuando** abre la
   conversación, **entonces** el panel y el cuadro se ven como en la versión de
   la 031.
6. **Dado** que tiene el control y el teclado abierto, **cuando** escribe,
   **entonces** el cuadro queda justo encima del teclado y el último mensaje
   sigue a la vista.

---

### Historia 2 — Inicio dice cada cosa una vez (Prioridad: P1)

La persona abre la app y en la primera pantalla sabe, sin desplazar:
- si alguien la espera, y cuántos;
- cuánto saldo le queda y para cuántos días;
- cuánto lleva gastado este mes.

Cada dato aparece una sola vez, y ningún número contradice a otro.

**Por qué esta prioridad**: es la primera pantalla. Hoy dedica casi la mitad
de lo que se ve a repetir un mismo dato. Con dos conversaciones esperando,
enseña dos números distintos para lo mismo (H1, H13).

**Prueba independiente**: se abre Inicio en tres casos y se cuentan las
apariciones de cada dato:
- con conversaciones esperando;
- sin nada pendiente;
- con el saldo bajo.

**Escenarios de aceptación**:

1. **Dado** dos conversaciones que esperan, **cuando** la persona abre Inicio,
   **entonces**:
   - ve un solo bloque de atención que dice «2» una vez, con la acción de
     atenderlas;
   - no ve otra cifra de «esperan a una persona» ni un contador de otra cosa
     al lado.
2. **Dado** que no hay nada pendiente, **cuando** abre Inicio, **entonces** ve
   una línea tranquila que lo dice, y no una cifra de espera a cero.
3. **Dado** un saldo asignado, **cuando** abre Inicio, **entonces** ve el saldo,
   los días que alcanza y el gasto del mes en un solo bloque, que lleva a
   Consumo.
4. **Dado** que hay conversaciones esperando y el saldo está bajo, **cuando**
   abre Inicio, **entonces** el bloque de atención lista las dos cosas, cada una
   con su dato una sola vez.
5. **Dado** el teléfono más pequeño que admite iOS 26, con el texto al tamaño
   por defecto, **cuando** abre Inicio, **entonces** ve lo que necesita
   atención y el bloque de dinero sin desplazar.

---

### Historia 3 — Legible siempre (Prioridad: P1)

La persona usa el teléfono como lo tiene configurado: con el texto grande, en
oscuro, con menos transparencia o con más contraste. El vidrio no le cuesta
leer nada.

**Por qué esta prioridad**:
- La crítica principal a Liquid Glass es justamente que cuesta leerlo.
- WCAG 2.2 AA es requisito de la 031 (R14.5), no un extra.

**Prueba independiente**: se recorren las pantallas con el contenido más
desfavorable pasando por debajo de las barras, en estas combinaciones:
- claro y oscuro;
- con «Reducir transparencia» y con «Aumentar contraste»;
- con el texto al máximo.

En cada una se mide el contraste.

**Escenarios de aceptación**:

1. **Dado** «Reducir transparencia», **cuando** la persona recorre la app,
   **entonces** las barras y los controles son opacos o esmerilados, y todo el
   texto se lee.
2. **Dado** «Aumentar contraste», **cuando** recorre la app, **entonces** las
   superficies flotantes tienen un borde o una separación claros.
3. **Dado** el texto del sistema al máximo, **cuando** abre cualquier pantalla,
   **entonces**:
   - el título crece con el texto;
   - el título nunca queda más pequeño que el texto de cuerpo que lo sigue;
   - nada se corta.
4. **Dado** que la app está abierta, **cuando** cambia a oscuro o activa
   «Reducir transparencia», **entonces** la app lo adopta en el momento, sin
   reiniciarse.

---

### Historia 4 — La navegación de iOS 26 es de vidrio (Prioridad: P2)

En iOS 26, la barra superior, la barra de pestañas, los botones de esas barras
y las hojas son de vidrio, y el contenido pasa por debajo. Ajustes se abre como
una hoja.

**Por qué esta prioridad**: es lo que se pidió, y el sistema ya da casi todo.
Pero su valor depende de que el contenido de debajo esté bien (Historias 1 y
2).

**Prueba independiente**: en iOS 26, se recorren la Bandeja, Inicio y Consumo
desplazando el contenido, y se abre Ajustes.

**Escenarios de aceptación**:

1. **Dado** iOS 26, **cuando** la persona desplaza la Bandeja, **entonces**:
   - las conversaciones se ven a través de la barra superior y de la de
     pestañas;
   - la barra de pestañas se encoge al bajar y vuelve al subir.
2. **Dado** iOS 26, **cuando** toca un botón de una barra, **entonces** es un
   botón del sistema, agrupado y con la respuesta al toque del sistema.
3. **Dado** iOS, **cuando** abre Ajustes, **entonces**:
   - se abre como una hoja que puede quedarse a media altura o subir a
     pantalla completa;
   - se cierra deslizando hacia abajo.
4. **Dado** un iOS anterior a 26 o Android, **cuando** recorre la app,
   **entonces** las barras se ven como hoy, y nada imita el vidrio.

---

### Historia 5 — Saber a dónde lleva cada cosa (Prioridad: P2)

Todo lo que lleva a otro sitio se reconoce igual en toda la app. Lo que sale a
la web lo dice antes de tocarlo. Las acciones que se arrepienten caras no
quedan al lado de las de cada día.

**Por qué esta prioridad**: hoy hay tres maneras distintas de decir «ir a otro
sitio» (H5), y borrar la cuenta está pegado a cerrar sesión (H7).

**Prueba independiente**: se revisan Inicio, Consumo y Ajustes, y se cuentan
las formas distintas de navegar y la distancia entre acciones de riesgo.

**Escenarios de aceptación**:

1. **Dado** Inicio, Consumo o Ajustes, **cuando** la persona busca cómo ir a
   otro sitio, **entonces**:
   - todo lo que lleva a otra pantalla es una fila con indicador de avance;
   - lo que sale a la consola web es una fila con el indicador de enlace
     externo, que dice a dónde lleva.
2. **Dado** Ajustes, **cuando** llega al final, **entonces**:
   - «Cerrar sesión» y «Solicitar el borrado de la cuenta» están en secciones
     distintas, con el borrado el último;
   - solo el borrado va en color de peligro, con una línea que dice qué pasa
     después.
3. **Dado** un cliente sin gasto en ningún periodo, **cuando** abre Consumo,
   **entonces** no se le ofrece elegir periodo, y se le dice qué hará aparecer
   el gráfico.
4. **Dado** el teléfono en inglés, **cuando** hay algo esperando, **entonces**
   la acción de atender dice lo que hace.

---

### Historia 6 — Formas y tacto de la plataforma (Prioridad: P3)

Los botones y controles tienen la forma y la respuesta al toque de cada
plataforma, y el texto sigue la escala del sistema.

**Por qué esta prioridad**: es lo que hace que la app parezca de iOS 26 y no
una web dentro de un teléfono (H6, H9). Se nota, pero no impide hacer nada.

**Prueba independiente**: se comparan los controles de la app con los del
sistema al lado (Ajustes del teléfono, Mensajes), en iOS 26 y en Android.

**Escenarios de aceptación**:

1. **Dado** iOS 26, **cuando** la persona ve un botón, **entonces** tiene forma
   de cápsula, y sus esquinas acompañan a las de la superficie que lo contiene.
2. **Dado** cualquier plataforma, **cuando** apoya el dedo en un control,
   **entonces** el control responde en ese instante, no al levantarlo.
3. **Dado** iOS, **cuando** lee una pantalla, **entonces**:
   - el texto tiene el tamaño de los estilos del sistema;
   - los títulos no llevan espacio extra entre letras.

---

### Casos límite

- **Un hilo de un solo mensaje.** Los controles flotantes no lo tapan: el
  mensaje queda por encima de ellos.
- **Sin red.** Los controles desactivados (031 R14.2) se distinguen sobre el
  vidrio y también con «Reducir transparencia».
- **Un solo módulo, sin barra de pestañas** (031 R3.4). No queda una franja de
  vidrio vacía al pie.
- **Un motivo vacío.** El panel dice que el agente no dio motivo, como hoy.
- **El aspecto del vidrio elegido en el sistema (claro o tintado).** La app se
  lee con las dos opciones.
- **Contenido de mucho contraste bajo la barra**, como una burbuja de color o
  una foto recibida. El título y los botones de la barra se siguen leyendo.
- **Otra persona toma el control con el panel a la vista** (031 R6.2). El
  panel pasa al estado real con la misma transición, y no aplica la acción.
- **Una conversación resuelta.** El panel de «Reabrir» flota igual que los
  demás.
- **Un cliente sin Consumo** (§V: la ausencia se diseña). El bloque de dinero de
  Inicio no parece navegable: no lleva indicador de avance.
- **Un saldo sin asignar.** El bloque de dinero lo dice, igual que hoy, sin
  cifras inventadas.
- **El texto al máximo con el panel de espera.** El panel crece, pero el hilo
  se sigue pudiendo desplazar para leer cualquier mensaje.
- **iOS 26 en un iPhone 13 (6,1″).** Las condiciones de «sin desplazar» se
  miden aquí, al tamaño de texto por defecto (decisión de Luis, 2026-10-21; el
  SE de 4,7″ sigue siendo el suelo que admite iOS 26, pero no se mide).

## Requisitos *(obligatorio)*

### Requisito 1 — La navegación de iOS 26 es de vidrio

**Historia de usuario:** Como persona de un cliente con iOS 26, quiero que la
app use el material del sistema, para que se sienta como el resto del
teléfono y el contenido tenga más sitio.

#### Criterios de aceptación

1. WHERE el teléfono tiene iOS 26 o posterior EL sistema DEBE pintar con el
   material de vidrio del sistema:
   - las barras superiores;
   - la barra de pestañas;
   - los botones de esas barras.

   Y el contenido DEBE desplazarse por debajo de ellas y verse a través.
2. El sistema NO DEBE poner el material de vidrio en el contenido: listas,
   filas, burbujas, cifras, gráficos, formularios y avisos de estado.
3. El sistema NO DEBE poner una superficie de vidrio encima de otra.
4. WHERE el teléfono tiene iOS 26 o posterior LOS botones de las barras DEBEN
   ser botones del sistema, con su agrupación y su respuesta al toque. En
   Android siguen siendo los botones de Material de hoy. En todos los casos,
   cada uno DEBE tener nombre accesible y un objetivo táctil de al menos
   44 × 44 pt.
5. La barra de pestañas DEBE encogerse al bajar en una lista y volver al subir.
6. El sistema DEBE usar un solo color de acento, y solo en lo que se toca,
   incluida la pestaña activa. Los títulos DEBEN ir en el color del texto.
7. WHEN la persona abre Ajustes en iOS THEN el sistema DEBE presentarlo como
   una hoja que puede quedarse a media altura o subir a pantalla completa, y
   que se cierra deslizando hacia abajo (D24 de la 031).
8. La búsqueda de la Bandeja DEBE seguir siendo de la Bandeja, en su cabecera,
   con una de las dos colocaciones del sistema que el spike S2 elija (bajo el
   título o integrada en la barra), y NO DEBE ocultarse al desplazar.

### Requisito 2 — Los controles de la conversación flotan

**Historia de usuario:** Como persona que atiende, quiero ver el hilo mientras
decido y mientras escribo, para no contestar a ciegas.

#### Criterios de aceptación

1. WHERE el teléfono tiene iOS 26 o posterior EL sistema DEBE mostrar los
   controles del pie de la conversación como controles flotantes de vidrio,
   con el hilo visible y desplazándose por debajo. Son cinco: el panel de
   espera, el de quién atiende, el de resuelta, el cuadro de escribir y el
   aviso de que pasaron las 24 horas sin poder escribir (031 R6.5).
2. WHEN el hilo está al final THEN el sistema DEBE dejar el último mensaje
   completo y visible por encima de los controles, a cualquier tamaño de
   texto.
3. El panel de espera DEBE mostrar el motivo del agente antes de la acción
   (031 R6.1), en dos líneas como mucho.
4. IF el motivo no cabe en dos líneas THEN el sistema DEBE dejar leerlo entero
   sin salir de la conversación.
5. WHEN la persona toma el control THEN el panel DEBE convertirse en el cuadro
   de escribir:
   - en una sola transición continua, sin rebote y de 300 ms como mucho;
   - con la vibración de éxito (031 R14.9);
   - sin ningún instante sin controles y sin que el hilo salte.
6. WHILE «Reducir movimiento» está activo, el cambio de R2.5 DEBE ser un
   fundido, sin cambio de forma ni desplazamiento.
7. WHILE el teclado está abierto, el sistema DEBE dejar el cuadro de escribir
   justo encima del teclado y el último mensaje a la vista.
8. IF otra persona cambia el control con el panel a la vista THEN el panel
   DEBE pasar al estado real con la transición de R2.5, y NO DEBE aplicar la
   acción (031 R6.2).
9. El sistema DEBE mantener «Devolver al agente» en el panel de espera, y
   también como primera opción del menú de la conversación (031 R6.7).

### Requisito 3 — Respaldo y otras plataformas

**Historia de usuario:** Como persona con un iPhone más antiguo o con Android,
quiero una app que funcione igual de bien, sin imitaciones del vidrio.

#### Criterios de aceptación

1. WHERE el teléfono tiene un iOS anterior a 26 EL sistema DEBE mostrar como
   en la versión de la 031:
   - las barras y las pestañas;
   - las hojas;
   - el panel de la conversación y el cuadro de escribir.
2. Esos mismos teléfonos NO DEBEN imitar el vidrio con transparencias ni
   desenfoques propios.
3. WHERE el teléfono es Android EL sistema DEBE seguir Material 3 Expressive en
   las barras, las hojas y los controles, y NO DEBE imitar el vidrio.
4. Los arreglos de contenido y de textos (R5, R6, R8 y R9) DEBEN aplicarse en
   todas las plataformas y versiones.

### Requisito 4 — Legible siempre

**Historia de usuario:** Como persona que configura su teléfono para leer
bien, quiero que el vidrio nunca me cueste leer.

#### Criterios de aceptación

1. El texto sobre vidrio DEBE tener un contraste de al menos 4,5:1, y los
   iconos y controles de al menos 3:1. Se mide con el contenido más
   desfavorable pasando por debajo, en claro y en oscuro.
2. WHILE «Reducir transparencia» está activo, las superficies de vidrio DEBEN
   volverse opacas o esmeriladas, y el texto DEBE mantener el contraste de
   R4.1.
3. WHILE «Aumentar contraste» está activo, las superficies flotantes DEBEN
   tener un borde o una separación definidos.
4. WHERE el sistema deja elegir el aspecto del vidrio (claro o tintado) EL
   sistema DEBE cumplir R4.1 con cada opción.
5. WHEN la persona cambia el modo claro u oscuro, «Reducir transparencia» o
   «Aumentar contraste» con la app abierta THEN la app DEBE adoptarlo sin
   reiniciarse.
6. WHILE el texto del sistema está a cualquier tamaño, el título de cada
   pantalla DEBE crecer con él. NO DEBE quedar más pequeño que el texto de
   cuerpo de esa pantalla.
7. WHILE el texto del sistema está al máximo, las barras y los controles
   flotantes DEBEN crecer sin cortar texto, y el hilo DEBE seguir pudiendo
   desplazarse hasta cualquier mensaje.
8. Los controles desactivados, por ejemplo sin red (031 R14.2), DEBEN
   distinguirse de los activos sobre vidrio y también con «Reducir
   transparencia».

### Requisito 5 — Inicio dice cada cosa una vez

**Historia de usuario:** Como negocio, quiero entender en un vistazo qué me
toca y cómo voy, sin leer lo mismo tres veces.

#### Criterios de aceptación

1. WHILE hay conversaciones que esperan a una persona, Inicio DEBE mostrar su
   número una sola vez, dentro del bloque de atención y junto a la acción de
   atenderlas. NO DEBE mostrar además una cifra aparte de «esperan a una
   persona».
2. El bloque de atención NO DEBE llevar un contador que cuente algo distinto de
   lo que dicen sus filas (H13).
3. WHILE no hay nada pendiente, Inicio DEBE decirlo en una línea, y NO DEBE
   mostrar una cifra de espera a cero.
4. Inicio DEBE mostrar el saldo, los días que alcanza y el gasto del mes en un
   solo bloque, que lleva a Consumo WHERE el cliente tiene ese módulo.
   - El contenido de Inicio sigue siendo el de 031 R4.1.
   - El detalle sigue en Consumo (031 R4.2).
   - Inicio NO DEBE repetir las tarjetas de Consumo.
5. Inicio y Consumo NO DEBEN organizarse como rejillas de tarjetas iguales con
   icono decorativo, etiqueta y cifra. DEBEN presentar las cifras de una de
   estas dos formas:
   - como filas de una lista agrupada;
   - con una cifra protagonista por bloque.
6. WHERE el teléfono es el más pequeño que admite iOS 26, con el texto al
   tamaño por defecto, EL sistema DEBE mostrar en Inicio, sin desplazar, lo que
   necesita atención y el bloque de dinero.

### Requisito 6 — Una sola forma de ir a otro sitio

**Historia de usuario:** Como persona que usa la app, quiero reconocer de un
vistazo qué me lleva a otro sitio y qué me saca de la app.

#### Criterios de aceptación

1. Todo lo que lleva a otra pantalla de la app DEBE presentarse como una fila
   con indicador de avance, igual en todas las pantallas.
2. Lo que sale de la app a la consola web DEBE presentarse como una fila con el
   indicador de enlace externo, y DEBE decir a dónde lleva.
3. El sistema NO DEBE usar párrafos, frases centradas ni textos sueltos como
   enlaces.
4. WHERE el cliente no tiene el módulo de destino EL bloque NO DEBE parecer
   navegable: ni indicador de avance ni respuesta al toque (constitución §V).

### Requisito 7 — Formas, tacto y texto de la plataforma

**Historia de usuario:** Como persona con un iPhone o un Android, quiero que
los controles se comporten como los del resto de mi teléfono.

#### Criterios de aceptación

1. WHERE el teléfono tiene iOS 26 o posterior EL sistema DEBE dar a los
   botones y controles forma de cápsula. Lo que va dentro de otra superficie
   DEBE tener las esquinas concéntricas con las de esa superficie.
2. WHEN la persona apoya el dedo en un control THEN la respuesta DEBE verse en
   ese instante, no al levantarlo, y NO DEBE consistir solo en bajar la
   opacidad.
3. WHERE el teléfono es un iPhone EL texto DEBE seguir los estilos de texto del
   sistema: el cuerpo mide 17 pt al tamaño por defecto. Los títulos NO DEBEN
   llevar espacio extra entre letras.
4. WHERE el teléfono es Android LAS formas y el texto DEBEN ser los de Material
   3 Expressive.

### Requisito 8 — Ajustes sin riesgo

**Historia de usuario:** Como persona de un cliente, quiero cerrar sesión sin
miedo a tocar por error lo que borra mi cuenta.

#### Criterios de aceptación

1. «Cerrar sesión» y «Solicitar el borrado de la cuenta» DEBEN ir en secciones
   distintas, con el borrado al final de Ajustes.
2. Solo el borrado DEBE usar el color de peligro.
3. El borrado DEBE decir en una línea, antes de tocarlo, qué pasa después. Lo
   que dice al tocarlo no cambia (031 R11.4).

### Requisito 9 — Consumo y textos

**Historia de usuario:** Como persona que lee la app, quiero que cada frase
diga algo y que cada acción diga lo que hace.

#### Criterios de aceptación

1. Consumo NO DEBE abrir con una frase que repita su título.
2. IF no hay gasto en ninguno de los periodos THEN Consumo NO DEBE ofrecer
   elegir periodo, y DEBE decir qué hará aparecer el gráfico.
3. La acción de atender del bloque de atención DEBE nombrar lo que hace, en
   español y en inglés. El cambio DEBE hacerse en el vocabulario compartido con
   la consola, para que la web diga lo mismo (031 R14.6).

### Requisito 10 — Lo que no cambia

**Historia de usuario:** Como Auphere, quiero que el rediseño no rompa nada de
lo que la 031 ya garantiza.

#### Criterios de aceptación

1. Cada cifra DEBE seguir coincidiendo al céntimo con la de la consola web
   (031 R4.3).
2. Todo lo de la 031 DEBE seguir ahí, con sus nombres accesibles:
   - las acciones y los filtros;
   - los estados de carga, vacío, error, reconectando y parcial;
   - los avisos.
3. Las transiciones entre pantallas DEBEN seguir siendo las del sistema (031
   R14.8). El único movimiento propio DEBE ser el de R2.5.
4. Los objetivos táctiles DEBEN seguir siendo de al menos 44 × 44 pt en iOS y
   48 × 48 dp en Android (031 R14.5).
5. Las pestañas DEBEN seguir saliendo de los módulos del cliente (031 R3).

## Criterios de éxito *(obligatorio)*

Medibles y sin tecnología dentro.

- **CE-001**: Con una conversación esperando, Inicio enseña su número una sola
  vez en el contenido, más la insignia de la pestaña. Hoy aparece tres veces,
  y con dos esperando hay dos números distintos.
- **CE-002**: En el teléfono más pequeño que admite iOS 26, con el texto al
  tamaño por defecto, se ve todo sin desplazar en dos pantallas:
  - Inicio: lo que necesita atención y el dinero;
  - una conversación en espera: el último mensaje, el motivo y «Tomar el
    control».
- **CE-003**: Desde Inicio, con algo esperando, la persona puede escribir al
  contacto con dos toques como mucho.
- **CE-004**: El paso del panel al cuadro de escribir dura 300 ms como mucho.
  En ningún momento la pantalla se queda sin controles ni el hilo salta.
- **CE-005**: El 100 % del texto sobre vidrio cumple al menos 4,5:1, y los
  iconos y controles al menos 3:1. Se cumple en claro, en oscuro, con
  «Reducir transparencia» y con «Aumentar contraste».
- **CE-006**: Una revisión heurística no encuentra ningún problema de
  severidad 3 o 4, y los trece hallazgos de la auditoría quedan cerrados. La
  revisión se hace sobre capturas de iOS 26, de un iOS anterior y de Android,
  en claro, en oscuro y con el texto al máximo.
- **CE-007**: Ninguna superficie imita el vidrio en un iOS anterior a 26 ni en
  Android.
- **CE-008**: Ninguna cifra difiere de la consola web.

## Fuera de alcance

- **Funciones, datos o acciones nuevos.** Es un cambio de presentación: lo que
  se ve y se hace lo sigue fijando la 031.
- **El icono de la app con capas de vidrio de iOS 26.** Hace falta el arte del
  icono en capas; va aparte cuando lo haya.
- **iPad.** La app no lo admite.
- **Imitar el vidrio en Android o en iOS anterior a 26.** Va contra el HIG y
  contra Material.
- **Subir la versión mínima de iOS.** Dejaría fuera a quien ya usa la app.
- **Widgets, Live Activities y controles del Centro de control.** No forman
  parte de la Consola Lite.
- **La consola web.** Solo cambia allí el texto compartido de R9.3.
- **La marca, es decir, el color y la voz.** La D24 los deja como están.

## Supuestos

- **La búsqueda de la Bandeja se queda en la Bandeja,** porque solo filtra
  conversaciones. Una pestaña de búsqueda prometería buscar en toda la app. En
  iOS 26 el spike S2 elige entre las dos colocaciones del sistema: bajo el
  título o integrada en la barra (R1.8).
- **El fondo de la app mantiene el color de la marca.** La D24 pone la marca en
  el color, y el vidrio lo recoge.
- **El respaldo antes de iOS 26 es la app de hoy,** porque es lo ya
  verificado. El material de las versiones anteriores no se usa. El pie de la
  conversación vuelve a verse anclado al borde de abajo, con su borde
  superior, aunque el hilo siga pudiendo desplazarse hasta el último mensaje.
- **El vocabulario compartido con la consola se cambia en su fuente.** La app
  lo recibe generado, como hoy.
- **El teléfono más pequeño que admite iOS 26 es el iPhone SE de 4,7″.** Las
  medidas de R5.6 y de CE-002 se toman en un iPhone 13 (6,1″) por decisión de
  Luis del 2026-10-21; el SE queda como suelo conocido y no medido.
- **El pase visual necesita un equipo que hoy no está.** Hace falta Xcode 26.4
  o posterior, espacio en disco para compilar para iOS, y simuladores de iOS 26
  y de un iOS anterior.
  - Es una dependencia de Luis.
  - Sin ella no se pueden cerrar CE-002 y CE-004 a CE-007 en iOS.
- **Lo que la auditoría dijo de iOS estaba «por ver».** Si el pase en
  simulador desmiente algún hallazgo, la spec se corrige con
  `/speckit-clarify`, no en silencio.
