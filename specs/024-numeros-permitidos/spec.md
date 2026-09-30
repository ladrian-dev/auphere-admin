# Especificación: los números permitidos se editan en Ajustes del agente

**Rama**: `024-numeros-permitidos` · **Creada**: 2026-09-30 · **Estado**: Borrador

**Entrada**: descripción del usuario: ver §Origen.

## Encabezado Auphere *(obligatorio)*

| Campo | Valor |
|---|---|
| **Superficie de confianza** | `0` — API de la consola. No entra ninguna lectura ni escritura nueva fuera de la plataforma |
| **Garantías de aislamiento tocadas** | Ninguna. La lista vive en la configuración del agente del tenant, que la RLS ya aísla; el que decide si un remitente está en la lista es el servidor, nunca el remitente |
| **Nota de KB que la justifica** | `[[sessions/2026-09-30-spec-023-tres-conectores-mas]]` (tarde: alta de Flor y Encanto) y `[[clients/flor-y-encanto]]` |
| **Qué se mide** | Nada nuevo. Un mensaje que el agente no responde no gasta modelo; ya es así hoy |

## Origen

El 2026-09-30, con Flor y Encanto recién conectado en producción, el owner
desvinculó el número porque el agente «le estaba respondiendo a todo el
mundo» y pidió que respondiera **solo a cinco números** mientras se prueba.

Medido en el código, eso ya existe: el modo «solo administradores»
(`policies.admin_access.admin_only` con una lista `admin_phones`) hace que
el agente responda únicamente a los números de la lista; a los demás no les
contesta ni les marca el mensaje como leído, aunque el mensaje entrante se
guarda. Es el modo con el que trabaja Mouna (cobranza). Pero **no tiene
pantalla**: solo se puede fijar por la API de partners con una clave de
API (`PUT /v2/partners/clients/{ref}/admins`), o en el asistente de alta
cuando la plantilla es de solo administradores. Ni la consola ni el panel
Admin lo enseñan ni lo editan. Para un partner que quiere pilotar un
cliente nuevo con su propio teléfono y el del dueño antes de abrirlo al
público, eso significa crear una clave, abrir una terminal y lanzar una
petición a mano. Hoy costó tres intentos.

La consola ya tiene el sitio natural: **Ajustes del agente**, donde el
partner decide identidad, tono, horario, idiomas, escalado y aviso de IA.
Ahí falta la pregunta «¿a quién responde?».

## Escenarios de usuario y pruebas *(obligatorio)*

### Historia 1 — El partner limita a quién responde el agente (Prioridad: P1)

En Ajustes del agente hay una sección **«A quién responde»** con un
interruptor: *A todo el mundo* (lo normal) o *Solo a estos números*. Con la
segunda opción, el partner escribe los números, uno por línea o separados
por comas, con prefijo internacional, y opcionalmente un nombre junto a
cada uno («+56 9 9191 9125 · Daniel, ventas»). Guarda, publica, y desde el
siguiente mensaje el agente responde solo a esos números. Los demás
mensajes llegan a Conversaciones marcados como «sin respuesta: número no
permitido», y el agente no los lee ni les contesta.

**Por qué esta prioridad**: es la forma de pilotar un cliente nuevo con
número real sin que atienda a desconocidos; hoy exige una clave de API y
una terminal.

**Prueba independiente**: con un cliente conectado, poner dos números en la
lista, publicar, escribir desde uno de la lista y desde uno que no lo está.

**Escenarios de aceptación**:

1. **Dado** un cliente con el agente respondiendo a todo el mundo,
   **cuando** el partner elige «Solo a estos números», escribe dos números
   y publica, **entonces** un mensaje desde uno de ellos recibe respuesta y
   un mensaje desde otro número no recibe respuesta ni se marca como leído.
2. **Dado** un cliente limitado a una lista, **cuando** el partner vuelve a
   «A todo el mundo» y publica, **entonces** el siguiente mensaje de
   cualquier número recibe respuesta.
