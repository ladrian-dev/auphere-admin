# Especificación: la experiencia de la aplicación de escritorio

**Rama**: `010-experiencia-app-escritorio` · **Creada**: 2026-09-17 · **Estado**: Borrador

**Entrada**: descripción del usuario: *«Estamos construyendo la app de escritorio
de Auphere y no le hemos dado mucho énfasis al Diseño y UX. […] Necesito que
investiguemos a fondo las diferentes opciones que tenemos para implementar un
diseño similar e incluso mejor, identificar si hay librerías de diseño de
Electron o todo debe ser from scratch, los problemas de UX que tenemos que
debemos arreglar»*, con Claude Desktop como referencia de armazón, estados,
onboarding, avisos y paywall que lleva a la acción.

## Encabezado Auphere *(obligatorio)*

| Campo | Valor |
|---|---|
| **Superficie de confianza** | `0` API de la consola · tramo ya abierto de `3a` (ejecutar en la máquina del partner). **No abre superficie nueva; retira una partición** |
| **Garantías de aislamiento tocadas** | Ninguna de las 7 de `architecture/agent-isolation.md`. Sí toca el **aislamiento de superficies de la cáscara** (002 R12.1, 003): la consola sigue **sin canal** hacia la aplicación, y la partición del puesto se retira al absorberse en la pantalla |
| **Nota de KB que la justifica** | `[[2026-09-17-experiencia-app-escritorio]]` en `/Users/lmatos/Work/Auphere/nexus/research/2026-09-17-experiencia-app-escritorio/_index.md` (cuatro anexos escritos y uno —el de referencias— pendiente de consolidar) · evaluación `.specify/assessments/experiencia-app-escritorio/` (veredicto **go**) |
| **Qué se mide** | **Nada nuevo.** No consume modelo, reloj de máquina ni herramienta de pago. El consumo que la aplicación muestra sale del medidor de la spec 004 |

> La superficie es la misma que ya está abierta. Esta spec **no añade** capacidad
> del agente: reordena lo que la persona ve y recorre dentro de las superficies
> `0` y `3a` (constitución §II). Al absorber el puesto de trabajo en la pantalla
> de operar, la ventana pasa de cuatro particiones a tres.

### Enmiendas que esta spec declara

Dos decisiones firmadas en la evaluación cambian contratos ya construidos. Se
declaran aquí para que no se cuelen:

| Enmienda | Qué cambia | Por qué |
|---|---|---|
| **002 — el puesto de trabajo deja de ser una superficie propia** | La barra inferior de 44 px y su lista de siete funciones desaparecen; emparejar, desemparejar, declarar directorios y el estado de la máquina pasan a la pantalla de operar | La barra fue la superficie **mínima** cuando la pantalla no existía (spec 002). Desde la 003 existe, con las mismas garantías. Absorberla **reduce** superficie: una partición y un preload menos, y elimina por construcción el fallo de las hojas invisibles |
| **003 — la pantalla aprende dónde está la consola** | La pantalla puede pedir que la consola se muestre en una ruta y recibir en qué ruta está, más el rectángulo donde pintarla | Es lo que permite una sola navegación. **No es un canal de la consola hacia la cáscara**: la consola sigue sin `preload` (002 R12.1); quien observa y quien decide es el proceso principal |

---

## Escenarios de usuario y pruebas *(obligatorio)*

### Historia 1 — Una sola aplicación, con armazón de escritorio (Prioridad: P1)

Adrián abre Auphere. La ventana tiene una franja superior propia, con los
controles del sistema integrados, y una lista lateral única: **Hoy**,
**Pendientes** con su número, sus teammates, y debajo **todo lo que hoy ofrece la
consola** según su rol (inicio, clientes, conocimiento, puesto de trabajo,
consumo, auditoría, notificaciones, equipo, claves y facturación). Al elegir
«Consumo», la página de la consola aparece **dentro del panel**, sin su propio
menú duplicado y sin que nada cambie de sitio. La lista lateral marca dónde
está. No existe «cambiar a la consola»: existe ir a una sección.

**Por qué esta prioridad**: es el cambio que convierte tres superficies pegadas
en una aplicación, y del que dependen las demás historias.

**Prueba independiente**: con la aplicación instalada, recorrer las secciones de
operar y de administrar sin usar el menú ni atajos de cambio de superficie, y
comprobar que la lista lateral siempre dice dónde se está.

**Escenarios de aceptación**:

1. **Dado** que la aplicación está abierta en «Hoy», **cuando** Adrián elige una
   sección de administrar, **entonces** esa página aparece en el panel de
   contenido, la lista lateral la marca como activa y la franja superior sigue
   siendo la misma.
2. **Dado** que Adrián está en una sección de administrar y navega dentro de
   ella, **cuando** llega a otra página, **entonces** la lista lateral refleja
   dónde está, y volver a un teammate no recarga ni pierde el sitio anterior.
3. **Dado** un teclado sin ratón, **cuando** Adrián recorre la aplicación,
   **entonces** alcanza la lista lateral, el panel y la zona de estado de la
   máquina, y cada sección se anuncia al llegar.
