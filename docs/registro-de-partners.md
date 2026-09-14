# El registro autónomo de partners

Cómo alguien pasa de «quiere ser partner» a «tiene una consola con su empresa
dentro», sin que nadie del equipo ejecute nada. Implementa la spec
[`006-registro-de-partners`](../specs/006-registro-de-partners/spec.md) y la
decisión [[ADR-038]] de la KB.

Estado al **2026-09-13**: construido y probado; **apagado por bandera en los dos
lados**. Falta el panel de operador (US4), el archivado por inactividad y el
paso por staging.

---

## 1 · El recorrido, en tres actos

```
POST /console/signup                    → fila en signup_requests + correo. NO crea nada más.
GET  /console/signup/{token}            → ¿sigue viva la solicitud?
POST /console/signup/{token}/complete   → en UNA transacción:
                                            partner + invitación owner + accept() + sesión
```

**El tercer acto no escribe `partner_memberships`.** Crea el partner, emite una
invitación de `owner` para el correo ya verificado y llama a
`PartnerInvitationRepository.accept()` — el mismo camino por el que entra
cualquier invitado desde la migración 0080. Podría insertar la membresía
directamente y serían diez líneas menos; no se hace porque entonces habría
**dos** caminos a esa tabla, y el que menos se usa es el que se queda sin la
regla nueva.

El partner nace **en Free**: sin fila en `partner_subscriptions`, porque la
ausencia de fila *es* Free y es un estado válido y diseñado.

## 1 bis · La lista pública del proxy, y cómo el alta llegó rota a staging

El alta se construyó entera —API, formularios, correo, Google—, pasó la
verificación completa en verde y se desplegó a staging **sin poder usarse**.

`apps/console/src/proxy.ts` (el «middleware» de Next 16) rebota a `/login`
cualquier ruta que no esté en su lista `PUBLIC`, y `/signup` no estaba. O sea:
la única gente para la que existe el registro —la que no tiene cuenta— rebotaba
a `/login?from=/signup` antes de ver el formulario. `/auth/google/callback`
tampoco estaba, así que la vuelta de Google, que llega del navegador con
`?code=&state=` y sin cookie, rebotaba igual.

**Nada de esto lo podía ver una prueba de las que había.** Las de componente
montan la página directamente, las de la API no pasan por Next y `next build`
no ejerce el enrutado. Se descubrió mirando la URL desplegada: un `curl` a
`console.staging.auphere.com/signup` devolviendo `307`.

Ahora hay `src/__tests__/proxy-public-routes.test.ts`, que fija ruta por ruta
qué puede abrir un desconocido y qué sigue cerrado. **Una ruta nueva que alguien
sin sesión deba alcanzar se añade a `PUBLIC` en el mismo commit que la crea.**

## 2 · Por qué estos endpoints no son anónimos

Van detrás del **token de servicio del BFF**, igual que `/console/auth/*` y
`/console/invitations/*`. La anonimidad del registro vive en el borde
**navegador ↔ BFF**; el borde **BFF ↔ API** nunca es anónimo (ADR-032).

No es una preferencia: `tests/isolation/test_console_scope.py` exige 401 sin
token en **toda** ruta registrada, y esa suite bloquea el merge.

## 3 · Nadie puede averiguar qué correos existen

`POST /console/signup` responde **202 con el mismo cuerpo byte a byte** exista o
no la dirección. Lo que cambia es el correo que llega: el enlace del alta, o un
«ya tienes cuenta, entra por aquí».

Los cuatro casos de token muerto —inexistente, caducado, usado, revocado— dan el
mismo 404 con el mismo cuerpo.

La consola **tampoco** distingue: ser más amable con quien ya tiene cuenta
reabriría desde el navegador el oráculo que la API cierra.

## 4 · El límite de ritmo, y lo que hubo que arreglar antes

Dos cubos independientes, por correo (hasheado) y por IP. **Tres por minuto**,
más estricto que el login: pedir el alta manda un correo, y un correo cuesta
dinero y reputación de dominio; un intento de login sólo cuesta un hash.

> **El cubo «por IP» del login no limitaba por IP.** Nada reenviaba la IP del
> cliente, así que detrás del BFF la API veía la misma para todo el mundo. Se
> arregló con `X-Nexus-Client-IP`, que pone el BFF y sólo el BFF —
> `X-Forwarded-For` lo puede poner cualquiera que alcance la API. Sin cabecera
> se cae a un **cubo único con nombre**, en vez de fingir que hay límite.
>
> Quedan **dos sitios con el fallo original**: `api/console/invitations.py` y
> `api/admin/auth.py`. Fuera del alcance de la spec 006.

