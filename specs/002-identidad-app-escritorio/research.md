# Fase 0 — Research: decisiones de diseño

**Rama**: `002-identidad-app-escritorio` · **Fecha**: 2026-09-09 · **Spec**: [`spec.md`](./spec.md)

Catorce decisiones. Cada una con lo que se eligió, por qué, y qué se descartó.
Ninguna marca `NEEDS CLARIFICATION` queda abierta: las tres de la spec se cerraron
con Luis antes de planificar, y las de aquí se cierran con evidencia del repo.

---

## D1 · La máquina pertenece al partner: `partner_devices.partner_id`

**Decisión.** `partner_devices` pierde `tenant_id` y `workdir` y gana
`partner_id` (FK `partners`, NOT NULL), `hostname`, `credential_generation`,
`credential_rotated_at` y `revoked_reason`. Los clientes a los que sirve y el
directorio de cada uno pasan a una tabla nueva, `device_client_links`
(`device_id`, `tenant_id`, `workdir NULL hasta declarar`, `removed_at`).

**Por qué.** Es la decisión D-1 de la evaluación y el Requisito 4. El vínculo por
tenant es lo que sí es dato de tenant —directorio y lista blanca—, así que va con
RLS por tenant y `test_21` lo cubre sin tocarlo.

**RLS de `partner_devices`: dos políticas OR, ambas FORCE, ambas fail-closed.**

```sql
-- la dueña: ve y escribe sus máquinas
USING (partner_id = P AND principal_id = PR)
-- el gestor: ve todas las del partner, solo cuando la dependencia lo fija
USING (partner_id = P AND current_setting('app.workstation_manager', true) = 'true')
```

con `P = NULLIF(current_setting('app.partner_id', true), '')::uuid` y
`PR = NULLIF(current_setting('app.principal_id', true), '')`, exactamente las
expresiones de `0094_partner_wallet.py` y `0090_companion.py`. Sin GUC de partner,
cero filas; sin GUC de persona ni de gestor, cero filas.

**Descartado.** Filtrar por persona en el repositorio (R5.4 lo prohíbe). Correr el
listado de gestor con el rol dueño (el Companion lo reserva a mantenimiento, no a
lecturas en nombre de alguien).

**Migración de datos.** Las filas existentes (piloto) se llevan al partner de su
tenant por `partner_tenants`, y su `workdir` se convierte en un vínculo. Es un
`UPDATE … FROM` y un `INSERT … SELECT`; sin datos de producción todavía.

## D2 · Credencial v2: `{svc, sub, pid, gen, iat, exp}` y una carga de fila por petición

**Decisión.** La credencial deja de llevar `tid` y lleva `pid` (partner) y `gen`
(generación). `require_device` verifica la firma **y luego carga la fila** con el
rol dueño por clave primaria —igual que hoy se resuelve el tenant— y comprueba,
en este orden: `revoked_at` → `403 device_archived`; `gen` distinto de
`credential_generation` (fuera de la gracia de D3) → `401`;
`last_heartbeat_at` más viejo que 30 días → `403 pairing_required`. Solo entonces
fija `app.partner_id` y `app.principal_id` y baja a `nexus_app`.

**Por qué.** Una credencial apátrida no se puede revocar ni rotar; una consulta por
clave primaria en cada latido (cada 10 s por máquina) es un coste que no se nota.
Y es lo que hace **verdadero** el 001-R6.3 «revocable por sí sola», que hoy no lo
es. Los motivos de rechazo se distinguen a propósito para quien tenía una
credencial válida (§V); un token inválido sigue recibiendo `401` sin motivo.

**Descartado.** Lista de revocación en Redis (otro sitio donde la verdad puede
desincronizarse); TTL corto sin renovación (es el problema que se arregla).

## D3 · Renovación: `POST /device/renew`, rotación con gracia de 60 s

