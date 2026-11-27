# Especificación: el enlace para que el cliente conecte Instagram y Messenger

**Rama**: `085-enlace-instagram-messenger` · **Creada**: 2026-11-27 · **Estado**: Borrador

**Entrada**: Luis, 2026-11-27: «Para conectar WhatsApp yo puedo generar un enlace para enviar y conectarlo. Para Instagram y Messenger estábamos trabajando para lo mismo». Y después: «La idea es replicar el mismo flujo que tiene el WhatsApp, no crear un flujo distinto». Es la spec 7 que propuso el plan del 2026-11-26 (P2 o P3), que nunca se empezó.

## Encabezado Auphere *(obligatorio)*

| Campo | Valor |
|---|---|
| **Superficie de confianza** | `1`, la misma página pública de la spec 040: la abre alguien sin cuenta, la autoriza un token de un solo uso que caduca y se puede anular, y la API solo la atiende con la credencial de servicio de la consola. No se abre una superficie nueva. Se añade una llamada pública más, la de elegir cuenta o Página, protegida por el mismo token. |
| **Garantías de aislamiento tocadas** | **1.** La conexión corre bajo el ámbito del cliente del enlace, como en la 040. La elección pendiente de cuenta o Página solo se completa con el enlace que la inició. |
| **Nota de KB que la justifica** | `research/2026-11-26-beta-jemma-p0-p1.md`, «Enlace de conexión para Instagram y Messenger (comprobado el 2026-11-27)». |
| **Qué se mide** | Nada nuevo. |

## Escenarios de usuario y pruebas *(obligatorio)*

### Historia 1 — El cliente conecta su Instagram desde un enlace (Prioridad: P1)

El partner abre Canales del cliente y, en la tarjeta de Instagram, pulsa «Enviar enlace al cliente». Se abre el mismo panel que en WhatsApp: crea el enlace, lo copia o lo envía por WhatsApp o por correo, y ve cuándo caduca. El dueño del negocio lo abre en su teléfono o en su ordenador, ve «Conecta el Instagram de {negocio}», elige cómo entra a Meta (con Instagram, o con Facebook y su Página), acepta en la ventana de Meta y termina en «¡Listo!». El partner se entera igual que cuando el cliente conecta WhatsApp.

**Por qué esta prioridad**: hoy el partner tiene que conectar Instagram desde su propia sesión, con la cuenta del cliente delante. Con WhatsApp ya no hace falta.

**Prueba independiente**: un cliente sin Instagram; el partner crea el enlace y un tercero, sin cuenta en Auphere, lo abre y conecta una cuenta. El canal aparece en el cliente y un DM recibe respuesta del agente.

**Escenarios de aceptación**:

1. **Dado** un cliente sin Instagram, **cuando** el partner crea el enlace desde la tarjeta de Instagram, **entonces** obtiene un enlace que puede copiar, enviar por WhatsApp o enviar por correo, con su fecha de caducidad.
2. **Dado** ese enlace, **cuando** el dueño lo abre, elige «Con Instagram» y acepta en Meta, **entonces** la página dice que su Instagram está conectado y el canal aparece en el cliente.
3. **Dado** un Instagram vinculado a una Página de Facebook, **cuando** el dueño elige «Con Facebook y tu Página», **entonces** se conecta con la configuración que recibe los mensajes directos de esas cuentas (spec 081).

---

### Historia 2 — El cliente conecta su Messenger desde un enlace (Prioridad: P1)

Igual que la historia 1, desde la tarjeta de Messenger. En la página del dueño no hay pregunta: entra con Facebook y elige la Página.

**Por qué esta prioridad**: es el mismo hueco que en Instagram, y comparten la conexión.

**Prueba independiente**: un cliente sin Messenger, un enlace y un tercero que conecta una Página. Un mensaje a la Página recibe respuesta del agente.

**Escenarios de aceptación**:

1. **Dado** un enlace de Messenger, **cuando** el dueño lo abre, entra con Facebook y elige su Página, **entonces** la página dice que su Messenger está conectado y el canal aparece en el cliente.

---

