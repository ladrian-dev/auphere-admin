# El puesto de trabajo en la aplicación de escritorio

**Spec viva.** Describe lo que existe hoy en `apps/desktop`, `apps/api` y
`apps/console` para la identidad y el puesto de trabajo de la máquina del
partner. Si cambias lo que describe, este documento va **en el mismo commit**
(`docs/spec-driven-development.md` §3). Especificaciones de origen:
`specs/001-puesto-trabajo-partner/` (ejecución local, contención, lista blanca)
`specs/002-identidad-app-escritorio/` (identidad, dueño de la máquina) y
`specs/012-la-maquina-se-registra-con-la-sesion/` (registro con la sesión, y la
retirada del código de emparejamiento).

## Qué es la aplicación

Una **cáscara** de Electron con dos vistas en una `BaseWindow`:

| Vista | Partición | `preload` | Qué carga |
|---|---|---|---|
| Armazón | `auphere-app` (no persistente) | `app-preload.cjs`, lista cerrada | `dist/app/index.html` — ocupa **toda** la ventana |
| Consola | `persist:auphere-console` (persistente) | **ninguno** | la consola **entera**, encima del armazón, desde la franja hacia abajo |

El ambiente del agente vive en una **tercera** partición (`auphere-agent`, no
persistente) y no alcanza ninguna de las otras dos. `session-isolation.ts` lo
comprueba al arrancar y `tests/session-isolation.test.ts` lo afirma.

> **La barra del puesto de 44 px ya no existe** (spec 010, D2-A). Era una cuarta
> partición con su propio `preload` de siete funciones, y sus hojas caían fuera
> de una ventana de 44 px con `overflow: hidden` — el foco iba a un campo
> invisible y la persona tecleaba a ciegas (P0-2 de la evaluación del
> 2026-09-17). Lo que hacía vive ahora en el armazón: el estado de la máquina al
> pie de la lista lateral, y declarar directorios y desemparejar como **diálogos
> de la aplicación**. Emparejar ya no es ninguno: ocurre al entrar.

> La pantalla de operar y todo lo que cuelga de ella (roster, hilo, Pendientes,
> Cuenta, ejecución en la máquina) se describen en
> [`docs/desktop-teammates.md`](desktop-teammates.md). Este documento es la
> identidad, el emparejamiento y la contención.

**La consola no puede hablarle a la cáscara.** Sin `preload` en su vista no hay
canal, y sigue sin haberlo. Lo que cambió con la spec 012 es que **ya no hace
falta**: el canal entre las dos era la persona copiando un código, y ahora la
cáscara habla con el BFF por su cuenta, desde el proceso principal y con la
cookie de su partición.

## Cómo entra una persona

Con el login de la consola, dentro de la ventana. La aplicación **no tiene
flujo de autenticación propio** (`tests/no-own-auth.test.ts`) y no guarda
ninguna credencial de backend: en su partición solo hay la cookie opaca de la
consola. El alta de un partner es un acto de Auphere seguido de una invitación
por correo; no hay registro.

Quién está dentro lo lee el **proceso principal** con
`GET /api/session/whoami` del BFF, con la cookie de la partición humana, al
arrancar y en cada cambio de la cookie `nexus-console.session`
(`src/session-gate.ts`, `src/electron/adapters.ts`). La respuesta trae también el
idioma de la cuenta, y la aplicación lo adopta entera —menús, diálogos nativos,
avisos y la bandeja del sistema incluidos (R12.2):

| `whoami` | El puesto | El puente |
|---|---|---|
| 200 `{user_id, partner_slug, locale}` con credencial guardada para ese `user_id` | `conectada` (en el idioma de la cuenta) | arranca |
| 200 sin credencial | se **registra sola** con esa sesión; si no se puede, `sin_emparejar` con el motivo | arranca tras registrar |
| 401 (sin sesión) · 403 `no_membership` | `sin_sesion` | parado |

## Cómo se registra una máquina

**Entrar la deja lista. No hay código que teclear** (spec 012).

1. La persona entra por el navegador (RFC 8252 + PKCE, spec 009). Al volver, la
   puerta de sesión confirma quién es.
2. Si esa persona no tiene máquina, la aplicación llama —desde el proceso
   principal, con la cookie de la partición humana— a
   `POST /api/desktop/register-machine` del BFF, que reenvía a
   `POST /console/workstation/machines` con su token de servicio.
