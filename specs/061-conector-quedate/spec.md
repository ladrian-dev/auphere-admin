# Especificación: Conector de Quédate

**Rama**: `061-conector-quedate` · **Creada**: 2026-11-13 · **Enmendada**: 2026-11-16 · **Estado**: En implementación (enmienda del 2026-11-16)

**Entrada**: Luis, 2026-11-11: «Necesito crear un nuevo conector de Amacrux […] El objetivo es que los agentes puedan hacer uso del mcp o conector de quedate para poder dar de alta anfitriones, etc, todo lo que la api permita. Debe tener el mismo comportamiento que cualquier conector».

El 2026-11-13: «Nuestro objetivo aquí no es crear el agente, es tener el conector completamente implementado y funcional».

El 2026-11-16, al tener acceso al entorno dev de Quédate:
- «Considera que estamos creando un conector, así que cuando ellos lo quieran usar deben colocar sus propios token o método de autenticación».
- «Comienza a trabajar en base a lo que podemos integrar, no lo que la API pueda o no, ya que ellos pueden estar trabajando en ello».
- Sus decisiones:
  - **publicar** = mandar a revisión de Quédate;
  - **KYC** = enlace y subida de documentos;
  - **herramientas de equipo**: dentro. «Nosotros estamos creando el conector; lo que ellos quieran hacer con los agentes es decisión del partner, no del conector».

> **Enmienda del 2026-11-16.** La versión del 2026-11-13 se apoyaba en la API general (`POST /register`, una contraseña generada y una clave por persona) porque era lo único documentado. Quédate publicó una **API del agente** (`/api/v1/agent/*`) con clave propia del cliente, aislada por clave y sin borrados. Esta enmienda rehace la spec sobre ella y deja sin efecto el registro con `/register`, la contraseña generada y la credencial por persona. Investigación: `[[research/2026-11-16-quedate-api-del-agente]]`.

## Encabezado Auphere *(obligatorio)*

| Campo | Valor |
|---|---|
| **Superficie de confianza** | `0`: el turno del agente y la API que ya existen. La credencial es **la clave del cliente**, guardada como cualquier conector por clave (`tenant_credentials`). No se guarda ninguna credencial por persona. Lo nuevo es **un vínculo por cliente final**: qué anfitrión de Quédate es la persona que escribe. Es un dato del tenant, no un secreto. |
| **Garantías de aislamiento tocadas** | **8 (cliente final dentro del negocio).** Una clave alcanza a todos los anfitriones que creó. Las herramientas «de la persona» toman su anfitrión del vínculo, resuelto en el servidor, y nunca de un argumento. **1 (RLS).** El vínculo va bajo la RLS del tenant, con FK compuesta y FK a `tenants`. **2 (lista blanca).** Las herramientas pasan por la activación por agente y la disponibilidad por partner (spec 060). |
| **Nota de KB que la justifica** | `[[decisions/2026-11-13-conector-quedate-alcance-v1]]` (con su cambio de premisa), `[[research/2026-11-16-quedate-api-del-agente]]` y el ADR `[[decisions/2026-11-13-adr-credenciales-de-terceros-por-cliente-final]]`, enmendado: ahora es un vínculo, no una credencial. |
| **Qué se mide** | **Nada nuevo en Auphere.** Las llamadas a Quédate no tienen coste por llamada y el turno ya se mide. |

## Por qué

- Amacrux quiere que **cualquier agente** dé de alta anfitriones en Quédate, les pida la verificación de identidad, cree sus anuncios con fotos y los mande a publicar.
- Quédate hizo una **API para agentes**. Cada cliente genera en su panel una clave con alcance `agent:onboarding` y la pega en Nexus. Esa clave solo ve los anfitriones y anuncios que creó, y no puede borrar nada.
- El conector **no decide para qué se usa**: ofrece las herramientas y el partner decide qué agente tiene cuáles (Luis, 2026-11-16).

## Escenarios de usuario y pruebas *(obligatorio)*

### Historia 1 — Un cliente conecta Quédate con su propia clave (Prioridad: P1)

El cliente genera en el panel de Quédate una clave con alcance `agent:onboarding` y la pega en su consola de Nexus. Para pruebas, indica el entorno de desarrollo. La conexión queda lista y el partner activa las herramientas que quiera en cada agente.

