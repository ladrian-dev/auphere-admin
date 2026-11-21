# Especificación: La app con el diseño nuevo

**Rama**: `069-la-app-con-el-diseno-nuevo` · **Creada**: 2026-11-21 · **Estado**: Borrador, implementada de noche con permiso de Luis para revisarla al día siguiente

**Entrada**: descripción del usuario (Luis, 2026-11-21): "Vamos a trabajar en la app mobile para mandarla a revisión en Google y Apple. Acá hay una investigación y diseño final de cómo debe quedar la app (https://claude.ai/artifact/AKR5o4U27DFt7FJ6CBF7iK); la app debe quedar así y podremos usar capturas de ahí para las portadas de cada tienda. Debemos actualizar las apps móviles con los cambios recientes que hemos hecho, ya que la tenemos un poco desactualizada porque le habíamos dado prioridad a la web. Esta app es sumamente importante, ya que los clientes finales la estarán usando." Y después: "No perdamos funcionalidades: si la app actual tiene funcionalidades que el demo no tiene, incluyámoslas; si el demo tiene funcionalidades que la app no tenga, incluyámoslas (si son críticas y le dan valor al cliente)."

## Encabezado Auphere *(obligatorio)*

| Campo | Valor |
|---|---|
| **Superficie de confianza** | `0`, la API de la consola lite (`/console/lite/*` y `/app/*`), la misma que abrió la 031. La app no tiene reglas de negocio propias y no se abre ninguna superficie nueva: todas las rutas que usa esta spec ya están en `main` y responden en producción (comprobado el 2026-11-21: `GET /app/config` → 200). |
| **Garantías de aislamiento tocadas** | **Ninguna.** No cambia la API. La app sigue sus reglas de siempre (031): lo de los clientes finales vive en memoria, nunca en disco, y el aviso enseña lo que la API envía. Si una tarea de esta spec necesitara una ruta nueva, sale de aquí a su propia spec con su barrido de `tests/isolation/`. |
| **Nota de KB que la justifica** | `[[research/2026-11-21-app-movil-a-tiendas]]` (inventario del diseño pantalla por pantalla, estado de la app, deriva con la web y decisiones de Luis). Plan para decidir: https://claude.ai/artifact/Neki7dgJXGm3z1kdjxDt8Z (v3). Diseño: https://claude.ai/artifact/AKR5o4U27DFt7FJ6CBF7iK, versión `1795099383-78fb` (copia en la KB, `demo-1795099383-78fb/`). |
| **Qué se mide** | **Nada.** Ni modelo, ni máquina, ni herramienta de pago. |

### Lo que enmienda

| Dónde | Qué decía | Qué dice ahora |
|---|---|---|
| `apps/mobile/AGENTS.md` y 031 D24 («nativo primero») | Iconos SF Symbols en iOS y Material Symbols en Android. Tipografía del sistema sin interletrado. | **Iconos Lucide** en contenido y controles, la misma familia que la consola. **Helvena** en títulos y cifras, si la licencia lo permite. El sistema sigue mandando en la estructura: pestañas, cabecera, hojas y permisos nativos. |
| 031 D15 (los colores son los de la consola) | Solo los roles de `tokens.css`, convertidos. | Siguen saliendo de `tokens.css`. Se añaden los **roles propios de la app** que el diseño necesita (selección, texto de destacado, tintes de estado y color de canal) en un bloque del generador que la web no lee. |
| 044 Requisito 16.7 | «Tomar el control y devolver NO DEBEN mostrar aviso breve.» | Tomar el control muestra un aviso breve con **«Devolver»**, que es el deshacer del diseño. Devolver no lo muestra. |
| 044 (exclusiones de la hoja de la reserva) | Mover y pedir confirmación no se ofrecen en el teléfono. | Se ofrecen, igual que en la web. |
| 064 (la app quedaba fuera) | Teléfono obligatorio, antelación del agente, recordatorios y cierre por inactividad, solo en la web. | La app los cumple (Requisitos 15 a 17). |
| 044 Requisito 9 (Inicio) | La atención y las cifras de la 044. | Inicio del diseño (Requisito 8): cuatro tarjetas, lo último de la Bandeja, quien espera abajo y la tarjeta calma. |

## Origen

El owner (Andrés) aprobó una demo interactiva de la app: 13 pantallas y 4 hojas, en iOS 26 y Android, claro y oscuro, con títulos en Helvena, iconos Lucide, color por función, vidrio solo para navegar y controles, y ocho microinteracciones. Luis pidió que la app quede así y que se ponga al día con lo que la web ya da al cliente. Desde la spec 056 (8 nov), la app solo ha recibido contratos regenerados.