3. La API comprueba el permiso `workstation:pair` (owner · admin · builder) y
   que la sesión **se abrió hace menos de una hora**. Se mira el momento de
   apertura, no el de último uso: tener la aplicación abierta mueve el segundo y
   no demuestra nada.
4. La respuesta trae la credencial **una vez**. La aplicación la guarda cifrada
   con `safeStorage` en `userData/credentials.bin`, en un mapa por `user_id`
   (`src/credential-store.ts`). Sin cifrado disponible no se guarda nada y la
   aplicación lo dice.

La máquina queda a nombre del **partner y de la persona** que entró
(`partner_devices.partner_id`, `principal_id`), con su `install_id` — que dice
qué instalación es y vive **aparte de la credencial**, para que sobreviva a
desemparejar.

**Tope**: cinco máquinas activas por persona. Las archivadas no cuentan.

### Por qué se retiró el código de 8 símbolos

Para poder teclearlo, la aplicación **ya tenía** la sesión confirmada: `pair()`
abortaba sin `userId`, y `userId` solo llegaba de un `whoami` con éxito. Eran dos
actos para probar una sola cosa, y el segundo no probaba nada. Además, «teclea
este código» es el patrón que explotó Storm-2372 contra el device code flow:
retirarlo cierra un vector, no abre uno.

Lo que **no** se retiró son sus propiedades, que la spec 009 ya había dejado
escritas al retirar el otro código: uso único, hash en reposo, rechazo
indistinguible y techo de intentos. Siguen aplicando al registro.

Y un aviso para quien lea el historial: `core/pairing_codes.py` y
`services/device_pairing.py` **no eran del emparejamiento**. Los códigos de
sesión de la spec 009 compartían su generador y su limitador, así que retirarlos
habría roto el inicio de sesión. Viven renombrados a lo que hacen:
`core/one_time_codes.py` y `services/one_time_code_limits.py`.

Y el otro aviso, que costó una tanda entera de restos: **retirar un endpoint no
retira a su cliente.** El escritorio conservó durante toda la retirada su
`HttpTransport.pair()` contra `POST /device/pair`, con su clase de error y un
test verde, porque nadie lo llamaba y el barrido buscaba **nombres de símbolos**
del lado del servidor. Ahora busca también la **ruta**: es la única cadena que
los dos extremos están obligados a compartir, y por eso es la que los caza a los
dos (`tests/isolation/test_39_no_pairing_code_path.py`).

## La credencial y sus cinco operaciones

JWT HS256, claims `{svc: "device", sub: device_id, pid: partner_id, gen}`,
12 h. **No lleva tenant.** `require_device` (`api/device_bridge.py`) verifica
la firma y **carga la fila** en cada petición: archivada → `403
device_archived` con motivo; generación vieja fuera de la gracia de 60 s →
`401`; treinta días sin latir → `403 pairing_required`.

| Operación | Ruta | Ámbito |
|---|---|---|
| Latir | `POST /device/heartbeat` | partner · solo mueve `last_heartbeat_at` |
| Sondear | `GET /device/poll` | partner · devuelve `work[]` y `links[]` (clientes vinculados y cuáles no tienen directorio) |

> Desde la spec 003 `work[]` **ya no vuelve vacío**: lleva lo que un teammate
> pidió ejecutar, con su `task_id`. El ciclo completo está en
> `specs/003-teammates-app-escritorio/contracts/local-dispatch.md`.
| Devolver resultado | `POST /device/result` | tenant del asiento, comprobado dentro del partner |
| Renovar | `POST /device/renew` | partner · `gen + 1`; la anterior vale 60 s más |
| Declarar directorio | `POST /device/links` | tenant resuelto desde `client_ref` **dentro del partner**; ajeno → `404` con asiento |

**Son cinco, y desde la spec 012 no hay una sexta ni una ruta anónima.**
`/device/pair` era la única de `/device/*` montada sin credencial —el código
*era* la credencial de un solo uso— y al mudarse el alta a la consola esa
excepción se quedó sin caso. `test_device_bridge_inbound.py` lo vigila con la
lista de excepciones vacía: añadir una obliga a escribirla y a razonarla.

La máquina renueva sola cuando le quedan menos de 6 h (`AppRuntime.maybeRenew`).

`/workstation` refresca sus datos con la cadencia del latido mientras la
pestaña está visible (`components/workstation/presence-refresh.tsx`): la
presencia se ve sin recargar a mano.

## De quién es una máquina, y quién la ve

