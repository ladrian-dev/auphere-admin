# Especificación: Acceso a conectores por partner

**Rama**: `060-acceso-conectores-por-partner` · **Creada**: 2026-11-13 · **Estado**: Implementada en la rama, sin commit, pendiente de la revisión de Luis (2026-11-13)

**Entrada**: descripción del usuario: "Permite que desde el admin panel al seleccionar un conector pueda limitar su acceso a algún partner en particular; por defecto todos los conectores estarán disponibles para todos a menos que yo lo actualice manualmente." (2026-11-11). Y el 2026-11-13: "Para resolver el punto 2 o 3 quiero agregar una nueva funcionalidad en el admin panel para habilitar o deshabilitar conectores por partners."

## Encabezado Auphere *(obligatorio)*

| Campo | Valor |
|---|---|
| **Superficie de confianza** | `0`: el panel de operador, la consola de partners y su API, que ya existen. No se abre ninguna superficie. |
| **Garantías de aislamiento tocadas** | **2 (lista blanca de herramientas)**. La disponibilidad por partner es una capa más sobre las herramientas que un agente ve y ejecuta. Solo puede quitar, nunca añadir. **1 (RLS), rozada**: la regla es un dato de plataforma sin cliente, que se lee desde el turno de cada cliente. Las conexiones, credenciales y activaciones siguen bajo su RLS y no se tocan. |
| **Nota de KB que la justifica** | `[[decisions/2026-11-13-acceso-a-conectores-por-partner]]` en `/Users/lmatos/Work/Auphere/nexus/` |
| **Qué se mide** | **Nada.** No añade llamadas a modelos, reloj de máquina ni herramientas de pago. |

### Lo que completa

| Dónde | Qué decía | Qué pasa ahora |
|---|---|---|
| Spec 047, **35.2** y su contrato `console-api.md` §6 | La consola enseña «el catálogo disponible para el partner». | Se implementa. Hoy ningún listado filtra por partner. |

## Por qué

- **Un conector puede ser de un solo partner.** El primer caso es Quédate, la plataforma de alquileres de Amacrux (spec 061): su conector solo tiene sentido para los clientes de Amacrux. Hoy no hay forma de ofrecerlo a uno y no a los demás.
- **Hoy todo se ofrece a todos.** Ninguno de los listados que ve un partner filtra por partner: integraciones del cliente, capacidades, conectores del agente, constructor de agentes y catálogo de herramientas por cliente. Cualquier configuración que se dé de alta en Composio aparece para todos los partners al momento.
- **La 047 ya lo pedía** («el catálogo disponible para el partner», 35.2) y nunca se implementó.
- Luis decidió el 2026-11-13 gestionarlo desde el panel, habilitando o deshabilitando cada conector por partner, con todo disponible para todos por defecto.

## Escenarios de usuario y pruebas *(obligatorio)*

### Historia 1 — Auphere habilita o deshabilita conectores desde la ficha de un partner (Prioridad: P1)

Una persona de Auphere abre un partner en el panel y ve la lista de conectores con su estado para ese partner. Deshabilita uno con un motivo y, desde ese momento, ningún cliente del partner lo ve ni lo usa. Lo vuelve a habilitar y todo vuelve como estaba.

**Por qué esta prioridad**: es lo que pidió Luis y la forma más directa de operar un partner concreto.

**Prueba independiente**: deshabilitar un conector para un partner con un cliente conectado. Comprobar que el cliente no lo ve en la consola, que no puede conectarlo y que su agente no ejecuta sus herramientas. Volver a habilitarlo y comprobar que todo vuelve sin que el partner haga nada.

**Escenarios de aceptación**:

1. **Dado** un partner sin cambios, **cuando** Auphere abre su ficha, **entonces** ve todos los conectores del catálogo como habilitados, heredados del valor por defecto.
2. **Dado** un conector habilitado para un partner, **cuando** Auphere lo deshabilita con un motivo, **entonces** queda deshabilitado para ese partner, marcado como decisión propia y no heredada, y la auditoría guarda quién, cuándo y por qué.
3. **Dado** un conector deshabilitado para un partner, **cuando** Auphere elige «Como el valor por defecto», **entonces** el partner vuelve a seguir el valor por defecto del conector.

