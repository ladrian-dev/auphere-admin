# Especificación: Aparcar el router y gobernar el precio por modelo

**Rama**: `059-aparcar-router-y-precios` · **Creada**: 2026-11-11 · **Estado**: Implementada en la rama, sin commit, pendiente de la revisión de Luis (2026-11-11)

**Entrada**: descripción del usuario: "Abre una nueva spec para quitar lo del router para trabajarlo correctamente después ya que debemos estudiarlo para mejorarlo, también aplica las recomendaciones que das." Las recomendaciones son las de la auditoría de Plataforma del panel del 2026-11-11, y el alcance lo decidió Luis ese mismo día (nota de KB).

## Encabezado Auphere *(obligatorio)*

| Campo | Valor |
|---|---|
| **Superficie de confianza** | `0`: el panel de operador y su API, que ya existen. No se abre ninguna superficie. |
| **Garantías de aislamiento tocadas** | **1 (RLS), rozada por el requisito 1**. Para saber si un modelo está en uso, la plataforma recorre los agentes de todos los clientes, cada uno bajo su propia RLS, y solo enseña a Auphere cuántos agentes y de qué clientes. No mueve datos entre clientes ni entre contactos, y no lee mensajes. Los requisitos 2 a 6 no tocan ninguna garantía: trabajan sobre datos de plataforma sin cliente (modelos, precios, pesos, números de Auphere) o solo cambian pantallas. |
| **Nota de KB que la justifica** | `[[decisions/2026-11-11-aparcar-router-y-gobernar-precios]]` en `/Users/lmatos/Work/Auphere/nexus/` |
| **Qué se mide** | **Nada nuevo.** No añade llamadas a modelos ni a herramientas de pago. El requisito 3 cambia **cuánto se cobra** por lo que ya se mide (los pesos por carril). El requisito 5.7 puede cambiar el modelo del Playground, que ya se mide con origen QA. |

### Lo que enmienda

| Dónde | Qué decía | Qué dice ahora |
|---|---|---|
| Spec 047, **41.7** (retirar) y **41.9** («No disponible») | Auphere retira un despliegue con su fecha o lo marca «No disponible», sin más condición que el motivo. | No se puede hacer sobre un modelo que la plataforma usa por defecto ni sobre uno con el que respondan agentes. Las dos acciones tienen camino de vuelta (requisito 1). |
| Spec 047, historia 30 y T150 (Router y Certificaciones en el panel) | El panel enseña y edita la política del router y las certificaciones. | El panel las oculta tras un solo ajuste mientras el router se estudia. El código, la API y el runtime se quedan como están (requisito 2). |
| Spec 047, **41.8** (aviso de subida de precio) | Un precio nuevo que sube más de un 10 % el precio estimado por mensaje de un agente avisa a su partner. El porcentaje se calcula sobre el coste. | El coste no avisa a nadie: lo que paga el partner sale de los pesos, y Luis decidió que cambiarlos tampoco avise (requisito 3.12). |
| Spec 007 (multiplicador 2,2 constante) | El objetivo de venta sobre el coste es una constante del código; los pesos solo cambian por migración. | El objetivo es un ajuste de plataforma que Auphere cambia desde el panel, y los pesos se editan desde Modelos. El suelo de 1,5 sigue fijo (requisito 3). |

## Por qué

La auditoría del 2026-11-11 revisó el código, la interfaz en producción y CloudWatch.
Esto es lo que encontró:

- **El router de la 047 no decide nada.** No hubo ninguna decisión en 30 días. Su
  vista previa en producción responde «Sin modelo disponible» para cualquier cliente:
  ningún modelo tiene comprobada la retención cero. Los agentes responden con un
  modelo fijo. Router y Certificaciones enseñan y editan cosas que no cambian lo que
  hace ningún agente, y sus textos afirman protecciones que no existen («Ningún modelo
  habla con un cliente sin haber pasado antes la batería común»).
