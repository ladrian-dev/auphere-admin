# Especificación: Las quejas de los partners del 2026-11-18

**Rama**: `063-quejas-partners-2026-11-18` · **Creada**: 2026-11-18 · **Estado**: Borrador, pendiente de la revisión de Luis

**Entrada**: descripción del usuario: "Quejas de partners en prod del 2026-11-18. Cuatro fallos reproducidos: (1) el agente contesta en español aunque el cliente final escriba en otro idioma. Decisión de Luis: por defecto contesta en el idioma del cliente, salvo que el partner limite los idiomas del agente. (2) «No se pudo escribir el borrador»: el modelo del constructor devolvió un JSON ilegible dos veces seguidas. (3) «Desde una plantilla» da 500 cuando un texto coincide con el nombre de otro cliente del mismo partner. (4) Tras conectar WhatsApp desde Cliente → Canales no encuentran la configuración del número. El número nace «Sin configurar», así que no responde a nadie. La solución tiene que ser definitiva, pero no extravagante."

## Encabezado Auphere *(obligatorio)*

| Campo | Valor |
|---|---|
| **Superficie de confianza** | `0`: la API de la consola, el runtime del agente y el constructor, que ya existen. No se abre ninguna superficie. |
| **Garantías de aislamiento tocadas** | **5 (prompt aislado), rozada por el requisito 4.** La comprobación de que un borrador no nombra a otro cliente es la guarda de la garantía 5 en el constructor (047, 15.4). Esta spec cambia qué cuenta como «de otro cliente»: ya no cuenta lo que el propio cliente le dio al constructor. Lo que el constructor escriba por su cuenta y nombre a otro cliente se sigue quitando, y una prueba de aislamiento lo fija (requisito 4.5). Los requisitos 1, 2 y 3 no tocan ninguna: no mueven datos entre clientes ni entre contactos. |
| **Nota de KB que la justifica** | `[[bugs/2026-11-18-quejas-partners-prod]]` en `/Users/lmatos/Work/Auphere/nexus/` |
| **Qué se mide** | **Nada nuevo.** El constructor hace las mismas llamadas al modelo: pedir la salida en JSON no añade llamadas ni reintentos, y en la prueba gastó lo mismo (5385 tokens frente a 5642 y 5807). La regla del idioma añade unas sesenta palabras a cada turno. Todo sigue midiéndose donde ya se mide: la conversación en la bolsa del cliente y el constructor en «Construcción y pruebas». |

### Lo que enmienda

| Dónde | Qué decía | Qué dice ahora |
|---|---|---|
| Spec 047, **16.1** (el AgentSpec: «tono, idiomas, registro y saludo») y la política de operación de la consola | Los idiomas marcados son los que habla el agente. La política del turno manda contestar en el principal y solo permite el principal, salvo que se haya tocado una página de ajustes que la consola v2 ya no enlaza. | El agente contesta en el idioma del cliente. El partner puede **limitar** los idiomas, y por defecto no están limitados. El primero marcado es el principal, y se usa cuando no se sabe el idioma (requisito 1). |
| Spec 047, **15.4** (validador: «que el texto no lleve datos de otro cliente») | Cualquier texto del borrador que contenga el nombre de otro cliente del partner tumba el borrador. Eso incluye la descripción que escribió el propio partner y la guía del sector. | No es de otro cliente lo que este cliente dio al constructor. Lo que el constructor escribe por su cuenta y nombra a otro cliente se quita de ese trozo, y el resto del borrador sigue (requisito 4). |
| Spec 047, **15.8** («Desde una plantilla» y «En blanco» cuando el constructor no responde) | No dice qué pasa si la alternativa también falla. Hoy devuelve un error 500 sin nombre. | La alternativa nunca acaba en un error sin nombre (requisito 4.4). |
| Spec 047, **30.6** («WHEN termina la conexión THEN … abrir la configuración del canal») | Se cumple al conectar desde el agente, pero no al conectar desde la página Canales del cliente. | Se cumple venga de donde venga la conexión (requisito 2.1). |
| Spec 047, **26.1** (al abrir la tarjeta de un agente «Listo · sin canal», «a Canales») | Se implementó como la página Canales **del cliente**. | Lleva a la pestaña Canales **del agente** (requisito 2.7). |
| Spec 047, **25** (estados del agente) | Un agente publicado cuyos números no responden a nadie se ve «Listo · sin canal», aunque tenga un número sin configurar. | Dice que tiene un número sin configurar (requisito 2.6). |
| Spec 047, **32.9** (un número sin número de prueba queda «Sin configurar») | Lo que hay que decidir solo se ve en la página del canal, y desde Canales del cliente no hay forma de llegar a ella. | Un número «Sin configurar» dice en cualquier lista que no responde a nadie, y lleva a decidirlo (requisito 2.3). |

