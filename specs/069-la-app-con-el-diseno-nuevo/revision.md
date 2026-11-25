# Revisión de calidad · spec 069 (la app con el diseño nuevo)

**Fecha:** 2026-11-21, entre las 02:30 y las 03:10. **Revisor:** subagente de calidad, solo lectura.

**Qué se revisó:**

- `apps/mobile/src` del árbol `069-app-movil`;
- las capturas de `evidence/` (Android 16, Pixel 9, claro, oscuro y texto grande, con datos de ejemplo);
- `spec.md`, `plan.md` y `log.md`;
- el inventario de diseño (`research/2026-11-21-app-movil-a-tiendas/01-03`).

**Cómo:**

- **Listas de comprobación:**
  - las tres skills de la app: `ux-heuristics`, con severidad 0–4; `design-critique`; e `impeccable`, con `reference/ios.md`, `android.md` y `audit.native.md`;
  - las tres puertas del workspace: `ui-states-checklist`, `a11y-audit` (WCAG 2.2 AA, estático) y `design-tokens`.
- **Contrastes:** calculados desde `theme/tokens.gen.ts`, con la composición alfa resuelta sobre el fondo real de cada par.

## Límites de esta revisión

- **iOS no se ha visto.** Todo lo que es solo de iOS queda **sin verificar**: vidrio, `NativeTabs` de iOS, título grande, `Stack.Toolbar` y «Reducir transparencia».
- **Las capturas están en inglés.** Faltan capturas en español, que es el idioma de las fichas de las tiendas. Los textos en español son un 15–30 % más largos y no se han visto en pantalla.
- **Sin navegador ni axe.** Es una revisión estática, y las capturas son la única prueba de lo que se pinta.
- **El código cambió durante la revisión.** Otra sesión editaba el árbol a la vez:
  - a las 02:53: `app/(app)/_layout.tsx`, `lib/modules.ts` y `__tests__/tabs.test.tsx`. Se revirtieron los dos arreglos de la barra;
  - entre las 03:01 y las 03:03: `features/inbox/{model.ts, thread/mode.tsx, list/conversation-row.tsx}` y `i18n/v13-bandeja.*`;
  - también `log.md` y capturas nuevas.

  Los números de línea son los de las 03:05. Cada hallazgo se volvió a comprobar en esa versión.
- **No se marcan como defecto las decisiones de `log.md`**, salvo que rompan una regla. Entre ellas: Helvena apagada, confirmaciones con la alerta del sistema, aviso de 6 s, búsqueda en la cabecera, «hoy» en `basil`, iconos del sistema en el cromo nativo y las diferencias de Reservas.

## Veredicto

| | |
|---|---|
| Severidad 4 | **0** |
| Severidad 3 | **0 confirmados** y **1 sin verificar** (H01, depende de un aviso real en un build que no sea de desarrollo) |
| Severidad 2 | **12** |
| Severidad 1 | **10** |
| **Fallos WCAG 2.2 AA** | **7 hallazgos**, todos de severidad 2: H04, H06, H07, H08, H09, H10 y H12. **SC-004 pide cero fallos AA, así que hoy no se cumple**, aunque ninguno llegue a severidad 3. Casi todos se arreglan con un token o una línea. |

En conjunto, la base es sólida:

- los estados están cubiertos en casi todas las pantallas;
- los gestos tienen su acción accesible;
- se respeta «Reducir movimiento»;
- no hay ni un hex en las pantallas;
- el texto crece con el sistema sin romper Inicio ni la Bandeja.

Lo que falta es pulir el contraste en claro, la carga y el error del bloque de avisos, y el dock de «espera», que se aleja del diseño.

## Tabla de hallazgos

Severidad según `ux-heuristics`: 0 no es problema, 1 cosmético, 2 menor, 3 mayor y 4 catastrófico. Un 3 o un 4 bloquea. «AA» marca un fallo de WCAG 2.2 AA, que bloquea SC-004.

