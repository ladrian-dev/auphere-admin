# Especificación: Editar plantillas de WhatsApp

**Rama**: `075-editar-plantillas` · **Creada**: 2026-11-23 · **Estado**: Implementada el 2026-11-23, sin commit, pendiente de probar en staging. D5, D6 y la regla de C1 las decidió el owner el 2026-11-23; D1–D4 siguen por defecto, sin objeción. **Enmendada el 2026-11-25** al ponerla sobre `develop` con la 077: un solo editor para crear y editar, también las plantillas de autenticación y el alta del panel (requisito 10, D7)

**Entrada**: el owner, el 2026-11-23: «Actualmente no tengo la opción de editar una plantilla de whatsapp desde la UI, nosotros podemos hacer eso desde la api?». La respuesta fue que no. La API de Nexus solo lista, crea y borra; Meta sí deja editar. Después pidió abrir la spec.

## Encabezado Auphere *(obligatorio)*

| Campo | Valor |
|---|---|
| **Superficie de confianza** | `0`: la consola de partners y el panel de operador, que ya existen. La única llamada nueva es una más a la API de Meta, con las mismas credenciales del cliente que ya usan crear y borrar. |
| **Garantías de aislamiento tocadas** | **1 (RLS).** La plantilla se busca por nombre e idioma dentro de la cuenta de WhatsApp de las credenciales del cliente. Esas credenciales se leen bajo su RLS. El llamante nunca da un identificador de Meta (requisito 8). El estado de plantillas que guarda Auphere no lleva RLS, porque también guarda las de la cuenta de Auphere. Toda lectura y escritura suya se filtra por la cuenta de las credenciales del cliente, como ya hace Reservas. Una prueba de aislamiento lo fija (8.6). **Nada nuevo entre negocios:** si dos clientes del mismo negocio comparten cuenta de WhatsApp, hoy ya comparten sus plantillas al crear y al borrar, y editar no cambia eso. |
| **Nota de KB que la justifica** | `[[features/2026-11-23-editar-plantillas-whatsapp]]` en `/Users/lmatos/Work/Auphere/nexus/` |
| **Qué se mide** | **Nada nuevo.** Editar una plantilla no cuesta en Meta. |

## Qué hay hoy (2026-11-23, `develop` en bfe97215)

- **Consola de partners**, sección de plantillas del canal de WhatsApp de un cliente:
  - Lista las plantillas con su estado y, si están rechazadas, el motivo y qué arreglar.
  - Deja crear, borrar y «Duplicar». «Duplicar» abre el editor con una copia llamada `<nombre>_v2`.
  - No deja editar.
- **Panel de operador**: un diálogo por cliente que lista, crea (solo el cuerpo del mensaje) y borra. No deja editar.
- **Consola lite** (el negocio): la pantalla de Reservas enseña el estado de sus seis plantillas. A una rechazada le dice «Quien gestiona tus agentes puede corregirla». Hoy no hay dónde corregirla.
- **Plantillas que Auphere manda por su nombre**:
  - Reservas, que las pide sola: `reserva_confirmada`, `reserva_pide_confirmacion`, `reserva_recordatorio`, `reserva_cambiada`, `reserva_cancelada` y `reserva_hueco_libre`. Sus variables salen de un catálogo (043, 15.8): lo que se pide a Meta y lo que se manda no pueden separarse.
  - Cobros: `recordatorio_pago_proximo` y `recordatorio_pago_vencido`, con `cliente`, `negocio`, `monto` y `fecha`.
- **Borrar y crear otra no sirve** para corregir una aprobada: Meta bloquea su nombre 30 días, y lo que la llama por nombre deja de encontrarla.

### Lo que dice Meta (leído el 2026-11-23)

Fuente: <https://developers.facebook.com/documentation/business-messaging/whatsapp/templates/template-management>.