**Prueba independiente**: conectar con una clave que Quédate acepta y con una que rechaza; comprobar que solo la primera queda conectada.

**Escenarios de aceptación**:
1. **Dado** el conector recién desplegado, **cuando** un partner abre su consola, **entonces** no lo ve, porque nace deshabilitado por defecto (spec 060).
2. **Dado** el conector habilitado para el partner, **cuando** el cliente guarda una clave que Quédate acepta, **entonces** la conexión queda activa en el entorno elegido.
3. **Dado** una clave que Quédate rechaza, **cuando** el cliente la guarda, **entonces** la consola dice que la clave no es válida y no se activa nada.

---

### Historia 2 — La persona que escribe se da de alta como anfitriona (Prioridad: P1)

María escribe porque quiere alquilar su apartamento. El agente le pide sus datos y la da de alta. Le manda el enlace de verificación de identidad, o sube las fotos de su cédula y su selfie que ella mandó por el chat. Cuando lo termina, le dice cómo va.

**Prueba independiente**: dar de alta a una persona y comprobar que su anfitrión queda vinculado solo a ella. Comprobar que otro cliente final del mismo negocio no lo alcanza con ninguna herramienta.

**Escenarios de aceptación**:
1. **Dado** una persona sin anfitrión vinculado, **cuando** el agente la da de alta con sus datos y su correo confirmado, **entonces** Quédate crea el anfitrión y Auphere lo vincula a esa persona.
2. **Dado** una persona con anfitrión vinculado, **cuando** el agente intenta darla de alta otra vez, **entonces** no se crea otro.
3. **Dado** un correo que ya es de un anfitrión de esta clave, **cuando** el agente intenta darlo de alta, **entonces** se vincula ese anfitrión en vez de fallar.
4. **Dado** una persona vinculada, **cuando** pide verificar su identidad, **entonces** recibe el enlace de Quédate.
5. **Dado** una persona que mandó por el chat la foto de su documento y su selfie, **cuando** elige cuáles son y el agente las sube, **entonces** su KYC queda en revisión en Quédate.
6. **Dado** dos clientes finales del mismo negocio, **cuando** el segundo pregunta por su anfitrión, **entonces** no recibe nada del primero.

---

### Historia 3 — La persona crea su anuncio y lo manda a revisión (Prioridad: P1)

María describe su apartamento y manda fotos. El agente crea el anuncio en borrador, sube las fotos que ella elige y lo manda a revisión de Quédate. Puede ver sus anuncios y ocultar uno.

**Prueba independiente**: crear un anuncio con fotos de la conversación, mandarlo a revisión y comprobar que nada se publica directamente y que solo se tocan anuncios de su anfitrión.

**Escenarios de aceptación**:
1. **Dado** una persona vinculada, **cuando** el agente crea su anuncio con los datos del catálogo, **entonces** queda en borrador a nombre de su anfitrión.
2. **Dado** su anuncio y las fotos que ella mandó, **cuando** elige cuáles subir, **entonces** se suben esas y ninguna otra.
3. **Dado** su anuncio con fotos, **cuando** pide publicarlo, **entonces** queda en revisión de Quédate (`pending_approval`) y el agente lo dice así.
4. **Dado** el identificador de un anuncio que no es suyo, **cuando** el agente intenta tocarlo, **entonces** se rechaza antes de escribir nada.

---

### Historia 4 — El equipo del negocio gestiona anfitriones y anuncios (Prioridad: P2)

El equipo de Amacrux da de alta a anfitriones que no escriben ellos mismos, revisa la lista, crea anuncios a su nombre, sube fotos y los manda a revisión.

**Prueba independiente**: con las herramientas de equipo, crear un anfitrión y un anuncio para otra persona, y comprobar que solo se alcanza lo de esta clave.

**Escenarios de aceptación**:
1. **Dado** un agente con las herramientas de equipo, **cuando** lista los anfitriones o los anuncios, **entonces** recibe los de la clave, paginados.
2. **Dado** un anfitrión de la clave, **cuando** el equipo crea un anuncio a su nombre, sube sus fotos y lo manda a revisión, **entonces** queda en revisión de Quédate.

---

### Historia 5 — Cualquier agente responde sobre alojamientos (Prioridad: P2)