La investigación está en la KB (`research/2026-11-21-app-movil-a-tiendas/`, cinco inventarios con referencias a líneas):

- `01`: fundamentos, Entrar e Inicio.
- `02`: Bandeja.
- `03`: Reservas, Consumo y Ajustes.
- `04`: la app hoy y las tiendas.
- `05`: lo que la web tiene y la app no.

**Regla de esta spec**, en orden:

1. El diseño manda en el aspecto: composición, tipografía, color, iconos, movimiento, hápticos y textos.
2. Nada de lo que la app ya hace se pierde; se viste con el diseño.
3. Del demo entra lo crítico o lo que da valor al cliente.
4. Las specs vigentes mandan en el comportamiento.
5. Las reglas de las tiendas mandan sobre todo lo anterior.
6. Si el diseño pide un dato que la API no da, la pantalla se adapta al dato que existe.

## Clarifications

### Session 2026-11-21

- Q: ¿Quién publica la app? → A: **FACELAD.** Se conservan el App ID `com.auphere.customers`, la app de App Store Connect y la de Play. Se puede transferir a Auphere después de la primera versión.
- Q: ¿Helvena en la app? → A: **Sí, si la licencia lo permite, y sin perder rendimiento.** La fuente es de Zippie Letras y no trae licencia; en el repo no hay EULA. Mientras no se confirme, un único token decide la familia de los títulos, y el respaldo es SF Pro y Roboto.
- Q: ¿Android con la cápsula esmerilada del demo o en Material 3? → A: **Material 3**, por rendimiento, **sin perder ninguna función** respecto de iOS.
- Q: ¿Pesos de letra? → A: **Hasta 600**, como la consola (068).
- Q: ¿«Recargar saldo»? → A: **Fuera.** Guía 3.1.3(f) de Apple.
- Q: ¿Qué funciones del demo entran? → A: las críticas o de valor. Las que no entran, y por qué, están en «Fuera de alcance».

## Escenarios de usuario y pruebas *(obligatorio)*

### Historia 1 — Saber cómo va el día de un vistazo (Prioridad: P1)

La persona del negocio abre la app y en Inicio, sin desplazarse, ve:
- cuántas reservas tiene hoy y cuál es la siguiente;
- cómo van las conversaciones;
- su saldo y cuánto le dura;
- lo que lleva gastado este mes.

Si alguien espera a una persona, lo ve abajo, al alcance del pulgar, con su motivo y el botón «Atender a …».

**Por qué esta prioridad**: es la primera pantalla y la que responde «¿tengo que hacer algo?».

**Prueba independiente**: con un cliente de ejemplo con alguien esperando, Inicio enseña las cuatro tarjetas, lo último de la Bandeja y la tarjeta de espera. Al tocar «Atender» se abre esa conversación.

**Escenarios de aceptación**:
1. **Dado** que alguien espera a una persona, **cuando** abro Inicio, **entonces** veo abajo la tarjeta con su nombre, desde cuándo espera, el motivo y «Atender a {nombre}».
2. **Dado** que ya nadie espera, **cuando** vuelvo a Inicio, **entonces** aparece una vez «Todo en orden», con el ✓ que se dibuja, y se retira sola.
3. **Dado** un cliente sin el módulo Reservas, **cuando** abro Inicio, **entonces** no aparece la tarjeta «Hoy».

---

### Historia 2 — Atender una conversación que espera (Prioridad: P1)

La persona encuentra quién espera en la Bandeja, que está agrupada por día y donde cada conversación lleva el logo de su canal. Abre la conversación, toma el control, contesta y, cuando termina, se la devuelve al agente o la resuelve.

**Por qué esta prioridad**: es la función principal de la app y el motivo del aviso urgente.

**Prueba independiente**: tomar el control de una conversación que espera, enviar un mensaje y devolverla, todo con el aspecto nuevo y sin perder adjuntos, nota ni etiquetas.

**Escenarios de aceptación**:
1. **Dado** una conversación que espera, **cuando** toco «Tomar el control», **entonces** la franja del agente se pliega, sube el cuadro de escribir, aparece «Tomaste el control» en el hilo y un aviso breve con «Devolver».
2. **Dado** que escribo, **cuando** toco enviar, **entonces** la burbuja sube desde abajo y el botón de enviar solo aparece cuando hay texto.
3. **Dado** una conversación de Instagram, **cuando** abro su contacto, **entonces** pone «Instagram» y «Cuenta», no «WhatsApp» y «Teléfono».

---

### Historia 3 — Encontrar a alguien al momento (Prioridad: P1)

