# Investigación (Fase 0): spec 031, Auphere Customers

Fecha: 2026-10-19.

**Fuentes:**
- El código en `develop` @ `883ee74c`, leído con tres barridos de solo lectura.
- La nota de KB `[[research/2026-10-19-consola-lite-movil]]`.
- Las fuentes primarias de Apple, Google, Expo, npm y PyPI, consultadas hoy.

Hay que volver a comprobar las versiones de librerías y SDK al ejecutar
`/speckit-tasks`.

Cada decisión sigue la forma **Decisión → Por qué → Alternativas**.

---

## D1 · La API comprueba la sesión del teléfono (camino A)

**Decisión.** La API acepta una credencial propia del teléfono.
`require_client_principal` gana una segunda rama, y esa rama acaba en **el
mismo** `resolve_client_principal(partner_id, principal_id)` que hoy usa el JWT
de la BFF. Por eso las rutas `/console/lite/*` no se tocan: reciben el mismo
`ClientPrincipal`.

**Por qué:**
- **La API necesita saber qué teléfono llama.** Lo exigen el registro de
  avisos, cerrar un teléfono concreto (R7), la lista «tus teléfonos» y la
  cola de avisos. El JWT de 60 s de la BFF no lleva identificador de
  sesión (`lib/jwt.ts:41-43`).
- **Un salto en vez de tres.** Con B, cada llamada iría del teléfono a Vercel
  (región sin fijar en el repo) y de ahí a la API dos veces seguidas: resolver la
  sesión y la ruta. La API está en `eu-south-2` y el piloto, en Chile. Abrir una
  conversación ya son tres llamadas seguidas (`openConversationAction`).
- **Ya hay precedente.** `/device/*` emite y comprueba su propia credencial,
  lee la fila en cada petición, renueva con generación y aplica la puerta de
  versión (`device_bridge.py:158`, `device_credential.py`).
- **Las sesiones web no sirven.** Duran 7 días absolutos y no se renuevan, a
  propósito (`console_identity.py:30,83`). Meter ahí el teléfono obliga a
  cambiar esa política para un caso que no es el suyo.

**Alternativas:**
- **B · La BFF resuelve una sesión de teléfono.** Ventaja: no cambia la
  dependencia de la API. Se descarta por cuatro razones:
  - hay que reescribir como route handlers las 17 Server Actions de la Bandeja;
  - añade dos viajes por llamada;
  - igualmente hay que tocar `principal_sessions` (tipo y TTL);
  - el registro de avisos necesita igualmente identidad de teléfono en la API.
- **Reutilizar `partner_devices`.** Se descarta: `partner_id` es NOT NULL, la
  RLS va por membresía de partner y los permisos son de `workstation`. Un rol más
  en esa tabla tendría el mismo problema que la spec 030 evitó con D1.

## D2b · Entrada propia de la app: contraseña nativa y Google por la API (2026-10-20)

**Sustituye a D2** por decisión del owner tras el pase vivo: la app no pasa por
la consola de partners (habrá una app de partners aparte). Ver la aclaración
del 2026-10-20 en la spec y el contrato `phone-auth.md`.

**Decisión:**
- **Correo y contraseña en la propia app**, contra `POST /app/sign-in/password`.
  Es la concesión de contraseña de una app de primera parte: la app es nuestra y
  la API es nuestra. Mismas reglas que el login web (`console_identity.authenticate`
  con su bloqueo, límites por correo y por IP). La contraseña no se guarda; el
  gestor de contraseñas del sistema la rellena.
- **Google con el flujo web de Google, alojado en la API** (`/app/sign-in/google`),
  en la ventana segura del sistema (`expo-web-browser`). La API reutiliza lo que
  ya usa la consola: `google_oidc` (PKCE propio, `select_account`, verificación
  del `id_token`) y `resolve_provider_identity`. Al volver, emite el código de un
  uso de siempre (`session_codes`, `purpose=client_phone`) atado al reto de la
  app, y la app lo canjea en `POST /app/sign-in/google`.
- **La regla del correo:** el correo verificado de Google tiene que ser el de la
  membresía de la persona en el cliente, aunque el `sub` ya esté vinculado.

**Por qué no un SDK nativo de Google:**
- `@react-native-google-signin/google-signin` (MIT) usa en su versión gratuita
  el SDK de Android que Google dejó obsoleto; Credential Manager solo viene en
  su versión de pago.
