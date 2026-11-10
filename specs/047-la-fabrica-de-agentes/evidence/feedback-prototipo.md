# La consola frente al prototipo aprobado — comentarios de Andrés · 2026-10-28

Fuente de la verdad de diseño y experiencia: el prototipo «Consola de partners v2»
(`index.html` + `icons.js`, vista «Prototipo»). Capturas de cada pantalla del
prototipo, en claro y en oscuro, en el scratchpad de la sesión del recorrido
(`proto/*.png`).

Andrés va añadiendo comentarios. Cada uno, con lo que muestra el prototipo y lo que
hace hoy la consola.

| # | Comentario | Prototipo | Consola hoy |
|---|---|---|---|
| 1 | Los placeholders del alta son de una barbería: deben ser generales, sin aludir a ningún nicho | También usa «Barbería Cultor»: **el comentario cambia el prototipo** | «Barbería Cultor», «Barbería de barrio con 2 sedes», «cultorbarber.com · @cultorbarber» (`clients/client-modal.tsx`, textos en `i18n`) |
| 2 | «Más ajustes» solo con zona horaria y moneda (EUR o USD) | «Más ajustes · Europe/Madrid · EUR»: Zona horaria y Moneda de cobro | País, Zona horaria, Moneda de los precios, Moneda de la bolsa y Solo UE |
| 3 | En general la consola no se parece al prototipo en experiencia ni interfaz | — | Ver la tabla por pantalla de abajo |
| 4 | El constructor es para los agentes, no para el tab Negocio | Negocio sin tarjeta del constructor | Tarjeta «Completar con el constructor» encima de Negocio |
| 5 | El Panel no es el aprobado | «Hola, Luis · Ladrian Studio · fecha»; cuatro cifras arriba (gasto del mes con barra por cliente, conversaciones con tendencia, clientes atendiendo, saldo con barra); «Conversaciones por día»; «Necesita tu atención» debajo, con «⋯» | «Necesita tu atención» primero, con un botón por fila; otras tarjetas y otro orden |
| 6 | El menú lateral está organizado distinto | Grupos con etiqueta «OPERAR» y «CUENTA» | Sin etiquetas de grupo (`nav-v2.ts`, decisión R47.1 de la spec), cuenta abajo |
| 7 | Falta el sistema de diseño de vidrio (liquid glass) aprobado | Vidrio en la barra de pestañas, la barra de guardar flotante, los modales y los menús | Vidrio solo en la capa flotante; pestañas y barras opacas |
| 8 | Nada del constructor se muestra en la interfaz: trabaja por dentro | El constructor no tiene nombre en pantalla (el agente se describe y se configura) | «Completar con el constructor», «Lo que proponen el constructor y el copiloto», el progreso del borrador por bloques |

## Diferencias por pantalla (vistas hasta ahora)

- **Agente**: el prototipo tiene cuatro pestañas en vidrio («Rendimiento ·
  Configurar y probar · Canales · Integraciones»), una tabla compacta de cinco
  filas (Qué hace, Cómo habla, Qué sabe, Qué puede hacer, Cuándo pasa a una
  persona) con lápiz por fila, a la derecha las pruebas y el chat de prueba, y una
  barra de guardar flotante. La consola tiene una página larga con once secciones
  ancladas (Borrador, Conocimiento, Canales, Conectores, Recepción, Rendimiento,
  Mejoras, Pruebas, Revisión, Historial y Avanzado).
- **Negocio**: el prototipo lee cada sección en modo lectura con «Editar», índice
  con marcas, y secciones «Documentos y webs» y «Redes sociales». La consola
  enseña formularios siempre abiertos (con el país como código ISO).
- **Nuevo cliente**: ver 1 y 2.

## Primera iteración de alineación (2026-10-28, sin commit)

Hecho, cada cosa con su prueba en rojo primero:

| # | Qué cambió | Dónde |
|---|---|---|
| 1 | Ejemplos generales en el alta: «Nombre comercial», «A qué se dedica, con tus palabras», «Qué vende, a quién y dónde. Pega su web o sus redes.» | `i18n/lanes/business.ts`, `client-modal.test.tsx` |
| 2 | «Más ajustes» solo con Zona horaria y Moneda (EUR o USD); el país, la moneda de los precios y «Solo UE» se deducen y se mandan sin pedirlos | `clients/client-modal.tsx` |
| 4 y 8 | Negocio sin la tarjeta del constructor; ningún texto de la interfaz nombra al constructor («borrador», «sugerido»), también en la lite | `clients/[ref]/business/page.tsx`, `i18n/lanes/{builder,business,money,notices}.ts`, `words.test.ts`, `apps/mobile/src/i18n/lite.gen.ts` |
| 5 | Panel con la composición del prototipo: «Hola, Luis · Ladrian Studio · día», gasto del mes a la izquierda, tres cifras, conversaciones por día y «Necesita tu atención» abajo con «N de M clientes sin problemas» y ⋯ por fila | `home/partner-panel.tsx`, `home/today-date.tsx`, `app/(console)/page.tsx`, `PageHeader size="display"` |
| 6 | Menú lateral con los grupos «Operar» y «Cuenta» | `shell/console-shell-v2.tsx` |
| 7 | Vidrio en las pestañas del cliente y del agente, y en la barra de guardar flotante | `clients/v2/client-header-v2.tsx`, `builder/agent-builder.tsx` |
| 3 | Cabecera del cliente como el prototipo (nombre grande, nicho y desde cuándo atiende, pestañas con el número de agentes y «Nuevo agente»). Pantalla del agente: título del agente con «de {cliente}», cuatro pestañas, tabla compacta de bloques con lápiz, «Guardar» flotante; las páginas de un agente no repiten la cabecera del cliente | `client-header-v2.tsx`, `agent-builder.tsx`, títulos de `builder-new`, `archived-agent` y `channel-page` |

La spec (historias 14 y 27, requisito del alta y del constructor) y
`docs/console.md` dicen ya lo mismo.

## Lo que falta para que se parezca del todo

- **Agente › Configurar y probar**: el prototipo tiene cinco filas (Qué hace, Cómo
  habla, Qué sabe, Qué puede hacer, Cuándo pasa a una persona) y a la derecha solo
  las pruebas y el chat de prueba. La consola tiene nueve bloques (los del
  AgentSpec) y debajo conocimiento, recepción, pruebas, revisión, historial y
  Avanzado; a la derecha, probador, copiloto y propuestas.
- **Negocio**: modo lectura con «Editar» por sección, índice con marcas y las
  secciones «Documentos y webs» y «Redes sociales».
- **Lista de clientes, Consumo, Auditoría, Equipo, Facturación, API, Guía y
  Teammate**: sin comparar todavía pantalla a pantalla.
- **Tamaños**: el menú lateral del prototipo usa letra de 15 px; la consola, 14.

## Decisiones para Andrés

1. **«Integraciones» o «Conectores».** La pestaña del prototipo dice
   «Integraciones»; la regla de palabras de la consola dice «conector» (y la
   Auditoría ya lo cambió, migración 0203). Se ha dejado «Conectores».
2. **El copiloto** no está en el prototipo. ¿Se quita de la pantalla del agente o se
   queda a la derecha?
3. **Las propuestas del constructor para la ficha** ya no se ven en ningún sitio
   (se quitó la tarjeta de Negocio). ¿Se aplican marcadas «Sugerido · confírmalo»
   como la lectura de la web, o no se generan?
4. **El rol «Constructor»** del equipo sigue con ese nombre.
5. **La tendencia de conversaciones** («↑ 27 % más que los 7 días anteriores») no
   sale: el bloque `panel` de la API no trae la semana anterior.

## Segunda iteración: el flujo completo del prototipo (2026-10-28, sin commit)

Andrés pidió recorrer el flujo completo del prototipo y llevarlo tal cual al código,
con las skills de diseño (impeccable, glassmorphism, critique, movimiento). El
análisis pantalla a pantalla, con textos, estados, acciones y huecos, está en
`evidence/prototipo/`: `marco-y-cuenta.md`, `clientes.md` y `agente.md`.