**Decisión.** La máquina renueva cuando a su credencial le quedan menos de **6 h**
(TTL 12 h). El servidor emite una credencial con `gen + 1`, guarda
`credential_rotated_at = now()`, y acepta `gen` **o** `gen − 1` durante 60 s desde
esa marca. Pasada la gracia, solo `gen`. Cada renovación se audita con actor
`device:{id}` (R13.1). Si la máquina no late 30 días, `renew` devuelve
`403 pairing_required` y la barra pasa a `hay que volver a emparejar`.

**Por qué.** Renovar por su propio endpoint mantiene la afirmación de `T072` —el
latido **solo** mueve `last_heartbeat_at`— y da un asiento de auditoría limpio. La
gracia cubre el fallo de red entre «el servidor rotó» y «la máquina guardó».

**Descartado.** Renovar dentro del latido (rompe `T072` y mezcla dos hechos);
tokens de refresco separados (dos secretos donde basta uno).

## D4 · La quinta operación: `POST /device/links` con `client_ref`, nunca `tenant_id`

**Decisión.** El dispositivo declara el directorio de un cliente enviando
`{client_ref, workdir, checks}`; la plataforma resuelve `client_ref` a tenant
**dentro del partner de la firma** vía `partner_tenants`, y solo entonces aplica
`app.tenant_id` y escribe el vínculo. Un `client_ref` que no sea del partner →
`404`, y el intento se registra. El sondeo (`GET /device/poll`) devuelve además
`links`: los clientes vinculados a esta máquina y cuáles no tienen directorio,
para que la barra sepa qué pedir.

**Por qué.** §I: el tenant nunca llega del llamante. `client_ref` es un nombre, no
una llave; la misma forma que `/console/clients/{ref}`. Y meter `links` en el
sondeo conserva la afirmación de `test_device_bridge_inbound`: **el único GET es
el sondeo**.

**Descartado.** `GET /device/links` (segundo GET); enviar `tenant_id` en el cuerpo
(§I de frente).

## D5 · Código de emparejamiento: 8 caracteres, alfabeto sin ambigüedad, 10 min, un uso, hash en reposo

**Decisión.** `device_pairing_codes` guarda `sha256(código)`, `partner_id`,
`principal_id`, `expires_at = now() + 10 min`, `consumed_at`,
`consumed_device_id`. El código se genera con `secrets.choice` sobre
`ABCDEFGHJKMNPQRSTVWXYZ23456789` (30 símbolos, sin `0/O/1/I/L/U`) y se muestra
como `XXXX-XXXX`; se acepta con o sin guion y en cualquier caja. Canje atómico:
`UPDATE … SET consumed_at = now() WHERE code_hash = :h AND consumed_at IS NULL AND
expires_at > now() RETURNING …`. Límite de intentos en Redis: 5 fallos por
`hostname+IP` → espera de 60 s que se duplica hasta 15 min; el mensaje no
distingue «no existe», «caducado» y «usado» (R3.3).

**Por qué.** 30⁸ ≈ 6,6 × 10¹¹ combinaciones vivas diez minutos, con cinco intentos
por cliente antes de esperar: la fuerza bruta no llega. Es la forma de las
invitaciones (`hash_invitation_token`, `secrets`) con un alfabeto que se puede
leer en voz alta. El precedente externo es RFC 8628 (`user_code` corto y una
`verification_uri`), invertido: aquí quien enseña el código es la web y quien lo
teclea es la máquina.

**Descartado.** Código de 6 dígitos (10⁶: se fuerza en minutos aunque haya
límite); QR (la barra y la consola están en la misma pantalla; no hay cámara).

## D6 · La puerta de sesión: `GET /api/session/whoami` leído por el proceso principal

**Decisión.** El BFF de la consola expone `GET /api/session/whoami` → `{user_id,
partner_slug}` o `401`, con la cookie de sesión y sin cuerpo. La cáscara lo llama
**desde el proceso principal** con `session.fromPartition(HUMAN_PARTITION).fetch`,
al arrancar y cada vez que `session.cookies.on('changed')` toca
`nexus-console.session`. El resultado decide: sin sesión → `sin sesión`, puente
parado; sesión de la persona que emparejó → puente arranca; sesión de otra
persona → `emparejada por otra persona`, con la oferta de emparejar la suya.

