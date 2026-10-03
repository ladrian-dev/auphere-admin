# Especificación: la ficha adelgaza y sus catálogos se navegan

**Rama**: `018-ficha-ligera-y-catalogos` · **Creada**: 2026-09-27 · **Estado**: Borrador

**Entrada**: ocho anotaciones del owner del 2026-09-27 sobre la consola tal y como
quedó al cerrar la spec 017 (iteraciones 1 y 2, fusionadas en `develop`).

## Encabezado Auphere *(obligatorio)*

| Campo | Valor |
|---|---|
| **Superficie de confianza** | `0` — API de la consola. No se abre ninguna nueva |
| **Garantías de aislamiento tocadas** | Ninguna nueva. Se mueve **dónde se lee** y **cómo se navega**; todo sigue acotado por tenant dentro de un partner, y el Resumen no puede enseñar de un cliente nada que su ficha no enseñara ya |
| **Nota de KB que la justifica** | `[[nexus/sessions/2026-09-27-spec-017-iteracion-2]]` (anotaciones del owner al cierre) y `[[nexus/PLAN-ACCION-CONSOLA-2026-09-22]]` |
| **Qué se mide** | Nada nuevo. El consumo que el Resumen enseña ya lo mide el medidor de la spec 004; esta spec solo lo **lee** |

## Contexto

La spec 017 dejó la ficha del cliente con once pestañas y dos pantallas nuevas
—Capacidades e Integraciones—. Funciona, pero el owner la usó y encontró tres
problemas de forma, no de fondo:

1. **El Resumen no resume.** Enseña la salud del cliente y tres cifras de
   conversaciones. Para saber si un cliente va bien hay que recorrer seis
   pestañas y volver.
2. **Hay pestañas que no se ganan su sitio.** «Datos del cliente» son dos
   campos. «Ajustes» y «Agente» son dos mitades de lo mismo.
3. **Los catálogos están pensados para seis elementos y van a tener decenas.**
   Habilidades, Conectores y Canales son tres listas que crecerán, y hoy solo
   una de ellas tiene buscador.

Nada de esto cambia lo que la consola **puede hacer**: cambia dónde está y
cuánto cuesta encontrarlo.

## Escenarios de usuario y pruebas *(obligatorio)*

### Historia 1 — El Resumen contesta sin abrir nada (Prioridad: P1)

Un partner con cinco clientes quiere saber, un lunes por la mañana, cómo fue el
fin de semana de la panadería. Abre su ficha y lo ve en una pantalla: si está
atendiendo, cuánto crédito le queda y a qué ritmo lo gasta, cuántas
conversaciones hubo y cuántas se escalaron, y qué tiene conectado. Si algo le
llama la atención, un clic lo lleva al detalle.

**Por qué esta prioridad**: es el problema que el owner nombró primero, y el que
hace que la consola se sienta un formulario en vez de un panel.

**Prueba independiente**: se entrega sola. Con el Resumen nuevo, un partner
contesta «¿cómo va este cliente?» sin cambiar de pestaña, aunque el resto de la
spec no exista.

**Escenarios de aceptación**:

1. **Dado** un cliente atendiendo con crédito y conversaciones de los últimos 30
   días, **cuando** el partner abre su Resumen, **entonces** ve en una sola
   pantalla estado, crédito restante con su ritmo de gasto, conversaciones y
   escaladas, y qué canales y conectores tiene conectados.
2. **Dado** un cliente recién creado sin actividad, **cuando** el partner abre su
   Resumen, **entonces** cada bloque dice que todavía no hay datos y por qué, y
   ninguno enseña un cero que parezca una caída.
3. **Dado** que una de las lecturas del Resumen falla, **cuando** la pantalla se
   pinta, **entonces** ese bloque dice que no se pudo leer y ofrece reintentar, y
   **el resto del Resumen sigue funcionando**.
4. **Dado** un partner con rol de analista, **cuando** abre el Resumen,
   **entonces** ve las cifras y no ve ningún control que le respondería que no
   tiene permiso.