- **Dos botones de Modelos pueden dejar mudos a todos los agentes.**
  - «No disponible» sobre el modelo de responder lo saca del runtime desde el turno
    siguiente, y la reserva es el mismo modelo.
  - «Retirar» pasa cada agente, en la fecha elegida, a «Automático», que hoy no tiene
    modelo.
  - Ninguno de los dos se deshace desde el panel.
- **El precio de venta no se gobierna.**
  - El coste por modelo se configura y llega al medidor.
  - Lo que paga el partner sale de tres pesos por modelo, calculados con un
    multiplicador fijo en el código. Solo cambian con una migración, y el panel ni
    siquiera los enseña.
  - Si sube un coste, el margen baja en silencio.
- **La tabla de Modelos no cabe en una pantalla.** Los botones quedan fuera, y al
  llegar a ellos no se ve el nombre del modelo de la fila.
- Hay piezas a medias:
  - un botón que no hace nada («Rotar secret»);
  - una galería sin enlace;
  - una beta sin su configuración;
  - un juez que se da por calibrado con la calibración de otro modelo;
  - una evaluación que enseña una cifra que nunca mide;
  - un Playground con los modelos escritos a mano;
  - una pantalla, Números de Auphere, con otro estilo, en voseo y con jerga.

Luis decidió **aparcar el router para estudiarlo y mejorarlo después**, sin borrar
su código, y aplicar el resto de recomendaciones.

## Escenarios de usuario y pruebas *(obligatorio)*

### Historia 1 — Nadie deja mudos a los agentes desde el panel (Prioridad: P1)

Una persona de Auphere entra en Modelos y pulsa «No disponible» o «Retirar» sobre Sol,
el modelo con el que responden los agentes. El panel se lo impide y le dice por qué:
qué tareas de la plataforma lo usan y cuántos agentes responden con él. Sobre un
modelo que nadie usa, las dos acciones funcionan como hoy. Si se equivoca, puede
deshacerlas desde el mismo sitio.

**Por qué esta prioridad**: es el único riesgo de la auditoría que puede tumbar
producción con dos clics, y hoy no tiene vuelta atrás sin SQL.

**Prueba independiente**: intentar las dos acciones sobre cada modelo que el runtime
usa por defecto y comprobar que todas se rechazan sin cambiar su estado. Sobre un
modelo sin uso, aplicarlas y deshacerlas.

**Escenarios de aceptación**:

1. **Dado** que Sol es el modelo de responder, **cuando** Auphere pide «No disponible» sobre Sol, **entonces** el panel lo rechaza, nombra las tareas que lo usan y Sol sigue activo.
2. **Dado** un cliente con sus agentes asignados a Terra, **cuando** Auphere pide «Retirar» Terra, **entonces** se rechaza, diciendo cuántos agentes y de qué clientes.
3. **Dado** un modelo activo que nadie usa, **cuando** Auphere lo marca «No disponible» con un motivo, **entonces** se aplica, y «Volver a disponible» lo devuelve a activo.
4. **Dado** un modelo en retirada, **cuando** Auphere pulsa «Cancelar retirada» con un motivo, **entonces** vuelve a activo y deja de avisarse su retirada.
5. **Dado** que alguien llama a la API directamente, saltándose el panel, **cuando** pide «No disponible» sobre Sol, **entonces** la API también lo rechaza.

---

### Historia 2 — El router se aparca sin borrarlo (Prioridad: P1)

Mientras el router se estudia, el panel no enseña nada que solo tenga sentido con el
router encendido: ni Router, ni Certificaciones, ni el bloque Router de Estado, ni en
Modelos las acciones y columnas que dependen de él. Cuando se retome, un solo ajuste
lo vuelve a mostrar tal como estaba.

**Por qué esta prioridad**: son pantallas que afirman protecciones falsas y dejan
editar cosas sin efecto. Mientras estén a la vista, inducen a error a quien opera.