**Por qué.** Es la única forma de que R11.1 («la misma persona») y la Historia 5
sean ciertas sin canal página→cáscara: la cookie la lee el proceso principal, que
es de confianza; la página no participa; el ambiente del agente no tiene esa
partición ni ese proceso. Y observar el cambio de cookie es lo que hace que cerrar
sesión y la caducidad de 7 días detengan el puente **en segundos**, no en el
siguiente sondeo.

**Descartado.** Preguntarle a la página (canal prohibido); adivinar por la URL
(`/login` no distingue a quién).

## D7 · El almacén de credenciales: `safeStorage`, por persona, nunca en claro

**Decisión.** `credential-store.ts` guarda en `userData/credentials.bin` el
resultado de `safeStorage.encryptString(JSON)` con un mapa
`{[user_id]: {device_id, token, gen, exp, partner_slug, display_name}}`. Si
`safeStorage.isEncryptionAvailable()` es falso, **no se guarda nada** y la barra
lo dice como estado. Desemparejar borra la entrada y sobrescribe el fichero.

**Por qué.** R14.2: cifrado con el llavero del sistema, legible solo por la
identidad del proceso de la aplicación. Por persona, porque una máquina compartida
tiene un emparejamiento por persona (Historia 5). **Límite conocido y escrito:**
en macOS el llavero pide permiso por aplicación; en Windows DPAPI descifra para
cualquier proceso del mismo usuario — otra razón por la que Windows sigue fuera.

**Descartado.** Fichero en claro con permisos 600 (es una llave en el disco de
otra persona); guardar en la partición de la consola (mezcla la sesión de la
persona con la de la máquina).

## D8 · La barra: `BaseWindow` con dos `WebContentsView`, y solo la barra tiene `preload`

**Decisión.** `main.ts` pasa de `BrowserWindow` a `BaseWindow` con dos vistas:
la de la consola (partición `persist:auphere-console`, **sin `preload`**, igual
que hoy) y la de la barra (partición `auphere-bar`, no persistente, `preload`
`bar-preload.ts` que expone por `contextBridge` exactamente:
`getState() · onState(cb) · pair(code) · unpair() · pickDirectory(clientRef) ·
openInBrowser(url)`). La barra mide 44 px, va abajo, y se expande como hoja para
emparejar y declarar directorios. Es HTML + TypeScript sin framework, con los
tokens de `@nexus/ui` copiados en el build (no se descargan en tiempo de
ejecución).

**Por qué.** R12.1 exige una superficie propia; R3.5 y 15.3 exigen que la consola
no tenga canal. Dos vistas es la forma de tener las dos cosas. `BaseWindow` y
`WebContentsView` son de serie en Electron 44.

**Descartado.** Inyectar la barra en la vista de la consola (le da `preload` a la
consola); una `BrowserWindow` hija (se pierde detrás); React en la barra (peso y
una segunda cadena de build para 44 px).

**Estética declarada** (regla del workspace): *terminal-bloomberg discreta* —
monoespaciada solo para el nombre de máquina y el código, tipografía y color del
sistema de tokens, un solo acento (`--color-primary-deep`) para «conectada»,
nunca rojo para un estado del enlace. Referencia: la barra de estado de Linear y
la de VS Code, no un dashboard.

## D9 · La consola reconoce a la cáscara por User-Agent, en un solo sitio

**Decisión.** La cáscara fija `session.setUserAgent(UA + ' AuphereDesktop/<v>')`
en la partición humana. En la consola, `lib/shell.ts` expone
`isDesktopShell()` leyendo `headers().get('user-agent')`. **Lo usa un único
componente**: el de conectar canales de Meta, que en la cáscara muestra
«Continúa en el navegador» con el enlace copiable en vez del botón. Un test
afirma que `isDesktopShell` se importa **exactamente una vez** fuera de su módulo.