---

### Historia 2 — Dos pestañas menos, y ninguna función perdida (Prioridad: P1)

El nombre y la zona horaria del cliente se editan desde el Resumen, donde ya se
leen. Los ajustes del agente viven dentro de «Agente», que es de lo que hablan.
La ficha pasa de once pestañas a nueve.

**Por qué esta prioridad**: es barato, se nota en cada visita, y sin ello el
Resumen de la Historia 1 compite con una pestaña que enseña lo mismo.

**Prueba independiente**: se recorre la ficha entera y ninguna acción de hoy ha
desaparecido; solo ha cambiado de sitio.

**Escenarios de aceptación**:

1. **Dado** un partner en el Resumen, **cuando** edita el nombre o la zona
   horaria del cliente, **entonces** se guarda desde ahí y la ficha lo refleja
   sin que exista una pestaña «Datos del cliente».
2. **Dado** un enlace guardado a `…/settings`, **cuando** alguien lo abre,
   **entonces** llega a donde está ahora esa información, no a un 404.
3. **Dado** un borrador con cambios en los ajustes del agente, **cuando** el
   partner mira la navegación, **entonces** el punto de «sin publicar» señala
   «Agente», que es donde vive el cambio.
4. **Dado** un partner que edita el nombre del cliente, **cuando** guarda,
   **entonces** ese cambio **no** entra en el borrador del agente: cambiar el
   nombre del negocio no es cambiar lo que el agente hace.

---

### Historia 3 — Un catálogo se navega igual en los tres sitios (Prioridad: P2)

Habilidades, Conectores y Canales se recorren con el mismo gesto: buscar, ver lo
que ya está activo o descubrir lo que hay, filtrar por categoría, y leer por
grupos en vez de por una lista larga. Quien aprende uno sabe usar los otros.

**Por qué esta prioridad**: es la que más trabajo cuesta y la que más aguanta el
crecimiento, pero no bloquea a las dos primeras.

**Prueba independiente**: con veinte elementos en cualquiera de los tres, un
partner encuentra el que busca sin recorrer la pantalla entera.

**Escenarios de aceptación**:

1. **Dado** un catálogo con más elementos de los que caben en pantalla,
   **cuando** el partner escribe en el buscador, **entonces** la lista se reduce
   a lo que coincide y dice cuántos quedan.
2. **Dado** un catálogo, **cuando** el partner elige ver solo lo activo,
   **entonces** ve únicamente lo que ese cliente tiene encendido o conectado, y
   puede volver a verlo todo.
3. **Dado** un filtro que no deja nada, **cuando** la lista queda vacía,
   **entonces** la pantalla dice con qué se filtró y ofrece quitarlo.
4. **Dado** que el partner filtró y buscó, **cuando** comparte la dirección de la
   página o vuelve atrás, **entonces** encuentra lo mismo que estaba viendo.
5. **Dado** cualquiera de los tres catálogos, **cuando** se comparan entre sí,
   **entonces** el buscador, las pestañas y los filtros están en el mismo sitio y
   se llaman igual.

---

### Historia 4 — Las palabras dicen lo que son (Prioridad: P2)

«Capacidades» pasa a llamarse **Habilidades** e «Integraciones» pasa a llamarse
**Conectores**. Y las dos pantallas de documentos —Conocimiento y Guía del
partner— dicen en su cabecera quién las lee, que es lo único que las diferencia.

**Por qué esta prioridad**: es copy, cuesta poco, y quita la única confusión que
el owner nombró como pregunta.

**Prueba independiente**: alguien que no conoce el producto lee las dos pantallas
de documentos y sabe cuál usar.

**Escenarios de aceptación**:

1. **Dado** un partner en la ficha, **cuando** lee la navegación, **entonces**
   encuentra «Habilidades» y «Conectores», y en ningún sitio de la consola queda
   «Capacidades» ni «Integraciones».
2. **Dado** un partner en «Conocimiento», **cuando** lee la cabecera,
   **entonces** sabe que eso lo lee el agente de **ese** cliente para responder a
   sus clientes finales.