- Se puede cambiar la categoría, el contenido y el tiempo de vida. El contenido se sustituye entero. El nombre y el idioma no cambian.
- Solo se editan las que están aprobadas, rechazadas o pausadas.
- Una aprobada admite hasta 10 ediciones en 30 días, o 1 cada 24 horas. Las rechazadas y las pausadas, sin límite.
- A una aprobada no se le puede cambiar la categoría.
- Tras editarla vuelve a revisión, y Meta la reaprueba sola si pasa.

**Por comprobar en Meta** (la documentación no lo dice). Se prueba en la cuenta de pruebas de Meta con una plantilla desechable; el resultado va a `research.md` (R2):

- **C1.** Si una aprobada se sigue pudiendo enviar mientras Meta revisa la edición.
- **C2.** Cuál de los dos límites de edición de una aprobada aplica, y qué error devuelve Meta al pasarlo.
- **C3.** En qué estado queda una rechazada justo después de editarla: en revisión o directamente aprobada.

Los requisitos valen con cualquier respuesta a C2 y C3. **C1 sí cambia algo:** Auphere solo manda plantillas aprobadas (los agentes, Reservas y cobros). Si Meta devuelve «en revisión» al editar una aprobada, Auphere deja de mandarla hasta que Meta la reapruebe. El aviso de 2.2 lo dice.

**C1, cerrada el 2026-11-23.** En la cuenta de pruebas de Meta, una aprobada editada pasa a «En revisión» al instante. Para saber si Meta seguía aceptando la versión anterior hacía falta un envío real, y el owner decidió no hacerlo: **«en revisión» no se envía**. Auphere espera a que vuelva a estar aprobada, que es lo que ya hace hoy, y el aviso de 2.2 lo dice (research R2).

## Escenarios de usuario y pruebas *(obligatorio)*

### Historia 1 — Corregir una plantilla rechazada o pausada (Prioridad: P1)

Un partner ve en la consola que Meta rechazó una plantilla, y por qué. Pulsa «Editar», cambia el texto siguiendo lo que la consola le sugiere y guarda. Meta la vuelve a mirar, con el mismo nombre. El operador puede hacer lo mismo desde el panel.

**Por qué esta prioridad**: es el caso que hoy no tiene salida. Meta no limita las ediciones en este estado, y lo que ya se envía no se rompe porque la plantilla no se estaba enviando.

**Prueba independiente**: con una plantilla rechazada en staging, editarla desde la consola. Ver que la lista enseña el estado que devuelve Meta sin el motivo anterior, que el nombre no cambia y que la auditoría guarda el antes y el después.

**Escenarios de aceptación**:

1. **Dado** una plantilla rechazada por formato, **cuando** el partner la edita y guarda, **entonces** la lista la enseña con el estado que devuelve Meta, con el mismo nombre e idioma, y sin el motivo de rechazo anterior.
2. **Dado** una plantilla pausada por quejas, **cuando** el partner cambia su texto y guarda, **entonces** la lista enseña el estado que devuelve Meta.
3. **Dado** una rechazada por categoría equivocada, **cuando** el partner cambia la categoría y guarda, **entonces** Meta la revisa con la categoría nueva.

---

### Historia 2 — Editar una plantilla aprobada (Prioridad: P2)

Un partner quiere cambiar una frase de una plantilla aprobada que ya usa. La edita y, antes de guardar, la consola le avisa: vuelve a revisión, Auphere puede dejar de mandarla hasta que Meta la reapruebe, y Meta limita cuántas veces se edita una aprobada. Confirma y guarda.

**Por qué esta prioridad**: es lo que hoy obliga a duplicar con otro nombre. Lleva más riesgo que la historia 1, porque la plantilla está en uso y Meta limita las ediciones.

**Prueba independiente**: editar una aprobada en staging. Ver el aviso, confirmar y ver el estado que devuelve Meta. Repetir hasta el límite y ver el motivo de Meta en palabras llanas.

**Escenarios de aceptación**:

1. **Dado** una plantilla aprobada, **cuando** el partner guarda un cambio, **entonces** la consola le pide confirmación antes de mandarlo a Meta.
2. **Dado** una plantilla aprobada, **cuando** se abre el editor, **entonces** la categoría no aparece como campo que se pueda cambiar.
3. **Dado** que Meta no deja editar más esa plantilla por ahora, **cuando** el partner guarda, **entonces** ve el motivo y lo que escribió no se pierde.

---

### Historia 3 — Corregir una plantilla que Auphere manda por su nombre (Prioridad: P3)

Meta rechaza `reserva_recordatorio` de un negocio. El partner la edita desde la consola. El editor le dice que Reservas la usa y qué variables tiene que llevar. Guarda, y la pantalla de Reservas del negocio la enseña con el estado que devolvió Meta.

**Por qué esta prioridad**: cierra el «quien gestiona tus agentes puede corregirla» de la consola lite. Va detrás porque añade una regla, las variables fijas, encima de la historia 1.

**Prueba independiente**: rechazar a propósito una plantilla de Reservas en staging, editarla y ver que Reservas la encuentra y la usa cuando Meta la aprueba. Intentar quitar `{{nombre}}` y ver que no deja guardar.

**Escenarios de aceptación**:

1. **Dado** `reserva_recordatorio` rechazada, **cuando** el partner quita una variable que Reservas manda, **entonces** no se puede guardar, y el editor dice qué variable falta.
2. **Dado** `reserva_recordatorio` rechazada, **cuando** el partner cambia el texto sin tocar las variables y guarda, **entonces** la pantalla de Reservas del negocio la enseña con el estado que devolvió Meta, y ya no como rechazada.

---

### Casos límite

- **En revisión, en apelación o desactivada**: no aparece «Editar». El estado ya dice por qué no se puede tocar.
- **Con partes que Auphere no sabe pintar** (por ejemplo imagen en la cabecera, botones de código, carrusel, o más botones de los que deja el editor): no aparece «Editar». El detalle dice en una línea qué parte la deja fuera y que se edita en WhatsApp Manager (D3).
- **Otra persona la cambió mientras tanto**, en la consola o en WhatsApp Manager: no se pisa ese cambio. Se avisa y se ofrece recargar (requisito 7).
- **Varios idiomas con el mismo nombre**: se edita uno y los demás no se tocan. Al contrario que borrar, que se lleva todos los idiomas de ese nombre.
- **Se quita o se renombra una variable de una plantilla que no es de Auphere**: se avisa antes de guardar de que los envíos preparados con las variables de antes fallarán, con cuántos hay en cola (requisito 5).
- **Meta no contesta o limita**: no se da nada por cambiado, y lo escrito sigue en el editor.
- **Quien solo puede ver el canal**: no ve «Editar». La ausencia se diseña (constitución §V).
- **Un cliente de solo envío** (077): crea y edita sus plantillas en el mismo diálogo y con el mismo editor que cualquier otro cliente (requisito 10.6).
- **El cliente perdió la conexión con Meta**: el mismo aviso que hoy al crear o borrar.

## Requisitos *(obligatorio)*

### Requisito 1 — Editar una plantilla rechazada o pausada

**Historia de usuario:** Como partner, quiero corregir una plantilla que Meta rechazó o pausó sin cambiarle el nombre, para no romper lo que la usa ni esperar 30 días.

#### Criterios de aceptación