**Prueba independiente**: con el ajuste apagado, el menú, la paleta de comandos y las
pantallas no muestran nada del router, y sus direcciones dan «no existe». Con el
ajuste encendido, todo aparece como hoy.

**Escenarios de aceptación**:

1. **Dado** el router aparcado, **cuando** Auphere abre el panel, **entonces** el menú no tiene «Router» ni «Certificaciones», y la paleta de comandos tampoco los ofrece.
2. **Dado** el router aparcado, **cuando** alguien abre la dirección de Router o de Certificaciones, **entonces** ve la página de «no existe» del panel.
3. **Dado** el router aparcado, **cuando** Auphere abre Estado, **entonces** no ve el bloque Router; el resto de Estado sigue igual.
4. **Dado** el router aparcado, **cuando** Auphere abre Modelos, **entonces** no ve «Nuevo despliegue», «Activar», «Certificado en» ni «Le falta».
5. **Dado** que se enciende el ajuste, **cuando** Auphere abre el panel, **entonces** todo lo anterior vuelve a aparecer, sin ningún otro cambio.

---

### Historia 3 — Auphere decide el precio de venta de cada modelo (Prioridad: P2)

En Modelos, Auphere ve por cada modelo lo que le cuesta y lo que cobra al partner en
cada carril (entrada, caché, salida), y el multiplicador que resulta. Puede cambiar los
pesos de un modelo, o el multiplicador objetivo de toda la plataforma, con un motivo.
El cambio entra en vigor al guardar, sin avisar a los partners. Si un coste nuevo deja
la venta desfasada, el panel lo dice y propone los pesos que corresponden.

**Por qué esta prioridad**: sin esto, una subida de coste baja el margen en silencio,
y cambiar lo que se cobra exige una migración.

**Prueba independiente**: cambiar los pesos de un modelo desde el panel y comprobar
que la cuota que consume el turno siguiente de un agente con ese modelo usa los pesos
nuevos. Cambiar el multiplicador y comprobar la propuesta.

**Escenarios de aceptación**:

1. **Dado** Sol con su coste y sus pesos, **cuando** Auphere abre Modelos, **entonces** ve el coste y la venta por millón en cada carril, y el multiplicador de cada carril.
2. **Dado** el multiplicador objetivo en 2,2, **cuando** Auphere edita los pesos de Terra, **entonces** el panel le propone los pesos de 2,2 sobre el coste vigente.
3. **Dado** unos pesos que dejan la salida por debajo de 1,5 veces su coste, **cuando** Auphere guarda, **entonces** se rechaza nombrando el carril.
4. **Dado** que Auphere cambia el multiplicador a 2,5 con un motivo y marca «aplicar a todos», **cuando** guarda, **entonces** cada modelo con coste pasa a los pesos de 2,5 y queda auditado.
5. **Dado** un coste nuevo para Sol, **cuando** Auphere lo guarda, **entonces** el diálogo dice que la venta queda desfasada y ofrece aplicar la propuesta.

---

### Historia 4 — La tabla de Modelos se lee y no promete lo que no hace (Prioridad: P2)

La tabla cabe en una pantalla de portátil. El nombre de cada modelo está junto a sus
acciones. Hay una acción principal visible y el resto en un menú, con las
destructivas al final. El diálogo de coste arranca con el coste vigente y la fecha de
hoy, y dice que el coste mueve el margen y no lo que paga el partner. Ningún texto
afirma protecciones que el sistema no aplica.

**Por qué esta prioridad**: hoy solo se ven 2 de 14 modelos por pantalla, y al llegar
a los botones no se ve qué fila se está tocando.

**Prueba independiente**: abrir Modelos a 1280 px de ancho y comprobar que se ven las
acciones de cada fila sin desplazamiento horizontal. Abrir el diálogo de coste y
comprobar que viene precargado.

**Escenarios de aceptación**:

1. **Dado** una pantalla de 1280 px, **cuando** Auphere abre Modelos, **entonces** cada fila muestra el nombre del modelo y su acción principal sin desplazamiento horizontal.
2. **Dado** Sol con coste vigente, **cuando** Auphere abre su diálogo de coste, **entonces** los campos traen el coste vigente y la fecha es hoy.
3. **Dado** una fecha anterior a hoy, **cuando** Auphere guarda un coste, **entonces** se rechaza con su razón.

---

### Historia 5 — Las piezas a medias se terminan o se quitan (Prioridad: P3)

Desaparece lo que no hace nada («Rotar secret», la galería sin enlace, la beta sin
configurar). Lo que mide algo lo mide bien: el juez solo bloquea si está calibrado él,
y la evaluación del constructor dice su cifra real y no enseña una métrica que nunca
mide. El Playground responde con los mismos modelos que un turno real.

**Por qué esta prioridad**: cada pieza es pequeña. Juntas son la diferencia entre un
panel en el que se confía y uno en el que no.

**Prueba independiente**: cada criterio del requisito 5 se comprueba solo.

**Escenarios de aceptación**:

1. **Dado** un modelo calibrado como juez que no es el juez configurado, **cuando** se decide si el juez bloquea las pruebas de un agente, **entonces** no bloquea.
2. **Dado** el banco de evaluación con 120 descripciones, **cuando** Auphere abre Evaluación, **entonces** la pantalla dice 120 y no enseña la cifra de pruebas del sector.
3. **Dado** que el despliegue no tiene la configuración de Meta del alta sin cuenta, **cuando** Auphere abre Canales, **entonces** no ve la subpestaña de la beta.

---

### Historia 6 — Números de Auphere habla como el resto del panel (Prioridad: P3)

La pantalla de los números propios de Auphere usa la misma cabecera, tabla, diálogos y
lenguaje que el resto del panel. Permite cambiar el token y el identificador de número
de Meta, confirma dentro de la página y deja en la auditoría a la persona que hizo el
cambio. En producción está vacía a propósito; su estado vacío dice qué significa.

**Por qué esta prioridad**: hoy no se usa (decisión de Luis), pero cuando se use, un
token caducado no se puede arreglar desde el panel.

**Prueba independiente**: registrar un número en staging, cambiarle el token,
desactivarlo y reactivarlo; comprobar la auditoría.

**Escenarios de aceptación**:

1. **Dado** un número registrado, **cuando** Auphere cambia su token con un motivo, **entonces** el número envía con el token nuevo y la auditoría nombra a esa persona.
2. **Dado** ningún número registrado, **cuando** Auphere abre la pantalla, **entonces** ve un estado vacío que dice que, sin número, Auphere no envía avisos por WhatsApp.

---

### Casos límite

- **Un modelo es a la vez el de responder y el de reserva** (hoy Sol). La protección lo
  cuenta una vez y nombra las dos tareas.
- **La configuración que dice qué modelos usa el runtime no se puede leer.** La
  protección se cierra: rechaza la acción y lo dice, en vez de dejarla pasar.
- **Un modelo que ya estaba «En retirada» antes de esta spec y aún tiene agentes.**
  Llega su fecha. El sistema no retira el modelo ni mueve agentes a un perfil que no
  puede atenderlos. Lo deja en retirada y lo señala en Modelos.
- **«Volver a disponible» sobre un modelo que antes era borrador.** Vuelve a borrador,
  no a activo: recupera el estado que tenía.
- **Un modelo que se cobra por minuto** (Whisper). No tiene carriles de tokens: no
  muestra pesos ni propuesta, y lo dice.
- **Un modelo sin coste vigente.** No hay propuesta de pesos. El panel lo dice y deja
  editar los pesos a mano.
- **El multiplicador baja y algún peso guardado queda por encima.** No es un error: el
  modelo aparece como «Desfasado» hasta que alguien aplica la propuesta.