4. **Dado** que la ventana se estrecha, **cuando** llega al ancho mínimo,
   **entonces** la lista lateral se colapsa sin que ninguna acción quede
   inalcanzable.

---

### Historia 2 — La pantalla no miente (Prioridad: P2)

Adrián abre la aplicación sin red. La ventana aparece pintada con su armazón y
dice que no hay conexión, con un reintento; no se queda en blanco ni finge estar
cargando para siempre, y **no le pide iniciar sesión**. Cuando la red vuelve, lo
que había queda como estaba. Si un hilo no se puede abrir, lo dice y ofrece
reintentar, en vez de pintarlo como una conversación vacía. Si su máquina está
reconectando, la aplicación dice desde cuándo, de qué, y qué puede hacer.

**Por qué esta prioridad**: es la constitución §V aplicada; sin esto, cualquier
mejora visual descansa sobre pantallas que engañan.

**Prueba independiente**: arrancar sin red, cortar la red a mitad de sesión y
forzar un hilo que falla; comprobar que cada caso tiene nombre, causa y salida.

**Escenarios de aceptación**:

1. **Dado** que no hay red, **cuando** Adrián abre la aplicación, **entonces** ve
   el armazón con un aviso de «sin conexión» y un reintento, y **no** se le
   presenta la pantalla de inicio de sesión.
2. **Dado** que la sesión estaba activa, **cuando** se corta la red, **entonces**
   la aplicación dice «sin conexión», conserva lo que Adrián estaba escribiendo y
   reintenta sola; **cuando** la red vuelve, sigue donde estaba.
3. **Dado** un hilo cuya apertura falla, **cuando** Adrián lo selecciona,
   **entonces** ve un error con motivo y reintento, nunca el estado «vacío».
4. **Dado** que la máquina lleva un rato sin conectar, **cuando** Adrián mira su
   estado, **entonces** ve desde cuándo, qué falta para que conecte y una acción;
   y esa misma lectura es la que aparece en las demás partes de la ventana.
5. **Dado** que Adrián cierra la ventana, **cuando** un teammate necesita una
   decisión, **entonces** la aplicación sigue avisando, y salir es una acción
   aparte que advierte si hay trabajo en marcha.

---

### Historia 3 — Avisos que se entienden y un solo número (Prioridad: P3)

Cuando algo pasa, Adrián lo sabe una vez y por el sitio correcto: un error se
queda donde ocurrió, una confirmación breve se va sola, algo que afecta a toda la
vista se queda arriba hasta resolverse, y lo que ocurre con la aplicación en
segundo plano llega como aviso del sistema, con el motivo. El número de cosas que
le esperan es **el mismo** en la lista lateral, en el icono del Dock, en el icono
de la barra del sistema y en Pendientes. Cuando hay una versión nueva, se entera.

**Por qué esta prioridad**: hoy hay siete mecanismos sin regla, tres contadores
distintos y siete sitios donde algo falla en silencio.

**Prueba independiente**: provocar un fallo de cada tipo y comparar los cuatro
contadores; publicar una versión y comprobar que se anuncia.

**Escenarios de aceptación**:

1. **Dado** cualquier fallo al guardar, decidir o cargar, **cuando** ocurre,
   **entonces** la persona lo ve junto a lo que intentaba hacer, con motivo y
   reintento; y **nunca** se comunica solo con un aviso efímero.
2. **Dado** un número de decisiones esperando, **cuando** Adrián lo mira en
   cualquier superficie, **entonces** las cuatro dicen lo mismo, y al decidir
   una, las cuatro bajan.
3. **Dado** que la aplicación está en primer plano, **cuando** llega algo nuevo,
   **entonces** no se emite un aviso del sistema: se refleja dentro de la ventana.
4. **Dado** que hay una versión nueva descargada, **cuando** Adrián lo mira,
   **entonces** la aplicación lo dice y le deja instalarla, sin reiniciar por su
   cuenta ni interrumpir trabajo en marcha.
5. **Dado** que la versión instalada ya no se admite, **cuando** Adrián pulsa la
   acción ofrecida, **entonces** llega a un sitio donde puede resolverlo.

---

### Historia 4 — De instalar a la primera respuesta, sin ayuda (Prioridad: P4)

Marta instala Auphere y la abre. La aplicación le ofrece entrar; el navegador se
abre para su cuenta de Google y, al volver, la ventana ya la reconoce y pasa al
frente. Una lista de puesta en marcha le dice qué falta (emparejar esta máquina,
crear su primer teammate) y cada paso se hace **desde la propia aplicación**. El
permiso de avisos se le pide cuando va a hacer falta, explicando para qué.
Termina con su primer teammate respondiendo.

**Por qué esta prioridad**: hoy este recorrido **no se puede completar** — entrar
con Google no vuelve y emparejar depende de algo que no se ve.

**Prueba independiente**: con una cuenta nueva y una máquina sin emparejar,
llegar desde la primera apertura hasta la primera respuesta de un teammate sin
ayuda ni instrucciones externas.

**Escenarios de aceptación**:

1. **Dado** que nadie ha entrado, **cuando** Marta abre la aplicación,
   **entonces** ve una pantalla que ofrece entrar, y al elegirlo se abre su
   navegador con un estado de espera en la ventana que permite reabrirlo, copiar
   el enlace o cancelar.
