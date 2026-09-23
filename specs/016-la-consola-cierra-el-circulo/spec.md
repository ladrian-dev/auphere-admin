# Especificación: la consola cierra el círculo

**Rama**: `016-la-consola-cierra-el-circulo` · **Creada**: 2026-09-23 · **Estado**: Clarificada — cero marcas abiertas, lista para `/speckit-plan`

**Entrada**: auditoría de la consola de partners (Fase 1, KB
`nexus/INFORME-AUDITORIA-CONSOLA-2026-09-22.md`, tabla E2E filas a, b, c, d1,
d2, d3, e2) y plan aprobado por el owner el 2026-09-23 (KB
`nexus/PLAN-ACCION-CONSOLA-2026-09-22.md`, Bloque B, B1–B8, con las seis
decisiones registradas).

Un partner entra hoy en la consola, crea un cliente en cuatro pasos, le publica
un agente y llega a una pestaña Canales cuyo botón «Conectar WhatsApp» está
deshabilitado con el texto «no disponible en este entorno. Escríbenos». Desde
ese punto ningún cliente llega a «listo»: el agente existe, tiene cuota, y no
tiene por dónde recibir un mensaje. Alrededor de ese hueco hay otros seis que
convierten «activado» en una promesa: mover cupo entre clientes puede perder
cupo, quedarse sin cupo deja al agente mudo sin que el partner lo vea ni lo
sepa, la publicación del wizard es una sola llamada opaca, el modelo del agente
no se puede elegir, el único conector de citas no se puede conectar, y conectar
un conector por clave exige un segundo clic que nadie espera.

Esta spec cierra ese círculo: **un partner deja a un cliente atendiendo de
verdad, y enterándose de lo que le falta, sin que nadie de Auphere intervenga.**

Depende de las specs **004** (medidor y pool semanal: el cupo por cliente y la
puerta `allow_channel_turn` existen), **005** (membresías y cobro: el crédito
se compra de verdad) y del Bloque A del plan (ya en `develop`: las pantallas
dejaron de mentir sobre cupo, Playground y activación).

## Encabezado Auphere *(obligatorio)*

| Campo | Valor |
|---|---|
| **Superficie de confianza** | **`0`** — API de la consola. No abre ninguna clase nueva: todo lo que aquí se pide ya existe como endpoint de operador (`/admin`) o como endpoint de consola sin pantalla. La única pieza nueva de verdad es un endpoint transaccional para mover cupo, dentro de la misma superficie |
| **Garantías de aislamiento tocadas** | **1. Postgres RLS** — el cupo, el estado «sin cupo», el modelo y las credenciales de un conector son por tenant dentro de un partner; mover cupo lee y escribe dos tenants **del mismo partner** en una transacción y no puede alcanzar un tercero · **2. Tool whitelist por agente** — conectar AgendaPro o un conector por clave enciende herramientas del catálogo solo para ese tenant · **4. Acción consecuente con rastro** (constitución §IV) — conectar un canal, mover cupo, cambiar el modelo, enlazar la agenda y conectar un conector son acciones de una persona y la auditoría la nombra · **6. Log + trace tagging** — ninguna clave de conector ni token de Meta aparece en logs ni en la respuesta de la API |
| **Nota de KB que la justifica** | `[[nexus/PLAN-ACCION-CONSOLA-2026-09-22]]` (decisiones del owner del 2026-09-23) y `[[nexus/INFORME-AUDITORIA-CONSOLA-2026-09-22]]`, en `/Users/matos/workspace/kb/Auphere/nexus/` (ruta real del vault; las plantillas citan una antigua) |
| **Qué se mide** | **Nada nuevo.** Los turnos siguen entrando en el medidor de la spec 004 y el crédito en el de la 005. El selector de modelo cambia **qué** se mide por turno (los pesos por carril de la spec 007 ya lo cubren), no si se mide. Las alertas «sin cupo» y los correos que las acompañan se limitan por ritmo (una por cliente y día), no por medidor |

