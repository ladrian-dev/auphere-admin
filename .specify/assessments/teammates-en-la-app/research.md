# Research: los teammates viven en la aplicación de escritorio

- **Slug**: teammates-en-la-app
- **Created**: 2026-09-10
- **Intake**: `intake.md` (mismo directorio)
- **Método**: se leyó el artefacto v3 entero (`Auphere Web v3.dc.html`, 159.636
  caracteres, extraído a `design-v3.html`: modelo de datos del editor, roster,
  hilos, aprobaciones, avisos, plugins, roles, jobs, brains y el copy de las seis
  pantallas); se inventarió lo que existe en `apps/api`, `apps/console`,
  `apps/desktop` y `apps/edition`; se abrió el clon de KiroCrew
  (`_oss-research/kirocrew` @37933a5: `website/electron`, `website/src`,
  `dashboard/server.py`, 80 specs de módulo); se desempaquetó el binario de
  **Grok Bot 0.24.0** instalado en esta máquina (`/Applications/Grok Bot.app`,
  `app.asar` → 912 entradas) y se leyó su documentación oficial; y se leyeron las
  docs oficiales de Claude Cowork y de la app de escritorio de Claude Code, más
  reseñas de la app Codex, de ChatGPT desktop y de Copilot Actions.
- **Lo que este documento no hace**: decidir. Eso es `problem.md` → `concept.md`
  → `decision.md`. Aquí hay evidencia, con su confianza, y las preguntas que
  la evidencia no cierra.

---

## En una página

1. **El artefacto v3 describe la app, no la consola.** De sus seis pantallas y
   cuatro overlays, lo que hoy existe es *plataforma* (hilo del Companion, eventos
   con `seq`, aprobaciones durables, medidor, RLS por persona) y *administración*
   (clientes, canales, equipo, emparejamiento). Roster, hilo por teammate,
   Pendientes, Cuenta-con-uso, Crear teammate, avisos por nivel, plugins
   «Pedirla» y el panel de entorno **no existen en ninguna superficie** (§2.1).
2. **001 y 002 no malinterpretaron nada: ejecutaron la premisa que la KB tenía
   escrita** («Electron como cáscara de la web: la consola ya existe; es
   empaquetarla», `[[14-mvp-y-fases]]` §3 fila 1; «en la beta 1 la app vive
   *dentro* de la consola», ibid. §7 decisión 4). Lo que Luis cambia es la premisa,
   no la ejecución. Todo lo que 001/002 construyeron **debajo** de la pantalla
   (emparejamiento, credencial de 12 h, puente v2 con cinco operaciones, lista
   blanca, contención, presencia, aislamiento de sesiones, edición sin
   credenciales de cliente) sigue en pie y es exactamente lo que Grok Bot hace en
   su capa equivalente (§2.2, §4.1). Lo que se supera son dos frases: 001-R15.1 /
   002-R12.1 («una sola superficie propia») y la de la KB «la interfaz se hereda
   [del Companion]».
3. **Las cinco apps de referencia convergen en el mismo esqueleto** (§4.3): lista
   de sesiones/hilos a la izquierda, hilo en el centro, panel de contexto a la
   derecha; antes del primer mensaje se elige *dónde corre*, *qué carpeta* y
   *cuánta autonomía*; la tarjeta de aprobación muestra el comando exacto con
   «Permitir una vez / Permitir siempre (regla) / Denegar»; la ejecución local es
   una política **aparte y más conservadora** que el trabajo en nube (por defecto
   «preguntar»); los pasos sensibles se entregan a la persona; las rutinas corren
   en nube; hay una bandeja «esperándote»; el uso se ve dentro de la app y las
   políticas se administran en un panel que «los miembros nunca ven». La matriz
   consola/app de Luis **es** esa división, con nombres nuestros.
4. **De KiroCrew se toma más de lo que el intake suponía, pero nada de su
   pantalla** (§3): la supervisión del gateway desde Electron (arranque, espera,
   token local, propiedad del puerto, actualización), el modelo *crew* (un agente
   con oficio, workspace, memoria y modelo — el roster ya existe ahí), `members.py`
   (bitácora, reglas permanentes, *briefing* que el propio agente mantiene — el
   hueco §5.8 de la revisión del diseño), `session-control`, `file-search` con
   `@`-mención acotada a un directorio, `notifications` con tres prioridades
   idénticas a las del diseño, y que **la app sea el cliente del dashboard**
   desbloquea los subagentes que el research anterior dejó abiertos.
5. **Lo que la evidencia no cierra y hay que decidir** (§7): dónde corre el hilo
   (plataforma o edición — y con qué medidor), si la UI vive en la cáscara o es
   una web servida por la plataforma, qué hace el móvil, cómo llega la edición a
   una máquina que solo instaló la app, y qué pasa con las aprobaciones cuando
   la app está cerrada.

---

## 1. Users & Demand

- **Quién opera**: el partner y las personas de su membresía (decisión 2: «solo
  el partner usa la app»; decisión 10: «compañero del partner, para lo que
  necesite»). Cada persona tiene su hilo privado con cada teammate (decisión 9,
  RLS por `principal_id` copiada de 0090). — [fuente: `[[10-decisiones]]` §1]
  (confianza: alta)
- **Qué pide**: la frase de `[[07-competencia]]` que la KB adopta como promesa —
  «si la IA termina la tarea mientras te vas a por un café» — y la corrección de
  Luis: para que un teammate trabaje de verdad necesita **los archivos que el
  partner le dé en su computador**, y después la VM. La demanda no es un chat
  mejor: es un compañero con acceso a la máquina, bajo permiso.