2. **Dado** que Marta completa su entrada en el navegador, **cuando** vuelve,
   **entonces** la aplicación la reconoce, pasa al frente y le muestra su sitio.
3. **Dado** que Marta cancela o el navegador no vuelve, **cuando** pasa un tiempo
   razonable, **entonces** la aplicación lo dice y le deja intentarlo de nuevo,
   sin quedarse esperando en silencio.
4. **Dado** que su cuenta no pertenece a ningún partner, **cuando** entra,
   **entonces** ve qué le falta y dos salidas —usar una invitación o entrar con
   otra cuenta—, sin bucles.
5. **Dado** que la máquina no está emparejada, **cuando** Marta abre el paso de
   puesta en marcha, **entonces** consigue el código y lo introduce **sin salir
   de la aplicación**, y al terminar las dos superficies dicen lo mismo.
6. **Dado** que Marta no ha concedido los avisos del sistema, **cuando** la
   aplicación va a necesitarlos por primera vez, **entonces** se los pide
   explicando para qué, y si los deniega, dice qué deja de funcionar y cómo
   cambiarlo.

---

### Historia 5 — Todo tope lleva a la acción (Prioridad: P5)

Adrián intenta crear un teammate y su plan no lo incluye. En vez de una frase, ve
qué plan lo desbloquea y un botón que le lleva exactamente ahí. Al pagar, la
aplicación le dice que el pago se abrió en su navegador y espera; cuando vuelve,
lo que había quedado bloqueado ya no lo está y puede terminar lo que empezó. Si
el pool de la semana se agota, ve cuándo se reinicia y qué puede hacer, y la
conversación en pausa puede reanudarse.

**Por qué esta prioridad**: hoy ninguno de los cinco topes lleva a ninguna parte,
y el único camino a pagar termina fuera de la aplicación sin avisar.

**Prueba independiente**: recorrer los cinco topes (sin plan, plan lleno, pool
sin saldo, pago fallido, versión no admitida) y comprobar que cada uno termina en
una acción con destino exacto o dice a quién pedírsela.

**Escenarios de aceptación**:

1. **Dado** un plan que no incluye teammates, **cuando** Adrián va a crear uno,
   **entonces** lo sabe **antes** de rellenar el formulario y tiene delante la
   acción que lo desbloquea.
2. **Dado** que Adrián no tiene permiso para contratar, **cuando** llega a un
   tope, **entonces** la aplicación le dice a qué rol pedírselo, en vez de
   ofrecerle una acción que no puede hacer.
3. **Dado** que una acción de pago sale al navegador, **cuando** ocurre,
   **entonces** la ventana lo dice y espera; **cuando** Adrián vuelve, el plan y
   el consumo están al día sin reiniciar nada.
4. **Dado** que el consumo de la semana se acerca a su fin, **cuando** Adrián
   trabaja, **entonces** lo ve venir con la fecha de reinicio, y no se entera al
   chocar.
5. **Dado** el consumo agotado y sin saldo, **cuando** Adrián mira la
   conversación, **entonces** una sola explicación le dice qué pasó, cuándo
   vuelve y qué opciones tiene; y tras resolverlo, la tarea en pausa se reanuda
   desde donde estaba.
6. **Dado** cualquier estado de cobro que degrade el servicio, **cuando** ocurre,
   **entonces** la aplicación lo dice antes de que se note en el trabajo.

---

### Historia 6 — Decidir sabiendo qué se decide (Prioridad: P6)

A Adrián le esperan tres decisiones. En Pendientes ve, en cada una, qué se va a
hacer, en qué máquina y sobre qué cliente, desde cuándo espera y si se puede
deshacer. Decide con el teclado. Si llega desde un aviso del sistema, la tarjeta
que lo produjo está delante y con el foco puesto. Si una decisión falla, se le
dice.

**Por qué esta prioridad**: §IV exige que quien decide esté informado; hoy se
aprueba a ciegas y un fallo al decidir no se comunica.

**Prueba independiente**: aprobar y rechazar desde Pendientes y desde un aviso
del sistema, con teclado y con un fallo forzado.

**Escenarios de aceptación**:

1. **Dado** una decisión esperando, **cuando** Adrián la mira en Pendientes,
   **entonces** ve qué se hará, dónde, desde cuándo espera y si se deshace, sin
   abrir nada más.
2. **Dado** el foco en una decisión, **cuando** Adrián usa el teclado,
   **entonces** puede aprobarla, aprobarla para siempre cuando corresponda, o
   rechazarla; y una pulsación hecha justo cuando aparece no decide por él.
3. **Dado** un aviso del sistema, **cuando** Adrián lo pulsa, **entonces** la
   ventana vuelve al frente con esa decisión delante y enfocada.
4. **Dado** que decidir falla, **cuando** ocurre, **entonces** Adrián lo ve y
   puede reintentar.
5. **Dado** que su rol no puede decidir, **cuando** abre Pendientes, **entonces**
   ve a quién pedírselo y puede abrir la conversación igualmente.

---

### Casos límite

