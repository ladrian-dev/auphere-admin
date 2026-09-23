# Especificación: la ficha de cliente y el consumo, por flujo

**Rama**: `017-ficha-de-cliente-y-consumo` · **Creada**: 2026-09-23 · **Estado**: Clarificada — tres preguntas cerradas, cero marcas, lista para `/speckit-plan`

**Entrada**: Bloque D del plan aprobado por el owner (KB
`nexus/PLAN-ACCION-CONSOLA-2026-09-22.md`, tabla «Bloque D» y decisiones 3, 4 y
5 del 2026-09-23) sobre la auditoría UX (KB `nexus/AUDITORIA-UX-CONSOLA-2026-09-22.md`,
§2 T2/T3/T5/T9/T11, §3.2–3.5, 3.7–3.9, 3.11, 3.15, 3.16 y §6 métrica de tareas).
Los Bloques A (quick wins), B (spec 016) y C (sistema de diseño) ya están en
`develop`; esta spec los usa y no los repite.

Un partner que ya puede dejar a un cliente atendiendo (spec 016) sigue teniendo
que **aprender la consola** para hacerlo: la ficha de cliente son diez pestañas
planas, la décima fuera de pantalla en un portátil, con «Eliminar» en rojo en la
cabecera de un cliente recién activado y sin el cupo a la vista (para saber
cuánto le queda hay que ir a Consumo y buscar la fila); publicar un cambio de
ajustes son cinco clics porque «Publicar» solo vive en la pestaña Agente;
Herramientas enseña 46 herramientas de todos los sectores con nombre técnico y
descripción en inglés, más un modo «Requiere aprobación» que el agente no
cumple, y Habilidades otras diez de un sector que no es el suyo con «Versión
1779800896557317»; Consumo mezcla cuatro unidades sin conversión y con jerga;
el alta preselecciona la primera plantilla y despliega veintitrés campos antes
de que nadie elija; la portada apila dos listas de tareas; la lista de clientes
enseña la referencia y la zona horaria y no si el cliente está listo; y hay
noventa y cinco ayudas escondidas en `title=` que ni el teclado ni el móvil
alcanzan.

Esta spec rediseña la consola **por flujo y sin perder ningún dato ni acción**:
**el partner encuentra lo que le falta, lo arregla desde donde está y entiende
lo que ve, con las palabras de su negocio.**

Vocabulario: **créditos** es la unidad de consumo; **cupo** es el tope de
créditos de un cliente dentro del saldo del partner; **capacidad** es algo que
el agente sabe hacer (por dentro, una herramienta o una habilidad; en pantalla
no se distingue); **integración** es un sistema externo conectado (WooCommerce,
AgendaPro, Amigable…); **sector** es el tipo de negocio del cliente (el de la
plantilla con la que se sembró su agente); **puesta en marcha** son los cuatro
pasos que separan a un cliente de «atendiendo»: agente, canal, cupo, activo.
**Canal** es cualquier vía por la que el agente atiende a clientes finales:
hoy WhatsApp; Instagram y Messenger llegarán después, y nada en esta spec
nombra WhatsApp donde cabe «canal».

Depende de las specs **016** (WhatsApp, «sin cupo», etapas del alta, modelo,
AgendaPro), **005** (crédito comprado y su precio), **004** (medidor y cupo por
cliente) y del Bloque C (los bloques `Meter`, `Checklist`, `Stepper`, `Section`,
`Callout`, `Field`, `DescriptionList`, `HelpHint`, `DraftBadge` existen).

## Encabezado Auphere *(obligatorio)*

| Campo | Valor |
|---|---|
| **Superficie de confianza** | **`0`** — API de la consola. No abre ninguna clase nueva: todo lo que se muestra o se cambia ya existe como dato o acción de la consola; lo nuevo son vistas agregadas de lo que hay (estado de puesta en marcha en la lista, conversaciones de los últimos 7 días por cliente, capacidades agrupadas y filtradas por sector, equivalencias del crédito) y un glosario |
| **Garantías de aislamiento tocadas** | **1. Postgres RLS** — el estado de puesta en marcha, el cupo restante, el borrador pendiente y las capacidades de un cliente son por tenant dentro de un partner; ninguna vista agregada (lista, portada, reparto) enseña un cliente de otro partner · **2. Tool whitelist por agente** — «Capacidades» enciende o apaga herramientas y habilidades **solo para ese tenant**; el filtro por sector es una vista sobre el catálogo, **no** un permiso ni un recorte del catálogo |
| **Nota de KB que la justifica** | `[[nexus/PLAN-ACCION-CONSOLA-2026-09-22]]` (Bloque D y decisiones 3, 4, 5) y `[[nexus/AUDITORIA-UX-CONSOLA-2026-09-22]]`, en `/Users/matos/workspace/kb/Auphere/nexus/` |
| **Qué se mide** | **Nada nuevo.** Los turnos siguen entrando en el medidor de la spec 004 y el crédito en el de la 005. «Créditos» es el nombre en pantalla de la unidad que ya se descuenta y una **conversión** a USD y a mensajes aproximados; no es una unidad nueva de cobro ni cambia ningún precio |

## Clarificaciones

### Sesión 2026-09-24

- Q: Al activar o desactivar una capacidad con un clic, ¿se guarda en el borrador en ese clic o se acumulan cambios hasta «Guardar»? → A: **Cada clic guarda en el borrador al instante**; no hay botón «Guardar» en Capacidades; publicar sigue exigiendo confirmación (R5.4).
- Q: ¿El paso «Canal» del alta desaparece o se mantiene un paso que conecta WhatsApp? → A: **Desaparece, y el canal no se llama WhatsApp**: el paso de puesta en marcha es «Conectar un canal» (hoy solo WhatsApp; Instagram y Messenger vendrán en otra spec) y la consola guía al partner a conectarlo para que el agente pueda atender (R1.1, R7.4, R7.5, R8.1).
- Q: «Ver diferencias» en la barra de borrador, ¿por pantalla o solo la comparación del prompt? → A: **Por pantalla, con las palabras de cada pantalla**; el prompt completo queda como detalle plegado (R3.2).