---

### Historia 2 — Auphere decide desde la ficha de un conector quién lo tiene (Prioridad: P1)

Una persona de Auphere abre un conector en el panel. Ve su valor por defecto para partners y la lista de partners con una decisión propia. Para Quédate, pone el valor por defecto en «deshabilitado» y lo habilita solo para Amacrux.

**Por qué esta prioridad**: sin un valor por defecto por conector, un partner que se dé de alta mañana vería un conector pensado para uno solo.

**Prueba independiente**: poner un conector en «deshabilitado por defecto» y habilitarlo para un partner. Comprobar que ese partner lo ve, que los demás no, y que un partner creado después tampoco lo ve.

**Escenarios de aceptación**:

1. **Dado** un conector con el valor por defecto «habilitado», **cuando** Auphere lo pasa a «deshabilitado» con un motivo, **entonces** queda deshabilitado para todo partner sin decisión propia y para los clientes sin partner.
2. **Dado** ese conector, **cuando** Auphere lo habilita para Amacrux desde la misma ficha, **entonces** Amacrux lo ve y los demás no, y la ficha de Amacrux muestra la misma decisión.
3. **Dado** un partner creado después, **cuando** abre su consola, **entonces** no ve el conector.

---

### Historia 3 — Un conector deshabilitado no llega a ninguna parte del partner (Prioridad: P1)

Para los clientes de un partner sin acceso, el conector no existe: no aparece en la consola, no se puede conectar por ningún camino y sus herramientas no corren en ningún turno ni en ningún proceso programado.

**Por qué esta prioridad**: esconderlo en la pantalla no es restringirlo. Sin esto, las historias 1 y 2 solo cambian lo que se ve.

**Prueba independiente**: con un conector deshabilitado para un partner, intentar verlo y conectarlo por cada camino (consola, panel, API de partners y consentimiento de Composio iniciado antes), y forzar que un agente del partner llame a una de sus herramientas. Todo se rechaza.

**Escenarios de aceptación**:

1. **Dado** un conector deshabilitado para un partner, **cuando** un miembro del partner abre integraciones, capacidades, conectores del agente o el constructor, **entonces** el conector no aparece. No hay botón apagado ni aviso.
2. **Dado** ese conector, **cuando** se intenta crear una conexión por cualquier vía, **entonces** se rechaza y no queda ninguna conexión nueva.
3. **Dado** un cliente del partner que ya lo tenía conectado y un agente que usa sus herramientas, **cuando** llega un mensaje, **entonces** el agente no ve ni ejecuta ninguna herramienta de ese conector, y responde con las demás.
4. **Dado** ese cliente, **cuando** el conector vuelve a estar habilitado, **entonces** su conexión, sus activaciones por agente y sus excepciones por herramienta funcionan como antes, sin que el partner haga nada.

---

### Historia 4 — Antes de quitar un acceso, Auphere ve a quién afecta (Prioridad: P2)

Antes de guardar un cambio que quita acceso, el panel enseña qué clientes tienen ese conector conectado y cuántos agentes usan sus herramientas. Auphere confirma o cancela.

**Por qué esta prioridad**: quitar un conector en uso deja a agentes sin herramientas. Tiene que ser una decisión informada, nunca una sorpresa.

**Prueba independiente**: con un cliente conectado, preparar la deshabilitación y comprobar que el panel lo nombra antes de guardar, y que cancelar no cambia nada.

**Escenarios de aceptación**:

1. **Dado** un conector conectado por dos clientes de un partner, **cuando** Auphere va a deshabilitarlo para ese partner, **entonces** ve los dos clientes y cuántos agentes usan sus herramientas, y tiene que confirmar.
2. **Dado** un conector que es el conector por defecto de un partner para dar de alta clientes, **cuando** Auphere intenta deshabilitarlo para ese partner, **entonces** el sistema lo rechaza y dice qué cambiar antes.

