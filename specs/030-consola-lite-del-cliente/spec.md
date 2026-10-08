# Especificación: la consola lite — el cliente final entra en la misma consola

**Rama**: `030-consola-lite-del-cliente` · **Creada**: 2026-10-08 · **Estado**: Borrador

**Entrada**: diseño «Consola Lite.dc.html» (Claude Design, proyecto
`e443cbee-f802-4f49-8ec6-422e1d8d97e6`, sincronizado el 2026-10-06) y
decisiones del owner del 2026-10-08: ver §Origen y §Clarifications.

## Encabezado Auphere *(obligatorio)*

| Campo | Valor |
|---|---|
| **Superficie de confianza** | `0` — API de la consola. Entra un tipo de persona nuevo (el usuario de un cliente) por la misma puerta; no entra nada nuevo de fuera: los mensajes y archivos siguen llegando y saliendo por el WhatsApp que ya está conectado |
| **Garantías de aislamiento tocadas** | **1** (RLS: las tablas nuevas son por cliente, y el cliente de quien entra sale de su acceso, nunca de la petición) · **2** (la lista blanca de herramientas pasa a ser por agente: un agente nunca ve las herramientas de otro agente del mismo cliente) · **4** (el hilo sigue siendo uno por cliente final y número, y cada número es de un solo agente) · **5** (el prompt se renderiza por agente) · **8** (sin cambio de regla: ninguna herramienta nueva acepta cliente final como argumento). **Ejes nuevos**: persona de un cliente ↔ persona de otro cliente del mismo partner, y persona del partner ↔ cuerpos de mensaje (C8). Cada uno lleva su test de barrido |
| **Nota de KB que la justifica** | `[[ADR-041-consola-lite-del-cliente-final]]` · `[[PLAN-CONSOLE-V1]]` C2, C3, C4, C8, C9 |
| **Qué se mide** | Nada nuevo en el modelo: no hay clasificador ni resúmenes nuevos. Los mensajes que una persona envía desde la Bandeja entran en el medidor de mensajes enviados como cualquier mensaje saliente, a cuenta del cliente. El medidor gana la dimensión **agente** para que el gasto se pueda leer por agente |

> La superficie es la que ya está abierta (`0`). No se abre ninguna nueva: el
> valor cabe entero dentro de la consola y del canal que ya existen.

## Origen

Hasta hoy la consola tiene un solo tipo de persona: el miembro de un partner,
que ve toda su cartera de clientes. El negocio que atiende el agente —el
cliente final— no entra en ningún panel. Si quiere saber qué pasa con sus
clientes, se lo pregunta a su partner o a Auphere; si una conversación
necesita a una persona, se entera por WhatsApp o no se entera.

El diseño «Consola Lite» propone darle al negocio **la misma consola**,
reducida a lo suyo: su Panel, su Consumo y una Bandeja de entrada donde lee y
contesta a sus clientes, con uno o varios agentes y con la posibilidad de
entrar en una conversación y devolverla.

Medido en el código el 2026-10-08:

1. **Identidad.** Toda persona de la consola es miembro de un partner y ve
   todos sus clientes. No existe una persona atada a un solo cliente.
2. **Admin.** El panel de Auphere no puede dar acceso a nadie a la consola: el
   primer usuario de un partner se crea con un script. No hay pantalla de
   personas ni de invitaciones.
3. **Panel y Consumo.** Existen para la cartera entera. Las piezas que los
   calculan ya aceptan una lista de clientes, pero varias cifras (el saldo del
   partner, el gasto fuera de clientes, las alertas) son del partner entero.
4. **Conversaciones.** La consola del partner solo recibe metadatos (C8), por
   diseño y con test de aislamiento que lo vigila. El panel de Auphere sí
   tiene una bandeja: lista, hilo, tomar el control con protección contra
   dos personas a la vez, enviar texto y avisos en vivo.
5. **Escalado.** Cuando el agente pide ayuda, la conversación se marca, pero
   **el agente sigue respondiendo** y el siguiente mensaje del cliente final
   abre una conversación nueva: el hilo se pierde. «Resuelta» no existe.
6. **Archivos.** Los que llegan se guardan; una persona no puede enviar
   ninguno. La ventana de 24 horas de WhatsApp no se comprueba antes de
   enviar: el mensaje falla después.
7. **Agentes.** Cada cliente tiene **un** agente, con versiones. Diez piezas
   del sistema lo suponen: la entrada de mensajes, el despachador, el
   cargador del agente, las versiones, el medidor, las pantallas del partner
   y las del admin. No existe traspaso entre agentes.
8. **Canales.** Solo se usa WhatsApp por Meta. YCloud y TikTok existen en el
   código y no se usan; Instagram y Messenger no existen.
9. **Dinero.** Investigando el saldo del cliente apareció un doble descuento
   del tope por cliente en cada turno. Va por el flujo de bug, aparte (ver
   §Supuestos).

## Clarifications

### Session 2026-10-08

