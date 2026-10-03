# Especificación: el alta deja de pesar

**Rama**: `019-alta-deja-pesar` · **Creada**: 2026-09-28 · **Estado**: Borrador

**Entrada**: el owner recorre el alta de un cliente el 2026-09-28 y pide que
crear uno sea «óptimo, simple e intuitivo», que no se vea «tan pesado de
solicitud y campos para rellenar», y que el Companion pueda ayudar a armarlo.

## Encabezado Auphere *(obligatorio)*

| Campo | Valor |
|---|---|
| **Superficie de confianza** | `0` — API de la consola. No se abre ninguna nueva. |
| **Garantías de aislamiento tocadas** | Ninguna nueva. El alta ya crea el tenant dentro del partner del llamante y el `tenant_id` no viaja en la petición; esta spec no toca esa ruta. **Sí roza la capa 2 del Companion** (lista blanca de solo lectura) y la spec la declara intacta: R5 prohíbe expresamente darle escritura. |
| **Nota de KB que la justifica** | `[[INFORME-AUDITORIA-CONSOLA-2026-09-22]]` (tabla E2E, fila a: «el wizard encadena publicar y activar sin estado visible») y la auditoría del alta del 2026-09-28, que se anota al cerrar esta spec. |
| **Qué se mide** | Nada nuevo. Sembrar un agente ya pasa por el medidor de la spec 004; esta spec no añade ni una llamada al modelo que no se mida ya. |

> La superficie es la que ya está abierta. Todo lo que pide esta spec se
> resuelve con lecturas y escrituras que la consola ya hace.

## Contexto

Lo que sigue está **medido sobre la consola en marcha** el 2026-09-28, no
estimado.

| Qué | Cuánto |
|---|---|
| Pasos del asistente | 4 — Datos · Plantilla · Canal · Revisión |
| Plantillas en el catálogo | 13, en rejilla plana sin agrupar |
| Campos de la plantilla marcada **por defecto** | **23 en pantalla, 12 obligatorios** |
| Placeholders por plantilla | de 3 a **24**; mediana 10 |
| Herramientas del Companion | 41, **todas de solo lectura** |
| Campos que el renderizador **exige de verdad** | **2** en 10 plantillas · **0** en 3 · **12** en `aesthetic_clinic_v1` |

Cuatro hechos que la spec ataca:

1. **La plantilla por defecto es la más pesada del catálogo, y es arbitraria.**
   Viene marcada `aesthetic_clinic_v1` porque la API la devuelve primera —orden
   alfabético—, no porque encaje. Pide 24 placeholders contra una mediana de 10.
   Quien da de alta una barbería aterriza en un formulario de medicina estética
   que le pide «Credencial del titular» y «Depósito de cirugía (%)».
2. **Veintitrés campos antes de que el cliente exista.** Ninguno hace falta para
   crearlo: son texto que rellena el prompt y que se edita después. El alta cobra
   por adelantado un trabajo que la ficha ya sabe pedir poco a poco.
3. **El paso 3 no hace nada.** Elegir «WhatsApp» o «más tarde» no viaja al
   servidor ni queda en el cliente (`case "channel": return done(); //
   informational`). Solo cambia qué botón sale al final: un cuarto del asistente
   dedicado a una pregunta cuya respuesta se descarta.
4. **Casi todo lo que se pide es opcional, y se pide igual.** Ejecutando el
   renderizador contra las trece semillas con los campos vacíos, **diez piden
   exactamente dos** —`tenant.address` y `tenant.business_hours_label`— y tres
   no piden ninguno. Solo `aesthetic_clinic_v1` exige doce. No son trece
   problemas distintos: casi todos los prompts mencionan la dirección y el
   horario, y nada más. Lo demás que el formulario enseña tiene valor por
   defecto y podría no preguntarse.
5. **«Publicar ahora» aparece la última.** Es la decisión que más pesa —determina
   si el agente nace vivo o en borrador— y se enseña en el paso 4, junto a un
   resumen de lo que el usuario acaba de escribir.

## Clarifications

### Session 2026-09-28

