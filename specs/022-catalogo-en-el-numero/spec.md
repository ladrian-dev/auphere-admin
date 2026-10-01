# Especificación: el catálogo en el número

**Rama**: `022-catalogo-en-el-numero` · **Creada**: 2026-09-30 · **Estado**: Borrador

**Entrada**: descripción del usuario: ver §Origen.

## Encabezado Auphere *(obligatorio)*

| Campo | Valor |
|---|---|
| **Superficie de confianza** | `0` — API de la consola. Las llamadas a Meta son tres nuevas del mismo cliente que ya usa el alta, con el mismo token |
| **Garantías de aislamiento tocadas** | Ninguna. El catálogo cuelga del canal y el canal ya está bajo la RLS del tenant; los catálogos que Meta devuelve son los del negocio dueño del token, y solo se enseñan a ese cliente |
| **Nota de KB que la justifica** | `[[sessions/2026-09-29-spec-021-el-numero-se-puede-mover]]` (continuación 2026-09-30) · `[[architecture/agent-isolation]]` §1 |
| **Qué se mide** | Nada nuevo: enviar una tarjeta de producto ya cuenta como un mensaje de canal |

## Origen

El 2026-09-30 el owner quiso conectar a «Flor y Encanto» —cliente nuevo en
producción— el catálogo de Commerce Manager de su número de WhatsApp, desde la
consola. No se puede, y la razón es que la pieza existe **a medias**:

| Lo que ya hay | Lo que falta |
|---|---|
| El motor envía **tarjetas de producto nativas** de WhatsApp (un producto, una lista, el catálogo entero) si el canal tiene un catálogo enlazado. Los identificadores que el agente usa son los del catálogo, que en una tienda WooCommerce coinciden con los del producto | Que el canal **tenga** ese catálogo sin un operador |
| El panel de Admin lo enlaza por la vía de operador «conectar número propio», pegando un token permanente | La consola no lo pide en el alta, no lo enseña en la tarjeta del número y no lo deja cambiar |
| Meta expone cómo listar los catálogos de un negocio, ver cuál tiene enlazado una cuenta de WhatsApp Business y enlazar uno | Nuestro cliente de Meta no tiene esas llamadas, y no sabemos si el alta de WhatsApp de la consola pide el permiso que necesitan (`catalog_management`) |
| «Catálogo y ventas» existe como categoría en Conectores | No hay nada de Meta en ella |

El resultado para el partner: su agente responde qué hay y cuánto cuesta
leyendo la tienda, pero **no puede enseñar el producto** como WhatsApp sabe
hacerlo —con foto, precio y botón—, y la única forma de arreglarlo es
escribirnos.

## Clarifications

### Session 2026-10-01

- Q: ¿Qué pasa con el catálogo en un número de coexistencia (la app de WhatsApp Business sigue en el teléfono)? → A: Meta no ofrece el catálogo por API a esas cuentas (`(#10) This operation can not be performed on SMB business type`, visto en producción con Flor y Encanto) y la tarjeta lo enseñaba como «falta el permiso». Ahora el número tiene el estado **«coexistencia»**: la consola no pregunta a Meta, apunta el catálogo que el partner elige de los de su negocio (es el que la app tiene conectado) y lo dice sin fingir que lo comprobó. Las tarjetas de producto sí salen por Cloud API en coexistencia (Barber Supply lo demuestra); lo que Meta bloquea es gestionar el enlace por API.
- Q: ¿Y si Meta tampoco deja listar los catálogos del número de coexistencia (`catalog_management` en acceso estándar)? → A: el partner apunta el identificador y el nombre a mano desde el selector. La consola los guarda tal cual y no finge haberlos comprobado.

### Session 2026-09-30

- Q: ¿Cómo encuentra el agente el producto que va a enseñar como tarjeta: leyendo el catálogo de Meta, o solo a través de la tienda conectada? → A: **leyendo el catálogo de Meta**. Nueva habilidad «buscar en el catálogo» (nombre, precio, disponibilidad); funciona sin tienda conectada, y el catálogo es la única fuente de las tarjetas.
- Q: Si la cuenta de WhatsApp Business ya tiene un catálogo enlazado en Meta (por un operador o desde Commerce Manager), ¿la consola lo adopta o solo cuenta lo enlazado desde ella? → A: **lo adopta**. Al cargar la tarjeta, la consola pregunta a Meta cuál está enlazado; si hay uno que no tenemos, lo guarda y lo enseña como conectado, con cambiar y desconectar.
- Q: Al enlazar un catálogo cuando la cuenta ya tiene otro distinto, ¿se sustituye directamente o se pide confirmación? → A: **confirmar antes**. La consola dice cuál sale y cuál entra («el agente enseñará productos de <B>») y el partner confirma; es una acción consecuente (constitución §IV).