| id | sev. | pantalla / área | archivo:línea | qué pasa | por qué importa | arreglo propuesto |
|---|---|---|---|---|---|---|
| H01 | **3, sin verificar** | Barra de pestañas e Inicio (Android) | `app/(app)/_layout.tsx:64-83`; `app/(app)/inicio/index.tsx:115` (`paddingBottom: 32`); `features/home/home-view.tsx:136,140` | Tras relanzar la app con un enlace, la barra salió sin iconos y la tarjeta «Atender a Lucía» quedó **debajo de la barra**, sin poder desplazarla (`evidence/fallo-inicio-tarjeta-bajo-barra.png`). El contenido mide lo mismo que la pantalla (`flexGrow` y `marginTop: auto`). Tocar un aviso relanza la app igual. `log.md` lo atribuye al cliente de desarrollo, y los dos arreglos se revirtieron a las 02:53. | Si pasa en release, el flujo del aviso urgente, que es la razón de la app, aterriza en una pantalla sin navegación y con la acción tapada. Heurísticas 1 y 3; R8.4 (al alcance del pulgar). | 1) **Puerta de la 070:** tocar un aviso real con la app cerrada y con la app en segundo plano, en un build de preview o staging de Android. 2) Defensa que no depende de la causa: en Android, `paddingBottom` de Inicio = alto de la barra + 16. El diseño reserva 108 (01 §3.5). Así la tarjeta nunca queda bajo la barra. 3) Etiquetas siempre visibles (H05): una barra sin iconos sigue siendo navegable. |
| H02 | 2 | Ajustes · Avisos en este teléfono | `app/ajustes.tsx:66,74,181-213` | Este bloque no tiene estado de carga ni de error. Mientras se lee, o si la lectura falla, los interruptores salen **apagados y desactivados** (`value` sale de `notices.data?.kinds ?? []`), sin texto y sin «Reintentar». `android-claro-ajustes.png` es ese estado; `log.md` lo descarta como «no era un fallo». El bloque de cierre por inactividad de la misma pantalla sí tiene carga y error (`ajustes.tsx:400-412`). | R3.1 (seis estados, error con «Reintentar»); heurísticas 1 y 9. Durante la carga el aviso urgente aparenta estar apagado, y con un error queda así sin salida. | Con `notices.isPending` y sin datos, filas esqueleto con `accessibilityRole="progressbar"` en lugar de interruptores. Con `notices.isError` y sin datos, texto y `<Button label={t("app.retry")} onPress={() => notices.refetch()} />`. Nunca pintar `value={false}` sin dato. |
| H03 | 2 | Conversación · espera (dock) | `features/inbox/thread/control.tsx:70-125` (ámbar en `:79` y `:86`); `ui/floating-surface.tsx:79-80`; `features/inbox/thread/bubble.tsx:260-264` | El dock repite lo que ya dice la pantalla: cabecera «Espera a una persona»; píldora del hilo «El agente pidió ayuda: {motivo}»; título «Esta conversación espera a una persona»; «Esperando hace 12 min · lo pidió Ava»; «Pidió una persona»; y el motivo otra vez. Usa ámbar en dos líneas de texto, en la píldora del hilo y en un borde de 1 px que en Android toca los tres bordes de la pantalla. Ocupa más o menos un tercio de la pantalla (`android-claro-conversacion-espera.png`). En el diseño (02 §4.5) es una franja «Ava pidió ayuda: {motivo}» con «Atender a Lucía», y el ámbar solo en la mano. | R1.2 («ámbar solo en la etiqueta y el icono de quien espera»), heurística 8 (minimalismo) y design-critique (jerarquía): la acción queda abajo del todo, tras cinco líneas. No es una decisión del `log.md`. | Título: «{agente} pidió ayuda: {motivo}», en dos líneas con «Leer más». Una sola línea muted «hace 12 min». `tone="mutedForeground"` en `control.tsx:79` y `:86`. En `floating-surface`, en modo acoplado, solo `borderTop` y no el borde completo de `defined`. Se queda «Devolver al agente» como botón fantasma («nada se pierde»). |
| H04 | 2 · **AA** | Reservas · Semana (Aforo) | `features/reservas/week.tsx:103,189` | La celda de nivel 3 pinta el número en `primaryForeground` (#F1F7F6) sobre `positive` (#2CC295): **2,09:1** en claro. Viene de la 044, pero sale en la 1.3.0. | WCAG 1.4.3. | `3: { bg: "positive", fg: "onHighlight" }`: #032221 sobre #2CC295 da 7,38:1 en los dos temas. |
| H05 | 2 | Barra de pestañas (Android) | `app/(app)/_layout.tsx:64-70` | Con cuatro destinos, la barra nativa de Android solo rotula el elegido. Los otros tres son solo iconos, y Consumo es un gráfico de barras (capturas de Inicio, Bandeja, Reservas y Consumo). | Material 3 (cada destino lleva etiqueta); heurística 6 (reconocer antes que recordar); el «mystery meat» de `ux-heuristics`. | Etiquetas siempre visibles en Android: `labelVisibilityMode="labeled"`, si `NativeTabs` lo expone en expo-router 58. **API sin verificar**: no pude leer `node_modules`. Si no lo expone, abrir un parche o un issue. |
| H06 | 2 · **AA** | Inicio · Lo último en la Bandeja | `features/home/latest.tsx:111-114` | Aquí el no leído solo se ve por un punto `highlight` (#2CC295) de 8 px sobre su halo: **2,27:1** contra la tarjeta y unos 2:1 contra el halo. Ni el peso ni la tinta de la fila cambian; la Bandeja, en cambio, sí pone la vista previa en tinta (`conversation-row.tsx:100-109`). | WCAG 1.4.11 (objeto gráfico que comunica un estado), en claro. | En claro, punto en `highlightInk` (#106958, 6,60:1). O, como en la Bandeja, vista previa en `foreground` cuando `c.unread`. |
| H07 | 2 · **AA** | Reservas · tira de días y Mes | `features/reservas/header.tsx:220,248`; `features/reservas/month.tsx:98` | Los puntos de «día con reservas» son `highlight` sobre el fondo: **2,09:1** en claro. En la tira de la semana, además, la etiqueta accesible es solo `«{day}»` (`reservas.day.a11y`): el lector no sabe qué días tienen reservas. Mes sí lo dice. | WCAG 1.4.11 y 1.3.1; incoherente con Mes. | Punto en `highlightInk` en claro (6,09:1). Añadir «, con reservas» a la etiqueta cuando `marked` (clave nueva `reservas.day.a11y.marked`). |
| H08 | 2 · **AA** | Controles segmentados | `ui/bits.tsx:114-130` (Día/Semana/Mes, 7/30/90 días); `features/reservas/header.tsx:142-160` (lista/cuadrícula) | Lo elegido solo se distingue por una tarjeta blanca sobre `muted`: **1,21:1** en claro, y menos en oscuro (#18201D sobre #222B28). No lleva borde ni ninguna otra marca de 3:1 o más. | WCAG 1.4.11 (indicador de estado de un componente); R1.2 («lo elegido lleva tinte y ✓, nunca solo color»). | Segmento elegido con borde `input` (3,11:1 en claro y 3,58:1 en oscuro), o en `selection` / `onSelection`, como los chips. |
| H09 | 2 · **AA** | Campos de texto | `ui/field.tsx:49` (Nueva reserva, lista de espera…); `features/inbox/thread/composer.tsx:136`; `features/entry/entry-field.tsx:67`; `app/conversacion/[id]/contacto.tsx:191,238` | Placeholder en `subtle` (tinta al 50 %): **3,59:1** sobre el fondo y **3,65:1** sobre la tarjeta, en claro. En Nueva reserva, «+56 9 1234 5678» es la única pista del formato del teléfono, que es obligatorio. | WCAG 1.4.3, en claro. | `placeholderTextColor={colors.mutedForeground}` (7,1–7,4:1), que es lo que ya usa la búsqueda de la Bandeja (`hintTextColor`). |
| H10 | 2 · **AA** (discutible) | Aviso breve con «Deshacer» | `ui/toast.tsx:25-26,60-64,90-95` | El aviso con acción se va a los 6 s siempre: no lee el «tiempo para actuar» de Android ni se alarga con VoiceOver o TalkBack activos. `announceForAccessibility` lee el texto pero no dice que hay «Deshacer». Con lector de pantalla no es realista llegar al botón en 6 s. Las cancelaciones de Reservas se envían al acabar ese plazo (`api/reservas-hooks.ts:276-301`). Además, `accessibilityLiveRegion` y el anuncio explícito pueden leerse dos veces en Android (**sin verificar**). | WCAG 2.2.1 (límite de tiempo ajustable); heurística 3. | `ms = await AccessibilityInfo.getRecommendedTimeoutMillis(TOAST_UNDO_MS)` en Android. Con `isScreenReaderEnabled()`, no cerrar solo un aviso con acción (o darle 20 s), anunciar «{texto}. Deshacer disponible» y llevar el foco al botón (`setAccessibilityFocus`). Dejar un solo anuncio. |
| H11 | 2 | Bordes de los controles | `ui/chip.tsx:61`; `features/inbox/thread/composer.tsx:117`; `features/reservas/slot-picker.tsx:234`; `features/reservas/day-grid.tsx:190,244` | Chips, horas y bloques de la cuadrícula llevan un borde `border` (tinta al 12 %): **1,30:1**. El plan (D2) prometía un rol `controlBorder` «que garantiza 3:1». No existe en `tokens.gen.ts`, como tampoco `warningTint`, `successText`, `successTint` ni `bubbleMine`. | R3.5 de la spec. WCAG 1.4.11 no falla, porque el texto identifica cada control. El plan y el código divergen. | Generar `controlBorder` (≥ 3:1; `input` da 3,06–3,11:1 en claro y 3,58:1 en oscuro) y usarlo en chips, horas y bloques. O corregir el plan si se decide no hacerlo. |
| H12 | 2 · **AA** | Recuperar la contraseña · «Revisa tu correo» | `app/forgot-password.tsx:221-243` | La lista «Qué sigue» es un solo elemento accesible con `accessibilityLabel="Qué sigue"`. El lector dice solo eso y se salta los tres pasos y sus pistas. | WCAG 1.3.1 y 4.1.2; R3.3. | Quitar `accessible` y `accessibilityLabel` del contenedor (dejar `accessibilityRole="list"`). Cada paso, `accessible`, con «Paso {n}: {título}. {pista}». |
| H13 | 2 | Reservas · Día (Android) | `features/reservas/screen.tsx:344-346,410` | El FAB extendido «Nueva reserva» (dos FAB apilados en Aforo) flota a 16 dp del borde, pero el contenido solo deja `paddingBottom: 32`. Al final de la lista, el FAB tapa el chevron, la píldora y parte del texto de la última reserva (`android-claro-reservas-dia.png`), y en la cuadrícula tapa los bloques de las 14:00–15:00. Viene de la 044. | Visibilidad; inset y solape (`impeccable`, audit.native §4). | En Android, `paddingBottom` = alto del FAB + 32 (unos 88 dp; unos 160 con dos FAB). O encoger el FAB a solo icono al desplazar, el patrón de M3. |
| H14 | 1 | Consumo · tarjeta de saldo | `features/usage/usage-view.tsx:192-201` | «Te alcanza hasta el domingo 21 de marzo de 2027» va en `title` (24, a 600, en dos líneas) y pesa más que el propio saldo. Debajo hay una barra llena sin escala y «Para unos 4 meses…», que dice lo mismo. En el diseño (03 §9.1): la cifra grande y una línea muted. `log.md` lo deja «para revisar». | Heurística 8; jerarquía (design-critique). | Una sola frase en `callout` muted: «Te alcanza hasta el dom 21 mar, unos 4 meses a este ritmo». Quitar el `Meter`, o decir su escala (de hoy a fin de mes). |
| H15 | 1 | Inicio · tarjeta «Hoy» | `features/home/tiles.tsx:89` | El punto menta de arriba a la derecha es igual que el punto de «sin leer» (mismo color y tamaño), pero no significa nada. | Heurística 4: el mismo signo, el mismo significado. | Quitarlo, porque el marco menta ya basta. O mostrarlo solo cuando haya algo sin confirmar. |
| H16 | 1 | Inicio · «Hoy» sin reservas | `features/home/tiles.tsx:258`; lo fija `__tests__/v13-inicio-pantalla.test.tsx:222-226` | Un día sin ninguna reserva dice «0 reservas · No quedan más hoy», que da a entender que hubo. | Casos límite de la spec: nunca ceros sueltos, y el vacío dice qué aparecerá. | Con `sum.total === 0`, «Sin reservas hoy». |
| H17 | 1 | Tiras de días (inglés) | `features/reservas/header.tsx:240`; `features/reservas/slot-picker.tsx:133` | «today» en minúscula junto a «Mon» y «Tue» (capturas de Reservas y de Nueva reserva). El inventario ya lo marcaba (03 §20.20: «hay que unificar»). | Heurística 4; i18n. | `toLocaleLowerCase` solo cuando el idioma escribe los días en minúscula (`es`). |
| H18 | 1 | Conversación · cuadro de escribir | `features/inbox/thread/composer.tsx:131-143,196` | El campo no tiene contorno ni fondo: «Escribe un mensaje…» flota entre la fila de respuestas y la de iconos, y enviar aparece lejos, a la derecha. En el diseño (02 §4.6) es una cápsula con «+» a la izquierda y enviar dentro. Estas pantallas serán capturas de tienda. | Affordance; coherencia con el diseño. | Una cápsula `card` con borde `input` y radio `RADII.xl` que envuelva el campo y enviar, con «+» a la izquierda. |
| H19 | 1 | Cabeceras de Android · «⋯» | `app/conversacion/[id]/index.tsx:232`; `features/reservas/screen.tsx:321`; `ui/icon.tsx:132` | El botón de «más» de la cabecera es la elipsis horizontal de Lucide (`Ellipsis`). En Android, el menú de desbordamiento es vertical. | `impeccable` android: patrones de iOS en Android. | En Android, `EllipsisVertical` para `icons.more`. |
| H20 | 1 | Escala de radios | `theme/theme.ts:36`; 31 usos de `radius.sm` y `radius.md` (p. ej. `ui/bits.tsx:114,123`, `ui/states.tsx:40,122,144`, `ui/field.tsx:37`); literales en `app/conversacion/[id]/index.tsx:369` (12) y `features/reservas/body.tsx:135` (10) | Conviven dos escalas: la de la consola (4 y 8) y `RADII` (8, 12, 16, 20 y 28). Las hojas nativas de Android tienen radio 16 (`SHEET_RADIUS`) y la de Entrar, 28 (`RADII.sheet`). | R1.10 («una sola escala»); design-tokens. | `radius.sm` → `RADII.sm`, `radius.md` → `RADII.md`, `SHEET_RADIUS` → `RADII.sheet`. Dejar `tokens.radius` solo para `full`. |
| H21 | 1 | Objetivos táctiles en Android | `features/reservas/day-grid.tsx:188,237`; `features/inbox/thread/bubble.tsx:173` | Los huecos libres, los bloques cortos de la cuadrícula y «Corregir» llegan a 44 con `hitSlop`, que vale para iOS pero no llega a 48 dp en Android. En la cuadrícula, los slops de bloques vecinos se pisan. | R3.3 (48 × 48 dp en Android). Pasa WCAG 2.5.8 (24 px). | En Android, `hitSlop` de `(TOUCH - alto) / 2`. |
| H22 | 1 | Ajustes · tarjeta de cuenta | `app/ajustes.tsx:172` | «Rol: Miembro del negocio» es un texto fijo, igual para todo el mundo; la spec deja el rol fuera porque la API no lo da. Bajo la fila queda un hueco grande (`android-claro-ajustes.png`). | Heurística 8; R21 (lo que se ve tiene que ser un dato). | Quitar la fila hasta que la API dé el rol. |
| H23 | 1 | Conversación · ventana vencida | `features/inbox/thread/control.tsx:131-150` (texto editado a las 03:01) | La cabecera dice «Ava no puede responder ahora» y la franja, «El agente ya no puede responder…», en tres líneas. Nombra de dos maneras al mismo agente (`android-claro-ventana-vencida.png`). | Heurística 4. | Usar el nombre en la franja («Ava ya no puede responder…») y acortarla a dos líneas. |

## Puerta 1 · `ux-heuristics` (Nielsen y Krug)

**Diagnóstico rápido**

| Pregunta | Resultado |
|---|---|
| ¿Se sabe qué pantalla es? | ✅ Título grande y la pestaña marcada. |
| ¿La acción principal es obvia? | ✅ «Atender a…», «Tomar el control», «Nueva reserva». ⚠️ En el dock de espera queda tras cinco líneas (H03). |
| ¿La navegación es clara? | ❌ En Android, tres de los cuatro destinos van sin etiqueta (H05). Y, sin verificar, la barra sin iconos de H01. |
| ¿Se encuentra la búsqueda? | ✅ En la cabecera de la Bandeja, con resultados al dejar de escribir y un vacío que ofrece quitar el canal. |
| ¿El sistema dice qué pasa? | ❌ Los avisos de Ajustes no tienen carga ni error (H02). En el resto: esqueletos, «Lo guardado a las…» y aviso breve. |
| ¿Los errores ayudan? | ✅ Errores de campo bajo el campo y solo tras el primer intento; motivos de envío fallido en palabras. |
| ¿Se puede deshacer? | ✅ «Deshacer» en resolver, leer, cancelar y quitar, y «Devolver». ⚠️ Plazo fijo de 6 s con lector de pantalla (H10). |
| ¿Funciona sin hover? | ✅ |
| ¿Está todo etiquetado? | ✅ Botones de icono con nombre. ⚠️ Las pestañas de Android (H05). |
| ¿Hay algo que haga pensar «¿eh?»? | ⚠️ El dock de espera repite tres veces lo mismo (H03), y la fecha de Consumo pesa más que el saldo (H14). |

**Puntuación: 7/10** (banda 6–8). Fallan tres filas, todas con severidad 2 como peor caso.

Para llegar a 9:

- etiquetas en la barra de Android (H05);
- carga y error en los avisos (H02);
- el dock de espera según el diseño (H03).

**Por heurística** (solo lo que suma a la tabla):

| Heurística | Resultado |
|---|---|
| 1 · Visibilidad | ✅ Esqueletos con medidas finales en Inicio, Bandeja y Consumo; «Reconectando»; offline con hora. ❌ H02. |
| 3 · Control | ✅ Guardar sin salir pide confirmación (`app/reserva/nueva.tsx:88-96`); apagar el aviso urgente también (`ajustes.tsx:100-108`). |
| 4 · Coherencia | ⚠️ H15, H17, H19 y H23. |
| 5 · Prevención | ✅ Sin horas en el pasado ni dentro de la antelación; las horas ocupadas se ven, tachadas y desactivadas. |
| 8 · Minimalismo | ⚠️ H03, H14 y H22. |

## Puerta 2 · `design-critique`

**Primera impresión (2 s).** Inicio responde «¿tengo que hacer algo?»: la tarjeta de quien espera, abajo, con su nombre, el motivo y el botón, es lo que el ojo busca después de «Hola, Camila». Los cuatro números se leen de un vistazo. En oscuro la paleta se sostiene, sin negro puro (`#0D1412`).

**Jerarquía.**

| Pantalla | Resultado |
|---|---|
| Bandeja | ✅ «Espera» primero, grupos por día, nombre en 600 y hora en tinta cuando hay algo sin leer. |
| Conversación en espera | ❌ Seis bloques compiten antes de la acción (H03). |
| Consumo | ❌ La fecha en `title` desplaza al saldo (H14). |
| Nueva reserva | ✅ Lee de arriba abajo en el orden en que se decide. |

**Coherencia.**

| Elemento | Problema | Hallazgo |
|---|---|---|
| Radios | Dos escalas | H20 |
| Bordes de control | 1,30:1 en chips frente a 3,11:1 en campos y botones secundarios | H11 |
| Punto menta | Significa «sin leer» en tres sitios y nada en «Hoy» | H15 |
| «today» / «hoy» | Caja distinta a la de los otros días | H17 |

**Lo que funciona bien.**

- **Color por función:**
  - la tinta para lo elegido, con un ✓ que se dibuja;
  - el verde sólido solo en la acción principal;
  - el ámbar en «Espera» y en lo pendiente.
- **Logotipos de canal** de cada marca en el avatar.
- **Datos que no se inventan:**
  - sin «Leído» si la API no lo da (`bubble.tsx:80-90`);
  - el nombre del agente sale de los datos;
  - la moneda de la bolsa.
- **El ámbar del hilo** en las reservas pendientes de la cuadrícula va con icono de reloj y borde discontinuo, nunca solo color (`day-grid.tsx:240-252`).

## Puerta 3 · `impeccable` (`audit.native`, Android verificado, iOS sin verificar)

| # | Dimensión | Nota | Hallazgo clave |
|---|---|---|---|
| 1 | Accesibilidad | 2 | Contraste en claro de puntos, segmentados y placeholders (H06–H09); la lista de pasos colapsada (H12); el plazo del aviso (H10). Etiquetas, acciones accesibles de los gestos y escalado de texto, bien. |
| 2 | Rendimiento | 3 | `FlatList` virtualizada, filas con `memo` y Lucide importado icono a icono. Las cifras del R22 (arranque, 1.000 conversaciones, fps del líquido) quedan **sin medir** (puerta de la 070). |
| 3 | Apariencia y tema | 3 | Cero hex en pantallas, y los dos temas salen de un solo generador. Dos escalas de radios (H20) y roles del plan sin generar (H11). |
| 4 | Conformidad de plataforma | 3 | Android usa la barra, la cabecera y las hojas nativas, y el back del sistema funciona. Faltan las etiquetas (H05). La elipsis horizontal (H19) y el cuadro de escribir sin cápsula (H18) se alejan de M3 y del diseño. |
| 5 | Adaptabilidad | 3 | Solo vertical y solo iPhone (`app.config.ts:61,68`), una decisión válida. El teclado está bien resuelto (`KeyboardStickyView`, el dock sube con él). Con texto grande, las tarjetas pasan a una columna (`tiles.tsx:43`) y la cuadrícula ofrece la lista (`day-grid.tsx:20`). |
| | **Total** | **14/20** | **Bueno** |

**Veredicto de plataforma (Android): pasa.** Se lee como una app nativa:

- barra inferior, cabecera y hojas nativas;
- ripple;
- interruptores del sistema.

Las desviaciones son de detalle (H05, H18 y H19), no de estructura. **En iOS: sin verificar.** El riesgo está en el vidrio y en «Reducir transparencia» (R1.8–R1.9), que no se han visto nunca.

## Puerta 4 · `ui-states-checklist`

| Pantalla | Carga | Vacío | Error | Parcial | Ideal | Sin conexión |
|---|---|---|---|---|---|---|
| Inicio | ✅ esqueleto (`HomeSkeleton`); «Lo último» con filas fantasma | ✅ «Aún nadie escribió», «Sin gasto»; ⚠️ «Hoy» sin reservas (H16) | ✅ `ErrorState` y error por bloque con «Reintentar» (`latest.tsx:58-63`) | ✅ `PartialNotice` | ✅ | ✅ `OfflineBanner` con hora |
| Bandeja | ✅ `InboxSkeleton` | ✅ vacío por filtro, por canal y por búsqueda; primer vacío | ✅ | ✅ `PartialNotice` y «Reconectando» | ✅ | ✅ |
| Conversación | ✅ esqueleto | n/a | ✅ hilo y detalle con «Reintentar» | ✅ páginas | ✅ | ✅ solo se apaga lo que escribe y el borrador se conserva |
| Reservas | ✅ `DaySkeleton` | ✅ cerrado, sin reservas, con filtro | ✅ | ✅ | ✅ | ✅ |
| Nueva reserva | ✅ horas con esqueleto | ✅ «No quedan horas…» | ✅ horas con «Reintentar»; el formulario conserva lo escrito | — | ✅ | ✅ sin FAB offline |
| Consumo | ✅ `UsageSkeleton` | ✅ «Sin gasto» | ✅ | ✅ | ✅ | ✅ |
| Ajustes | ❌ avisos (H02); ✅ cierre por inactividad | ✅ canales «sin conectar» | ❌ avisos (H02); ✅ cierre y borrado | — | ✅ | ✅ |
| Entrar y Recuperar | ✅ | — | ✅ bajo el campo, tras el primer intento | — | ✅ | ✅ (`sign-in.tsx:102,121`) |

**Transversales.**

| Comprobación | Resultado |
|---|---|
| Reducir movimiento | ✅ Cada micro tiene su forma reducida (`motion/micro.tsx`), y la espera de 3,2 s de la tarjeta calma no se recorta. |
| Texto largo | ✅ `minWidth: 0` en los hijos flex; una línea con elipsis en los nombres. |
| Imágenes | ✅ Fotos solo en memoria, con las iniciales de respaldo (`bits.tsx:50-70`). |
| Sesión caducada | Sin verificar en esta revisión. |

**Puntuación: 8/10.** Mejor arreglo: H02.

**Veredicto: NEEDS WORK** por H02.

## Puerta 5 · `a11y-audit` (WCAG 2.2 AA, estático en React Native)

**Contraste de los pares de tokens que se usan** (calculados desde `tokens.gen.ts`, con el alfa resuelto):

| Par | Claro | Oscuro | Uso |
|---|---|---|---|
| `mutedForeground` sobre `card` / `background` | 7,39 / 7,12 | 9,77 / 10,67 | Texto secundario ✅ |
| `subtle` sobre `card` / `background` | **3,65 / 3,59** | 5,51 / 5,78 | Placeholders ❌ (H09); chevrons y pista apagada ✅ (≥ 3) |
| `warningText` sobre `card` / sobre `background` con `highlightSoft` | 7,30 / 5,96 | 9,45 / 8,08 | «Espera», «sin confirmar» ✅ |
| `primaryForeground` sobre `primary` | 6,79 | 8,53 | Botón principal ✅ |
| `toastAccent` sobre `toastBg` | 8,53 | 6,79 | «Deshacer» y «Devolver» ✅ |
| `highlightInk` sobre `background` | 6,09 | 8,22 | «hoy» en las tiras ✅ |
| `highlight` sobre `card` / `background` | **2,27 / 2,09** | 7,33 / 8,22 | Puntos de sin leer y de reservas ❌ en claro (H06, H07) |
| `primaryForeground` sobre `positive` | **2,09** | 8,53 | Semana de Aforo, nivel 3 ❌ (H04) |
| `card` sobre `muted` (segmento elegido) | **1,21** | ≈ 1,1 | Estado del segmentado ❌ (H08) |
| `input` sobre `card` | 3,11 | 3,58 | Campos y botón secundario ✅ (3:1) |
| `border` sobre `card` | **1,30** | 1,52 | Chips, horas y bloques ❌ R3.5 (H11) |
| `positiveText` sobre `positiveBg` sobre `card` | 6,66 | 5,91 | Fondo de deslizar ✅ |
| `accentDeep` sobre `accentSoft` | 5,03 | 5,03 | Iniciales y etiquetas ✅ |
| `ring` sobre `background` | 5,57 | 8,22 | Anillo de foco de Entrar, de 2 pt ✅ |

**Infracciones.**

| Nivel | Criterio | Dónde | Hallazgo |
|---|---|---|---|
| 🔴 | 1.4.3 | Número de la Semana de Aforo | H04 |
| 🔴 | 1.4.3 | Placeholders en claro | H09 |
| 🔴 | 1.4.11 | Punto de no leído de Inicio | H06 |
| 🔴 | 1.4.11 y 1.3.1 | Puntos de las tiras | H07 |
| 🔴 | 1.4.11 | Segmento elegido | H08 |
| 🔴 | 1.3.1 / 4.1.2 | Pasos de «Revisa tu correo» | H12 |
| 🟡 | 2.2.1 | Aviso de 6 s con «Deshacer», sin ajustar | H10 |
| 🟡 | R3.5 de la spec | Bordes de control | H11 |
| 🟡 | R3.3 de la spec | 44 frente a 48 dp en Android | H21 |

**Lo que pasa.**

| Criterio | Cómo se cumple |
|---|---|
| 2.5.7 Arrastre y gestos | Deslizar la fila tiene `accessibilityActions` (`bandeja/index.tsx:219-228`). La tira de días tiene «semana anterior» y «semana siguiente» (`header.tsx:208-230`). No hay `onLongPress`. |
| 2.5.8 Tamaño del objetivo | `TOUCH = 48`. Botones, filas, chips (36 + 12) y horas (40 + 12) pasan. |
| 1.4.4 / Dynamic Type | Sin `allowFontScaling={false}`, con `maxFontSizeMultiplier` por estilo según la tabla de Apple (`type.ts:96-115`). |
| 2.3.3 / Reducir movimiento | Respetado. |
| 3.3.1 / 3.3.3 | Errores en palabras y con icono, bajo el campo y anunciados (`entry-field.tsx:83`). |
| 3.3.8 Autenticación accesible | `autoComplete` y `textContentType` en correo y contraseña; mostrar y ocultar; Google. |
| 4.1.3 Mensajes de estado | Aviso breve con `announceForAccessibility`; `accessibilityRole="alert"` en los errores. |
| 1.4.1 Solo color | Pendiente y cancelada con icono o palabra; sin leer con tinta en la Bandeja; el elegido con ✓. |

**Puntuación: 4/10. Veredicto: PARTIAL (6 🔴).**

El arreglo que más sube la nota cuesta poco, porque está en los tokens:

- `placeholderTextColor` → `mutedForeground`;
- puntos en `highlightInk` en claro;
- `fg` del nivel 3 → `onHighlight`;
- borde en el segmento elegido.

Con eso y H12 quedaría en 7–8/10. Hace falta una pasada viva con TalkBack, y otra con VoiceOver cuando haya simulador.

## Puerta 6 · `design-tokens`

| Comprobación | Resultado |
|---|---|
| Una sola fuente | ✅ `packages/ui/.../tokens.css` → `scripts/gen-tokens.mts` → `tokens.gen.ts`, con `gen:check` byte a byte. |
| Hex, `rgb()` o colores con nombre en pantallas | ✅ **Ninguno** fuera de `*.gen.ts`; solo `"transparent"`, que es correcto. |
| Estilos en línea para tema | ✅ Todos los colores salen de `useTheme().colors[rol]`. |
| Contraste calculado | 🔴 H04, H06, H07, H08 y H09 (pares en la tabla de arriba). |
| Tokens fantasma o desfase con el plan | 🟡 D2 promete `controlBorder`, `warningTint`, `successText`, `successTint` y `bubbleMine`, que no existen. No los usa ninguna pantalla (no hay fantasmas en el código), pero R3.5 se queda sin rol (H11). |
| Fuera de escala | 🟡 Dos escalas de radio (H20). `fontSize` literal en `app/conversacion/[id]/contacto.tsx:346` (16) y en `features/inbox/thread/composer.tsx:196` (17): deberían ir con `type.body`, porque en Android `body` es 16 y el cuadro de escribir sale a 17. |
| Riesgo de «slop» | ✅ Tipografía del sistema por decisión (Helvena apagada hasta la licencia); paleta corta; oscuro sin negro ni blanco puros. |

**Puntuación: 4/10** (hay 🔴 de contraste calculado). Sin H04–H09 sería 8/10.

**Veredicto: PARTIAL.**

## Contraste con el inventario de diseño

Sin las decisiones de `log.md`. Solo diferencias que se ven y que importan para las capturas o para el uso:

| Pantalla | Diferencia | Hallazgo |
|---|---|---|
| Conversación en espera | Dock de seis bloques frente a la franja de una línea; ámbar fuera de la mano | H03 |
| Cuadro de escribir | Tres filas sueltas frente a la cápsula con «+» y enviar dentro | H18 |
| Consumo | Fecha en título y barra frente a una línea muted | H14 |
| Ajustes | Fila de rol con un texto fijo (el diseño dice «Dueña», y la spec lo deja fuera) | H22 |
| Tiras de días | «today» en minúscula en inglés, un defecto del demo que el inventario pedía unificar | H17 |

**Coincide con el diseño:**

- la composición de Inicio: cuatro tarjetas, lo último con dos o cuatro filas, quien espera abajo y la tarjeta calma;
- las filas de la Bandeja: avatar con logotipo, «Espera», «Tú», punto y grupos por día;
- los chips con su número y el ✓;
- la cuadrícula con solapes lado a lado y la línea de ahora;
- Nueva reserva, con las horas en mañana y tarde y las ocupadas tachadas;
- Entrar, con el líquido, la tarjeta, mostrar y ocultar, y Google;
- el preaviso de los avisos, con el ejemplo real.

## Sin verificar y para la 070

- **H01**, con un aviso real en un build que no sea de desarrollo, con la app muerta y con la app en segundo plano.
- **Todo iOS:**
  - vidrio y «Reducir transparencia» (R1.8 y R1.9);
  - la lente del sistema (R2.2);
  - título grande con Dynamic Type AX5;
  - VoiceOver en el dock, la Bandeja (acciones de fila) y Nueva reserva.
- **Capturas en español**, en claro y en oscuro, y con el texto de Android a 1,3 y a 2,0.
- **Un pase con TalkBack:**
  - orden de foco de Inicio;
  - anuncio único del aviso breve (H10);
  - acciones de fila.
- **R22:** arranque en frío, 1.000 conversaciones y fps del líquido en un Android de gama media.
- **El contraste del titular de Entrar** sobre el líquido animado cuando la zona clara pasa por detrás. No se puede medir en estático.