- Q: Si el alta deja de pedir los datos del negocio, ¿dónde se piden después? → A: un paso más en la tarjeta «Pasos para activar tu agente», con su propia barra.
- Q: ¿Dónde vive la ayuda del Companion durante el alta? → A: una caja en el propio alta; el panel no escribe en la página.
- Q: Si una plantilla no da un agente coherente sin rellenar nada, ¿qué hacemos? → A: esa conserva sus campos mínimos, anotado en paridad. **Revocada el 2026-09-28** (ver abajo).
- Q: ¿Qué se rellena en el alta y qué no? → A: **lo básico aquí, lo avanzado en los ajustes del agente**. Precios, formas de pago, credenciales del titular y teléfonos de referencia no son datos de alta. Consecuencia: `aesthetic_clinic_v1` deja de ser la excepción y **las trece plantillas piden lo mismo**; su semilla lleva valores por defecto seguros, y esa tarea entra en alcance.
- Q: ¿El horario se escribe o se elige? → A: se elige, con controles de hora. Y eso **disuelve el campo «Sábados»**, que solo existía porque el horario era texto libre.
- Q: ¿Se pregunta si publicar al crear? → A: **no**. El cliente no atiende hasta estar configurado y con canal, así que elegirlo al crear no adelanta nada. Publicar es un paso de la ficha. **Historia 4 y R6 quedan retiradas.**
- Q: ¿Con cuánto crédito nace un cliente? → A: **cero**. El partner se lo asigna cuando lo vea.
- Q: ¿El horario empieza resumido o día a día? → A: **día a día**, con la opción de resumirlo. Casi ningún negocio abre los siete días igual.
- Q: ¿La dirección permite elegir en un mapa? → A: **pendiente**. Añade un script de terceros, una clave de API y manda la dirección del cliente a Google; cambia la superficie de confianza que esta spec declara.
- Q: ¿Qué contesta un agente al que nadie le ha configurado sus políticas? → A: **calla y deriva**. Si el valor no lo puso el partner, la política **no entra en el prompt** y en su lugar va una frase de derivación al equipo. Un defecto de plantilla no es una respuesta: hoy una clínica que no toca nada tiene un agente diciendo por WhatsApp que el no-show se cobra al 100 % y la seña de quirófano es el 30 %, cifras que nadie le dio. El mismo prompt ya le prohíbe inventar promociones y improvisar la tasa de cambio; esto es la misma regla. *(owner, 2026-09-28 — redefine T036, cuya premisa original era falsa: medido, las trece plantillas renderizan sin esos campos.)*

## Escenarios de usuario y pruebas *(obligatorio)*

### Historia 1 — Crear un cliente cabe en una pantalla (Prioridad: P1)

El partner abre «Nuevo cliente», dice a qué se dedica el negocio y cómo se
llama, y el cliente existe. Nada más. Lo que el agente necesita saber del
negocio se le pide después, en la ficha, donde ya hay una tarjeta que lo pide.

**Por qué esta prioridad**: es el primer contacto con el producto y hoy es el
peor momento de la consola. Entregada sola ya quita 23 campos del camino.

**Prueba independiente**: un partner crea un cliente de principio a fin sin
rellenar ningún campo de plantilla, y el cliente queda utilizable.

**Escenarios de aceptación**:

1. **Dado** un partner con cupo, **cuando** abre «Nuevo cliente», **entonces** lo
   primero que se le pregunta es a qué se dedica el negocio, y **ninguna**
   opción viene marcada.
2. **Dado** que ha elegido a qué se dedica y ha escrito el nombre, **cuando**
   pulsa crear, **entonces** el cliente existe sin haber rellenado ningún campo
   de los que la plantilla admite.
3. **Dado** un alta recién terminada, **cuando** el partner llega a la ficha,
   **entonces** lo que falta se lo pide la tarjeta de pasos, no un formulario.

---

### Historia 2 — La plantilla se elige, no se hereda (Prioridad: P1)

Elegir a qué se dedica el negocio es la primera decisión y decide el resto: el
prompt, las herramientas y qué se le puede preguntar al negocio. El catálogo se
recorre como un catálogo —se busca y se agrupa—, no como una rejilla de trece
botones.

**Por qué esta prioridad**: sin esto, la historia 1 arregla la cantidad de
campos pero deja el error de raíz — empezar en la plantilla equivocada.

**Prueba independiente**: con las trece plantillas, un partner encuentra la que
busca sin recorrer la rejilla entera, y no puede continuar por inercia con una
que nadie eligió.

**Escenarios de aceptación**:

1. **Dado** el catálogo de plantillas, **cuando** el partner llega, **entonces**
   no hay ninguna seleccionada y no puede continuar hasta elegir.
2. **Dado** que escribe en el buscador, **cuando** teclea, **entonces** la lista
   se reduce a lo que coincide y dice cuántas quedan.
3. **Dado** que no encuentra la suya, **cuando** mira las opciones, **entonces**
   existe una salida explícita —empezar sin plantilla— y dice qué implica.

---

### Historia 3 — El Companion redacta el borrador (Prioridad: P2)

El partner escribe una frase sobre el negocio —«barbería en Madrid, cuatro
sillas, abre sábados»— y el Companion propone qué plantilla encaja y rellena lo
que pueda de los datos del negocio. El partner lo revisa y decide. **El clic
que crea el cliente sigue siendo suyo.**

**Por qué esta prioridad**: es lo que convierte «menos campos» en «ningún campo
en blanco», pero las dos primeras historias valen sin ella.

**Prueba independiente**: con el Companion apagado o caído, el alta funciona
igual; con él encendido, el partner llega a la confirmación con los campos ya
propuestos.

**Escenarios de aceptación**:

1. **Dado** un partner en el alta, **cuando** describe el negocio en una frase,
   **entonces** el Companion propone una plantilla y explica por qué.
2. **Dado** que el Companion ha propuesto valores, **cuando** el partner mira el
   formulario, **entonces** distingue **qué ha propuesto la máquina y qué ha
   escrito él**, y puede cambiar o descartar cualquiera.
3. **Dado** que el Companion no responde, **cuando** el partner sigue, **entonces**
   el alta continúa sin él y no se queda bloqueada.
4. **Dado** cualquier estado, **cuando** el Companion actúa, **entonces** NO crea
   el cliente, NO lo publica y NO lo activa: solo propone texto.

---

### Historia 4 — *(retirada el 2026-09-28)*

Decía que publicar se decidiera junto a la plantilla. El owner la retiró
entera: **la elección no tenía consecuencia**. Un cliente no atiende hasta
estar configurado y con canal, así que «publícalo ahora» no adelantaba el día
siguiente — solo obligaba a elegir entre dos palabras. El agente nace en
borrador y se publica desde la ficha.

---

### Casos límite

- **El cupo está lleno.** El alta lo dice antes de pedir nada, no después de
  rellenar el formulario.
- **La referencia ya existe en ese partner.** Se detecta antes de crear y se
  dice en el campo, no en un error del servidor al final.
- **El catálogo de plantillas no carga.** El alta sigue: se puede crear un
  cliente sin plantilla, y se dice qué se está perdiendo.
- **Una etapa falla a mitad.** Lo que ya se creó no se pierde ni se duplica al
  reintentar, y la pantalla dice qué quedó hecho.
- **El Companion no está disponible** (apagado por el partner, sin conexión, o
  sin permiso de su rol). Constitución §V: no se enseña un botón apagado ni una
  pantalla que explique lo que no tienes — **la ayuda sencillamente no aparece**,
  y el alta se recorre entera sin ella.

## Requisitos *(obligatorio)*

### Requisito 1 — Crear un cliente pide lo imprescindible

**Historia de usuario:** Como partner, quiero crear un cliente sin rellenar un
formulario largo, para que empezar no cueste más que continuar.

#### Criterios de aceptación

1. El sistema DEBE permitir crear un cliente con **cuatro datos, iguales para
   las trece plantillas**: a qué se dedica el negocio, cómo se llama, dónde
   está y cuándo abre. *(Owner, 2026-09-28: «los datos básicos los rellenamos
   acá y los datos más avanzados en los ajustes del agente».)*
2. El sistema NO DEBE pedir en el alta **ningún dato avanzado**: precios,
   formas de pago, credenciales profesionales, teléfonos de referencia ni
   tablas. Son configuración del agente y van a sus ajustes.
3. WHERE una plantilla exige un dato avanzado para renderizar EL sistema DEBE
   traerlo de un **valor por defecto seguro en su semilla** —una respuesta que
   un agente bien educado daría mientras no se lo hayan dicho, no un hueco
   vacío— y NO DEBE pedirlo en el alta. *(Revoca la aclaración anterior: la
   excepción de `aesthetic_clinic_v1` se arregla en la semilla, no en la
   pantalla.)*