> **Por qué esto no es una superficie nueva.** Conectar WhatsApp por Embedded
> Signup ya funciona desde el panel de operador y desde la API pública de
> partners (`POST /partners/clients/{ref}/whatsapp/signup`); la agenda pública de
> AgendaPro ya se enlaza desde `/admin`; el modelo por cliente ya se lee y
> se escribe por `/console`. Lo que falta es la mitad barata: pantallas y una
> transacción. La constitución §II pide agotar la superficie abierta antes de
> abrir otra, y esto es exactamente eso.

> **Credenciales de un cliente final: ninguna nueva.** La primera versión de esta
> spec preveía que el partner introdujera las credenciales de AgendaPro de su
> cliente. La Fase 0 encontró que ningún runtime del repo las consume: lo que
> atiende citas es la URL pública de reservas. Esta spec **no guarda ninguna
> credencial de cliente final**; las claves de los conectores por API son del
> negocio del cliente (WooCommerce, Amigable) y siguen cifradas y sin lectura de
> vuelta, como hasta ahora.

---

## Clarificaciones

### Sesión 2026-09-23

- **Hallazgo de la Fase 0 que cambia R6 (pendiente de confirmación del owner).** En el repo no existe ningún runtime que use credenciales de AgendaPro: lo que atiende citas hoy es la **URL pública de reservas** del cliente (`tenants.agendapro_public_url`, que fija el operador desde el panel de admin), y el camino «credenciales de navegador» es un seed sin consumidor (nada crea la fila, nada la valida, nada marca «necesita reautorizar»). Guardar credenciales que nada usa sería un botón que promete lo que no hace (§V) y credenciales de cliente final en reposo sin propósito (§III). **Decisión del plan**: R6 se cumple enlazando la URL pública de AgendaPro desde la consola, con auditoría; el formulario de credenciales queda fuera hasta que exista el runtime (spec aparte, superficie `1`). Ver `research.md` R6.
- Barrido completo sin preguntas: las tres dudas de alcance las cerró el owner el 2026-09-23 (alerta al partner sin cambiar el mensaje al cliente final; AgendaPro con las credenciales del cliente desde la consola; unidad «créditos»). Dos dudas menores quedan como supuestos, no como marcas: el rol que conecta AgendaPro es el mismo que conecta los demás conectores (escritura sobre el agente), y «sin cupo» se recalcula a partir del mismo libro que cierra la puerta del canal, no de una copia.

---

## Escenarios de usuario y pruebas *(obligatorio)*

### Historia 1 — Conectar WhatsApp desde la consola (Prioridad: P1)

Un partner con un cliente que ya tiene agente publicado abre Canales, pulsa
«Conectar WhatsApp», completa el registro de Meta con la cuenta del propio
cliente, vuelve a la consola y ve el número conectado, la ficha en «listo» y el
onboarding con «Conecta un canal» hecho. Si en su entorno Meta no está
configurado, no ve un botón apagado: ve que en ese entorno WhatsApp lo conecta
Auphere y cómo pedirlo.

**Por qué esta prioridad**: sin canal no hay cliente atendido. Es el único paso
del flujo end-to-end que hoy es imposible, y bloquea el onboarding y la
métrica «tiempo hasta el primer cliente activo».

**Prueba independiente**: con las claves de Meta de staging, crear un cliente,
publicar, conectar un número de prueba y comprobar que la ficha dice «listo» y
que un mensaje entrante recibe respuesta.

**Escenarios de aceptación**:

1. **Dado** un cliente con agente publicado y sin canal, **cuando** el partner pulsa «Conectar WhatsApp» y completa el registro de Meta, **entonces** el número aparece en Canales como activo, la ficha pasa a «listo» y el onboarding marca «Conecta un canal».
2. **Dado** un entorno sin las claves de Meta, **cuando** el partner abre Canales, **entonces** no hay botón deshabilitado: hay una explicación de que en ese entorno la conexión la hace Auphere y un medio de pedirla.
3. **Dado** que el partner cierra la ventana de Meta a medias, **cuando** vuelve a la consola, **entonces** el cliente sigue sin canal, nada queda a medio guardar y puede volver a intentarlo.
4. **Dado** un rol sin permiso de escritura en canales, **cuando** abre Canales, **entonces** no ve la acción de conectar.