- `react-native-nitro-google-signin` (MIT, Credential Manager) es joven, pide
  `react-native-nitro-modules` y no se puede compilar aquí para iOS (Xcode
  26.0.1 frente a 26.4 del SDK 58): sería código nativo sin verificar camino de
  TestFlight.
- El flujo web no añade dependencias, funciona igual en iOS y Android, y no pide
  registrar huellas SHA-1 por cada firma (desarrollo, EAS y Play). En iOS es lo
  mismo que hace por dentro el SDK de Google (ASWebAuthenticationSession).
- **Se revisa** si el piloto pide la hoja nativa de Android: entonces Credential
  Manager, con el `id_token` verificado por la misma API (audiencia propia).

**Riesgo conocido:** en Android la vuelta usa el esquema propio. PKCE y `state`
impiden canjear un código ajeno; un flujo iniciado por otra app exige que la
persona elija su cuenta en Google (`select_account`), así que ya no hay un camino
silencioso como el de la sesión abierta de la consola (observación de `/cso` del
2026-10-20).

**Guía 4.8 del App Store:** ver «Supuestos» en la spec.

## D2 · Entrar con la ventana del sistema y PKCE del RFC 7636 — sustituida por D2b

**Decisión:**
- **Página nueva de la consola:** `/app-auth?app=customers&…`. Si la persona no
  tiene sesión, pasa por el `/login` de siempre, con correo, contraseña y
  Google.
- **Emisión del código:** `POST /console/lite/phone-codes` la llama la BFF con la
  persona de cliente ya resuelta.
- **Canje:** público, en `POST /app/phones`.
- **Tabla de códigos:** se reutiliza `console_auth.session_codes`, con
  `purpose = client_phone`.
- **PKCE:** **S256 en base64url, como manda el RFC 7636.**
- **Vuelta a la app:** un enlace universal o App Link verificado, y como
  respaldo el esquema `auphere-customers://`.
- **En la app:** `expo-web-browser`, que usa ASWebAuthenticationSession y Custom
  Tabs.

**Por qué:**
- **Nada nuevo para la persona.** La contraseña nunca se escribe en la app
  (R1.2) y la entrada es la de la web (R1.1).
- **Separación de flujos.** El código de un flujo no se canjea en el otro.

**Hallazgo lateral, fuera de esta spec.** La API calcula el challenge del
escritorio en **hex** (`services/session_codes.py:64`), pero la app de escritorio
lo envía en **base64url** (`apps/desktop/src/loopback-login.ts:47`). O hay una
normalización que no vimos, o el canje de la spec 009/012 no puede cuadrar.
- Se abre por el flujo de bugs, aparte.
- Esta spec no depende de eso: guarda la codificación en
  `session_codes.challenge_encoding` y el teléfono siempre usa `base64url`.

**Alternativas:**
- **Login nativo con contraseña en la app.** Va contra R1.2 y RFC 8252.
- **Reutilizar `/desktop-auth`.** Solo acepta redirecciones de loopback HTTP y
  emite para partners (`desktop-redirect.ts:22-35`, `session_codes.py:77`).
- **Auth Tab de Android.** `expo-web-browser` aún no la trae (usa
  androidx.browser 1.6.0); un App Link verificado cubre el mismo riesgo.

## D3 · El teléfono se lee como identidad; el tenant sale de su fila

**Decisión** (corregida al implementar, 2026-10-19).
- La credencial **no lleva tenant**: `{svc, sub: <phone_id>, gen, iat, exp, iss, aud}`.
- La comprobación lee la fila de `client_phones` **como identidad**: en una
  transacción corta, con el usuario de conexión y sin el rol `nexus_app`. Es lo
  mismo que ya hace `resolve_client_principal` con `client_memberships`
  (`core/client_auth.py:105-108`).
- De esa fila salen `partner_id` y `principal_id`. Todo lo demás (membresía,
  acceso, tenant, RLS) es el camino de siempre.

**Por qué.**
- **Elimina un valor que viaja.** El tenant ni siquiera va firmado: sale de una
  fila que se busca por un identificador que la API emitió.
- **Permite reglas entre clientes en la capa de identidad.** Una sola sesión por
  instalación y un dueño por destino de avisos se aplican en esa misma
  transacción de identidad, sin saltarse la RLS de los datos del cliente.