4. El sistema NO DEBE pedir en el alta ningún dato que la ficha del cliente ya
   sepa pedir después.
5. WHERE un dato del negocio es necesario para que el agente atienda EL sistema
   DEBE pedirlo como **un paso más de «Pasos para activar tu agente»**, con su
   barra y su cuenta de cuántos faltan, y NO en el alta. *(Aclaración
   2026-09-28: la tarjeta pasa de tres pasos a cuatro; es el sitio donde el
   partner ya mira qué le falta, y una barra a medias dice cuánto queda.)*
6. El sistema NO DEBE limitar cuántos clientes puede crear un partner, y NO
   DEBE enseñar ningún contador ni aviso de cupo en el alta. *(Owner,
   2026-09-28: «crear un cliente no tiene limitantes para los partners».)*

### Requisito 7 — Lo que se pide, se pide con el control que le corresponde

**Historia de usuario:** Como partner, quiero decir cuándo abre el negocio sin
inventarme un formato, para que el agente diga la hora bien.

#### Criterios de aceptación

1. El horario DEBE elegirse con controles de hora, NO escribirse como texto
   libre.
2. El sistema NO DEBE tener un campo «Sábados» aparte: el sábado es un día del
   horario. *(Ese campo solo existía porque el horario era una cadena que
   alguien escribía a mano y los sábados no cabían en ella.)*
3. El horario DEBE empezar por el caso corriente —un tramo de lunes a viernes y
   el sábado— y DEBE poder abrirse día a día para quien lo necesite.
4. La dirección DEBE ser lo que el agente necesita para decir dónde está el
   negocio. *(Si se elige en un mapa o se escribe, está pendiente de decisión:
   un mapa de terceros cambia la superficie de confianza de esta spec.)*

### Requisito 2 — La plantilla se elige la primera, y a conciencia

**Historia de usuario:** Como partner, quiero decir a qué se dedica el negocio
antes que nada, para que el resto del alta se estreche solo.

#### Criterios de aceptación

1. El sistema DEBE preguntar por la plantilla **antes** que por el nombre.
2. El sistema NO DEBE preseleccionar ninguna plantilla, y NO DEBE permitir
   continuar sin una elección explícita.
3. WHEN hay más plantillas de las que caben de un vistazo THEN el sistema DEBE
   ofrecer buscarlas y DEBE decir cuántas quedan al filtrar.
4. El sistema DEBE ofrecer empezar **sin plantilla** como una opción nombrada, y
   DEBE decir qué implica: el agente nace vacío y lo escribe el partner.
5. WHERE una plantilla está elegida EL sistema DEBE decir, antes de crear, qué
   trae: para qué sirve y cuántas habilidades enciende.

### Requisito 3 — Un paso menos, y ninguno que no haga nada

**Historia de usuario:** Como partner, quiero que cada pregunta del alta tenga
consecuencia, para no gastar clics en nada.

#### Criterios de aceptación

1. El sistema NO DEBE preguntar por el canal durante el alta.
2. WHEN el cliente se ha creado THEN el sistema DEBE llevar al partner a donde se
   conecta el canal, que es la ficha.
3. El sistema NO DEBE tener ningún paso cuya respuesta no cambie lo que se crea.

### Requisito 4 — La referencia deja de ser la segunda pregunta

**Historia de usuario:** Como partner, quiero no tener que inventar un
identificador para empezar, para que el vocabulario de la API no sea mi segundo
contacto con el producto.

#### Criterios de aceptación

1. El sistema DEBE derivar la referencia del nombre del negocio.
2. WHERE el partner quiere fijarla a mano EL sistema DEBE permitirlo, plegada
   fuera del camino principal.
3. WHEN la referencia derivada ya existe en ese partner THEN el sistema DEBE
   decirlo antes de intentar crear, y DEBE proponer una libre.
4. El sistema DEBE seguir diciendo que la referencia no se puede cambiar
   después, **donde se edita** y no antes.

### Requisito 5 — El Companion propone; el partner decide

**Historia de usuario:** Como partner, quiero describir el negocio con mis
palabras y que alguien me prepare el borrador, para no empezar de cero.

#### Criterios de aceptación