### Historia 3 — Elegir entre varias cuentas o Páginas (Prioridad: P2)

Si la persona administra más de una cuenta de Instagram o más de una Página, la página del dueño le pregunta cuál conecta, con el mismo diálogo que la consola.

**Por qué esta prioridad**: sin este paso, quien administra varias cuentas no podría usar el enlace. Va después porque el caso más común es una sola cuenta.

**Prueba independiente**: una persona con dos Páginas abre un enlace de Messenger, elige la segunda y es esa la que queda conectada.

**Escenarios de aceptación**:

1. **Dado** que Meta devuelve dos Páginas, **cuando** el dueño elige una, **entonces** se conecta esa y no la otra.
2. **Dado** el diálogo de elección abierto, **cuando** el dueño lo cancela, **entonces** no se conecta nada y el enlace sigue valiendo.

---

### Historia 4 — Un enlace de WhatsApp no tropieza con Instagram ni con Messenger (Prioridad: P1)

Hoy, el enlace de WhatsApp cuenta las cuentas de Instagram y las Páginas como si fueran números. Un cliente con Instagram conectado y una plaza de número libre recibe «Este negocio ya tiene todos los números que puede conectar». La consola no los cuenta (spec 049). El enlace aplica la misma regla.

**Por qué esta prioridad**: ya puede estar pasando en producción, y al abrir los enlaces de Instagram y Messenger pasaría más.

**Prueba independiente**: un partner con un número por cliente; un cliente con Instagram y sin WhatsApp conecta un número por enlace.

**Escenarios de aceptación**:

1. **Dado** un cliente con Instagram y Messenger conectados y ningún número, con un tope de un número, **cuando** el dueño usa un enlace de WhatsApp, **entonces** el número se conecta.

---

### Casos límite

- **Enlace usado, caducado, anulado o inexistente:** los mismos mensajes que en WhatsApp. El de Instagram dice lo mismo que el de WhatsApp.
- **El dueño cierra la ventana de Meta o Meta falla:** el enlace sigue valiendo para reintentar. Reintentar repite la forma de entrar que eligió.
- **La cuenta ya está conectada a otro cliente:** se dice al dueño con el motivo de la consola, y que avise a quien le envió el enlace.
- **No se compartió la Página o faltó un permiso:** el motivo de la consola, con la invitación a volver a intentarlo aceptando todos los pasos.
- **La elección de cuenta caducó:** «La elección caducó. Vuelve a conectar», y el enlace sigue valiendo.
- **La cuenta ya estaba conectada en este mismo cliente:** se actualiza su canal y su token, como desde la consola.
- **Instagram y Messenger no están disponibles para el partner:** la tarjeta no ofrece el enlace. No hay botón apagado ni explicación (constitución §V).
- **No está configurada la conexión con Página:** la página de Instagram no pregunta y abre directamente la ventana de entrar con Instagram, como la consola (081, 1.5).

## Requisitos *(obligatorio)*

### Requisito 1 — Crear y compartir el enlace

**Historia de usuario:** Como partner, quiero enviar al cliente un enlace para que conecte él mismo su Instagram o su Messenger, como ya hago con WhatsApp.

#### Criterios de aceptación

1. WHERE Instagram y Messenger están disponibles para el partner EL sistema DEBE ofrecer «Enviar enlace al cliente» en las tarjetas de Instagram y de Messenger de Canales del cliente, y en los mismos sitios del agente donde WhatsApp lo ofrece.
2. WHEN el partner crea un enlace de Instagram o de Messenger THEN el sistema DEBE ligarlo al cliente, a ese canal y, si se crea desde un agente, a ese agente, con el mismo plazo de caducidad y de un solo uso que el de WhatsApp.
3. WHEN el partner crea un enlace de Instagram o de Messenger THEN el panel NO DEBE preguntar «¿Cómo lo conecta?»: la forma de entrar a Meta la elige el dueño en su página.
4. El panel DEBE ofrecer lo mismo que el de WhatsApp: copiar el enlace, enviarlo por WhatsApp, enviarlo por correo con el asunto de su canal («Conecta el Instagram de tu negocio», «Conecta el Messenger de tu negocio») y ver la fecha de caducidad.
5. WHEN hay enlaces pendientes de Instagram o de Messenger THEN el sistema DEBE mostrarlos en la misma lista que los de WhatsApp, cada uno con su canal, y DEBE permitir anularlos igual.
6. El sistema DEBE pedir para crear y anular estos enlaces el mismo permiso que para los de WhatsApp.