1. WHERE una plantilla está rechazada o pausada y quien mira puede gestionar el canal, EL sistema DEBE ofrecer «Editar» en su fila y en su detalle.
2. WHEN se abre «Editar» THEN el sistema DEBE abrir el editor con el contenido actual de esa plantilla en ese idioma. Si está rechazada, DEBE tener a la vista lo que la consola sugiere arreglar.
3. El editor DEBE enseñar el nombre y el idioma como título, NO como campos.
4. WHERE la plantilla está rechazada o pausada, EL editor DEBE dejar cambiar la categoría entre Utilidad y Marketing. NO DEBE ofrecer Autenticación al editar: una de autenticación no se edita (3.2), y otra no pasa a serlo. _(Enmendado el 2026-11-25: desde la 077 Autenticación también se crea, y «las que hoy se pueden crear» ya la incluía.)_
5. WHEN se guarda THEN el sistema DEBE mandar a Meta la plantilla entera, con lo editado y lo demás tal cual (3.3), y DEBE enseñar el estado que devuelve Meta.
6. IF Meta rechaza la edición THEN el sistema DEBE enseñar su motivo en palabras llanas y dejar en el editor lo que se escribió, y NO DEBE dar la plantilla por cambiada.

### Requisito 2 — Editar una plantilla aprobada

**Historia de usuario:** Como partner, quiero cambiar el texto de una plantilla aprobada sin duplicarla, sabiendo antes lo que eso supone.

#### Criterios de aceptación

1. WHERE una plantilla está aprobada y quien mira puede gestionar el canal, EL sistema DEBE ofrecer «Editar».
2. WHEN se guarda un cambio en una aprobada THEN el sistema DEBE pedir confirmación antes de mandarlo a Meta. El aviso DEBE decir tres cosas: que vuelve a revisión, que Auphere puede dejar de mandarla hasta que Meta la reapruebe, y que Meta limita cuántas veces se edita una aprobada.
3. WHERE la plantilla está aprobada, EL editor NO DEBE ofrecer la categoría como campo que se pueda cambiar.
4. IF Meta responde que la plantilla no se puede editar más por ahora THEN el sistema DEBE decirlo en palabras llanas. NO DEBE llevar una cuenta propia de ediciones: la de Meta es la única.

### Requisito 3 — Lo que no se edita

**Historia de usuario:** Como partner, quiero que editar una plantilla nunca le quite algo que no toqué.

#### Criterios de aceptación

1. WHILE una plantilla está en revisión, en apelación, desactivada o en cualquier estado que Meta no deja editar, EL sistema NO DEBE ofrecer «Editar».
2. IF la plantilla lleva una parte que el editor no sabe pintar ni reenviar tal cual, o es de autenticación, THEN el sistema NO DEBE ofrecer «Editar». La regla es esa, no una lista cerrada. Ejemplos de hoy: imagen, vídeo o documento en la cabecera; botones de código, de catálogo o de formulario; carrusel; más botones de los que deja el editor. El detalle DEBE decir en una línea qué parte la deja fuera y que se edita en WhatsApp Manager.
3. El sistema DEBE mandar a Meta, tal cual, toda parte de la plantilla que la pantalla no deja editar. Lo que no se tocó NO DEBE desaparecer ni cambiar.
4. WHEN se guarda una edición que no cambia nada THEN el sistema NO DEBE llamar a Meta. En una aprobada, eso gastaría una edición.

### Requisito 4 — Plantillas que Auphere manda por su nombre

**Historia de usuario:** Como partner, quiero corregir las plantillas de Reservas y de cobros sin que Auphere deje de poder mandarlas.

#### Criterios de aceptación

1. WHERE la plantilla es una de las que Auphere manda por su nombre, EL editor DEBE decirlo y DEBE listar las variables que puede llevar. Son las seis de Reservas, con sus variables del catálogo de 043, y las dos de cobros, con `cliente`, `negocio`, `monto` y `fecha`.
2. IF en una de Reservas falta una variable del catálogo, o hay una que no está en él, THEN el sistema DEBE rechazar el guardado diciendo cuál, y NO DEBE llamar a Meta. Lo que se pide a Meta y lo que se manda no pueden separarse (043, 15.8).
3. IF en una de cobros hay una variable que Auphere no manda, o falta una que la versión actual lleva, THEN el sistema DEBE rechazar el guardado diciendo cuál, y NO DEBE llamar a Meta. Así una edición no puede romper lo que ya se manda.
4. WHEN Meta acepta la edición de una de Reservas THEN la pantalla de Reservas de la consola lite DEBE enseñarla con el estado que devolvió Meta, y ya no como rechazada.
5. WHEN Meta acepta la edición de una de Reservas THEN Reservas NO DEBE volver a pedirla a Meta. La plantilla sigue existiendo con su nombre.