**Alternativa descartada.** Firmar `tid` y buscar bajo la RLS, que era la
versión del plan. Funciona, pero es una pieza más y no permite las reglas entre
clientes.

## D4 · Dos credenciales: acceso y renovación

**Decisión:** el detalle está en [contracts/phone-auth.md](contracts/phone-auth.md).
- **Acceso:** JWT de 1 h.
- **Renovación:** opaca y rotativa, con 60 s de gracia. Si se reutiliza fuera de
  la gracia, revoca el teléfono. Caduca tras 90 días sin uso.
- **Secreto propio:** `customers_app_token_secret`.
- **Almacén:** las dos van en el llavero de la app
  (`WHEN_UNLOCKED_THIS_DEVICE_ONLY`). La app renueva de una en una.

**Por qué:**
- **Un teléfono pasa días sin abrir la app.** El token único de 12 h del
  escritorio caducaría y obligaría a entrar otra vez, contra R2.1.
- **No hace falta una tercera credencial.** Con avisos normales (D5), nada fuera
  de la app necesita leer el llavero.

**Alternativas:**
- **Una sola credencial de 12 h, como el escritorio.** Choca con R2.1.

## D5 · Avisos normales: el aviso viaja completo

**Decisión** (del owner, 2026-10-19: «notificaciones push normales, sin mucha
lógica, que funcionen como deben»):
- **El servidor compone** título y texto en el idioma del teléfono, y los envía
  dentro del aviso.
- **El sistema lo muestra tal cual,** sin extensión de iOS, sin tarea en segundo
  plano en Android y sin credencial aparte.
- **Lo que viaja es lo mínimo que el aviso enseña** (R9.2): el nombre del
  contacto; el motivo o el principio del mensaje, como mucho 100 caracteres; y
  el estado del saldo. Nunca teléfonos, mensajes completos, archivos ni notas.
- **Cada aviso va marcado como privado:** en iOS con
  `hiddenPreviewsBodyPlaceholder`; en Android con `visibility: PRIVATE`.

**Por qué:**
- **Es el comportamiento que espera cualquiera** que use una app de mensajería
  de empresa.
- **Llega siempre,** también sin red en el momento de mostrarlo.
- **No hay código nativo propio.** Ningún riesgo de la ventana de 30 s de la
  extensión ni de la de FCM.
- **Quita a la vez** una pieza nativa (la extensión en Swift), una credencial,
  una ruta pública y un spike.

**El precio.** Apple y Google pasan a ver el nombre del contacto y un texto
corto, como encargados del tratamiento. Queda escrito en la lectura de RGPD
(D21), en la política de privacidad y en las etiquetas de privacidad de las
tiendas.

**Alternativas:**
- **Que el teléfono pida el texto** con una extensión y una credencial de
  avisos. Era la versión anterior de este plan, y el owner la descartó por la
  complejidad.
- **Payload cifrado para el teléfono.** Es aún más complejo.
- **Solo texto genérico.** Incumple R8.11.

## D6 · Outbox en la base y una tarea nueva del worker

**Decisión:**
- **Dónde se escribe el evento:** en `client_push_events`, **en la misma
  transacción** que el hecho:
  - el escalado, en `mark_waiting`;
  - el mensaje entrante, en el bloque transaccional de
    `_process_inbound_after_gates`;
  - el aviso de saldo, junto al `emit()`, con `SET LOCAL` del tenant.
- **Quién lo reparte:** la tarea `push-dispatcher`, de la familia egress. Se
  despierta con `pg_notify('nexus_push')` y lee con `FOR UPDATE SKIP LOCKED`.
  Calcula los destinatarios **al repartir**.

**Por qué:**
- **Ya hay patrón.** El worker no usa Dramatiq. Usa tareas asyncio con un
  contrato de nombres, y para lo que debe ir atado al commit usa filas como
  outbox: `outbound.py:155-212` y `owner_outbox.py`.
- **Cumple R8.5 sin código extra:** el worker solo ve filas confirmadas.
- **Cumple R7.2 y R11.2:** calcular destinatarios al repartir respeta las
  revocaciones y los interruptores de ese instante.

**Alternativas:**
- **Redis Streams (`xadd_capped`).** No va atado al commit.
- **Enviar dentro de `emit()`,** como el correo. El correo sale antes del commit
  del llamante, y eso es justo lo que R8.5 prohíbe.