---

### Casos límite

- **Un conector de Composio que nadie ha conectado todavía.** La regla vale igual: se decide por el conector, no por si ya existe una conexión.
- **Un consentimiento iniciado antes de deshabilitar y completado después.** No crea una conexión utilizable.
- **Un cliente que cambia de partner.** Pasa a tener la disponibilidad de su nuevo partner desde el turno siguiente.
- **Un cliente sin partner.** Sigue el valor por defecto del conector.
- **Un partner suspendido.** Sus decisiones se conservan y se siguen mostrando, para que valgan si se reactiva.
- **Un partner que se borra.** Sus decisiones desaparecen con él.
- **Un conector retirado del catálogo.** Sus decisiones se quedan, sin efecto.
- **Dos personas de Auphere cambiando lo mismo.** Gana la última, y las dos quedan en la auditoría.
- **Si la regla no se puede leer durante un turno**, el turno se queda sin herramientas de conectores, como ya pasa hoy cuando no se puede leer la política, y queda rastro. Nunca se interpreta como «todo disponible».
- **Los canales** (WhatsApp, Instagram, Messenger, TikTok) no entran: se gestionan en Canales y en las betas por partner.
- **Google Calendar** no entra: es de sistema. Lo conecta cada profesional desde Reservas, y restringirlo dejaría sin agenda a los clientes.
- **Ausencia diseñada (constitución §V).** En la consola, un conector deshabilitado no deja rastro: ni botón apagado ni pantalla que lo explique. Editar y guardar un agente que tenía sus herramientas sigue funcionando. Esas herramientas se conservan en la ficha del agente y vuelven al rehabilitar. Ninguna otra parte de la consola las ofrece.
- **Un cliente vinculado a un partner solo por `partner_tenants`** (creado desde el panel y vinculado después) sigue a ese partner. Si está vinculado a varios, recibe lo más restrictivo.

## Requisitos *(obligatorio)*

### Requisito 1 — La regla de disponibilidad

**Historia de usuario:** Como persona de Auphere, quiero que cada conector tenga un valor por defecto para partners y que pueda decidirlo para un partner concreto, para ofrecer un conector a quien corresponde y a nadie más.

#### Criterios de aceptación

1. El sistema DEBE guardar para cada conector del catálogo un valor por defecto para partners: habilitado o deshabilitado. Al desplegar esta spec, todos están habilitados, y ningún partner ni cliente pierde nada.
2. El sistema DEBE permitir a Auphere fijar, para un par conector y partner, «habilitado» o «deshabilitado», y quitar esa decisión para volver al valor por defecto.
3. El sistema DEBE calcular la disponibilidad de un conector para un partner así: su decisión propia si la tiene y, si no, el valor por defecto del conector.
4. IF un cliente no tiene partner THEN el sistema DEBE aplicarle el valor por defecto del conector.
5. El sistema DEBE aplicar la regla a todo conector que se ofrezca a un partner, incluidos los de Composio que aún no ha conectado nadie y los que se añadan después, sin tocar esta regla. Quedan fuera los conectores que son canales y los de sistema, que no son de ningún agente: hoy, Google Calendar, que conecta cada profesional desde Reservas. El panel NO DEBE ofrecer cambiarlos.
6. El sistema DEBE hacer cumplir la regla en el servidor, de modo que una llamada directa a la API se trate igual que una desde una pantalla.
7. Solo Auphere DEBE poder cambiar la regla. Ningún partner ni cliente DEBE poder leer ni cambiar las decisiones sobre otros partners.

### Requisito 2 — Vista por partner en el panel

**Historia de usuario:** Como persona de Auphere, quiero ver y cambiar en la ficha de un partner qué conectores tiene, para operarlo sin ir conector a conector.

#### Criterios de aceptación