- **Router aparcado, y alguien llega por un enlace antiguo a Router o Certificaciones.**
  Ve «no existe». Ninguna pantalla visible enlaza a ellas.
- **Ausencia diseñada (constitución §V).** Con el router aparcado no hay botones
  apagados ni textos que expliquen lo que falta: simplemente no está.

## Requisitos *(obligatorio)*

### Requisito 1 — Proteger el modelo en uso

**Historia de usuario:** Como persona de Auphere, quiero que el panel me impida retirar o marcar «No disponible» un modelo en uso, y poder deshacer esas acciones, para no dejar mudos a los agentes con un clic.

#### Criterios de aceptación

1. IF Auphere pide «Retirar» o «No disponible» sobre un modelo que resuelve **cualquier** valor por defecto de la plataforma THEN el sistema DEBE rechazarlo, nombrando cada uso, y NO DEBE cambiar su estado. Hoy esos usos son responder y su reserva, clasificar y su reserva, extraer, simular y juzgar, construir agentes, leer fuentes, identificar el sector, el Playground QA, el freno de reservas, el companion, transcribir, ver imágenes, mejorar agentes y el modelo de los turnos degradados. La lista no es cerrada: un valor por defecto que se añada mañana queda protegido sin tocar esta regla.
2. IF algún agente activo responde con ese modelo, por asignación de su cliente o por elección propia, THEN el sistema DEBE rechazarlo, diciendo cuántos agentes y de qué clientes, y NO DEBE cambiar su estado.
3. WHEN la petición es sobre un modelo que no cumple 1.1 ni 1.2 THEN el sistema DEBE aplicarla como hoy, con motivo y auditoría.
4. El sistema DEBE hacer las comprobaciones 1.1 y 1.2 en el servidor, de modo que una llamada directa a la API se rechace igual que desde el panel.
5. El sistema DEBE juzgar «usado por defecto» con la misma configuración con la que responde el runtime de ese despliegue. Los valores por defecto viven en un solo sitio que leen la API y el runtime, y el runtime publica al arrancar los modelos que usa de verdad, con sus ajustes del despliegue ya aplicados. IF la publicación del runtime falta, está caducada o no coincide con lo que la API conoce THEN el sistema DEBE rechazar la acción, y decir por qué.
6. WHEN un modelo está «En retirada» THEN el panel DEBE ofrecer «Cancelar retirada». Con un motivo, el modelo vuelve a activo, se audita y dejan de salir sus avisos de retirada pendientes.
7. WHEN un modelo está «No disponible» THEN el panel DEBE ofrecer «Volver a disponible». Con un motivo, el modelo vuelve al estado que tenía antes de marcarlo, sin pasar por la puerta de activación, y se audita.
8. IF llega la fecha de retirada de un modelo y algún agente sigue respondiendo con él sin un sustituto que pueda atenderle THEN el sistema NO DEBE retirarlo ni mover ese agente a un perfil sin modelo. DEBE dejarlo en retirada, marcarlo en Modelos como «Retirada detenida» con el número de agentes, y registrar cada día un aviso de plataforma hasta que se resuelva. Ninguna de esas señales puede quedar oculta por el requisito 2. Si el proveedor apaga el modelo de verdad (GPT-4o, el 14-ene-2027), esos agentes fallarán: la señal existe para que Auphere los mueva antes.
9. El texto de cada diálogo DEBE decir lo que la acción hace de verdad en el runtime, sin mencionar un router que no decide.

### Requisito 2 — Aparcar el router en el panel

**Historia de usuario:** Como persona de Auphere, quiero que el panel no enseñe el router mientras se estudia, sin perder su código, para no operar sobre pantallas sin efecto.

#### Criterios de aceptación

