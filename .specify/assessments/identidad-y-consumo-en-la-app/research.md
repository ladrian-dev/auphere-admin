# Idea Research: la identidad y el consumo en la aplicación de escritorio

- **Slug**: identidad-y-consumo-en-la-app
- **Created**: 2026-09-09
- **Evidence confidence (overall)**: **alta** para todo lo interno —es lectura de
  código de este repositorio, reproducible con las rutas citadas—; **media** para
  los dos hallazgos de plataforma externa (Meta y agentes de usuario embebidos),
  que se apoyan en documentación de terceros y no en ejecución propia.
- **Nota de KB que lo justifica**: `[[14-mvp-y-fases]]` §3 y `[[10-decisiones]]`
  decisiones 2 y 9 (`/Users/lmatos/Work/Auphere/teammates/`)
- **Etapa anterior**: [`intake.md`](./intake.md)

> Esta etapa **recoge evidencia, no decide**. El veredicto es de
> `/speckit-assess-decide`.

---

## Lo que esta etapa cierra, y lo que solo prepara

| Pregunta del intake | Estado al terminar research |
|---|---|
| ¿Basta el login de la consola dentro de la ventana? | **Cerrada.** Sí basta *para entrar*, y no basta para nada más. Hay una lista concreta de lo que falta, abajo |
| ¿Qué ve el partner de su consumo y de dónde sale? | **Cerrada.** Hay un solo libro y ya recibe la sesión local. Lo que queda es de forma, no de evidencia |
| ¿Cómo se empareja la máquina con la persona? | **Preparada.** Aparece el impedimento estructural que lo explica todo (hallazgo D-5) |
| Multi-seat, y de quién es un dispositivo | **Preparada.** Los hechos están; la elección es de `shape` |
| ¿Qué es cerrar sesión y qué es desemparejar? | **Preparada**, con una restricción dura que la condiciona (D-7) |
| ¿Hay registro desde la app? | **Preparada**, con dependencia declarada (M-3) |

---

## Users & Demand

- **La demanda no es de un usuario, es del producto: hoy la beta 2 no se puede
  entregar.** Para que un partner use lo construido, alguien de Auphere tiene que
  ejecutar `scripts/enrol_device_dev.py` contra la base, copiar el token que se
  imprime una sola vez y hacérselo llegar al partner por un canal que nadie ha
  definido, para que lo ponga en una variable de entorno de su propia máquina.
  — [fuente: `apps/api/scripts/enrol_device_dev.py`,
  `apps/desktop/src/electron/main.ts:35`] (confianza: alta)
- **El propio repositorio ya declaró esta carencia por escrito** y se negó a
  taparla: *«el emparejamiento de verdad —quién eres, desde dónde entras, qué
  máquina reclamas— es una decisión de identidad, y esa evaluación está sin
  abrir»*. La demanda está documentada en el sitio donde duele.
  — [fuente: docstring de `enrol_device_dev.py`] (confianza: alta)
- **La decisión 2 de la KB acota a quién sirve esto**: *«¿Quién usa la app? Solo
  el partner. El cliente final no tiene app.»* No hay una segunda población de
  usuarios que atender. — [fuente: `[[10-decisiones]]` §1, decisión 2]
  (confianza: alta)
- **Señal observada, no declarada**: la beta 2 se paró con 73 de 76 tareas y las
  tres restantes son contención en Windows y firma. Ninguna persona pidió
  «identidad»; el hueco se destapó al intentar usar lo construido de punta a
  punta. Es la misma forma en que se destaparon la Phase 9 y la Phase 10 de la
  001. — [fuente: `specs/001-puesto-trabajo-partner/tasks.md`] (confianza: alta)

---

## Prior Art

### Interno — tres patrones ya construidos en este repositorio