- **Colgarse de `announce_waiting`.** Corre después del commit, pero en otra
  transacción: un fallo entre las dos pierde el aviso.

**Riesgo conocido.** Una tarea nueva rompe la tubería si no se declara en el
contrato. Va en tres sitios: `_spawn`, `EGRESS_TASK_NAMES` y `ALL_EXPECTED` de
`test_bootstrap_split.py`. Ya ha pasado dos veces.

## D7 · La pantalla bloqueada la decide el teléfono

**Decisión:**
- **Cada aviso se marca como privado:**
  - en iOS, la categoría lleva `hiddenPreviewsBodyPlaceholder` con el texto
    neutro del tipo;
  - en Android, el aviso lleva `visibility: PRIVATE`.
- **La app explica el ajuste.** La pantalla de permiso y Ajustes dicen cómo
  ocultar el contenido con el teléfono bloqueado.
- **La spec cambia.** R8.10 se reescribió en este sentido.

**Por qué.** Ninguna de las dos plataformas deja a una app forzar qué se ve
bloqueado: lo decide el ajuste de vistas previas.
- En iPhone con Face ID, el valor por defecto ya es «Al desbloquear».
- En Android y en iPhone con Touch ID, por defecto se enseña el contenido.

## D8 · Enviar a Apple y a Google desde Python con una sola dependencia nueva

**Decisión:**
- **APNs:** HTTP/2 con `httpx[http2]`, que trae `h2`, MIT. El token del
  proveedor se firma en ES256 con PyJWT, que ya está.
- **FCM:** HTTP v1 con una aserción de cuenta de servicio en RS256 firmada con
  PyJWT y canjeada en `oauth2.googleapis.com/token`.

**Por qué:**
- `httpx` y PyJWT ya están en el árbol. Lo único nuevo es `h2`.

**Alternativas:**
- **`aioapns`** (Apache-2.0). Está poco activo y trae pyOpenSSL.
- **`google-auth`** (Apache-2.0). Es correcto, pero no hace falta.
- **El servicio de push de Expo.** Sería un tercero más viendo los destinos y
  los payloads.

## D9 · Envío idempotente con la columna que ya existe

**Decisión:**
- **Cabecera:** `Idempotency-Key` en el envío y en los adjuntos de la Bandeja
  lite, guardada en `messages.idempotency_key` (0053).
- **Respuestas:** un replay devuelve 200 con el mismo cuerpo; un `failed` se
  reintenta sobre la misma fila; la carrera entre dos peticiones se resuelve
  capturando la violación de unicidad.
- **La web** también la manda.

**Por qué.** Cumple R6.4 y CE-004, y reutiliza el índice parcial por tenant.
Además corrige el hueco del precedente: `direct_messages.py` no captura la
carrera y devuelve un 500.

**Alternativas:**
- **Deduplicar por hash del texto.** Dos mensajes iguales y legítimos se
  perderían.

## D10 · El orden de los módulos sale de la API

**Decisión:**
- **Campo nuevo:** `GET /console/lite/me` devuelve `nav`, sacado de
  `ClientAccess.ordered_modules()`.
- **La consola** borra el `ORDER` de `lite-nav.ts` y pinta `nav`.
- **La app** también pinta `nav`.

**Por qué.** Hoy el orden está escrito tres veces (la API,
`principal-access.ts:21` y `lite-nav.ts:21`). R3.2 pide una sola fuente.

**Alternativas:**
- **Un JSON compartido entre los dos workspaces.** Añade un tercer sitio en vez
  de quitar dos.

## D11 · Pestañas dinámicas con las pestañas nativas de Expo Router

**Decisión:**
- **Se declaran las pestañas de los módulos que conoce la versión de la app:**
  `panel`, `inbox` y `usage`.
- **Se montan después de leer `nav`,** detrás de la pantalla de arranque.
- **Las que no están en `nav` van con `hidden`.**
- **Si `nav` cambia al volver al primer plano,** se vuelve a montar la barra.
  Se pierde la pila de navegación, y si la pestaña abierta desapareció, R3.5
  lleva al primer módulo.
- **Un módulo que la app no conoce** se ignora (R3.6).