## Por qué

El 2026-11-18 un partner en producción mandó tres quejas. Las tres parecían diferencias entre staging y prod. No lo eran: `main` contiene todo `develop`, y la consola de prod está en el último commit de `main`. Al investigarlas apareció un cuarto fallo en el mismo flujo. Los cuatro están reproducidos:

1. **«El agente traduce bien, pero no responde en el idioma de la pregunta sino en español».** Cada turno de un agente publicado lleva una política que dice «contesta en es; permitido: es; si no, usa el principal». Marcar inglés en el constructor no cambia esa línea. En staging, a una pregunta en inglés, el agente contestó en español **4 de 4 veces**, tal como está publicado y también con el inglés marcado.
   - **Con la regla nueva, al final del turno, acertó 10 de 10 veces** con las respuestas esperadas: inglés al inglés, español al francés con el límite y español al español. Acertó también en los casos difíciles: después de una conversación en español, y con un prompt que dice «Never answer in English».
   - **La misma regla dentro del bloque de política** perdía ante esa prohibición (0 de 2). Por eso va al final.
2. **«Sale un aviso al generar el borrador».** El constructor llamó al modelo dos veces, a las 15:20 y a las 15:25 UTC, y las dos veces el modelo devolvió un JSON que no se pudo leer. El partner lo resolvió empezando desde una plantilla, que no usa el modelo. No era el saldo: el constructor nunca cobra de la bolsa del cliente. Al repetir la llamada con la entrada real, salió bien **3 de 3 veces**, una de ellas pidiendo la salida en JSON. El fallo es intermitente, y nada de lo que queda guardado dice qué parte venía rota.
3. **«Desde una plantilla» devolvió 500 tres veces seguidas** en otro cliente, el mismo día. El constructor comprueba que un borrador no nombre a otros clientes del mismo partner. La comprobación también mira lo que escribió el propio partner y la guía del sector. Si otro cliente se llama como una palabra corriente («Peluquería»), cualquier borrador que la use queda inválido. Por la vía de plantilla, ese error no tiene nombre y sale como 500. Reproducido en local.
4. **«En prod no vemos la configuración del canal».** Se recorrió la misma ruta en los dos entornos (Cliente → Agentes → el agente), en el Chrome de Luis y solo mirando. La página del agente es igual en los dos. Lo que cambia es **a dónde lleva la tarjeta**, que depende del estado del agente:
   - **Ava (staging)** atiende, así que su tarjeta abre la página del agente (`/clients/{ref}/agents/{id}`) en Rendimiento.
   - **Ana (prod)** está «Listo · sin canal», así que su tarjeta abre **la página Canales del cliente** (`/clients/{ref}/channels`) y no la pestaña Canales de Ana. Es lo que se ve en la captura del partner.

   Eso cierra un bucle:
   1. El partner conectó el número en esa página.
   2. El número quedó sin agente asignado y «Sin configurar» (047, 32.9), que significa que **no responde a nadie**.
   3. Ana sigue «Listo · sin canal», así que cada vez que la pulsa vuelve a la misma página, que no tiene la configuración del número.

   Además:
   - La tarjeta del número en esa página solo deja elegir el agente, y dice «Activo».
   - La tarjeta de Ana dice «Sin canal», aunque el número sale en su pestaña Canales cuando se llega a ella por la URL. En staging, la de Ava dice «No channel» por la misma causa.

## Clarifications

### Session 2026-11-18

Las tres primeras las respondió Luis antes de escribir la spec. Las dos últimas
las decidí con criterio, siguiendo su forma de trabajar (avanzar y revisar al
final), y quedan para que las revise.