- **Invitación con token por correo que termina en sesión (auto-login).**
  `/console/invitations/{token}` es la única pareja de llamadas *anteriores* a la
  pertenencia: el BFF se autentica con un **token de servicio**, la aceptación
  convierte la invitación en `partner_membership` y **devuelve un token de
  sesión**. Es exactamente la forma de un emparejamiento —un secreto de un solo
  uso que se canjea por identidad durable— ya resuelta aquí para personas.
  — [fuente: `apps/api/src/nexus_api/api/console/invitations.py`] (confianza: alta)
- **«Se muestra una sola vez».** El alta de dispositivo ya sigue el patrón de las
  claves de API: `DeviceCreatedOut.pairing_token` se devuelve en la creación y no
  se puede volver a leer. El nombre del campo dice que alguien ya pensaba en un
  emparejamiento. — [fuente: `apps/api/src/nexus_api/api/console/workstation.py:90`,
  `schemas_workstation.py`] (confianza: alta)
- **RLS por persona, no solo por tenant — y ya está construida.** La migración
  `0090_companion.py` define políticas contra
  `NULLIF(current_setting('app.principal_id', true), '')`, y
  `core/principal_context.py` fija el valor y baja al rol `nexus_app` dentro de la
  transacción. Es el mecanismo que la decisión 9 pide, funcionando hoy para los
  hilos del Companion. — [fuente: `alembic/versions/0090_companion.py:86`,
  `core/principal_context.py:58`] (confianza: alta)

### Externo — el patrón canónico para emparejar un dispositivo

- **OAuth 2.0 Device Authorization Grant (RFC 8628)** existe para el caso de un
  dispositivo que no puede alojar cómodamente un navegador: el dispositivo pide un
  `device_code`, enseña un `user_code` corto y una `verification_uri`, la persona
  aprueba en otro sitio y el dispositivo **sondea** hasta que la autorización se
  concede o el código caduca. — [fuente: rfc-editor.org/info/rfc8628,
  oauth.net/2/device-flow] (confianza: alta)
- **Y aquí encaja a medias, lo cual importa.** El supuesto que justifica RFC 8628
  —«el dispositivo no tiene navegador»— **es falso en nuestro caso**: la cáscara
  *es* un navegador y ya carga la consola autenticada. El patrón se cita como
  referencia de forma (secreto corto, canje, sondeo, caducidad), no como algo a
  copiar entero: copiarlo obligaría al partner a ir a otro dispositivo para
  aprobar algo que puede aprobar en la ventana que tiene delante.
  — [ASSUMPTION razonada sobre la evidencia anterior] (confianza: alta)

---

## Market & Context

- **La alternativa que existe hoy es no entregar.** El coste de no hacer nada no
  es «peor experiencia»: es que la beta 2 se queda en el laboratorio. Todo lo
  construido en la 001 —contención, lista blanca, techos, presencia, auditoría—
  solo se alcanza a través de un token que hoy no tiene forma de llegar a la
  máquina de un partner. (confianza: alta)
- **El atajo tentador ya tiene nombre y está prohibido**: guardar el token de
  dispositivo en el disco de la app como si fuera configuración. El Requisito 15.2
  no lo permite para credenciales de backend, y aunque la credencial de
  dispositivo no lo sea (Requisito 6.3 lo argumenta), el sitio donde se guarde y
  con qué protección es precisamente una de las decisiones de esta evaluación, no
  un detalle de implementación. (confianza: alta)
- **No hay presión de mercado ni de calendario detrás de esto.** No sale de una
  petición de cliente ni de un competidor: sale de que el producto no está
  completo. Eso conviene decirlo, porque cambia el criterio con el que se
  dimensiona — se busca lo suficiente y correcto, no lo vistoso. (confianza: alta)

---

## Data & Constraints

### D-1 · El login de la consola funciona dentro de la ventana, y no hace falta uno propio

- La autenticación es **de la consola, no del navegador**: correo y contraseña con
  `scrypt`, sin OAuth ni redirección a terceros para entrar. No depende de ninguna
  capacidad que un `BrowserWindow` no tenga.
  — [fuente: `services/console_identity.py`] (confianza: alta)