- **La aplicación se abre por primera vez y la consola tarda**: el armazón se
  pinta igual y las secciones de administrar dicen que están cargando.
- **La persona cambia el tema del sistema** con la aplicación abierta: toda la
  ventana cambia a la vez, incluidas las secciones de administrar.
- **La sesión caduca mientras escribe**: no se la lleva a otra pantalla sin
  avisar; se le dice, se conserva lo escrito y se le ofrece entrar.
- **Dos personas en la misma máquina**: la máquina emparejada por otra persona se
  explica con nombre y con la salida que corresponda.
- **Texto largo** (nombres de cliente, rutas, comandos en alemán): se ajusta sin
  desbordar ni cortar información necesaria para decidir.
- **Zoom del sistema o del contenido al 200 %**: nada queda inalcanzable.
- **Sin permiso para una sección de administrar**: la sección no se ofrece; si se
  llega por un enlace, se explica y se ofrece a quién pedirlo. **No hay controles
  apagados** (constitución §V).
- **La máquina nunca llega a conectar** porque falta lo que debe ejecutarse en
  ella: se dice qué falta, no «reconectando» indefinido.
- **Hay trabajo en marcha y llega una actualización**: no se instala; se dice
  que espera y por qué.

---

## Requisitos *(obligatorio)*

### Requisito 1 — Un solo armazón y una sola navegación

**Historia de usuario:** Como persona que opera, quiero una sola aplicación con
una sola navegación, para dejar de saltar entre dos mundos dentro de la misma
ventana.

#### Criterios de aceptación

1. La ventana DEBE presentar una franja superior propia que integre los controles
   de ventana del sistema, y esa franja DEBE poder arrastrar la ventana en toda
   su extensión libre.
2. La ventana DEBE presentar una **única** lista lateral con: lo que se opera
   (Hoy, Pendientes con su número, los teammates) y lo que se administra; y al
   pie, la identidad de la persona, su plan y el estado de su máquina.
   **La parte de administrar DEBE ofrecer todas las secciones que la consola
   ofrece hoy a esa persona según su rol**: ninguna queda inalcanzable por el
   hecho de integrarla.
3. WHEN la persona elige una sección de administrar THEN el sistema DEBE mostrar
   esa página **dentro del panel de contenido**, sin una segunda navegación
   propia dentro del panel.
4. WHILE una sección de administrar está visible el sistema DEBE marcarla como
   activa en la lista lateral, y DEBE reflejar la navegación que ocurra dentro de
   la sección.
5. El sistema NO DEBE ofrecer ningún cambio manual entre «la consola» y «la
   pantalla de operar»: esa distinción NO DEBE existir para la persona.
6. WHEN la persona vuelve a una sección ya visitada THEN el sistema DEBE
   mostrarla sin recargarla desde cero.
7. El sistema DEBE ofrecer un menú de aplicación completo —con ajustes, ventana,
   ayuda, mostrar u ocultar la lista lateral, zoom y buscar actualizaciones— y
   **toda acción del armazón DEBE existir como orden del menú**.
8. El sistema DEBE ofrecer una búsqueda de acciones y objetos con un único atajo,
   que muestre el atajo de cada acción que lo tenga.
9. Los atajos estándar del sistema operativo NO DEBEN reutilizarse para otra cosa.
10. WHEN la persona reabre la aplicación THEN el sistema DEBE restaurar el tamaño,
    la posición y la última sección visitada.

### Requisito 2 — Sistema visual de escritorio, con una sola voz

**Historia de usuario:** Como persona que usa la aplicación todo el día, quiero
que todo dentro de la ventana se vea y se comporte como una sola cosa.

#### Criterios de aceptación

1. Toda la ventana —incluidas las secciones de administrar— DEBE usar la misma
   familia tipográfica de marca y la misma monoespaciada, **servidas con la
   aplicación**, sin depender de la red ni de lo que haya instalado la máquina.
2. El sistema DEBE usar una sola escala de espaciado, radios, tamaños de control
   y densidad declarada para escritorio, y NO DEBE usar valores de color fuera de
   los tokens.
3. El sistema DEBE ofrecer tema claro y oscuro, decididos por el sistema
   operativo salvo que la persona elija otra cosa, y el cambio DEBE alcanzar a
   toda la ventana a la vez.
4. En ambos temas, todo texto DEBE alcanzar **4,5:1** de contraste, y los
   elementos no textuales portadores de significado —incluido el indicador de
   foco— **3:1**.
5. El indicador de foco DEBE ser visible en todos los controles, con el mismo
   aspecto en toda la ventana, y NO DEBE quedar tapado por nada que la aplicación
   muestre encima.
6. Un estado NO DEBE comunicarse **solo** por color: siempre con texto o forma
   además.
7. WHEN la aplicación arranca THEN la ventana NO DEBE mostrar un destello de
   color distinto al del tema activo.
8. El sistema DEBE usar un conjunto de iconos coherente en tamaño y trazo, con
   licencia apta para uso comercial multiplataforma.
9. Ningún estado normal de trabajo DEBE pintarse con el color de peligro; el
   color de peligro queda para lo que la persona debe detener o revisar.

### Requisito 3 — Conexión, sesión y ciclo de vida, dichos por su nombre