## Escenarios de usuario y pruebas *(obligatorio)*

### Historia 1 — El partner enlaza el catálogo desde la tarjeta del número (Prioridad: P1)

En Canales, la tarjeta de un número conectado dice si tiene catálogo. Si no lo
tiene, ofrece **conectar uno**: la consola le enseña al partner los catálogos
de su negocio en Meta, elige uno, y desde ese momento el número lo tiene
enlazado y el agente puede enviar productos. Si lo tiene, la tarjeta dice cuál
y deja **cambiarlo** o **desconectarlo**.

**Por qué esta prioridad**: es lo que el owner pidió, literal, y es el único
tramo que hoy exige un operador.

**Prueba independiente**: con un número conectado y un negocio con un catálogo
en Commerce Manager, conectar el catálogo desde la tarjeta y comprobar que el
número lo tiene enlazado en Meta y que el agente puede enviar un producto.

**Escenarios de aceptación**:

1. **Dado** un número conectado sin catálogo, **cuando** el partner pulsa
   «Conectar catálogo», **entonces** ve los catálogos de su negocio con su
   nombre, elige uno, y la tarjeta pasa a decir «Catálogo: <nombre>».
2. **Dado** un número con catálogo, **cuando** el partner elige otro,
   **entonces** la consola le dice cuál sale y cuál entra y pide confirmar; al
   confirmar, el número queda enlazado al nuevo y el anterior deja de estarlo.
3. **Dado** un número con catálogo, **cuando** el partner lo desconecta,
   **entonces** el número deja de tener catálogo, el agente deja de poder
   enviar productos, y el número sigue atendiendo igual.
4. **Dado** un negocio sin catálogos en Meta, **cuando** el partner pulsa
   «Conectar catálogo», **entonces** la consola le dice que su negocio no tiene
   ninguno y dónde se crea, sin lista vacía ni error.
5. **Dado** un número cuya cuenta ya tiene un catálogo enlazado en Meta por
   otra vía, **cuando** el partner abre Canales, **entonces** la tarjeta lo
   enseña como conectado, con su nombre, sin que nadie pulse nada.

---

### Historia 2 — El catálogo se ofrece al conectar el número (Prioridad: P2)

Cuando un partner conecta un número nuevo desde la consola y su negocio tiene
catálogos, la consola se lo ofrece en ese momento —no hace falta buscar la
opción después—. Puede saltárselo.

**Por qué esta prioridad**: el momento en que alguien conecta un número es el
momento en que más quiere que todo quede listo. Pero sin la Historia 1 no
existe, y con la Historia 1 se puede vivir sin esto.

**Prueba independiente**: conectar un número nuevo con un negocio que tiene
catálogo y ver que la consola lo ofrece; saltarlo y ver que la tarjeta sigue
ofreciéndolo después.

**Escenarios de aceptación**:

1. **Dado** un negocio con al menos un catálogo, **cuando** el alta de
   WhatsApp termina, **entonces** la consola ofrece enlazarlo con la misma
   lista de la Historia 1.
2. **Dado** esa oferta, **cuando** el partner la salta, **entonces** el número
   queda conectado sin catálogo y la tarjeta ofrece conectarlo más tarde.
3. **Dado** un negocio sin catálogos, **cuando** el alta termina, **entonces**
   no se ofrece nada y el alta termina como hoy.

---

### Historia 3 — El agente enseña productos, y la consola lo dice (Prioridad: P2)

Con un catálogo enlazado, el agente **busca en el catálogo** (nombre, precio,
disponibilidad) y **envía la tarjeta** del producto: dos capacidades que
aparecen en Capacidades como cualquier otra, y que las plantillas de venta
traen. El catálogo es la única fuente de las tarjetas; no hace falta tienda.
Sin catálogo, la capacidad **no aparece** —no hay un botón apagado que
explique lo que no tienes—.

**Por qué esta prioridad**: enlazar el catálogo sin que el agente lo use es
un ajuste sin consecuencia. Va después de la Historia 1 porque depende de ella.

**Prueba independiente**: con catálogo enlazado, pedirle al agente en el
Playground un producto por su nombre y recibir una tarjeta de producto; sin
catálogo, la capacidad no está en la lista.

**Escenarios de aceptación**:

1. **Dado** un número con catálogo, **cuando** un cliente final pregunta por un
   producto que existe en él, **entonces** el agente lo encuentra en el
   catálogo y responde con la tarjeta nativa del producto.