1. El sistema DEBE controlar con un solo ajuste si el router está aparcado o visible en el panel. Por defecto está aparcado.
2. WHILE el router esté aparcado, el menú y la paleta de comandos NO DEBEN ofrecer «Router» ni «Certificaciones».
3. WHILE el router esté aparcado, abrir las direcciones de Router (incluidas sus anomalías) o de Certificaciones DEBE dar la página de «no existe» del panel.
4. WHILE el router esté aparcado, Estado NO DEBE mostrar el bloque Router, y el resto de Estado DEBE seguir igual. Este criterio depende de los 1.1 a 1.4 y 1.8: el bloque es hoy la única alarma si alguien retira el modelo de responder, y solo puede ocultarse en la misma entrega que la protección, nunca antes.
5. WHILE el router esté aparcado, Modelos NO DEBE mostrar «Nuevo despliegue», «Activar», la columna «Certificado en» ni «Le falta».
6. WHILE el router esté aparcado, ninguna pantalla visible DEBE enlazar a Router ni a Certificaciones.
7. WHEN el ajuste pasa a visible THEN el sistema DEBE mostrar todo lo anterior como antes de esta spec, sin ningún otro cambio.
8. Aparcar el router NO DEBE cambiar ninguna respuesta de la API del router o de certificaciones, ni nada de lo que hacen los agentes.

### Requisito 3 — Precio de venta por modelo

**Historia de usuario:** Como persona de Auphere, quiero ver y decidir lo que cobro por cada modelo, para que una subida de coste no me coma el margen sin enterarme.

#### Criterios de aceptación

1. WHEN Auphere abre Modelos THEN el sistema DEBE mostrar, por cada modelo cobrado por tokens, el coste vigente, el precio de venta por millón y el multiplicador sobre el coste en cada carril (entrada, caché, salida).
2. WHEN Auphere guarda los pesos de un modelo con un motivo THEN el sistema DEBE guardarlos, auditarlos con la persona y el motivo, y aplicarlos a lo que paga el partner en 5 minutos como mucho. NO DEBE avisar a los partners.
3. WHEN Auphere edita los pesos de un modelo con coste vigente THEN el sistema DEBE proponer los pesos que corresponden al multiplicador objetivo sobre ese coste.
4. IF unos pesos dejan algún carril por debajo de 1,5 veces su coste THEN el sistema DEBE rechazarlos nombrando el carril.
5. IF unos pesos traen unos carriles y otros no THEN el sistema DEBE rechazarlos: van los tres o ninguno.
6. WHEN Auphere cambia el multiplicador objetivo con un motivo THEN el sistema DEBE guardarlo como ajuste de la plataforma y auditarlo. DEBE ofrecer, en el mismo paso, aplicar los pesos propuestos a todos los modelos con coste. Si no se elige, ningún peso cambia.
7. IF el multiplicador objetivo es menor que 1,5 THEN el sistema DEBE rechazarlo.
8. WHERE los pesos de un modelo no corresponden al multiplicador objetivo, la tabla DEBE marcarlo «Desfasado». WHERE algún carril queda por debajo de 1,5, DEBE marcarlo como peligro.
9. WHEN un coste nuevo deja desfasados los pesos de su modelo THEN el diálogo de coste DEBE decirlo y ofrecer aplicar la propuesta.
10. La comprobación de pesos desfasados que ya registra la plataforma DEBE usar el multiplicador objetivo vigente, no una constante.
11. WHERE un modelo se cobra por minuto, Modelos DEBE decir que no tiene pesos por carril y NO DEBE ofrecer editarlos.
12. WHEN cambia el coste de un modelo THEN el sistema NO DEBE avisar a los partners: el coste solo mueve el margen de Auphere, y lo que paga el partner cambia solo con los pesos (3.2).

### Requisito 4 — Modelos legible y honesto

**Historia de usuario:** Como persona de Auphere, quiero una tabla de Modelos que quepa en mi pantalla y un diálogo de coste que me diga lo que hay, para no equivocarme de fila ni de cifra.

#### Criterios de aceptación