- Q: ¿Consola nueva o la misma? → A: **La misma** (owner). Panel y Consumo son las pantallas que ya existen, para un único cliente: el de quien entra. Lo único nuevo es la Bandeja de entrada.
- Q: ¿A qué clientes va? → A: **Directos de Auphere y clientes de partners.** Los directos cuelgan de Auphere Internal Partner. El acceso lo da a mano el equipo de Auphere desde el admin.
- Q: ¿Los módulos se eligen por cliente o por usuario? → A: **Por cliente.** Se eligen una vez y los ven todos sus usuarios.
- Q: ¿Qué dinero ve el cliente? → A: **El mismo consumo final que ya enseña la consola**, en US$. Nunca nuestro coste.
- Q: ¿Qué hace «Comprar saldo»? → A: **Nada: el saldo es de solo lectura.** Se ve el saldo y los días que alcanza; si se queda corto, el aviso dice a quién acudir. C2 sigue en pie.
- Q: ¿Quién tiene Bandeja? → A: **Solo los usuarios de clientes finales, y solo si el cliente tiene su WhatsApp conectado.** El partner sigue sin cuerpos de mensaje.
- Q: ¿Entra el multiagente en esta spec? → A: **Sí** (owner, sabiendo que toca el runtime): de 1 a N agentes por cliente, con traspaso agente ↔ persona y entre agentes.
- Q: ¿Qué canales? → A: **Solo WhatsApp por Meta.** Ni YCloud ni TikTok.
- Q: ¿Qué agente atiende una conversación nueva, y puede un agente pasarla a otro? → A: **La Bandeja sigue el patrón de la de Meta: junta los canales, no reparte un número entre agentes** (owner). Un cliente puede tener más de un agente y un agente puede tener uno o más canales conectados, pero **un número de WhatsApp es de un solo agente**. La conversación la atiende el agente de su número; no hay clasificador ni traspaso entre agentes. El traspaso de la Bandeja es agente ↔ persona.
- Q: ¿Dónde se crean y editan los agentes? → A: **Con el flujo que ya existe** (owner): cada agente se configura con el mismo editor de hoy (plantilla → borrador → publicar). Lo que se añade es poder tener más de uno por cliente —hoy no existe, confirmado por el owner— y asignar cada número a un agente.
- Q: ¿El agente se calla al pedir ayuda? → A: **Se calla si el cliente tiene Bandeja** hasta que una persona toma el control, se la devuelve o la resuelve. Sin Bandeja sigue respondiendo como hoy, porque nadie la atendería. En los dos casos el siguiente mensaje sigue en el mismo hilo.

## Escenarios de usuario y pruebas *(obligatorio)*

### Historia 1 — Auphere da acceso a un cliente desde el admin (Prioridad: P1)

En la ficha de un cliente del panel de Auphere, una sección «Acceso del
cliente» permite activar la consola lite, elegir sus módulos (Panel, Bandeja de
entrada, Consumo) e invitar a sus personas por correo. La lista de personas
dice quién ha entrado, quién tiene la invitación pendiente y permite reenviar o
revocar.

**Por qué esta prioridad**: sin esto nadie entra. Es la puerta, y la abre
Auphere a mano.

**Prueba independiente**: activar el acceso de un cliente de prueba con Panel y
Consumo, invitar un correo, aceptar la invitación y entrar.

**Escenarios de aceptación**:

1. **Dado** un cliente que pertenece a un partner, **cuando** un operador activa
   el acceso con Panel y Consumo e invita a `valeria@minegocio.com`,
   **entonces** ella recibe un correo con un enlace para crear su contraseña y
   el operador la ve como «Invitación pendiente».
2. **Dado** un cliente sin WhatsApp conectado, **cuando** el operador mira los
   módulos, **entonces** Bandeja de entrada no se puede elegir y una línea dice
   que necesita el WhatsApp conectado.
3. **Dado** una persona con acceso, **cuando** el operador la revoca,
   **entonces** sus sesiones abiertas se cierran y no vuelve a entrar.
4. **Dado** cualquier cambio de acceso, **cuando** se guarda, **entonces** la
   auditoría dice qué operador lo hizo.

---

### Historia 2 — El cliente entra y ve solo lo suyo (Prioridad: P1)

Valeria entra por la misma página de acceso que un partner. La consola le
enseña una barra lateral con los módulos de su cliente —en el orden Panel,
Bandeja de entrada, Consumo—, la marca con la insignia «lite» y, al pie, su
nombre y el de su negocio. Nada más: ni Clientes, ni Auditoría, ni Equipo, ni
nada del partner.

**Por qué esta prioridad**: es la frontera nueva. Si deja ver algo de otro
cliente o del partner, no se puede abrir a nadie.

**Prueba independiente**: con dos clientes del mismo partner, entrar como
usuario del primero e intentar llegar a cualquier pantalla del partner y a
cualquier dato del segundo.

**Escenarios de aceptación**:

1. **Dado** un cliente con Panel y Consumo, **cuando** su usuario entra,
   **entonces** aterriza en el Panel y la barra tiene exactamente esos dos
   módulos.
2. **Dado** un cliente con solo Bandeja, **cuando** su usuario entra,
   **entonces** aterriza en la Bandeja.
3. **Dado** un usuario de cliente, **cuando** escribe a mano la dirección de una
   pantalla del partner o de un módulo que su cliente no tiene, **entonces**
   vuelve a su primer módulo, sin una pantalla que explique lo que no tiene.
4. **Dado** dos clientes del mismo partner, **cuando** el usuario del primero
   pide cualquier dato del segundo, **entonces** la respuesta es la misma que
   si no existiera.
5. **Dado** un usuario de cliente, **cuando** olvida su contraseña, **entonces**
   la recupera por el mismo camino que un partner.

---

### Historia 3 — El Panel de un solo cliente (Prioridad: P1)

El Panel saluda por el nombre («Hola, Valeria», con el negocio encima) y
enseña lo mismo que el partner ve de ese cliente: el gasto del mes, las
conversaciones de los últimos 7 días con su tendencia, lo que espera a una
persona, el saldo con los días que alcanza y las conversaciones por día. Debajo,
«Necesita tu atención» cuando algo lo pide, o una línea tranquila cuando no.

**Por qué esta prioridad**: es lo primero que ve el negocio y reutiliza lo que
ya existe.

**Prueba independiente**: con 7 días de actividad sembrada, comparar cada cifra
del Panel del cliente con la que ve su partner para ese mismo cliente.

**Escenarios de aceptación**:

1. **Dado** un cliente con un solo agente, **cuando** su usuario abre el Panel,
   **entonces** el gasto del mes es un importe sin desglose.
2. **Dado** un cliente con varios agentes, **cuando** abre el Panel,
   **entonces** el gasto del mes se desglosa por agente.
3. **Dado** un saldo que alcanza para menos días de los que quedan de mes,
   **cuando** abre el Panel, **entonces** «Necesita tu atención» dice para
   cuántos días alcanza y a quién pedir más saldo, sin botón de compra.