**El límite se comprueba antes de mandar nada.** Un limitador que responde 429
después de haber mandado el correo no contiene el abuso, sólo lo documenta.

## 5 · Entrar con Google

OIDC contra Google **directamente**, sin proveedor de identidad intermedio
(ADR-038 D5): las próximas integraciones son leer Calendar o Gmail para un
teammate, y eso pide tokens propios con autorización incremental.

Tres cosas sostienen la seguridad del recorrido:

- **`email_verified`.** Google emite un `id_token` con correo para *cualquier*
  cuenta, verificada o no. Sin esa bandera, cualquiera registra una cuenta de
  Google con el correo de otra persona y llega con una identidad ajena. Se
  acepta booleano o la cadena `"true"`; **`"false"` como texto no cuela**,
  porque una cadena no vacía sería verdadera en una comprobación ingenua.
- **El `state` firmado** (`services/oauth_state.py`, compartido con TikTok).
- **El uso único**, que lo da consumir el `code_verifier` de Redis de forma
  atómica. Una firma no puede impedir que el mismo `state` se presente dos veces.

El verificador restringe el algoritmo a **RS256**. No es ceremonia: la clave
pública de Google es pública, y un verificador que aceptara HS256 daría por
bueno un token firmado con esa clave pública **como secreto compartido**. Hay
una prueba que forja ese token a mano.

**Preguntar si hay Google no crea nada, y hubo que arreglarlo.** El botón
decidía si pintarse llamando a `/console/auth/google/start`, que es el endpoint
que **empieza** un inicio de sesión: acuña un par PKCE y lo guarda diez minutos
en Redis. Como preguntaba al montar y volvía a llamar al pulsar, cada visita a
`/login` —una página pública— dejaba una clave que nadie iba a consumir jamás.
Ahora hay `GET /console/auth/google/available`, que sólo responde, y la consola
lo resuelve **en el servidor**: la página se renderiza con la respuesta dentro,
sin llamada desde el navegador y sin el parpadeo del botón que aparece y se va.

Responde **200 con `false`**, no 503: que no haya Google es una respuesta, no un
fallo, y la consola necesita distinguir «no hay» de «no se pudo preguntar». Un
fallo del backend se trata como «no hay» — no se anuncia lo que no se puede
demostrar.

**La identidad se ancla al `sub`, no al correo.** Un correo cambia de dueño; en
Workspace se reasigna cada vez que alguien se va. El `sub` no se reasigna nunca.

**No se guarda ningún token del proveedor.** El `id_token` ya trae `sub` y
`email_verified`, y no se pide `refresh_token` porque hoy no hay ámbito que
refrescar. Guardarlos sería una credencial almacenada sin lector — la figura de
`NEXUS_WEBHOOK_HMAC_SECRET`.

## 5 bis · El cliente OAuth de Google, y cómo está montado

Proyecto **`auphere-nexus`** en Google Cloud, bajo la organización `auphere.com`
— no bajo una cuenta personal, para que sobreviva a quien lo creó.

**Un cliente OAuth por entorno, no uno compartido.** El `client_secret` de
staging vive en máquinas de desarrollo; el de producción no. Con un solo
cliente para los dos, comprometer staging sería comprometer producción.

| Entorno | Redirect URI autorizado |
|---|---|
| staging | `https://console.staging.auphere.com/auth/google/callback` |
| dev local | `http://localhost:3110/auth/google/callback` (en el cliente de staging) |
| producción | `https://console.auphere.com/auth/google/callback` |

**«Authorized JavaScript origins» se deja vacío a propósito.** El canje del
código lo hace el servidor; ningún JavaScript del navegador habla con Google.
Rellenarlo sería declarar una superficie que no existe.

**Audiencia `External`, estado `In production`.** `Internal` sólo dejaría entrar
cuentas de `auphere.com`, y quien se registra es justo alguien de fuera.
`Testing` tiene un tope de **100 usuarios contados para toda la vida del
proyecto**, que no se reinicia.

**Los ámbitos son `openid`, `email` y `profile`, y por eso no hace falta
verificación de Google.** Su propio Verification Center lo dice: *«Verification
is not required since your app is not requesting any sensitive or restricted
scopes»*. Cuando una spec futura pida leer Calendar o Gmail para un teammate,
eso **sí** será un ámbito sensible y **sí** exigirá pasar revisión — conviene
saberlo antes de prometer fechas.