- Q: Cuando un cliente final escribe en otro idioma, ¿qué hace el agente por defecto? → A: Contesta en el idioma del cliente, salvo que el partner limite los idiomas del agente. Los agentes existentes quedan sin límite (Luis).
- Q: ¿La solución es para el cliente que se quejó o para todos? → A: Para todos: cualquier agente puede tener el fallo (Luis).
- Q: ¿Se puede leer prod de ese cliente y repetir el borrador con el modelo real? → A: Sí, solo lectura y solo de `estetica-spa-demo` (Luis).
- Q: Cuando el saneado quita un trozo por nombrar a otro cliente, ¿dónde queda constancia? → A: En el registro de usos del constructor (047, 15.9), con el motivo y el sitio y sin el nombre. La consola no lo enseña, porque mostrarle a la persona de un cliente el nombre de otro sería la fuga que la guarda evita (decidido, para revisión).
- Q: ¿Puede el constructor activar el límite de idiomas? → A: No, solo una persona, igual que el aviso de IA (047, 16.6). Si no, una descripción que diga «atiende en español» volvería a limitar el agente sin que nadie lo decidiera (decidido, para revisión).

## Escenarios de usuario y pruebas *(obligatorio)*

### Historia 1 — El agente contesta en el idioma del cliente (Prioridad: P1)

Un cliente final escribe en inglés al WhatsApp de un spa de Madrid y el agente le contesta en inglés. Si al rato escribe en español, el agente pasa al español. Nadie tuvo que marcar nada. Si el negocio prefiere atender solo en español y en inglés, lo limita en «Cómo habla». A partir de ahí, un mensaje en francés recibe la respuesta en español, que es su idioma principal.

**Por qué esta prioridad**: afecta a todos los agentes publicados, en prod y en staging, y es lo que el cliente final ve en cada respuesta.

**Prueba independiente**: un agente publicado sin tocar nada recibe una pregunta en inglés y contesta en inglés. Se limita a español e inglés y recibe una en francés: contesta en español.

**Escenarios de aceptación**:

1. **Dado** un agente publicado sin idiomas limitados, **cuando** el cliente final escribe en inglés, **entonces** contesta en inglés.
2. **Dado** ese agente, **cuando** el cliente cambia de idioma a mitad de la conversación, **entonces** contesta en el idioma del último mensaje.
3. **Dado** un agente limitado a español e inglés, **cuando** el cliente escribe en francés, **entonces** contesta en español, su idioma principal.
4. **Dado** un agente cualquiera, **cuando** el mensaje no deja saber el idioma (un emoji, «ok», un número), **entonces** contesta en el idioma en que iba la conversación, y al empezar, en el principal.
5. **Dado** un agente publicado antes de esta spec, sea del constructor, de una plantilla o de un prompt antiguo, **cuando** se despliega el cambio, **entonces** contesta en el idioma del cliente sin que nadie lo vuelva a publicar.
6. **Dado** el probador de la consola, **cuando** se le escribe en inglés, **entonces** contesta igual que el agente en el canal.

---

### Historia 2 — Encontrar y decidir la configuración de un número (Prioridad: P1)

Una persona crea su primer agente y lo abre desde Agentes. Como todavía no tiene un número que responda, la consola lo abre en **su** pestaña Canales, y no en la página Canales del cliente. Conecta allí el número, y el número queda con ese agente. Si lo conecta desde la página Canales del cliente, al terminar la consola la lleva igualmente a la configuración de ese número, como si lo hubiera conectado desde el agente. Si el número quedó «Sin configurar», la página se lo dice: el número no responde a nadie hasta que decida a quién responde. Si cierra la página y vuelve otro día a Canales del cliente, cada número tiene su «Configurar». El que está sin configurar dice «No responde a nadie».

**Por qué esta prioridad**: hoy un número conectado así no atiende a nadie, y el partner no tiene forma de descubrirlo ni de arreglarlo desde donde está.

**Prueba independiente**: conectar un número desde Canales del cliente sin número de prueba. Al terminar se abre su configuración con la barra de «Sin configurar». De vuelta en Canales del cliente, su tarjeta dice que no responde a nadie y su «Configurar» lleva a la misma página.