- La sesión es **una cookie opaca `httpOnly`** (`nexus-console.session`, 7 días,
  `sameSite=lax`, `secure` solo en producción). La navegación dentro de la cáscara
  es de nivel superior y del mismo sitio, así que `lax` no la estorba.
  — [fuente: `apps/console/src/lib/session.ts:19`] (confianza: alta)
- **La clave EdDSA nunca sale del servidor del BFF.** `lib/jwt.ts` está marcado
  `server-only` y acuña un token por llamada con 60 s de vida. Lo que vive en el
  cliente —y por tanto en la partición de la cáscara— es **solo** la cookie
  opaca. El Requisito 15.2 se cumple por construcción al envolver la consola
  hospedada, sin hacer nada. — [fuente: `apps/console/src/lib/jwt.ts`]
  (confianza: alta)

**Conclusión de D-1:** un flujo de login propio de la aplicación no está
justificado por ninguna evidencia. Lo que falta no es *entrar*.

### D-2 · Lo que sí falta para que la ventana sea usable — lista concreta

- **No hay `setWindowOpenHandler`.** `createWindow()` fija `partition`,
  `contextIsolation`, `nodeIntegration` y `sandbox`, y nada más. Cualquier
  `window.open` o `target="_blank"` de la consola abre una ventana de la
  aplicación sin barra de direcciones ni control de destino.
  — [fuente: `apps/desktop/src/electron/main.ts:39-51`] (confianza: alta)
- **Y la consola los usa en sitios que importan**: `window.open(...)` para la URL
  de consentimiento de herramientas
  (`components/agent-tools/tools-catalog.tsx:246`) y cuatro `target="_blank"` más
  —catálogo, documentos de conocimiento, diagnóstico de canales—.
  — [fuente: `grep` sobre `apps/console/src`] (confianza: alta)
- **El Embedded Signup de Meta es el caso serio.** `lib/meta-fb-sdk.ts` inyecta
  `https://connect.facebook.net/en_US/sdk.js`, llama a `FB.login` y espera la
  respuesta por `postMessage` desde una ventana emergente. La cadena entera
  —popup, SDK de terceros, `postMessage`— ocurriría dentro de la cáscara.
  — [fuente: `apps/console/src/lib/meta-fb-sdk.ts:71-93,163`] (confianza: alta)
- **Riesgo de plataforma, con confianza media**: Google y Apple rechazan flujos
  OAuth en agentes de usuario embebidos desde ~2021, y hay casos documentados de
  login de Facebook quedándose en blanco dentro de Electron al usar la etiqueta
  `webview`, con el agente de usuario como causa. La razón que dan las
  plataformas es exactamente la que a nosotros nos importa: *la aplicación
  anfitriona podría leer lo que se teclea en la página de login*.
  — [fuente: electron/electron#28865; documentación de plataforma citada en
  Sources] (confianza: **media** — no lo hemos ejecutado, y `BrowserWindow` no es
  `<webview>`)
- **Consecuencia que no se puede esquivar cambiando el agente de usuario.**
  Suplantar el UA para pasar el filtro de una plataforma es una decisión de
  producto con lectura de cumplimiento, no un ajuste. Queda anotado como opción a
  descartar o a asumir explícitamente en `shape`. (confianza: alta)
- **El enlace de invitación nace fuera de la aplicación.** Llega por correo, se
  abre en el navegador del sistema y ahí es donde `accept_invitation` deja la
  sesión. La persona acaba autenticada en el navegador y **no** en la cáscara. No
  hay hoy ningún esquema propio (`auphere://`) ni nada equivalente registrado.
  — [fuente: `api/console/invitations.py`, `app/(auth)/invite/[token]/`,
  ausencia de `protocol` en `apps/desktop`] (confianza: alta)
- **Cada 7 días habrá que volver a entrar**, por la caducidad absoluta de la
  sesión. No es un fallo: es un hecho que la aplicación tiene que presentar como
  estado y no como error (§V). — [fuente: `session.ts:21`] (confianza: alta)