---

### Historia 2 — Ver y resolver «sin cupo» sin que nadie llame (Prioridad: P1)

Un cliente agota su cupo. El agente deja de responder (eso no cambia: la
puerta del libro sigue cerrada). Lo que cambia es que el partner **lo ve** —en
la ficha del cliente, en la lista y en la portada— y **lo sabe**: recibe un
aviso en la consola y por correo que nombra al cliente y le lleva a asignarle
más cupo. Mover cupo de otro cliente es una sola acción que o se hace entera o
no se hace.

**Por qué esta prioridad**: el silencio al agotar cupo es el incidente del
31-ago y la única forma que hoy tiene el partner de enterarse es que su cliente
se queje.

**Prueba independiente**: bajar el tope de un cliente a lo ya consumido,
provocar un turno, y comprobar el estado en las tres pantallas, el aviso y el
correo; después mover cupo desde otro cliente y ver que ambos topes cambian a
la vez.

**Escenarios de aceptación**:

1. **Dado** un cliente cuyo cupo restante llega a cero, **cuando** entra un mensaje, **entonces** en menos de un minuto la ficha, la lista y la portada muestran «sin cupo» en ese cliente y el partner recibe un aviso en la consola que nombra al cliente y enlaza a asignarle cupo.
2. **Dado** el mismo caso, **cuando** el partner tiene destinatarios de correo configurados, **entonces** recibe un correo con el nombre del cliente y el enlace, y no recibe otro por ese cliente hasta el día siguiente aunque entren más mensajes.
3. **Dado** dos clientes con cupo, **cuando** el partner mueve una cantidad del primero al segundo, **entonces** los dos topes cambian en la misma operación; **si** la operación falla, **entonces** ningún tope cambia y el partner ve por qué.
4. **Dado** un cliente «sin cupo», **cuando** el partner le asigna cupo, **entonces** el estado desaparece de las tres pantallas y el siguiente mensaje recibe respuesta.

---

### Historia 3 — El alta termina con la verdad a la vista (Prioridad: P2)

El partner crea un cliente con el wizard y marca «publicar y activar». Ve cada
etapa —crear, generar el agente, publicar, activar— avanzar por separado; si
una falla, ve cuál, por qué, y la reintenta sin repetir las anteriores. Al
terminar, la ficha le dice qué falta para que el cliente atienda.

**Por qué esta prioridad**: hoy las tres últimas llamadas van juntas y un fallo
a mitad deja un cliente creado, un agente publicado y un estado que la pantalla
resume como «parcial».

**Prueba independiente**: simular un fallo en «activar» y comprobar que crear,
generar y publicar quedan hechos y verdes, «activar» queda en error con motivo
y reintento, y el reintento no vuelve a publicar.

**Escenarios de aceptación**:

1. **Dado** el wizard en el paso de revisión, **cuando** el partner ejecuta, **entonces** ve cuatro etapas con estado propio y ninguna avanza sin que la anterior haya terminado.
2. **Dado** que «activar» falla, **cuando** el partner reintenta, **entonces** solo se reintenta «activar» y el agente no se publica dos veces.
3. **Dado** que el alta termina sin canal, **cuando** aterriza en la ficha, **entonces** la ficha nombra lo que falta («Conectar WhatsApp») con la acción a un clic.

---

### Historia 4 — Elegir el modelo del agente (Prioridad: P2)

En los ajustes del agente el partner ve con qué modelo responde su cliente,
elige otro entre los que su plan permite, con su coste relativo en créditos, y
el cambio se aplica al siguiente turno sin publicar una versión nueva del
prompt.

**Por qué esta prioridad**: la capacidad existe en la API con permisos y lista
blanca; solo falta que se vea. Y es lo que un partner toca cuando un cliente
sale caro o responde mal.

**Prueba independiente**: cambiar el modelo, enviar un turno en el Playground
y comprobar que el inspector muestra el modelo nuevo.