### Requisito 5 — Variables que cambian

**Historia de usuario:** Como partner, quiero saber antes de guardar si mi cambio va a hacer fallar envíos ya preparados.

#### Criterios de aceptación

1. WHEN la edición quita o renombra una variable de una plantilla que no es de las del requisito 4 THEN el sistema DEBE avisar, antes de guardar, de que los envíos preparados con las variables de antes fallarán. DEBE decir cuántos de esos envíos hay en cola, si hay alguno.
2. WHEN se prepara un envío después de guardar THEN el sistema DEBE comprobar sus variables contra la versión nueva, no contra la anterior.

### Requisito 6 — Lo que se ve después de guardar

**Historia de usuario:** Como partner, quiero ver enseguida en qué estado queda la plantilla que edité.

#### Criterios de aceptación

1. WHEN Meta acepta la edición THEN la lista DEBE enseñar el estado nuevo sin recargar la página, y NO DEBE seguir enseñando el motivo de rechazo anterior.
2. WHEN Meta acepta la edición THEN el estado que Auphere guarda de esa plantilla DEBE pasar en ese momento al que devolvió Meta. Así Reservas, cobros y los envíos de agentes ven lo mismo que la lista.
3. IF el aviso de Meta con el resultado de la revisión llega antes que esa escritura THEN el sistema NO DEBE pisarlo con el estado de la respuesta, que es más antiguo. Es la misma regla que ya sigue Reservas.

### Requisito 7 — Dos cambios a la vez

**Historia de usuario:** Como partner, no quiero pisar sin saberlo el cambio que otra persona hizo en la misma plantilla.

#### Criterios de aceptación

1. IF la plantilla cambió en Meta desde que se abrió el editor THEN el sistema DEBE rechazar el guardado, decir que cambió y ofrecer recargar. El cambio puede venir de otra persona o de WhatsApp Manager. El sistema NO DEBE pisarlo.

### Requisito 8 — Aislamiento, permisos y rastro

**Historia de usuario:** Como Auphere, quiero que una edición solo pueda tocar las plantillas del cliente que se está mirando, y que quede dicho quién la hizo.

#### Criterios de aceptación

1. El sistema DEBE buscar la plantilla por nombre e idioma dentro de la cuenta de WhatsApp de las credenciales del cliente de la sesión. NO DEBE aceptar del llamante un identificador de plantilla ni de cuenta de Meta.
2. IF el nombre y el idioma no existen en esa cuenta THEN el sistema DEBE responder que no existe, igual que si fueran de otro cliente.
3. En la consola, editar DEBE pedir el mismo permiso que crear y borrar. En el panel, ser operador.
4. WHEN se edita una plantilla THEN la auditoría DEBE guardar la persona que la editó, la plantilla y el idioma, el contenido de antes y el de después, y el estado que devolvió Meta.
5. IF Meta devuelve un error THEN el registro técnico DEBE guardar su tipo y su código, NO su texto. El de Meta puede llevar el token o lo que escribió alguien.
6. Una prueba en `tests/isolation/` DEBE fijar dos cosas. Una edición pedida con la sesión de un cliente no alcanza una plantilla de la cuenta de WhatsApp de otro. Y no cambia el estado guardado de una plantilla de otra cuenta. La prueba barre todas las rutas de edición, no solo las que hoy se conocen.

### Requisito 9 — Panel de operador

**Historia de usuario:** Como operador de Auphere, quiero corregir la plantilla de un cliente desde el panel, sin entrar en WhatsApp Manager.

#### Criterios de aceptación