4. **Dado** conversaciones esperando a una persona y el módulo Bandeja,
   **cuando** abre el Panel, **entonces** ve cuántas y un botón «Atender» que
   lleva a la primera.
5. **Dado** un cliente sin módulo Bandeja, **cuando** abre el Panel, **entonces**
   no hay tarjeta de «Esperan a una persona» ni fila de atención sobre ella.

---

### Historia 4 — El Consumo de un solo cliente (Prioridad: P1)

Consumo enseña el saldo de su cliente y los días que alcanza, el gasto del mes
con la proyección a fin de mes, las conversaciones del mes con lo que cuesta
cada una de media, el gasto por día en 7, 30 o 90 días y, plegado, el detalle
técnico con su exportación. Con varios agentes, una tabla de gasto por agente y
un filtro por agente en la gráfica. Nunca un botón de compra, ni el saldo del
partner, ni otros clientes.

**Prueba independiente**: con gasto sembrado, comparar las cifras con las del
partner para ese cliente y descargar el CSV.

**Escenarios de aceptación**:

1. **Dado** un cliente con tope asignado, **cuando** su usuario abre Consumo,
   **entonces** ve su saldo en US$ y para cuántos días alcanza al ritmo actual.
2. **Dado** un mes sin gasto suficiente para proyectar, **cuando** mira el gasto
   del mes, **entonces** no ve una proyección inventada.
3. **Dado** varios agentes, **cuando** filtra la gráfica por uno, **entonces**
   solo ve el gasto de ese agente.
4. **Dado** que exporta el detalle técnico, **cuando** abre el archivo,
   **entonces** solo contiene lo de su cliente.

---

### Historia 5 — La Bandeja: ver y leer las conversaciones (Prioridad: P1)

La Bandeja lista las conversaciones del negocio de la más reciente a la más
antigua: quién escribe, cuándo, el último mensaje con quién lo dijo («Ventas:
…», «Tú: …»), si está sin leer y su estado («Necesita humano», «Tú respondes»,
«Resuelta»). Se filtra por no leídos, por las que necesitan a una persona y por
resueltas, y se busca por nombre, teléfono o texto. Al abrir una se ve el hilo
entero: los mensajes del contacto, los del agente con su nombre, los de las
personas con el suyo, las notas de lo que pasó y los archivos.

**Por qué esta prioridad**: leer es la mitad barata de la Bandeja y ya entrega
valor sin escribir nada.

**Prueba independiente**: con conversaciones sembradas, filtrar, buscar, abrir
una y ver que llega un mensaje nuevo sin recargar.

**Escenarios de aceptación**:

1. **Dado** un mensaje nuevo de un contacto, **cuando** la Bandeja está abierta,
   **entonces** la conversación sube arriba y se marca sin leer en segundos, sin
   recargar.
2. **Dado** un contacto que manda una foto, **cuando** se abre el hilo,
   **entonces** la foto se ve; un documento se ve con su nombre, y un audio con
   su transcripción si la hay.
3. **Dado** filtros que no devuelven nada, **cuando** se aplican, **entonces**
   se lee «No hay conversaciones con estos filtros», distinto de una bandeja
   que todavía no ha recibido ninguna.
4. **Dado** un cliente con un solo canal conectado, **cuando** abre la Bandeja,
   **entonces** no hay pestañas de canal.

---

### Historia 6 — Entrar en una conversación, contestar y devolverla (Prioridad: P1)

Mientras el agente responde, el cuadro de escritura dice «El agente de ventas
está respondiendo en WhatsApp. Si quieres escribir tú, toma el control.» Al
pulsar «Tomar el control», el agente deja de responder en esa conversación, el
hilo lo anota y la persona escribe: Enter envía, Mayúsculas+Enter salta de
línea. «Devolver al agente de ventas» le devuelve la conversación, y el agente
retoma en el siguiente mensaje sabiendo lo que hizo la persona.

**Por qué esta prioridad**: es la razón de ser de la Bandeja.

**Prueba independiente**: tomar el control, enviar un mensaje que llega al
WhatsApp del contacto, devolver la conversación y ver que el agente responde al
siguiente mensaje sin volver a saludar.

**Escenarios de aceptación**:

1. **Dado** una conversación atendida por el agente, **cuando** una persona toma
   el control, **entonces** el agente no responde al siguiente mensaje del
   contacto y el hilo dice «Tomaste el control».
2. **Dado** dos personas del mismo negocio en la misma conversación, **cuando**
   la segunda actúa sobre un estado que ya cambió, **entonces** ve el estado
   real y nada se pisa en silencio.
3. **Dado** que han pasado más de 24 horas desde el último mensaje del contacto,
   **cuando** la persona intenta escribir, **entonces** el cuadro dice que
   WhatsApp no deja escribir hasta que el contacto vuelva a hacerlo, y no deja
   enviar.
4. **Dado** un mensaje que WhatsApp rechaza, **cuando** falla, **entonces** el
   mensaje queda marcado como no enviado con el motivo.

---

### Historia 7 — Lo que espera a una persona (Prioridad: P2)

Cuando el agente pide ayuda —un reembolso, un presupuesto, un cambio que no
puede hacer—, la conversación pasa a «Esta conversación espera a una persona»
con el motivo que dio el agente y un botón «Tomar el control». La campana avisa
a las personas del negocio, el Panel lo cuenta, y el siguiente mensaje del
contacto sigue en el mismo hilo.

**Prueba independiente**: hacer que el agente pida ayuda en una conversación y
ver el aviso en la campana, la cifra en el Panel y el estado en la Bandeja.

**Escenarios de aceptación**:

1. **Dado** que el agente pide ayuda, **cuando** pasa, **entonces** el hilo
   muestra el aviso con el motivo, la conversación sale en «Necesita humano» y
   la campana avisa.
2. **Dado** una conversación que espera a una persona, **cuando** el contacto
   vuelve a escribir, **entonces** el mensaje aparece en el mismo hilo.
3. **Dado** que una persona toma el control de una conversación que esperaba,
   **cuando** lo hace, **entonces** deja de contar como «espera a una persona».