**Historia de usuario:** Como persona que trabaja con una red imperfecta, quiero
que la aplicación distinga entre «no hay red», «no hay sesión» y «hay un fallo».

#### Criterios de aceptación

1. WHEN la aplicación arranca sin conexión THEN el sistema DEBE mostrar su
   armazón con un estado de «sin conexión» y una acción de reintento, y NO DEBE
   quedarse cargando indefinidamente ni abortar su puesta en marcha.
2. IF no se puede comprobar quién ha iniciado sesión THEN el sistema DEBE
   mantener el último veredicto conocido marcándolo como no confirmado, y NO DEBE
   tratarlo como «nadie ha iniciado sesión».
3. WHEN la conexión se recupera THEN el sistema DEBE volver al estado normal sin
   intervención y sin perder lo que la persona hubiera escrito.
4. WHEN la sesión caduca THEN el sistema DEBE decirlo **dentro de la pantalla en
   la que está la persona**, conservar su borrador y ofrecer entrar de nuevo.
5. WHEN la persona cierra la ventana THEN el sistema DEBE seguir activo para
   avisar de lo que espera decisión, y salir DEBE ser una orden explícita que
   advierta si hay trabajo en marcha.
6. El sistema DEBE ofrecer en todo momento una lectura de su máquina que incluya
   **el estado, desde cuándo, la causa cuando se conoce y la acción disponible**;
   y WHERE la máquina no puede conectar porque falta algo en ella, el sistema
   DEBE nombrar qué falta.
7. Todas las superficies que muestren el estado de la máquina DEBEN mostrar la
   misma lectura.

### Requisito 4 — Estados honestos en cada pantalla y en cada turno

**Historia de usuario:** Como persona que delega trabajo en un teammate, quiero
saber siempre en qué punto está, incluso cuando algo va mal.

#### Criterios de aceptación

1. Toda pantalla que muestre datos DEBE tener definidos y distinguibles los
   estados `normal · cargando · vacío · error · reconectando · parcial ·
   bloqueado`, y NO DEBE presentar uno por otro.
2. IF la apertura de una conversación falla THEN el sistema DEBE mostrar un error
   con motivo y reintento, y NO DEBE mostrar el estado «vacío».
3. Un turno del teammate DEBE distinguir, para la persona: enviando, esperando
   respuesta, razonando, usando una herramienta, esperando su decisión,
   terminado, detenido y fallido.
4. WHILE el teammate trabaja el sistema DEBE ofrecer detenerlo, y DEBE mantener
   visible lo ya producido al detenerse.
5. WHEN un mensaje no se puede enviar THEN el sistema DEBE conservar el texto de
   la persona y ofrecer reintentar.
6. WHERE el sistema solo pudo leer parte de lo pedido, la respuesta DEBE acotar
   su propio alcance diciendo qué parte cubre.
7. Un teammate bloqueado esperando a otro NO DEBE presentarse como ocioso.
8. Un indicador de espera NO DEBE aparecer para respuestas inmediatas, y cuando
   aparezca DEBE describir qué se está haciendo.
9. Cuando una capacidad no está disponible, el sistema NO DEBE mostrar un control
   apagado ni una pantalla que solo explique lo que no se tiene.

### Requisito 5 — Una taxonomía de avisos y un solo número

**Historia de usuario:** Como persona que recibe información de muchas fuentes,
quiero que cada tipo de mensaje aparezca siempre del mismo modo.

#### Criterios de aceptación

1. El sistema DEBE tener una taxonomía declarada —mensaje junto al elemento,
   aviso de vista, confirmación efímera, diálogo, aviso del sistema, número en un
   icono, bandeja— con la regla de cuándo se usa cada uno.
2. IF una acción falla THEN el sistema DEBE comunicarlo junto a lo que se
   intentaba, con motivo y salida, y NO DEBE comunicarlo únicamente con una
   confirmación efímera.
3. Ninguna acción que la persona inicie DEBE terminar sin señal: éxito visible o
   fallo explicado.
4. El número de decisiones que esperan DEBE salir de **una sola definición**, y
   DEBE coincidir en la lista lateral, en el icono de la aplicación, en el icono
   de la barra del sistema y en Pendientes.
5. WHILE la ventana tiene el foco el sistema NO DEBE emitir avisos del sistema
   por lo que ya es visible dentro de ella.
6. Un aviso del sistema DEBE decir **el motivo** —esperando tu decisión,
   terminado, fallido—, NO DEBE incluir el contenido de lo que el teammate leyó o
   ejecutó, y al pulsarlo DEBE traer la ventana al frente sobre el objeto que lo
   produjo.
7. Los mensajes de estado DEBEN anunciarse a las tecnologías de apoyo sin mover
   el foco, y sin repetir el mismo mensaje por dos vías.
8. La persona DEBE poder bajar el ruido de los avisos desde la aplicación, y esa
   preferencia NO DEBE poder silenciar lo que espera su decisión sin decirlo.

### Requisito 6 — La actualización se anuncia y la decide la persona

**Historia de usuario:** Como partner, quiero enterarme de que hay una versión
nueva y decidir cuándo se instala.

#### Criterios de aceptación

