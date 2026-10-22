# Revisión heurística de las capturas — spec 042 (T084, CE-006)

**Producto:** Auphere Customers, iOS 26.0.1 en «13 26» (iPhone 13).
**Fecha:** 2026-10-21. **Capturas:** `evidence/capturas/ios26-13-*.png`.
**Quién usa esto y para qué:** la persona del negocio que mira si alguien
espera, entra a la conversación, toma el control y escribe; de paso mira el
saldo y los avisos.

Tres pasadas, con las skills locales de `apps/mobile/.claude/skills/`:
`ux-heuristics` (Krug + Nielsen, severidad 0–4 y puntuación 0–10 desde el
«Quick Diagnostic»), `design-critique` (una crítica por pantalla, en cinco
puntos) e `impeccable` (`reference/audit.native.md`, cinco dimensiones 0–4,
con `reference/ios.md` como listón de plataforma). **Un hallazgo de severidad
3 o 4 abierto bloquea igual que un test rojo** (`AGENTS.md`); al cierre no
queda ninguno.

## 1. `ux-heuristics` — puntuación 9/10

**Quick Diagnostic** (diez preguntas; se resta por fila fallida):

| Pregunta | Pasa | Nota |
|---|---|---|
| ¿Sé dónde estoy al instante? | sí | Título grande «Hola, Valeria» / «Bandeja de entrada» / «Consumo»; en la conversación, el nombre y quién atiende |
| ¿La acción principal es obvia? | sí | Una sola cápsula primaria por pantalla: «Atender ahora», «Tomar el control», «Activar avisos» |
| ¿La navegación está clara? | sí | Tres pestañas del sistema con insignia; chevrón = dentro, flecha saliente = fuera (R6) |
| ¿Encuentro la búsqueda? | sí | Nativa en la cabecera de la Bandeja |
| ¿El sistema dice qué pasa? | sí | «Enviando…», «Enviado», «Tomaste el control», «Se la devolviste al agente», esqueletos |
| ¿Los errores ayudan? | sí (sin captura nueva) | «Reintentar» con el motivo; la ventana de 24 h explica por qué no se puede escribir |
| ¿Puedo deshacer o volver? | sí | Atrás con el chevrón y el gesto de borde; «Devolver al agente» deshace tomar el control; las hojas se cierran deslizando |
| ¿Funciona sin hover? | sí | Todo es toque; nada depende de pasar el dedo |
| ¿Todo lo interactivo tiene etiqueta? | sí | `accessibilityLabel` en cada botón de barra e icono; los menús del sistema llevan texto |
| ¿Algo me hace parar y pensar «¿eh?»? | **una vez** | Con el texto al máximo, el panel de espera obliga a desplazarse dentro para llegar a «Tomar el control» (ver R-01) |

Una fila fallida de severidad 1 → **9/10**.

### Hallazgos de la pasada (severidad 0–4)

| # | Pantalla | Hallazgo | Sev. | Estado |
|---|---|---|---|---|
| R-01 | Conversación, texto al máximo | El panel de espera se detiene al 60 % de la pantalla y su contenido se desplaza dentro: «Tomar el control» queda bajo el pliegue del panel (`ios26-13-conversacion-espera-texto-max.png`). Es la alternativa a que el panel tape el hilo entero (H19); es lo que hace el sistema con cualquier hoja en tamaños de accesibilidad, y el indicador de desplazamiento se ve | 1 | aceptado; documentado en research D3 y `contracts/ui.md` |
| R-02 | Pestañas, oscuro | La etiqueta de la pestaña activa («Inicio») sobre la píldora de vidrio del sistema da 3,5:1 (`ios26-13-inicio-oscuro.png`): ≥ 3:1 como control, < 4,5:1 como texto. El tinte es `primaryText` (= `primary` en oscuro, `#2CC295`); Apple con su azul del sistema queda igual. Subirlo es decisión de marca: un `primaryText` oscuro más claro (≈ `#5FD9B4`) daría ≥ 4,5:1 sin tocar el código | 1 | pendiente de Luis (tokens compartidos con la consola) |
| R-03 | Ajustes | «Versión 1.0.0» sin el entorno en un build de desarrollo (la prueba de `versionLabel` espera «· development»): el dev client de EAS no pasa la variante al JS. No afecta a producción | 1 | abierto, fuera de esta spec (031 R11) |
| R-04 | Conversación, con el teclado | El hilo arranca bajo el borde de la cabecera y no pasa bajo su título: se pierde el fundido del sistema bajo la barra. Consecuencia deliberada de H20 (el efecto de borde del sistema atenuaba el hilo entero); los botones de la barra siguen en vidrio | 0 | aceptado; research D4 |
| R-06 | Conversación, oscuro + «Aumentar contraste» | Dos capturas con los botones de barra como discos claros y el tinte menta a 1,85:1. Era un artefacto de la recarga en caliente de Metro durante la tanda: con el código congelado no se reproduce y el disco sigue el esquema (6,9:1). Sin cambio (H21) | 0 | cerrado |
| R-07 | Pestañas | La barra se encoge al bajar y, en el simulador, no vuelve al subir; vuelve al tocarla. La insignia de espera queda oculta mientras tanto (H22) | 2 | abierto: comprobar en un iPhone |
| R-05 | Bandeja | Con cinco conversaciones la lista no llega a pasar bajo las barras; la captura «desplazada» de T070 no es posible con esta semilla | 0 | no es un problema de la app |