Un huésped busca un apartamento para unas fechas. El agente busca, le enseña uno con sus fechas ocupadas y le cotiza la estadía.

**Escenarios de aceptación**:
1. **Dado** un agente con las herramientas públicas, **cuando** busca por ciudad, fechas y huéspedes, **entonces** recibe una lista recortada.
2. **Dado** un alojamiento y unas fechas, **cuando** cotiza, **entonces** recibe el total en USD y VES, o un aviso claro si no está libre.

---

### Casos límite

- **La clave del cliente cambia.** Quédate aísla **por clave**: una clave nueva no ve los anfitriones de la anterior (comprobado en dev; 403). Los vínculos de las personas apuntan a anfitriones que ya no se alcanzan. Una herramienta de la persona que reciba 403 marca el vínculo para revisión y lo dice. No hay reintento con otra clave.
- **El alta tarda y no responde.** No se sabe si Quédate creó el anfitrión. Al repetirlo, si el correo ya existe, se busca entre los anfitriones de la clave y se vincula **solo si su teléfono es el del chat** y nadie más lo tiene vinculado (escenario 2.3, /cso del 2026-11-16). No se reintenta solo.
- **Alguien da el correo de otra persona.** Quédate dice que está tomado y el anfitrión de ese correo tiene otro teléfono, o ya es de otra persona del negocio: no se vincula, y el agente dice que lo revise el equipo del negocio.
- **Un anuncio se crea sin respuesta.** No se reintenta (Quédate no borra: un duplicado sería permanente). Queda en la auditoría.
- **Una foto equivocada.** Quédate no deja quitarla. Por eso la persona elige cuáles subir, viendo la lista numerada de las que mandó.
- **Las fotos son de hace días.** Solo se ofrecen las de las últimas 24 horas de su conversación, como máximo 20.
- **El catálogo es grande** (26 estados, 484 ciudades y 1.288 sectores). Se filtra por estado y ciudad.
- **Lo que devuelve Quédate es dato** (principio III).

## Requisitos *(obligatorio)*

### Requisito 1 — La conexión

**Historia de usuario:** Como cliente, quiero conectar Quédate con mi propia clave, para que mis agentes lo usen sin que Auphere tenga una cuenta mía.

#### Criterios de aceptación
1. El sistema DEBE ofrecer el conector `quedate` por clave, con dos campos:
   - la clave de la API del agente, secreta;
   - el entorno, no secreto y opcional. Vacío significa producción, y `dev` significa desarrollo.
2. El entorno DEBE ser una elección cerrada: producción (`api-v2.quedate.net`) o desarrollo (`dev-api.quedate.net`). Cualquier otro valor es producción. Ningún cliente ni partner DEBE poder poner otra dirección.
3. WHEN un cliente guarda la clave THEN el sistema DEBE comprobarla contra el catálogo de la API del agente del entorno elegido, antes de activar nada.
4. IF Quédate la rechaza THEN la conexión DEBE quedar para reautorizar, sin herramientas activadas. IF Quédate no responde THEN DEBE quedar guardada sin comprobar.
5. El conector DEBE nacer deshabilitado por defecto para los partners (spec 060), y conectar NO DEBE activar ninguna herramienta en ningún agente.
6. La clave NO DEBE aparecer en ninguna respuesta, registro, auditoría ni mensaje de error.

### Requisito 2 — Catálogos y herramientas públicas

#### Criterios de aceptación
1. El sistema DEBE ofrecer las ubicaciones del catálogo (estados, ciudades y sectores, con su identificador), filtradas por estado y ciudad.
2. El sistema DEBE ofrecer las opciones de anuncio del catálogo: tipos de propiedad y comodidades, con su identificador, modalidades, modos de reserva, tipos de documento y tasa BCV.
3. El sistema DEBE ofrecer, con la API general del mismo entorno y sin clave: buscar alojamientos, ver uno, cotizar una estadía y el modo de reserva de la plataforma.
4. Cada resultado DEBE caber bajo el tope de la salida de una herramienta en el turno, y NO DEBE incluir datos de contacto de un anfitrión.

### Requisito 3 — El anfitrión de la persona que escribe

#### Criterios de aceptación
1. WHEN el agente da de alta a la persona que escribe THEN el sistema DEBE crear el anfitrión en Quédate con estos datos y vincularlo al cliente final del turno, que resuelve el servidor:
   - nombre, apellido y correo;
   - tipo y número de documento;
   - fecha de nacimiento, sexo y nacionalidad (por defecto, `VEN`).