**Escenarios de aceptación**:

1. **Dado** un cliente con agente, **cuando** el partner abre los ajustes del agente, **entonces** ve el modelo actual con nombre comercial y la lista de los permitidos para su plan, cada uno con su coste relativo en créditos.
2. **Dado** que elige otro modelo y guarda, **cuando** entra el siguiente turno, **entonces** responde el modelo elegido y la auditoría registra quién lo cambió.
3. **Dado** un modelo que su plan no permite, **cuando** intenta elegirlo, **entonces** no aparece en la lista (no es un botón apagado).

---

### Historia 5 — Conectar AgendaPro y los conectores por clave sin fricción (Prioridad: P3)

El partner enlaza la agenda de AgendaPro de su cliente pegando la URL pública
de reservas en la consola; al guardar, el conector queda conectado y sus
herramientas de citas disponibles para el agente. Para
WooCommerce, Amigable Cobro y Amigable Venta, al guardar la clave el conector
se sincroniza solo, y los campos del formulario están en su idioma.

**Por qué esta prioridad**: es la última pieza del «operativo de verdad» para
los verticales de citas y de venta; lo demás ya funciona por trazado.

**Prueba independiente**: enlazar AgendaPro con una URL pública de prueba y ver
las herramientas de citas activables; conectar WooCommerce y comprobar que no
hace falta pulsar «Sincronizar».

**Escenarios de aceptación**:

1. **Dado** AgendaPro sin enlazar, **cuando** el partner pega la URL pública de reservas del cliente y guarda, **entonces** el conector pasa a conectado y las herramientas de citas aparecen activables.
2. **Dado** un conector por clave de API, **cuando** el partner guarda la clave, **entonces** el conector se sincroniza sin más clics y el resultado (conectado / parcial / error con motivo) se ve en el mismo sitio.
3. **Dado** cualquier formulario de credenciales, **cuando** se muestra, **entonces** las etiquetas de los campos están en el idioma del partner.
4. **Dado** un conector que devuelve error de credenciales, **cuando** el partner guarda, **entonces** ve el motivo en su idioma y nada queda guardado como conectado.

---

### Casos límite

- Meta devuelve un número que ya está conectado a **otro** cliente del mismo o de otro partner: la conexión se rechaza con motivo y no se roba el número.
- El partner mueve más cupo del que el origen tiene, o mueve a sí mismo: la operación no empieza y el motivo es legible.
- El aviso «sin cupo» de un cliente al que el partner ya reasignó cupo un minuto antes: no se envía (el estado se recalcula antes de avisar).
- Un cliente sin cupo **y** sin canal: la ficha nombra las dos cosas, en ese orden (sin canal primero: no llega nada que responder).
- El plan del partner deja de permitir el modelo elegido (baja de plan): el siguiente turno usa el modelo por defecto del plan y el partner ve un aviso, no un error.
- La URL pública de AgendaPro deja de responder (el cliente cambió de plan o de página): el conector lo muestra en su diagnóstico y el agente escala la cita al dueño en vez de inventarla.
- Rol sin permiso de escritura en cualquiera de las cinco historias: la acción **no aparece** (constitución §V), y si llega por otra vía, la consola responde con su propio «no puedes».
- Meta no configurada en el entorno (sin claves): la ausencia se diseña — un texto que dice quién conecta y cómo pedirlo, sin botón.

## Requisitos *(obligatorio)*

### Requisito 1 — WhatsApp se conecta desde la consola

**Historia de usuario:** Como partner, quiero conectar el WhatsApp de mi cliente desde la consola, para que atienda sin pedírselo a Auphere.

#### Criterios de aceptación