---

### Historia 8 — Resolver, reabrir y marcar como no leída (Prioridad: P2)

Una conversación se marca como resuelta y sale de la lista por defecto; si el
contacto vuelve a escribir, se reabre y responde el agente. Se puede reabrir a
mano. Cualquier conversación se puede marcar como no leída para volver a ella.

**Escenarios de aceptación**:

1. **Dado** una conversación resuelta, **cuando** el contacto escribe de nuevo,
   **entonces** vuelve a la lista sin resolver y responde el agente.
2. **Dado** una conversación leída, **cuando** la persona la marca como no
   leída, **entonces** vuelve a contar en el número de no leídas de la barra,
   solo para ella.

---

### Historia 9 — El panel de contacto (Prioridad: P2)

A la derecha del hilo, plegable: el resumen que escribió el agente, los datos
del contacto (quién lo atiende, canal, teléfono, primer mensaje, cuántas
conversaciones), la actividad (pidió ayuda, tomaste el control, devuelta,
resuelta), etiquetas que se ponen y se quitan con sugerencias de las que ya usa
el negocio, y notas internas que solo ve el equipo.

**Escenarios de aceptación**:

1. **Dado** una nota interna, **cuando** se guarda, **entonces** el contacto
   no la recibe nunca y el agente no la lee.
2. **Dado** una conversación en la que el agente no escribió ningún resumen,
   **cuando** se abre el panel, **entonces** no hay sección de resumen vacía.
3. **Dado** una etiqueta nueva, **cuando** se pone en una conversación,
   **entonces** aparece como sugerida en las demás del mismo negocio.

---

### Historia 10 — Respuestas guardadas y archivos (Prioridad: P2)

Con el control tomado, la persona puede insertar una respuesta guardada del
negocio y adjuntar una imagen o un documento. Las respuestas guardadas se crean
y se editan desde el mismo desplegable.

**Escenarios de aceptación**:

1. **Dado** una respuesta guardada, **cuando** se elige, **entonces** su texto
   queda en el cuadro para revisarlo antes de enviar.
2. **Dado** un archivo de un tipo o tamaño que WhatsApp no admite, **cuando** se
   adjunta, **entonces** se rechaza antes de enviarlo, diciendo el límite.

---

### Historia 11 — Varios agentes por cliente (Prioridad: P2)

Un cliente puede tener varios agentes —soporte, ventas, eventos—, cada uno con
su nombre, su prompt, sus herramientas y sus versiones, y cada uno con uno o
más números de WhatsApp. Un número es de un solo agente: la conversación la
atiende el agente de su número. La Bandeja junta los números de todos los
agentes del cliente, como la de Meta junta canales: cada fila lleva la etiqueta
de su agente, la lista se filtra por agente, y Panel y Consumo desglosan el
gasto por agente. Los clientes que hoy tienen un agente siguen exactamente
igual.

**Por qué esta prioridad**: el diseño lo pide y el negocio con varias áreas lo
necesita, pero la Bandeja ya entrega su valor con un solo agente; por eso va
después de leer y contestar.

**Prueba independiente**: con un cliente de dos agentes, cada uno con su número,
escribir a cada número y ver que responde su agente, que la Bandeja enseña las
dos conversaciones con su etiqueta y que el gasto de cada una cae en la fila de
su agente.

**Escenarios de aceptación**:

1. **Dado** un cliente con un solo agente, **cuando** se despliega este cambio,
   **entonces** su agente responde igual que antes y nada de la consola habla de
   agentes en plural.
2. **Dado** un cliente con el agente de soporte en un número y el de ventas en
   otro, **cuando** un contacto escribe al de ventas, **entonces** responde el
   agente de ventas y la fila de la Bandeja lleva su etiqueta.
3. **Dado** una conversación que una persona devuelve, **cuando** la devuelve,
   **entonces** vuelve al agente de su número, nunca a otro.
4. **Dado** varios agentes, **cuando** se mira el gasto del mes, **entonces**
   cada agente tiene su parte y suman el total.
5. **Dado** que hay que añadir un agente a un cliente, **cuando** se hace,
   **entonces** se configura con el mismo editor de hoy y se le asignan números
   en Canales.

---

### Historia 12 — Buscar desde cualquier pantalla (Prioridad: P3)

⌘K enfoca la búsqueda de la barra superior; Enter abre la Bandeja con esa
búsqueda aplicada.

---

### Casos límite

- **Cliente sin partner.** No se le puede dar acceso hasta que esté en un
  partner; el admin lo dice en lugar de ofrecer el interruptor.
- **WhatsApp se desconecta con la Bandeja activa.** La Bandeja sigue dejando
  leer el historial y dice que el número está desconectado; no deja enviar.
- **Se quita la Bandeja con conversaciones esperando.** Las que el agente dejó
  de atender al pedir ayuda vuelven a él, y el hilo lo anota: sin Bandeja nadie
  las atendería.
- **Acceso desactivado con sesiones abiertas.** La siguiente acción de esas
  personas las lleva fuera, a la página de sin acceso.
- **Módulo quitado mientras alguien lo usa.** La siguiente navegación lo lleva
  a su primer módulo; el módulo desaparece de la barra.
- **Sin ningún módulo.** El admin no deja guardar un acceso activo sin módulos.
- **Una persona ya es de un partner.** No puede ser además usuario de un
  cliente con la misma cuenta; el admin lo dice al invitar.
- **Tope agotado.** El agente no responde (como hoy); la Bandeja lo dice en la
  conversación y el Panel lo pone arriba, con a quién acudir.
- **Saldo sin tope asignado.** Panel y Consumo no inventan un saldo: dicen que
  no hay tope asignado.
- **Datos que no se pueden leer.** Cada bloque que falla lo dice y el resto se
  pinta; nunca un cero donde no se sabe (constitución §V).
- **Agente con números.** No se puede archivar hasta que sus números pasen a
  otro agente; el último agente de un cliente no se archiva.