1. WHEN el partner describe el negocio en texto libre **en una caja del propio
   alta** THEN el sistema DEBE proponer una plantilla y DEBE explicar en una
   línea por qué esa. *(Aclaración 2026-09-28: la ayuda vive en la pantalla, no
   en el panel del Companion. El panel **no** escribe en la página: ese
   acoplamiento se evita a propósito.)*
2. El sistema DEBE proponer valores para los datos del negocio que la plantilla
   admite, y DEBE distinguir en pantalla **lo propuesto de lo escrito por el
   partner**.
3. El partner DEBE poder cambiar o descartar cualquier valor propuesto, uno a uno
   y todos a la vez.
4. **El Companion NO DEBE crear, publicar ni activar el cliente.** La escritura
   la hace el partner con su propia acción. *(Constitución §I, capa 2: las
   herramientas del Companion son de solo lectura y hay un test que recorre el
   catálogo y lo exige. Esta spec no lo enmienda.)*
5. IF el Companion no está disponible THEN el sistema DEBE dejar el alta
   completamente usable y NO DEBE enseñar un control apagado (§V).
6. El sistema NO DEBE enviar al Companion nada que el partner no haya escrito o
   elegido en esta pantalla.

### Requisito 6 — Lo que se crea se ve mientras se crea

**Historia de usuario:** Como partner, quiero saber qué está pasando y qué
quedó hecho si algo falla, para no tener que adivinar si repetir.

#### Criterios de aceptación

1. WHILE el alta se ejecuta el sistema DEBE decir qué etapa va y cuál queda.
2. IF una etapa falla THEN el sistema DEBE decir cuál, DEBE conservar lo ya hecho
   y DEBE ofrecer reintentar **solo** lo que falló.
3. WHEN el alta termina THEN el sistema DEBE decir qué se creó y ofrecer el
   siguiente paso real, que es conectar el canal.
4. El sistema NO DEBE preguntar si publicar el agente. *(Owner, 2026-09-28: el
   cliente no atiende hasta estar configurado y con canal, así que la elección
   no adelantaba nada. El agente nace en borrador y se publica desde la ficha,
   donde la tarjeta de pasos ya lo pide.)*

### Requisito 8 — Un cliente nace sin crédito

**Historia de usuario:** Como partner, quiero decidir yo cuánto crédito lleva
cada cliente, para no repartir sin querer lo que he comprado.

#### Criterios de aceptación

1. WHEN se crea un cliente THEN el sistema DEBE asignarle **cero créditos**.
2. El sistema DEBE crear igualmente su fila de cupo. *(Una fila con tope 0 es
   visible y explicable; **la ausencia de fila es el silencio que costó el corte
   del 31-ago** — `seed_default_allocation` existe por eso y no se toca.)*
3. WHEN el alta termina THEN el sistema DEBE decir que el cliente empieza sin
   crédito y dónde se le asigna.

### Requisito 9 — Todo en un idioma

**Historia de usuario:** Como partner, quiero leer la consola en mi idioma sin
palabras sueltas del otro, para no tener que traducir a medias.

#### Criterios de aceptación

1. El sistema NO DEBE mezclar idiomas en una misma pantalla. *(Medido el
   2026-09-28: «Spa (belleza y wellness)» y «Clínica estética (medspa +
   cirugía)» en una pantalla en español.)*
2. WHERE un nombre de plantilla lleva una palabra del otro idioma EL sistema
   DEBE cambiarla en la semilla, que es de donde sale.
3. Un nombre de marca —WooCommerce, WhatsApp— NO es una palabra en inglés y se
   deja como es.

### Requisito 10 — Cada tipo de negocio se reconoce sin leerlo

**Historia de usuario:** Como partner, quiero reconocer el rubro de mi cliente
de un vistazo, para no leer trece nombres.

#### Criterios de aceptación

1. Cada plantilla DEBE llevar un icono de su rubro.
2. El icono NO DEBE ser la única señal: el nombre y para qué sirve siguen ahí.

### Entidades clave

Ninguna nueva. El alta sigue creando un **Tenant** dentro del partner del
llamante, con su `external_client_ref` único por partner, y sembrando su
**versión de agente** desde una plantilla. Ni tablas, ni columnas, ni políticas
de RLS cambian.

## Criterios de éxito *(obligatorio)*