1. WHEN el partner con permiso de escritura en canales pulsa «Conectar WhatsApp» THEN el sistema DEBE abrir el registro de Meta con la configuración del entorno y, al completarse, DEBE dejar el canal activo y visible en Canales sin recargar a mano.
2. WHEN el canal queda activo THEN el sistema DEBE recalcular la salud del cliente («listo» cuando agente, canal y activación coinciden) y el paso «Conecta un canal» del onboarding.
3. IF el entorno no tiene la configuración de Meta THEN el sistema DEBE mostrar quién conecta WhatsApp en ese entorno y cómo pedirlo, y NO DEBE mostrar un botón deshabilitado.
4. IF el registro de Meta se interrumpe o falla THEN el sistema NO DEBE dejar ningún canal a medias y DEBE permitir reintentar.
5. IF el número ya está conectado a otro cliente THEN el sistema DEBE rechazar la conexión con un motivo legible y NO DEBE modificar el otro cliente.
6. El sistema DEBE registrar en la auditoría quién conectó el canal y sobre qué cliente, sin ningún token de Meta.
7. WHERE el partner entra desde la aplicación de escritorio EL sistema DEBE seguir ofreciendo continuar en el navegador, y esa ruta DEBE llevar al botón real.
8. El wizard y el diagnóstico del canal DEBEN describir la conexión tal como existe (sin prometer un botón que no está).

### Requisito 2 — «Sin cupo» es un estado visible y avisado

**Historia de usuario:** Como partner, quiero enterarme en el momento de que un cliente se ha quedado sin cupo y poder resolverlo, para que no me lo cuente él.

#### Criterios de aceptación

1. WHEN el cupo restante de un cliente llega a cero THEN el sistema DEBE mostrar el estado «sin cupo» en la ficha, en la lista de clientes y en la portada en menos de un minuto.
2. WHEN un mensaje entrante se salta por falta de cupo THEN el sistema DEBE crear un aviso en la consola que nombre al cliente y enlace a asignarle cupo, como máximo uno por cliente y día.
3. WHERE el partner tiene destinatarios de correo configurados EL sistema DEBE enviar el mismo aviso por correo, con la misma frecuencia máxima.
4. WHEN el partner asigna cupo a un cliente «sin cupo» THEN el sistema DEBE retirar el estado de las tres pantallas y el siguiente mensaje DEBE recibir respuesta.
5. IF el estado se recalcula antes de enviar el aviso y el cliente ya tiene cupo THEN el sistema NO DEBE enviar el aviso.
6. El sistema NO DEBE cambiar lo que recibe el cliente final al agotarse el cupo (decisión del owner del 2026-09-23).
7. WHERE un cliente está sin cupo y sin canal EL sistema DEBE nombrar las dos cosas, el canal primero.

### Requisito 3 — Mover cupo es una sola operación

**Historia de usuario:** Como partner, quiero pasar cupo de un cliente a otro sin riesgo de perderlo por el camino.

#### Criterios de aceptación

1. WHEN el partner mueve una cantidad de un cliente a otro THEN el sistema DEBE bajar el tope del origen y subir el del destino en una única operación que o se completa entera o no cambia nada.
2. IF la cantidad supera el tope del origen, o el origen y el destino son el mismo cliente, o alguno no pertenece al partner THEN el sistema DEBE rechazar la operación con un motivo legible y NO DEBE modificar ningún tope.
3. WHEN la operación se completa THEN el sistema DEBE registrar en la auditoría quién movió cuánto y entre qué clientes.
4. El sistema DEBE presentar mover cupo como una sola acción con un solo resultado, no como «dos guardados».

### Requisito 4 — El alta avanza por etapas visibles

**Historia de usuario:** Como partner, quiero ver qué etapa del alta falla y reintentar solo esa, para no acabar con un cliente a medias sin saberlo.

#### Criterios de aceptación

1. WHEN el partner ejecuta el alta desde la revisión THEN el sistema DEBE ejecutar «crear», «generar el agente», «publicar» y «activar» como etapas separadas, cada una con estado propio visible.
2. IF una etapa falla THEN el sistema DEBE mostrar cuál y por qué, DEBE conservar el resultado de las anteriores y DEBE ofrecer reintentar solo esa.
3. WHEN se reintenta «publicar» o «activar» THEN el sistema NO DEBE publicar una segunda versión ni activar dos veces.
4. WHEN el alta termina THEN la ficha DEBE nombrar lo que falta para atender con la acción a un clic.