2. El teléfono del alta DEBE salir del canal del cliente final, no de un argumento: el teléfono que dio Meta o, en WhatsApp, su identificador. En Instagram y Messenger el identificador es el id de Meta y NO DEBE mandarse como teléfono: el alta va sin él (Quédate no lo exige; comprobado en dev el 2026-11-16).
3. El alta DEBE exigir que el agente confirme que leyó el correo a la persona y que ella lo confirmó.
4. IF la persona ya tiene un anfitrión vinculado y en buen estado THEN el sistema NO DEBE crear otro.
5. IF Quédate responde que el correo ya está tomado THEN el sistema DEBE buscar ese correo entre los anfitriones de la clave y vincularlo SOLO si el teléfono de ese anfitrión es el del cliente final del turno (el del canal, que nadie escribe) y ningún otro cliente final del negocio lo tiene vinculado. Si no está, o no se cumple, NO DEBE vincular nada y DEBE devolver que el correo ya es de otra cuenta. (Enmienda tras /cso del 2026-11-16: vincular por correo dejaba a cualquiera quedarse con el anfitrión de otra persona.)
6. El sistema DEBE ofrecer el estado del anfitrión de la persona: nombre, si su identidad está verificada, el estado de su documento y su selfie, y cuántos anuncios tiene. Sin correo, teléfono ni documento.
7. El sistema DEBE ofrecer su enlace de verificación de Quédate, reutilizando el último mientras le queden más de 24 horas de validez.
8. El sistema DEBE ofrecer la subida de la foto de su documento (obligatoria) y de su selfie (opcional), elegidas por número entre las fotos que la persona mandó en su conversación.
9. Ninguna de estas herramientas DEBE recibir un identificador de cliente final, de tenant, de anfitrión ni una clave. El anfitrión sale del vínculo.
10. IF Quédate responde 403 a una operación sobre el anfitrión vinculado THEN el sistema DEBE marcar el vínculo para revisión y decirlo, sin intentar otra clave.
11. WHEN se vincula un anfitrión THEN el sistema DEBE auditarlo con el cliente final, sin datos personales.

### Requisito 4 — Los anuncios de la persona

#### Criterios de aceptación
1. El sistema DEBE ofrecer crear el anuncio de la persona en borrador, a nombre de su anfitrión vinculado, con estos campos del contrato:
   - título y descripción;
   - tipo de propiedad y sector, por su identificador del catálogo;
   - dirección, apartamento y coordenadas;
   - precio por noche;
   - capacidad, habitaciones, camas y baños;
   - comodidades.
2. El sistema DEBE ofrecer subir a un anuncio suyo las fotos que la persona elija por número entre las que mandó.
3. El sistema DEBE ofrecer **mandar a revisión** un anuncio suyo (`pending_approval`) y **ocultarlo** (`hidden`). El agente NO DEBE poder publicarlo directamente (Luis, 2026-11-16).
4. El sistema DEBE ofrecer la lista de sus anuncios: identificador, título, estado y precio.
5. IF el anuncio no es de su anfitrión THEN el sistema DEBE rechazarlo antes de escribir nada.
6. Crear un anuncio, subir fotos y subir el documento de identidad NO DEBEN reintentarse solos. IF no hay respuesta THEN DEBE quedar en la auditoría.
7. Las escrituras de una misma persona DEBEN ir de una en una.

### Requisito 5 — Las herramientas de equipo

#### Criterios de aceptación
1. El sistema DEBE ofrecer, sobre **cualquier anfitrión de la clave**:
   - listar anfitriones, paginados;
   - ver uno;
   - darlo de alta;
   - pedir su enlace de verificación;
   - subir su documento y su selfie;
   - listar anuncios, paginados y opcionalmente de un anfitrión;
   - ver uno;
   - crear un anuncio a su nombre;
   - subir fotos;
   - mandarlo a revisión u ocultarlo.
2. Las fotos y los documentos DEBEN salir de la conversación del turno, elegidos por número.
3. Estas herramientas NO DEBEN publicar directamente.
4. Qué agente tiene estas herramientas lo decide el partner. El conector no las condiciona (Luis, 2026-11-16).