## Escenarios de usuario y pruebas *(obligatorio)*

### Historia 1 — La ficha dice qué le falta al cliente y lo arregla desde ahí (Prioridad: P1)

Un partner abre un cliente y, sin hacer nada más, ve en la cabecera si está
atendiendo y, si no, **cuál de los cuatro pasos** le falta (agente · canal ·
cupo · activo) con un solo botón que lleva a resolver **el primero**. Ve cuánto
cupo le queda como una barra, no como un número que hay que buscar en otra
página. La navegación tiene tres grupos con nombre —**Configurar**, **Conectar**,
**Observar**— y cada persona ve solo las pestañas que su rol puede usar. Las
acciones que cambian el estado del cliente (pausar, reactivar, archivar,
eliminar) viven en un menú «Más», y «Eliminar» solo aparece cuando el cliente
ya está archivado.

**Por qué esta prioridad**: es la pantalla en la que un partner pasa casi todo
su tiempo y la que hoy le exige aprender la consola. Todo lo demás cuelga de
aquí. El plan la fija como primera iteración.

**Prueba independiente**: con un cliente al que le falta el canal, abrir la
ficha con un rol de `builder` y con uno de `analyst`; comprobar que la cabecera
dice «falta el canal» y que el botón lleva a Canales, que el cupo aparece en la
cabecera, que el builder ve Configurar y Conectar y el analyst no ve nada que
no pueda usar, y que «Eliminar» no existe hasta archivar.

**Escenarios de aceptación**:

1. **Dado** un cliente con agente publicado y sin canal, **cuando** el partner abre su ficha, **entonces** la cabecera muestra los cuatro pasos con «canal» como el primero pendiente y un botón «Conectar un canal» que lleva a Canales, donde hoy el único canal es WhatsApp.
2. **Dado** un cliente con un tope de 5 000 créditos y 1 200 gastados, **cuando** el partner abre cualquier pestaña de la ficha, **entonces** ve «3 800 de 5 000 créditos» como barra en la cabecera sin haber hecho ningún clic.
3. **Dado** un usuario con rol `analyst`, **cuando** abre la ficha, **entonces** ve Observar y las pestañas de solo lectura de Configurar y Conectar, y ninguna acción de escritura ni el menú «Más».
4. **Dado** un cliente activo, **cuando** el partner abre «Más», **entonces** ve Pausar y Archivar y **no** ve Eliminar; **cuando** el cliente está archivado, **entonces** ve Reactivar y Eliminar.
5. **Dado** un portátil de 1 061 px de ancho, **cuando** el partner abre la ficha, **entonces** los tres grupos y todas sus pestañas se ven sin desplazamiento horizontal.

---

### Historia 2 — Publicar desde cualquier sitio (Prioridad: P1)

Un partner cambia el horario en Ajustes, o activa una capacidad, y guarda. En
cualquier pestaña de ese cliente aparece una **barra de borrador** que dice qué
pantallas tienen cambios sin publicar, permite **ver las diferencias** y
**publicar** con una confirmación. Publicar cuesta dos clics desde donde está,
no cinco pasando por otra pestaña.

**Por qué esta prioridad**: publicar es la acción con la que el agente empieza
a comportarse como el partner quiere; hoy es la más escondida (cinco clics y un
toast que se va).

**Prueba independiente**: guardar un cambio en Ajustes, ir a Capacidades y
comprobar que la barra sigue ahí y publica; comprobar que tras publicar la barra
desaparece y el historial de versiones muestra la nueva como activa.

**Escenarios de aceptación**:

1. **Dado** un cliente sin borrador, **cuando** el partner guarda un cambio en Ajustes, **entonces** en todas las pestañas del cliente aparece la barra «Cambios sin publicar en Ajustes · Ver diferencias · Publicar».
2. **Dado** un borrador con cambios en Ajustes y en Capacidades, **cuando** el partner pulsa «Ver diferencias», **entonces** ve qué cambió en cada una respecto a la versión activa, con las palabras de la pantalla (no el texto del prompt sin más).
3. **Dado** la barra visible, **cuando** el partner pulsa «Publicar» y confirma, **entonces** la versión pasa a activa, la barra desaparece y Agente muestra el historial con la versión nueva arriba.
4. **Dado** un usuario sin permiso de publicar, **cuando** hay borrador, **entonces** la barra dice que hay cambios sin publicar y quién puede publicarlos, y no ofrece el botón.

---

### Historia 3 — Integraciones primero, capacidades en el idioma del negocio (Prioridad: P2)

Un partner con una panadería entra en la pestaña de capacidades y ve primero
sus **integraciones** (qué sistema externo puede conectar, qué le da, «Conectar»)
y debajo las **capacidades** de su agente agrupadas por función —Citas, Pedidos,
Mensajes, Escalado…— con nombres de negocio, descripción en su idioma y solo
las de su sector, con un buscador, «recomendadas para tu sector» y **un clic**
para activar o desactivar. «Ver todas» descubre el resto del catálogo. Lo
técnico (nombre interno, si es herramienta o habilidad, versión) es un detalle
plegado, no el título.

**Por qué esta prioridad**: hoy dos pestañas (Herramientas y Habilidades)
enseñan 56 cosas de todos los sectores con nombres técnicos; es donde un partner
externo se pierde (decisión 3 del owner: una sola pantalla, dinámica).

**Prueba independiente**: con un cliente sembrado con la plantilla de panadería,
abrir Capacidades y contar: solo grupos y capacidades de su sector; activar una
con un clic y comprobar que la barra de borrador aparece; conectar WooCommerce
desde arriba y ver cómo las capacidades de Pedidos pasan a utilizables.

**Escenarios de aceptación**:

1. **Dado** un cliente sembrado con la plantilla de panadería, **cuando** el partner abre Capacidades, **entonces** ve solo las capacidades de ese sector, agrupadas por función, sin ninguna etiqueta de otro sector ni nombre interno como título.
2. **Dado** la misma pantalla, **cuando** pulsa «Ver todas», **entonces** aparecen las capacidades de los demás sectores, marcadas como fuera de su sector, y siguen siendo activables.
3. **Dado** una capacidad apagada, **cuando** el partner la activa con un clic, **entonces** queda activa en el borrador sin ningún «Guardar» adicional y la barra de borrador lo refleja.
4. **Dado** una capacidad que necesita una integración no conectada, **cuando** el partner la mira, **entonces** la tarjeta dice qué integración le falta y enlaza a conectarla arriba, y **no** la ofrece como utilizable.
5. **Dado** cualquier capacidad, **cuando** el partner la mira, **entonces** no existe ninguna opción «Requiere aprobación».
6. **Dado** un partner que busca «reserva», **cuando** escribe en el buscador, **entonces** ve las capacidades cuyo nombre de negocio o descripción lo contienen, también las de fuera de su sector si «Ver todas» está activo.

---

### Historia 4 — El consumo se entiende en créditos (Prioridad: P2)

Un partner abre Consumo y ve **tres bloques** en este orden: **Saldo** (lo que
le queda, incluido y comprado, con su caducidad, el botón de comprar y las
alertas plegadas), **Reparto por cliente** (una barra por cliente con su cupo y
lo que le queda; editar un tope o mover cupo entre dos clientes ocurre en un
diálogo) y **Consumo** (qué se gastó, por cliente y por tipo, con etiquetas
humanas). Todo en **créditos**, con la equivalencia aproximada en USD y en
mensajes como segunda línea, nunca como cifra principal.

**Por qué esta prioridad**: el dinero es lo segundo que un partner quiere
entender y hoy hay cuatro unidades sin relación (decisión 4 del owner).

**Prueba independiente**: con un partner con saldo y tres clientes, abrir
Consumo y comprobar el orden de bloques, que cada cifra principal está en
créditos con su equivalencia, que mover cupo se hace en un diálogo y que la
tabla no muestra ningún nombre interno de medidor.

**Escenarios de aceptación**:

1. **Dado** un partner con 20 000 créditos incluidos y 5 000 comprados, **cuando** abre Consumo, **entonces** el primer bloque dice «25 000 créditos» con la caducidad del incluido y, debajo, «≈ X USD · ≈ Y mensajes».
2. **Dado** tres clientes con tope, **cuando** mira Reparto por cliente, **entonces** ve una barra por cliente con «restante de tope» y un botón por fila para editar el tope o mover cupo, ambos en un diálogo.
3. **Dado** la tabla de consumo, **cuando** la lee, **entonces** cada fila dice «Mensajes», «Modelo», «Multimedia» o «Voz», nunca `channel.message` ni `llm.*`.
4. **Dado** las alertas de consumo, **cuando** el partner las quiere ajustar, **entonces** las despliega dentro de Saldo sin cambiar de página.
5. **Dado** un partner cuyo saldo no se ha podido leer, **cuando** abre Consumo, **entonces** Saldo dice que no se pudo leer y ofrece reintentar, y los otros dos bloques siguen mostrando lo que sí se sabe.

---

### Historia 5 — Crear un cliente cuesta lo que debe (Prioridad: P2)

Un partner crea un cliente escribiendo solo el **nombre** (la zona horaria
viene propuesta; la referencia queda en «Avanzado»), elige el **sector** entre
tarjetas con una frase («Restaurante: reservas y consultas de carta») sin que
haya ninguna preseleccionada, rellena solo los datos que esa plantilla pide con
los obligatorios primero, revisa y lanza. El alta termina **en la ficha del
cliente**, con «Conectar un canal» como siguiente paso a la vista.

**Por qué esta prioridad**: es el primer minuto de cada cliente nuevo; hoy la
preselección abre veintitrés campos y el paso de canal promete lo que no hace.

**Prueba independiente**: crear un cliente contando clics y campos (objetivo: 4
clics, 1 campo, 2 campos de plantilla) y comprobar que termina en la ficha con
«Conectar un canal» como acción.

**Escenarios de aceptación**:

1. **Dado** el paso 1, **cuando** el partner lo abre, **entonces** ve Nombre y Zona horaria (propuesta desde su navegador) y la referencia solo si despliega «Avanzado».
2. **Dado** el paso 2, **cuando** el partner lo abre, **entonces** ninguna plantilla está elegida, cada tarjeta muestra el sector y una frase, y no aparece ningún identificador técnico ni recuento de herramientas.
3. **Dado** una plantilla elegida con 2 datos obligatorios y 11 opcionales, **cuando** el partner sigue, **entonces** ve los 2 obligatorios primero y los opcionales plegados.
4. **Dado** el alta lanzada, **cuando** todas las etapas terminan, **entonces** el partner está en la ficha del cliente y la cabecera señala «Conectar un canal» como siguiente paso.
5. **Dado** el alta, **cuando** el partner la recorre, **entonces** no existe un paso «Canal» que le pida elegir nada.

---

### Historia 6 — La portada y la lista dicen qué falta (Prioridad: P3)

En la portada hay **una sola** tarjeta «Ponte en marcha» con lo que le falta al
partner y la acción de cada cosa; «Tu puesto de trabajo» solo aparece si su
plan tiene teammates; las métricas tienen etiquetas normales y una línea de
contexto solo cuando aporta. La lista de clientes enseña **Nombre · Puesta en
marcha (agente · canal · cupo) · Cupo restante · Conversaciones de 7 días ·
Actualizado**, cada fila entera es un enlace, y la referencia se queda en la
ficha.

**Por qué esta prioridad**: son las dos pantallas de «¿qué tengo que hacer
hoy?»; hoy responden con dos listas y con datos que no ayudan a decidir.

**Prueba independiente**: con un partner nuevo, abrir la portada y ver una
tarjeta; con tres clientes en distintos estados, abrir la lista y leer de un
vistazo cuál está listo y cuánto cupo le queda.

**Escenarios de aceptación**:

1. **Dado** un partner con plan sin teammates, **cuando** abre la portada, **entonces** ve «Ponte en marcha» y no ve «Tu puesto de trabajo».
2. **Dado** un partner que ya conectó un canal de cliente final, **cuando** mira «Ponte en marcha», **entonces** «Conecta un canal» está hecho; **dado** que solo usó el Playground, **entonces** **no** lo está.
3. **Dado** tres clientes (listo, sin canal, sin cupo), **cuando** el partner abre la lista, **entonces** cada fila muestra los tres puntos de puesta en marcha y la barra de cupo, y pulsar en cualquier parte de la fila abre la ficha.
4. **Dado** la lista, **cuando** el partner la lee, **entonces** no ve la referencia ni la zona horaria como columnas.

---

### Historia 7 — Los ajustes del agente se leen por secciones (Prioridad: P3)

Ajustes del agente son secciones plegables con un resumen en la cabecera de
cada una («Horario: atiende siempre», «Idiomas: español»), un índice lateral
para saltar entre ellas, un pie fijo con Guardar, selectores con nombres en vez
de códigos, contador de caracteres en los textos largos y «Atiende siempre»
como estado explícito del horario.

**Por qué esta prioridad**: un formulario único de siete secciones se puede
usar; se usa mal. Va después de lo que impide o engaña.

**Prueba independiente**: abrir Ajustes sin tocar nada y leer el resumen de
cada sección; cambiar el idioma con un selector de nombres; comprobar que sin
franjas el horario dice «Atiende siempre» y no «Cerrado».

**Escenarios de aceptación**:

1. **Dado** un agente sin franjas horarias, **cuando** el partner abre Ajustes, **entonces** la sección Horario está plegada con el resumen «Atiende siempre» y al abrirla ese estado está marcado.
2. **Dado** el selector de zona horaria, **cuando** el partner lo abre, **entonces** ve nombres de ciudad o región, no identificadores técnicos; lo mismo con los idiomas.
3. **Dado** un texto con tope de 2 000 caracteres, **cuando** el partner escribe, **entonces** ve cuántos le quedan.
4. **Dado** cualquier sección abierta, **cuando** el partner baja por la página, **entonces** Guardar sigue visible.

---

### Historia 8 — Las palabras son las del negocio, y la ayuda se alcanza (Prioridad: P3)

En toda la consola, cada término que un partner externo no tiene por qué
conocer lleva una ayuda accesible con teclado y táctil, y existe una página de
glosario. El Playground nunca muestra un turno fallido como completado, los
hilos se llaman por su fecha y el presupuesto de pruebas es una línea. Ajustes
del cliente tiene «Datos» (con la referencia copiable) y «Zona de peligro»;
Facturación permite cambiar el correo; Notificaciones y Auditoría hablan en
títulos de negocio y Auditoría se filtra por categoría.

**Por qué esta prioridad**: es transversal y de pulido; cada pantalla lo
incorpora en su iteración y esta historia recoge lo que no cabe en las otras.

**Prueba independiente**: recorrer las vistas principales con teclado y abrir
cada ayuda; abrir `/ayuda` y encontrar «cupo», «créditos», «capacidad»,
«integración», «sector», «borrador»; provocar un turno fallido en el Playground
y leer la causa.

**Escenarios de aceptación**:

1. **Dado** un término con ayuda, **cuando** el partner llega a él con Tab y pulsa Enter, o lo toca en un móvil, **entonces** la ayuda se muestra; **cuando** no hace nada, **entonces** no hay ninguna ayuda que solo aparezca al pasar el ratón.
2. **Dado** un turno del Playground que falló, **cuando** el partner lo mira, **entonces** ve «Error» con la causa en una frase y un botón de reintentar, y nunca «Completado · 0 tokens».
3. **Dado** Auditoría, **cuando** el partner elige la categoría «Clientes», **entonces** solo ve acciones de esa categoría, con sus títulos de negocio.
4. **Dado** Ajustes del cliente, **cuando** el partner los abre, **entonces** ve la referencia con un botón de copiar en «Datos» y las acciones destructivas solo en «Zona de peligro».

---

### Casos límite

- ¿Qué pasa cuando un cliente no fue sembrado con ninguna plantilla (agente escrito a mano)? Capacidades no tiene sector: enseña todo el catálogo agrupado por función y lo dice en una línea («Este cliente no tiene sector; se muestran todas las capacidades»); no existe «recomendadas».
- ¿Qué pasa cuando el sector del cliente ya no tiene plantilla en el catálogo? Se conserva el sector guardado, se filtra por él y, si no queda nada, se muestra todo con la misma línea.
- ¿Qué pasa cuando hay borrador y otra persona publica desde otra sesión? La barra desaparece en la siguiente lectura y no vuelve a ofrecer publicar lo que ya está activo; si el partner tenía el diálogo de publicar abierto, se le dice que ya se publicó.
- ¿Qué pasa cuando el saldo no se puede leer? Saldo lo dice y reintenta; Reparto y Consumo se muestran (spec 016, R2); ninguna equivalencia se inventa: «≈ —».
- ¿Qué pasa cuando no hay historial de consumo para estimar mensajes? La equivalencia en mensajes usa el valor de referencia de la plataforma y lo dice («estimación general»).
- ¿Qué pasa con el cupo en la cabecera si el cliente no tiene tope? La barra no se pinta: se dice «Sin tope: consume del saldo del partner» (spec 016, R2.5).
- ¿Qué ve un `billing` que abre la URL de una ficha? No puede leer clientes: la respuesta es la de hoy (redirección a la portada), sin una ficha vacía.
- ¿Qué pasa en la lista cuando un cliente tiene más de 999 conversaciones en 7 días? Se muestra la cifra completa con separador de miles, sin recortar.
- ¿Qué pasa con las pestañas cuando un rol solo puede leer un grupo entero? El grupo se muestra igual, con las pestañas en solo lectura; un grupo sin ninguna pestaña legible no se pinta.
- ¿Qué ve el usuario cuando una capacidad **no está disponible**? Hoy solo hay dos motivos: no es de su sector (no aparece por defecto; en «Ver todas» aparece marcada y sigue siendo activable) o necesita una integración no conectada (aparece con «Necesita {integración} · Conectar» y sin conmutador). No hay tarjeta apagada (constitución §V: la ausencia se diseña). Capacidades por plan no existen; si algún día existen, son otra spec.
- ¿Qué pasa a 360 px? Los tres grupos de la ficha se convierten en un selector; la barra de borrador se queda pegada abajo; Reparto por cliente apila la barra bajo el nombre; nada desborda.