1. WHEN hay una versión nueva lista THEN el sistema DEBE decirlo dentro de la
   aplicación, sin interrumpir el trabajo.
2. WHEN la persona acepta actualizar THEN el sistema DEBE instalarla y volver al
   mismo sitio.
3. IF hay trabajo en marcha THEN el sistema DEBE posponer la instalación y decir
   que espera, en vez de callar.
4. WHERE la versión instalada ya no se admite, la acción ofrecida DEBE llevar a
   un lugar donde la persona pueda resolverlo, y el sistema DEBE nombrar la
   versión mínima.
5. El sistema DEBE permitir comprobar si hay actualizaciones y ver la versión
   instalada desde el menú.
6. El sistema NO DEBE reiniciarse por su cuenta en ningún caso que no sea la
   persona aceptando actualizar.

### Requisito 7 — De instalar a la primera respuesta

**Historia de usuario:** Como persona que acaba de instalar la aplicación, quiero
llegar sola hasta mi primer teammate respondiendo.

#### Criterios de aceptación

1. WHEN nadie ha iniciado sesión THEN la aplicación DEBE ofrecer **desde su
   propia pantalla** la acción de entrar, incluida la entrada con proveedor
   externo.
2. WHEN la persona inicia la entrada THEN el sistema DEBE abrir su navegador y
   mostrar en la ventana un estado de espera con: volver a abrir, copiar el
   enlace y cancelar.
3. WHEN la entrada se completa en el navegador THEN el sistema DEBE reconocerla,
   traer la ventana al frente y continuar donde la persona estaba.
4. IF la entrada se cancela, falla o no vuelve en un tiempo acotado THEN el
   sistema DEBE decirlo y ofrecer intentarlo otra vez, y NO DEBE esperar en
   silencio.
5. IF la cuenta no pertenece a ningún partner THEN el sistema DEBE explicarlo y
   ofrecer dos salidas —usar una invitación y entrar con otra cuenta—, sin
   devolver a la persona al mismo punto de partida.
6. El sistema DEBE mostrar una lista de puesta en marcha con los pasos que faltan
   y su estado, accesible en todo momento y **no bloqueante**.
7. Cada paso de esa lista DEBE completarse **sin salir de la aplicación**, salvo
   lo que por seguridad ocurre en el navegador (entrar y pagar), que DEBE seguir
   el traspaso del Requisito 9.
8. WHEN el sistema va a necesitar por primera vez un permiso del sistema
   operativo THEN DEBE pedirlo en ese momento explicando para qué.
9. La primera pantalla con la sesión iniciada NO DEBE estar vacía: DEBE ofrecer
   lo siguiente que tiene sentido hacer.
10. IF un permiso del sistema operativo se deniega THEN el sistema DEBE decir qué
    deja de funcionar y cómo concederlo.

### Requisito 8 — El puesto de trabajo, dentro de la aplicación

**Historia de usuario:** Como partner que va a dejar que un teammate trabaje en
su máquina, quiero emparejarla y decidir qué ve, desde la misma aplicación.

#### Criterios de aceptación

1. El sistema DEBE mostrar el estado de la máquina en el armazón, de forma
   visible sin abrir nada, y DEBE poder alcanzarse con el teclado.
2. WHEN la máquina no está emparejada THEN el sistema DEBE ofrecer emparejarla
   desde la propia aplicación, y el recorrido completo —pedir el código e
   introducirlo— DEBE poder verse y completarse **sin que ninguna parte quede
   fuera de la vista**.
3. WHEN el emparejamiento se completa THEN todas las superficies DEBEN reflejarlo
   sin que la persona tenga que recargar nada.
4. El sistema DEBE ofrecer declarar el directorio de cada cliente desde la
   aplicación; IF el directorio elegido no vale THEN DEBE decir por qué.
5. Desemparejar DEBE confirmarse explicando qué deja de funcionar.
6. Las instrucciones para poner en marcha la máquina DEBEN decir lo mismo en
   todas las superficies, y NO DEBEN pedir a la persona algo que ya hizo.
7. La aplicación NO DEBE presentar ningún formulario de credenciales propio.

### Requisito 9 — Llevar a la acción, dentro y fuera de la ventana

**Historia de usuario:** Como partner, quiero que cuando algo no se pueda hacer,
la aplicación me lleve a poder hacerlo.

#### Criterios de aceptación

1. Todo estado que impida algo por plan, consumo, cobro o versión DEBE terminar
   en **una acción con destino exacto**, o en el nombre del rol a quien pedirlo.
2. WHEN la persona no tiene permiso para contratar o comprar THEN el sistema DEBE
   decir a quién pedírselo, y NO DEBE ofrecerle la acción.
3. WHEN una capacidad no está incluida en el plan THEN el sistema DEBE decirlo
   **antes** de que la persona rellene o prepare nada.
4. WHEN una acción sale al navegador THEN la ventana DEBE decirlo, quedarse en
   espera y ofrecer volver a abrirla o cancelar.
5. WHEN la persona vuelve del navegador THEN el sistema DEBE actualizar plan y
   consumo sin reiniciar la aplicación, y DEBE devolverla a lo que estaba
   haciendo.