**El logo está subido pero no se muestra**, y es el estado esperado: enseñar
marca propia en la pantalla de consentimiento exige verificación de marca
aparte (demostrar la propiedad del dominio en Search Console y esperar revisión).
No bloquea entrar: la pantalla dice «Auphere» y el dominio. Está sin mandar a
propósito.

## 5 ter · Un correo que no sale no se anuncia como enviado

Encontrado en staging, no en el repositorio. El dominio no estaba verificado en
Resend, que devolvió `403 The auphere.com domain is not verified`, y la API
respondió **202 «revisa tu correo»** igual. Quien pide el alta lee que hay un
enlace esperando, no llega nada, y el único rastro es una línea de log — con la
circularidad de que la alerta que avisaría de que el correo está roto **se manda
por correo**.

La causa no era el proveedor: era que `send_email` devuelve `False` y nadie
miraba el resultado.

| Situación | Respuesta | Por qué |
|---|---|---|
| Sin proveedor configurado | `202` | No es una avería. Ese entorno no manda correo y nunca prometió hacerlo. |
| Proveedor configurado que rechaza | `502` | Eso es una avería, y callársela convierte el alta en un callejón sin salida silencioso. |

**El 502 no abre el oráculo que `CE-004` cierra.** Que el proveedor rechace no
depende de la dirección: le pasa a todas por igual, así que la respuesta sigue
siendo idéntica exista o no la cuenta. Hay una prueba que lo fija, y una
mutación que la pone roja si alguien hace que el fallo dependa del correo.

> **El paso de Mailhog del quickstart no puede funcionar.** `docker-compose`
> levanta Mailhog, pero `services/email.py` sólo habla con Resend: en local
> `email_enabled` es `False` y no se manda nada a ninguna parte. El enlace del
> alta en desarrollo se saca de la base de datos, no de `localhost:8025`.

## 5 quater · De quién viene el correo

**`no-reply@auphere.com`, y es una decisión, no una herencia.**

Salía de `facturacion@auphere.com` porque `send_email` cae a
`receipt_from_email` cuando quien llama no pasa remitente. El primer correo que
recibe alguien que no te conoce no puede venir de «facturación»: todavía no hay
nada que facturar, invita a marcarlo como no deseado, y ensucia la reputación de
la dirección que **sí** tiene que llegar cuando haya recibos de verdad.

Los dos correos del alta —el enlace y el «ya tienes cuenta»— usan el **mismo**
remitente. Que vinieran de sitios distintos delataría cuál te tocó, que es justo
lo que `CE-004` cierra.

No hace falta configurar nada más: Resend verifica el **dominio**, así que
cualquier buzón de `auphere.com` sale en cuanto el dominio está verificado.

## 6 · Las banderas, y que tienen que coincidir

| Dónde | Ajuste | Defecto |
|---|---|---|
| API | `signup_enabled` | `False` |
| Consola | `NEXUS_SIGNUP_ENABLED` | `false` |

**Si la consola la enciende y la API no, el formulario da 503 al enviar**, que
es peor que no existir. Con la bandera apagada, `/signup` devuelve 404 y el
login no enseña enlace: no hay botón gris ni pantalla que explique lo que no
hay (constitución §V).

Google es independiente: sin `google_client_id/secret/redirect_uri` el botón
**no se pinta**, y el alta con contraseña sigue funcionando. La guarda de
arranque rechaza tener esos tres a medias.

### Encenderlo, y en qué orden

**Secreto → Terraform → despliegue.** Nunca al revés: una definición de tarea
que pide una clave ausente del secreto **no arranca**
(`ResourceInitializationError: did not contain json key`), y ese apply se lleva
por delante los cinco servicios del entorno.

```bash
# 1 · El secreto. Los valores salen del JSON que descarga Google, así que
#     ningún secreto pasa por la pantalla ni por el historial del shell.
J=~/Downloads/client_secret_<id>.apps.googleusercontent.com.json
export NEXUS_GOOGLE_CLIENT_ID=$(jq -r .web.client_id "$J")
export NEXUS_GOOGLE_CLIENT_SECRET=$(jq -r .web.client_secret "$J")
export NEXUS_GOOGLE_REDIRECT_URI=https://console.staging.auphere.com/auth/google/callback
AWS_PROFILE=nexus ./infra/scripts/add_app_secret_keys.sh staging \
  NEXUS_GOOGLE_CLIENT_ID NEXUS_GOOGLE_CLIENT_SECRET NEXUS_GOOGLE_REDIRECT_URI

# 2 · Terraform. `app_secret_keys` es una lista COMPARTIDA por los dos
#     workspaces: prod necesita las tres claves aunque prod todavía no abra
#     el alta, o su próximo apply no arranca.
# 3 · Despliegue.
```