Nada de severidad 3 o 4; una de severidad 2 abierta (R-07, H22), a confirmar en hardware. Los seis hallazgos nuevos del pase (H14, H17–H20)
están cerrados en `hallazgos.md` con su captura de antes y de después.

## 2. `design-critique` — una crítica por pantalla

### Inicio (`ios26-13-inicio-{claro,oscuro,texto-max}.png`)

- **Primera impresión:** el título grande y, debajo, una sola tarjeta con
  borde de aviso que dice qué pasa y qué hacer. La mirada va al «2» y al botón.
- **Usabilidad:** «Atender ahora» es la única primaria; «Ver consumo ›» es la
  única salida. Nada compite. El bloque de dinero no repite la cifra (H1, H2).
- **Jerarquía:** título grande (34 → 60 en AX5), negocio en `title`, tarjeta
  con cabecera `headline`, cifra en `figure`. Con el texto al máximo el
  título grande sigue mandando (H8, tras el tope por estilo).
- **Consistencia:** cápsulas, tarjetas con `CARD_RADIUS`, chevrón del sistema.
  La barra de pestañas deja ver la gráfica de abajo a través del vidrio.
- **Accesibilidad:** 17,8:1 el título, 5,5:1 el cuerpo sobre tarjeta, 5,0:1 la
  pestaña activa en claro; el botón de Ajustes 5,7:1. Objetivos ≥ 44 pt.

### Bandeja (`ios26-13-bandeja-{claro,oscuro}.png`)

- **Primera impresión:** título grande, búsqueda del sistema, chips y filas.
  Se lee como Mensajes con la marca en el color.
- **Usabilidad:** los chips son cápsulas con el recuento («Necesita humano ·
  2»); las etiquetas de fila («Necesita humano», «Tú respondes») dicen el
  estado sin icono inventado; el punto verde marca lo no leído.
- **Jerarquía:** nombre > último mensaje > etiqueta; la hora a la derecha.
- **Consistencia:** las mismas cápsulas que los botones; iniciales en avatar.
- **Accesibilidad:** la barra de búsqueda y la de pestañas son del sistema;
  pestaña activa 5,0:1 en claro, 3,5:1 en oscuro (R-02).

### Conversación (`ios26-13-conversacion-*.png`)

- **Primera impresión:** nombre y quién atiende en la cabecera de vidrio; el
  hilo opaco; el pie flotante con borde de aviso cuando alguien espera.
- **Usabilidad:** «Tomar el control» primaria y «Devolver al agente» fantasma
  en el panel; el menú de la barra lleva «Devolver al agente» la primera
  cuando atiendes tú (R6.7); «Leer más» abre el motivo entero. El paso del
  panel al cuadro es un fundido de 200 ms con el hilo quieto (`motion.md`).
- **Jerarquía:** el pie es lo único de vidrio sobre el contenido; las burbujas
  son opacas y el aviso del agente va en cápsula de tono.
- **Consistencia:** el botón de enviar es concéntrico con el cuadro; el
  adjunto y el enviar usan el único tinte.
- **Accesibilidad:** 17,8:1 el título, 18:1 el motivo sobre el vidrio claro,
  11,7:1 en oscuro, 5,7:1 el botón «⋯»; con «Reducir transparencia» el pie se
  ancla opaco (19:1); con «Aumentar contraste» el pie lleva borde definido.
  Con el texto al máximo el hilo se sigue pudiendo leer (H19, R-01).

### Ajustes (`ios26-13-ajustes-hoja.png`, `-abajo.png`)

- **Primera impresión:** una hoja del sistema que para a 0,6 con el asa, con
  «Tu cuenta» y los avisos a la vista.
- **Usabilidad:** «Activar avisos» es la única primaria; «Abrir en la consola
  web» dice que sale y a dónde; «Cerrar sesión» y «Solicitar el borrado» en
  grupos distintos, el borrado el último y en rojo, con su consecuencia escrita
  antes de tocar (H7).