### Requisito 5 — El modelo del agente se elige en la consola

**Historia de usuario:** Como partner, quiero elegir con qué modelo responde el agente de un cliente entre los que mi plan permite, para ajustar coste y calidad.

#### Criterios de aceptación

1. WHEN el partner abre los ajustes del agente THEN el sistema DEBE mostrar el modelo actual con nombre comercial y la lista de modelos permitidos para su plan, cada uno con su coste relativo en créditos.
2. WHEN el partner elige un modelo y guarda THEN el sistema DEBE aplicarlo al siguiente turno sin exigir publicar una versión nueva, y DEBE registrar en la auditoría quién lo cambió.
3. El sistema NO DEBE listar modelos que el plan no permite; si el plan deja de permitir el elegido, el sistema DEBE usar el modelo por defecto del plan y avisar al partner.
4. WHERE el Playground muestra el detalle de un turno EL sistema DEBE mostrar el modelo que respondió.

### Requisito 6 — AgendaPro se enlaza desde la consola

**Historia de usuario:** Como partner, quiero enlazar la agenda de AgendaPro de mi cliente desde la consola, para que el agente gestione sus citas sin pedírselo a Auphere.

> Reescrito tras la Fase 0 (ver Clarificaciones): la agenda se enlaza con la **URL pública de reservas** del cliente, que es lo único que el runtime de citas usa hoy. El formulario de credenciales queda fuera hasta que exista un runtime que las consuma.

#### Criterios de aceptación

1. WHEN el partner abre enlazar AgendaPro THEN el sistema DEBE pedir la URL pública de reservas del cliente, con un ejemplo y la explicación de dónde se obtiene.
2. WHEN el partner guarda una URL válida THEN el sistema DEBE dejar el conector como conectado, las herramientas de citas activables, y DEBE registrar en la auditoría quién enlazó la agenda de qué cliente.
3. IF la URL no es segura (https) o no es de AgendaPro THEN el sistema DEBE rechazarla con un motivo legible y NO DEBE cambiar el estado del conector.
4. WHEN el partner desenlaza THEN el sistema DEBE pedir confirmación, dejar el conector desconectado y el agente NO DEBE ofrecer citas.
5. El sistema NO DEBE ofrecer ningún formulario de credenciales de AgendaPro mientras no exista un runtime que las use (la ausencia se diseña).

### Requisito 7 — Conectar un conector por clave sincroniza solo y habla el idioma del partner

**Historia de usuario:** Como partner, quiero que al guardar una clave el conector quede listo, y entender cada campo que me piden.

#### Criterios de aceptación

1. WHEN el partner guarda la clave de un conector THEN el sistema DEBE sincronizarlo en la misma operación y DEBE mostrar el resultado (conectado / parcial / error con motivo) en el mismo sitio, sin exigir «Sincronizar».
2. El sistema DEBE mostrar las etiquetas y ayudas de los campos de credenciales en el idioma del partner.
3. IF la sincronización falla tras guardar la clave THEN el sistema DEBE dejar el conector en un estado que diga qué pasó y DEBE ofrecer reintentar la sincronización sin volver a pedir la clave.

### Requisito 8 — Cada acción de la consola comprueba el rol y está probada

**Historia de usuario:** Como partner con un rol limitado, quiero que la consola me diga con sus palabras lo que no puedo hacer, y como equipo queremos que ninguna acción quede sin prueba.

#### Criterios de aceptación

1. El sistema DEBE comprobar el permiso del rol en cada acción de servidor de la consola antes de llamar a la API, y responder con la frase propia de la consola cuando falte.
2. Cada acción de servidor de la consola DEBE tener al menos una prueba automática del camino permitido y del camino denegado.
3. WHERE una acción no está permitida para el rol EL sistema NO DEBE mostrar el control que la dispara.

### Entidades clave *(si la feature toca datos)*