## Requisitos *(obligatorio)*

### Requisito 1 — La cabecera de la ficha dice qué falta y lo resuelve

**Historia de usuario:** Como partner, quiero ver de un vistazo si mi cliente está atendiendo, qué le falta y cuánto cupo le queda, y arreglar lo primero que falte desde ahí, para no aprenderme dónde vive cada cosa.

#### Criterios de aceptación

1. WHEN se abre cualquier pestaña de un cliente THEN la cabecera DEBE mostrar los cuatro pasos de puesta en marcha (agente · canal · cupo · activo) con el estado de cada uno, y DEBE mostrar un único botón con la acción del **primer** paso pendiente que el rol pueda ejecutar.
2. WHERE el cliente tiene tope EL sistema DEBE mostrar en la cabecera el cupo restante como barra con «restante de tope» en créditos; WHERE no tiene tope DEBE decir que consume del saldo del partner.
3. WHEN el cliente está atendiendo (los cuatro pasos hechos) THEN la cabecera DEBE decirlo en una línea y NO DEBE ofrecer ningún botón de puesta en marcha.
4. El sistema DEBE agrupar las acciones de ciclo de vida (pausar, reactivar, archivar, eliminar) en un menú «Más» de la cabecera, visible solo para quien tiene permiso de escritura sobre clientes.
5. IF el cliente no está archivado THEN el menú NO DEBE ofrecer «Eliminar»; WHEN está archivado THEN DEBE ofrecerlo con la confirmación por nombre que ya existe.
6. El sistema DEBE mostrar en la cabecera el nombre, el estado y el teléfono conectado si lo hay; la referencia y la zona horaria DEBEN vivir en Ajustes del cliente y no en la cabecera.

### Requisito 2 — La navegación de la ficha tiene tres grupos y respeta el rol

**Historia de usuario:** Como partner con un rol concreto, quiero que la ficha me enseñe solo lo que puedo usar, ordenado por lo que hago (configurar, conectar, observar), para no ver diez pestañas iguales.

#### Criterios de aceptación

1. El sistema DEBE organizar la ficha en tres grupos con nombre: **Configurar** (Agente, Ajustes, Capacidades, Conocimiento), **Conectar** (Canales, Integraciones, Puesto de trabajo) y **Observar** (Resumen, Conversaciones, Playground).
2. WHEN un rol no puede leer una pestaña THEN el sistema NO DEBE mostrarla; WHEN un rol solo puede leerla THEN DEBE mostrarla sin acciones de escritura; IF un grupo se queda sin pestañas THEN NO DEBE pintarse.
3. WHILE el ancho es de 1 024 px o más EL sistema DEBE mostrar los tres grupos y todas sus pestañas sin desplazamiento horizontal; WHILE es menor DEBE ofrecer la misma navegación en un control compacto accesible con teclado.
4. WHEN el partner está en una pestaña THEN el sistema DEBE marcarla como actual para el lector de pantalla y visualmente, y DEBE mantener el grupo abierto.
5. WHEN un partner abre la ficha por su URL raíz THEN el sistema DEBE mostrar Resumen sin redirigir de forma visible.

### Requisito 3 — El borrador se ve y se publica desde cualquier pestaña

**Historia de usuario:** Como partner, quiero saber desde cualquier pestaña del cliente que tengo cambios sin publicar, ver qué cambió y publicarlo ahí mismo, para que publicar cueste dos clics.

#### Criterios de aceptación

1. WHILE existe un borrador para el cliente EL sistema DEBE mostrar en todas sus pestañas una barra que nombre las pantallas con cambios («Ajustes», «Capacidades», «Conocimiento», «Agente») y ofrezca «Ver diferencias» y «Publicar».
2. WHEN el partner pulsa «Ver diferencias» THEN el sistema DEBE mostrar, pantalla por pantalla, qué cambió respecto a la versión activa con las palabras de esa pantalla; el texto completo del prompt DEBE quedar disponible como detalle, no como primera vista.
3. WHEN el partner pulsa «Publicar» y confirma THEN el sistema DEBE publicar el borrador con las mismas reglas que hoy en Agente (confirmación, permiso `agents:write`, rastro de auditoría) y la barra DEBE desaparecer.
4. IF el rol no puede publicar THEN la barra DEBE decir que hay cambios sin publicar y qué roles pueden publicarlos, y NO DEBE mostrar el botón.
5. WHEN una pantalla guarda un borrador THEN el sistema NO DEBE depender de un aviso temporal (toast) para ofrecer publicar; el toast puede confirmar el guardado.
6. El sistema DEBE mostrar en Agente las versiones como historial (fecha, quién, qué cambió, activa/borrador) con revertir confirmado, sin quitar ninguna acción que exista hoy.

### Requisito 4 — Integraciones van primero y se conectan desde arriba

**Historia de usuario:** Como partner, quiero ver qué sistemas de mi cliente puedo conectar y conectarlos antes de ver qué sabe hacer el agente, porque muchas capacidades dependen de eso.

#### Criterios de aceptación

1. El sistema DEBE mostrar las integraciones como pestaña propia dentro de **Conectar**, y como bloque superior de Capacidades cuando alguna capacidad visible dependa de una integración no conectada.
2. WHEN el partner mira una integración THEN DEBE ver qué es, qué permite (las funciones que desbloquea, en lenguaje de negocio), su estado y la acción que toca (Conectar, Enlazar, Reconectar, Desconectar), con las mismas reglas de la spec 016 (sincroniza sola, campos traducidos, AgendaPro por URL pública).
3. WHEN una integración se conecta THEN las capacidades que dependían de ella DEBEN pasar a utilizables en la misma vista sin recargar a mano.