3. **Dado** un partner en «Guía del partner», **cuando** lee la cabecera,
   **entonces** sabe que eso lo lee su asistente de la consola y que el agente de
   un cliente **no** lo ve.

---

### Historia 5 — «Puesta en marcha» pesa menos (Prioridad: P3)

La tarjeta que dice qué falta para que el agente atienda mete hoy el recorrido de
cuatro pasos, el siguiente paso explicado y el crédito en un solo bloque. Se
reparte para que se lea de un vistazo.

**Por qué esta prioridad**: es la anotación más de forma de las ocho, y la única
cuyo arreglo depende de cómo quede el Resumen de la Historia 1.

**Prueba independiente**: la cabecera de un cliente a medio configurar se lee sin
detenerse.

**Escenarios de aceptación**:

1. **Dado** un cliente al que le falta un paso, **cuando** el partner abre su
   ficha, **entonces** ve qué falta y cómo resolverlo sin leer un bloque de más
   de una decisión.
2. **Dado** un cliente con los cuatro pasos hechos, **cuando** el partner abre su
   ficha, **entonces** la puesta en marcha no ocupa sitio.

---

### Casos límite

- **Un catálogo vacío** (el entorno todavía no tiene nada publicado): se
  distingue de «el filtro no deja nada». Son dos vacíos distintos y dicen cosas
  distintas.
- **Un elemento sin categoría**: cae en un grupo que existe y se llama por lo que
  es, nunca en uno llamado «otros» que en realidad signifique «no lo sabemos».
- **Un cliente sin actividad**: ningún bloque del Resumen enseña un cero que
  parezca una caída; dice que aún no hay datos.
- **Una lectura del Resumen que falla**: se dice en su bloque, con reintento, y no
  tumba la pantalla (constitución §V).
- **La ausencia se diseña**: un canal que todavía no existe —Instagram, Telegram—
  **no** aparece apagado ni prometido. Lo que no se puede conectar no se enseña
  como si se pudiera.
- **Roles**: quien no puede escribir no ve controles muertos en ninguna de las
  pantallas nuevas; lee el estado igual.

## Requisitos *(obligatorio)*

### Requisito 1 — El Resumen del cliente

**Historia de usuario:** Como partner, quiero abrir la ficha de un cliente y
entender cómo va sin recorrer pestañas, para poder atender a cinco clientes sin
que cada uno me cueste diez minutos.

#### Criterios de aceptación

1. El Resumen DEBE contestar cuatro preguntas, cada una en su bloque: **¿atiende?**,
   **¿cuánto consume y cuánto le queda?**, **¿cómo va la conversación?** y **¿qué
   tiene conectado?**
2. Cada bloque DEBE enseñar la cifra que responde y NO DEBE enseñar más de lo que
   cabe leer de un vistazo; el detalle se alcanza con un clic a la pantalla que ya
   lo tiene.
3. El bloque de consumo DEBE decir crédito restante, gasto del periodo y a qué
   ritmo va, en la unidad «créditos», y DEBE enlazar al detalle de consumo.
4. El bloque de conversación DEBE decir cuántas conversaciones hubo, cuántas se
   escalaron y cuántos mensajes fallaron, cada cifra enlazando a su lista filtrada.
5. El bloque de lo conectado DEBE decir qué canales y qué conectores están activos
   y cuáles necesitan atención.
6. WHEN una de las lecturas del Resumen falla THEN el sistema DEBE decirlo en su
   bloque con un reintento, y los demás bloques DEBEN seguir funcionando.
7. WHERE el cliente no tiene actividad todavía EL sistema DEBE decir que aún no hay
   datos, y NO DEBE enseñar un cero indistinguible de una caída.
8. El Resumen NO DEBE necesitar una lectura por fila ni una llamada por bloque que
   crezca con el número de clientes del partner.

### Requisito 2 — Los datos del cliente se editan donde se leen