1b. **Dado** un número con catálogo y sin tienda conectada, **cuando** un
   cliente final pregunta «¿qué ramos tenéis?», **entonces** el agente
   responde con productos del catálogo, con precio.
2. **Dado** un número con catálogo, **cuando** el partner abre Capacidades,
   **entonces** ve «Enviar productos del catálogo» y puede apagarla.
3. **Dado** un número sin catálogo, **cuando** el partner abre Capacidades,
   **entonces** esa capacidad no aparece.

---

### Casos límite

- **El permiso no está.** Si el token del alta no permite gestionar catálogos,
  la tarjeta dice que la conexión de WhatsApp no incluyó ese permiso y que hay
  que volver a conectar el número para concederlo; nunca «error».
- **Meta rechaza el enlace** (el catálogo es de otro negocio, o la cuenta ya
  tiene otro): la tarjeta dice lo que Meta dijo, traducido a una frase, y el
  canal queda como estaba.
- **El catálogo se borra o se desenlaza en Commerce Manager** después de
  enlazarlo: la próxima vez que la tarjeta se carga, la consola ve que Meta
  ya no lo tiene, deja de enseñarlo y ofrece conectar otro (Requisito 1.9).
- **Dos números del mismo cliente en la misma cuenta de WhatsApp Business**:
  el catálogo se enlaza a la cuenta, así que ambos números lo tienen; la
  consola lo dice en los dos.
- **Desvincular el número** (spec 021): el catálogo se va con él; al
  reconectarlo, la Historia 2 lo vuelve a ofrecer.
- **Quien solo mira** ve el catálogo enlazado y no ve los controles.

## Requisitos *(obligatorio)*

### Requisito 1 — El catálogo se enlaza y se desenlaza desde la consola

**Historia de usuario:** Como partner, quiero enlazar el catálogo de Meta de
mi negocio a mi número desde la tarjeta del número, para que el agente pueda
enseñar productos sin que nadie de Auphere intervenga.

#### Criterios de aceptación

1. WHEN el partner pide conectar un catálogo THEN el sistema DEBE listar los
   catálogos del negocio dueño del número, con su nombre, y NO DEBE enseñar
   catálogos de ningún otro negocio ni de ningún otro cliente.
2. WHEN el partner elige un catálogo THEN el sistema DEBE enlazarlo a la cuenta
   de WhatsApp Business del número en Meta y guardarlo en el canal, y la
   tarjeta DEBE decir su nombre.
3. WHEN el partner elige otro catálogo con uno ya enlazado THEN el sistema
   DEBE pedir confirmación diciendo cuál sale y cuál entra, y solo al
   confirmar DEBE dejar enlazado el nuevo.
4. WHEN el partner desconecta el catálogo THEN el sistema DEBE deshacer el
   enlace en Meta y borrarlo del canal, y el número DEBE seguir atendiendo.
5. IF Meta rechaza cualquiera de esas operaciones THEN el sistema DEBE dejar el
   canal como estaba y decir en la tarjeta qué pasó y qué hacer, y NO DEBE
   presentarlo como un error de la consola.
6. IF el permiso para gestionar catálogos no está en la conexión de WhatsApp
   THEN el sistema DEBE decirlo en la tarjeta y explicar que se concede
   volviendo a conectar el número.
7. El sistema DEBE anotar en la auditoría quién enlazó, cambió o desconectó
   qué catálogo, y ese registro DEBE leerse en la pantalla de Auditoría con
   una frase.
8. Solo quien puede escribir canales DEBE poder enlazar, cambiar o
   desconectar; quien solo mira DEBE ver el catálogo enlazado sin controles.
9. WHEN la consola enseña un número THEN el sistema DEBE comprobar en Meta qué
   catálogo tiene enlazado su cuenta, y IF hay uno que no está guardado THEN
   DEBE guardarlo y enseñarlo como conectado; IF el guardado ya no está
   enlazado en Meta THEN DEBE dejar de enseñarlo y ofrecer conectar otro.
   *(La pantalla dice la verdad de Meta, no la de nuestra base.)*

### Requisito 2 — El alta lo ofrece

**Historia de usuario:** Como partner, quiero que al conectar un número la
consola me ofrezca el catálogo si mi negocio tiene uno, para no tener que
buscarlo después.

#### Criterios de aceptación

1. WHEN el alta de WhatsApp termina y el negocio tiene al menos un catálogo
   THEN el sistema DEBE ofrecer enlazarlo con la misma lista del Requisito 1.