6. La aplicación DEBE mostrar, allí donde se consume, la proporción usada del
   pool y **cuándo se reinicia**, sin mostrar la cifra absoluta del pool.
7. WHEN el consumo se acerca a su fin THEN el sistema DEBE avisarlo antes de
   agotarse.
8. WHILE el trabajo está en pausa por consumo el sistema DEBE dar **una sola**
   explicación, con lo que pasó, cuándo vuelve y qué opciones hay.
9. IF un cobro falla o el estado de la suscripción degrada el servicio THEN el
   sistema DEBE decirlo en la aplicación **antes** de que se note en el trabajo.
10. La aplicación NO DEBE pedir ni mostrar datos de tarjeta en ningún caso.
11. WHEN la causa de una pausa por consumo se resuelve THEN el sistema DEBE poder
    reanudar lo que quedó en pausa sin empezar de nuevo.

### Requisito 10 — Decidir con lo necesario delante

**Historia de usuario:** Como persona responsable de lo que hace un teammate,
quiero decidir sabiendo exactamente qué autorizo.

#### Criterios de aceptación

1. Toda decisión pendiente DEBE mostrar, sin abrir nada más: qué se hará, sobre
   qué cliente y máquina, desde cuándo espera, y si tiene vuelta atrás.
2. El sistema DEBE permitir aprobar, rechazar y —cuando la decisión lo admita—
   aprobar de forma permanente, con el teclado.
3. WHEN una tarjeta de decisión aparece THEN el sistema NO DEBE aceptar como
   respuesta una pulsación hecha en el instante de aparecer.
4. WHEN la persona llega desde un aviso del sistema THEN el sistema DEBE mostrar
   la decisión que lo produjo, traerla a la vista y darle el foco.
5. IF decidir falla THEN el sistema DEBE decirlo y permitir reintentar.
6. IF el rol de la persona no puede decidir THEN el sistema DEBE decir a quién
   pedírselo y DEBE permitir abrir la conversación igualmente.
7. La decisión DEBE quedar atribuida a la persona que la tomó, y esa atribución
   DEBE poder verse después.

### Requisito 11 — Accesibilidad y teclado *(ubicuo)*

**Historia de usuario:** Como persona que usa teclado o lector de pantalla,
quiero poder hacer todo lo que hace cualquiera.

#### Criterios de aceptación

1. Toda acción DEBE poder ejecutarse con el teclado, incluido el estado de la
   máquina y todo lo que hoy vive fuera de la pantalla principal.
2. El sistema DEBE permitir moverse entre las zonas del armazón —lista lateral,
   panel, estado de la máquina— con una orden de teclado.
3. WHEN la sección visible cambia THEN el sistema DEBE llevar el foco al
   encabezado de la nueva sección.
4. Cada zona y cada región de la ventana DEBE tener un nombre único y
   descriptivo.
5. Un grupo de opciones excluyentes DEBE presentarse como tal, y no como varios
   interruptores.
6. Ningún objetivo de interacción DEBE ser menor de 24×24 píxeles.
7. El sistema DEBE respetar la preferencia de movimiento reducido y la de
   transparencia reducida.
8. El contenido DEBE seguir siendo utilizable con el texto o el contenido
   ampliados al 200 %.
9. Cada pantalla DEBE pasar una revisión automática de accesibilidad sin
   incidencias graves o críticas.

### Requisito 12 — Una sola voz *(ubicuo)*

**Historia de usuario:** Como persona que lee la aplicación, quiero que las cosas
se llamen siempre igual.

#### Criterios de aceptación

1. El sistema DEBE usar un glosario único en toda la ventana: «teammate» (nunca
   «agente» ni «Companion» al hablar del interlocutor de la persona), «pool
   semanal» (nunca «tope mensual»), «puesto de trabajo», «pendiente».
2. Todo el texto que escribe la aplicación DEBE estar en el idioma de la cuenta:
   la pantalla, los menús, los avisos del sistema, los títulos y mensajes que la
   aplicación pasa a los diálogos del sistema operativo, y las páginas que la
   propia aplicación sirve en el navegador. Los botones que pone el sistema
   operativo quedan fuera de su control.
3. El texto de la aplicación NO DEBE mostrar identificadores internos ni códigos
   crudos a la persona; cuando se necesite un dato técnico para soporte, DEBE
   poder copiarse aparte.
4. Las cantidades, fechas y proporciones DEBEN formatearse según el idioma de la
   cuenta.
5. El texto de una conversación con un cliente final NO DEBE transcribirse en las
   superficies de esta aplicación: se referencia y se cita.

### Entidades clave

- **Lo que te espera** (derivado, no dato nuevo): el conjunto de decisiones que
  esperan a **esta** persona en **este** partner, con su nivel. Es la **única**
  fuente del número que aparece en la lista lateral, en los iconos y en
  Pendientes. Pertenece al tenant por la pertenencia de la persona al partner y
  se alcanza por el mismo camino que hoy usa Pendientes.
- **Estado del puesto de trabajo**: la lectura única del estado de la máquina de
  esta persona —estado, desde cuándo, causa conocida, acción disponible—,
  consumida por el armazón y por la puesta en marcha. Pertenece al tenant por la
  máquina y su dueño.