`partner_devices` lleva RLS **forzada con dos políticas OR**: la dueña
(`app.partner_id` + `app.principal_id`) y el gestor (`app.partner_id` +
`app.workstation_manager = 'true'`, que la dependencia de consola fija solo con
`workstation:write`). Sin GUC, cero filas. `PartnerDeviceRepository.list_visible`
no filtra nada: la RLS decide (`test_30`).

Los clientes a los que sirve una máquina y el directorio de cada uno viven en
`device_client_links`, por tenant (RLS de tenant) y legibles por quien ve la
máquina (política de lectura por máquina). El directorio se declara **desde la
máquina** con el selector nativo (`src/directory-declare.ts`, cuatro
comprobaciones); la consola no acepta rutas.

La presencia de un tenant pasa por sus vínculos con directorio cuya máquina late
y no está archivada (`services/device_presence.tenant_presence`).

## Cerrar sesión, desemparejar, archivar

| Acto | Dónde | Qué pasa |
|---|---|---|
| Cerrar sesión | Cuenta, en la consola | la cookie cambia → `whoami` 401 → el latido para, el puesto dice `sin_sesion`; la credencial se conserva sellada para la misma persona |
| Desemparejar | el diálogo de la aplicación, que explica qué deja de funcionar y qué no (R8.5) | la aplicación **olvida** la credencial y deja de latir; la máquina queda `ausente` hasta que alguien la archive |
| Archivar | `/workstation` → Archivar, o la pertenencia retirada | `revoked_at` + motivo (`archivada_consola` · `pertenencia_retirada` · `desemparejada`); el siguiente latido recibe `403 device_archived` y el puesto pasa a `archivada_desde_consola`. Terminal: se empareja otra |

## Cómo se entra, y por dónde vuelve el navegador

**Spec**: `specs/009-volver-y-entrar-desde-la-app/` · **Contrato**:
[`bar-preload.md`](../specs/009-volver-y-entrar-desde-la-app/contracts/bar-preload.md)

Dos cosas que la spec 009 añadió, y la segunda cambió una garantía.

**Volver a la pantalla del equipo.** Existió mientras la ventana enseñaba **una
superficie u otra**: con la consola delante, la barra ofrecía la vuelta. La spec
010 lo retiró con la barra — la consola se pinta **dentro del panel** del
armazón y no hay a dónde volver: la persona elige secciones, no superficies.

**Entrar.** Es **RFC 8252**: *authorization code* + PKCE con retorno a
`127.0.0.1`, lo mismo que hacen Claude Code, `gh` y `gcloud`. La cáscara genera
el par PKCE, levanta un oyente efímero, manda el navegador del sistema a
`/desktop-auth`, y canjea el código con el `fetch` de su partición — **así que la
cookie la guarda la partición y la aplicación nunca ve un token**. El Requisito
2.1 de la spec 002 sigue siendo cierto sin excepciones.

**El canje va contra la consola (`POST /api/desktop/redeem`), no contra la API.**
Las dos mitades de esa frase importan y se aprendieron rompiéndolo. La ruta de
la API exige la credencial de servicio del BFF, y la cáscara no tiene ninguna ni
puede tenerla; llamando directamente recibía `401 Missing bearer token`, y el
inicio de sesión no terminaba nunca **sin que se viera**, porque en el navegador
todo salía bien. Y aunque no exigiera credencial, la API devuelve el token en
JSON: la sesión de la aplicación es la cookie del origen de la consola, así que
un token en el cuerpo no habría hecho entrar a nadie. La consola es el único
sitio que tiene la credencial y a la vez puede poner la cookie; por eso contesta
`204` y nada más.

> **Esto enmendó el Requisito 6 de la spec 001.** Decía «el puente es saliente» a
> secas; ahora dice que nunca escucha **en la red** y que escucha en loopback
> sólo mientras dura un inicio de sesión, con cuatro condiciones (criterio 6.5)
> que `apps/desktop/tests/no-inbound.test.ts` comprueba recorriendo el fuente.
> Ese test sigue prohibiendo cualquier otro oyente: la excepción es **una**.
>
> **Lo que se pierde, dicho en voz alta**: durante esos segundos otro proceso de
> la misma máquina puede hablarle a ese puerto. Es el riesgo que PKCE cubre — sin
> el `code_verifier`, que no sale del proceso, el código no vale.

Antes se construyó otra cosa: un código que la persona tecleaba en la aplicación. Era
un RFC 8628 hecho a mano y al revés, y se retiró. El porqué está en
`[[ADR-039-volver-y-entrar-desde-la-app-de-escritorio]]`.

