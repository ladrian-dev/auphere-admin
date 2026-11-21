# Bitácora de la noche del 2026-11-21 (spec 069)

Luis dejó trabajar toda la noche sin preguntas y lo revisa por la mañana. Aquí está lo que se decidió sin él, lo que se verificó y cómo, y lo que no.

## Para revisar primero

- **iOS se vio la mañana del 2026-11-21** en el simulador iPhone 13 (iOS 26.0, Xcode 26.0.1), con el negocio de ejemplo. Lo que salió está en «iOS en el simulador (mañana del 2026-11-21)», más abajo. Lo más importante: **con el build hecho aquí (Xcode 26.0.1), el código de `develop` se cae al arrancar en iOS** al registrar las categorías de los avisos, por un fallo de Expo sin arreglo publicado. **Con el build de EAS (Xcode 27.1) no se cae**: 0 de 21 arranques, la tarde del mismo día. No es un P0.
- **Android sí se verificó** en el emulador Pixel 9, con datos de ejemplo.
- **Dónde la app se aparta ahora del diseño, por accesibilidad** (revisión de calidad; capturas `evidence/android-claro-reservas-bordes.png` y `android-oscuro-reservas-bordes.png`):
  - los bordes de chips, horas, huecos y bloques son más marcados (tinta al 50 %, 3:1);
  - el segmento elegido (Día, 30 días, lista) lleva borde;
  - los puntos de «sin leer» y de «día con reservas» son de un menta más oscuro;
  - los textos de ejemplo de los campos son más oscuros;
  - el número del nivel más alto de la Semana de Aforo va en tinta oscura.

  Todo sale de cumplir WCAG 2.2 AA (SC-004). Si alguno no te gusta, se cambia el token, no la pantalla.

## Orden del flujo (analyze C2)

La implementación de la Fase 2 (sistema) y el arranque de las áreas empezaron **antes** de que `/speckit-analyze` estuviera en verde. Se hizo así para no perder la noche: el análisis corría en paralelo.

Cuando llegó con 2 críticos y 3 altos, se corrigieron los documentos (C1 Helvena, H1 umbral del líquido, H2 medidas, H3 iOS y Android como puerta de la 070). El análisis se vuelve a pasar al cerrar.

Nada de lo ya escrito contradecía esas correcciones, salvo D3 (Helvena), que no llegó a incrustarse en ningún build.

## Decisiones tomadas sin Luis

1. **044 R16.7 enmendado.** Tomar el control muestra el aviso breve con «Devolver», como en el diseño. Devolver no lo muestra.
2. **Marco menta en la tarjeta «Hoy».** El CSS del demo lo tenía y el JS no lo aplicaba. Se aplica.
3. **Una sola regla para abrir una conversación desde Inicio:** siempre en la pestaña Bandeja.
4. **Modo de datos de ejemplo de toda la app** (Requisito 23), para verificar sin servidor y sin tocar la base compartida ni staging. Solo existe en `__DEV__` con `EXPO_PUBLIC_DEMO=1`.
5. **Helvena apagada en todos los builds** hasta leer su licencia (analyze C1).
   - Los TTF originales están en `~/Downloads/Helvena Font File/TTF/`. Por el nombre del zip, parecen de Envato Elements; el zip no trae texto de licencia.
   - Para activarla:
     1. Confirma la licencia.
     2. Copia `Helvena-Regular.ttf`, `Helvena-Medium.ttf` y `Helvena-Semibold.ttf` a `apps/mobile/assets/fonts/helvena/`.
     3. Construye con `APP_HELVENA=1`.