Desde la búsqueda de la barra de pestañas, o desde la propia Bandeja, la persona escribe un nombre, un teléfono o una palabra que se dijo, y llega a la conversación.

**Por qué esta prioridad**: con cientos de conversaciones, desplazarse no es una forma de encontrar.

**Prueba independiente**: buscar «seña» devuelve las conversaciones en las que se dijo, incluidas las resueltas.

**Escenarios de aceptación**:
1. **Dado** que escribo en la búsqueda, **cuando** paro de escribir, **entonces** veo los resultados sin pulsar ningún botón.
2. **Dado** que no hay resultados, **cuando** termino la búsqueda, **entonces** veo un vacío que dice qué busqué y cómo ampliar la búsqueda.

---

### Historia 4 — Ordenar la Bandeja con el dedo (Prioridad: P2)

La persona desliza una conversación para resolverla o reabrirla y para marcarla como leída o no leída. Si se equivoca, la deshace desde el aviso breve.

**Prueba independiente**: deslizar para resolver y deshacer deja la conversación como estaba, en la API y en la lista.

**Escenarios de aceptación**:
1. **Dado** una conversación abierta, **cuando** la deslizo hacia la izquierda, **entonces** se resuelve y aparece un aviso con «Deshacer» y una barra de tiempo. Dura 6 s (044; la decisión 8 de `log.md` cambia los 4 s del demo), o 20 s con un lector de pantalla activo (revisión, H10).
2. **Dado** que uso VoiceOver o TalkBack, **cuando** estoy sobre una fila, **entonces** tengo las mismas acciones en el menú de acciones accesibles.

---

### Historia 5 — Reservar, mover y cerrar el día (Prioridad: P2)

La persona ve el día en lista o en cuadrícula. Toca un hueco libre para reservar a esa hora (el teléfono es obligatorio), abre una reserva para confirmarla, moverla, pedir confirmación, cancelarla ofreciendo el hueco a la lista de espera o marcar Llegó y No vino.

**Prueba independiente**: crear, mover y cancelar una reserva con el aspecto nuevo en modo Servicios, y registrar una llegada sin reserva en modo Aforo.

**Escenarios de aceptación**:
1. **Dado** la cuadrícula del día, **cuando** toco un hueco libre, **entonces** se abre Nueva reserva con ese día y esa hora elegidos.
2. **Dado** Nueva reserva sin teléfono, **cuando** toco «Guardar», **entonces** el campo dice que el teléfono es obligatorio y no se guarda nada.
3. **Dado** que cancelo una reserva, **cuando** confirmo, **entonces** puedo elegir si se avisa al cliente y si se ofrece el hueco a la lista de espera, y tengo «Deshacer».

---

### Historia 6 — Saber cuánto me dura el saldo (Prioridad: P2)

En Consumo, la persona ve su saldo y para cuánto le alcanza a este ritmo, el gasto y las conversaciones del mes, y el gasto por día en 7, 30 o 90 días. No hay botón de recarga.

**Escenarios de aceptación**:
1. **Dado** un saldo en EUR, **cuando** abro Consumo o Inicio, **entonces** todas las cifras salen en EUR, con dos decimales.
2. **Dado** que cambio de 30 a 90 días, **cuando** se carga el periodo, **entonces** el total corre hasta su valor y el lector de pantalla solo dice el final.

---

### Historia 7 — Entrar y quedarse dentro (Prioridad: P2)

La persona entra con su correo y su contraseña o con Google, sobre el líquido de los verdes de Auphere. Si olvidó la contraseña, pide un enlace, ve a qué dirección se mandó y puede pedir otro a los 30 s. Antes del permiso de avisos, ve un ejemplo real del aviso urgente.

**Escenarios de aceptación**:
1. **Dado** que dejo la contraseña vacía, **cuando** toco «Entrar», **entonces** el campo dice «Escribe tu contraseña.». El error no aparece antes del primer intento.
2. **Dado** «Reducir movimiento», **cuando** abro Entrar, **entonces** el líquido es un cuadro quieto.

---

### Historia 8 — Ajustar lo que me avisa (Prioridad: P3)

En Ajustes, la persona ve:
- su cuenta, su negocio y los canales conectados;
- los avisos de este teléfono por tipo (apagar el urgente pide confirmación);
- el silencio fuera del horario;
- la política de privacidad y el soporte;
- cerrar sesión y solicitar el borrado de la cuenta.