1. WHEN Auphere abre la ficha de un partner THEN el panel DEBE listar cada conector del catálogo con su estado para ese partner. DEBE indicar si es una decisión propia o si se hereda del valor por defecto.
2. WHEN Auphere habilita o deshabilita un conector para el partner con un motivo THEN el sistema DEBE guardarlo y auditarlo con la persona, el motivo, el valor anterior y el nuevo.
3. WHEN Auphere elige «Como el valor por defecto» para un conector con decisión propia THEN el sistema DEBE quitar la decisión y auditarlo.
4. IF Auphere intenta guardar sin motivo THEN el sistema DEBE rechazarlo.
5. El panel DEBE mostrar en esta vista los estados de carga, vacío, error, parcial e ideal.

### Requisito 3 — Vista por conector en el panel

**Historia de usuario:** Como persona de Auphere, quiero decidir en la ficha de un conector su valor por defecto y qué partners lo tienen, para restringir un conector a uno o unos pocos partners en un solo sitio.

#### Criterios de aceptación

1. WHEN Auphere abre la ficha de un conector THEN el panel DEBE mostrar su valor por defecto para partners y la lista de partners con decisión propia, cada uno con su estado.
2. WHEN Auphere cambia el valor por defecto con un motivo THEN el sistema DEBE guardarlo y auditarlo.
3. WHEN Auphere añade, cambia o quita la decisión de un partner desde esta ficha THEN el sistema DEBE guardar la misma decisión que en la vista por partner. Las dos vistas DEBEN mostrar siempre lo mismo.
4. El catálogo de conectores del panel DEBE seguir mostrando todos los conectores, y DEBE marcar los que tienen el valor por defecto en «deshabilitado» o alguna decisión propia.
5. WHERE un cliente tiene conectado un conector no disponible para su partner, la ficha de conectores de ese cliente en el panel DEBE mostrar la conexión marcada como «No disponible para su partner».
6. El panel DEBE mostrar en esta vista los estados de carga, vacío, error, parcial e ideal.

### Requisito 4 — Antes de quitar un acceso

**Historia de usuario:** Como persona de Auphere, quiero ver a quién afecta un cambio antes de guardarlo, para no dejar agentes sin herramientas por sorpresa.

#### Criterios de aceptación

1. WHEN Auphere prepara un cambio que deja un conector no disponible para algún partner o para los clientes sin partner THEN el sistema DEBE mostrar, antes de guardar:
   - los clientes afectados que lo tienen conectado, por partner;
   - cuántos agentes de esos clientes tienen activa alguna de sus herramientas.

   DEBE pedir confirmación. Aplica tanto al deshabilitar para un partner como al pasar el valor por defecto a «deshabilitado», que afecta a todo partner sin decisión propia y a los clientes sin partner.
2. WHEN Auphere cancela THEN el sistema NO DEBE cambiar nada.
3. IF el conector es el conector por defecto de un partner afectado para dar de alta clientes THEN el sistema DEBE rechazar el cambio para ese partner, nombrarlo y decir que primero se cambie su conector por defecto.
4. El sistema DEBE hacer en el servidor la comprobación del criterio 4.3 y el cálculo de afectados del 4.1, de modo que una llamada directa a la API se trate igual.

### Requisito 5 — Lo que pasa cuando un conector no está disponible

**Historia de usuario:** Como persona de Auphere, quiero que un conector no disponible para un partner no llegue a ninguna parte de sus clientes, y que vuelva intacto al habilitarlo, para restringir sin romper ni perder nada.

#### Criterios de aceptación