### Requisito 2 — La página del dueño para Instagram

**Historia de usuario:** Como dueño del negocio, quiero conectar mi Instagram desde el enlace sin tener cuenta en Auphere.

#### Criterios de aceptación

1. WHEN el dueño abre un enlace válido de Instagram THEN la página DEBE decir «Conecta el Instagram de {negocio}».
2. WHERE está configurada la conexión con Página EL sistema DEBE preguntar «¿Cómo entras a Meta?» antes de abrir la ventana, con las dos opciones de la consola y lo que significa cada una: «Con Facebook y tu Página», si su Instagram está vinculado a una Página, y «Con Instagram», si no lo está.
3. WHEN el dueño elige una opción THEN el sistema DEBE abrir la ventana de Meta con la misma configuración que abre la consola para esa opción (081, 1.3 y 1.4).
4. WHEN no está configurada la conexión con Página THEN el sistema DEBE abrir directamente la ventana de entrar con Instagram, sin preguntar.
5. WHEN la conexión falla y el dueño vuelve a intentarlo THEN el sistema DEBE repetir la forma de entrar que eligió.

### Requisito 3 — La página del dueño para Messenger

**Historia de usuario:** Como dueño del negocio, quiero conectar la Página de mi negocio a Messenger desde el enlace.

#### Criterios de aceptación

1. WHEN el dueño abre un enlace válido de Messenger THEN la página DEBE decir «Conecta el Messenger de {negocio}» y ofrecer entrar con Facebook, sin más preguntas.
2. WHEN el dueño entra THEN el sistema DEBE abrir la ventana de Meta con la misma configuración de Messenger que abre la consola.

### Requisito 4 — Elegir la cuenta o la Página

**Historia de usuario:** Como dueño que administra varias cuentas, quiero elegir cuál conecto.

#### Criterios de aceptación

1. WHEN Meta devuelve más de una cuenta de Instagram o más de una Página THEN la página DEBE mostrar el mismo diálogo de elección que la consola: «¿Qué cuenta de Instagram conectas?» o «¿Qué Página de Facebook conectas?».
2. WHEN Meta devuelve una sola THEN el sistema DEBE conectarla sin preguntar.
3. WHEN el dueño elige THEN el sistema DEBE completar la conexión con el mismo enlace que inició la elección.
4. IF la elección caducó THEN el sistema DEBE decir «La elección caducó. Vuelve a conectar», y NO DEBE dar el enlace por usado.
5. WHEN el dueño cancela la elección THEN el sistema NO DEBE conectar nada ni dar el enlace por usado.

### Requisito 5 — El resultado

**Historia de usuario:** Como dueño, quiero saber que quedó conectado; como partner, quiero enterarme.

#### Criterios de aceptación

1. WHEN la conexión termina THEN la página DEBE decir «¡Listo! Tu Instagram está conectado», con la cuenta, o «¡Listo! Tu Messenger está conectado», con la Página, y que puede cerrar la página.
2. WHEN la conexión termina THEN el sistema DEBE dar el enlace por usado, dejar el canal en el cliente y, si el enlace venía de un agente, en ese agente.
3. WHEN la conexión termina THEN el sistema DEBE avisar al partner igual que cuando el cliente conecta WhatsApp por enlace.
4. IF Meta rechaza la conexión THEN la página DEBE dar el motivo que da la consola (código no aceptado, Página no compartida, permiso no concedido, cuenta conectada a otro cliente, Meta no deja recibir mensajes), con lo que puede hacer el dueño. Si no depende de él, DEBE decirle que avise a quien le envió el enlace.
5. IF el dueño cierra la ventana de Meta o la conexión falla THEN el sistema NO DEBE dar el enlace por usado.
6. IF el enlace está usado, caducado, anulado o no existe THEN la página DEBE decirlo con los mismos mensajes que la de WhatsApp.

