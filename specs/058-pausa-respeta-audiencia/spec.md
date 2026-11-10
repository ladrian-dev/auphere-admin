# Especificación: La pausa respeta la audiencia

**Rama**: `058-pausa-respeta-audiencia` · **Creada**: 2026-11-10 · **Estado**: Implementada en la rama, pendiente de la revisión de Luis (2026-11-10)

**Entrada**: descripción del usuario: "Un cliente en pausa (o archivado, o con el agente/canal en pausa) no debe convertir en «Espera a una persona» ni avisar por correo/campana/push los mensajes de contactos que están fuera de la audiencia del canal (canal «Solo mi equipo» / agente solo para administradores). Hoy la puerta de pausa del cliente se evalúa antes que la de audiencia, así que en prod Flor y Encanto (en pausa, solo administradores) manda a su persona del cliente un correo «X está esperando una respuesta» por cada cliente final que escribe, cosa que no pasaría con el cliente activo. Requisito: la audiencia se decide antes que cualquier pausa; el mensaje se sigue guardando siempre (047 req. 2.1), con motivo out_of_audience, sin Bandeja ni avisos."

## Encabezado Auphere *(obligatorio)*

| Campo | Valor |
|---|---|
| **Superficie de confianza** | `0`: el runtime del agente y la Bandeja, que ya existen. No se abre ninguna superficie. |
| **Garantías de aislamiento tocadas** | **1 (RLS), rozada por la limpieza** (requisito 3): recorre todos los clientes, y cada uno se trabaja bajo su RLS, sin tocar las conversaciones ni los avisos de otro. La puerta del turno (requisitos 1 y 2) no toca ninguna: solo reduce qué conversaciones de un cliente llegan a su Bandeja y quién recibe un aviso dentro de ese mismo cliente. No mueve datos entre tenants ni entre contactos. C8 (el partner nunca lee el cuerpo de un mensaje) tampoco cambia, porque el aviso sigue sin llevar texto del mensaje. |
| **Nota de KB que la justifica** | `[[bugs/2026-11-10-pausa-avisa-fuera-de-audiencia]]` en `/Users/lmatos/Work/Auphere/nexus/` |
| **Qué se mide** | **Nada.** No llama al modelo ni a herramientas de pago. Lo único que cambia es que salen menos correos, y eso alivia el cupo compartido de correo de staging y prod. |

### Lo que enmienda

| Dónde | Qué decía | Qué dice ahora |
|---|---|---|
| Spec 047, **27.2** | «WHILE algo esté en pausa, el sistema DEBE guardar los mensajes y llevarlos a la Bandeja con el motivo.» | Los guarda siempre. Los lleva a la Bandeja **salvo los de contactos fuera de la audiencia del número** (requisito 1). |
| Spec 047, **2.3** y contrato `events.md` §2 | Salvo `out_of_audience`, la conversación va a «Espera a una persona». No dice qué pasa si además hay una pausa. | Si el contacto está fuera de la audiencia, el motivo es `out_of_audience` **aunque** el cliente, el canal o el agente estén en pausa, archivados, en alta o sin publicar (requisito 1.2). |

## Por qué

El 2026-11-10 a las 18:21 UTC llegó a producción la spec 047. Desde las 18:37, cada
contacto que escribe a **Flor y Encanto** genera un correo «{contacto} está
esperando una respuesta» a la persona de ese cliente, además de la campana y el
push. En los primeros veinte minutos salieron tres.

- **El cliente está en pausa.**
- **Su número responde solo a su equipo.** La API ya ve a esos contactos fuera de
  la audiencia: no marca sus mensajes como leídos.

Con el cliente activo, esos mismos mensajes se guardarían en silencio, porque su
agente no les contestaría nunca. Pausar el cliente, que es la parada de
emergencia del negocio, vuelve el número **más ruidoso**: lo llena de esperas que
no espera nadie.