**Escenarios de aceptación**:
1. **Dado** el aviso urgente encendido, **cuando** lo apago, **entonces** la app pregunta «¿Apagar el aviso urgente?» antes de guardarlo.
2. **Dado** Ajustes, **cuando** toco «Política de privacidad», **entonces** se abre la política publicada.

---

### Casos límite

- **Negocio nuevo**: sin conversaciones, sin reservas y sin gasto. Inicio y cada pestaña enseñan un vacío que dice qué aparecerá y cómo empieza, nunca ceros sueltos.
- **Varios agentes**: el nombre del agente sale de los datos, nunca de un texto fijo («Ava» es del demo).
- **Moneda sin decimales** (CLP) y **con decimales** (EUR o USD): las mismas pantallas, cada una con su formato.
- **Miles de conversaciones**: la Bandeja carga por páginas y el desplazamiento no se traba.
- **Módulos que el cliente no tiene**: su pestaña, su tarjeta de Inicio, su fila del contacto y sus avisos no existen (constitución §V: la ausencia se diseña).
- **Modo Aforo**: Reservas enseña su capacidad del día, las llegadas sin reserva y los bloqueos, que el demo no muestra.
- **Sin conexión**: cada pantalla enseña lo guardado con «Lo guardado a las HH:MM» y desactiva solo lo que escribe; el borrador se conserva.
- **Ventana del agente vencida** (Instagram o Messenger pasadas 24 h): no se dice «responde el agente». Se dice hasta cuándo puede contestar una persona.
- **Licencia de Helvena no confirmada**: los títulos salen en SF Pro o Roboto, con la misma escala.
- **iOS anterior a 26 o «Reducir transparencia»**: las superficies de vidrio pasan a opacas sin perder ningún control.

## Requisitos *(obligatorio)*

### Requisito 1 — Sistema visual

**Historia de usuario:** Como persona del negocio, quiero una app que se lea igual de clara en cualquier pantalla, para no tener que aprender cada una.

#### Criterios de aceptación

1. El sistema DEBE sacar todo color de los tokens de la app, generados desde `tokens.css`, sin un solo color escrito a mano en las pantallas.
2. El sistema DEBE usar color por función: verde sólido solo para la acción principal, menta para lo que merece atención y ámbar solo en la etiqueta y el icono de quien espera. Lo elegido DEBE llevar tinte y ✓, nunca solo color.
3. El sistema DEBE usar una sola familia de iconos (Lucide) en contenido y controles. Los logotipos de WhatsApp, Instagram y Messenger DEBEN ser los de cada marca.
4. WHERE la licencia de Helvena permite incrustarla en la app EL sistema DEBE usarla en títulos grandes, títulos de hoja y diálogo, nombres destacados y cifras. El resto del texto DEBE ir en la fuente del sistema.
5. IF la licencia de Helvena no está confirmada THEN el sistema DEBE usar la fuente del sistema en esos mismos elementos, con la misma escala, y el cambio DEBE ser un único valor.
6. El sistema NO DEBE usar pesos de letra por encima de 600.
7. El sistema DEBE crecer con el tamaño de texto del sistema (Dynamic Type y escala de fuente de Android) en todas las pantallas, sin recortar lo esencial.
8. El sistema DEBE poner vidrio solo en barras, pestañas, botones flotantes, el dock de la conversación y los menús. Listas, tarjetas, burbujas y cifras DEBEN ser opacas, y NO DEBE haber vidrio sobre vidrio.
9. WHILE «Reducir transparencia» está activo, o en iOS anterior a 26, el sistema DEBE pintar opacas las superficies de vidrio.
10. Los radios de las esquinas DEBEN salir de una sola escala de la app.

### Requisito 2 — Movimiento y microinteracciones

#### Criterios de aceptación

1. El sistema DEBE tener las microinteracciones del diseño:
   - (2) el chip elegido con el ✓ que se dibuja;
   - (3) lo que esperas llega, con la fila que entra y la insignia que late una vez;
   - (4) la cifra que corre hasta su valor;
   - (5) la hoja que abre al instante con esqueletos;
   - (6) el aviso breve con «Deshacer» y una barra de tiempo;
   - (7) enviar;
   - (8) el vacío que tranquiliza.
2. La lente de la barra de pestañas (micro 1) DEBE ser la del sistema.
3. «Tomar el control» DEBE ser la única coreografía: la franja se pliega en 120 ms, hay una pausa de 40 ms y el cuadro de escribir sube en 240 ms.
4. Ninguna transición de la interfaz DEBE durar más de 300 ms ni rebotar.
5. WHILE «Reducir movimiento» está activo el sistema DEBE cambiar cada movimiento por un fundido o por el estado final, y NO DEBE acortar los tiempos de espera que no son animación (como la tarjeta «Todo en orden»).
6. Cada acción con háptico DEBE usar el del mapa de hápticos de la app: selección, ligero, éxito o advertencia.