La consola va aparte, en Vercel: `NEXUS_SIGNUP_ENABLED=true` en el proyecto del
entorno. **Las dos banderas se encienden en la misma ventana**, no en días
distintos.

## 7 · La solicitud, y lo que caduca

`public.signup_requests` guarda **sólo** el SHA-256 del token y la IP hasheada.
TTL de **24 h**, no los 21 días de una invitación: una invitación la manda
alguien que te conoce; una solicitud de alta la pide un desconocido y su correo
está en la bandeja ahora mismo.

Pedir el alta dos veces **revoca la anterior**: un enlace viejo no debe seguir
abriendo la puerta después de que su dueño pidiera otro, y el motivo habitual
para pedir otro es sospechar del primero.

La caducidad se marca de dos formas, y las dos hacen falta: **perezosamente**
al mirar la fila (para que el estado sea verdad entre pasadas) y con el cron
`expire-signups-cron` (para limpiar lo que nadie vuelve a mirar, que es el caso
normal de un alta abandonada).

> Ese cron se declara en **dos** sitios: `bootstrap.SCHEDULER_TASK_NAMES` y el
> contrato de `tests/unit/test_bootstrap_split.py`. Olvidar el segundo abortó
> dos despliegues (2026-09-11 y 2026-09-13).

## 8 · Lo que ve el operador

Al abrir la puerta, el panel deja de ser donde se crean los partners y pasa a
ser donde uno **se entera** de los que se crearon sin él. Eso es `/signups`.

La tabla mezcla a propósito dos cosas que no son iguales —empresas ya nacidas y
registros a medias—: separarlas en dos pantallas escondería justo la relación
que el operador necesita ver.

**La vía de entrada sale de `signup_requests.provider`, no de `partners`.** Lo
que faltaba para R8.1 no era un atributo del partner sino saber *qué partner
salió de qué solicitud*, y eso es una relación: `signup_requests.partner_id`
(migración 0119). Se podría haber añadido `partners.created_via`; no se hace por
lo mismo que no se le añade un tercer estado — esa tabla la lee media
plataforma, y cada columna nueva es una que alguien tendrá que interpretar en
sitios que hoy ni se sospechan. `ON DELETE SET NULL`: borrar un partner no borra
el rastro de que alguien se registró.

**`provider` nunca sale `null`.** En la base, nulo significa «con contraseña»;
obligar a quien lee el panel a saber eso es trasladarle un detalle de
almacenamiento. La API lo traduce a `password`.

**El nivel es `free` cuando no hay fila en `partner_subscriptions`**, porque la
ausencia de fila *es* Free (ADR-037), no la ausencia de un dato.

### Las dos acciones, sin entrar en la VPC (R8.2)

| | |
|---|---|
| **Suspender** | `PATCH /admin/partners/{id}` con `status`. **Ya existía**; no hizo falta nada. |
| **Reenviar el enlace** | `POST /admin/signups/{id}/resend`. Esto era lo único que obligaba a abrir una consola dentro de la VPC. |

Reemitir **mata el enlace anterior** — `create` revoca las pendientes de ese
correo. Con dos vivos, reenviar duplicaría la superficie en vez de reemplazarla,
y el enlace viejo seguiría abriendo una cuenta.

Sólo sobre una solicitud **viva**: 409 si está consumida —ya tiene cuenta, y
reenviarle un alta la mandaría a rehacer lo hecho— o caducada, porque resucitar
un plazo desde el panel lo convierte en una sugerencia. En los dos casos el
camino es que la persona vuelva a pedirlo. Queda rastro en auditoría
(`signup.resend`): una acción de operador que manda un correo a un desconocido
no puede no dejarlo.

## 9 · Lo que todavía no está

- **El archivado por inactividad** (180 días, R6.3–6.5). Necesita un tercer
  valor en `partners.status`, que hoy sólo admite `active` y `suspended` y se
  lee por toda la plataforma. Merece su propia pasada, no un añadido.
- **El paso por staging** del recorrido completo, con la comparación de tiempos
  de respuesta entre correo existente y nuevo.