1. WHILE un conector no esté disponible para el partner de un cliente, la consola NO DEBE mostrarlo en ningún listado de ese cliente: integraciones, capacidades, conectores del agente, herramientas del conector y constructor de agentes. NO DEBE quedar un botón apagado ni un aviso.
2. WHILE un conector no esté disponible para el partner de un cliente, el sistema DEBE rechazar cualquier intento de crear una conexión nueva de ese conector para ese cliente. Eso incluye la consola, el panel, el alta de clientes por la API de partners y la llegada de un consentimiento de Composio iniciado antes. NO DEBE quedar ninguna conexión utilizable.
3. WHILE un conector no esté disponible para el partner de un cliente, el sistema NO DEBE ofrecer ni ejecutar ninguna herramienta de ese conector en ningún turno de ningún agente de ese cliente, empezando por el turno siguiente al cambio.
4. WHILE un conector no esté disponible para el partner de un cliente, ningún proceso programado DEBE usar la conexión de ese cliente. Hoy el caso conocido son los recordatorios de cobranza de Amigable, pero la regla vale para todos.
5. Quitar el acceso NO DEBE borrar ni cambiar de estado la conexión, sus credenciales, sus activaciones por agente ni sus excepciones por herramienta.
6. WHEN el conector vuelve a estar disponible THEN el sistema DEBE usar de nuevo la conexión, las activaciones y las excepciones como estaban, sin que el partner haga nada.
7. WHEN un miembro del partner edita y guarda un agente que tenía herramientas de un conector no disponible THEN el sistema DEBE guardarlo sin error. DEBE conservarlas, para que vuelvan al rehabilitar. La ficha del propio agente (su borrador y su versión) las sigue nombrando, porque son suyas. Ningún listado, catálogo ni constructor DEBE ofrecerlas, y NO DEBE poder añadirse una nueva.
8. IF la regla no se puede leer durante un turno THEN el sistema DEBE dejar el turno sin herramientas de conectores y registrar el fallo. NO DEBE tratarlo como «todo disponible».

### Entidades clave

- **Valor por defecto de un conector para partners**: habilitado o deshabilitado, uno por conector, identificado por el conector y no por una conexión. Es un dato de plataforma sin cliente, así que no lleva RLS de cliente: lo escribe solo Auphere y lo leen el panel, la consola y el turno.
- **Decisión de un partner sobre un conector**: el par conector y partner, con su estado (habilitado o deshabilitado), quién la tomó, cuándo y el motivo. Es un dato de partner sin cliente: lo escribe solo Auphere y desaparece con el partner.
- **Registro de auditoría**: cada cambio, con la persona, el motivo, el valor anterior y el nuevo.

## Criterios de éxito *(obligatorio)*

- **CE-001**: Auphere deja un conector disponible solo para un partner (deshabilitado por defecto y habilitado para ese partner) en menos de un minuto desde el panel.
- **CE-002**: con un conector no disponible para un partner, ninguna herramienta de ese conector se ejecuta para sus clientes, ni en un turno ni en un proceso programado, desde el turno siguiente al cambio.
- **CE-003**: volver a habilitar un conector devuelve a los agentes las mismas herramientas que tenían, sin ninguna acción del partner.
- **CE-004**: al desplegar, ningún partner ni cliente pierde ningún conector ni herramienta.
- **CE-005**: ningún cambio que quite acceso a clientes con el conector conectado se guarda sin que Auphere haya visto antes la lista de afectados.

## Fuera de alcance

- **El conector de Quédate**: es la spec 061, que nacerá deshabilitada por defecto y habilitada para Amacrux usando esta.
- **Decidir por cliente**: la granularidad es el partner. Por cliente ya existen las conexiones y las excepciones por herramienta.
- **Decidir por herramienta y partner**: por herramienta ya hay excepciones por cliente.
- **Los canales**: WhatsApp, Instagram, Messenger y TikTok se gestionan en Canales y en las betas por partner.
- **Los conectores de sistema**: Google Calendar es de Reservas, no de un agente.
- **Que un partner gestione su propio catálogo**: solo Auphere decide.

## Supuestos

- **El valor por defecto por conector lo añade esta spec.** Luis pidió habilitar o deshabilitar por partner, con todo disponible para todos. El valor por defecto hace falta para que un partner nuevo no herede un conector pensado para uno solo, como Quédate.
- Quitar el acceso no borra nada y bloquea en el turno y en los procesos programados: decisión 2 de la propuesta, aprobada por Luis el 2026-11-13.
- Un cliente sin partner sigue el valor por defecto: decisión 3, aprobada el 2026-11-13. `auphere-direct` es un partner más.
- Solo Auphere usa el panel de operador. Los permisos de quién dentro de Auphere puede cambiarlo son los mismos que para el resto de ajustes de partners.