La causa es el orden de las puertas del turno. Las de estado (cliente en pausa,
archivado o en alta, canal en pausa o desconectado, agente sin publicar, agente
en pausa) van antes que la de audiencia, y la primera que cierra gana. La spec
047 deja el hueco: el requisito 27.2 manda a la Bandeja todo lo que llega en
pausa, y el 2.3 deja fuera de la Bandeja lo de fuera de la audiencia. No dice cuál
gana cuando se cumplen los dos.

## Escenarios de usuario y pruebas *(obligatorio)*

### Historia 1 — Pausar no llena la Bandeja de contactos a los que el número no responde (Prioridad: P1)

Un negocio tiene su número en «Solo mi equipo» mientras prueba el agente, y lo
pone en pausa unos días. Durante la pausa le escriben clientes finales que no
están entre los números de prueba. Sus mensajes se guardan y se ven en
Conversaciones como «sin responder · número no permitido», igual que con el
cliente activo. No aparecen en la Bandeja, y nadie del negocio recibe correo,
campana ni push por ellos. Cuando escribe uno de sus números de prueba, en
cambio, la conversación sí va a la Bandeja como «Cliente en pausa» y se avisa,
como hoy.

**Por qué esta prioridad**: es el fallo que está mandando correos en producción.

**Prueba independiente**: un cliente en pausa con un número «Solo mi equipo».
Escribe un contacto que no es número de prueba: el mensaje queda guardado con
motivo `out_of_audience`, la conversación no espera a nadie y no sale ningún
aviso. Escribe un número de prueba: espera con «Cliente en pausa» y sale un aviso.

**Escenarios de aceptación**:

1. **Dado** un cliente en pausa con un número «Solo mi equipo», **cuando** escribe un contacto que no es número de prueba, **entonces** el mensaje se guarda, la conversación no pasa a «Espera a una persona» y no sale correo, campana ni push.
2. **Dado** ese mismo cliente, **cuando** escribe uno de sus números de prueba, **entonces** la conversación pasa a «Espera a una persona» con «Cliente en pausa» y se avisa a sus personas, como hoy.
3. **Dado** un número «A todos» con excepciones y el agente en pausa por falta de saldo, **cuando** escribe un número de las excepciones, **entonces** no va a la Bandeja ni avisa. **Cuando** escribe cualquier otro contacto, **entonces** va a la Bandeja con «Sin saldo».
4. **Dado** un cliente archivado, un canal en pausa, un agente sin publicar o un agente pausado a mano, **cuando** escribe un contacto fuera de la audiencia, **entonces** pasa lo mismo que en el escenario 1.
5. **Dado** un cliente en pausa sin módulo de Bandeja, **cuando** escribe un contacto fuera de la audiencia, **entonces** no se avisa a los destinatarios de escalado del canal ni se envía el mensaje de espera.

---

### Historia 2 — Una espera que ya no es cierta deja de esperar (Prioridad: P2)

Una conversación entró en «Espera a una persona» por una pausa, porque el
contacto estaba entonces dentro de la audiencia o por este fallo. Ahora ese
contacto está fuera de la audiencia y vuelve a escribir. La espera deja de ser
cierta: su número no le responde ni con el cliente activo. La conversación deja
de esperar, se queda con el motivo «fuera de la audiencia» y su aviso
pendiente pasa a atendido. Si la conversación esperaba porque el contacto pidió
una persona, sigue esperando.

**Por qué esta prioridad**: sin esto, la conversación se quedaría en la Bandeja
para siempre con un motivo que no se pinta, porque `out_of_audience` no tiene
texto de Bandeja.

**Prueba independiente**: una conversación que espera con «Cliente en pausa» y
cuyo contacto queda fuera de la audiencia. Llega un mensaje suyo: la
conversación deja de esperar y su aviso queda atendido. La misma prueba con una
conversación escalada a una persona: sigue esperando.

**Escenarios de aceptación**:

1. **Dado** una conversación que espera por «Cliente en pausa» y un contacto fuera de la audiencia, **cuando** ese contacto escribe, **entonces** la conversación sale de «Espera a una persona», queda con el motivo «fuera de la audiencia» y su aviso pendiente pasa a atendido.
2. **Dado** una conversación que espera porque el contacto pidió una persona, **cuando** ese contacto, ya fuera de la audiencia, escribe, **entonces** sigue esperando a una persona.

---

### Historia 3 — Limpiar lo que el fallo ya dejó en la Bandeja (Prioridad: P3)

Una persona de Auphere lanza la limpieza una vez, después de desplegar el
arreglo. Primero en seco: dice qué conversaciones sacaría, por cliente, sin tocar
nada. Después de verdad. Las conversaciones que este fallo dejó en «Espera a una
persona» dejan de esperar sin que cada contacto tenga que volver a escribir, y
la persona de Flor y Encanto no tiene que resolverlas a mano. Ningún despliegue la
lanza solo, igual que el paso a Reservas desde el 2026-11-10.

**Por qué esta prioridad**: hoy son tres en producción y se pueden resolver a
mano. Pero crecen con cada contacto nuevo hasta el despliegue, y también afectan a
cualquier otro cliente en pausa con un número «Solo mi equipo».

**Prueba independiente**: con datos sembrados (dos esperas por pausa con el
contacto fuera de la audiencia, una dentro y una escalada), la pasada en seco las
cuenta sin cambiar nada. La pasada de verdad saca solo las dos primeras, no envía
nada y dice cuántas cambió por cliente.

**Escenarios de aceptación**:

1. **Dado** un cliente en pausa con conversaciones que esperan por «Cliente en pausa», unas con el contacto fuera de la audiencia y otras dentro, **cuando** se lanza la limpieza de verdad, **entonces** solo dejan de esperar las de fuera, y sus avisos pendientes pasan a atendidos.
2. **Dado** ese mismo cliente, **cuando** se lanza en seco, **entonces** dice cuántas sacaría y no cambia nada.
3. **Dado** la limpieza ya hecha, **cuando** vuelve a lanzarse, **entonces** no cambia nada.

---

### Casos límite

- **Número «Sin configurar».** No responde a nadie hasta que se decida (047,
  32.9), así que todo contacto está fuera de la audiencia. Con el cliente en pausa
  tampoco va nada a la Bandeja, igual que con el cliente activo.
- **Número sin audiencia propia** (la API de partner, un tenant directo, una línea
  que no es WhatsApp). Decide la política de solo administradores del agente del
  número. Si el agente está en pausa, decide su versión publicada. Sin versión
  publicada no hay política, y el contacto cuenta como dentro de la audiencia: va
  a la Bandeja con «Agente sin publicar», como hoy.
- **La audiencia cambia mientras hay una espera.** La decide el siguiente mensaje,
  porque la audiencia se lee en cada turno (047, 32.7). Si entonces el contacto
  está fuera, aplica la historia 2.
- **Ráfaga de mensajes.** Un turno junta varios mensajes del mismo contacto y en
  el mismo número, así que comparten audiencia y comparten el resultado.
- **Número solo de envío.** Esta spec no lo toca y sus mensajes siguen igual que
  hoy (requisito 1.7). Hay un hueco parecido, anotado en Fuera de alcance.
- **Agente en pausa por saldo o por tope.** Los contactos fuera de la audiencia no
  van a la Bandeja. Los avisos de saldo y de tope al cliente y al partner (047,
  2.4) no dependen de ningún mensaje y siguen saliendo igual.
- **Una persona tomó el control** de la conversación. Hoy la audiencia ya se
  decide antes que eso, y no cambia.
- **Qué ve la persona del cliente.** Nada nuevo, porque no hay estado que diseñar:
  el mensaje aparece en Conversaciones con su etiqueta de siempre y la Bandeja no
  lo enseña.

## Requisitos *(obligatorio)*

### Requisito 1 — La audiencia se decide antes que cualquier pausa