- **La matriz que Luis fija** (verbatim del intake, ordenada):

  | Capacidad | Consola (administrar) | App (operar) |
  |---|---|---|
  | Membresías | Se administran | — |
  | Consumo y uso | Se ve | Se ve |
  | Teammates | **No se ven ni se usan** | Solo aquí; gastan el consumo de la membresía |
  | Clientes | Se operan | Se operan; los teammates tienen capacidades especiales para construir sus agentes |
  | Crear agentes de cliente | Sí, con el Companion | Sí, con teammates |
  | Pendientes | — | Solo aquí |

  «Una versión mejorada de Grok Bot (la app) y el platform de Claude (la
  consola)». — [fuente: mensaje de Luis, 2026-09-10] (confianza: alta en lo
  dicho; ver §7 para lo que la frase deja abierto)

---

## 2. Prior Art — interno

### 2.1 · El artefacto v3, pantalla a pantalla, contra lo que existe

Extraído del editor del artefacto (`data-v3`): props `estadoDelHilo`
(`normal · cargando · vacío · error · reconectando · parcial`), `estadoEnReposo`,
`pausaPorTope`, `mostrarInvitacion`, `companionHabilitado`; roster `AGENTS`
`{id, name, role, tone, scope, model, done, busy, unread}`; mensajes
`ask | bot | note | say | user`; notas `check | file | handoff | live | ticket`;
aprobaciones `AP` con `urgent / flagged / trial / trialDot`; `notifGroups`
Crítico / Aviso / Informativo; `PLUGINS` `auphere / on / absent` con «Pedirla»;
`ROLES` Owner / Admin / Operador / Lectura; `jobList` de 8 oficios; `brains`.

| Pantalla u overlay del diseño | Qué pinta | Existe hoy | Dónde / qué falta |
|---|---|---|---|
| **Hilo** (roster lateral + conversación + panel derecho) | Mensajes `say/ask/note`, estado del hilo, `pausaPorTope`, handoff entre teammates, ficheros adjuntos, panel de entorno `navegador/archivos/terminal` | **Parcial, y en el lugar equivocado**: el hilo existe como *drawer* del Companion en la consola (`components/companion/`, 44 archivos, 2.450 LOC, 12 tests) sobre `GET /console/companion/runs/{id}/events` (`seq/since_seq`) y `/stream`; `pausaPorTope` existe como `budget.paused` (CONTRACT-V2 §6) | Roster: **no existe** (no hay tabla de teammate). Handoff agente↔agente: **bloqueado** por el consumer secuencial (`[[14-mvp-y-fases]]` §2.4). Panel de entorno: `archivos` es el `workdir` declarado por máquina (002) y `terminal` es `shell_local` (001); `navegador` es la beta 4 |
| **Clientes / Cliente** | Lista y ficha, canales, «ver en consola» | **Sí** | `apps/console/(console)/clients/*` |
| **Pendientes** | Bandeja global de aprobaciones con `urgent/flagged`, prueba adjunta («Probada antes de proponerla»), niveles de aviso | **No** como bandeja. Las aprobaciones son durables (§IV, caducidad, idempotencia, 409) pero se pintan **dentro del hilo** (`confirm-card.tsx`); la cola del gateway local sí existe y la app ya la contesta (001-T069, `approvals-client.ts` → `/api/approvals`) | Falta la bandeja, el nivel de aviso y el «empuje» a la otra pantalla (`[[14-mvp-y-fases]]` §2.2 fila 9) |
| **Cuenta** | Membresía, uso del mes, roles, invitación | **Parcial**: membresías, roles e invitaciones existen (`partner_memberships`, spec 002 solo-invitación); el medidor existe (`/console/companion/budget`, `partner_wallet`, `budget_gate.py`) | Falta una pantalla de uso pensada para operar («cuánto queda y quién lo gasta»), no solo para facturar |
| **Crear teammate** (formulario) | Nombre, oficio (`jobList`), modelo, alcance, política de permiso, `brains` | **No** | Decisión 7 (formulario y conversación, sin roles de agente) sigue vigente |
| Overlay **Plugins** («Pedirla») | Catálogo con `auphere / on / absent` | **Parcial**: `support.request_capability` existe como herramienta `propose` con ticket (CONTRACT-V2 §4) | Falta el catálogo como pantalla |
| Overlay **Tomar control** | Ver la pantalla del agente y tomar el mando | **No** (superficie 3b, beta 6) | Fuera de esta evaluación por el intake |
| Onboarding de invitación (3 pasos) | Aceptar invitación → cuenta → primer teammate | **Parcial**: invitación y alta existen (002 D-registro); no hay «primer teammate» porque no hay teammate | — |
| Avisos por nivel | Crítico / Aviso / Informativo como política | **No** | KiroCrew trae el mismo trío (§3.3) |

Lo que la revisión previa del diseño ya había fijado y esta lectura confirma:
los cinco estados del hilo y «ninguno miente» (`[[00-revision-del-diseno-v3]]`
§3.2), la aprobación que trae su propia prueba (§3.4), los tres niveles de aviso
(§3.5), la ausencia diseñada (§3.7), «borrar no existe» (§3.9); y lo rechazado:
el agente navegando la consola (§4.1, hoy §VI), `personal` vs `team` (§4.2,
eliminado), herramientas globales (§4.3). **Ninguna de esas decisiones depende
de en qué ventana se pinte el hilo**: se trasladan a la app tal cual.
— [fuente: `design-v3.html`, `apps/console/src/components/companion/`,
`api/console/companion.py`, `docs/companion/CONTRACT-V2.md`] (confianza: alta)

### 2.2 · Lo que 001 y 002 hicieron, y qué de ello supera la nueva dirección

**No hubo malentendido: hubo premisa.** La KB escribió la beta 2 como «Electron
como cáscara de la web — la consola ya existe; es empaquetarla»
(`[[14-mvp-y-fases]]` §3, fila 1) y refinó la decisión 4 así: «en la beta 1 la
app vive *dentro* de la consola; en la 2 la consola se empaqueta» (ibid. §7). La
001 (R15) y la 002 (R12) tradujeron eso en «una sola superficie propia, la
barra». Y la beta 1 (§2) ponía la pantalla de los teammates en la consola
heredando el Companion. Luis mueve la beta 1 de sitio; **001 y 002 son la beta 2
tal como estaba escrita**. — (confianza: alta)