3. **Dado** «Solo a estos números» con la lista vacía, **cuando** el partner
   intenta guardar, **entonces** la consola no guarda y dice que hace falta
   al menos un número: un agente que no responde a nadie no se puede
   publicar.
4. **Dado** un número mal escrito (sin prefijo, con menos de siete cifras),
   **cuando** el partner guarda, **entonces** la consola señala ese número
   y no guarda hasta corregirlo.

---

### Historia 2 — La pantalla dice que el agente está limitado (Prioridad: P2)

Mientras la lista está activa, la ficha del cliente lo dice en la cabecera
(«Responde solo a 5 números»), la lista de clientes lo enseña como estado
distinto de «Activo» a secas, y en Conversaciones cada mensaje que el agente
no respondió por no estar en la lista lleva su motivo. Nadie tiene que
adivinar por qué el agente calla.

**Por qué esta prioridad**: sin esto, un partner que olvidó la lista vería
un agente «Activo» que no contesta a un cliente real, y escribiría a
Auphere. Va después de la Historia 1 porque necesita que la lista exista.

**Prueba independiente**: activar la lista y mirar cabecera, lista de
clientes y una conversación de un número no permitido.

**Escenarios de aceptación**:

1. **Dado** un cliente con lista activa, **cuando** el partner abre su ficha
   o la lista de clientes, **entonces** ve que responde solo a N números.
2. **Dado** un mensaje entrante de un número fuera de la lista, **cuando**
   el partner abre esa conversación, **entonces** ve que el agente no
   respondió y el motivo.

---

### Historia 3 — Las plantillas de solo administradores no se pueden abrir a todo el mundo (Prioridad: P3)

Un cliente creado con una plantilla de solo administradores (hoy,
cobranza) nace con la lista obligatoria: en Ajustes del agente la sección
enseña la lista y permite editarla, pero el interruptor «A todo el mundo»
no está disponible, y la consola explica por qué: ese agente es el
asistente del dueño, no atiende a clientes finales.

**Por qué esta prioridad**: evita que un clic abra a los deudores un agente
que puede registrar abonos y descuentos.

**Prueba independiente**: abrir Ajustes del agente de Mouna y comprobar que
la lista se edita y el modo no se puede cambiar.

**Escenarios de aceptación**:

1. **Dado** un cliente de plantilla de solo administradores, **cuando** el
   partner abre Ajustes del agente, **entonces** puede editar la lista y no
   puede elegir «A todo el mundo».

---

### Casos límite

- **El mismo número dos veces**, o con formato distinto (+56 9…, 56 9…,
  con espacios): se guarda una sola vez, normalizado.
- **El partner pone su propio número y el del dueño**: es el caso normal
  del piloto; nada especial.
- **Un número de la lista escribe por otro canal** (otro número del mismo
  cliente): la lista es del agente, no del canal; aplica igual.
- **La lista está activa y el crédito se agota**: el silencio por crédito
  sigue mandando y se muestra como hoy; la lista no lo tapa.
- **Quien solo mira** ve la sección y la lista, sin poder editarlas.
- **Un mensaje entrante de un número no permitido llegó antes de activar
  la lista**: la conversación existente se mantiene; los mensajes nuevos
  quedan sin respuesta con su motivo.

## Requisitos *(obligatorio)*

### Requisito 1 — La lista se edita en Ajustes del agente

**Historia de usuario:** Como partner, quiero decidir en Ajustes del agente
si responde a todo el mundo o solo a una lista de números, para pilotar un
cliente con número real sin abrirlo al público.

#### Criterios de aceptación

1. El sistema DEBE ofrecer en Ajustes del agente una sección «A quién
   responde» con dos opciones: a todo el mundo, o solo a una lista de
   números.
2. WHEN el partner elige la lista THEN el sistema DEBE aceptar números con
   prefijo internacional, con o sin espacios, uno por línea o separados por
   comas, con un nombre opcional por número, y DEBE guardarlos
   normalizados y sin duplicados.