## Cómo se distribuye y cómo se actualiza

**Spec**: `specs/008-empaquetado-firma-y-canal/` · **Contrato**:
[`release-channel.md`](../specs/008-empaquetado-firma-y-canal/contracts/release-channel.md)

**El canal de actualización es una superficie de confianza**, de la misma clase
que la ejecución local: lo que se publique ahí reemplaza el binario que ejecuta
comandos en la máquina del partner. Por eso:

| Regla | Dónde vive |
|---|---|
| Solo lectura para todo el mundo, sin credenciales en el cliente | Bucket privado + CloudFront con OAC (`infra/terraform/40-releases/`) |
| Escribe una sola identidad, **distinta de la que despliega** | Rol OIDC `nexus-<ws>-desktop-publisher`, sin permiso de borrado |
| Publicar es **añadir**: la versión anterior se queda | Versionado del bucket + el workflow no borra nada |
| Todo lo publicado pasó por la cadena | `.github/workflows/release-desktop.yml`, con disparo manual para que nadie firme en su portátil |

La cadena corre en **`macos-latest`** —el único trabajo del repositorio que no
es Ubuntu— porque firmar y notarizar sólo se puede hacer en macOS. Importa el
certificado a un **llavero temporal** que destruye siempre, y **abre el `.app`
firmado antes de publicar**: `hardenedRuntime` sin los permisos correctos no
falla al construir, falla al abrir.

> **Y abre sólo el de la arquitectura del runner**, que es arm64. El `.app` de
> Intel se verifica (firma, notarización, sello) pero **no se abre nunca**:
> abrirlo ahí exigiría Rosetta, que los runners de GitHub no tienen. Es el hueco
> por el que v0.1.0 y v0.1.1 publicaron un x64 de 2,1 GB que en un Mac Intel
> sale con código 1 a los 290 ms. Cerrarlo del todo pide un runner Intel o una
> máquina de pruebas; mientras tanto, **el x64 se prueba a mano o no se prueba**.

### Qué comprueba la app antes de actualizarse

El orden **es** la política (`src/update-policy.ts`), y falla cerrada:

1. ¿Este binario lleva nuestra firma de distribución? Si no, **no le pregunta
   nada al canal** — ni aunque ya tenga un paquete descargado.
2. ¿Hay versión nueva? La descarga sin preguntar y sin interrumpir.

> **Esto describe la política, y la política estuvo bien desde el principio. Lo
> que no corría era el paso 2.** En v0.1.0 y v0.1.1 la carga del módulo de
> `electron-updater` lanzaba un `TypeError` antes de armar nada, así que
> **ninguna máquina llegó a preguntarle al canal ni una vez**. Arreglado el
> 2026-09-15 (`.specify/bugs/updater-no-arranca/`), a partir de 0.1.2.
>
> Se pudo publicar así porque este camino es **inalcanzable salvo en un binario
> empaquetado y firmado**: en desarrollo el paso 1 devuelve `unpackaged` y la
> política corta antes. La primera vez que corrió fue la primera publicación
> real.
3. ¿Hay sesión de agente viva o aprobación pendiente? **Espera, y lo dice.**
4. Si no, se instala **al salir**. Nunca reiniciando por su cuenta.

Las aprobaciones de nivel `informativo` no cuentan: no esperan a nadie.

### La versión mínima admisible

Vive en el **latido**, que es lo único que corre solo y cada poco
(`desktop_version.py`). **Está apagada**: `desktop_min_version` vacío significa
que no se rechaza a nadie, y ése es el estado del despliegue actual.

Tres reglas cuando se encienda:

- **Preaviso obligatorio.** `desktop_min_version_from` es la fecha de entrada en
  vigor; antes de ella la puerta no cierra aunque el mínimo esté declarado. Es
  lo que hace comprobable el aviso — Slack avisa seis meses antes, Zoom noventa
  días.
- **Avisar ≠ bloquear.** Una versión vieja pero admisible sigue funcionando.
- **Sólo por contrato roto o seguridad.** No es una palanca para empujar
  mejoras: una máquina bloqueada es un partner que no puede trabajar.

**Falla abierto**, a diferencia de casi todo lo demás aquí: si la máquina no
dice su versión, o la versión no se puede leer, **pasa**. El riesgo de dejar
entrar una versión vieja es mucho menor que el de dejar fuera a un partner por
un guion mal puesto.

## Los estados del puesto