**Historia de usuario:** Como partner, quiero cambiar el nombre o la zona horaria
del cliente sin que eso sea una pestaña, para que la ficha tenga menos sitios donde
mirar.

#### Criterios de aceptación

1. El nombre y la zona horaria del cliente DEBEN poder leerse y editarse desde el
   Resumen.
2. La pestaña «Datos del cliente» DEBE desaparecer de la navegación.
3. IF alguien abre la dirección antigua de esa pestaña THEN el sistema DEBE llevarlo
   a donde está ahora esa información, y NO DEBE responder que no existe.
4. Editar el nombre o la zona horaria NO DEBE crear ni tocar el borrador del agente.

### Requisito 3 — Agente y sus ajustes, una sola pestaña

**Historia de usuario:** Como partner, quiero configurar el agente en un sitio, para
no tener que recordar cuál de dos pestañas guarda qué.

#### Criterios de aceptación

1. Los ajustes del agente DEBEN vivir dentro de «Agente», y la pestaña «Ajustes»
   DEBE desaparecer de la navegación.
2. WHEN hay cambios sin publicar en los ajustes del agente THEN la marca de
   borrador DEBE señalar «Agente».
3. IF alguien abre la dirección antigua de los ajustes THEN el sistema DEBE llevarlo
   a la pestaña «Agente».
4. Ninguna acción que hoy existe en cualquiera de las dos pantallas DEBE
   desaparecer al fundirlas.

### Requisito 4 — Un catálogo se navega igual en los tres sitios

**Historia de usuario:** Como partner, quiero encontrar lo que busco en una lista
que crece, para que tener más opciones no signifique tardar más.

#### Criterios de aceptación

1. Habilidades, Conectores y Canales DEBEN ofrecer el mismo patrón de navegación:
   buscador, separación entre lo que el cliente ya tiene y lo que hay disponible,
   filtro por categoría, y agrupación por categoría.
2. WHEN el partner busca THEN el sistema DEBE filtrar sobre lo que ya tiene cargado
   y DEBE decir cuántos elementos quedan.
3. WHEN el partner filtra y no queda nada THEN el sistema DEBE decir con qué se
   filtró y ofrecer quitarlo, distinguiéndolo de un catálogo vacío.
4. El estado de búsqueda y filtro DEBE viajar en la dirección de la página, de modo
   que se pueda compartir y que volver atrás haga lo que el partner espera.
5. WHERE un elemento no tiene categoría EL sistema DEBE colocarlo en un grupo con
   nombre propio, y NO DEBE inventar una categoría que no le corresponde.
6. El patrón DEBE definirse una vez y usarse en los tres sitios; los tres DEBEN
   llamar igual a las mismas cosas y colocarlas en el mismo sitio.
7. WHERE un canal o conector no está disponible todavía EL sistema NO DEBE
   enseñarlo apagado ni prometido (constitución §V).

### Requisito 5 — Las palabras dicen lo que son

**Historia de usuario:** Como partner, quiero que cada pantalla se llame como lo que
hace, para no tener que aprender el vocabulario interno de Auphere.

#### Criterios de aceptación

1. «Capacidades» DEBE pasar a llamarse **Habilidades** y «Integraciones» DEBE pasar
   a llamarse **Conectores**, en los dos idiomas, y ninguno de los dos nombres
   viejos DEBE quedar visible en la consola.
2. La pantalla «Conocimiento» DEBE decir en su cabecera que lo que hay ahí lo lee el
   agente de ese cliente para responder a sus clientes finales.
3. La pantalla «Guía del partner» DEBE decir en su cabecera que lo que hay ahí lo lee
   el asistente de la consola y que el agente de un cliente **no** lo ve.
4. El cambio de nombre NO DEBE cambiar ninguna dirección que alguien pueda tener
   guardada, o DEBE llevarla a su sitio nuevo.

### Requisito 6 — La puesta en marcha se lee de un vistazo

**Historia de usuario:** Como partner, quiero ver qué le falta a un cliente sin
leer un bloque denso, para poder resolverlo en vez de estudiarlo.