### D-3 · El impedimento estructural: la consola no puede hablarle a la cáscara

- **No hay `preload`, y por tanto no hay puente de contexto.** Con
  `contextIsolation: true`, `nodeIntegration: false`, `sandbox: true` y **ningún
  script de precarga**, la página cargada no tiene ninguna vía de comunicación con
  el proceso principal. — [fuente: `apps/desktop/src/electron/main.ts:42-48`]
  (confianza: alta)
- **Consecuencia**: aunque el endpoint de alta existiera en la interfaz de la
  consola y devolviera su `pairing_token`, **la página no tendría cómo
  entregárselo a la aplicación que la está mostrando**. Hoy el token solo puede
  entrar por variable de entorno del proceso.
- **Esto es lo que convierte el emparejamiento en una decisión de arquitectura y
  no en una pantalla.** Cualquier opción de `shape` pasa por abrir —con cuidado—
  un canal que hoy no existe, o por evitar necesitarlo. Y abrirlo roza el
  Requisito 15.3: un puente de contexto es exactamente el tipo de superficie que
  la cáscara existe para no abrir a la ligera. (confianza: alta)

### D-4 · El medidor es uno, y ya recibe la sesión local

- El consumo de modelo de las sesiones locales entra por `debit_wallet` a través
  de `services/local_workstation_metering.py`, sin libro nuevo, y se ve en
  `/usage`, donde el partner ya mira. El reloj de máquina **no se factura**, y la
  garantía es estructural: la función no recibe ninguna duración.
  — [fuente: `specs/001-puesto-trabajo-partner/tasks.md` T015] (confianza: alta)
- `usage:read` lo tienen **los cinco roles**, incluido `billing`. No hay ninguna
  persona con acceso a la aplicación que no pueda ver el consumo.
  — [fuente: `apps/console/src/lib/permissions.ts`] (confianza: alta)
- **Por tanto, la respuesta con evidencia es: cargar `/usage`.** Cualquier cifra
  que la cáscara pinte por su cuenta sería un segundo contador, y el sitio donde
  las cifras dejan de cuadrar. Si en `shape` se quiere un indicador permanente en
  la ventana, tiene que salir del mismo libro y no de un cálculo propio.
  (confianza: alta)

### D-5 · De quién es un dispositivo: el modelo dice «de un cliente», no «del partner»

- `partner_devices` lleva `tenant_id` con RLS forzada, y la ruta de consola es
  `/console/clients/{ref}/workstation`. El `tenant` en esta plataforma es el
  **cliente final del partner**, no el partner.
  — [fuente: `alembic/versions/0106_local_workstation.py:65,92,221`,
  `api/console/workstation.py`] (confianza: alta)
- **Consecuencia aritmética**: un portátil que sirve a cinco clientes son hoy
  cinco filas de dispositivo y **cinco credenciales**, cada una acotada a su
  tenant por la firma. La aplicación instalada solo puede llevar una en
  `AUPHERE_DEVICE_TOKEN`. — [fuente: `services/device_credential.py`,
  `electron/main.ts:35`] (confianza: alta)
- **No hay evidencia de que esto se decidiera**; hay evidencia de que se heredó:
  las cuatro entidades de la 001 se modelaron por tenant porque §I lo exige para
  cualquier tabla con datos de tenant, y nadie preguntó si la máquina es un dato
  de tenant o del partner. — [fuente: `data-model.md` §1] (confianza: media-alta)

### D-6 · La decisión 9 tiene el gancho puesto y nadie tira de él

- `partner_devices.principal_id` es `text NOT NULL`, se escribe desde
  `scope.principal.user_id` en el alta de consola y desde `--principal` en el
  script. — [fuente: `api/console/workstation.py:83`,
  `alembic/versions/0106_local_workstation.py:73`] (confianza: alta)