**Por qué.** Las pestañas nativas no dejan añadir ni quitar pestañas en
caliente, pero sí ocultarlas («Dynamically adding or removing tabs at runtime
is not supported»). Un módulo nuevo de verdad, como Reservas, necesita pantallas
nuevas, y por tanto una versión nueva de todos modos.

**Alternativas:**
- **Pestañas en JavaScript.** Perderían Liquid Glass y el comportamiento nativo
  que pide el prototipo.

## D12 · Expo SDK 58, con el 57 de respaldo

**Decisión:**
- **SDK:** Expo **58** (React Native 0.88, React 19.3.0, Node 24), con
  `expo-router/native-tabs`, que ya es estable, y UIScene por defecto.
- **Respaldo:** si el spike S1 encuentra un bloqueo, `expo@57.0.30` con
  `ios.enableSceneSupport`.

**Por qué:**
- **Empezar en 57 obliga a migrar justo después del piloto.** Habría que
  cambiar el import inestable de pestañas, el núcleo del router y la opción de
  UIScene.
- **El riesgo de librerías de terceros es bajo,** porque dependemos sobre todo
  de módulos de Expo.
- **iOS 27 obligará a usar UIScene.** Según TN3187, una app sin él no arrancará
  cuando se compile con el SDK siguiente.

**Alternativas:**
- **Flutter, Compose Multiplatform y nativo puro.** Están descartados en la nota
  de KB §1.

## D13 · `apps/mobile` en su propio workspace de pnpm

**Decisión:**
- **Workspace y lockfile propios,** como `apps/admin`, fuera de la lista raíz.
- **Sin dependencias `workspace:*`.**
- **Lo compartido entra como archivos generados y comprobados en CI:** tipos,
  tokens y vocabulario.

**Por qué:**
- **React no puede ir duplicado.** Expo 58 fija React 19.3.0 y la raíz fija
  19.2.4. Expo avisa: «Duplicate React versions in a single app will cause
  runtime errors».
- **El lockfile compartido ya rompió tipos de otro paquete.** Lo recoge la
  memoria «lockfile único y pares compartidos».

**Pendiente de verificar en S1:** que EAS Build funcione desde un workspace
anidado dentro del repo.

## D14 · Tipos generados desde el OpenAPI de la API

**Decisión:**
- **Generador:** `openapi-typescript` 7.x, con cliente `openapi-fetch` 0.17
  (los dos MIT).
- **Origen:** el OpenAPI 3.1 de FastAPI, filtrado a `/console/lite/*` y `/app/*`.
- **Destino:** `apps/mobile/src/api/schema.gen.ts`.
- **En `verify.sh`:** se vuelve a generar y se compara con el archivo
  confirmado.
- **Deriva que se corrige de paso** en `lite-api.md` y `realtime.md`: `user.id`
  no existe, y `message.status` lleva `status`, no `delivery`.

**Por qué.** `@nexus/shared-types` solo tiene un README. Escribir los tipos a
mano por segunda vez garantiza que diverjan.

**Alternativas:**
- **Activar por fin `shared-types` como paquete.** Obligaría a una dependencia
  `workspace:*` desde el workspace del móvil (ver D13).

## D15 · Los colores de `@nexus/ui`, convertidos a hex para React Native

**Decisión:**
- **Un script con `culori`** (MIT) lee `packages/ui/src/styles/tokens.css` y lo
  convierte, con ajuste de gama a sRGB, en
  `apps/mobile/src/theme/tokens.gen.ts`, para claro y oscuro.
- **Se comprueba en CI.**
- **La app no escribe ningún color a mano:** los nombres de los tokens son los
  de la web.

**Por qué.** React Native 0.86–0.88 no interpreta `oklch()` ni
`color(display-p3 …)`, y el CSS no se puede leer desde React Native.

**Alternativas:**
- **Migrar los tokens a DTCG JSON con Style Dictionary 5** (Apache-2.0). Sería
  la buena fuente única a futuro, pero hoy cambiaría la web sin que la spec lo
  pida.

## D16 · Textos: el patrón de la consola y el vocabulario generado

**Decisión:**
- **Traductor:** el mismo `t(locale, key, vars)` de la consola, sin
  dependencias.
- **Vocabulario compartido:** se genera `apps/mobile/src/i18n/lite.gen.ts`
  desde `apps/console/src/i18n/messages.ts`, con una lista cerrada de prefijos
  de clave (Bandeja, Panel, Consumo, estados). Se comprueba en CI. Así «Tomar el
  control» se escribe igual en las dos (R14.6).