**Escenarios de aceptación**:

1. **Dado** un agente «Listo · sin canal», **cuando** se pulsa su tarjeta en Agentes, **entonces** se abre la página del agente en su pestaña Canales.
2. **Dado** un cliente con agente por defecto, **cuando** se conecta un número desde Canales del cliente, **entonces** al terminar se abre la configuración de ese número dentro del agente que lo atiende.
3. **Dado** un número en la lista de Canales del cliente, **cuando** la persona pulsa «Configurar», **entonces** llega a esa misma configuración.
4. **Dado** un número «Sin configurar», **cuando** aparece en Canales del cliente o en Canales del agente, **entonces** dice que no responde a nadie, y lleva a decidirlo.
5. **Dado** un cliente sin ningún agente, **cuando** conecta un número, **entonces** la consola dice que el número necesita un agente que lo atienda y lleva a crearlo, sin enseñar una configuración que no puede existir.
6. **Dado** un agente publicado cuyo único número está «Sin configurar», **cuando** se abre su página o la lista de agentes, **entonces** su estado dice que tiene un número sin configurar, no «sin canal».

---

### Historia 3 — El constructor no pierde el borrador por un JSON mal formado (Prioridad: P2)

Una persona describe su agente y pulsa «Generar borrador». El borrador llega, aunque el modelo tienda a equivocarse en el formato de vez en cuando. Si aun así falla, el mensaje dice que puede intentarlo de nuevo o empezar desde una plantilla, como hoy. El equipo de Auphere encuentra en los registros por qué falló, sin leer lo que escribió el modelo.

**Por qué esta prioridad**: el partner tiene una salida, que es la plantilla, pero pierde el borrador escrito a su medida y paga la espera.

**Prueba independiente**: con un modelo de prueba que devuelve JSON mal formado, el borrador falla con un motivo clasificado en los registros. Con el modelo real, la llamada pide la salida en JSON.

**Escenarios de aceptación**:

1. **Dado** un modelo que admite salida JSON garantizada, **cuando** el constructor le pide el borrador, **entonces** la pide así.
2. **Dado** una salida que no se puede leer, **cuando** el borrador falla, **entonces** el registro dice el tipo de error, la posición, cómo terminó el modelo y cuántos tokens escribió, sin una sola palabra de lo escrito.
3. **Dado** una salida que el modelo cortó por longitud, **cuando** el borrador falla, **entonces** el motivo es «cortado» y no «JSON ilegible».

---

### Historia 4 — Ni el constructor ni la plantilla se caen por un nombre (Prioridad: P2)

Un partner tiene un cliente que se llama «Peluquería» y otro que se llama «Salón Rita». Al crear un agente para Salón Rita desde la plantilla de peluquería, el borrador sale, aunque el texto diga «peluquería». Si el constructor escribe por su cuenta el nombre de otro cliente del partner, ese trozo se quita y el resto del borrador llega. Y si algo impide de verdad crear el borrador, la consola lo dice con nombre y ofrece las alternativas, nunca un error sin explicación.

**Por qué esta prioridad**: rompe la alternativa que la 047 da cuando el constructor no responde, y le pasó al propio Luis en producción el día de las quejas.

**Prueba independiente**: los cuatro casos del research (mismo nombre, palabra corriente, un nombre dentro de otro y nombres ajenos) dan borrador. Un borrador del constructor que nombra a otro cliente, sin que ese nombre esté en lo que recibió, sale sin ese trozo.

**Escenarios de aceptación**:

1. **Dado** un partner con un cliente llamado como una palabra corriente, **cuando** otro de sus clientes crea un agente desde una plantilla cuyo texto la usa, **entonces** el borrador se crea.
2. **Dado** una descripción escrita por el partner que nombra a otro de sus clientes, **cuando** se genera el borrador, **entonces** se crea.
3. **Dado** un borrador del constructor que nombra a otro cliente del partner, sin que ese nombre esté en lo que recibió, **cuando** se sanea, **entonces** ese trozo se quita, el resto llega y el registro de usos lo anota sin el nombre.
4. **Dado** un borrador que no se puede sanear, **cuando** se pide desde una plantilla, **entonces** la consola enseña el motivo con nombre y las alternativas, y no un error 500.