**Historia de usuario:** Como persona del cliente, quiero que solo me avisen de las conversaciones que mi número atendería, para que una pausa no me llene la Bandeja y el correo de contactos a los que el número nunca responde.

#### Criterios de aceptación

1. WHEN llega un mensaje a un número del cliente que no es solo de envío THEN el sistema DEBE decidir si el contacto está dentro de la audiencia de ese número antes de tener en cuenta el estado del cliente, del canal o del agente.
2. IF el contacto está fuera de la audiencia THEN el sistema DEBE guardar el mensaje y dejar en la conversación el motivo «fuera de la audiencia», aunque además se cumpla cualquiera de estas condiciones:
   - el cliente está en pausa, archivado o en alta;
   - el canal está en pausa o desconectado;
   - el agente está sin publicar, o en pausa por cualquier motivo (a mano, sin saldo, tope del agente, cliente en pausa o cliente archivado).

   En ese caso NO DEBE poner la conversación en «Espera a una persona».
3. IF el contacto está fuera de la audiencia THEN el sistema NO DEBE avisar a nadie de ese mensaje: ni campana, ni correo, ni push de la app, ni destinatarios de escalado del canal. Tampoco DEBE enviar el mensaje de espera al contacto.
4. WHILE el contacto esté dentro de la audiencia, el sistema DEBE seguir aplicando las puertas de estado como hoy (047, requisitos 2 y 27): la conversación va a la Bandeja con su motivo y se avisa a quien toca.
5. El sistema DEBE mostrar un mensaje fuera de la audiencia en Conversaciones igual que con el cliente activo («sin responder · número no permitido»), sea cual sea el estado del cliente, del canal o del agente.
6. WHERE el número no tenga audiencia propia (API de partner, tenant directo, línea que no es WhatsApp) EL sistema DEBE decidir la audiencia con la política de solo administradores de la versión publicada del agente del número, aunque ese agente esté en pausa. Sin versión publicada, el contacto DEBE contar como dentro de la audiencia.
7. WHERE el número sea solo de envío EL sistema DEBE tratar sus mensajes exactamente igual que antes de esta spec.

### Requisito 2 — Una espera que ya no es cierta deja de esperar

**Historia de usuario:** Como persona del cliente, quiero que una conversación deje de esperarme cuando su contacto ya no está en la audiencia del número, para que la Bandeja solo tenga lo que de verdad me toca.

#### Criterios de aceptación

1. WHEN un contacto fuera de la audiencia escribe en una conversación que espera a una persona por un motivo de puerta THEN el sistema DEBE sacarla de «Espera a una persona», dejarle el motivo «fuera de la audiencia» y dar por atendido su aviso pendiente. Los motivos de puerta son: cliente en pausa, cliente archivado, canal en pausa, canal con problemas, agente en pausa, agente sin publicar, sin saldo, tope del agente, sin modelo, fallo del modelo y límite del turno.
2. IF la conversación espera por un motivo que no es de puerta (el contacto pidió una persona, el freno de citas, la agenda sin preparar, derivaciones en bucle), o una persona ya se la asignó, THEN el sistema NO DEBE sacarla de la espera ni cambiar su motivo. Lo que una persona tomó a mano se respeta, como al quitar la Bandeja (spec 056).
3. Sacar una conversación de la espera por este requisito NO DEBE enviar ningún aviso ni ningún mensaje al contacto.

### Requisito 3 — Limpiar lo que el fallo ya dejó en la Bandeja

**Historia de usuario:** Como persona del cliente, quiero que las esperas que este fallo creó desaparezcan al arreglarlo, para no tener que resolverlas una a una.

#### Criterios de aceptación