- **Textos propios de la app:** en sus propios archivos, en ES y EN.
- **Idioma:** con `expo-localization`, leído al volver al primer plano.

**Por qué.** La consola no usa ICU ni plurales, y Hermes no garantiza
`PluralRules`.

## D17 · Tiempo real: SSE propia sobre `expo/fetch`

**Decisión:**
- **Cliente:** unas 80 líneas sobre `expo/fetch` (con streaming) y
  `eventsource-parser` (MIT). Gestiona `AppState`, la espera creciente y
  `Last-Event-ID`.
- **Solo en primer plano.** Al volver, se vuelve a pedir antes de dejar actuar.

**Alternativas:**
- **`react-native-sse`** (MIT). Está sin mantenimiento desde 2024 y vuelve a
  leer todo `responseText`, así que su memoria crece.

## D18 · Versión mínima por configuración

**Decisión:**
- **Configuración:** `customers_app_min_version_{ios,android}`, `…_reason` y
  `…_from`, en la de la API. Es el patrón de `desktop_version.py`.
- **Dónde se publica:** en `GET /app/config`.
- **Cómo se aplica:** cualquier petición con la credencial del teléfono por
  debajo de la mínima responde 403 `app_update_required` (R13).

## D19 · Actualizaciones por aire: incluidas, solo para arreglos

**Decisión:**
- **`expo-updates` va en el primer binario,** porque añadirlo después exige
  pasar por la tienda.
- **Se usa solo para arreglos y textos.** Las funciones nuevas pasan por
  revisión (guía 2.5.2).
- **Cada actualización queda anotada en el registro de cambios de la spec.**

**Alternativa.** No incluirlo. Un arreglo urgente esperaría a la revisión de la
tienda; la puerta de versión mínima evita el daño, pero no arregla nada.

## D20 · Sin servicio de errores de terceros en la v1

**Decisión:**
- **Errores de cliente:** los informes de fallos de App Store Connect y Play
  Console.
- **Errores de servidor:** los registros de la API.

**Por qué:**
- **Ninguna app del repo usa Sentry hoy.** Añadirlo es un subencargado nuevo
  con su lectura de RGPD.
- **El piloto se puede llamar por teléfono.**
- Se revisa tras el piloto.

## D21 · Distribución y secretos

**Decisión:**
- **Cuentas y nombre:**
  - Bundle y paquete `com.auphere.customers`, en el team de FACELAD (decisión
    del owner).
  - Los builds y envíos los hace EAS, con una **API key nueva** de App Store
    Connect. La `[Expo] EAS Submit` de FACELAD no se reutiliza.
- **APNs:**
  - La clave `.p8` la crea Daniel (Account Holder) o un Admin con acceso a
    «Certificates, Identifiers & Profiles».
  - Se guarda en AWS Secrets Manager y la lee el worker.
- **FCM:**
  - El proyecto de Firebase es de Auphere.
  - La cuenta de servicio va a Secrets Manager.
- **Lectura de RGPD** de lo que reciben Apple, Google y Expo:
  - Apple y Google reciben el destino del teléfono y el texto mínimo de cada
    aviso (D5), como encargados del tratamiento.
  - Expo procesa el código fuente y los builds, con SCC según sus términos, y
    nunca datos de clientes.
  - Queda escrita en la KB, en la política de privacidad y en las etiquetas de
    privacidad de las tiendas.

## D22 · Cómo se prueba

| Capa | Herramientas |
|---|---|
| API y worker | pytest: `unit`, `integration`, y `isolation` con los seis barridos de R15 |
| Consola (`/account/phones`) | vitest y Playwright con axe |
| Admin | vitest |
| App | `jest-expo` y `@testing-library/react-native` 14 (MIT), con consultas por rol y nombre accesible (R14.5) |
| Flujos de punta a punta | Maestro 2.x (Apache-2.0), en simulador y emulador |
| Escala de texto máxima y modo oscuro | Pruebas con `fontScale` y `colorScheme` |
| VoiceOver y TalkBack | Una lista manual con capturas en `evidence/` |

`eslint-plugin-react-native-a11y` no sirve: solo soporta ESLint 8, y el repo usa
ESLint 9.

## D23 · Un spike antes de construir