1. WHERE el operador abre las plantillas de un cliente en el panel, EL panel DEBE ofrecer «Editar» con las mismas reglas que la consola (requisitos 1 a 8).
2. El editor del panel DEBE dejar cambiar lo mismo que el de la consola: cabecera de texto, cuerpo, pie, botones, un ejemplo por variable y, cuando Meta lo permite, la categoría (D6).
3. Las reglas que deciden si una plantilla se puede editar y cómo se arma lo que se manda a Meta DEBEN ser las mismas en la consola y en el panel. Una regla escrita dos veces acaba diciendo dos cosas.
4. IF una variable no tiene ejemplo THEN el editor DEBE pedirlo antes de guardar. Meta no revisa variables sin ejemplo.

### Requisito 10 — Un solo editor para crear y editar

_Añadido el 2026-11-25 (D7)._

**Historia de usuario:** Como partner o como operador, quiero crear y editar cualquier plantilla con el mismo editor, sea de la categoría que sea y tenga o no agentes el cliente, para no aprender dos pantallas que dicen cosas distintas.

#### Criterios de aceptación

1. Crear y editar plantillas en la consola y en el panel DEBE hacerse con un único editor, el de `@nexus/ui`. NO DEBE haber otro formulario de plantillas en ninguna de las dos pantallas.
2. WHEN se crea una plantilla y se elige Autenticación THEN el editor DEBE pedir el texto del botón de copiar código, la caducidad (de 1 a 90 minutos, o vacía) y el aviso de seguridad, en lugar del mensaje y los botones, y DEBE enseñar el texto fijo de Meta (077, 3.1). Lo que falta y lo que se envía DEBEN salir de las mismas reglas que las demás categorías.
3. El editor DEBE enseñar el texto fijo de Meta en español solo si la plantilla es en español, también con la pantalla en otro idioma. Si la plantilla es en otro idioma, DEBE decir que Meta pone el texto en el idioma de la plantilla.
4. WHEN se pulsa «Duplicar» en una plantilla de autenticación THEN el editor DEBE abrirse en Autenticación, con su botón, su caducidad y su aviso.
5. El panel DEBE crear con el mismo editor que la consola: cabecera de texto, cuerpo, pie, botones, un ejemplo por variable, las tres categorías y los idiomas de la misma lista. Lo que el panel manda a la API al crear DEBE tener la misma forma que lo que manda la consola, y la API DEBE armar lo que se envía a Meta con la misma función para las dos (9.3).
6. Los clientes de solo envío (077) DEBEN crear y editar sus plantillas con ese mismo editor, en el mismo diálogo que cualquier otro cliente.

### Entidades clave

- **Plantilla de WhatsApp**: vive en Meta, dentro de una cuenta de WhatsApp Business, y se identifica por nombre e idioma. Tiene categoría, estado y contenido: cabecera, cuerpo, pie y botones. Es del negocio a través de las credenciales de Meta del cliente, que van bajo su RLS en `tenant_credentials`.
- **Estado guardado de una plantilla**: lo que Auphere sabe de cada plantilla por cuenta de WhatsApp: estado, motivo de rechazo y calidad. **No lleva RLS**, porque también guarda las de la cuenta de Auphere. Toda lectura y escritura se filtra por la cuenta de WhatsApp de las credenciales del cliente de la sesión.
- **Registro de auditoría**: uno por edición, con la persona, la plantilla, el antes, el después y la respuesta de Meta. Lleva el cliente de la sesión, como los de crear y borrar.

## Criterios de éxito *(obligatorio)*

- **CE-001**: un partner corrige una plantilla rechazada y la devuelve a revisión, con el mismo nombre, en menos de dos minutos desde la lista.
- **CE-002**: tras corregir una plantilla de Reservas o de cobros, ningún envío falla porque la plantilla se llame de otra manera o le falte una variable.
- **CE-003**: ninguna edición deja una plantilla sin una parte que tenía y que nadie tocó.
- **CE-004**: cada edición se puede reconstruir desde la auditoría: quién, cuándo, el antes y el después.
- **CE-005**: un negocio con una plantilla de Reservas rechazada deja de verla como rechazada en su consola lite en cuanto el partner la corrige, sin pasar por Auphere.