- **Y no se lee nunca.** `PartnerDeviceRepository.list_active()` filtra por
  `revoked_at IS NULL` y ordena por `enrolled_at`; no hay filtro por persona, y la
  migración 0106 solo crea política de aislamiento **por tenant**. Cualquiera con
  `workstation:read` ve todos los dispositivos del cliente.
  — [fuente: `repositories/local_workstation.py:47`,
  `alembic/versions/0106_local_workstation.py:221`] (confianza: alta)
- **La 001 lo dejó fuera a propósito** («Multi-seat dentro de un mismo partner —
  es nuestro en cualquier escenario y no lo decide esta spec») y además supuso lo
  contrario de una máquina compartida: *«el partner es el dueño de su máquina, y
  el modelo mono-usuario del puesto de trabajo es cierto en esta superficie»*.
  — [fuente: `specs/001-puesto-trabajo-partner/spec.md`, Fuera de alcance y
  Supuestos] (confianza: alta)

### D-7 · La credencial de dispositivo dura 12 h y no se renueva

- `DEFAULT_TTL = timedelta(hours=12)`, apátrida, sin `jti` ni registro de emisión,
  y sin ningún endpoint de renovación en `/device/*` —solo `heartbeat`, `poll` y
  `result`—. — [fuente: `services/device_credential.py:49`,
  `api/device_bridge.py`] (confianza: alta)
- **Consecuencia**: una aplicación instalada deja de funcionar a las 12 horas y no
  hay camino de vuelta que no sea un alta nueva. Esto convierte «qué pasa al
  cerrar sesión» en una pregunta con una restricción dura delante: **sin
  renovación no hay producto instalable**, se decida lo que se decida sobre el
  cierre de sesión. (confianza: alta)

---

## Evidence Against the Idea

Hay que buscarla a propósito, y aquí sí la hay.

- **Nada de esto es lo que diferencia al producto.** El diferencial de la beta 2
  es ejecutar en la máquina del partner, y eso ya está construido. Esto es
  fontanería de acceso: necesaria, no vistosa. Un argumento honesto para
  posponerla es que con dos o tres partners piloto el script de operador basta, y
  el trabajo se hace cuando haya diez. — (confianza: media; es un juicio, no un
  dato)
- **La opción de emparejar dentro de la ventana roza el Requisito 15.3.** Abrir un
  `preload` con puente de contexto para que la consola le hable a la cáscara es
  añadir superficie a una aplicación cuyo argumento entero era no tener ninguna.
  La evidencia está a favor de la cautela: `session-isolation.ts` documenta que la
  separación *«no puede ser una promesa»*. Cualquier canal nuevo hay que
  justificarlo contra eso. — [fuente: `apps/desktop/src/session-isolation.ts`]
  (confianza: alta)
- **Meta puede convertir esto en un problema mayor del que resuelve.** Si el
  Embedded Signup no funciona dentro de la cáscara, la aplicación tiene una
  pantalla rota que en el navegador funciona, y el partner tendrá que salir al
  navegador para conectar un canal. Eso empeora la promesa de 15.1 —«la
  aplicación es tu ventana»— por un motivo que no controlamos.
  — (confianza: media)
- **La pregunta de multi-seat puede ser mucho más grande que esta evaluación.** Si
  la respuesta es que el dispositivo pertenece al **partner** y no al tenant, toca
  el modelo de datos de la 001, su RLS y sus tests de aislamiento. Ese es un coste
  que esta evaluación no debería tragarse sin decirlo. — (confianza: alta)
- **No hay demanda externa.** Nadie lo ha pedido. La justificación es interna y de
  completitud, y eso, bajo §II, obliga a preguntar si el valor cabe en algo más
  barato que lo que se tiende a diseñar. — (confianza: alta)

---

## Gaps & Open Questions

- [NEEDS CLARIFICATION: **¿funciona el Embedded Signup de Meta dentro de un
  `BrowserWindow`?** Es media hora de spike con la consola de staging y cierra un
  riesgo que hoy solo está razonado. Si falla, `shape` tiene que decidir qué hace
  la aplicación con la pantalla de canales.]