| Pieza construida | ¿Sigue valiendo con los teammates en la app? | Por qué |
|---|---|---|
| Emparejamiento por código, credencial de máquina de 12 h con renovación y generación, `pairing_required` a los 30 días (002 R4–R8) | **Sí, sin tocar** | Es la identidad de la *máquina*. Grok Bot hace lo mismo con otro nombre (§4.1): la app se enrola «comparable a dar de alta un portátil nuevo» |
| La persona entra con la sesión de la consola dentro de la ventana, sin credencial de backend en la app (002 R2, R3) | **Sí** | Es la regla «el Bot actúa como el miembro con sesión, nunca con más acceso que él» de Grok Bot, y la del §II. Ver §5.2 para *cómo* la UI nueva hereda esa sesión |
| Puente v2: `pair · heartbeat · poll · result · renew` + `links` (002 R4.2) | **Sí** | Es el `node-agent-coordinator` de Grok Bot (sync, offline, heartbeat) en pequeño |
| Lista blanca de ejecutables solo desde la consola, argumentos aprobados en el turno (001 R2, decisión 2.7) | **Sí** | Encaja con la matriz: la lista blanca es *administrar*. Grok Bot va más lejos en conservador («recomendamos *Never* salvo motivo») y ofrece techo por equipo |
| Contención de escrituras (6 ataques) y su variante Windows (001) | **Sí, y sube de valor** | Cowork tuvo una fuga de sandbox en julio de 2026 y ChatGPT desktop listó archivos sin permiso (§4.2): la contención probada es el foso |
| Aislamiento: tres particiones, la del agente sin cookies, la consola sin `preload` (001 R15.3, 002 R14) | **Sí como garantía; cambia la forma** | Si la app pinta su propia UI, esa vista necesita `preload` + IPC (como la barra) — la *consola* sigue sin él. Ver §5.2 |
| Presencia derivada del latido, `workdir` declarado por la máquina, `/workstation` en la consola (002 R9, R10) | **Sí** | Emparejar y vincular clientes es *administrar* |
| «Continúa en el navegador» para Meta, una sola bifurcación (002 R12.7) | **Sí** | La consola cargada dentro de la app sigue existiendo (clientes se operan desde ambas) |
| Edición sobre KiroCrew: marca, sin credenciales de cliente final, entorno de runtime (`apps/edition`) | **Sí** | Sigue siendo el sustrato; ver §3 y §6.3 (no viene con la app) |
| **001-R15.1 / 002-R12.1**: «una sola superficie propia y no reimplementar ninguna pantalla de la consola» | **Se supera** | La app pasa a tener la pantalla grande. Lo que se conserva es el espíritu: *no duplicar la consola*; la app pinta lo que la consola no tiene |
| **`[[14-mvp-y-fases]]` §2 «la interfaz se hereda: los 44 archivos del Companion son la pantalla de la beta 1»** | **Se supera en el lugar, no en el material** | Ver §2.4: el material es portable; el *drawer* no es el layout |
| 001-R13.1: dashboard y navegador del sustrato inalcanzables | **Sí** | La app es *nuestra* pantalla sobre la API del gateway, no la de KiroCrew (§3.2) |

### 2.3 · Lo que la plataforma ya tiene y la app usa sin tocar

- Hilos y ejecuciones del Companion: `GET/POST /console/companion/threads`,
  `PATCH …/{id}`, `POST …/runs`, `GET …/runs/{id}/events` (`seq`, `since_seq`,
  `available_from` → «tarea ≠ turno» resuelto), `GET …/runs/{id}/stream`,
  `DELETE …/runs/{id}`, `GET /console/companion/budget`. — [`api/console/companion.py`]
- CONTRACT-V2: 20 eventos con un solo dueño, `budget.paused` (la pausa es
  derivada, no un estado; §6), `support.ticket`, el documento de capacidades y
  límites (§5), `verify.result` con prueba en playground (§7: «probada antes de
  proponerla» ya existe como dato).
- Aprobaciones durables con caducidad, idempotencia y 409 (§IV); RLS por
  `principal_id` (0090) y por dueño de máquina (0107); `partner_wallet` y
  `budget_gate.py`; un solo medidor.
- En la máquina: `GatewayApprovals` (`/api/approvals`, `approve/deny`), el
  ejecutor con lista blanca y contención, la edición. — (confianza: alta)

### 2.4 · Los 44 archivos del Companion: cuánto viaja

Medido: 4 archivos con `"use client"`; solo 2 importan de `next`
(`companion-launcher.tsx`, `trial-panel.tsx`); el resto es React + tokens de
`@nexus/ui` + `client.ts` (fetch al BFF). `timeline`, `confirm-card`,
`composer`, `meters`, `thinking`, `verify-table`, `state.ts` (la máquina de
estados del hilo) y `use-companion.ts` **son portables a un renderer React
dentro de la cáscara** con cambios pequeños. Lo que **no** viaja es la forma:
`drawer.tsx` + `page-context.ts` son un cajón que acompaña a la página de la
consola; el diseño v3 es una ventana entera con roster a la izquierda, hilo en
medio y panel a la derecha. — [fuente: `grep` sobre `components/companion/`]
(confianza: alta en la medida; media en el coste real de portar, que no se ha
probado)

---

## 3. Prior Art — KiroCrew: qué se toma, qué no

Licencia confirmada Apache-2.0 (`LICENSE`, `NOTICE`, `THIRD-PARTY-NOTICES`);
la tabla de `[[15-kirocrew-y-alternativas]]` §5 no se reabre.

### 3.1 · La cáscara Electron (`website/electron`) — **tomar los patrones, no los ficheros**

`kirocrew-desktop` 0.7.0: Electron 43, `electron-builder`, `electron-updater`,
`electron-store`; ~80 módulos CJS pequeños y **puros, con inyección de
dependencias y `node --test`** — la misma filosofía que nuestros `bar-state.ts`
o `session-gate.ts`. Los que responden preguntas que hoy tenemos abiertas:

| Módulo | Qué resuelve | Para nosotros |
|---|---|---|
| `gateway-supervisor.js` (1.729 LOC) + `gateway-wait`, `gateway-stop`, `gateway-recovery`, `gateway-liveness`, `bundle-integrity`, `find-bin` | La app **arranca el backend empaquetado**, espera a que escuche, detecta puerto ocupado por otro proceso, reintenta, reclasifica «instalando», y lo para limpio al salir | Es literalmente el hueco «la app no instala ni arranca la edición» del intake (§6.3) |
| `local-token.js` + `token-acquire.js` | Mint de un token de dashboard contra `127.0.0.1/api/token/local` con `X-Local-Secret` leído de disco, con reintentos | Cómo la app se autentica ante **su propio** gateway sin teclear nada. Hoy `approvals-client.ts` no lleva credencial |
| `permission-handler.js` | `setPermissionCheckHandler` que concede micrófono y deniega todo lo demás, con el bug real de `webContents` nulo documentado | Nuestra vista propia necesitará esto en cuanto haya voz o cámara; hoy la consola sin preload no lo necesita |
| `hide-to-tray`, `global-hotkey`, `window-state`, `instance-guard`, `blocking-prompt`, `renderer-recovery`, `hang-recovery`, `crash-collector` | Vivir en la bandeja, atajo global de «invocar», una sola instancia, ventana que recuerda su sitio | Lo que separa una app de escritorio de una ventana con una web |
| `sandbox-profile.js` | En Linux con AppArmor restringido, la app **no puede** aplicar el perfil y solo puede *nombrar el comando* al usuario | Confirma el hallazgo del research anterior: sin techos de recursos fuera de Linux, y en Linux hace falta un paso privilegiado |
| `auto-update.js`, `update-logger.js` | `electron-updater` con log | Firma y actualización (001-T057 pendiente) |

No se copian ficheros: son CJS con `electron-store`, y nuestra cáscara es TS ESM
con vitest. Se copian **decisiones** y, donde compense, tests. — [fuente:
`website/electron/*.js`, `package.json`] (confianza: alta)

### 3.2 · El dashboard (`website/src`) — **no tomar la pantalla; tomar el vocabulario**

React + Redux Toolkit + Tailwind + Radix + i18next + TanStack Query, 306
componentes, ~880k líneas contando tests. Pensado para desarrolladores, con
marca Kiro en UI, paquetes y rutas (`~/.kiro`), y por 001-R13.1 inalcanzable
desde nuestra edición. Lo que sí merece mirarse antes de dibujar lo nuestro:
`ApprovalCard.tsx` + `ToolInputPreview.tsx` (cómo se muestra el input exacto de
una herramienta), `ApprovalModePicker.tsx`, `SessionTabStrip` /
`SessionGridView` / `SessionPulseSurveyCard` (varias sesiones a la vez, pulso de
actividad), `OnboardingFlow.tsx` (capítulos), `NotificationsPage.tsx`,
`SchedulePage.tsx`, `KiroCrewAgentsPage.tsx` (el roster de *crews*). —
(confianza: alta en el inventario; el diseño v3 ya fija nuestra forma)

### 3.3 · El backend del gateway — **lo que la app puede pedirle por `localhost`**

Rutas de `dashboard/server.py` y specs de módulo:

| Capacidad | Ruta / módulo | Encaje con el diseño |
|---|---|---|
| **Crew** = agente con oficio, `workspace`, `memory_store`, `model`, `reasoning_effort`, `triggers`, `avatar`; `select_crew` | `crew-mode.md`, `config/sections.py` `KiroCrewAgentConfig` | **Es el roster** (`AGENTS.role/model/scope`) ya modelado en el sustrato |
| Espacio por miembro: bitácora de actividad, hilo DM, **reglas permanentes**, ***briefing* que el propio agente mantiene** | `members.py` | El hueco «no hay memoria ni instrucciones de equipo» (`[[00-revision-del-diseno-v3]]` §5.8) y los `brains` del diseño |
| Chat y envío | `/api/chat`, `/api/send-message`, `/api/session-keepalive`, `/api/session-directive` | El hilo, si corre en la edición (§5.3) |
| Control de sesiones: crear, parar, cerrar, **enviar a otra sesión**, leer cola | `session-control.md` (5 herramientas MCP, rutas estrictamente internas) | El handoff Sofía→Nilo del diseño, sin tocar el consumer de plataforma |
| Subagentes con `on_tool_approval` enrutado al sistema de aprobaciones; techo auto-dimensionado (suelo 3, techo 32), 3 h, 100 turnos | `subagent.md`, `/api/spawn` | **Responde el gap «¿subagentes sin dashboard?» del research anterior: la app es el cliente** |
| TaskRunner: spec → pasos → ejecución con tests, reintentos, *checkpoints*, worktrees, pausa/reanudación | `taskrunner.md`, `/api/taskrunner` | «Tarea ≠ turno» en local; el diseño lo llama *jobs* |
| Rutinas | `/api/crons`, `heartbeat.md` (`HEARTBEAT.md`, `HEARTBEAT_KEEP`) | Las «Routines» de Grok Bot; fuera de la beta 1 por la KB |
| `@`-mención de ficheros y **directorios** acotada a un `project` canonizado (`realpath`, raíz segura) | `file-search.md`, `GET /api/file-search` | «Los archivos que el partner le dé acceso» con la disciplina de 001 (directorio fijado) |
| Notificaciones con prioridad `critical / default / passive`, `group_key`, acciones **solo a rutas internas** | `app-notifications.md`, `/api/notifications/push` | Idéntico al trío Crítico / Aviso / Informativo del diseño y a «no enlaces externos» de §III |
| Política de herramientas por sesión | `/api/session-tool-policy` | Permisos como reducción de interrupciones (§3.6 de la revisión) |
| Computer use (accesibilidad, macOS y Windows), **apagado hasta que el operador lo activa en un fichero que el agente no puede leer**; PiP de lo que el modelo ya vio | `computer-use.md` | 3b, beta 6. Se anota: el *keystone enable* fuera de banda es el patrón correcto |
| Auth del dashboard: token HMAC, cookie + refresh, `POST /api/auth/mobile-link` | `dashboard-token-auth.md` | Cómo un cliente local se autentica; no aplica a la persona (esa es la consola) |