### Requisito 5 — Capacidades: una sola pantalla, por función y por sector

**Historia de usuario:** Como partner, quiero ver lo que mi agente sabe hacer con los nombres de mi negocio, solo lo de mi sector, y activarlo con un clic, para no distinguir herramientas de habilidades ni leer nombres internos.

#### Criterios de aceptación

1. El sistema DEBE presentar herramientas y habilidades en una única pestaña «Capacidades», agrupadas por función (Citas, Pedidos, Mensajes, Escalado, Conocimiento, Otras…), cada una con nombre de negocio y descripción en el idioma del partner.
2. WHEN el cliente tiene sector THEN la vista por defecto DEBE mostrar solo las capacidades de ese sector y las comunes a todos, y DEBE ofrecer «Ver todas»; WHEN no tiene sector THEN DEBE mostrar todo y decirlo.
3. El sistema DEBE marcar como «recomendadas para tu sector» las capacidades que la plantilla del sector activa por defecto.
4. WHEN el partner activa o desactiva una capacidad THEN el sistema DEBE guardar el cambio en el borrador con ese clic, sin un «Guardar» aparte, y la barra de borrador DEBE reflejarlo; IF el rol no puede escribir THEN el conmutador NO DEBE existir y el estado DEBE leerse igual.
5. WHEN el partner escribe en el buscador THEN el sistema DEBE filtrar por nombre de negocio y descripción dentro de la vista actual (sector o todas).
6. El sistema DEBE mostrar el nombre interno, el tipo (herramienta o habilidad), la versión como fecha y las etiquetas técnicas solo como detalle plegado de cada capacidad.
7. El sistema NO DEBE ofrecer ningún modo «Requiere aprobación»; los modos que el agente cumple hoy (siempre, nunca) DEBEN seguir disponibles con sus nombres, y una capacidad marcada con «requiere aprobación» en una versión anterior DEBE mostrarse con el modo efectivo real.
8. WHEN una capacidad necesita una integración no conectada THEN la tarjeta DEBE decir cuál y enlazar a conectarla, y NO DEBE contarse como utilizable.
9. El sistema DEBE conservar todo lo que hoy se puede hacer en Herramientas y Habilidades: marcar y desmarcar, marcar y desmarcar todas las visibles, cambiar el modo, ver si está en la versión activa, conectar/desconectar/sincronizar integraciones.

### Requisito 6 — El consumo se cuenta en créditos y se lee en tres bloques

**Historia de usuario:** Como partner, quiero entender cuánto me queda, cómo lo tengo repartido y en qué se ha ido, en una sola unidad y con las palabras de mi negocio.

#### Criterios de aceptación

1. El sistema DEBE ordenar Consumo en tres bloques: **Saldo**, **Reparto por cliente** y **Consumo**, en ese orden, y DEBE integrar la compra de crédito y las alertas dentro de Saldo (las alertas plegadas por defecto).
2. Toda cifra principal DEBE estar en créditos; WHERE haya equivalencia EL sistema DEBE mostrarla como segunda línea «≈ USD · ≈ mensajes» marcada como aproximada, y NO DEBE mostrar tokens, unidades ni nombres de medidor como cifra principal.
3. WHEN el partner mira Reparto por cliente THEN DEBE ver por cliente el tope, lo consumido y lo restante como barra, el estado «sin cupo» si aplica, y una acción por fila que abre un diálogo para editar el tope o mover cupo a otro cliente (una sola operación, spec 016 R3).
4. WHEN el partner mira Consumo THEN la tabla y las gráficas DEBEN usar etiquetas humanas para cada medidor y fuente, y DEBEN poder filtrarse por cliente, tipo y periodo como hoy.
5. IF el saldo no se puede leer THEN Saldo DEBE decirlo y ofrecer reintentar, y los otros bloques DEBEN seguir; ninguna equivalencia DEBE inventarse.
6. El sistema DEBE conservar todo lo que hoy se puede hacer en Consumo y Alertas: comprar crédito, ver incluido/comprado/reserva, asignar cupo a un cliente sin asignación, editar topes, mover cupo, ajustar umbrales y destinatarios de alertas, ver totales, gráficas y detalle por registro.

### Requisito 7 — El alta pide lo justo y termina en la ficha

**Historia de usuario:** Como partner, quiero crear un cliente con lo mínimo y que el alta me deje donde sigue el trabajo.

#### Criterios de aceptación

1. WHEN el partner abre el paso 1 THEN DEBE ver Nombre y Zona horaria (propuesta) y la referencia solo dentro de «Avanzado», editable y con la misma validación de hoy.
2. WHEN abre el paso 2 THEN ninguna plantilla DEBE estar elegida; cada tarjeta DEBE mostrar el sector y una frase, y NO DEBE mostrar identificadores técnicos ni recuentos de herramientas.
3. WHEN elige una plantilla THEN el sistema DEBE pedir sus datos con los obligatorios primero y los opcionales plegados, y NO DEBE pedir ninguno antes de elegir.
4. El sistema NO DEBE tener un paso de canal; la revisión DEBE mantener «Publicar y activar» como opción con las etapas visibles y reintentables de la spec 016.
5. WHEN todas las etapas terminan THEN el sistema DEBE llevar al partner a la ficha del cliente, cuya cabecera señala el siguiente paso pendiente (normalmente «Conectar un canal»); la pestaña Canales DEBE listar los canales disponibles con su acción, de modo que añadir Instagram o Messenger mañana no cambie la ficha ni el alta.
6. El sistema DEBE conservar la guardia de salida con cambios y el cierre por cuota de clientes que existen hoy.

### Requisito 8 — La portada tiene una lista de tareas, no dos