### Requisito 3 — Estados honestos y accesibilidad

#### Criterios de aceptación

1. Toda pantalla que pinta datos DEBE tener carga (esqueleto con las medidas finales), vacío, error con «Reintentar», parcial, ideal y sin conexión.
2. WHILE no hay conexión el sistema DEBE enseñar lo guardado con la hora de la última lectura y desactivar solo lo que escribe.
3. Todo control DEBE tener nombre accesible y un objetivo táctil de al menos 44 × 44 pt en iOS y 48 × 48 dp en Android.
4. Toda acción por gesto (deslizar, mantener pulsado) DEBE tener una acción accesible equivalente.
5. Los bordes de los controles y el foco visible DEBEN contrastar al menos 3:1, y el texto al menos 4,5:1.
6. Un estado (pendiente, cancelada, sin leer) NO DEBE comunicarse solo con color.

### Requisito 4 — Android en Material 3

#### Criterios de aceptación

1. En Android el sistema DEBE usar la barra inferior y la barra superior nativas, superficies tonales en lugar de vidrio, y la fuente del sistema en el texto corrido.
2. El sistema DEBE ofrecer en Android **las mismas funciones** que en iOS. La lista de funciones del Requisito 20 se comprueba en las dos plataformas.
3. El sistema NO DEBE imitar el vidrio con desenfoque en Android.

### Requisito 5 — Entrar

#### Criterios de aceptación

1. El sistema DEBE enseñar Entrar con el líquido vivo de los verdes de Auphere (el de la spec 066), el logo, el titular y la tarjeta con correo, contraseña con mostrar y ocultar, «¿Olvidaste tu contraseña?», «Entrar» y «Continuar con Google».
2. WHILE «Reducir movimiento» está activo, o el teléfono no mantiene la animación, el sistema DEBE pintar un cuadro quieto del líquido.
3. WHEN la persona toca o arrastra el líquido THEN el sistema DEBE seguir el dedo y abrir una onda.
4. El sistema DEBE enseñar el error de cada campo bajo ese campo y solo después del primer intento.
5. IF no hay conexión THEN Entrar DEBE decirlo en la tarjeta y no intentar entrar.

### Requisito 6 — Recuperar la contraseña

#### Criterios de aceptación

1. WHEN la persona pide el enlace THEN el sistema DEBE enseñar «Revisa tu correo» con la dirección que escribió, y la opción de cambiarla.
2. El sistema DEBE permitir pedir otro enlace pasados 30 s, con la cuenta atrás a la vista.
3. El texto de «enviado» DEBE ser el mismo exista o no la cuenta (spec 011, R1.3).

### Requisito 7 — Preaviso de los avisos

#### Criterios de aceptación

1. Antes de pedir el permiso de avisos, el sistema DEBE enseñar un ejemplo real del aviso urgente y los tipos de aviso de este teléfono.
2. WHEN la persona toca «Activar avisos» THEN el sistema DEBE abrir el permiso del sistema (iOS, y Android 13 o superior), sin imitarlo.
3. IF la persona no da permiso THEN el sistema DEBE decir que los puede activar en Ajustes y seguir.

### Requisito 8 — Inicio

#### Criterios de aceptación

1. El sistema DEBE enseñar «Hola, {nombre}», el negocio y quién atiende, y cuatro tarjetas que abren su pestaña:
   - **Hoy:** reservas y la siguiente, con marco menta;
   - **Conversaciones:** lo que da la API;
   - **Saldo:** con «para unos N meses» o «N días», según lo que dure;
   - **Este mes:** el gasto en la moneda de la bolsa.
2. WHERE el cliente no tiene un módulo EL sistema NO DEBE enseñar su tarjeta, y las que quedan DEBEN ocupar el espacio.
3. El sistema DEBE enseñar «Lo último en la Bandeja», con dos filas si alguien espera y con cuatro si no.
4. WHEN alguien espera a una persona THEN el sistema DEBE enseñar abajo su tarjeta con el desde cuándo, el motivo, «+N más» si hay más, y «Atender a {nombre}», que abre la conversación en la pestaña Bandeja.
5. WHEN deja de esperar nadie THEN el sistema DEBE enseñar una vez «Todo en orden», con el ✓ que se dibuja, y retirarla a los 3,2 s.

### Requisito 9 — Bandeja

#### Criterios de aceptación