**Por qué.** Clarificación cerrada: acoplamiento mínimo, una sola bifurcación. La
UA es lo que el proceso ya envía; no hace falta cabecera nueva. El test es la
guarda contra la segunda bifurcación (R12.7).

**Descartado.** Cabecera propia (más superficie para lo mismo); detectar
`Electron/` a secas (no versiona y se confunde con otras aplicaciones).

## D10 · La puesta en marcha: `GET /console/workstation/setup`, calculada por persona en cada visita

**Decisión.** Un endpoint derivado —sin tabla, como `GET /console/onboarding`—
que devuelve los cuatro pasos y su estado **para la persona que llama**:
`paired` (tiene máquina activa propia) · `clients` (alguna máquina propia con
≥ 1 vínculo) · `directories` (todos sus vínculos con directorio) ·
`executables` (cada cliente vinculado con ≥ 1 ejecutable habilitado por
Auphere). Se pinta como tarjeta en la home y en `/workstation`. Cerrarla es
estado del componente en esa visita; al volver, se recalcula (R6.2, R6.3). Con los
cuatro en verde, no se renderiza (R6.4). Sin `workstation:pair`, no se renderiza
(R6.5).

**Por qué.** Cero deriva: no hay nada guardado que pueda mentir. Continúa el paso 3
del onboarding del diseño en vez de abrir un segundo onboarding.

**Descartado.** Persistir el descarte (localStorage, como la tarjeta CP-29): R6.3
quiere que reaparezca mientras falte algo.

## D11 · Consola a nivel de partner: `/workstation` y `/console/workstation/*`

**Decisión.** Ruta nueva `/workstation` (nav «Operar», permiso
`workstation:read`, icono `Laptop`): mis máquinas —o todas con dueño, para
`workstation:write`—, botón «Emparejar esta máquina» (diálogo con el código, la
cuenta atrás y la instrucción de tecleárselo a la barra), y por máquina: clientes
a los que sirve (añadir/quitar), estado del directorio de cada uno, «Archivar».
API: `POST /console/workstation/pairing-codes` · `GET /console/workstation/devices`
· `PATCH …/devices/{id}` (nombre) · `POST …/devices/{id}/clients` · `DELETE
…/devices/{id}/clients/{ref}` · `DELETE …/devices/{id}` (archiva) ·
`GET /console/workstation/setup`. Los ejecutables **siguen** en
`/console/clients/{ref}/workstation/executables`. Permiso nuevo
`workstation:pair` = owner · admin · builder, espejado en `permissions.ts` y
cubierto por el test de deriva.

**Por qué.** La máquina es del partner (D1); los ejecutables son del cliente
(001-R2.1). Cada cosa en su nivel. `test_console_scope` cubre las rutas nuevas
automáticamente.

**Descartado.** Dejar todo bajo `/clients/{ref}` y «elegir el primero» (miente
sobre el dueño).

## D12 · Licencias: ninguna dependencia nueva

Verificado contra `apps/desktop/package.json` (Electron 44.3.0, `electron-builder`,
`electron-updater`, todo MIT ya declarado en `THIRD-PARTY-LICENSES.md`),
`apps/api/pyproject.toml` (`pyjwt`, FastAPI, SQLAlchemy, Alembic, `redis`) y
`apps/console/package.json` (`lucide-react` para el icono `Laptop`, ya
instalado). **Si una tarea quiere añadir algo, para y declara el párrafo.**

## D13 · La pertenencia retirada archiva las máquinas

**Decisión.** `PartnerMembershipRepository.remove` y la suspensión de una cuenta
llaman a `PartnerDeviceRepository.archive_all_for_principal(principal_id,
reason='pertenencia_retirada')` en la misma transacción. `revoked_reason` es
vocabulario cerrado: `desemparejada` · `archivada_consola` ·
`pertenencia_retirada`, con CHECK en la base.

**Por qué.** R11.4. Y vocabulario cerrado por la misma razón que
`DENIAL_REASONS`: un motivo que nadie diseñó es un motivo que la auditoría no
sabe explicar.