- **Número que cambia de agente.** Las conversaciones de ese número siguen su
  hilo y las atiende el agente nuevo desde el siguiente mensaje; el hilo lo
  anota.
- **Texto largo.** Nombres de contacto, de agente y de negocio de 40 caracteres
  o más se recortan sin romper la fila; los mensajes largos se ajustan.
- **Ausencia diseñada** (constitución §V). Sin Bandeja no hay tarjeta, ni fila,
  ni contador que hable de ella. Con un solo agente no hay filtro ni desglose
  por agente. Con un solo canal no hay pestañas de canal. Sin saldo comprable
  no hay botón de compra apagado.

## Requisitos *(obligatorio)*

### Requisito 1 — Acceso del cliente, desde el admin

**Historia de usuario:** Como operador de Auphere, quiero dar acceso a la
consola a un cliente y elegir sus módulos, para que el negocio vea lo suyo sin
pedírnoslo.

#### Criterios de aceptación

1. WHEN un operador activa el acceso de un cliente THEN el sistema DEBE exigir al
   menos un módulo de entre Panel, Bandeja de entrada y Consumo, y guardarlo para
   el cliente entero.
2. IF el cliente no pertenece a ningún partner THEN el sistema DEBE impedir
   activar su acceso y decir por qué.
3. IF el cliente no tiene un WhatsApp conectado THEN el sistema NO DEBE permitir
   elegir la Bandeja de entrada.
4. WHEN un operador invita a una persona de un cliente con acceso THEN el sistema
   DEBE enviarle un enlace de un solo uso que caduca, con el que crea su
   contraseña o entra con su cuenta de Google.
5. IF el correo invitado ya pertenece a una persona de un partner o de otro
   cliente THEN el sistema DEBE rechazar la invitación diciendo por qué.
6. WHEN un operador reenvía una invitación THEN el sistema DEBE invalidar el
   enlace anterior.
7. WHEN un operador revoca a una persona o desactiva el acceso del cliente THEN
   el sistema DEBE cerrar sus sesiones y negarle cualquier acción siguiente.
8. El sistema DEBE registrar en la auditoría cada cambio de acceso, de módulos y
   de personas con la identidad del operador que lo hizo.
9. El sistema DEBE enseñar en el admin, por cliente, el estado de cada persona:
   activa, invitación pendiente, invitación caducada o revocada.

### Requisito 2 — Identidad y alcance del usuario de cliente

**Historia de usuario:** Como negocio, quiero entrar y ver solo lo mío, para
confiar en que nadie más lo ve y en que yo no veo lo de otros.

#### Criterios de aceptación

1. El sistema DEBE atar cada usuario de cliente a un único cliente y tomar ese
   cliente de su acceso en el servidor; el cliente NO DEBE llegar nunca como
   argumento de una petición.
2. IF un usuario de cliente pide cualquier pantalla, acción o dato del partner
   THEN el sistema DEBE responder como si no existiera.
3. IF un usuario de cliente pide cualquier dato de otro cliente, aunque sea del
   mismo partner, THEN el sistema DEBE responder igual que si no existiera.
4. IF un usuario de cliente pide un módulo que su cliente no tiene THEN el
   sistema DEBE negarlo y la consola DEBE llevarlo a su primer módulo.
5. IF una persona del partner pide cualquier ruta de la Bandeja THEN el sistema
   DEBE negarlo; ninguna ruta alcanzable por el partner DEBE poder devolver el
   cuerpo de un mensaje.
6. WHEN un usuario de cliente entra THEN el sistema DEBE usar la misma página de
   acceso, la misma recuperación de contraseña y la misma duración de sesión que
   un partner.
7. WHILE el acceso del cliente está desactivado o la persona está revocada el
   sistema DEBE llevarla a la página de sin acceso.

### Requisito 3 — La consola lite

**Historia de usuario:** Como negocio, quiero una consola clara con lo mío,
para no perderme en lo que no uso.

#### Criterios de aceptación

1. El sistema DEBE enseñar al usuario de cliente una barra lateral con
   exactamente los módulos de su cliente, en el orden Panel, Bandeja de entrada,
   Consumo, con la marca y la insignia «lite».
2. El sistema DEBE enseñar al pie de la barra el nombre de la persona y el de su
   negocio.
3. El sistema NO DEBE enseñar al usuario de cliente ningún elemento del partner:
   Clientes, Auditoría, Guía, Teammate, Equipo, Facturación, API, el Companion
   ni la gestión de otros clientes.
4. WHEN el usuario de cliente entra o pide la raíz THEN el sistema DEBE llevarlo
   a su primer módulo.
5. WHERE el cliente tiene Bandeja EL sistema DEBE enseñar junto a «Bandeja de
   entrada» el número de conversaciones sin leer de esa persona.
6. El sistema DEBE respetar en la consola lite las mismas reglas de la consola:
   modo claro y oscuro, idioma español e inglés, foco visible y uso con teclado.

### Requisito 4 — Panel de un cliente

**Historia de usuario:** Como negocio, quiero ver de un vistazo cómo va mi
agente y si algo me necesita.

#### Criterios de aceptación

1. El sistema DEBE calcular cada cifra del Panel del cliente con la misma regla
   que la consola del partner aplica a ese cliente, en US$ y con el mismo
   redondeo.
2. El sistema DEBE enseñar el gasto del mes del cliente; WHERE el cliente tiene
   más de un agente EL sistema DEBE desglosarlo por agente.
3. El sistema DEBE enseñar las conversaciones de los últimos 7 días con su
   variación contra los 7 anteriores; IF no hay periodo anterior THEN DEBE
   decirlo en vez de inventar una variación.
4. El sistema DEBE enseñar el saldo del cliente (lo que le queda de su tope) y
   para cuántos días alcanza al ritmo de los últimos 7 días; IF no hubo gasto
   THEN NO DEBE inventar días.
5. WHERE el cliente tiene Bandeja EL sistema DEBE enseñar cuántas conversaciones
   esperan a una persona, con acceso directo a la primera.