1. El sistema DEBE agrupar las conversaciones por día (Hoy, Ayer, Esta semana y Anteriores) en filas compactas con avatar o foto, el logo de su canal, el nombre, el último mensaje con su autor, la hora y el punto de sin leer.
2. El sistema DEBE ofrecer los filtros Abiertas, Sin leer, Esperan y Resueltas, con el ✓ que se dibuja, y un selector de canal con los canales que tenga el cliente.
3. El sistema DEBE poner primero a quien espera a una persona.
4. WHEN la persona desliza una fila THEN el sistema DEBE resolverla o reabrirla (hacia la izquierda) o marcarla leída o no leída (hacia la derecha), con aviso de «Deshacer».
5. WHEN llega una conversación nueva THEN el sistema DEBE meterla con la micro 3, en su grupo y respetando el filtro.
6. El sistema DEBE cargar por páginas y releer al tirar.
7. El pie de la Bandeja NO DEBE nombrar un canal concreto.
8. El sistema DEBE conservar el filtro por agente cuando el cliente tiene varios agentes.

### Requisito 10 — Búsqueda

#### Criterios de aceptación

1. WHERE el sistema da una pestaña de búsqueda propia (iOS 26) EL sistema DEBE ofrecer la búsqueda ahí y también dentro de la Bandeja. En otro caso (iOS anterior a 26 y Android), la búsqueda DEBE estar en la cabecera de la Bandeja, con las mismas funciones.
2. WHEN la persona escribe THEN el sistema DEBE buscar por nombre, teléfono o cuenta y texto de los mensajes, incluidas las resueltas, respetando el canal elegido.
3. IF no hay resultados THEN el sistema DEBE decir qué se buscó y ofrecer quitar el filtro de canal.

### Requisito 11 — Conversación

#### Criterios de aceptación

1. La cabecera DEBE decir con quién se habla, su canal y quién responde («Atiende {agente}», «Respondes tú» o «Espera a una persona»).
2. El dock DEBE flotar sobre el hilo: la franja del agente con su explicación y «Tomar el control» (o «Atender a {nombre}» si espera), o el cuadro de escribir con adjuntar y enviar.
3. Bajo cada respuesta del agente DEBE estar «Corregir».
4. El menú de la conversación DEBE ofrecer:
   - Contacto;
   - Marcar como no leída;
   - Resolver o Reabrir;
   - Vaciar chat;
   - Eliminar chat, con confirmación.
5. IF la ventana del agente venció THEN el sistema NO DEBE decir «responde el agente», y DEBE decir hasta cuándo puede contestar una persona.
6. WHEN un comentario llega de una publicación THEN el sistema DEBE enseñar la publicación.
7. WHEN la conversación se cerró por inactividad THEN el hilo DEBE decirlo con esas palabras.
8. El sistema DEBE conservar adjuntos, etiquetas, nota, respuestas guardadas, motivos de envío fallido, baja por palabra y la ventana de 24 h.

### Requisito 12 — Contacto

#### Criterios de aceptación

1. El sistema DEBE enseñar el nombre, el canal real con su identificador («Teléfono» en WhatsApp, «Cuenta» en Instagram y Messenger), la primera vez que escribió, sus conversaciones y su próxima reserva.
2. WHEN la persona toca la próxima reserva THEN el sistema DEBE abrirla.

### Requisito 13 — Reservas · Día, Semana y Mes

#### Criterios de aceptación

1. El sistema DEBE ofrecer Día, Semana y Mes, con la tira de días donde «hoy» va en turquesa, sin círculo.
2. El Día DEBE verse en lista (una tarjeta por reserva con el color suave de su estado y su motivo en palabras) y en cuadrícula (horario de apertura, línea de «ahora» y solapes lado a lado).
3. WHEN la persona toca un hueco libre de la cuadrícula THEN el sistema DEBE abrir Nueva reserva con ese día y esa hora.
4. El sistema NO DEBE ofrecer huecos en el pasado.
5. La Semana DEBE enseñar la ocupación de cada día y el Mes un punto por día con reservas.
6. En modo Aforo el sistema DEBE conservar la capacidad del día, las llegadas sin reserva y los bloqueos.
7. El sistema DEBE enseñar el estado real del calendario de Google de cada profesional: conectado, pendiente, falta elegir calendario, hay que volver a conectarlo o falló.

### Requisito 14 — Una reserva

#### Criterios de aceptación