- **Jerarquía / consistencia:** grupos agrupados del sistema, una cápsula.
- **Accesibilidad:** el contenido pasa bajo el título de la hoja con el fundido
  del sistema (aquí la lista no está invertida y el efecto funciona).

### Contacto (`ios26-13-contacto-hoja.png`)

- Hoja a 0,6 con los datos, etiquetas, nota y actividad de la 031; sin fondo
  propio, se ve el material del sistema. Sin hallazgos nuevos.

### Consumo (`ios26-13-consumo-{claro,oscuro}.png`)

- **Primera impresión:** título grande y tres filas con una cifra cada una.
- **Usabilidad:** sin selector de periodo cuando no hay gasto (H11); el vacío
  de «Gasto por día» dice cuándo habrá algo; «Abrir en la consola web» sale.
- **Jerarquía:** el saldo en rojo cuando está agotado y lo dice en palabras.
- El título no se repite (H10).

## 3. `impeccable` — `audit.native.md`

| # | Dimensión | Puntos | Hallazgo clave |
|---|---|---|---|
| 1 | Accesibilidad (VoiceOver, Dynamic Type, objetivos, contraste) | 4 | Etiquetas en todo lo interactivo; Dynamic Type con la tabla de Apple (tope por estilo); ≥ 44 pt; contraste medido en `a11y.md`. R-02 (3,5:1 en una etiqueta de pestaña en oscuro) queda como decisión de marca |
| 2 | Rendimiento | 4 | `FlatList` virtualizada; el pie anima su altura en el hilo del UI; nada de propiedades de layout de Reanimated dentro de la lista (H20); imágenes con `expo-image` |
| 3 | Apariencia y tema | 4 | Tokens OKLCH en claro y oscuro; vidrio solo del sistema o `expo-glass-effect`; nada de hex |
| 4 | Conformidad con la plataforma | 4 | Pestañas, cabeceras, hojas, menús y botones de barra nativos; cápsulas; SF Symbols; el gesto de borde vivo; el chevrón solo (H17) |
| 5 | Adaptabilidad | 3 | Teclado e insets correctos; el panel se desplaza dentro al 60 % con texto máximo (R-01). Sin iPad en el objetivo; sin pase en horizontal |
| | **Total** | **19/20** | **Excelente** |

**Veredicto de conformidad:** la app se ve y se toca como una app de iOS 26:
lo que es del sistema es del sistema, lo propio va en el color y la voz.

## 4. Android (2026-10-21)

Las tres pasadas sobre `capturas/android-*.png` (emulador con la imagen del
Pixel 9, API 36):

- **`ux-heuristics`**: el mismo diagnóstico rápido que en iOS pasa entero;
  sin la fila de R-01 (el panel de espera al 200 % cabe sin desplazarse dentro).
  Dos hallazgos de severidad 2 corregidos en el pase: H23 (la lupa de la
  búsqueda invisible en oscuro) y H24 (el título de la conversación no crecía
  con el texto). Puntuación **10/10**.
- **`design-critique`**: Material 3 sin imitar el vidrio (CE-007). Barra
  superior y pestañas de Material con el indicador en píldora; el pie de la
  conversación anclado y opaco con su borde de aviso; el contacto en hoja
  inferior; Ajustes como pantalla con los grupos de la app junto a los del
  sistema (`android-botones-vs-sistema.png`); menús en hoja de acciones.
  Mismo contenido y misma voz que en iOS.
- **`impeccable`** (`reference/android.md` y `audit.native.md`): 20/20.
  Etiquetas, ≥ 48 dp, sp, ondulación de Material en lo que se pulsa, el gesto
  de atrás vivo, tema claro y oscuro desde los tokens.

| # | Pantalla | Hallazgo | Sev. | Estado |
|---|---|---|---|---|
| A-01 | Bandeja, oscuro | La lupa de la búsqueda salía gris oscuro sobre negro (H23) | 2 → 0 | cerrado |
| A-02 | Conversación, 200 % | El nombre y quién atiende no crecían con el texto (H24) | 2 → 0 | cerrado |
| A-03 | Pestañas, 200 % | Las etiquetas de las pestañas crecen hasta tocarse («Bandeja» y «Consumo»); es el comportamiento de Material con el texto al máximo | 1 | aceptado |

## 5. Lo que no cubre esta revisión

- **iOS anterior a 26 y 26.1 (vidrio tintado)**: sin runtime.
- **Hardware**: posturas, gestos y rendimiento real necesitan un iPhone.