6. WHEN el saldo no alcanza hasta fin de mes o está agotado THEN el sistema DEBE
   ponerlo en «Necesita tu atención» diciendo a quién pedir más saldo: el nombre
   de su partner, o Auphere si es cliente directo.
7. IF nada necesita atención THEN el sistema DEBE enseñar una sola línea que lo
   diga, sin bloques vacíos.
8. El sistema NO DEBE ofrecer en el Panel del cliente comprar saldo, cambiar el
   tope ni nada del saldo del partner.

### Requisito 5 — Consumo de un cliente

**Historia de usuario:** Como negocio, quiero saber cuánto gasto y para cuánto
me alcanza, para no quedarme sin agente.

#### Criterios de aceptación

1. El sistema DEBE enseñar el saldo del cliente, el gasto del mes con su
   proyección a fin de mes, y las conversaciones del mes con su gasto medio por
   conversación, con las mismas reglas de dinero que la consola del partner.
2. El sistema DEBE enseñar el gasto por día del cliente en 7, 30 o 90 días.
3. WHERE el cliente tiene más de un agente EL sistema DEBE enseñar una tabla de
   gasto por agente y un filtro por agente en el gasto por día.
4. El sistema DEBE ofrecer el detalle técnico del cliente plegado, y su
   exportación DEBE contener solo filas de ese cliente.
5. El sistema NO DEBE enseñar al usuario de cliente nuestro coste, el saldo del
   partner, el gasto fuera de clientes ni otro cliente.
6. El sistema NO DEBE ofrecer comprar saldo, cambiar ni mover topes, ni
   configurar alertas.

### Requisito 6 — Disponibilidad de la Bandeja

**Historia de usuario:** Como negocio con WhatsApp conectado, quiero una bandeja
donde leer y contestar a mis clientes.

#### Criterios de aceptación

1. El sistema DEBE ofrecer la Bandeja solo a usuarios de un cliente que tenga el
   módulo y un WhatsApp conectado.
2. IF el WhatsApp del cliente se desconecta THEN la Bandeja DEBE seguir dejando
   leer el historial, DEBE decir que el número está desconectado y NO DEBE
   dejar enviar.
3. WHERE el cliente tiene conectado más de un tipo de canal EL sistema DEBE
   ofrecer pestañas por tipo de canal con su número de no leídas; con un solo
   tipo NO DEBE haber pestañas.

### Requisito 7 — Lista de conversaciones

**Historia de usuario:** Como negocio, quiero ver qué conversaciones tengo y
cuáles me necesitan.

#### Criterios de aceptación

1. El sistema DEBE listar las conversaciones del cliente por última actividad,
   la más reciente primero, cargando más al llegar al final.
2. El sistema DEBE enseñar en cada fila el contacto, la hora del último mensaje,
   el último mensaje precedido de su autor (el nombre corto del agente, «Tú» o
   el nombre de otra persona del negocio), si está sin leer y su estado.
3. El sistema DEBE dejar filtrar por sin leer, por las que esperan a una persona
   (con su número) y por resueltas; por defecto NO DEBE enseñar las resueltas.
4. El sistema DEBE dejar buscar por nombre del contacto, por teléfono y por el
   texto de los mensajes.
5. WHEN llega un mensaje o cambia el estado de una conversación THEN la lista
   DEBE reflejarlo en segundos, sin recargar.
6. El sistema DEBE distinguir una bandeja sin conversaciones de una búsqueda o
   filtro sin resultados.

### Requisito 8 — El hilo

**Historia de usuario:** Como negocio, quiero leer la conversación entera y
entender quién dijo qué.

#### Criterios de aceptación

1. El sistema DEBE enseñar los mensajes en orden, con separadores de día, y
   distinguir los del contacto, los de cada agente con su nombre y los de cada
   persona con el suyo.
2. El sistema DEBE enseñar en el hilo, como notas, cada toma de control,
   devolución, resolución y reapertura, y como aviso cada vez
   que el agente pidió ayuda, con su motivo.
3. El sistema DEBE enseñar los archivos recibidos: las imágenes visibles, los
   documentos con su nombre, los audios con su transcripción cuando exista.
4. El sistema DEBE enseñar el estado de cada mensaje enviado por el negocio, y
   IF un envío falló THEN DEBE decir que no se envió y por qué.
5. WHEN una persona abre una conversación THEN el sistema DEBE marcarla como
   leída solo para esa persona.

### Requisito 9 — Tomar el control y devolverlo

**Historia de usuario:** Como negocio, quiero entrar en una conversación cuando
hace falta y devolvérsela al agente después.

#### Criterios de aceptación

1. WHILE el agente atiende una conversación el sistema NO DEBE dejar enviar a
   una persona y DEBE ofrecer «Tomar el control».
2. WHEN una persona toma el control THEN el agente NO DEBE responder en esa
   conversación hasta que se le devuelva, y la conversación DEBE quedar
   asignada a esa persona.
3. WHEN una persona devuelve la conversación THEN el agente de su número DEBE responder al
   siguiente mensaje del contacto sabiendo lo que hizo la persona mientras tanto,
   sin responder a lo que ya pasó.
4. IF dos personas actúan sobre la misma conversación y el estado cambió entre
   medias THEN el sistema DEBE rechazar la acción que llega tarde y enseñar el
   estado real.
5. El sistema DEBE registrar en la auditoría cada toma de control y cada
   devolución con la persona que la hizo.

### Requisito 10 — Enviar

**Historia de usuario:** Como negocio, quiero contestar por WhatsApp desde la
consola.

#### Criterios de aceptación

1. WHILE una persona tiene el control el sistema DEBE dejarle enviar texto; Enter
   envía y Mayúsculas+Enter salta de línea.
2. IF han pasado más de 24 horas desde el último mensaje del contacto THEN el
   sistema NO DEBE dejar enviar y DEBE decir que WhatsApp no deja escribir hasta
   que el contacto vuelva a hacerlo.
3. WHILE una persona tiene el control el sistema DEBE dejarle adjuntar imágenes
   y documentos de los tipos y tamaños permitidos, dentro de lo que WhatsApp
   admite, y IF el archivo no los cumple THEN DEBE rechazarlo antes de enviarlo
   diciendo el límite.