1. La hoja DEBE enseñar las píldoras de estado y origen, y las acciones que permita la API: Abrir el chat, Confirmar, Pedir confirmación, Mover, Llegó, No vino y Cancelar.
2. WHEN la persona cancela THEN el sistema DEBE preguntar si avisa al cliente y si ofrece el hueco a la lista de espera, y DEBE dar «Deshacer».
3. WHEN la persona mueve una reserva THEN el sistema DEBE ofrecer solo huecos libres.
4. Los precios DEBEN salir en la moneda del negocio y con sus decimales.

### Requisito 15 — Nueva reserva

#### Criterios de aceptación

1. El sistema DEBE pedir servicio, con quién, día (los siete días abiertos siguientes), hora (en mañana y tarde, con las ocupadas tachadas), nombre y **teléfono obligatorio y válido** (064 R3).
2. El sistema NO DEBE ofrecer horas antes de la antelación mínima del agente.
3. IF hay datos escritos THEN cerrar sin guardar DEBE pedir confirmación.
4. WHEN se guarda THEN la reserva DEBE entrar animada en el día, con «Deshacer».

### Requisito 16 — Lista de espera

#### Criterios de aceptación

1. El sistema DEBE permitir apuntar a alguien con **teléfono obligatorio**, salvo en una llegada en persona (064 R3.7).
2. El sistema DEBE enseñar las ofertas en curso y permitir pararlas.
3. «Reservarle ahora» y «Quitar» DEBEN funcionar como hoy, con «Deshacer» al quitar.

### Requisito 17 — Ajustes de reservas y de la Bandeja

#### Criterios de aceptación

1. El sistema DEBE permitir cambiar la antelación mínima del agente y los recordatorios, además de lo que ya permite (confirmación, lista de espera, aforo y estancia).
2. El sistema DEBE permitir cambiar el cierre por inactividad de las conversaciones.
3. Lo que solo se edita en la web (horario, equipo, servicios y plantillas) DEBE enseñarse como lectura, sin botones que no hacen nada.

### Requisito 18 — Consumo

#### Criterios de aceptación

1. El sistema DEBE enseñar:
   - el saldo, con para cuánto alcanza a este ritmo;
   - el gasto del mes, con la proyección;
   - las conversaciones del mes y la media por conversación;
   - las barras de 7, 30 y 90 días;
   - el gasto por agente, con su filtro.
2. El sistema NO DEBE ofrecer recargar ni comprar saldo, ni con un botón ni con un enlace. DEBE decir «Pídeselo a {partner}» como texto.
3. WHEN cambia el periodo THEN el total DEBE correr hasta su valor (micro 4).

### Requisito 19 — Ajustes

#### Criterios de aceptación

1. El sistema DEBE enseñar:
   - la cuenta: nombre y correo;
   - el negocio;
   - los canales conectados con su estado;
   - los avisos de este teléfono por tipo;
   - el silencio fuera del horario;
   - la política de privacidad;
   - el soporte;
   - la consola web;
   - cerrar sesión;
   - solicitar el borrado de la cuenta;
   - la versión.
2. WHEN la persona apaga el aviso urgente THEN el sistema DEBE pedir confirmación antes.
3. WHEN la persona cierra sesión THEN el sistema DEBE avisar de que deja de recibir avisos en este teléfono y de que el agente sigue atendiendo.

### Requisito 20 — Nada se pierde

#### Criterios de aceptación

1. El sistema DEBE conservar, con el aspecto nuevo y en las dos plataformas, todo lo que hacía la 1.2.0:
   - **Bandeja:** los filtros y el filtro por agente;
   - **Conversación:** adjuntos (cámara, galería y documentos), etiquetas, nota, respuestas guardadas, corrección de respuestas, motivos de espera y de envío fallido;
   - **Reservas:** Llegó, No vino, la llegada sin reserva, bloqueos, ajustes de reservas, Aforo y la lista de espera;
   - **Consumo:** «Ver en la web»;
   - **Cuenta y app:** los siete tipos de aviso con sus enlaces profundos, «Solicitar el borrado», «Actualizar» cuando la versión es vieja, «Sin acceso», «No es cliente» y Entrar con Google.
2. Cada función de la lista DEBE tener al menos un test que la recorra.

### Requisito 21 — Lo que se ve tiene que ser verdad

#### Criterios de aceptación

1. Todo importe DEBE salir en la moneda de su bolsa o de su negocio, con los decimales que tenga esa moneda.
2. El nombre del agente y el canal DEBEN salir de los datos, nunca de un texto fijo.
3. «Leído» NO DEBE aparecer si la API no lo dice.

### Requisito 22 — Versión y rendimiento

#### Criterios de aceptación