**Sistema de diseño** (`packages/ui`, también lo ven el panel y la lite): el vidrio
del prototipo (60 %, 22 px, canto de luz y sombra), radios de 12 px en tarjetas y
menús y 16 en lienzo y diálogos, el título de 40 px (`text-display`), botones y
campos de 36 px con radio 8, insignias con el texto en el color de su tono, el menú
lateral de 256 px con el activo en verde suave, avisos abajo en vidrio, el control
segmentado de vidrio y los colores del chat de prueba. Detalle en
`docs/console.md` › «Sistema visual».

**Pantallas**: Negocio en lectura con «Editar» por sección y seis secciones (con
Documentos y webs y Redes sociales); lista de clientes; Panel del cliente; Panel
del partner (cifras de 28 px, tendencia semanal, «Ver N más»); el agente
(«Configurar y probar» con cinco filas, pruebas y chat a la derecha, barra de
vidrio); Consumo, Auditoría (sin el «N más como esta» repetido), Guía del partner,
Teammate, Equipo, Facturación, API y Notificaciones.

### Lo que todavía no es como el prototipo

- **Canales del agente**: el asistente de cuatro pasos, las tarjetas de canal, el
  modal Coexistencia / Cloud API y la configuración del canal dentro de las
  pestañas (hoy es otra página).
- **Nuevo agente**: el prototipo lo hace en la propia pantalla del agente, con
  ejemplos, los cuatro pasos y las preguntas una a una.
- **Servicios**: edición en la fila y «Eliminar» con «Deshacer» (hoy un diálogo y
  «Archivar»). **Redes sociales**: el grupo con el logo de cada red.
- **Modal «Asignar saldo»**: sus textos (H12 de `clientes.md`).

### Huecos de la API (el prototipo enseña datos que la API no da)

- Tarjetas de agente: qué hace, canal y número, gasto del mes (`AgentOut`).
- Las preguntas pendientes de un agente ya creado (`open_questions`).
- El avance «N de 20» de las pruebas en curso; la relación de una prueba que falla
  con su conector.
- Conversaciones por franja del día (Panel); el «Le queda» de Consumo.
- Comprar saldo en euros (el cobro es en dólares).
- «14 páginas leídas» en Documentos y webs.

### Decisiones para Andrés

1. «Integraciones» (prototipo) o «Conectores» (regla de palabras). Se dejó «Conectores».
2. Vocabulario del estado: la lista de clientes dice «Al día» como el prototipo; los
   agentes siguen con «Atendiendo» (requisito 25.5) y no «Publicado».
3. El copiloto y las propuestas no están en el prototipo: quedaron dentro de «Más
   ajustes».
4. Las propuestas de ficha que hace el sistema por dentro ya no se ven en ningún
   sitio.
5. El rol de equipo «Constructor» sigue con ese nombre.
6. El prototipo dice que guardar la ficha vuelve a pasar las pruebas. La API no lo
   hace: la consola dice «Los cambios se aplican desde el siguiente mensaje».
7. Archivar un cliente ya no pide confirmación (se deshace con «Deshacer»), como
   el prototipo.

## Tercera ronda: los comentarios de Andrés en local (2026-10-28)

Hecho: Equipo, Facturación y API en el menú del perfil; el tema como interruptor
junto a la campana; botón redondo de volver junto al título; un solo botón
primario por vista; los arreglos de «Necesita tu atención» dentro del «⋯»; la
columna Estado sin lo de los agentes; el Panel del cliente solo con Saldo, Este mes
y Agentes que más consumen; redes con su logo y solo el usuario (el enlace se arma
solo); el alta de canales del prototipo (cuatro pasos, tarjetas, «Conectar
WhatsApp»); el lateral que se pliega sin saltos; las gráficas de cuadros del
prototipo; insignias con icono en línea; pestañas sin números; la campana con
borde; «Configuración» en vez de «Configurar y probar»; el chat de prueba arriba;
tono e idiomas en desplegables; y el alta de un agente como el prototipo
(describir, preparar el borrador con sus pasos, preguntas una a una).

Pendiente:
- `apps/console/e2e/builder.e2e.ts` describe el flujo viejo del agente nuevo (el CI
  no corre Playwright; hay que reescribirlo).
- Decisión D3 de `agente.md`: el flujo del agente nuevo habla en primera persona
  («Leo…», «Me faltan…»), como el prototipo.
- Las preguntas respondidas se recuerdan en la sesión del navegador: la API no
  devuelve las respuestas al leer el trabajo.