**Historia de usuario:** Como partner, quiero abrir la consola y ver qué me falta y qué está pasando, sin repetir listas ni rótulos.

#### Criterios de aceptación

1. El sistema DEBE mostrar una única tarjeta «Ponte en marcha» con los pasos pendientes del partner y una acción por paso que lleve al control real («Conectar un canal» lleva a la pestaña Canales del cliente, con la acción de cada canal disponible).
2. WHERE el plan del partner incluye teammates EL sistema DEBE mostrar «Tu puesto de trabajo» como parte de la misma tarjeta o justo debajo; WHERE no los incluye NO DEBE mostrarla.
3. La puesta en marcha DEBE contar como canal solo canales de cliente final y como conversación solo las de canal; el Playground NO DEBE marcar ningún paso.
4. Las métricas DEBEN llevar etiqueta en texto normal y una línea de contexto solo cuando añada información; NO DEBEN mostrar tiempos de cálculo.
5. WHEN un partner tiene clientes con incidencias THEN la portada DEBE decirlo con el cliente y su acción, como hoy.

### Requisito 9 — La lista de clientes dice quién está listo

**Historia de usuario:** Como partner, quiero ver en la lista cuál de mis clientes está listo y cuánto cupo le queda, sin entrar en cada uno.

#### Criterios de aceptación

1. La lista DEBE mostrar por cliente: Nombre, Puesta en marcha (agente · canal · cupo como tres puntos con nombre), Cupo restante como barra, Conversaciones de los últimos 7 días y Actualizado.
2. WHEN el partner pulsa en cualquier parte de la fila THEN DEBE abrirse la ficha; el nombre DEBE seguir siendo un enlace para el lector de pantalla.
3. La lista NO DEBE mostrar la referencia ni la zona horaria como columnas; la búsqueda DEBE seguir encontrando por referencia.
4. Los filtros por estado DEBEN conservarse y mostrar cuántos clientes hay en cada uno.

### Requisito 10 — Los ajustes del agente se leen por secciones

**Historia de usuario:** Como partner, quiero ver de un vistazo cómo está configurado el agente y cambiar solo lo que toca.

#### Criterios de aceptación

1. El sistema DEBE presentar Ajustes en secciones plegables con un resumen de una línea en cada cabecera, y un índice lateral (o superior en pantallas estrechas) que lleve a cada sección.
2. WHILE el partner se desplaza EL sistema DEBE mantener visible Guardar (y el estado de guardado).
3. Los selectores de zona horaria e idiomas DEBEN ofrecer nombres legibles y buscar por ellos; el valor técnico NO DEBE ser lo que se teclea.
4. WHEN un texto tiene tope de caracteres THEN el sistema DEBE mostrar los restantes mientras se escribe.
5. WHERE el horario no tiene franjas EL sistema DEBE mostrar y guardar el estado «Atiende siempre» como opción explícita; NO DEBE mostrar «Cerrado» como valor por defecto.
6. El sistema DEBE conservar todos los campos, validaciones y secciones que existen hoy (identidad, tono, horario, idiomas, escalado, aviso de IA, modelo).

### Requisito 11 — Lenguaje de negocio y ayuda alcanzable en toda la consola

**Historia de usuario:** Como partner externo, quiero entender cada palabra de la consola o poder preguntarle a la propia pantalla.

#### Criterios de aceptación

1. El sistema DEBE ofrecer ayuda contextual accesible por teclado y por toque en cada término de negocio (cupo, créditos, capacidad, integración, sector, borrador, versión, escalado, puesta en marcha…), y NO DEBE usar ayudas que solo aparezcan al pasar el ratón.
2. El sistema DEBE tener una página de glosario en la consola con esos términos, en los idiomas de la consola, enlazada desde cada ayuda.
3. WHEN un turno del Playground falla THEN el sistema DEBE mostrarlo como error con su causa en una frase y reintento; los hilos DEBEN nombrarse por fecha cuando no tengan nombre; el presupuesto de pruebas DEBE ocupar una línea.
4. Ajustes del cliente DEBE tener «Datos» (nombre, zona horaria, referencia copiable) y «Zona de peligro» (pausar, archivar, eliminar con las reglas de hoy).
5. Facturación DEBE permitir cambiar el correo de facturación; Notificaciones y Auditoría DEBEN usar títulos de negocio para cada evento y acción; Auditoría DEBE filtrarse por categoría.
6. Ningún rótulo de sección, métrica, menú o tarjeta DEBE ir en monoespaciado; el monoespaciado DEBE reservarse a identificadores copiables y código.

### Requisito 12 — Nada desaparece y cada pantalla se aprueba antes de salir

**Historia de usuario:** Como owner, quiero que el rediseño no pierda ningún dato ni acción y poder ver cada pantalla antes de que llegue a staging.

#### Criterios de aceptación

1. El sistema (la spec, en su carpeta) DEBE incluir una tabla de paridad, campo a campo y acción a acción, **antes → después**, para cada pantalla tocada; cada fila DEBE decir «se conserva», «se mueve a …» o «se retira porque …», y ninguna fila DEBE retirar algo sin una decisión escrita del owner.
2. WHEN una iteración termina THEN el recorrido completo (crear cliente → cupo → agente → integraciones → operativo) DEBE seguir en verde en local y en staging.
3. WHEN una iteración termina THEN la suite de accesibilidad automática DEBE estar en verde en las vistas tocadas, en los dos idiomas, a 360 y 1 920 px, sin desbordamiento con un 30 % más de texto.
4. El trabajo DEBE entregarse por pantallas, una por iteración, empezando por la ficha (R1–R3), y cada pantalla DEBE tener un prototipo revisado y aprobado por el owner antes de implementarse.
5. Cada iteración DEBE dejar la consola usable de punta a punta: una pantalla nueva y una vieja DEBEN poder convivir sin enlaces rotos.

### Entidades clave *(si la feature toca datos)*