1. WHEN Auphere abre Modelos en una pantalla de 1280 px THEN la tabla DEBE caber sin desplazamiento horizontal, con el nombre de cada modelo visible en la misma vista que sus acciones.
2. Cada fila DEBE tener una acción principal visible («Precio») y el resto en un menú, con las destructivas al final y separadas del resto.
3. WHEN Auphere abre el diálogo de coste de un modelo con coste vigente THEN los campos DEBEN venir precargados con él y la fecha DEBE ser la de hoy.
4. IF la fecha de un coste nuevo es anterior a hoy THEN el sistema DEBE rechazarlo con su razón.
5. El diálogo de coste DEBE decir, antes de guardar, que el coste mueve el margen y no lo que paga el partner, y cuál sería el multiplicador de cada carril con el coste nuevo y los pesos actuales.
6. El panel NO DEBE afirmar protecciones que el sistema no aplica: ni la cabecera de Modelos ni el texto de ningún diálogo.
7. Modelos DEBE tener sus estados de carga, vacío, error y parcial. IF la lista se lee pero falta el ajuste del multiplicador THEN DEBE mostrar los modelos y decir que no puede proponer pesos.

### Requisito 5 — Terminar o quitar las piezas a medias

**Historia de usuario:** Como persona de Auphere, quiero que cada botón haga algo y cada cifra mida algo, para fiarme del panel.

#### Criterios de aceptación

1. Números de Auphere NO DEBE ofrecer «Rotar secret» ni enseñar si un número tiene secreto propio o compartido.
2. La galería de pruebas del Playground QA DEBE dejar de existir: su dirección DEBE dar «no existe».
3. WHILE el despliegue no tenga la configuración de Meta del alta sin cuenta, Canales NO DEBE mostrar la subpestaña de la beta. WHEN la tenga, DEBE mostrarla como hoy.
4. WHEN se decide si el juez bloquea las pruebas de un agente THEN el sistema DEBE contar solo una calibración aprobada y vigente del modelo que hace de juez en ese despliegue.
5. La pantalla de Calibración del juez DEBE decir qué modelo hace de juez y si ese modelo está calibrado.
6. La Evaluación del constructor DEBE decir el número real de descripciones del banco, y NO DEBE enseñar la cifra de pruebas del sector mientras la evaluación no la mida.
7. El Playground QA DEBE clasificar y responder con los mismos modelos que el runtime del despliegue.

### Requisito 6 — Números de Auphere con el estilo del panel

**Historia de usuario:** Como persona de Auphere, quiero gestionar los números de Auphere como el resto del panel, para poder arreglar un token caducado sin tocar la base.

#### Criterios de aceptación

1. La pantalla DEBE usar la cabecera, la tabla, los diálogos y el lenguaje del resto del panel: español neutro, sin términos de proveedor sin explicar y con título propio en la pestaña del navegador.
2. WHEN Auphere edita un número THEN DEBE poder cambiar su token y su identificador de número de Meta, con un motivo.
3. Las confirmaciones DEBEN estar dentro de la página, no en diálogos del navegador.
4. Cada cambio DEBE quedar auditado con la persona del panel que lo hizo.
5. WHEN no hay ningún número THEN la pantalla DEBE decir que, sin un número, Auphere no envía avisos ni consultas por WhatsApp, y ofrecer registrar uno.

### Entidades clave

- **Modelo (despliegue)**: un modelo en un proveedor, con su estado, su coste con
  vigencia y sus tres pesos de venta. Dato de plataforma, sin cliente: no lo alcanza
  ninguna RLS de cliente.
- **Multiplicador objetivo de venta**: el múltiplo del coste que Auphere quiere cobrar,
  igual para toda la plataforma. Dato de plataforma, sin cliente. Su suelo (1,5) no
  es un ajuste.