## D14 · Presencia por tenant a través de los vínculos

**Decisión.** `device_presence` deja de mirar «dispositivos del tenant» y mira
«vínculos del tenant cuya máquina está presente»: latido fresco, no archivada, con
directorio declarado. El catálogo del turno ofrece herramientas locales al
teammate del cliente X **solo** si existe ese vínculo (R7.5). Cerrar sesión para
el latido → la presencia decae en 30 s → las herramientas salen del catálogo
(R11.1) sin ninguna pieza nueva.

**Por qué.** Es la 001-R4 con el dueño cambiado; la regla «la presencia es un
filtro sobre la whitelist» (`[[03-ecosistema-multiplataforma]]` §4.3) se conserva.

---

## Mapa de tests — cada criterio con su test, en rojo antes de existir

| Criterios | Test | Suite |
|---|---|---|
| 4.1–4.6, 5.1, 5.4, 11.3, 11.4, 14.3 | `test_30_device_partner_scope.py`: la credencial de A no late/sondea/renueva/declara para B; `client_ref` ajeno → 404 registrado; RLS dueña/gestor/nadie; revocada → 403 en las cinco; `gen` viejo fuera de gracia → 401; sin GET nuevo | `tests/isolation/` (bloquea) |
| 4.5 (lista y directorio por cliente en una máquina del partner) | `test_28` reescrito: vínculos por tenant no se cruzan; máquinas por partner | `tests/isolation/` |
| 3.1–3.4, 13.2 | `test_device_pairing.py`: emitir, canjear una vez, segunda vez falla, caducado falla, otro partner falla, límite de intentos, mensaje único, auditoría | `tests/integration/` |
| 10.1–10.4, 13.1 | `test_device_renewal.py`: rota `gen`, gracia de 60 s, sin gracia falla, 30 días → `pairing_required`, asiento con actor `device:` | `tests/integration/` |
| 6.1–6.6 | `test_workstation_setup.py`: cuatro pasos derivados por persona; sin `workstation:pair` no hay pasos | `tests/integration/` |
| 7.4, 7.5, 14 (presencia) | `test_device_presence.py` ampliado: sin directorio no hay herramientas; dos clientes, dos directorios | `tests/integration/` |
| 9.1, 9.2 | `test_identity_acts_do_not_meter.py`: cero asientos en `usage_ledger` por los cinco actos | `tests/integration/` |
| 3.5, 14.1, 14.2 | `session-isolation.test.ts` ampliado: la vista de la consola no tiene `preload`; tres particiones distintas; `credential-store.test.ts`: nunca texto plano en disco, por persona, sin cifrado no guarda | `apps/desktop/tests/` |
| 1.1, 1.3, 12.2, 12.3 | `bar-state.test.ts`: siete estados, transiciones, ningún tono de error, sin herramientas fuera de `conectada` | `apps/desktop/tests/` |
| 2.2, 11.1, Historia 5 | `session-gate.test.ts`: sin sesión para; misma persona arranca; otra persona → estado y oferta; cambio de cookie reacciona | `apps/desktop/tests/` |
| 7.1–7.3 | `directory-declare.test.ts`: cuatro validaciones, cada una con su mensaje; nada se envía si falla | `apps/desktop/tests/` |
| 12.7 | `shell-detect.test.ts`: `isDesktopShell` importado exactamente una vez; en cáscara no hay botón de Meta y sí «continúa en el navegador» | `apps/console` |
| 5.2, 8.1, 8.4, 6.x (pantalla) | `workstation-page.test.tsx` + `setup-card.test.tsx`: 5 estados Hurff cada uno; «Pedirla» para ejecutables ausentes; sin cifra de consumo en ningún sitio de la barra | `apps/console` |
| 12.4–12.6 | `a11y-audit` + `responsive-audit` sobre la barra y `/workstation`; test de tokens: cero hex, `fg-subtle` no aparece en la barra | auditorías del workspace |
| Historia 1 completa | `quickstart.md` §1–§5 en una máquina limpia | manual, con evidencia |