Va por el flujo `assess`, y **su código no se fusiona**.

**S1 · Esqueleto de SDK 58 en dispositivo.** Prueba seis cosas:
- la entrada por la ventana del sistema, con vuelta universal y vuelta por
  esquema propio;
- el almacén seguro;
- un aviso real de APNs y otro de FCM, enviados desde un script, con el nivel
  `time-sensitive` y `visibility: PRIVATE`;
- pestañas nativas que se ocultan y se vuelven a montar;
- una animación de reanimated en el hilo de UI;
- EAS Build desde el workspace anidado.

Si algo bloquea, se baja a 57.0.30.

## D24 · Experiencia y movimiento: nativo primero, movimiento donde aporta

**Dirección.** La de la nota de KB y del prototipo:
- la **estructura es de la plataforma** (barras, hojas, gestos, tipografía del
  sistema);
- la **marca** está en el color, el contenido y la voz.

Referencias de tono: Mail y Mensajes de Apple, Things 3 y Linear para móvil, por
su contención. En Android, el movimiento de Material 3 Expressive.

**Reglas:**
1. **Transiciones del sistema y ninguna propia.**
   - Pila nativa para entrar en una conversación.
   - En iOS, hojas con detención media o grande para el detalle (contacto y
     notas) y para Ajustes.
   - En Android, hoja inferior modal, y Ajustes como pantalla, con el gesto
     atrás predictivo.
   - Pull-to-refresh nativo.
2. **Un momento orquestado: «Tomar el control».**
   - La franja con el motivo del agente se recoge y el cuadro de escribir sube a
     su sitio, en una sola transición de unos 250 ms con un muelle sin rebote.
   - Va con una vibración de éxito y con «Tomaste el control» apareciendo en el
     hilo.
   - Es el único movimiento con coreografía de la app.
3. **El envío es optimista.**
   - La burbuja aparece al instante como «enviando» y pasa a enviada con un
     fundido de 150 ms.
   - Si falla, se queda con «Reintentar» (R6.6).
   - Vibración ligera al enviar.
4. **Lo que llega entra sin saltos.**
   - Los mensajes nuevos aparecen con un fundido y un desplazamiento de 8 pt en
     200 ms.
   - En la Bandeja, una conversación que sube a la cabeza se recoloca con una
     transición de lista de 200 ms.
5. **Deslizar como en cada plataforma.**
   - En iOS, deslizar revela «No leída» y «Resolver».
   - En Android, deslizar entero resuelve, con una barra «Deshacer» de 4 s.
   - Siempre hay una alternativa sin gesto en el menú (R14.5).
6. **Esqueletos, no ruedas.**
   - Las primeras cargas pintan esqueletos con las medidas finales.
   - Solo aparecen si la carga tarda más de 300 ms, así no parpadean.
7. **Vibraciones con significado y no más:** éxito al tomar el control, ligera al
   enviar, aviso en un conflicto (412 o 409).
8. **Movimiento reducido** (R14.7). Todo lo anterior pasa a un fundido corto o a
   instantáneo.
9. **Presupuesto.**
   - Las transiciones duran 300 ms o menos.
   - Nada en bucle, salvo el indicador «Reconectando», que se apaga con
     movimiento reducido.
   - Todo corre en el hilo de UI, a 60 fps en un teléfono medio.

**Con qué:**
- `react-native-reanimated`, con sus transiciones de layout y
  `useReducedMotion`;
- `react-native-gesture-handler`, para deslizar;
- `expo-haptics`.

Los tres son MIT, y `expo-router` ya trae `react-native-screens` y
`react-native-safe-area-context`.

---

## Licencias de lo que entra (constitución §VIII)

Todo es MIT, Apache-2.0 o BSD, con su LICENSE leído el 2026-10-19 por la
investigación de Fase 0. El párrafo citado se copia en la tarea de instalación.