2. WHEN el partner salta la oferta THEN el sistema DEBE dejar el número
   conectado sin catálogo, y la tarjeta DEBE seguir ofreciéndolo.
3. IF el negocio no tiene catálogos THEN el sistema NO DEBE ofrecer nada y el
   alta DEBE terminar como hoy.
4. La conexión de WhatsApp desde la consola DEBE pedir el permiso de gestión
   de catálogos, para que la oferta y el Requisito 1 no fallen por permiso.

### Requisito 3 — El agente lo usa, y solo cuando lo tiene

**Historia de usuario:** Como partner, quiero que el agente enseñe productos
con la tarjeta nativa de WhatsApp cuando hay catálogo, y que la consola no me
enseñe una capacidad que no puedo usar.

#### Criterios de aceptación

1. WHERE el número tiene catálogo EL sistema DEBE ofrecer en Capacidades
   «Buscar en el catálogo» y «Enviar productos del catálogo», encendidas por
   defecto en las plantillas de venta y apagables.
2. WHERE el número no tiene catálogo EL sistema NO DEBE mostrar esa capacidad.
3. WHEN el agente busca un producto THEN el sistema DEBE leerlo del catálogo
   de Meta (nombre, precio, disponibilidad e identificador), y NO DEBE
   depender de una tienda conectada.
3b. WHEN el agente responde por un producto del catálogo THEN el sistema DEBE
   enviarlo como tarjeta nativa de WhatsApp, con el identificador del
   producto tal como está en el catálogo.
4. WHEN se desconecta el catálogo THEN el agente NO DEBE volver a enviar
   tarjetas de producto desde el turno siguiente.

### Requisito 4 — Lo que no cambia

1. El sistema NO DEBE crear, editar ni sincronizar catálogos: el catálogo se
   hace y se llena en Commerce Manager, y es del negocio.
2. Un número sin catálogo DEBE atender exactamente igual que hoy.
3. Lo que Meta devuelve (nombres, identificadores) DEBE tratarse como dato: se
   enseña, no se ejecuta ni se interpreta.

### Entidades clave

- **Catálogo enlazado**: el identificador y el nombre del catálogo de Commerce
  Manager que la cuenta de WhatsApp Business del número tiene enlazado.
  Pertenece al **canal**, y por él al **tenant**; la RLS lo alcanza por
  `tenant_id` del canal. No es una entidad propia: es un atributo del canal.
- **Catálogo disponible**: cada catálogo que Meta lista para el negocio dueño
  del token. No se guarda; se enseña en el momento de elegir.

## Criterios de éxito *(obligatorio)*

- **CE-001**: un partner enlaza el catálogo de su negocio a su número desde la
  consola, sin escribir a Auphere, en menos de un minuto.
- **CE-002**: con el catálogo enlazado, un cliente final que pregunta por un
  producto recibe la tarjeta nativa de WhatsApp con foto, nombre y precio.
- **CE-003**: sin permiso o con Meta rechazando, la tarjeta dice qué falta y
  qué hacer; nada queda a medias y el número sigue atendiendo.
- **CE-004**: al conectar un número nuevo con un negocio que tiene catálogo,
  la consola lo ofrece y se puede saltar.
- **CE-005**: quien solo mira ve el catálogo y no puede tocarlo; la
  auditoría nombra a quien lo enlazó.

## Fuera de alcance

- **Crear o rellenar el catálogo** — es de Commerce Manager y del negocio.
- **Sincronizar la tienda (WooCommerce) con el catálogo de Meta** — Meta ya
  ofrece esa sincronización desde Commerce Manager; no la duplicamos.
- **La vía de operador «conectar número propio»** — se conserva tal cual.
- **Un conector «Catálogo de Meta» en Conectores** — el catálogo es un
  atributo del número, no una integración aparte; vive en su tarjeta.

## Supuestos

- El permiso de gestión de catálogos se añade a la configuración del alta de
  WhatsApp en el panel de Meta; los números ya conectados antes de eso
  necesitarán volver a conectarse para concederlo (Requisito 1.6).
- Un negocio suele tener un catálogo; la lista se diseña para pocos.
- Enlazar un catálogo a una cuenta de WhatsApp Business que ya tiene otro lo
  sustituye tras confirmar (Requisito 1.3); si Meta exige desenlazar antes,
  la consola lo hace en el mismo paso; si lo rechaza, lo decimos (1.5).
- El motor que envía tarjetas de producto ya existe y se reutiliza; lo nuevo
  es cómo llega el catálogo al canal, que el agente pueda leerlo, y que la
  consola lo cuente.