1. La app DEBE salir como **1.3.0**, versión nueva de tienda (pantallas nuevas y un módulo nativo nuevo), y NO DEBE llegar por OTA a builds anteriores.
2. La mediana de 5 arranques en frío hasta Inicio NO DEBE pasar de 1,10 veces la de la 1.2.0, en el mismo teléfono y con la misma cuenta.
3. Con 1.000 conversaciones cargadas, al desplazar la Bandeja NO DEBE tardar más de 16,7 ms más del 1 % de los cuadros.
4. El líquido de Entrar DEBE ir a 50 cuadros por segundo o más en un Android de gama media (referencia: Pixel 6a o Galaxy A35). IF 30 cuadros seguidos tardan más de 20 ms THEN el sistema DEBE pasar al cuadro quieto.
5. Las medidas 22.2 a 22.4 y la comprobación en el simulador de iOS 26 son puerta de la spec 070: la app no se envía a las tiendas sin ellas. También lo son, desde el cierre de la noche: tocar un aviso real en un build de Android (T057) y recorrer en Android lo del Requisito 20 que no se vio en el emulador (T058); y, desde la mañana del 2026-11-21, iOS con builds de EAS: arrancar en frío sin la caída de las categorías de avisos, y que «Salir sin guardar» (15.3) pregunte antes de cerrar la hoja (T061).

### Requisito 23 — Datos de ejemplo en desarrollo

**Historia de usuario:** Como equipo de Auphere, quiero ver y revisar todas las pantallas con un negocio de ejemplo sin depender de un servidor, para verificar el diseño y preparar las capturas.

#### Criterios de aceptación

1. WHERE el build es de desarrollo y se pidió al arrancar (`EXPO_PUBLIC_DEMO=1`) EL sistema DEBE servir toda la app con un negocio ficticio en memoria, con las mismas formas de datos que la API.
2. El sistema NO DEBE incluir los datos de ejemplo en ningún build que no sea de desarrollo: preview, staging ni producción.
3. Los datos de ejemplo DEBEN ser ficticios: personas, teléfonos y correos inventados, sin ningún dato real.

## Fuera de alcance

- **Recargar o comprar saldo** (decisión de Luis; guía 3.1.3(f)).
- **Selector de tamaño de texto propio:** lo hace el sistema.
- **Tema e idioma dentro de la app:** los da el sistema.
- **Enviar en cola sin conexión:** la 031 decidió no encolar; el borrador se conserva.
- **El rol en Ajustes:** la API no lo da.
- **Horas de silencio por rangos:** la API guarda «fuera del horario».
- **Editar horario, equipo, servicios y plantillas; gestionar respuestas guardadas; la campana; «Tus teléfonos»; el detalle de Consumo y su CSV:** siguen en la web.
- **«Iniciar sesión con Apple»:** se defiende la excepción de la guía 4.8. Si App Review la pide, se hace en una spec aparte, porque cambia el backend.
- **Fichas, capturas, cuenta de revisión, configuración de producción y envío:** spec 070.

## Criterios de éxito

- **SC-001**: Las 13 pantallas y 3 de las 4 hojas del diseño (todas menos Recargar) existen en la app y se reconocen en una comparación de capturas con el demo, en claro y en oscuro.
- **SC-002**: El 100 % de las funciones del Requisito 20 siguen disponibles en iOS y en Android, y cada una tiene su test.
- **SC-003**: Cada pantalla que pinta datos tiene sus seis estados, y ninguna enseña una cifra o un nombre escrito a mano.
- **SC-004**: Ninguna pantalla tiene un hallazgo de severidad 3 o 4 en `ux-heuristics`, `design-critique` o `impeccable`, ni un fallo de la auditoría WCAG 2.2 AA.
- **SC-005**: Una persona encuentra una conversación por una palabra que se dijo en menos de 10 s desde Inicio.
- **SC-006**: La mediana de 5 arranques en frío no pasa de 1,10 veces la de la 1.2.0, y con 1.000 conversaciones no más del 1 % de los cuadros de la Bandeja tarda más de 16,7 ms. Lo mide la 070 antes del envío.

## Supuestos

- La API de `main` es la que usará el build (producción); no hace falta ninguna ruta nueva.
- Los clientes de ejemplo de staging bastan para probar; las capturas de las tiendas son de la 070.
- La licencia de Helvena se confirmará fuera de esta spec. Mientras tanto, **ningún build la incrusta** y los títulos van con la fuente del sistema (1.5). El interruptor queda listo: con la licencia confirmada, un build con `APP_HELVENA=1` y los TTF originales en `assets/fonts/helvena/` la activa sin tocar código.
- El líquido de Entrar se dibuja con un motor gráfico nativo que entra como dependencia nueva, con su licencia leída en el plan.