6. **Iconos del sistema en el cromo nativo** (pestañas, botones de barra y menús nativos), y Lucide en todo lo demás. Lucide se importa icono a icono: Metro no poda el barril, que traería unos 1.600 iconos al bundle.
7. **Las confirmaciones son las alertas del sistema**, no los «diálogos con carácter» del demo (icono en su tono y título en Helvena). En iOS 26 ya son de vidrio, son accesibles y suenan a sistema. Rehacerlas a mano no aporta lo bastante para el riesgo.
8. **El aviso con «Deshacer» dura 6 s** (044), no los 4 s del demo. Da más tiempo para tocarlo (WCAG 2.2.1). La barra de tiempo sí es del diseño.
9. **El «hoy» de la tira de días va en `basil` (#106958)**, no en el `#087F5C` del demo, porque este no llega a 4,5:1 sobre el fondo.
10. **Búsqueda en la cabecera de la Bandeja**, en las dos plataformas (Requisito 10.1, rama «en otro caso»). Queda pendiente la pestaña de búsqueda nativa de iOS 26: según la documentación de SDK 58, su forma completa (`UISearchTab`) llega con expo-router 58.0.26 o posterior, y la app tiene la 58.0.25. Subir de versión y verificarlo en el simulador de iOS es de mañana.

### Decisiones del área Reservas

- **Semana en modo Servicios:** ya no lista ni abre reservas. Cada fila abre su día.
- **La antelación mínima del agente** también se aplica a las reservas nuevas y a los movimientos hechos desde la app. Esto contradice el «Desde aquí puedes reservar cualquier hora» de la web, y el texto de los ajustes lo dice. **A revisar con Luis.**
- **Cancelar y «Quitar» esperan 6 s antes de enviarse**, porque la API no tiene inverso y un WhatsApp no se puede desenviar. «Deshacer» simplemente no lo envía. Si la app pasa a segundo plano, se envía al momento, y después «Deshacer» dice «Ya se había enviado».
- **«Deshacer» tras guardar una reserva la cancela.** Al cliente se le avisa si ya le llegó la confirmación.
- **«Quitar» de la lista de espera ya no pregunta antes:** quita con «Deshacer» (antes pedía confirmación, 044).
- **«Reservarle ahora» deja a la persona en la lista**, como hace la API y como el diseño.
- **Diferencias con el diseño:**
  - servicio y «Con» son chips, no filas que abren un selector;
  - el resumen y «Guardar» van en línea, no en un dock de vidrio;
  - la tira del formulario no marca los días con huecos (haría falta leer 7 veces);
  - la barra conserva el menú ⋯.
- **Las plantillas de WhatsApp de Reservas** se nombran en los ajustes, pero no se listan.
- **Los botones de la hoja de una reserva ya no son mitades iguales** (mañana del 2026-11-21, tras el simulador de iOS).
  - Cada uno toma el ancho de sus palabras en una línea: van juntos si caben, y si no, cada uno en su línea.
  - Con mitades iguales, «Pedir confirmación» se partía dentro de la palabra.
  - Ahora «No vino» y «Marcar confirmada» quedan juntos pero de distinto ancho. Ese caso no se capturó: el negocio de ejemplo no tenía ninguna reserva así cuando se miró.
  - **A revisar con Luis**, por si prefiere mitades iguales y el texto en dos líneas.

### Decisiones del área Bandeja

- «La atiende {agente}» ya no sale en las filas cuando hay un solo agente; sí cuando hay varios o cuando la conversación espera.
- Resolver desde el menú se queda en el hilo y avisa con «Deshacer».
- Deshacer una resolución la reabre con el agente. No recupera «espera» ni «persona», porque la API no lo permite.
- «Esta semana» es la semana de calendario desde el lunes, como en el demo.
- La búsqueda hace dos lecturas (abiertas y resueltas con el mismo `q`), porque la API deja fuera las resueltas salvo en su filtro. Las resueltas salen en su propio grupo.
- Las fotos de los clientes se guardan solo en memoria (`cachePolicy="memory"`, regla de la 031).

### Decisiones del área Entrar

- **«Cuenta de partner» no enlaza la consola web.** La 031 (decisión del owner del 2026-10-20) dice que nada en la app lleva a la consola de partners, hay un test que lo comprueba y la 069 no lo enmienda. Si se quiere el enlace del diseño, hay que enmendarlo.
- **«Revisa tu correo» no tiene «Abrir el correo».** No hay una forma fiable de abrir la app de correo en las dos plataformas sin una dependencia nueva. La acción principal es «Volver a entrar».
- **Los textos del correo de recuperación son los de la API:** el enlace dura una hora (`RESET_TTL`), no los 30 minutos del demo, y el texto es el mismo exista la cuenta o no (spec 011).
- **El líquido de Skia sale del modelo de la consola, generado** (`scripts/gen-liquid.mts`). Hay tres diferencias con el original, todas con los mismos píxeles:
  - las funciones del modelo van en orden de dependencia, porque un worklet captura lo que usa al definirse;
  - `smoothstep` con bordes invertidos se reescribe como `1.-smoothstep(b,a,x)`, porque con los bordes invertidos el resultado no está definido en Metal;
  - `pow(x,2.)` pasa a `x*x`.
- **Se congela si 30 cuadros seguidos pasan de 20 ms**, tras 30 de calentamiento. En un build de desarrollo puede congelarse más que en uno de release: los fps se juzgan en release (T056).

## Verificado

- Base de `develop` en verde antes de empezar: 38 suites y 442 tests.
- Licencias leídas enteras: `react-native-svg` (MIT), `@shopify/react-native-skia` (MIT) y `lucide-react-native` (ISC, con iconos de Feather en MIT).

- El sistema (tokens, letra, iconos, radios, micro, toast y chip) con `tsc` limpio y las 442 pruebas en verde.
- **Integración: `pnpm verify` en verde**, con 64 suites, **740 tests**, `tsc` limpio, lint sin errores ni avisos y `gen:check` (incluido `gen-liquid`).
- **Al cierre, tras los arreglos de la revisión y de la segunda pasada de `/speckit-analyze`: `./scripts/verify.sh mobile` en verde**, con 66 suites, **790 tests**, `tsc` limpio, lint, `gen:check` y el contrato OpenAPI al día (04:58), tras `/cso`, la pasada `responsive-audit` y la tercera de `/speckit-analyze`.
- **Tras la pasada de iOS (mañana del 2026-11-21, 14:05): `./scripts/verify.sh mobile` en verde**, con 67 suites, **799 tests**, `tsc` limpio, lint, `gen:check` y el contrato OpenAPI al día.
- La app arranca en el emulador Pixel 9 (Android 16) con SVG, Skia y Lucide nativos, en un build de desarrollo arm64 nuevo (6 min).
- `push.test` falló una vez con la máquina cargada (build de Gradle en paralelo) y pasó al repetir: es de tiempos, no del cambio.

- **En el emulador Pixel 9 (Android 16), con el negocio de ejemplo** (capturas en `evidence/`):
  - Entrar, con el líquido vivo de Skia y el error bajo el campo;
  - el preaviso de los avisos y el permiso real del sistema;
  - Inicio, con las cuatro tarjetas, lo último y quien espera;
  - Consumo;
  - Ajustes, con los canales conectados;
  - la Bandeja: grupos por día, quien espera primero, filtros, búsqueda (abiertas y resueltas), deslizar para resolver y «Deshacer», que la devuelve a la lista;
  - una conversación: cabecera, dock, «Corregir» y el pie con la ventana del agente vencida;
  - Reservas: tira de días, lista del día con sus estados y filtros por profesional.

### Arreglado tras verlo en el emulador

- **La cabecera de la conversación decía «Atiende Ava» con la ventana del agente vencida**, mientras el pie decía que ya no podía responder (Requisito 11.5).
  - Ahora dice «Ava ya no puede responder», con el punto en gris, con la misma regla que el pie: ventana cerrada para todos, o la del agente vencida con hora de cierre.
  - La lista no conoce la ventana y sigue sin decir nada en esas filas.
  - Test: `v13-bandeja-arreglos`. Evidencia: `evidence/android-claro-ventana-vencida.png`.
- **El negocio de ejemplo y la app no tenían la misma hora.** El ejemplo sembraba el día con un reloj fijo a las 11:20, pero la app lee la hora real del negocio (Santiago), como contra la API. Resultado: reservas «confirmadas» ya pasadas, e Inicio con «No quedan más hoy» a media mañana.
  - Ahora el negocio de ejemplo usa la misma hora real de Santiago (`createDemo(…, { clock: "business" })`).
  - Por la mañana en España es de madrugada en Chile, así que **todas las reservas del día salen por venir**. Es lo coherente.
  - Test: `demo-reservas`.
- **La cápsula de Contacto perdía su última palabra en Android** («Ava can't answer» sin «now»). Es un fallo de Android al partir líneas en una cápsula que se ajusta a su contenido. Ahora va en una línea, con puntos suspensivos si no cabe; el lector la lee entera.
- **TalkBack leía «te digo..» con dos puntos** cuando la vista previa ya acababa en punto. Test: `v13-bandeja-lista`.

### Para revisar (encontrado en el emulador)

- **Barra sin iconos y tarjeta de Inicio bajo la barra: es del cliente de desarrollo, no de la app.**
  - Solo pasa cuando el **cliente de desarrollo** recarga la app dentro de la misma actividad al abrir un enlace (`am start` con el esquema de la app). Ahí la app vuelve a arrancar (el contador de minutos de Lucía se reinicia).
  - Con un **arranque en frío de verdad** (parar la app y abrirla), los iconos y la tarjeta acaban saliendo bien (`evidence/android-claro-arranque-en-frio.png`). Pero mientras se ve el esqueleto, la barra sale sin iconos y con la insignia suelta; los iconos llegan unos segundos después (`evidence/android-arranque-en-frio-iconos-tarde.png`, 03:38). Es un build de desarrollo, que carga el bundle desde Metro; en release no se ha visto.
  - Se probaron dos arreglos (reenviar la barra en Android y cargar antes la fuente de Material Symbols), no cambiaban nada y se revirtieron.
  - **Hay que confirmarlo** tocando un aviso de verdad en un build de staging, que no recarga. Es la tarea T057, puerta de la 070 (revisión, H01).
- **Los interruptores de avisos de Ajustes salían apagados mientras se leían sus datos.** Aquí escribí «no era un fallo», y sí lo era (revisión, H02): sin datos, el aviso urgente parecía apagado, y si la lectura fallaba no había «Reintentar». Arreglado: ahora dice «Leyendo tus avisos…» o el error con «Reintentar», y nunca pinta interruptores sin dato.
- **Consumo:** «Te alcanza hasta el domingo…» (grande) y «Para unos 4 meses…» dicen casi lo mismo. La primera podría bajar de tamaño.

## La revisión de calidad (`revision.md`) y qué se hizo con cada hallazgo

La hizo un agente aparte con las puertas del workspace. No hay ningún hallazgo confirmado de severidad 3 o 4. Los siete fallos AA (SC-004 pide cero) están arreglados, cada uno con su test.

| id | Sev. | Qué | Estado |
|---|---|---|---|
| H01 | 3 sin verificar | Barra sin iconos y tarjeta de Inicio bajo la barra al relanzar con un enlace | **Abierto:** T057, puerta de la 070. En un arranque en frío de desarrollo, los iconos llegan tarde: la barra sale sin ellos mientras carga y aparecen unos segundos después (`evidence/android-arranque-en-frio-iconos-tarde.png`). En release no se ha visto. |
| H02 | 2 | Avisos de Ajustes sin carga ni error | Arreglado (`ajustes-avisos`) |
| H03 | 2 | El dock de «espera» repite el motivo y pone ámbar fuera del icono | **Para Luis:** es decisión de diseño (T059) |
| H04 | 2 · AA | Número de la Semana de Aforo a 2,09:1 | Arreglado: `onHighlight`, 7,38:1 (`v13-revision-aa`) |
| H05 | 2 | La barra de Android solo rotula la pestaña elegida | **Para Luis:** API de `NativeTabs` sin verificar (T059) |
| H06 | 2 · AA | Punto de no leído de Inicio a 2,27:1 | Arreglado: `highlightInk` (`v13-revision-aa`) |
| H07 | 2 · AA | Puntos de la tira a 2,09:1, y el lector no los dice | Arreglado: `highlightInk`, y «, con reservas» en la etiqueta (`v13-revision-aa`) |
| H08 | 2 · AA | Segmento elegido a 1,21:1 | Arreglado: borde `controlBorder` (`v13-revision-aa`) |
| H09 | 2 · AA | Placeholders a 3,6:1 | Arreglado: `mutedForeground` en los cinco campos, y un test que barre `src` |
| H10 | 2 · AA | «Deshacer» de 6 s fijos con lector de pantalla | Arreglado: 20 s con VoiceOver o TalkBack, o lo que pida Android; se anuncia con «Deshacer». La cancelación diferida de Reservas espera lo mismo (`toast`). |
| H11 | 2 | Bordes de control a 1,30:1; `controlBorder` no existía | Arreglado: rol generado y usado en chips, horas, huecos y bloques (`v13-revision-aa`); plan D2 enmendado |
| H12 | 2 · AA | «Qué sigue» se leía como un solo elemento | Arreglado: cada paso con su pista (`v13-entrar-recuperar`) |
| H13 | 2 | El botón flotante tapa la última reserva | **Sin cambio:** al final de la lista no tapa nada, por el espaciador de `screen.tsx:235` (comprobado en el emulador) |
| H14 | 1 | Consumo repite cuánto dura | **Para Luis** |
| H15 | 1 | Punto menta de «Hoy» sin significado | **Para Luis** (ya no se confunde con el de no leído, que ahora es más oscuro) |
| H16 | 1 | «0 reservas · No quedan más hoy» | Arreglado: «Sin reservas hoy» (`v13-inicio-pantalla`) |
| H17 | 1 | «today» en minúscula junto a «Mon» | Arreglado (`v13-revision-aa`) |
| H18 | 1 | El cuadro de escribir no es una cápsula | **Para Luis** |
| H19 | 1 | «⋯» horizontal en Android | **Para Luis** |
| H20 | 1 | Dos escalas de radio | **Para Luis:** 31 usos, refactor aparte (T059) |
| H21 | 1 | `hitSlop` a 44 y no a 48 dp en Android | Arreglado: `slopFor(alto)` lleva al mínimo de cada plataforma, 44 pt o 48 dp (`v13-revision-aa`) |
| H22 | 1 | «Papel: Persona del negocio» fijo | **Para Luis:** lo pide un test de la 031 |
| H23 | 1 | La franja dice «El agente» y la cabecera «Ava» | Arreglado: la franja nombra al agente (`v13-bandeja-arreglos`) |

Además, la pasada `responsive-audit` en el emulador (360 dp de ancho, texto a 1,3, en español): Inicio, Bandeja, Reservas (día, una reserva y Nueva reserva), Consumo, Ajustes y Entrar (`evidence/android-estrecho-grande-*.png`). Nada se corta ni se sale; las hojas suben enteras para dejar libre lo que queda bajo la barra de gestos. Lo que encontró, ya arreglado:
- «Conversaciones» se partía a mitad de palabra en Inicio. Ahora se parte con guion («Conversacio-nes») y sigue escalando (`v13-inicio-pantalla`).
- Reservas decía «25 reservas · 0 sin confirmar». Con todo confirmado, ahora sale solo el total (`reservas-dia`).

## Requisito 20: cada función y la prueba que la recorre (analyze S1)

La segunda pasada de `/speckit-analyze` encontró que T050 prometía «un test por función» sin un mapa que lo enseñara. Este es el mapa. Las pruebas corren en Jest, con iOS como plataforma por defecto; lo visto en el emulador de Android va en la última columna.

| Función (R20.1) | Prueba | Visto en Android |
|---|---|---|
| Filtros de la Bandeja | `bandeja.test.tsx` «filters: all, unread, waiting and resolved…» | sí |
| Filtro por agente | `bandeja.test.tsx` «the agent filter only with more than one agent» | no (el ejemplo tiene un solo agente) |
| Adjuntos: cámara, galería y PDF | `v13-nada-se-pierde` (el menú, nuevo); `atender.test.tsx` (tipo y tamaño) | sí (el menú) |
| Etiquetas y nota | `contacto.test.tsx` «shows the data, the summary, the tags, the note…» | sí |
| Respuestas guardadas | `atender.test.tsx` «a saved reply lands in the box, not sent» | no |
| Corregir respuestas | `corregir.test.tsx` «the agent's answers have «Corregir esta respuesta»…» | sí |
| Motivo de espera | `atender.test.tsx` «says why it waits before «Tomar el control»…» | sí |
| Motivo del envío fallido | `hilo.test.tsx` «a failed send says why» | no |
| Llegó y No vino | `reservas-dia.test.tsx` «offers «Llegó» and «No vino» as the API allows…»; `v13-reservas-hoja` (No vino tras atender) | no (Aforo) |
| Llegada sin reserva | `llegada-nueva.test.tsx` «registers the arrival with its party and name» | no (Aforo) |
| Bloqueos | `reservas-espera-ajustes.test.tsx` «in Aforo, the blocks with «Quitar» and «Bloquear horas»» | no (Aforo) |
| Ajustes de reservas | `v13-reservas-arreglos.test.tsx` «Ajustes de reservas shows the real state of each member» | no |
| Aforo | `reservas-semana-mes.test.tsx` «is a heat map…» | no |
| Lista de espera | `llegada-nueva.test.tsx` «when they do not fit, offers the waitlist instead»; `v13-reservas-espera` | sí (la tarjeta) |
| «Ver en la web» de Consumo | `consumo.test.tsx` «the way to the web is one row…» | sí |
| Los siete avisos con sus enlaces | `v13-nada-se-pierde` (los siete tipos, en tabla); `push.test.tsx`; `fabrica-avisos.test.tsx` | no |
| Solicitar el borrado | `ajustes-avisos.test.tsx` ««Solicitar el borrado» confirms first…» | sí |
| Actualizar | `v13-nada-se-pierde` (la pantalla, nueva); `api-client.test.ts` (el evento) | no |
| Sin acceso y No es cliente | `v13-entrar-cuentas.test.tsx` | no |
| Entrar con Google | `sign-in.test.tsx`, `v13-entrar-signin.test.tsx` | no |

**Lo que falta en Android** queda en la tarea T058, que es puerta de la 070 junto con iOS (T052). El negocio de ejemplo de la app entera es de Servicios, así que lo de Aforo pide otro negocio de ejemplo o staging.

La misma pasada encontró dos fallos más del negocio de ejemplo, ya arreglados:
- **Historial en el futuro.** Con la hora real, una reserva podía decir «Cancelada · Hoy, 08:00» a las 00:10. Ahora ningún suceso pasa de la hora actual (`demo-reservas`).
- **La reserva de Lucía desaparecía los sábados.** Se sembraba «mañana», y el domingo cierra. Ahora va al siguiente día abierto (`demo-reservas`). La prueba `v13-reservas-fuente` fallaba por eso desde la medianoche de Chile, y habría fallado en la tubería cada sábado.

## La auditoría de seguridad (`/cso`, `cso.md`)

Ningún hallazgo crítico ni alto: nada bloquea. El modo de ejemplo solo existe con `__DEV__`, no hay secretos en el cambio y las tres dependencias no traen scripts de instalación.

| id | Qué | Estado |
|---|---|---|
| L1 | `lucide-react-native` va con `^1.77.0`, no fijada como las otras dos | **Para Luis:** cambia el lockfile, que esta sesión no puede leer. `cd apps/mobile && pnpm add lucide-react-native@1.77.0 --save-exact` |
| L2 | Nada impedía importar el código de ejemplo sin el `__DEV__` | Arreglado: regla `no-restricted-imports` en `eslint.config.js` (comprobada con un import de prueba) |
| L3 | La prueba de versión no miraba el `env` heredado ni `APP_HELVENA` | Arreglado (`version.test`) |
| L4 | Los teléfonos de ejemplo (`+34 600 000 0NN`) tienen formato de móvil real | **Para la 070:** antes de hacer capturas de tienda con el negocio de ejemplo, usar números y cuentas claramente inventados |
| L5 | El motor de Skia llega como binarios ya compilados | Anotado: revisar los hashes del lockfile en cada subida de versión |
| I1–I3 | Enlace de Meta sin comprobar el esquema; Helvena como riesgo de licencia; 26 avisos de `pnpm audit` en herramientas de build, anteriores a la 069 | Anotados. I3 merece una tarea aparte |

## `/speckit-analyze` al cierre

Tres pasadas en `analyze.md`. La tercera queda **en verde**: ningún crítico ni alto abierto (11 MEDIUM y 19 LOW). Lo que queda va con tarea:
- T057 y T058: Android, puerta de la 070, ya también en R22.5;
- T059: decisiones de diseño;
- T060: lo abierto dentro de tareas marcadas y lo aplazado de `/cso`.

De esa pasada también se arregló N5: el selector lista/cuadrícula medía 44 dp de ancho en Android, y ahora mide 48.

## iOS en el simulador (mañana del 2026-11-21)

iPhone 13 con iOS 26.0, build de desarrollo hecho con Xcode 26.0.1, Metro con el negocio de ejemplo. La app, en español por idioma de app.

**Se vio bien:**

- Entrar, con el líquido;
- el preaviso de los avisos;
- Inicio;
- la Bandeja, deslizar incluido;
- una conversación, tomando el control;
- Reservas y la hoja de una reserva;
- Nueva reserva con el teclado;
- Consumo y Ajustes;
- modo oscuro, texto grande y «Reducir transparencia»;
- la cabecera y la cápsula de Contacto en español.

Con texto grande, las tarjetas de Inicio pasan a una columna y «Conversaciones» cabe en una línea: el guion de corte es solo de Android. Las capturas están en `evidence/ios-*.png`.

**Arreglado tras verlo:**

- **Los botones compactos y los que van de dos en dos apilaban el icono sobre el texto** («Devolver», «Pedir confirmación»).
  - En iOS, una fila con `flexWrap: "wrap"` manda el texto a otra línea en cuanto no cabe.
  - Ahora la fila del botón nunca se parte; el texto se parte al lado del icono.
  - Afecta a todos los botones de las dos plataformas. Repasado en Android a tamaño 1,0 y 1,3: Inicio, la hoja de una reserva y el pie de la conversación con «Devolver» (`evidence/android-texto-grande-devolver.png`, `android-texto-grande-atender.png`).
  - Test: `v13-revision-aa`, «found in the iOS simulator (T052)».
- **Una imagen que no carga se quedaba en gris para siempre** en la conversación.
  - Ahora vuelve a la ficha de archivo, con «Abrir».
  - Test: `hilo`.
- **«¿Salir sin guardar?» volvía a preguntar en bucle** al cerrar Nueva reserva deslizando la hoja.
  - En iOS, el gesto de la hoja y el `usePreventRemove` se pisaban.
  - Ahora `features/reservas/discard-guard.ts` guarda la salida pedida y la despacha una sola vez, con la guarda ya apagada.
  - Visto en el simulador: «Salir sin guardar» cierra al primer toque y «Seguir aquí» deja la hoja con lo elegido (`evidence/ios-claro-salir-sin-guardar.png`).
  - **Queda un fallo de R15.3:** si se desliza la hoja alrededor de un segundo después del primer cambio, iOS la cierra antes de saber que no debía. La pregunta llega tarde y lo elegido se pierde. La app no se queda atascada: la hoja vuelve a abrirse.
  - Se vio en el build de desarrollo; en uno de tienda está sin mirar, y que vaya más rápido es una suposición. Comprobarlo es parte de T061, puerta de la 070.
  - Test: `v13-salir-sin-guardar`.
- **«Pedir confirmación» se partía dentro de la palabra** («confirmació / n») junto a la campana, en la hoja de una reserva.
  - Lo trajo el arreglo de los botones: con dos mitades iguales, la palabra no cabía al lado del icono.
  - Ahora cada botón toma el ancho de sus palabras en una línea. Si dos caben, van juntos; si no, cada uno en su línea (`evidence/ios-claro-reserva-acciones.png`; con texto grande, `ios-texto-grande-reserva-acciones.png` y, en Android a 1,3, `android-texto-grande-reserva-acciones.png`). Es un cambio de aspecto: está en «Decisiones del área Reservas».
  - Test: `v13-reservas-hoja`, «side by side only when their words fit».
- **Cancelar con «Deshacer»**, visto en el simulador: la reserva sale tachada, el aviso dice «Reserva cancelada» con su barra de tiempo y «Deshacer» la devuelve a «Sin confirmar» (`evidence/ios-claro-cancelar-con-deshacer.png` y `ios-claro-cancelar-deshecho.png`).

### La caída de las categorías de avisos

**Qué pasa.** Al arrancar, la app registra en iOS las cinco categorías de avisos (`ensureCategories`, `src/push/categories.ts`). Es código anterior a la 069.

- En el SDK 58, Expo convierte la respuesta de `setNotificationCategoryAsync` a JavaScript **fuera del hilo de JS**, y eso corrompe la memoria de Hermes (`EXC_BAD_ACCESS`).
- Es un fallo de Expo, abierto y **sin arreglo publicado**: [expo/expo#52462](https://github.com/expo/expo/issues/52462).
  - A 2026-11-21, lo último publicado es expo-modules-core 58.1.0, expo-modules-jsi 58.0.23 y expo-notifications 58.1.9, y ninguna toca ese camino.
  - El arreglo de fondo es un borrador: [expo/expo#51727](https://github.com/expo/expo/pull/51727).

**Medido en el simulador** (iPhone 13, iOS 26.0), con un build de desarrollo hecho aquí con **Xcode 26.0.1**. Esa versión está por debajo de la mínima que pide `docs/app-movil.md` para el SDK 58 (26.4).

| Código | Arranque normal | Arranque y recarga del bundle a los 3 s |
|---|---|---|
| `develop`: las cinco a la vez (`Promise.all`) | **5 de 5 se caen** | — |
| 069: una a una, en cola | **0 de 6** | 5 de 6 se caen |

- **Cómo se midió.**
  - *Arranque normal:* app cerrada, enlace a Metro y 16 s de espera, contando los informes de caída nuevos.
  - *Columna de la recarga:* otro protocolo. Abrir la app, a los 3 s el enlace a Metro, que recarga el bundle, y 14 s de espera.
- **Con este build, el código de `develop` se cae al arrancar.** No está probado que pase con lo que se publica:
  - el mismo código corrió en este simulador en las specs 042 y 044, con builds de EAS (Xcode 27), sin que conste una caída;
  - los tres informes del issue de Expo son de Xcode 26.0.1.
- El arreglo va en su propio commit, el primero del guion, para poder llevarlo a `develop` solo. Test: `push`, «categories one at a time».
  - Con EAS no se reprodujo (abajo), así que no es un P0: entra con el resto de la 069. Luis ya hizo los commits (`5feb963e`).
- **El arreglo solo estrecha la ventana.** Si JS está ocupado cuando llega la respuesta, se cae igual, como al recargar el bundle en pleno arranque (cosa de desarrollo).
  - La caída de las 13:17 fue con ediciones seguidas y recargas a mano; no se sabe si hubo recarga en ese momento.
- Llamar a la función una sola vez no evita la conversión. Comprobar antes con `getNotificationCategoriesAsync` tampoco sirve, porque devuelve lo mismo por el mismo camino.

**Con el build de EAS (tarde del 2026-11-21, T061).**

- El build `development-simulator` de EAS, del commit `3c4ccb11`, se compiló con **Xcode 27.1**. Lo dice `DTXcode` 2710 en su `Info.plist`; el local tenía 2601. Se instaló en el mismo simulador iPhone 13 con iOS 26.0, con el mismo Metro: solo cambia la versión de Xcode.
- Con la sesión iniciada y en Inicio, igual que por la mañana:

  | Código | Arranque normal | Arranque y recarga del bundle a los 3 s |
  |---|---|---|
  | `develop`: las cinco a la vez | **0 de 6** (y 0 de 3 sin sesión) | 0 de 6 por las categorías |
  | 069: una a una | **0 de 6** | — |

- La recarga tiró la app una vez de seis, pero no por las categorías. Fue en el hilo de JavaScript, en el renderizador de React, mientras la recarga deshacía la pantalla. No hay ningún marco del camino de las categorías en ningún hilo. Es cosa de recargar en desarrollo.
- **Conclusión: el fallo de Expo depende del build hecho con Xcode 26.0.1.** Coincide con el issue: sus tres informes son de esa versión, y con Xcode 27.1 Expo tampoco lo reprodujo. `develop` no se cae con lo que publica EAS.
- El arreglo de la 069 se queda: no cuesta nada y cubre a quien compile en local con un Xcode antiguo. Para compilar iOS en local hace falta Xcode 26.4 o posterior (`docs/app-movil.md`); este Mac tiene el 26.0.1.
- Falta, de T061, arrancar el build de staging en un iPhone. Si alguna vez se cae ahí, la salida es registrar las categorías en nativo (un config plugin con `UNUserNotificationCenter.setNotificationCategories`), que no pasa por esa conversión.

**No es de la app:**

- Deslizar una fila de la Bandeja desde la derecha fallaba a veces. Lo tapaba el botón flotante «Tools» del cliente de desarrollo. Escondiéndolo desde el menú de desarrollo, el gesto funciona. En un build de tienda ese botón no existe.

## Helvena en todos los builds (tarde del 2026-11-21)

- Luis confirmó la licencia de Helvena y la guarda él.
- Los tres TTF estáticos (`Regular`, `Medium`, `Semibold`) se versionan en `apps/mobile/assets/fonts/helvena/`. Son los de `~/Downloads/Helvena Font File/TTF/`, con familia tipográfica «Helvena» y pesos 400, 500 y 600.
- `app.config.ts` la incrusta siempre. `APP_HELVENA=0` la quita en un build local, para medir la fuente del sistema (R22). Si falta un archivo, el build se para en lugar de salir sin la marca.
- Test: `version`, «every build carries Helvena».
- **Ojo al probar en local:** si `ios/` o `android/` ya existían, `expo run` no los regenera y el build sale sin la fuente. Hay que pasar antes `npx expo prebuild`. Pasó aquí la primera vez.

## Builds de staging y tiendas (tarde del 2026-11-21)

- Los dos builds salen del commit 31eb8856 de esta rama. Lo que `develop` tiene además es de la consola, nada de `apps/mobile`.
- **iOS:** build 4 del perfil `staging`, terminado en EAS y enviado a TestFlight. Dentro del `.ipa`: las tres caras de Helvena en `UIAppFonts` y el `PrivacyInfo.xcprivacy` de la app (razones de `UserDefaults`, marcas de tiempo y hora de arranque; `NSPrivacyTracking: false`), con la lista de datos recogidos vacía.
- **Android:** el build de `staging` falló dos veces en EAS (builds 6 y 7; el segundo, `eb255a27-…`), las dos en «Run gradlew» con «Gradle build daemon disappeared unexpectedly». En el segundo, Gradle murió durante `:app:minifyReleaseWithR8`, con la compilación nativa de react-native-screens y react-native-worklets en paralelo para cuatro arquitecturas y `-Xmx4g`: es memoria de la máquina por defecto. Sin AAB de la 1.3.0, no hay prueba interna en Play. Las salidas y lo que decide Luis, en `apps/mobile/store/README.md`.
- **Precios en dólares**, por la excepción de cambio trivial de `docs/spec-driven-development.md`: solo cambia el negocio de ejemplo, que ningún build de tienda lleva (test `version`, 23.2). El negocio de ejemplo cobraba en pesos chilenos y en euros. Luis: «todo debe estar en usd, todavia no manejamos multimoneda». Los servicios de Reservas, la seña de Lucía, el presupuesto de Valentina y el precio del blanqueamiento pasan a dólares (`reservas-demo.ts`, `demo/data.ts`; test `demo-router`).
- **Fichas y capturas** en `apps/mobile/store/`: App Store y Play en español e inglés, notas para App Review, privacidad de las dos tiendas con el mismo inventario, y siete capturas por tienda, las de Android ya del emulador. `check_limits.py` comprueba los límites de longitud; encontró la descripción breve de Play en 83 de 80 y una palabra clave repetida del nombre, ya corregidas.
- La imagen destacada de Play pasa de SF Pro a Helvena: la licencia de SF Pro solo cubre maquetas de software de Apple.
- Visto al hacer las capturas, sin tocar: la razón de la espera sale dos veces en la conversación (H03); Reservas enseña servicios de barbería bajo el nombre de una clínica; y el negocio de ejemplo suena a España («podéis», «os paso», «23,91 US$» con la app en es-ES) mientras las fichas son para Latinoamérica.

## Pruebas que dependen de la fecha

Dos suites construyen el negocio de ejemplo con la fecha real: `reservas-demo` y `v13-reservas-fuente`. Se pasaron con el reloj desplazado a domingo al mediodía, a lunes de madrugada, a sábado de noche y a domingo de madrugada (hora de Chile), con un parche de `Date` temporal. Las cuatro en verde. Las demás fijan la fecha.

## No verificado

- Las cifras de rendimiento del Requisito 22 (arranque, 1.000 conversaciones y fps del líquido): piden un teléfono real.
- En iOS: la pestaña de búsqueda nativa de iOS 26 (T060) y VoiceOver.
- En un iPhone real, nada: solo simulador.

## Tests existentes enmendados

| Test | Por qué |
|---|---|
| `__tests__/states.test.tsx` | `CARD_RADIUS` pasa de 12 a 16 (D4, tarjetas del diseño), y el botón de icono se construye con `icons.more`, porque `IconName` lleva ahora su glifo de Lucide. |
| `__tests__/inicio.test.tsx` | Inicio del diseño (Requisito 8, que enmienda la 044 R9 y la 042 R5).<ul><li>Las cifras se buscan por la frase de cada tarjeta.</li><li>La atención pasa a la tarjeta de abajo («+N más»).</li><li>Sin bloque «Necesita tu atención», sin grupo de dinero con medidor, sin barras de conversaciones y sin filas «Ver …».</li><li>Se añade el test de que «Atender» abre la conversación en la pestaña Bandeja.</li></ul> |
| `__tests__/consumo.test.tsx` | La etiqueta del gráfico ya no dice «en dólares» (21.1). Nueva línea «Para unos N días…» (18.1). «¿Necesitas más saldo? Pídeselo a …» (18.2). |
| `__tests__/ajustes-avisos.test.tsx` | Mock de los ajustes de la Bandeja (17.2). La fila de la web se busca en su sección, porque privacidad y soporte también son enlaces externos (19.1). |
| `__tests__/demo-router.test.ts` | Cubre las rutas de ejemplo nuevas de los ajustes de la Bandeja. |
| `__tests__/sign-in.test.tsx` | Sin rellenar los campos, el error va bajo el campo que falta: «Escribe tu contraseña.», no «Escribe tu correo y tu contraseña.» (5.4; Historia 7, escenario 1). |
| `__tests__/bandeja.test.tsx` | Bandeja del diseño (9.1, 9.2, 9.7, 10.1).<ul><li>Simulaciones nuevas: lista con canal, gesto, aviso breve y React Query.</li><li>Etiqueta hablada con canal y «Espera a una persona».</li><li>Chips con su número.</li><li>Búsqueda con espera.</li><li>Grupo «Hoy».</li><li>Pie sin «WhatsApp».</li></ul> |
| `__tests__/atender.test.tsx` | El botón de enviar solo existe con texto escrito (micro 7, Historia 2), y el control del modo propio pasa a `composer-input`. |
| `__tests__/fabrica-avisos.test.tsx` | «Necesita humano.» pasa a «Espera a una persona.» (9.1). |
| `__tests__/llegada-nueva.test.tsx` | Tres tests:<ul><li>el día se pulsa por su nombre completo (tira de 7 días);</li><li>4 celdas de relleno en lugar de 3 (las horas ocupadas se quedan en su sitio);</li><li>«Guardar» siempre responde y dice lo que falta: el teléfono es obligatorio y se envía (15.1, 064 R3).</li></ul> |
| `__tests__/reservas-semana-mes.test.tsx` | Semana como filas con ocupación que abren el día, y Mes con puntos y números en lugar de % (13.5, que enmienda la 044 R3.1 y R3.3). |
| `__tests__/tabs.test.tsx` | El icono de la pestaña Reservas lleva además su glifo de Lucide: `toMatchObject` en lugar de `toEqual`. El símbolo del sistema no cambia. |
| `__tests__/v13-inicio-pantalla.test.tsx` | Un día sin reservas dice «Sin reservas hoy», no «No quedan más hoy» (revisión, H16). |
| `__tests__/v13-bandeja-arreglos.test.tsx` | Con la ventana cerrada, la franja nombra al agente como la cabecera (H23). La frase de la consola queda para cuando no hay nombre. |
| `__tests__/ajustes-avisos.test.tsx` | La simulación de `useNotices` acepta carga y error (H02). |
| `__tests__/demo-reservas.test.ts` | El ejemplo que compara usa el reloj del negocio, como el de la app (`clock: "business"`). |
| `__tests__/version.test.ts` | 1.2.0 pasa a 1.3.0 (Requisito 22.1), y el test también comprueba que ningún build de tienda lleva `EXPO_PUBLIC_DEMO` (23.2). |