- **CE-001**: crear un cliente utilizable requiere una elección y **cuatro
  datos, los mismos para las trece plantillas** —nombre, zona horaria,
  dirección y horario—; hoy la plantilla marcada por defecto enseña 23 campos.
  **Sin excepciones**: si una plantilla exige más para renderizar, lo trae de su
  semilla.
- **CE-002**: el alta tiene **tres pasos o menos**, y ninguno cuya respuesta se
  descarte; hoy tiene cuatro y uno se descarta.
- **CE-003**: ningún partner puede terminar el alta con una plantilla que no
  eligió.
- **CE-004**: alguien que no conoce el producto encuentra la plantilla de su
  negocio entre las trece sin recorrerlas todas, y lo dice en voz alta al
  probarlo.
- **CE-005**: con el Companion encendido, el partner llega a confirmar con los
  campos del negocio ya propuestos y sabe cuáles son suyos y cuáles no.
- **CE-006**: con el Companion apagado o caído, el alta se completa igual, y
  ninguna pantalla menciona una ayuda que no está.
- **CE-007**: ninguna dirección que la consola tenía antes de esta spec responde
  «no existe».
- **CE-008**: un cliente recién creado tiene **cero créditos** y su ficha lo
  dice; hoy nace con 50 000 que nadie decidió.
- **CE-009**: ninguna pantalla del alta mezcla idiomas.

## Fuera de alcance

- **Dar escritura al Companion** — es una decisión de seguridad (capa 2 del
  aislamiento), no un cambio de interfaz. Si algún día se quiere, va en su
  propia spec con su ADR.
- **Conectar el canal desde el alta** — el canal se conecta en su pantalla, con
  su ventana de Meta. Traerlo aquí es la superficie de la spec 016, no ésta.
- **Reescribir los prompts de las plantillas** — esta spec cambia **cuándo** se
  piden los datos y **de dónde salen si no se piden**. Dar valores por defecto
  seguros a los campos avanzados de `aesthetic_clinic_v1` **sí entra** desde el
  2026-09-28: sin ellos, la regla «lo avanzado no se pide en el alta» no se
  puede cumplir.
- **Rehacer la ficha del cliente** — la tarjeta de pasos ya existe y ya pide lo
  que falta (spec 018, R6).
- **Importar clientes en lote** — nadie lo ha pedido y multiplicaría el alcance.

## El límite de clientes se retira

El owner decidió el 2026-09-28 que **crear un cliente no tiene limitantes para
los partners**. Hoy sí lo tiene, y en tres sitios:

| Dónde | Qué hace |
|---|---|
| `partners.max_clients` | Columna con `server_default="5"` (migración 0081) |
| `provision_partner_client` | **409** bajo bloqueo de fila, antes de crear nada |
| Consola | Contador «{used} de {max} clientes» en la lista, aviso en el alta, estado de cupo lleno |

**Una cosa que conviene no perder al quitarlo.** El límite tiene una segunda
vida que nadie escribió: se comprueba **antes de crear nada y bajo bloqueo de
fila**, así que hoy acota el daño si una clave se filtra o un bucle se
descontrola. Sin ninguna comprobación, nada impide crear diez mil tenants.

Por eso la retirada se plantea como **quitar el límite de producto, no la
guarda**: desaparece de la consola —contador, aviso y pantalla— y el modelo
conserva un techo de cordura alto que ningún partner real alcanza. Si el owner
prefiere retirarlo del todo, es una línea menos y queda anotado aquí.

## Supuestos## Supuestos

- **Ya no es un supuesto: está medido.** Se ejecutó el renderizador de semillas
  contra las trece plantillas con los campos vacíos, contando qué exige cada una
  antes de poder renderizar. Diez exigen dos campos, tres no exigen ninguno y
  `aesthetic_clinic_v1` exige doce. Un campo sin valor y sin defecto **no produce
  un agente incoherente: levanta `SeedTemplatePlaceholderMissing`**, así que la
  frontera es dura y comprobable, no un juicio de calidad.
- El partner sabe a qué se dedica el negocio que está dando de alta. Es su
  cliente.
- Las trece plantillas caben en un catálogo buscable sin agrupar por categoría;
  si el catálogo creciera, el patrón de la spec 018 ya resuelve el agrupado.
- El Companion puede leer el catálogo de plantillas con las herramientas que ya
  tiene (`console.list_templates`, `console.get_onboarding`): esta spec no le
  añade ninguna.