1. WHEN una persona de Auphere lanza la limpieza de verdad THEN el sistema DEBE sacar de «Espera a una persona» cada conversación que espera por un motivo de puerta y cuyo contacto está fuera de la audiencia **actual** de su número, y DEBE dar por atendidos sus avisos pendientes.
2. WHEN se lanza en seco, que es lo que pasa si no se pide otra cosa, THEN el sistema DEBE decir cuántas conversaciones sacaría en cada cliente y NO DEBE cambiar nada.
3. La limpieza NO DEBE tocar:
   - las conversaciones resueltas;
   - las que esperan por un motivo que no es de puerta;
   - las que una persona ya se asignó;
   - las de contactos dentro de la audiencia;
   - las de números sin audiencia propia (1.6), porque ahí la audiencia depende de qué agente lleva la conversación. Esas las arregla el requisito 2 en el siguiente mensaje del contacto.
4. La limpieza NO DEBE enviar avisos ni mensajes. DEBE dejar rastro de cuántas conversaciones cambió en cada cliente, sin datos del contacto.
5. WHEN la limpieza vuelve a lanzarse THEN NO DEBE cambiar nada más.
6. Ningún despliegue DEBE lanzar la limpieza solo.

### Entidades clave

No hay entidades nuevas. Se tocan estas:

- **Conversación**: su motivo de espera y si está en «Espera a una persona».
  Pertenece al tenant del cliente, y la RLS la alcanza por `tenant_id`.
- **Aviso de la consola** («espera a una persona»): solo cambia cuándo se crea y
  cuándo pasa a atendido. Es del partner y lo filtran el partner y la referencia
  del cliente (047, spec 056 requisito 8).

## Criterios de éxito *(obligatorio)*

- **CE-001**: Con un cliente en pausa y un número «Solo mi equipo», los mensajes de contactos fuera de la audiencia producen **0** correos, campanas y push. Es el mismo número que con el cliente activo.
- **CE-002**: El **100 %** de los mensajes fuera de la audiencia queda guardado y visible en Conversaciones, con cualquier estado del cliente, del canal o del agente.
- **CE-003**: Con contactos dentro de la audiencia, las esperas y los avisos por pausa son los mismos antes y después del cambio.
- **CE-004**: Tras el despliegue en producción, Flor y Encanto no tiene ninguna conversación en «Espera a una persona» por pausa con un contacto fuera de la audiencia. Mientras siga en pausa y con «Solo mi equipo», su persona no recibe ningún correo más de «está esperando una respuesta» por esos contactos.

## Fuera de alcance

- **Qué es la audiencia y cómo se configura** (047, requisito 32). No cambia: solo cambia cuándo se mira.
- **El orden de las puertas de estado entre sí** (pausa del cliente, del canal, del agente, sin publicar). Solo se mueve la audiencia por delante de todas ellas.
- **Los avisos de saldo y de tope por cliente** (047, 2.4). No nacen de un mensaje.
- **Un resumen de los mensajes fuera de la audiencia** para el negocio. Nadie lo ha pedido, y Conversaciones ya los enseña.
- **Qué hacer con Flor y Encanto** (reanudarla, archivarla o desactivar a su persona). Es una decisión operativa. Archivarla no cortaría los correos.
- **Un número solo de envío de un cliente en pausa.** Hoy sus mensajes pasan a la Bandeja por la pausa, porque esa puerta va antes que la de solo envío, aunque ese número no lo atiende nadie (spec 045). Es un hueco del mismo tipo, pero nadie lo ha pedido y ningún cliente está así. Queda anotado en `research.md`.

## Supuestos

- Un contacto fuera de la audiencia es uno al que el número no respondería ni con
  todo activo. Por eso nadie lo espera, pase lo que pase con el estado del
  cliente. Es la lectura de 047, 2.3 que esta spec hace explícita.
- El número de Flor y Encanto está en «Solo mi equipo», o su agente es solo para
  administradores. Lo prueba la API: no marca como leídos los mensajes de esos
  contactos (`read_receipt_suppressed_not_admin`).
- Ningún cliente necesita ver en la Bandeja, durante una pausa, a contactos a los
  que su número no responde. Si alguno lo necesita, la vía es cambiar la audiencia
  del número, no la pausa.