- **Puesta en marcha**: los pasos pendientes del partner y de esta máquina, con
  su estado. Es una lectura derivada de lo que ya existe; no introduce datos
  nuevos.
- **Preferencias de la ventana** (local, sin identidad): tamaño y posición,
  última sección, tema y ruido de avisos. NO DEBE contener credenciales.

## Criterios de éxito *(obligatorio)*

- **CE-001**: una persona nueva, con una cuenta nueva y una máquina sin
  emparejar, llega desde la primera apertura hasta **la primera respuesta de un
  teammate en ≤10 minutos**, sin ayuda externa y sin salir de la aplicación salvo
  para entrar y, si procede, pagar.
- **CE-002**: **cero** estados sin salida: todo estado de vacío, error,
  bloqueado, tope, sin sesión o sin conexión ofrece una acción o dice a quién
  pedirla (hoy: al menos doce no lo hacen).
- **CE-003**: **cero** acciones que fallen o salgan de la aplicación sin decirlo
  (hoy: siete).
- **CE-004**: el número de decisiones que esperan **coincide en las cuatro
  superficies** en todo momento (hoy: tres reglas distintas).
- **CE-005**: **cero** incidencias graves o críticas en la revisión automática de
  accesibilidad de cada pantalla, y todo texto y todo indicador de foco cumple el
  contraste exigido en ambos temas (hoy: foco a 2,09:1 y pares a 1,24:1).
- **CE-006**: los **cinco** estados de tope (sin plan, plan lleno, consumo
  agotado, cobro degradado, versión no admitida) terminan en una acción con
  destino exacto o en el rol a quien pedirla (hoy: ninguno).
- **CE-007**: la aplicación muestra su armazón **en menos de un segundo** desde
  que se abre, sin destello y sin depender de la red.
- **CE-008**: una sola familia tipográfica de marca en toda la ventana (hoy:
  dos), y cero valores de color fuera de los tokens.
- **CE-009**: el recorrido de emparejamiento se completa **dentro de la ventana**
  y ninguna parte de él queda fuera de la vista, con teclado incluido.
- **CE-010**: tras resolver una pausa por consumo, **el trabajo pendiente se
  reanuda sin volver a empezar**.

## Fuera de alcance

- **Windows** — el armazón no le cierra la puerta, pero su empaquetado y su barra
  de título propia no entran en esta spec.
- **Reimplementar pantallas de la consola** — 003 R12.6 sigue vigente: se
  integran, no se reescriben.
- **Pagar dentro de la ventana** — la política de ventanas lo impide; lo que se
  diseña es el traspaso al navegador y la vuelta.
- **La página de agradecimiento tras pagar** — es un defecto de la spec 005 que
  afecta también a la consola web; va por el flujo de bugs.
- **Enlaces entrantes con esquema propio** — abriría superficie nueva (§II) sin
  necesidad para estos objetivos.
- **Capacidades nuevas del agente** (navegador del agente, VM, subagentes) — se
  diseñan los estados de lo que ya existe, no se añade nada.
- **Cambios de precios, planes o del propio medidor** — esta spec los muestra y
  los enlaza; no los define.
- **Tours guiados paso a paso** — la evidencia desaconseja imponerlos; se usa una
  lista de puesta en marcha no bloqueante.

## Supuestos

1. **La consola sigue siendo la dueña de administrar.** Esta spec cambia dónde se
   pinta y cómo se llega, no qué hace.
2. **Las secciones de administrar se listan una a una** en la lista lateral (no
   agrupadas tras una sola entrada), porque ese es el sentido de tener una sola
   navegación; se ofrecen según el permiso de cada persona. **La lista es la que
   la consola ya define** —inicio, clientes, conocimiento, puesto de trabajo,
   consumo, auditoría, notificaciones, equipo, claves y facturación—, con sus
   mismos permisos: integrar la consola no puede dejar ninguna sección fuera de
   alcance.
3. **«Hoy» es la sección de inicio** la primera vez; después se restaura la
   última sección visitada.
4. **El aviso de consumo cercano se emite al 80 %**, que es el umbral que el
   producto **ya usa** en los avisos de consumo de la consola («Umbrales: 80 %
   (aviso) y 100 % (tope alcanzado)»). No se inventa un valor nuevo.
5. **El tiempo de espera de la entrada por navegador es el que ya existe** en la
   aplicación; lo que añade esta spec es que, al agotarse, se diga.
6. **La atribución de una decisión ya existe** como dato (spec 003/§IV); esta spec
   la muestra.
7. **La reanudación tras una pausa por consumo se apoya en la tarea durable** que
   ya define la spec 003; no se crea un mecanismo nuevo.
8. **No hay periodo de prueba** como concepto de producto (spec 005).
9. **El idioma de la cuenta** es el que ya devuelve la sesión; esta spec lo
   extiende a las superficies que hoy están solo en español.
10. **Las seis historias entregan valor por separado, pero no todas arrancan a la
    vez**: las historias 4 y 5 ocurren *dentro* del armazón, así que se
    construyen después de la 1. Las historias 2, 3 y 6 son independientes entre
    sí y de la 1.