---

### Casos límite

- **Idioma que el modelo no distingue bien** (dialectos, mezcla de dos idiomas en un
  mensaje). Contesta en el idioma que domine el mensaje. Si no se sabe, en el de la
  conversación.
- **Idioma limitado y el cliente insiste en otro.** Contesta en el principal, en cada
  mensaje. Esta spec no le pide explicar en qué idiomas atiende el negocio.
- **Textos que la plataforma envía sin el modelo**, como el mensaje de espera del
  número. Siguen como los escribió el negocio, en su idioma. Ver Fuera de alcance.
- **Un agente cuyo prompt fija el idioma** («Hablas en es», o incluso «Never answer in
  English», como la plantilla `inventario_v1`). La regla del turno manda sobre esa
  línea porque va la última y lo dice. En staging hay una versión activa con esa
  prohibición, y la prueba con ella dio 4 de 4.
- **La reescritura de una respuesta.** Cuando el evaluador de respuestas pide
  rehacerla, la respuesta nueva conserva el idioma de la que se rehace.
- **Un agente con idiomas guardados en la página de ajustes antigua**, que la consola
  v2 ya no enlaza. Esa lista no limita nada: lo que limita es lo que se decide en
  «Cómo habla» (requisito 1.6).
- **El número de un cliente con varios agentes.** Un número conectado desde la página
  del cliente lo atiende el agente por defecto (047, 26.3). Su configuración se abre
  dentro de ese agente, el mismo que lo enseña en su pestaña Canales.
- **Un constructor sin salida JSON garantizada** (otro proveedor, otro modelo). Se lee
  como hoy, y si falla, el registro dice por qué (requisito 3.2).
- **Una persona reintenta el borrador.** Cada intento es una llamada que se paga, en
  «Construcción y pruebas» del partner, nunca en la bolsa del cliente. No hay
  reintentos automáticos.
- **Qué ve el partner cuando no puede limitar idiomas** (por ejemplo, en la consola
  lite). Nada nuevo: el agente contesta en el idioma del cliente.

## Requisitos *(obligatorio)*

### Requisito 1 — El agente contesta en el idioma del cliente

**Historia de usuario:** Como cliente final, quiero que el agente me conteste en el idioma en que le escribo, para entenderle sin pedírselo.

#### Criterios de aceptación

1. WHEN un cliente final escribe a un agente cuyos idiomas no están limitados THEN el sistema DEBE hacer que el agente conteste en el idioma de ese mensaje.
2. WHERE el partner limitó los idiomas del agente, IF el cliente escribe en uno de ellos THEN el agente DEBE contestar en ese idioma; IF escribe en otro THEN el agente DEBE contestar en el idioma principal.
3. IF el mensaje no deja saber el idioma THEN el agente DEBE contestar en el idioma en que iba la conversación, y en el primer mensaje, en el principal.
4. El sistema DEBE aplicar esta regla en cada turno de todos los agentes que atiende, y también en el probador de la consola. Da igual el origen del agente: el constructor, una plantilla o un prompt anterior a la 047. Y DEBE hacerlo sin que haga falta volver a publicarlos.
5. La regla del idioma DEBE prevalecer sobre cualquier otra instrucción de idioma del prompt del agente, incluidas las que prohíben un idioma. WHEN el evaluador de respuestas pide reescribir una respuesta THEN la reescritura DEBE conservar el idioma de la respuesta original.
6. Los idiomas del agente DEBEN decidirse en un solo sitio, «Cómo habla» del agente. El principal es el primero marcado. El partner DEBE poder limitar el agente a los idiomas marcados, y por defecto NO DEBE estar limitado. Ningún otro ajuste DEBE contradecirlo.
7. WHEN se despliegue este cambio THEN los agentes existentes DEBEN quedar sin límite de idiomas, con su principal de siempre (decisión de Luis, 2026-11-18).
8. El sistema DEBE decir en «Cómo habla», en una línea, qué hace el agente con los idiomas: «Contesta en el idioma del cliente. Si no lo sabe, en {principal}.» o «Solo en: {lista}. Si le escriben en otro, en {principal}.»
9. El constructor NO DEBE activar el límite de idiomas, ni al escribir el borrador ni al proponer un cambio. Solo una persona DEBE poder activarlo o quitarlo.