4. El sistema DEBE ofrecer las respuestas guardadas del negocio, que se crean,
   editan y borran desde la propia Bandeja; elegir una DEBE dejar su texto en el
   cuadro, sin enviarlo.
5. El sistema DEBE medir cada mensaje enviado desde la Bandeja como cualquier
   mensaje saliente del cliente.

### Requisito 11 — Lo que espera a una persona

**Historia de usuario:** Como negocio, quiero enterarme cuando el agente
necesita a alguien.

#### Criterios de aceptación

1. WHEN el agente pide ayuda en una conversación THEN el sistema DEBE marcarla
   como «espera a una persona» con el motivo que dio el agente.
2. WHERE el cliente tiene Bandeja EL agente NO DEBE responder en una
   conversación que espera a una persona; IF el cliente no tiene Bandeja THEN
   el agente DEBE seguir respondiendo como hoy.
3. WHILE una conversación espera a una persona el siguiente mensaje del contacto
   DEBE quedar en el mismo hilo, tenga el cliente Bandeja o no.
4. WHEN una conversación pasa a esperar a una persona THEN el sistema DEBE avisar
   a las personas del cliente en la campana y por correo, una vez por
   escalado.
5. WHEN una persona toma el control, la devuelve al agente o la resuelve THEN
   la conversación DEBE dejar de esperar a una persona.

### Requisito 12 — Resolver, reabrir y no leída

**Historia de usuario:** Como negocio, quiero cerrar lo atendido y volver a lo
pendiente.

#### Criterios de aceptación

1. WHEN una persona resuelve una conversación THEN el sistema DEBE sacarla de la
   lista por defecto y anotarlo en el hilo.
2. WHEN el contacto escribe en una conversación resuelta THEN el sistema DEBE
   reabrirla y DEBE responder el agente que la tenía.
3. WHEN una persona reabre una conversación THEN el agente que la tenía DEBE
   volver a responder.
4. WHEN una persona marca una conversación como no leída THEN DEBE contar como
   no leída solo para esa persona.

### Requisito 13 — El panel de contacto

**Historia de usuario:** Como negocio, quiero tener a mano lo que sé del
contacto.

#### Criterios de aceptación

1. WHERE el agente escribió un resumen del contacto al pedir ayuda EL sistema
   DEBE enseñar el último; IF no hay ninguno THEN NO DEBE haber sección de
   resumen.
2. El sistema DEBE enseñar quién atiende, el canal, el teléfono, la fecha del
   primer mensaje y cuántas conversaciones ha tenido el contacto con el negocio
   (la primera más cada vez que volvió a escribir tras una resuelta).
3. El sistema DEBE enseñar la actividad de la conversación, de la más reciente a
   la más antigua.
4. El sistema DEBE dejar poner y quitar etiquetas, y DEBE sugerir las que ya usa
   el negocio.
5. El sistema DEBE dejar escribir notas internas del contacto; una nota interna
   NO DEBE enviarse nunca al contacto NI llegar nunca al agente.

### Requisito 14 — Varios agentes por cliente

**Historia de usuario:** Como negocio con varias áreas, quiero un agente para
cada una, con su propio número, y verlos todos en una sola Bandeja.

#### Criterios de aceptación

1. El sistema DEBE admitir de 1 a N agentes por cliente, cada uno con su nombre,
   su prompt, sus herramientas y sus versiones.
2. El sistema DEBE asignar cada número de WhatsApp del cliente a exactamente un
   agente, y un agente DEBE poder tener uno o más números.
3. WHEN llega un mensaje a un número THEN el sistema DEBE hacerlo atender por el
   agente de ese número, con su prompt, su versión y sus herramientas.
4. El sistema DEBE dar a cada agente solo las herramientas de su propia lista
   blanca.
5. WHEN se añade un agente a un cliente THEN el sistema DEBE configurarlo con el
   mismo editor de hoy —plantilla, borrador, publicar— allí donde hoy se
   configura el agente, y cada pantalla que hoy edita «el agente» DEBE dejar
   elegir cuál.
6. WHEN un número pasa a otro agente THEN las conversaciones de ese número DEBEN
   conservar su hilo y atenderlas el agente nuevo desde el siguiente mensaje.
7. El sistema DEBE atribuir cada mensaje del agente y cada gasto al agente que
   lo produjo.
8. WHEN se despliega el multiagente THEN cada cliente existente DEBE quedar con
   un único agente dueño de todos sus números, y responder exactamente igual.
9. IF un agente tiene números asignados o es el último del cliente THEN el
   sistema NO DEBE dejar archivarlo.
10. Los agentes de un mismo cliente DEBEN compartir su conocimiento.

### Requisito 15 — Avisos del cliente

**Historia de usuario:** Como negocio, quiero que la campana me hable de lo mío.

#### Criterios de aceptación

1. El sistema DEBE enseñar al usuario de cliente solo avisos de su cliente:
   conversaciones que esperan a una persona y saldo agotado o en riesgo.
2. El sistema NO DEBE enseñar al usuario de cliente avisos del partner
   (facturación, equipo, saldo del partner, otros clientes).
3. El sistema NO DEBE enviar al partner los avisos de conversaciones que esperan
   a una persona del cliente con Bandeja.

### Requisito 16 — Lo que ve el partner

**Historia de usuario:** Como partner, quiero saber qué hacen mis clientes en su
consola sin leer sus conversaciones.

#### Criterios de aceptación

1. El sistema DEBE enseñar en la Auditoría del partner las acciones de los
   usuarios de sus clientes con el nombre de la persona y sin contenido de
   mensajes ni de notas.
2. El sistema NO DEBE dar al partner ninguna ruta que devuelva el cuerpo de un
   mensaje, una nota interna o un archivo de conversación.

### Requisito 17 — Aislamiento comprobado

**Historia de usuario:** Como Auphere, quiero que las fronteras nuevas se
prueben barriendo, no enumerando.