- **Canal (WhatsApp)**: el número de un cliente conectado a Meta; pertenece a un tenant (columna `tenant_id`, RLS). Nace de un registro de Meta iniciado por una persona del partner.
- **Asignación de cupo**: tope y restante de un cliente dentro de la cartera del partner; por tenant dentro de un partner. Mover cupo toca dos asignaciones del mismo partner a la vez.
- **Estado «sin cupo»**: derivado (restante ≤ 0 o sin asignación); no se guarda, se calcula, y el aviso que provoca lleva una clave de deduplicación por cliente y día.
- **Modelo del agente**: elección por tenant entre los permitidos al partner; con auditoría de quién lo cambió.
- **Credenciales de conector**: cifradas, por tenant e integración; nunca se leen de vuelta (conectores por clave). AgendaPro no guarda credenciales: guarda la URL pública de reservas del cliente.
- **Aviso al partner**: por partner, con cliente, tipo «sin cupo», severidad de aviso y deduplicación por cliente y día; se muestra en la consola y opcionalmente por correo.

## Criterios de éxito *(obligatorio)*

- **CE-001**: un partner nuevo crea un cliente, publica, conecta WhatsApp y recibe la primera respuesta a un mensaje real sin ninguna intervención de Auphere, en menos de 15 minutos.
- **CE-002**: en staging, un cliente que agota su cupo aparece «sin cupo» en la ficha, la lista y la portada en menos de un minuto, y el partner recibe un aviso; nunca más de un aviso por cliente y día.
- **CE-003**: mover cupo entre dos clientes nunca deja la suma de topes distinta de la de partida, ni cuando la operación falla (prueba de fallo inyectado).
- **CE-004**: un fallo en la última etapa del alta se reintenta sin publicar una segunda versión, en el 100 % de los intentos de prueba.
- **CE-005**: el partner cambia el modelo y el siguiente turno del Playground muestra el modelo nuevo.
- **CE-006**: AgendaPro se enlaza desde la consola en una sola acción y la auditoría nombra quién lo hizo; la consola no pide ni guarda ninguna credencial de AgendaPro.
- **CE-007**: conectar un conector por clave pasa de dos clics a uno, y el 100 % de las etiquetas del formulario están traducidas en ES y EN.
- **CE-008**: la suite de acciones de servidor cubre el 100 % de las acciones de la consola con un caso permitido y uno denegado.

## Fuera de alcance

- Rediseñar la ficha de cliente, la pantalla de Consumo o el wizard (Bloque D, spec 017) — aquí solo se añade el estado «sin cupo», la etapa visible y el selector donde ya viven.
- Otros canales (TikTok, Instagram, web) — TikTok sigue apagado por bandera; no hay más canales.
- Conectores nuevos (CRM, ERP, Google Calendar) — no existen; entrarían por `assess`.
- Cambiar el mensaje que recibe el cliente final al agotarse el cupo — decisión del owner: no cambia.
- Que el partner elija el modelo del Companion — es global por diseño (H3), fuera de esta spec.
- El registro de partners y el panel de operador del registro — spec 006.

## Supuestos

- Las claves de Meta (`app id` y configuraciones de Embedded Signup) existen en staging y producción, como documenta `infra/README-console.md`; en local no, y por eso la ausencia diseñada es parte de la spec y no un caso raro.
- Los destinatarios del correo «sin cupo» son los mismos que ya reciben los avisos de saldo del partner (spec 004); no se crea otra lista.
- La lista de modelos permitidos por plan es la que ya expone la API de la consola (allowlist por partner); no se define aquí ninguna política de precios nueva.
- «Coste relativo en créditos» se expresa con los pesos por carril de la spec 007 (por ejemplo «×1», «×4»), no en dólares.
- La URL pública de AgendaPro se valida por forma (https y dominio de AgendaPro), no abriendo la página: es lo mismo que hace hoy el panel de operador.
- El aviso «sin cupo» reutiliza el canal de avisos existente (consola + correo con deduplicación), añadiendo un tipo nuevo por cliente.
- Enlazar AgendaPro exige el mismo permiso que conectar cualquier otro conector (escritura sobre el agente); no se crea un permiso nuevo.
- El estado «sin cupo» se deriva del mismo libro de cupo que decide si un turno se atiende; no existe una copia que pueda discrepar.