### Requisito 2 — Encontrar y decidir la configuración de un número

**Historia de usuario:** Como persona del partner o del cliente, quiero llegar a la configuración de un número desde donde lo conecté, para decidir a quién responde sin buscarla.

#### Criterios de aceptación

1. WHEN termina la conexión de un número desde la página Canales del cliente THEN el sistema DEBE abrir la configuración de ese número dentro del agente que lo atiende, igual que al conectarlo desde el agente (047, 30.6).
2. La página Canales del cliente DEBE ofrecer, en cada número, el acceso a su configuración. DEBE llevar a la misma página que «Configuración» en Canales del agente.
3. WHERE un número esté «Sin configurar», el sistema DEBE decir en la página Canales del cliente y en Canales del agente que **no responde a nadie**. Su acción principal DEBE llevar a decidir a quién responde.
4. El agente que enseña un número en su pestaña Canales y en su tarjeta, el que lo cuenta en su estado y el agente en cuya configuración se abre ese número DEBEN ser siempre el mismo: el asignado o, si no hay, el que atiende los números sin asignar.
5. IF el cliente no tiene ningún agente THEN el sistema DEBE decir que el número necesita un agente que lo atienda y llevar a crearlo, y NO DEBE ofrecer una configuración que no puede abrirse.
6. WHERE un agente publicado tenga números, pero ninguno que responda a nadie porque todos están «Sin configurar», el sistema DEBE decir en su estado que tiene un número sin configurar, y NO DEBE decir «sin canal».
7. WHEN una persona sigue un enlace a «los canales» que nace en un agente THEN el sistema DEBE abrir la pestaña Canales de ese agente, y NO DEBE llevar a la página Canales del cliente. Esos enlaces son: su tarjeta en Agentes cuando espera un número, «Guardar y conectar un canal» y el arreglo «canal» de la revisión y de las pruebas.

### Requisito 3 — El borrador del constructor no se pierde por el formato

**Historia de usuario:** Como persona que crea un agente, quiero que «Generar borrador» llegue a buen puerto, para no tener que empezar desde una plantilla genérica.

#### Criterios de aceptación

1. WHERE el modelo del constructor admita salida JSON garantizada, el sistema DEBE pedirla en cada llamada del borrador.
2. IF la salida del modelo no se puede leer THEN el sistema DEBE registrar el tipo de error, su posición, cómo terminó el modelo y los tokens escritos. NO DEBE registrar nada de lo escrito, ni de la descripción ni de la ficha.
3. IF el modelo cortó la salida por longitud THEN el motivo del fallo DEBE ser «cortado», distinto de «JSON ilegible».
4. El sistema NO DEBE reintentar solo una llamada del borrador que falló: cada intento se paga. La consola DEBE seguir ofreciendo «Intentar de nuevo», «Desde una plantilla» y «En blanco» sin perder lo escrito (047, 15.8).
5. El gasto de un borrador fallido DEBE seguir en «Construcción y pruebas» del partner, y NO DEBE salir de la bolsa del cliente (047, 15.7).

### Requisito 4 — Ni el constructor ni la plantilla se caen por un nombre

**Historia de usuario:** Como persona que crea un agente, quiero que el borrador salga aunque su texto coincida con el nombre de otro cliente de mi partner, para no quedarme sin agente por una casualidad.

#### Criterios de aceptación