#### Criterios de aceptación

1. El sistema DEBE tener un test que recorra todas las rutas de la consola y
   compruebe que un usuario de cliente solo alcanza las de sus módulos.
2. El sistema DEBE tener un test que recorra todas las rutas de la consola y
   compruebe que solo las de la Bandeja pueden devolver cuerpos de mensaje, y
   que una persona del partner no alcanza ninguna de ellas.
3. El sistema DEBE tener un test que, con dos clientes del mismo partner,
   compruebe que ninguna ruta alcanzable por el usuario de uno devuelve datos
   del otro.
4. El sistema DEBE tener un test que compruebe que un turno atendido por un
   agente solo recibe las herramientas, el prompt y la versión de ese agente,
   nunca los de otro agente del mismo cliente.

### Entidades clave

- **Acceso de cliente**: si el cliente tiene consola lite y qué módulos. Uno por
  cliente; pertenece al cliente y lo alcanza la RLS por su cliente.
- **Usuario de cliente**: una persona con cuenta de consola atada a un único
  cliente de un partner. Pertenece al partner y al cliente; sus lecturas se
  filtran por el cliente de su acceso.
- **Invitación de cliente**: enlace de un solo uso, con caducidad, para un
  correo y un cliente.
- **Agente**: cada agente de un cliente, con nombre y estado. Sus versiones son
  las que hoy tiene el cliente. Pertenece al cliente.
- **Número del agente**: a qué agente pertenece cada número de WhatsApp del
  cliente. Uno por número. Pertenece al cliente.
- **Atención de la conversación**: si la atiende el agente de su número o una
  persona, y cuál. Pertenece al cliente.
- **Estado de lectura**: hasta dónde ha leído cada persona cada conversación.
  Pertenece al cliente.
- **Etiqueta**: palabra que el negocio pone a una conversación. Pertenece al
  cliente.
- **Nota interna**: texto del equipo sobre un contacto, que nunca sale ni llega
  al agente. Pertenece al cliente.
- **Respuesta guardada**: título y texto reutilizable del negocio. Pertenece al
  cliente.
- **Evento de conversación**: cada cosa que le pasó a la conversación (pidió
  ayuda, control tomado, devuelta, resuelta, reabierta), con quién.
  Pertenece al cliente.

## Criterios de éxito *(obligatorio)*

- **CE-001**: Un operador da acceso a un cliente e invita a una persona, y esa
  persona está dentro de su consola en menos de 5 minutos desde que abre el
  correo.
- **CE-002**: Los tres barridos de aislamiento (rutas del usuario de cliente,
  cuerpos de mensaje, cliente contra cliente del mismo partner) pasan con cero
  excepciones no escritas.
- **CE-003**: Cada cifra del Panel y del Consumo de un cliente coincide al
  céntimo con la que ve su partner para ese cliente.
- **CE-004**: Un mensaje de un contacto aparece en la Bandeja abierta en menos
  de 5 segundos sin recargar.
- **CE-005**: Desde el aviso de «espera a una persona» hasta poder escribir la
  primera respuesta hay como mucho 3 clics.
- **CE-006**: Tras el despliegue del multiagente, los clientes existentes
  responden igual: su batería de evaluación da el mismo resultado que antes.
- **CE-007**: La primera página de la Bandeja carga en menos de 1,5 s con 5.000
  conversaciones en el cliente.
- **CE-008**: Ninguna pantalla de la consola lite tiene incidencias graves o
  críticas de accesibilidad, ni desborda en horizontal a 360 px.

## Fuera de alcance

- **Comprar saldo** — el saldo es de solo lectura; C2 sigue en pie.
- **Alertas de consumo del cliente** — el diseño las trae, pero lo único nuevo
  de esta spec es la Bandeja; el cliente ve su saldo y el aviso del Panel.
- **Enviar plantillas fuera de la ventana de 24 horas** — la Bandeja dice que
  no se puede; las plantillas siguen en la consola del partner.
- **Instagram, Messenger, YCloud y TikTok** — solo se usa WhatsApp por Meta.
- **Marca blanca** (C4) — la consola lite sale con marca Auphere.
- **Bandeja para el partner** — C8: el partner sigue sin cuerpos de mensaje.
- **Que el cliente invite o gestione a sus personas** — en esta versión lo hace
  Auphere desde el admin.
- **Módulos por usuario** — se eligen por cliente.
- **Que el cliente edite sus agentes** — el cliente los usa y transfiere entre
  ellos; configurarlos no es suyo.
- **Conocimiento por agente** — los agentes de un cliente comparten el
  conocimiento.
- **Asignar una conversación a otra persona del negocio** — se toma el control
  para uno mismo.
- **Traspaso entre agentes y enrutado por intención** — un número es de un solo
  agente; la Bandeja junta números, no los reparte.
- **«Visto por» y escribiendo…** — el estado de lectura es de cada persona y no
  se enseña a las demás.

## Supuestos

- **Se trabaja en desarrollo** como en las specs anteriores: rama, consola local
  con datos sembrados y staging; a producción cuando el owner promueve.
- **El doble descuento del tope se arregla antes** de abrir Consumo y el saldo a
  un cliente real, por el flujo de bug (`/speckit-bug-assess`). Sin eso, el
  cliente vería su saldo bajar el doble de rápido.
- Una cuenta de consola es de un partner o de un cliente, nunca de los dos.
- Los usuarios de un cliente tienen todos los mismos permisos: los módulos de
  su cliente.
- El resumen del contacto es el que el agente ya escribe al pedir ayuda; esta
  spec no añade llamadas al modelo para resumir.
- Las respuestas guardadas, etiquetas y notas son del cliente, compartidas por
  todas sus personas.
- **El modelo es del cliente, no del agente**: el que elige el partner en la
  ficha del cliente aplica a todos sus agentes. Elegir modelo por agente queda
  para otra spec.
- El idioma de la consola lite sigue las reglas de la consola (español por
  defecto, inglés disponible) y el vocabulario de dinero de las specs 027 y 028.