Los seis puntos en contra del research de KiroCrew siguen vigentes y **dos
suben** al correr en la máquina del partner: la herencia de servidores MCP del
usuario (`--strict-mcp-config` sin verificar) y la falta de techos de recursos
fuera de Linux. — [fuente: `kirocrew-como-sustrato/research.md` §Evidence
Against] (confianza: alta)

---

## 4. Prior Art — externo: cómo lo hacen

### 4.1 · Grok Bot (xAI / Cursor), leído del binario y de la doc oficial

**Binario** (`/Applications/Grok Bot.app`, `com.anysphere.sand` 0.24.0, 361 MB,
nombre interno `sand`): Electron; `dist/electron-main/main.cjs` (8,7 MB);
**cuatro procesos aparte**: `local-exec-daemon` (4 MB: `pty`, `cwd`, `policy`,
`sandbox`, `approval`, `allowlist/denylist`, socket `.sock`, `tree-sitter-bash`
para entender el comando antes de aprobarlo), `node-agent-coordinator` (`sync`,
`offline`, `transcript`, `heartbeat`), `host-main` con *workers* de aislamiento
por agente (`agent-store-worker`, `transcript-mirror-worker`, índice de búsqueda
de contenido) y dos nativos (`sand-webauthn-signer` para passkeys,
`sand-op-launcher`). Login **OAuth** (Cursor, SSO en equipos), `safeStorage`,
esquemas `grokbot://` y `sand://`, `powerMonitor`, `autoUpdater` (Squirrel),
`showOpenDialog` una sola vez (elegir carpeta). Renderer: StyleX + Base UI +
Lingui (en, de, fr, es, pt) + TanStack Query + Tiptap con menciones; Sentry,
Statsig, OpenTelemetry. Descripciones de uso pedidas al SO: audio, bluetooth,
cámara, micrófono. — [fuente: `Info.plist`, `app.asar` extraído] (confianza:
alta)

**Vocabulario de su UI**, sacado de los *chunks*: «New Bot or Channel», «Routines
are recurring tasks this Bot runs on a schedule», «Routines paused while you were
away», «Waiting for you», «Take over the computer», «Execution on Local
Computer», «Always allow / Deny once (Esc) / Never allow», «Usage & Billing»,
«Plugins / Connectors / Skills», «Invite people», «Sign in to create shared
groups».

**Modelo** (doc oficial): el Bot vive en un **ordenador en nube persistente**
(una microVM Firecracker por persona, compartida por todos sus Bots; «no son
fronteras de seguridad entre sí»), con `/workspace` durable, navegador con
sesiones persistentes y terminal. La máquina local es **opcional y aparte**:
«Execution on Local Computer» con política *ask every time / always allow /
never*, aprobación por comando por defecto mostrando el comando exacto, techo
por equipo, y «recomendamos *Never* salvo motivo». La tarjeta de aprobación
muestra «la operación propuesta y sus entradas: objetivo, alcance y valores»;
reglas «Require Approval» y «Always Allow», y **si ambas encajan gana Require
Approval**. Pasos sensibles (contraseña, passkey, 2FA, CAPTCHA, pago) → *secure
handoff*: el Bot entrega el ordenador a la persona. Los Bots «actúan como el
miembro con sesión y no pueden tener más acceso que él»; los tokens de conectores
«nunca se guardan en el ordenador». Rutinas, *skills* (procesos que salieron bien
convertidos en flujos reutilizables con sus puntos de aprobación), chats de grupo
de 2–6 Bots con paso de propiedad. Admin: «Members never see this page» (el
dashboard de Cursor: enable global, controles de red, *Action Recording* 90 días,
export OTel); «usage follows the seat's allowance», límites semanales de tokens;
iPhone como *companion* que sincroniza. Sin auto-hospedaje. — [fuente:
docs.x.ai/grok-bot/{approvals-security-and-privacy, computer-and-apps,
teams-and-enterprises, security}, Vellum, Composio] (confianza: alta)

**Lectura para nosotros**: Grok Bot es «nube primero, local opcional». Auphere
hoy es lo contrario (001: el loop en plataforma, la máquina ejecuta
`shell_local`; la VM es la beta 5). Las dos formas comparten la capa que ya
tenemos; lo que Grok Bot añade y nosotros no es la separación **por proceso** del
ejecutor local (nuestro equivalente es la edición) y la política de ejecución
local **como ajuste de la persona con techo del administrador**, no solo como
lista blanca.

### 4.2 · Claude, OpenAI, Microsoft

- **Claude Cowork** (GA 2026-04-09, todos los planes de pago): la persona conecta
  **carpetas concretas** (con «folder instructions» que el agente puede
  actualizar); tres modos *Manually approve / Automatically approve (con
  clasificadores de exfiltración e inyección; si bloquea repetidamente vuelve a
  preguntar) / Skip*; **borrar siempre pide confirmación**; `/schedule` corre en
  nube «sin que el ordenador esté despierto»; las sesiones no se comparten, los
  artefactos sí; «consume más uso que chatear», *Auto* aún más. Desde julio las
  sesiones corren **en nube por defecto** y la app de escritorio es «el puente a
  carpetas, navegador y apps locales»; en julio de 2026 se documentó una **fuga
  del sandbox local** en macOS con recomendación de rotar credenciales. —
  [fuente: support.claude.com, AppleInsider 2026-07-27] (confianza: alta)