`comprobando · sin_emparejar · emparejando · conectada · reconectando ·
sin_sesion · volver_a_emparejar · archivada_desde_consola ·
version_no_admitida` — `src/workstation-state.ts`. Ninguno se pinta como error;
las herramientas locales solo existen en `conectada`; el latido solo corre en
`conectada` y `reconectando`.

`comprobando` entra con la spec 010: al arrancar no consta todavía si la máquina
está emparejada, y enseñar `sin_emparejar` mientras se comprueba era afirmar algo
que no se sabe. Cada estado lleva además **desde cuándo** lo es y, cuando se
sabe, **de qué** se reconecta (`sin_red` · `sin_ejecutor` · `sesion_perdida`): el
2026-09-17 el puesto pasó horas en `reconectando` sin decir ninguna de las dos
cosas, mientras la consola daba la máquina por emparejada.

**Y un octavo dato que NO es un estado**: `update`, que dice si hay una versión
descargada y si está **lista** («se instala al cerrar») o **esperando** («a que
termine lo que hay vivo»). Va aparte de `status` a propósito: son ortogonales
—una máquina puede estar `conectada` **y** tener una versión esperando— y
meterlo en la enumeración obligaría a elegir cuál de las dos cosas se pinta.
**Ausente significa que no hay nada que decir**: sin versión esperando, el
armazón no muestra indicador apagado ni texto explicando lo que no hay.

## Lo que la consola sabe de la cáscara

Una sola cosa: el agente de usuario lleva `AuphereDesktop/<versión>`
(`lib/shell-ua.ts`). Se usa en **un solo sitio** — la página de canales, que
dentro de la aplicación sustituye la conexión de Meta por «continúa en el
navegador» — y `shell-detect.test.ts` afirma que no hay un segundo.

## Auditoría

`audit_log`, filas de partner (`target = partner:<id>`, `tenant_id` NULL) salvo
la declaración de directorio, que es del tenant del cliente. Vocabulario:
`device.pair_code_issued` · `device.paired` · `device.pair_denied` ·
`device.renewed` (actor `device:<id>`) · `device.link_declared` ·
`device.link_denied` · `device.unpaired` · `device.archived` (migración `0108`),
más `principal.access_revoked` (migración `0124`).

**Dos entradas del vocabulario no las escribe nadie, y es a propósito.**
`device.unpaired` y el motivo de revocación `desemparejada` se declararon
cuando se pensaba que desemparejar llamaría al servidor. La enmienda T048 de la
spec 002 decidió lo contrario —archivar es un acto de persona con su nombre
(R13.1) y la credencial no gana una sexta operación (R4.2)—, así que
desemparejar quedó como un acto **local**: la aplicación olvida su credencial y
la máquina queda pendiente de archivar desde la consola. Las dos entradas se
quedaron sin escritor y **nadie las limpió**.

Se dejan escritas aquí en vez de retirarlas o inventarles uso, que es lo que
hace falta: quien las encuentre no descubrió un defecto, encontró el rastro de
una decisión. Si algún día desemparejar pasa a llamar al servidor, ya tienen
sitio.

### Retirar todo el acceso de una persona (spec 012)

`DELETE /console/team/members/{id}/access`, permiso **`team:manage`**. Cierra
**todas** sus sesiones de consola y archiva **todas** sus máquinas, en una
transacción: o las dos mitades, o ninguna. Deja `principal.access_revoked`.

Vive bajo `/console/team/*` y no bajo `/console/workstation/*` por el permiso:
allí el permiso es `workstation:pair`, que tiene el builder porque es «reclamar
lo que es tuyo». Retirarle el acceso a **otra persona** es lo contrario, y con
aquel permiso un builder podría echar a un owner.

Corre con el rol dueño —es mantenimiento de plataforma, como archivar las
máquinas de quien pierde la pertenencia—, así que **la RLS no la protege**: lo
único que la acota es su `WHERE` por persona, y eso lo vigila
`tests/isolation/test_38_principal_access_revocation_scope.py`.

## Desarrollo local

```bash
docker compose up -d
cd apps/api && uv run alembic upgrade head && uv run uvicorn nexus_api.main:app --reload
cd apps/console && pnpm dev                     # http://localhost:3110
cd apps/desktop && pnpm build && \
  AUPHERE_CONSOLE_URL=http://localhost:3110 AUPHERE_API_URL=http://127.0.0.1:8000 pnpm start
```

La variable `AUPHERE_DEVICE_TOKEN` **ya no existe**: la credencial se obtiene
emparejando. `scripts/enrol_device_dev.py` se borró con la spec 002.