| Dependencia | Licencia | Dónde |
|---|---|---|
| `expo` 58, `expo-router`, `expo-web-browser`, `expo-secure-store`, `expo-notifications`, `expo-image-picker`, `expo-document-picker`, `expo-image`, `expo-localization`, `expo-network`, `expo-updates`, `expo-crypto`, `jest-expo` | MIT (expo/expo LICENSE) | `apps/mobile` |
| `react-native` 0.88, `react` 19.3 | MIT | `apps/mobile` |
| `react-native-reanimated` (la versión que fija el SDK), `react-native-gesture-handler`, `expo-haptics`, `react-native-screens`, `react-native-safe-area-context` | MIT | `apps/mobile` |
| `@tanstack/react-query` 5 | MIT | `apps/mobile` |
| `openapi-fetch` 0.17 y `openapi-typescript` 7 | MIT | `apps/mobile` y su script |
| `eventsource-parser` 4 | MIT | `apps/mobile` |
| `culori` 4 | MIT | Script de tokens |
| `@testing-library/react-native` 14 | MIT | `apps/mobile` (pruebas) |
| Maestro CLI 2 | Apache-2.0 | Pruebas de punta a punta |
| `h2`, a través de `httpx[http2]` | MIT | `apps/worker` |
| **EAS** (Build, Submit, Update) | Servicio propietario, Expo Terms del 2025-06-30. Es un servicio, no código que se distribuye | Tubería |

### Lo instalado (T006, 2026-10-20)

Versiones exactas de `apps/mobile/pnpm-lock.yaml` y `apps/worker/uv.lock`, con
el LICENSE de cada paquete leído en `node_modules` o en el `dist-info`. Todos
llevan el texto MIT estándar; su párrafo de concesión, idéntico en todos, es:

> «Permission is hereby granted, free of charge, to any person obtaining a copy
> of this software and associated documentation files (the "Software"), to deal
> in the Software without restriction, including without limitation the rights
> to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
> copies of the Software, and to permit persons to whom the Software is
> furnished to do so, subject to the following conditions:»

La única condición es conservar el aviso de copyright, que va en los paquetes
tal cual se instalan. Ninguno añade cláusulas sobre uso multi-tenant o como
servicio (el problema de las «MIT modificadas» de abajo).

| Paquete | Versión | Licencia | Titular (línea de copyright del LICENSE) |
|---|---|---|---|
| `expo` (y los `expo-*` del SDK, `jest-expo`) | 58.0.16 (módulos 58.x) | MIT | 650 Industries, Inc. (aka Expo) |
| `expo-device` (nuevo: el nombre del teléfono en «Tus teléfonos») | 58.0.5 | MIT | 650 Industries, Inc. (aka Expo) |
| `expo-font` (dependencia par de `expo-symbols`; sin ella Android cae) | 58.0.9 | MIT | 650 Industries, Inc. (aka Expo) |
| `react-native` | 0.88.0 | MIT | Meta Platforms, Inc. and affiliates |
| `react-native-reanimated` | 4.7.1 | MIT | Software Mansion |
| `react-native-worklets` (lo trae reanimated 4) | 0.13.0 | MIT | «nobody» (Software Mansion) |
| `react-native-gesture-handler` | 3.3.0 | MIT | Software Mansion |
| `react-native-keyboard-controller` (nuevo: el teclado del hilo) | 1.22.7 | MIT | Kiryl Ziusko |
| `@tanstack/react-query` | 5.104.5 | MIT | Tanner Linsley |
| `openapi-fetch` | 0.17.0 | MIT | Drew Powers |
| `openapi-typescript` | 7.13.0 | MIT | Drew Powers |
| `eventsource-parser` | 4.1.2 | MIT | Espen Hovlandsdal |
| `culori` | 4.0.2 | MIT | Dan Burzo |
| `@testing-library/react-native` | 14.1.0 | MIT | Callstack and Rally Health |
| `@types/node`, `@types/jest`, `@types/culori` | 24.x / 30.x / 4.x | MIT | DefinitelyTyped |
| `h2` (por `httpx[http2]`, en el worker) | 4.4.1 | MIT | Cory Benfield and contributors |

**Maestro** (Apache-2.0) es una herramienta de la máquina de pruebas, no se
instala en el repo. **EAS** es un servicio: sus términos (Expo Terms del
2025-06-30) rigen el uso de la cuenta de FACELAD, y lo que procesa —código y
builds, nunca datos de clientes— está en la lectura de RGPD de la KB
(`compliance/2026-10-19-avisos-del-telefono.md`).

**Ya no hacen falta, tras el cambio a avisos normales:** `@bacons/apple-targets`.

**Descartadas por licencia:** `expo-notification-service-extension-plugin` y
`onesignal-expo-plugin` llevan una «MIT modificada» que solo permite su uso con
OneSignal.