## Decisiones

D5 y D6 las decidió el owner el 2026-11-23. D1–D4 se tomaron por defecto y no se le preguntaron; siguen en pie mientras no diga otra cosa.

- **D1.** La plantilla se busca por nombre e idioma, nunca por el identificador de Meta. Así el llamante no da nada que alcance otra cuenta (requisito 8.1).
- **D2.** En las plantillas que Auphere manda por su nombre, el texto se edita y las variables no: las de Reservas son exactamente las del catálogo, y las de cobros no pueden perder ninguna de las que tienen ni ganar una que Auphere no manda (requisito 4).
- **D3.** Si la plantilla tiene una parte que Auphere no sabe pintar, no se ofrece editarla. Basta una línea en el detalle que diga por qué y dónde se edita (requisito 3.2). La alternativa era reenviar esas partes tal cual. Para la multimedia no vale: su ejemplo en Meta es un enlace, no un archivo subido.
- **D4.** Antes de guardar una aprobada, se pide confirmación, y Auphere no lleva cuenta de ediciones (requisito 2).
- **D5. Decidida por el owner el 2026-11-23.** Si cambian las variables de una plantilla que no es de Auphere, se avisa de cuántos envíos en cola fallarán y se deja guardar (requisito 5).
- **D6. Decidida por el owner el 2026-11-23.** El panel edita todo lo que edita la consola, no solo el cuerpo (requisito 9).
- **D7. Decidida por el owner el 2026-11-25.** Al poner la 075 sobre `develop`, el editor compartido chocaba con el formulario de autenticación que la 077 había añadido al compositor de la consola. El owner: «El OTP es un tipo de plantilla igual, así que debería ir por el flujo normal, y ese mismo flujo o componente es el que se debería estar usando para los clientes que no tienen agentes. No deberíamos estar haciendo más flujos o componentes innecesarios si ya tenemos flujos creados para ellos.» Por eso la autenticación entra en el editor compartido, el panel crea con él y el formulario propio de cada pantalla desaparece (requisito 10).

## Fuera de alcance

- **Consola lite y app móvil**: el negocio no gestiona plantillas. Sigue el «quien gestiona tus agentes puede corregirla».
- **Una herramienta de agente para editar plantillas**: ningún agente edita plantillas hoy, y abrirlo es otra decisión.
- **Cambiar el nombre o el idioma**: Meta no lo permite. Para eso sigue «Duplicar».
- **Editar el tiempo de vida**: ninguna pantalla lo enseña hoy.
- **Editar plantillas de autenticación, con multimedia, carrusel o formularios**: el editor no las pinta al editar (D3, 3.2). Las de autenticación sí se crean y se duplican con él (requisito 10); abrir su edición lo decide el owner.
- ~~**Crear en el panel con el editor completo**~~: entró el 2026-11-25 (D7, requisito 10.5).
- **Las plantillas de la cuenta de WhatsApp de Auphere** (el canal con los dueños): se gestionan aparte.
- **Avisar a quien recibe la plantilla de que cambió**: Meta no lo hace y no hace falta.

## Supuestos

- Editar en Meta no tiene coste, y la respuesta trae el estado nuevo, o al menos aceptado o no.
- La lista de la consola ya trae el contenido de cada plantilla tal como lo da Meta. Con eso basta para abrir el editor y para detectar un cambio ajeno (7.1).
- El aviso de Meta cuando cambia el estado de una plantilla sigue llegando después de una edición, y corrige el estado si la revisión termina distinta.
- Los envíos ya preparados guardan las variables que llevaban. Si Meta los rechaza porque la plantilla cambió, se ven como fallidos con su motivo, como cualquier otro fallo de envío de hoy.