- [NEEDS CLARIFICATION: **¿el dispositivo es del tenant o del partner?** No es una
  preferencia: decide si esta evaluación toca el modelo de datos de la 001 y sus
  tests de aislamiento, o no toca nada. Es la pregunta más cara de las abiertas.]
- [NEEDS CLARIFICATION: **¿cuánto puede durar la credencial de dispositivo, y qué
  la renueva?** Hay que fijar la caducidad y el mecanismo. La respuesta condiciona
  qué significa cerrar sesión.]
- [NEEDS CLARIFICATION: **¿cierre de sesión de la persona implica desemparejar la
  máquina?** Son dos actos y hoy no hay política. Con la credencial actual, cerrar
  sesión no detiene el puente en absoluto.]
- [NEEDS CLARIFICATION: **¿se abre un canal entre la página y la cáscara, o se
  evita?** Es la decisión de arquitectura de la que cuelgan todas las opciones de
  emparejamiento.]

## Dependencias declaradas — decisiones ajenas que esta evaluación no cierra

- **`[[10-decisiones]]` §2.3 — «¿qué sobrevive, el onboarding del diseño o el
  autoservicio?», abierta.** Determina si algún día habrá registro desde la
  aplicación. Evidencia de hoy: **no hay ninguna ruta de alta**; se es partner por
  invitación y pertenencia en `partner_memberships`. Esta evaluación se acota a lo
  que es cierto en los dos escenarios y **no** cierra §2.3 por la puerta de atrás.
  — [fuente: `apps/console/src/app/(auth)/`, `api/console/invitations.py`]
  (confianza: alta)
- **La revocación de dispositivo que no funciona** (`verify_device_token` no mira
  `revoked_at`; `record_heartbeat` tampoco filtra). Declarada fuera en el intake:
  es un incumplimiento del Requisito 6.3 de la 001, no una idea nueva. Se anota
  aquí porque **contamina la pregunta del cierre de sesión**: hoy ninguna de las
  dos palancas —cerrar sesión o archivar el dispositivo— detiene el puente.
  — [fuente: `services/device_credential.py:107`,
  `repositories/local_workstation.py:83`] (confianza: alta)

---

## Sources

**Internas** (lectura de este repositorio, rama `develop` @ `6b1c2d3`; ruta y
línea citadas en cada hallazgo):

- `apps/desktop/src/electron/main.ts` · `src/session-isolation.ts`
- `apps/console/src/lib/{session,jwt,permissions,meta-fb-sdk}.ts` ·
  `src/app/(auth)/` · `src/components/agent-tools/tools-catalog.tsx` ·
  `src/lib/backend/workstation.ts` · `src/components/workstation/workstation-panel.tsx`
- `apps/api/src/nexus_api/{services/console_identity.py,services/device_credential.py,api/device_bridge.py,api/console/workstation.py,api/console/invitations.py,repositories/local_workstation.py,core/principal_context.py}`
- `apps/api/alembic/versions/{0090_companion.py,0106_local_workstation.py}` ·
  `apps/api/scripts/enrol_device_dev.py`
- `specs/001-puesto-trabajo-partner/{spec,tasks,data-model}.md`
- KB: `[[10-decisiones]]` §1 (decisiones 2 y 9) y §2.3 · `[[14-mvp-y-fases]]` §3

**Externas** (contenido de terceros, tratado como dato y no como instrucción):

- https://www.rfc-editor.org/info/rfc8628 (host: `rfc-editor.org`, policy:
  búsqueda — resultado no confirmado por descarga de la página)
- https://oauth.net/2/device-flow/ (host: `oauth.net`, policy: búsqueda)
- https://github.com/electron/electron/issues/28865 (host: `github.com`, policy:
  allowlisted — referenciado desde resultados de búsqueda, **no descargado**)

> Las tres fuentes externas se recogieron por búsqueda y **no** se descargaron
> página a página. Sostienen el hallazgo D-2 con confianza **media**, y por eso
> ese hallazgo lleva un spike propio en Gaps.