#### Criterios de aceptación

1. La información de puesta en marcha DEBE repartirse de modo que ningún bloque
   pida más de una decisión a la vez.
2. WHERE el cliente ya tiene los cuatro pasos hechos EL sistema NO DEBE ocupar sitio
   con la puesta en marcha.
3. Lo que la tarjeta dice hoy —los cuatro pasos, cuál es el siguiente y el estado del
   crédito— DEBE seguir estando, en el sitio que le corresponda.

### Entidades clave

Esta spec no crea entidades. Lee las que ya existen:

- **Cliente (tenant)**: nombre, zona horaria, estado y sector. Pertenece a un partner
  por su fila de `partner_tenants`; la RLS lo alcanza por `tenant_id`.
- **Consumo**: unidades medidas por el medidor de la spec 004 y crédito asignado al
  cliente. Acotado por tenant dentro del partner.
- **Conversaciones**: recuento, escaladas y mensajes fallidos del periodo, por tenant.
- **Habilidad** (antes capacidad): herramienta o habilidad del catálogo, con su función
  y su sector.
- **Conector** (antes integración) y **Canal**: su estado de instalación por tenant.

## Criterios de éxito *(obligatorio)*

- **CE-001**: un partner contesta «¿cómo va este cliente?» sin salir del Resumen; hoy
  necesita abrir al menos cuatro pestañas.
- **CE-002**: la ficha pasa de once pestañas a nueve sin que se pierda ninguna acción
  de las que hoy existen.
- **CE-003**: con veinte elementos en un catálogo, un partner encuentra uno concreto
  en menos de tres interacciones (escribir, filtrar o elegir pestaña).
- **CE-004**: los tres catálogos se recorren con el mismo gesto; alguien que usó uno
  no necesita instrucciones para el siguiente.
- **CE-005**: una persona que no conoce el producto lee Conocimiento y Guía del
  partner y dice correctamente cuál alimenta al agente del cliente.
- **CE-006**: cada pantalla nueva o rehecha pasa el barrido de accesibilidad sin
  violaciones serias ni críticas y sin desbordes a 360 px ni a 1920 px, en español y
  en inglés.
- **CE-007**: ninguna dirección que alguien pudiera tener guardada de la consola de
  hoy responde «no existe» después de esta spec.

## Fuera de alcance

- **Conectar canales nuevos** (Messenger, Instagram, Telegram, Gmail) — esta spec
  prepara la pantalla para que quepan; cada canal es trabajo propio, con su spec.
- **Crear o publicar habilidades desde la consola** —el «Crear Skill» de la
  referencia visual— porque las publica Auphere, no el partner.
- **Cambiar qué mide el medidor o cómo se factura**: el Resumen solo lee.
- **Rediseñar el consumo del partner** (`/usage`): es la iteración 3 de la spec 017 y
  sigue su curso.
- **Tema claro/oscuro y atajos de teclado**: siguen donde estaban.

## Supuestos

- El consumo, las conversaciones, los canales y los conectores que el Resumen
  necesita **ya se pueden leer por cliente** — comprobado el 2026-09-27 contra la
  API, no supuesto. Esta spec los junta; no inventa lecturas nuevas. Si alguna
  cifra concreta no existiera, el bloque que la necesite dirá que aún no hay dato
  en vez de rellenarlo.
- El renombrado a «Habilidades» y «Conectores» es un cambio de lo que se ve: las
  claves internas y las direcciones pueden conservar su nombre técnico mientras nada
  de eso llegue a la pantalla.
- «Habilidades» como nombre visible absorbe la distinción interna entre herramienta y
  habilidad, que sigue estando en el detalle técnico de cada ficha.
- La referencia visual de Perplexity se usa como **patrón de navegación**, no como
  diseño a copiar: la consola mantiene su propio sistema de diseño.
- Nadie pierde permisos con esta spec: lo que un rol podía hacer, lo sigue pudiendo
  hacer desde su sitio nuevo.