1. WHEN se crea un borrador, con el constructor o desde una plantilla, THEN la comprobación de nombres de otros clientes NO DEBE contar lo que este cliente dio al constructor: el nombre del agente, la descripción, la ficha del negocio y la guía o plantilla usada. Un nombre que aparezca ahí no es de otro cliente.
2. IF el texto que escribió el constructor nombra a otro cliente del partner, y ese nombre no está en lo que recibió, THEN el sistema DEBE quitar ese trozo del borrador (la instrucción, el procedimiento o la regla en que aparece) y dejar el resto. DEBE anotarlo en el registro de usos del constructor (047, 15.9) con el motivo y el sitio, sin el nombre. La consola NO DEBE enseñar el nombre quitado.
3. IF después de quitar lo que falla el borrador sigue sin ser válido THEN el sistema DEBE fallar con un motivo con nombre.
4. WHEN falla un borrador pedido desde una plantilla THEN la consola DEBE enseñar el motivo con nombre y las alternativas, y el sistema NO DEBE responder con un error sin nombre.
5. Una prueba de aislamiento DEBE fijar que un borrador del constructor que nombra a otro cliente del partner, sin haberlo recibido, nunca llega con ese nombre (garantía 5).

### Entidades clave

No hay entidades nuevas. Se tocan estas:

- **Versión del agente**: sus idiomas (el principal y si están limitados) dentro de
  «Cómo habla». Pertenece al tenant del cliente, y la RLS la alcanza por `tenant_id`.
- **Canal**: solo se lee, para saber si está «Sin configurar» y qué agente lo atiende.
  Pertenece al tenant del cliente.
- **Trabajo del borrador**: el motivo de su fallo. Pertenece al tenant del cliente.

## Criterios de éxito *(obligatorio)*

- **CE-001**: En staging, con la batería de la reproducción:
  - un agente sin idiomas limitados contesta en inglés a una pregunta en inglés **4 de 4 veces**, también después de una conversación en español y con un prompt que dice «Never answer in English»;
  - uno limitado a español e inglés que recibe francés contesta en español **4 de 4 veces**.

  Hoy: 0 de 4 en inglés.
- **CE-002**: Los agentes publicados antes del despliegue cumplen CE-001 sin que nadie los vuelva a publicar.
- **CE-003**: Quien abre desde Agentes un agente sin número que responda llega a la pestaña Canales **de ese agente** en **1** clic; hoy llega a la página del cliente. Quien conecta un número desde Canales del cliente llega a su configuración en **0 pasos** más (se abre sola), y desde la lista en **1**. Hoy no hay camino.
- **CE-004**: En las dos semanas siguientes al despliegue en producción, **ningún** borrador falla por «JSON ilegible». Cualquier fallo del constructor tiene un motivo clasificado en los registros.
- **CE-005**: **Cero** respuestas 500 de «Desde una plantilla». Los cuatro casos de nombres del research dan borrador.

## Fuera de alcance

- **Traducir los textos que la plataforma envía sin el modelo**, como el mensaje de espera del número. Los escribe el negocio y salen tal cual. Traducirlos sería otra función.
- **La respuesta fija del evaluador de respuestas cuando agota sus reintentos**, que es un texto en español escrito por la plataforma. Solo la usan los agentes que tienen el evaluador encendido, que por defecto está apagado, y es otro texto fijo más.
- **Reintentar solo el borrador.** Cada intento cuesta una generación entera (047 ya lo decidió).
- **Cambiar a qué agente va un número conectado desde la página del cliente.** Lo atiende el agente por defecto (047, 26.3), y eso no cambia.
- **Retirar la página de ajustes antigua del agente**, que la consola v2 no enlaza. Deja de mandar en los idiomas (1.6), pero quitarla es limpieza aparte.
- **El idioma que detecta el clasificador de intención.** Hoy nadie lo usa, y la regla del turno no lo necesita.
- **Decidir a quién responde el número del partner que se quejó.** Es una decisión del negocio. Luis se lo indica al partner y esta spec no lo cambia por él.

## Supuestos

- El modelo de respuesta distingue el idioma del mensaje sin ayuda: lo hizo en 4 de 4 casos en staging con una sola línea de instrucción.
- El modelo del constructor admite salida JSON garantizada. Lo comprobó una llamada con la entrada real (`finish=stop`, JSON válido, mismo coste).
- El fallo de JSON del 2026-11-18 no se pudo repetir: 0 de 3 con la entrada real. Esta spec no promete conocer su causa exacta. Promete que la salida JSON garantizada la evite, y que el próximo fallo, si llega, diga por qué.
- Un nombre de otro cliente que aparece en lo que el propio cliente dio al constructor no es una fuga: el constructor solo recibe datos de este cliente y guías de Auphere.