- **Claude Code, app de escritorio**: sesiones en la barra lateral, cada una con
  su carpeta y su *worktree*; **antes del primer mensaje** se elige entorno
  (Local / Cloud / SSH / WSL), carpeta, modelo y **modo de permiso** (Manual,
  Accept edits, Plan, Auto, Bypass — este último solo en sandbox); tarjeta
  «Allow once / Always allow / Deny» al tocar un dominio externo; revisión de
  diff con comentarios por línea; **anillo de uso** junto al selector de modelo
  (sesión + plan); notificación del SO al terminar si no estás mirando; mensajes
  entre sesiones como tarjetas con remitente; **archivar exige aprobación humana
  incluso en Auto**. Problemas reales de campo: carpetas bajo `~/Documents` y
  `~/Library/CloudStorage` fallan por TCC con errores poco claros (issues
  #32584, #34554, #51984). — [fuente: code.claude.com/docs/en/desktop, GitHub]
  (confianza: alta)
- **Codex app** (macOS, 2026-02-02; Windows con control total en mayo):
  proyectos → hilos, cada hilo con su *worktree*; Local / Worktree / Cloud
  explícito; automatizaciones con destino (Slack…); las reseñas señalan **sin UI
  de aprobación clara y sin indicador de uso**. — [fuente: Verdent,
  IntuitionLabs] (confianza: media — reseñas, no doc)
- **ChatGPT desktop** (2026-07-09: Chat, Work y Codex en una ventana): *Work*
  usa archivos y apps locales «solo cuando el plan y el espacio lo permiten y tú
  das permiso»; *Work with Apps* pide Accesibilidad y Grabación de pantalla; un
  incidente público de listado de archivos sin permiso. — [fuente: OpenAI help,
  wccftech] (confianza: media)
- **Copilot Actions / Agent Workspace** (Windows 11): el agente corre en una
  **sesión hija de escritorio remoto con su propia cuenta**, apagado por defecto,
  pide acceso a **seis carpetas conocidas** y debe solicitar más; agentes
  firmados. — [fuente: BleepingComputer, Windows Forum] (confianza: media)

### 4.3 · Lo que converge — el esqueleto de una app «de clase mundial» en 2026

1. **Tres columnas**: lista de teammates/sesiones · hilo · contexto (entorno,
   archivos, uso). El diseño v3 ya es esto.
2. **Antes de hablar, tres elecciones**: dónde corre, qué carpeta, cuánta
   autonomía. Nosotros: máquina emparejada (002) · `workdir` por cliente (002) ·
   política del teammate (por definir).
3. **La aprobación enseña el comando exacto** y ofrece *una vez / siempre (regla) /
   denegar*; la regla restrictiva gana. Nuestro `confirm-card` enseña el cambio y
   su prueba; falta la regla «siempre» (KiroCrew: `session-tool-policy`).
4. **La ejecución local es una política aparte y más conservadora**, por defecto
   «preguntar», con techo del administrador. Nosotros: lista blanca en consola +
   argumentos en el turno. Falta el ajuste de la persona.
5. **Lo sensible se entrega a la persona**; ninguna credencial pasa por el hilo.
   Ya es §II/§III y decisión 2.7.
6. **Rutinas corren en nube**, no en el portátil («paused while you were away»).
   Fuera de la beta 1, pero decide dónde vive el loop (§5.3).
7. **Bandeja «esperándote»** y notificación al terminar o al necesitar
   aprobación; el móvil aprueba. Es Pendientes + niveles de aviso.
8. **El uso se ve dentro de la app**; las políticas y el enable global viven en
   un panel «que los miembros nunca ven». Es la matriz de Luis.
9. **Sesiones privadas por persona, artefactos compartibles.** Decisión 9.
10. **Todos han tenido incidentes de acceso local**: la contención probada (001)
    es el diferencial, no un coste.

Donde Auphere **no** converge y debe decirlo: los teammates están **atados a
clientes** (tenants con RLS) y a un **solo medidor**; el permiso es lista blanca
por cliente y no política global; y el handoff entre teammates es un hilo
legible, no un chat de grupo.

---

## 5. Data & Constraints

### 5.1 · Restricciones que no se reabren
§I–§IX de la constitución; 001-R13.1; 001-R15.3 / 002-R14 (la sesión de la
persona no es alcanzable desde el agente; la consola no tiene canal con la
cáscara); decisiones 2, 7, 8, 9, 10, 11; un solo medidor.

### 5.2 · Con qué credencial habla la UI nueva — **hallazgo**
La cáscara tiene hoy dos identidades: la **sesión de la persona** (cookies en
`persist:auphere-console`, sin `preload`) y la **credencial de la máquina** (12 h,
`svc:"device"`). Una UI de teammates propia necesita llamar a la plataforma
*como la persona*. Tres caminos, medidos contra lo que existe:

| Camino | Credencial | Coste | Veredicto de la evidencia |
|---|---|---|---|
| A. Web servida por la plataforma (otra ruta de la consola o app aparte) cargada en la partición de la persona | La misma sesión; el BFF acuña los tokens de 60 s | Cero credenciales nuevas; el aislamiento de 002 se conserva tal cual | Compatible con R14; la «segunda superficie» sigue siendo web |
| B. React dentro de la cáscara (`preload` + IPC), y el proceso principal llama al BFF con `session.fromPartition(...).fetch` — como hace hoy `consoleWhoami` | La misma sesión, desde el proceso principal | Una vista con preload (como la barra) y un cliente IPC | Compatible; la consola sigue sin preload |
| C. La UI llama a la API con la credencial de la máquina | `svc:"device"` | Ninguno de infra | **Descartado por principio**: la máquina no es la persona; rompería RLS por `principal_id` y «el teammate actúa como el miembro» |

— [fuente: `apps/desktop/src/electron/adapters.ts`, `session-isolation.ts`,
`device_credential.py`] (confianza: alta)

### 5.3 · Dónde corre el hilo — dos loops existen hoy
- **Plataforma**: el loop del Companion (`make_investigate`, Dramatiq,
  checkpointer, LiteLLM, medidor) con herramientas sobre la superficie 0 y
  `shell_local` por el puente (001). El móvil y la web pueden pintar este hilo.
- **Edición**: el loop del sustrato (harness `claude`/kiro-cli) en la máquina,
  con sus propias herramientas de ficheros y sus subagentes. El research anterior
  midió que **sus llamadas al modelo salen por el harness, no por LiteLLM**: si
  el hilo del teammate corriera ahí, habría un segundo camino de facturación
  fuera del medidor salvo que la edición enrute el modelo por la plataforma
  (no verificado). — [fuente: `kirocrew-como-sustrato/research.md` spike 1]
  (confianza: media)

### 5.4 · Tamaños
Companion: 44 archivos / 2.450 LOC. KiroCrew `website/src`: ~880k líneas.
Grok Bot: 171 *chunks* de renderer, main 8,7 MB, daemon local 4 MB. La barra
nuestra: HTML+CSS+TS sin framework. Un renderer React en la cáscara sería el
primer *build* de UI del paquete `apps/desktop` (hoy `tsc` + copia).

### 5.5 · Empaquetado de la edición
`apps/edition` construye una rueda del sustrato (`build-substrate-wheel.sh`) y
verifica la composición; la app **asume** `localhost:5476`. Grok Bot resuelve lo
mismo metiendo el daemon dentro del `.asar`; KiroCrew lo resuelve con
`gateway-supervisor` sobre un backend empaquetado. Python 3.12 dentro de un
`.app`/`.exe` firmado es trabajo propio (001-T057 sigue pendiente).

---

## 6. Evidence Against the Idea

1. **Una segunda pantalla grande es un segundo frontend**. La consola (Next) y la
   app (React en cáscara, o web aparte) divergen salvo disciplina: la barra ya
   necesitó `copy-tokens.mjs` porque `@theme` solo lo entiende Tailwind. El camino
   A de §5.2 evita la divergencia; el B la paga. — (confianza: alta)
2. **«Teammates solo en la app» quita la red de seguridad**: si la máquina está
   apagada, nadie habla con su teammate ni aprueba nada. Cowork movió las
   sesiones a nube por esto; Grok Bot tiene iPhone; Claude Code notifica al móvil
   y el móvil aprueba. Las aprobaciones durables caducan (§IV): Pendientes «solo
   en la app» necesita decir qué pasa mientras la app no está. — (confianza: alta)
3. **Sin edición empaquetada la promesa es falsa en una máquina limpia**: «el
   teammate trabaja con los archivos del partner» exige que la app traiga o
   instale el sustrato. Hoy no lo hace. — (confianza: alta)
4. **Más superficie local = más radio de explosión.** Los tres grandes tuvieron
   incidentes en 2026; TCC en macOS (`~/Documents`, CloudStorage) es coste de
   soporte real. La lista blanca y la contención de 001 son la respuesta; no hay
   que aflojarlas para «parecerse» a una política *always allow*. — (confianza: alta)
5. **Dos loops**: construir la UI de teammates sobre el loop de plataforma **y**
   sobre el del gateway duplica el modelo de estados y los eventos. Hay que
   elegir uno para el hilo, y el otro queda como ejecutor. — (confianza: alta)
6. **El medidor**: si el hilo corre en la edición, el modelo se paga fuera del
   medidor salvo que se enrute (§5.3). «Un solo medidor» es principio, no
   preferencia. — (confianza: media)
7. **Los subagentes del sustrato necesitan la app abierta** (la app es el
   cliente que aprueba): es la misma dependencia de «máquina encendida» del
   punto 2, con otro nombre. — (confianza: alta)

---

## 7. Gaps & Open Questions

- [NEEDS CLARIFICATION: **¿Dónde corre el hilo del teammate?** (a) en plataforma
  —el loop del Companion, con la máquina como ejecutor por el puente, el móvil
  y la web pueden verlo, un solo medidor sin más trabajo— o (b) en la edición
  —acceso a ficheros nativo, subagentes del sustrato, pero el hilo vive en la
  máquina y hay que enrutar el modelo por la plataforma para no romper el
  medidor. La evidencia (§4.2, §5.3, §6.2, §6.6) empuja a (a) para la beta 1.]
- [NEEDS CLARIFICATION: **¿La UI vive en la cáscara (camino B) o es una web de
  la plataforma cargada en la app (camino A)?** §5.2. Decide el coste del
  segundo frontend (§6.1) y cuánto del Companion se porta (§2.4).]
- [NEEDS CLARIFICATION: **¿Qué ve el móvil (beta 3) y la web (beta 4)?** Luis:
  «desde la consola web no se pueden ver ni usar los teammates». ¿Eso incluye
  *aprobar* desde el móvil o desde una notificación? Si el hilo corre en
  plataforma, técnicamente el móvil puede pintarlo; la decisión es de producto.]
- [NEEDS CLARIFICATION: **¿Qué pasa con una aprobación pendiente cuando la app
  está cerrada?** Caduca (§IV) → ¿se reintenta al abrir, avisa por correo, o
  espera indefinidamente como estado honesto «esperándote»?]
- [NEEDS CLARIFICATION: **¿La edición se empaqueta con la app** (como el daemon
  de Grok Bot) **o se instala aparte**? Condición de la promesa (§6.3). Y ¿la
  app la arranca y supervisa (patrón `gateway-supervisor`) o espera a que
  esté?]
- [NEEDS CLARIFICATION: **¿Crear teammate es operar?** La matriz dice
  «teammates solo desde la app», luego crearlos es de la app; el diseño lo tiene
  como pantalla (decisión 7: formulario y conversación). Confirmar.]
- [NEEDS CLARIFICATION: **¿Las aprobaciones del Companion en la consola cuentan
  como Pendientes?** Luis mantiene el Companion en la web para crear agentes;
  sus `confirm-card` son aprobaciones. Si Pendientes es «solo app», o el
  Companion web deja de proponer, o Pendientes muestra también lo de la web.]
- [NEEDS CLARIFICATION: **¿Política de ejecución local por persona con techo del
  administrador** (Grok Bot: *ask / always / never* + techo de equipo) además de
  la lista blanca por cliente, o solo lista blanca?]
- [NEEDS CLARIFICATION: **¿Qué del sustrato entra en la beta 1?** `select_crew`
  como roster, `members.py` como memoria, `session-control` para handoff,
  `file-search` para `@`-mención, `notifications` con tres niveles. Cada uno
  ahorra trabajo y cada uno ata más a KiroCrew; la elección es por pieza.]
- [NEEDS CLARIFICATION: **¿Se verifica `--strict-mcp-config`** antes de que un
  teammate ejecute en la máquina de un partner con su propio `~/.claude.json`?
  Diferido por Luis el 2026-09-09 como primera tarea de la beta 2; sigue abierto.]

---

## Sources

**Internas**
- Artefacto: `Auphere Web v3.dc.html` (Claude Design, proyecto abc1c221…),
  extraído a `scratchpad/design-v3.html`.
- `.specify/assessments/teammates-en-la-app/intake.md`;
  `.specify/assessments/kirocrew-como-sustrato/research.md`;
  `.specify/assessments/identidad-y-consumo-en-la-app/`.
- `specs/001-puesto-trabajo-partner/spec.md` (R2, R13, R15);
  `specs/002-identidad-app-escritorio/spec.md` (R2–R4, R9–R12, R14) y
  `contracts/`; `docs/desktop-workstation.md`; `docs/companion/CONTRACT-V2.md`.
- `apps/api/src/nexus_api/api/console/companion.py`;
  `apps/console/src/components/companion/` (44 archivos);
  `apps/desktop/src/{electron/adapters.ts, session-isolation.ts, approvals-client.ts}`;
  `apps/edition/`.
- KB: `[[10-decisiones]]` §1, §2.4–2.8; `[[14-mvp-y-fases]]` §1–§3, §7;
  `[[00-revision-del-diseno-v3]]` §3–§5, §7; `[[07-competencia]]`;
  `[[15-kirocrew-y-alternativas]]` §5.

**KiroCrew** (`/Users/lmatos/Workspace/_oss-research/kirocrew` @37933a5, Apache-2.0)
- `website/electron/{package.json, gateway-supervisor.js, local-token.js,
  token-acquire.js, permission-handler.js, sandbox-profile.js, hide-to-tray.js,
  global-hotkey.js, data-home.js}`; `website/package.json`; `website/src/{pages,
  components}`.
- `src/kiro_crew/dashboard/server.py` (rutas); `docs/system-specs/modules/{crew-mode,
  subagent, session-control, taskrunner, heartbeat, file-search, app-notifications,
  computer-use, dashboard-token-auth, instances, mochi}.md`.

**Grok Bot**
- Binario: `/Applications/Grok Bot.app` (`Info.plist`, `app.asar`,
  `app.asar.unpacked/dist/{native,deps}`), extraído a `scratchpad/gb/`.
- [Approvals, security, and privacy](https://docs.x.ai/grok-bot/approvals-security-and-privacy) ·
  [Use the computer and apps](https://docs.x.ai/grok-bot/computer-and-apps) ·
  [Teams and enterprises](https://docs.x.ai/grok-bot/teams-and-enterprises) ·
  [Security](https://docs.x.ai/grok-bot/security) ·
  [Vellum — Official Grok Bot Breakdown](https://www.vellum.ai/blog/official-grok-bot-breakdown) ·
  [Composio — Guide to Grok Bot](https://composio.dev/content/guide-to-frok-bot) ·
  [MacRumors 2026-08-11](https://www.macrumors.com/2026/08/11/grok-bot-macos-ios/).

**Claude**
- [Get started with Claude Cowork](https://support.claude.com/en/articles/13345190-get-started-with-claude-cowork) ·
  [Claude Code — Desktop application](https://code.claude.com/docs/en/desktop) ·
  [Permission modes](https://code.claude.com/docs/en/permission-modes) ·
  [How we built auto mode](https://www.anthropic.com/engineering/claude-code-auto-mode) ·
  [AppleInsider — Cowork sandbox escape](https://appleinsider.com/articles/26/07/27/claude-cowork-can-escape-its-sandbox-rummage-through-all-of-your-files) ·
  [CoworkHow — Cloud vs local sessions](https://coworkhow.com/guides/cloud-vs-local-sessions) ·
  GitHub issues [#32584](https://github.com/anthropics/claude-code/issues/32584),
  [#34554](https://github.com/anthropics/claude-code/issues/34554),
  [#51984](https://github.com/anthropics/claude-code/issues/51984).

**OpenAI**
- [Introducing the Codex app](https://openai.com/index/introducing-the-codex-app/) (403 al fetch; leído por reseñas) ·
  [Verdent — Codex app first impressions](https://www.verdent.ai/guides/codex-app-first-impressions-2026) ·
  [Verdent — worktrees](https://www.verdent.ai/guides/codex-app-worktrees-explained) ·
  [IntuitionLabs — Codex app](https://intuitionlabs.ai/articles/openai-codex-app-ai-coding-agents) ·
  [Work with Apps on macOS](https://help.openai.com/en/articles/10119604-work-with-apps-on-macos) ·
  [wccftech — files listed without permission](https://wccftech.com/chatgpt-mac-update-made-ai-agent-show-complete-list-of-files-without-permission/).

**Microsoft**
- [BleepingComputer — Copilot Actions](https://www.bleepingcomputer.com/news/microsoft/microsoft-debuts-copilot-actions-for-agentic-ai-driven-windows-tasks/) ·
  [Windows Forum — Agent Workspace](https://windowsforum.com/threads/agentic-windows-copilot-actions-and-agent-workspaces-explained.390544/) ·
  [XDA — revoked file access](https://www.xda-developers.com/turned-on-windows-11-ai-agents-then-immediately-revoked-their-file-access/).