- **Estado de puesta en marcha**: los cuatro pasos (agente · canal · cupo · activo) de un cliente y cuál es el primero pendiente; deriva de datos que ya existen (versión activa, canal de cliente final activo, cupo, estado del cliente). Pertenece al tenant del cliente; la RLS lo alcanza por `tenant_id` y el partner por su pertenencia.
- **Borrador pendiente**: la versión no publicada de la configuración del agente de un cliente y qué pantallas la tocaron. Por tenant. Existe hoy; lo nuevo es exponer «qué cambió, por pantalla».
- **Capacidad**: la vista unificada de una herramienta o una habilidad del catálogo para un cliente: nombre de negocio, función, sector(es), descripción traducida, si está activa en el borrador y en la versión activa, la integración de la que depende, el modo efectivo. El catálogo es común a todos los partners; **el estado de activación es por tenant** (lista blanca del agente).
- **Sector del cliente**: el sector de la plantilla con la que se sembró su agente, guardado con el agente; puede no existir. Por tenant.
- **Saldo y reparto**: el saldo del partner (incluido, comprado, caducidad) y los topes por cliente con lo consumido y lo restante; existen (specs 004, 005, 016). Por partner y por tenant respectivamente.
- **Equivalencia**: la conversión de créditos a USD (precio de compra vigente) y a mensajes aproximados (media reciente del partner o valor de referencia); es una lectura, no se guarda.
- **Glosario**: términos y definiciones en los idiomas de la consola; contenido del producto, no del partner.

## Criterios de éxito *(obligatorio)*

- **CE-001**: el partner ve cuánto cupo le queda a un cliente con **0 clics** desde cualquier pestaña de su ficha (hoy 3).
- **CE-002**: publicar un cambio de ajustes cuesta **2 clics** desde la pantalla donde se hizo (hoy 5).
- **CE-003**: crear un cliente con agente publicado cuesta **4 clics + 1 campo + los campos obligatorios de la plantilla (2 en la de panadería, la de `panaderia-la-espiga` del quickstart)**; ningún campo de plantilla aparece antes de elegirla.
- **CE-004**: un cliente de panadería ve por defecto **solo** capacidades de su sector y comunes (ninguna etiqueta de otro sector) y ningún nombre interno como título; con «Ver todas» ve el catálogo completo.
- **CE-005**: la tabla de paridad de cada pantalla tiene el **100 %** de sus filas en «se conserva» o «se mueve a …», o «se retira» con decisión escrita del owner; el recorrido E2E completo sigue en verde tras cada iteración.
- **CE-006**: la suite de accesibilidad automática da **0 violaciones** y **0 desbordamientos** a 360 y 1 920 px, en español e inglés, en todas las vistas tocadas.
- **CE-007**: la ficha muestra los tres grupos y todas sus pestañas **sin desplazamiento horizontal a 1 024 px**.
- **CE-008**: cada iteración se entrega tras un prototipo **aprobado por el owner**, y la consola sigue usable de punta a punta entre iteraciones.
- **CE-009**: no queda ningún rótulo en monoespaciado fuera de identificadores y código, ni ninguna ayuda que dependa del ratón, en las vistas tocadas.

## Fuera de alcance

- **Conmutador de tema y respeto a `prefers-color-scheme`** — ya existe en el menú de usuario (claro, oscuro, sistema) desde el Bloque A; esta spec no lo toca. Solo se exige que las pantallas nuevas se vean bien en los dos temas.
- **Conectar WhatsApp, «sin cupo», etapas del alta, modelo, AgendaPro, conectores por clave** — spec 016, ya entregada; aquí solo se recolocan.
- **Instagram y Messenger como canales** — otra spec; esta deja la ficha, el alta y Canales preparados para listar más de un canal sin cambiar de forma.
- **Nuevos bloques del sistema de diseño** (`NavTabs`, `RowActions`, `Kbd`, densidad por token) — se crean dentro de esta spec como parte de la pantalla que los necesita, sin spec propia; sus reglas están en `console-design-system.md`.
- **Implementar «Requiere aprobación» en el agente** — se retira de la pantalla porque el agente no lo cumple; implementarlo es otra spec.
- **Cambiar precios, la unidad de cobro o la venta de crédito** — spec 005; «créditos» es nombre y conversión.
- **El panel de operador (`/admin`) y la app de escritorio** — no cambian.
- **El Companion (⌘J)** — no cambia; leerá las mismas capacidades.
- **Un editor visual del prompt** — «Ver diferencias» muestra cambios; no edita.

## Supuestos

- **El sector del cliente es el de la plantilla con la que se sembró su agente**, y queda guardado con el agente; un agente escrito a mano no tiene sector.
- **«Recomendadas para tu sector»** son las capacidades que la plantilla del sector activa por defecto.
- **Las funciones** (Citas, Pedidos, Mensajes, Escalado, Conocimiento, Otras) salen de las etiquetas que el catálogo ya trae; una capacidad sin etiqueta de función va a «Otras».
- **La equivalencia en USD** usa el precio de compra de crédito vigente para el partner (spec 005); **la de mensajes** usa la media de créditos por mensaje del propio partner en los últimos 30 días y, sin historial, un valor de referencia de la plataforma, siempre marcada como aproximada.
- **Los grupos de la ficha se filtran con el mapa de permisos que ya existe** (`clients:read`, `agents:read`, `channels:read`, `conversations:read`, `workstation:read`, `playground:run`, `knowledge:read` y sus escrituras); no se crean permisos nuevos.
- **«Plan con teammates»** es un plan cuyo nivel permite al menos un teammate.
- **Las conversaciones de 7 días** por cliente se calculan del mismo modo que las del mes en la portada, acotadas a 7 días.
- **El glosario vive con el resto de textos de la consola** en español e inglés, y lo mantiene el producto.
- **Los prototipos** se revisan en Storybook o como pantalla estática en staging, a criterio del owner, antes de cada iteración.
- **Orden de iteraciones**: ficha (R1–R3), Capacidades e Integraciones (R4–R5), Consumo (R6), alta (R7), portada y lista (R8–R9), Ajustes del agente (R10), transversal (R11). R12 aplica a todas.