- **Uso de un modelo**: las tareas de la plataforma que lo usan por defecto, más los
  agentes activos que responden con él. Los agentes son de cada cliente y se leen
  bajo su RLS; a Auphere solo le llegan el recuento y los nombres de los clientes.
- **Número de Auphere**: un número de WhatsApp propio de Auphere, con su identificador
  de Meta y su token cifrado. Dato de plataforma, sin cliente.
- **Ajuste «router visible»**: si el panel enseña o no las pantallas del router. Es
  del panel, no de la API.

## Criterios de éxito *(obligatorio)*

- **CE-001**: ninguna secuencia de acciones en el panel ni en la API deja sin modelo a
  un agente. Probado sobre cada modelo que el runtime usa por defecto: el 100 % de los
  intentos de «Retirar» y «No disponible» se rechazan y el modelo no cambia de estado.
- **CE-002**: una persona de Auphere cambia el precio de venta de un modelo en menos de
  un minuto, sin migración, y el turno siguiente de un agente con ese modelo, pasados
  5 minutos como mucho, consume cuota con los pesos nuevos.
- **CE-003**: a 1280 px, Modelos muestra los 14 modelos de producción con el nombre y la
  acción principal de cada uno, sin desplazamiento horizontal.
- **CE-004**: ninguna pantalla visible del panel afirma una protección que el sistema
  no aplica. Comprobado leyendo los textos de Modelos, Estado y Constructor.
- **CE-005**: volver a mostrar el router en el panel es cambiar un solo ajuste, sin
  ningún otro cambio de código.
- **CE-006**: el Playground QA y un turno real del mismo agente usan el mismo modelo.

## Fuera de alcance

- **Estudiar, encender o cambiar el router y las certificaciones**: es el estudio
  pendiente desde el 2026-11-05, en otra spec.
- **Borrar el código del router, su API o sus tablas**: Luis lo quiere intacto.
- **Registrar un número de Auphere en producción**: está vacío a propósito.
- **Avisar a los partners de un cambio de precio**, de coste o de venta: decisión de
  Luis. El aviso por subida de coste que existía se retira (requisito 3.12).
- **Pesos con fecha de vigencia**: entran al guardar. La vigencia queda para el coste.
- **Medir la cifra de pruebas del sector en la evaluación**: cuesta modelo por cada
  borrador. Se deja de enseñar hasta que se decida medirla.
- **Los demás sitios de la API que auditan con un trozo del token de admin**: solo se
  arregla Números de Auphere.
- **La lista de canales escrita a mano en la consola de partners, reordenar Canales y
  dar buscador al Playground**: observaciones de la auditoría sin decisión.

## Supuestos

- «Usado por defecto» es lo que el despliegue configura para cada tarea, variables de
  entorno incluidas. Hoy la API no conoce el modelo de responder del worker. Se
  corrige sin tocar la infraestructura (decisión de Luis, requisito 1.5): los valores
  por defecto en un solo sitio del código, y la publicación del runtime.
- **Una sola entrega** (decisión de Luis): las seis partes se revisan y fusionan
  juntas. Dentro de ella, `tasks.md` ordena la protección (requisito 1) antes que
  ocultar el bloque Router de Estado (2.4).
- Lo que cobra hoy son los tres pesos por carril. El peso único antiguo ya no cobra
  nada: solo lo usa la consola como respaldo para mostrar pesos ausentes.
- Lo que se cobra al partner son los pesos guardados. El multiplicador es el objetivo
  con el que se proponen y se comprueban, no una fórmula que los recalcule sola. Se
  mantiene la separación de la spec 007: un cambio de coste no se traslada solo al
  partner.
- Los modelos por minuto (Whisper) se valoran por otra vía y quedan fuera de los pesos.
- «Retirar» y «No disponible» siguen existiendo para modelos sin uso, como GPT-4o, que
  OpenAI retira el 14 de enero de 2027.
- El ajuste del router vive en el panel, con un único punto de cambio, y aparcado es
  el valor por defecto en todos los entornos.