### Requisito 6 — Aislamiento y datos

#### Criterios de aceptación
1. Cada vínculo DEBE pertenecer a un solo tenant y un solo cliente final, con como mucho uno por conector. DEBE ir bajo la RLS del tenant, con FK compuesta al cliente final y FK a `tenants`, y borrarse con cualquiera de los dos.
2. El vínculo guarda el identificador del anfitrión y su estado mínimo. NO DEBE guardar credenciales ni datos personales.
3. Toda herramienta DEBE comprobar la conexión y la disponibilidad para el partner (spec 060) antes de llamar a Quédate.
4. Los datos personales (nombre, correo, teléfono, documento, fecha de nacimiento) NO DEBEN escribirse en registros ni en la auditoría.
5. **El inventario de `test_51`** crece en tres entradas razonadas, y nada más:
   - el correo del alta de la persona;
   - el correo y el teléfono del alta de equipo, que es una herramienta de operador.

   El número de documento y la fecha de nacimiento son datos personales que el eje no nombra: se declaran aquí.

### Requisito 7 — Lo que ve Auphere

1. La ficha del conector de un cliente en el panel DEBE mostrar cuántas personas tienen un anfitrión vinculado, cuántas están en revisión y la fecha del último vínculo. No muestra datos personales.

### Entidades clave

- **Conexión**: la clave del cliente (secreta) y su entorno (en claro), como cualquier conector por clave.
- **Anfitrión vinculado**: tenant y cliente final, con:
  - el identificador del anfitrión en Quédate;
  - el último enlace de verificación y su caducidad;
  - si está en revisión;
  - las fechas.

## Criterios de éxito *(obligatorio)*

- **CE-001**: Una persona queda dada de alta, con su enlace de verificación, en una sola conversación.
- **CE-002**: Un barrido de las herramientas encuentra exactamente tres argumentos del eje de personas: el correo de cada alta y el teléfono del alta de equipo.
- **CE-003**: La clave del cliente aparece en 0 salidas, registros y filas de auditoría.
- **CE-004**: Con el turno de una persona, 0 llamadas a Quédate tocan el anfitrión o los anuncios de otra.
- **CE-005**: 0 anuncios publicados directamente por el agente.
- **CE-006**: Una pasada real contra dev de Quédate recorre el alta, el enlace, el anuncio, las fotos y el envío a revisión con las herramientas del conector.

## Fuera de alcance

- **Publicar directamente** (decisión de Luis): solo `pending_approval`.
- **Editar** un anfitrión o un anuncio, y **quitar o reordenar fotos**: la API no lo ofrece todavía.
- **Reservas, calendario, mensajes y reseñas**: no están en la API del agente.
- **El dinero, los referidos, borrar cuentas** y la configuración de Quédate.
- **Un desplegable para el entorno** en la consola: hoy es un campo de texto opcional.

## Supuestos

- **Lo comprobado en dev es la verdad hasta que Quédate diga otra cosa.** Las pruebas usan respuestas reales capturadas en dev el 2026-11-16, sin claves ni datos de personas reales.
- **Quédate puede ampliar la API**, por ejemplo con editar o reordenar. El conector integra lo que hay y crece con ella (Luis, 2026-11-16).
- **El alcance `agent:onboarding` no se aplica hoy en dev**: la clave también alcanza la API general. El conector solo llama a lo que necesita, y se le comunica a Quédate.

## Lo que se le pide a Quédate

1. **Aplicar el alcance `agent:onboarding`.** En dev, esa clave responde en la API general, también en `/admin/api-keys`.
2. **Aislar por usuario o por agente, y no por clave**, o permitir rotar la clave sin perder los anfitriones. Hoy, cambiar la clave deja huérfanos a todos.
3. **Exigir el KYC aprobado para publicar.** En dev se publica sin él.
4. **Un `Idempotency-Key`** en las altas de anfitrión y de anuncio: sin borrados, un duplicado es para siempre.
5. **Editar** anfitrión y anuncio, y **quitar o reordenar** fotos.
6. **La API del agente en el `openapi.json`**, con sus errores y su límite de peticiones.
7. **Un aviso o webhook** cuando el KYC se aprueba o se rechaza.
8. **Que `kyc-link` diga si invalida el enlace anterior.** Cada llamada genera uno nuevo (T060).
