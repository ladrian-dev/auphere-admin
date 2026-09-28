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
4. **«Publicar ahora» aparece la última.** Es la decisión que más pesa —determina
   si el agente nace vivo o en borrador— y se enseña en el paso 4, junto a un
   resumen de lo que el usuario acaba de escribir.

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

### Historia 4 — Publicar se decide cuando se elige la plantilla (Prioridad: P3)

La decisión de si el agente nace publicado o en borrador se toma junto a la
plantilla, que es lo que la hace entendible, y no en un resumen final.

**Por qué esta prioridad**: es una mejora de orden; el alta ya funciona sin
ella.

**Prueba independiente**: el partner ve la elección antes de escribir nada, y el
resumen final se limita a resumir.

**Escenarios de aceptación**:

1. **Dado** que el partner ha elegido plantilla, **cuando** se le ofrece
   publicar, **entonces** la elección está en la misma pantalla y dice qué pasa
   con cada opción.
2. **Dado** que el rol no puede publicar, **cuando** llega ahí, **entonces** no
   ve un control muerto y el alta no promete lo que no va a ocurrir.

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

1. El sistema DEBE permitir crear un cliente con **tres datos**: a qué se dedica
   el negocio, cómo se llama y su zona horaria.
2. WHEN el partner no rellena ningún campo de los que la plantilla admite THEN el
   sistema DEBE crear el cliente igual, usando los valores por defecto de la
   plantilla.
3. El sistema NO DEBE pedir en el alta ningún dato que la ficha del cliente ya
   sepa pedir después.
4. WHERE un dato del negocio es necesario para que el agente atienda EL sistema
   DEBE pedirlo en la ficha, donde vive la tarjeta de pasos, y NO en el alta.
5. WHEN el cupo de clientes está agotado THEN el sistema DEBE decirlo antes de
   pedir el primer dato.

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

1. WHEN el partner describe el negocio en texto libre THEN el sistema DEBE
   proponer una plantilla y DEBE explicar en una línea por qué esa.
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

**Historia de usuario:** Como partner, quiero saber qué está pasando y qué quedó
hecho si algo falla, para no tener que adivinar si repetir.

#### Criterios de aceptación

1. WHILE el alta se ejecuta el sistema DEBE decir qué etapa va y cuál queda.
2. IF una etapa falla THEN el sistema DEBE decir cuál, DEBE conservar lo ya hecho
   y DEBE ofrecer reintentar **solo** lo que falló.
3. WHEN el alta termina THEN el sistema DEBE decir qué se creó y ofrecer el
   siguiente paso real, que es conectar el canal.

### Entidades clave

Ninguna nueva. El alta sigue creando un **Tenant** dentro del partner del
llamante, con su `external_client_ref` único por partner, y sembrando su
**versión de agente** desde una plantilla. Ni tablas, ni columnas, ni políticas
de RLS cambian.

## Criterios de éxito *(obligatorio)*

- **CE-001**: crear un cliente utilizable requiere **tres datos y ningún campo
  de plantilla**; hoy la plantilla por defecto pide 23 campos, 12 obligatorios.
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

## Fuera de alcance

- **Dar escritura al Companion** — es una decisión de seguridad (capa 2 del
  aislamiento), no un cambio de interfaz. Si algún día se quiere, va en su
  propia spec con su ADR.
- **Conectar el canal desde el alta** — el canal se conecta en su pantalla, con
  su ventana de Meta. Traerlo aquí es la superficie de la spec 016, no ésta.
- **Cambiar las plantillas o sus campos** — esta spec cambia **cuándo** se
  piden, no qué pide cada plantilla. Adelgazar `aesthetic_clinic_v1` es trabajo
  de la plantilla, en la KB.
- **Rehacer la ficha del cliente** — la tarjeta de pasos ya existe y ya pide lo
  que falta (spec 018, R6).
- **Importar clientes en lote** — nadie lo ha pedido y multiplicaría el alcance.

## Supuestos

- Los valores por defecto de cada plantilla producen un agente **coherente aunque
  nadie rellene nada**. Es lo que ya hace hoy quien deja los campos opcionales en
  blanco (`cleanPlaceholders` los descarta para que caigan al valor por defecto);
  esta spec lo extiende a los obligatorios y el plan lo verifica plantilla a
  plantilla antes de escribir código.
- El partner sabe a qué se dedica el negocio que está dando de alta. Es su
  cliente.
- Las trece plantillas caben en un catálogo buscable sin agrupar por categoría;
  si el catálogo creciera, el patrón de la spec 018 ya resuelve el agrupado.
- El Companion puede leer el catálogo de plantillas con las herramientas que ya
  tiene (`console.list_templates`, `console.get_onboarding`): esta spec no le
  añade ninguna.