### Requisito 6 — La cuota de números

**Historia de usuario:** Como partner, quiero que el enlace cuente los canales igual que la consola.

#### Criterios de aceptación

1. El sistema DEBE contar la cuota de canales del enlace con la misma regla que la consola: las cuentas de Instagram y las Páginas no ocupan la plaza de un número de WhatsApp (spec 049).
2. WHEN se usa un enlace de WhatsApp para volver a autorizar un número que el cliente ya tiene THEN el sistema NO DEBE contarlo como otro número, igual que la consola (spec 076, 4.3).
3. WHEN se usa un enlace de Instagram o de Messenger THEN el sistema NO DEBE aplicar la cuota de números.

### Requisito 7 — Aislamiento

**Historia de usuario:** Como Auphere, quiero que un enlace solo pueda conectar canales en su cliente.

#### Criterios de aceptación

1. El sistema DEBE decidir el cliente por el token del enlace, y NO DEBE aceptar un identificador de cliente de la página.
2. El sistema DEBE hacer la conexión y la elección de cuenta bajo el ámbito del cliente del enlace.
3. IF una elección pendiente la inició otro enlace o la consola THEN el sistema DEBE rechazar que se complete con este enlace, y NO DEBE conectar nada.
4. El sistema NO DEBE poner el token en la dirección de la página donde corre la ventana de Meta, igual que en la 040.

### Entidades clave

- **Enlace de conexión**: el que ya existe para WhatsApp (spec 040). Pertenece a un cliente (`tenant_id`) y ahora dice qué canal conecta: WhatsApp, Instagram o Messenger. La forma de conectar solo la fija el partner en WhatsApp. No tiene RLS, a propósito: la página solo conoce el token (migración 0160).
- **Elección pendiente**: la que ya usa la consola entre la ventana de Meta y la elección de cuenta. Ahora recuerda desde dónde se inició, la consola o un enlace concreto, para que solo se complete desde ahí.

## Criterios de éxito *(obligatorio)*

- **CE-001**: un dueño sin cuenta en Auphere conecta Instagram desde el enlace en menos de dos minutos, y el agente contesta su primer mensaje directo.
- **CE-002**: lo mismo con Messenger y una Página.
- **CE-003**: un cliente con Instagram conectado y una plaza de número libre conecta un número de WhatsApp por enlace sin error de cuota.
- **CE-004**: ningún enlace conecta una cuenta en un cliente distinto del suyo, ni completa una elección que inició otro enlace o la consola.

## Fuera de alcance

- **Crear enlaces de Instagram o Messenger desde el panel de operador:** el panel no conecta estos canales hoy. Solo cambia lo que comparte con la consola.
- **Un enlace que conecte varios canales a la vez:** un enlace conecta un canal, como en WhatsApp.
- **Cambiar cómo conecta la consola:** la página del dueño usa la misma conexión, no una nueva.
- **TikTok:** no se usa.

## Supuestos

- **Dependencias antes de abrirlo a los partners:**
  - la T008 del hotfix 081: un DM real que llega con la conexión con Página;
  - la T072 de la 049: entrar con Instagram, probado en vivo.
- **Meta no pide una revisión nueva:** el dueño entra con las mismas configuraciones y permisos que ya usa la consola, igual que el enlace de WhatsApp usa los del registro integrado. Se confirma antes de abrir.
- **Decisiones tomadas sin Luis, para su revisión:**
  - **D1.** La forma de entrar a Instagram la elige el dueño en su página, no el partner al crear el enlace. Es el dueño quien sabe si su Instagram está vinculado a una Página.
  - **D2.** Un enlace conecta un solo canal. Para Instagram y Messenger se envían dos enlaces.
  - **D3.** La regla de la cuota del enlace es la de la consola entera, incluida la excepción de volver a autorizar un número (076, 4.3), que hoy el enlace tampoco aplica.