3. IF la lista está activa y vacía, o contiene un número que nunca podría
   coincidir con un remitente, THEN el sistema NO DEBE guardar y DEBE decir
   qué número falla.
4. El cambio DEBE seguir el mismo camino que el resto de Ajustes del agente:
   se guarda en el borrador y publicar es el paso explícito; publicar DEBE
   aplicar la lista desde el siguiente mensaje.
5. Quien solo mira DEBE ver la sección sin poder editarla.

### Requisito 2 — El agente respeta la lista

1. WHEN la lista está activa THEN el sistema DEBE responder solo a los
   remitentes cuyo número esté en la lista, y a los demás NO DEBE
   responderles ni marcarles el mensaje como leído; el mensaje entrante SÍ
   DEBE guardarse.
2. WHEN el partner vuelve a «A todo el mundo» y publica THEN el sistema
   DEBE responder a cualquier remitente desde el siguiente mensaje.
3. La comparación de números DEBE ser la misma que ya usa el modo de solo
   administradores, para que un número guardado desde la consola y otro
   guardado por la API de partners se comporten igual.

### Requisito 3 — La pantalla dice que está limitado

1. WHILE la lista está activa, la cabecera de la ficha del cliente y la
   lista de clientes DEBEN decir que el agente responde solo a N números.
2. WHEN un mensaje entrante no recibió respuesta por no estar en la lista
   THEN Conversaciones DEBE enseñarlo con ese motivo.
3. El Companion DEBE poder leer si un cliente está limitado y a cuántos
   números, con la misma lectura que la pantalla.

### Requisito 4 — Las plantillas de solo administradores

1. WHERE la plantilla del cliente es de solo administradores EL sistema
   DEBE enseñar la lista como obligatoria y NO DEBE ofrecer «A todo el
   mundo», explicando por qué.

### Requisito 5 — Lo que no cambia

1. La API de partners sigue fijando la lista como hoy; consola y API
   escriben y leen el mismo dato, y el último que guarda gana.
2. El asistente de alta sigue pidiendo los números cuando la plantilla lo
   exige.
3. Los roles por número (consultar o cambiar) siguen existiendo solo en la
   API de partners; la consola no los enseña en esta spec.

### Entidades clave

- **Lista de números permitidos**: parte de la configuración del agente
  (versión). Modo (todo el mundo / lista) y números normalizados con nombre
  opcional. Pertenece al tenant y viaja con las versiones: publicar,
  revertir y el historial la incluyen.
- **Mensaje sin respuesta por lista**: un mensaje entrante guardado con el
  motivo de que el agente no respondió.

## Criterios de éxito *(obligatorio)*

- **CE-001**: un partner limita un cliente a dos números desde la consola,
  sin clave de API ni terminal, en menos de dos minutos.
- **CE-002**: con la lista activa, un mensaje desde un número que no está en
  ella no recibe respuesta ni queda marcado como leído, y aparece en
  Conversaciones con su motivo.
- **CE-003**: con la lista activa, la ficha y la lista de clientes lo dicen;
  ninguna pantalla enseña «Activo» a secas.
- **CE-004**: la lista escrita desde la consola y la escrita por la API de
  partners se leen igual desde las dos.
- **CE-005**: el agente de Mouna no se puede abrir a todo el mundo desde la
  consola.

## Fuera de alcance

- Roles por número (solo consultar / cambiar) en la consola.
- Listas por canal: la lista es del agente.
- Horarios o límites por número.
- Avisar por WhatsApp al número no permitido de que no será atendido: el
  silencio es el comportamiento elegido para este modo y no cambia aquí.

## Supuestos

- El modo de solo administradores que ya existe es el mecanismo: la spec le
  da pantalla, estado visible y motivo en Conversaciones; no crea otro
  filtro.
- «Guardar en borrador y publicar» es la convención de Ajustes del agente
  (spec 017) y se mantiene aquí, aunque la API de partners aplique la lista
  al momento. La barra de borrador deja publicar en un clic desde cualquier
  pestaña.
- Los nombres junto a cada número son texto para el partner; el agente no
  los usa.
