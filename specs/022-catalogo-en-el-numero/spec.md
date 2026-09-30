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
2. **Dado** un número con catálogo, **cuando** el partner lo cambia por otro,
   **entonces** el número queda enlazado al nuevo y el anterior deja de
   estarlo.
3. **Dado** un número con catálogo, **cuando** el partner lo desconecta,
   **entonces** el número deja de tener catálogo, el agente deja de poder
   enviar productos, y el número sigue atendiendo igual.
4. **Dado** un negocio sin catálogos en Meta, **cuando** el partner pulsa
   «Conectar catálogo», **entonces** la consola le dice que su negocio no tiene
   ninguno y dónde se crea, sin lista vacía ni error.

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

Con un catálogo enlazado, la capacidad «enviar productos del catálogo» aparece
en Capacidades como cualquier otra, y las plantillas de venta la traen.
Sin catálogo, la capacidad **no aparece** —no hay un botón apagado que
explique lo que no tienes—.

**Por qué esta prioridad**: enlazar el catálogo sin que el agente lo use es
un ajuste sin consecuencia. Va después de la Historia 1 porque depende de ella.

**Prueba independiente**: con catálogo enlazado, pedirle al agente en el
Playground un producto por su nombre y recibir una tarjeta de producto; sin
catálogo, la capacidad no está en la lista.

**Escenarios de aceptación**:

1. **Dado** un número con catálogo, **cuando** un cliente final pregunta por un
   producto que existe en él, **entonces** el agente responde con la tarjeta
   nativa del producto.
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
- **El catálogo se borra en Commerce Manager** después de enlazarlo: la
  tarjeta lo sigue mostrando hasta la siguiente comprobación de salud del
  canal, que lo marca como «ya no existe» y ofrece conectar otro.
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
3. WHEN el partner cambia el catálogo THEN el sistema DEBE dejar enlazado solo
   el nuevo.
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
   «Enviar productos del catálogo», encendida por defecto en las plantillas de
   venta y apagable.
2. WHERE el número no tiene catálogo EL sistema NO DEBE mostrar esa capacidad.
3. WHEN el agente responde por un producto del catálogo THEN el sistema DEBE
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
  sustituye, o Meta lo rechaza y lo decimos (Requisito 1.5).
- El motor que envía tarjetas de producto ya existe y se reutiliza; lo nuevo
  es cómo llega el catálogo al canal y que la consola lo cuente.
