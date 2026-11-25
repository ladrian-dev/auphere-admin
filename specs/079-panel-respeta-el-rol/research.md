# Investigación: el panel respeta el rol del operador

Fase 0 de [`plan.md`](plan.md). Cada decisión dice qué se eligió, por qué y qué se
descartó. Hecha el 2026-11-25 sobre `origin/develop` e26c4f0b.

## Lo que hay hoy

- **El panel** (`apps/admin`, Next 16.2, React 19.2) resuelve la sesión en cada petición
  con `POST /admin/auth/session`, que devuelve el operador con `role` y `access`.
  `requireOperator()` (`src/lib/session.ts`) solo mira `access`. El rol solo lo miran
  `requireQAOperator()` (`src/lib/qa-access.ts`, siete rutas de `app/api/qa`) y
  `qa/page.tsx`.
- **Las llamadas a la API** salen de cuatro sitios: `call()` en `src/lib/backend.ts`
  (que usan también los seis `backend-*.ts`), `src/lib/qa-api.ts`, las tres rutas de
  flujo de `app/api` con `fetch` propio y `src/lib/operator-auth.ts` (login y sesión).
  Desde la enmienda de la 078 (PR 61), todas leen el token de servicio de un único
  sitio, `adminToken()` en `src/lib/admin-token.ts`. Algunas añaden `X-Operator-Id`.
- **La API** monta 64 routers bajo `/admin` (`api/admin/__init__.py`), con 245 rutas.
  El token de servicio se exige router a router; no hay un punto único. Una parte de
  las rutas nombra al operador por `X-Operator-Id`, de formas distintas; el resto no lo
  nombra, y sus escrituras se auditan con un actor genérico del panel, el mismo para
  todo el equipo.
- **Las acciones** devuelven formas distintas: `ActionResult<T>`, `Result<T>`
  (`src/lib/action-result.ts`), `AccessOutcome`, `GuideResult`, datos sueltos y
  `Promise<never>`. 88 de los 125 componentes de cliente llaman a alguna.
- **La consola de partners** tiene el patrón de permisos del repo: la matriz vive en
  la API (`core/console_auth.py`), cada ruta declara el suyo
  (`require_console_principal("clients:write")`) y la consola guarda una copia para
  pintar (`apps/console/src/lib/permissions.ts`) con una prueba de deriva.
- **El rol por defecto** es `qa_operator` (`operator_identity.DEFAULT_ROLE`, y el
  `server_default` de la columna).

## D1 — La guarda pide el permiso como argumento obligatorio

**Decisión**: `requireOperator(permission)`, con el permiso obligatorio. Sigue siendo
la primera sentencia de cada acción, página, layout y ruta, como exige la 078. La
versión sin argumento desaparece.

**Por qué**: la prueba estructural de la 078 ya barre «la guarda es lo primero». Basta
con que además lea el argumento: un literal que esté en la matriz. Ninguna de las 129
acciones cambia de forma ni de tipo de retorno.

**Descartado**:
- *Envolver cada acción* (`export const x = guarded("money", async (op, …) => …)`).
  Cambia la forma de las 129, obliga a un tipo de rechazo común a funciones que
  devuelven cosas distintas, y la prueba de la 078 tendría que aprender otra forma.
- *Un valor por defecto* (`read`). Una acción nueva que olvide el permiso pasaría con
  `read`: es justo el olvido que la spec quiere parar (4.2).

## D2 — Qué pasa cuando falta el permiso

| Dónde | Respuesta | Por qué |
|---|---|---|
| Server Action | Deja una línea de registro y **redirige a la misma página** con un aviso. Antes invalida el layout del panel para que el menú y los controles se pinten con el rol vigente. | `redirect()` es lo que la guarda ya hace sin sesión o con la cuenta deshabilitada: no hay que tocar ninguna acción. El operador se queda donde estaba, ve la página sin el control y un aviso de que la acción no se hizo (spec 2.2). |
| Página o layout | `notFound()` | §V: no se explica qué falta (spec 2.7). Ya hay `app/not-found.tsx`. |
| Ruta de `app/api` | 401 sin sesión; 403 en los demás casos. Nunca redirige. | Igual que la 078 (2.3) y que `requireQAOperator`: las piden `fetch` y flujos de eventos. |
| Rol desconocido | `/sin-acceso` en acciones y páginas; 403 en rutas | Falla cerrado (spec 1.4). `/sin-acceso` pasa a mirar lo mismo; si no, iría y volvería a `/tenants`. |

La página de destino sale de la cabecera `Referer` de la petición de la acción, que va
a la URL de la propia página. Solo vale si es del mismo host, y su ruta pasa por
`safeRedirect()` (`src/lib/safe-redirect.ts`, de la enmienda de la 078): un flujo para
las redirecciones de vuelta, no dos. Si no vale, se va a `/`. Comprobado el
2026-11-25: el panel no fija `Referrer-Policy`, así que el navegador manda la ruta
entera dentro del mismo origen. Las cinco acciones que se invocan solas (al montar o
por sondeo) piden `read`, así que un rechazo no puede repetirse en bucle.

El aviso lo pinta un componente del armazón que lee un parámetro de la URL, enseña un
aviso («Tu rol no permite esa acción; no se hizo nada») y quita el parámetro.

**Descartado**:
- *Lanzar un error*. En producción Next cambia el mensaje de una Server Action por uno
  genérico, y el error sube al límite de errores: saca al operador de la página.
- *`forbidden()` de Next*. Sigue siendo experimental (`authInterrupts`) y pinta una
  pantalla de «prohibido» en vez de la página.
- *Devolver un rechazo tipado*. Exige cambiar el tipo de retorno de las 129 acciones y
  el manejo de cada llamada.

**El registro**: una línea estructurada con `event: "operator.permission_denied"`, el
id del operador, su rol, el permiso y el nombre de la acción o ruta. Sin argumentos de
la acción: pueden llevar datos de un cliente.

## D3 — La matriz vive en la API; el panel guarda una copia vigilada

**Decisión**: la matriz se escribe una vez en la API (`core/operator_permissions.py`,
un diccionario literal permiso → roles). El panel tiene su copia en
`src/lib/permissions.ts` para decidir y pintar, y una prueba del panel **lee el archivo
de Python** y falla si la copia difiere.

**Por qué**:
- Es el patrón de la consola (un flujo por concepto). La copia de la consola se
  compara con una instantánea escrita a mano. Leer el archivo de verdad caza la deriva
  aunque alguien cambie las dos instantáneas a la vez.
- La fase 1 no depende de que la API esté desplegada antes. Si la sesión devolviera
  la lista de permisos ya resuelta y el panel saliera primero (Vercel despliega en
  minutos y ECS en unos quince), el panel no tendría permisos que leer y dejaría fuera
  a todo el equipo hasta que llegara la API.
- En la fase 2 la API decide con la misma matriz que ya existe.

**Descartado**:
- *Solo en el panel*. La fase 2 tendría que copiarla a la API después: dos sitios
  desde el principio, y sin autoridad clara.
- *Un JSON compartido*. La imagen de la API se construye desde `apps/api`, y el panel
  se despliega desde `apps/admin`: uno de los dos se quedaría sin el archivo.

## D4 — Cómo sabe la interfaz qué pintar (fase 1b)

**Decisión**: el layout de `(dashboard)` pasa el rol a un proveedor de contexto, y los
componentes preguntan `useCan("money")`. Las páginas de servidor usan
`can(operator, "money")` con el operador que les devuelve la guarda.

- El menú lateral (`components/shell/nav.ts`) añade un permiso a cada entrada;
  `navFor()` filtra por rol.
- La paleta ⌘K (`command-palette.tsx`) usa la misma lista filtrada.
- Un vacío con acción de crear la pinta solo si `useCan` lo permite.
- El menú del operador sigue nombrando el rol (spec 3.4).

**Por qué**: es la forma más corta de llegar a 88 componentes sin pasar el permiso
prop a prop. La API nunca confía en la interfaz: la decisión de verdad es la guarda.

**Riesgo asumido**: el layout no se vuelve a ejecutar al navegar. Si cambia el rol a
mitad de sesión, el contexto se queda viejo hasta recargar o hasta el primer rechazo,
que invalida el layout (D2). La seguridad no depende de eso.

## D5 — El Playground QA entra por la misma guarda

`requireQAOperator()`, `QA_ROLES` y la explicación de `qa/page.tsx` («Tu rol no abre el
Playground») desaparecen. Las rutas de `app/api/qa` y las tres páginas de QA piden
`qa` con la guarda común. La entrada del menú se oculta a quien no tiene `qa`.

## D6 — Separar `setTenantStatusAction`

Hoy pausa, reanuda y archiva con un argumento. Se parte en dos acciones: pausar y
reanudar (`operate`) y archivar (`delete`). Archivar es borrar (§IV). Las dos llaman a
la misma ruta de la API.

## D7 — La suplantación abierta deja de valer sin el permiso (fase 1b)

El panel lee la cookie de suplantación en el layout de la ficha del partner. Si el
operador no tiene `impersonate`, el panel ignora la cookie y la borra. No hace falta
revocarla en la API: caduca sola, y en la fase 2 la API ya no la acepta de quien no
tiene el permiso.

## D8 — El rol por defecto pasa a `viewer` (fase 1b)

Cambian `operator_identity.DEFAULT_ROLE` y el `server_default` de la columna, con una
migración que solo toca el valor por defecto: no cambia el rol de ninguna cuenta que ya
exista. El script de alta ya acepta `--role`. Va en la 1b y no en el envío del
2026-11-26: una migración más en un envío de madrugada no compensa, y el script de alta
siempre pasa un rol.

Los textos que dicen que el rol no decide nada en `/admin/*` (el docstring de
`services/operator_identity.py`, el comentario del modelo, la migración 0089 y el
docstring de `seed_operator.py`) se corrigen en la 1a, con la guarda.

## D9 — Fase 2: la credencial del operador es su propia sesión

**Decisión**: en cada llamada, el panel manda el token de servicio (dice «soy el panel»)
**y** el token de sesión del operador (dice «soy esta persona»), en una cabecera
propia. La API resuelve la sesión con el mismo código que `/admin/auth/session` (hash,
caducidad, cuenta activa), lee el rol de la base y aplica la matriz de la ruta.

**Por qué**:
- La API ya emite, guarda y revoca esas sesiones (ADR-034). Es la credencial que ya
  prueba la contraseña del operador: no hay claves nuevas que generar ni rotar.
- La revocación es inmediata: cerrar sesión o deshabilitar la cuenta corta las
  llamadas en la siguiente petición.
- Un token de servicio filtrado, solo, ya no basta; una sesión robada, sin el token de
  servicio, tampoco.

**Descartado**:
- *Un JWT EdDSA de 60 s por llamada, como la consola*. La consola lo usa porque no
  puede guardar una credencial de la API ni tiene una sesión de la API. El panel tiene
  las dos. ADR-034 ya descartó copiar ese mecanismo para el login por la misma razón:
  añade un par de claves sin quitar ninguna capacidad.
- *`X-Operator-Id`*. Es una afirmación del panel que la API no puede comprobar. Era la
  opción B de `/speckit-clarify`, y Luis eligió la credencial propia.

**Cómo se resuelve**: `resolve_session` (`services/identity.py`) busca por el hash
SHA-256, borra la sesión si caducó (siete días, sin renovación) y apunta `last_used_at`
como mucho cada cinco minutos, así que **escribe** y necesita su transacción. No mira
`disabled_at`: eso lo hace `load_operator_view`, y la dependencia llama a las dos. El
esquema `operator_auth` no da permisos a `nexus_app`, así que la resolución abre su
propia sesión de base, como ya hace `operator_from_header`.

**Coste**: una búsqueda por clave primaria por llamada, en una sesión de base aparte.
Una página hace unas cinco en paralelo; no hace falta caché.

**Cuidado**: la cabecera con la sesión no se registra nunca, ni en la API ni en el
panel.

## D10 — Fase 2: la sesión viaja junto al token de servicio

La enmienda de la 078 ya dejó un único sitio para el token de servicio
(`adminToken()`, con su prueba). No se toca. Cada sitio que hoy llama a `adminToken()`
para hablar con `/admin/*` o `/qa/*` (`call()`, `qa-api.ts` y las tres rutas de flujo)
añade la sesión del operador, que lee `operatorSessionToken()` de `src/lib/session.ts`
desde la cookie. `operator-auth.ts` no la añade: hace el login y resuelve la sesión.

Una prueba del panel falla si un archivo que llama a `adminToken()`, salvo
`operator-auth.ts`, no manda también la sesión.

**Descartado**: *rehacer las cuatro salidas como un cliente único nuevo*. Cambiaría el
módulo que la enmienda de la 078 acaba de cerrar y no añade nada que la prueba no dé.

## D11 — Fase 2: una sola dependencia en la API

`require_panel_operator("money")` sustituye a `require_operator`,
`require_enabled_operator`, `operator_from_header`, la comprobación propia de
`impersonate.py` y la cabecera de `require_qa_operator`. Como `require_console_principal`,
falla al importar si recibe un permiso que no está en la matriz.

- **QA**: `require_qa_operator` resuelve la sesión y devuelve el id del operador; el
  `app.operator_id` que usa la RLS de `qa.*` no cambia de forma. La API ejecuta el grafo
  en su propio proceso, así que `apps/qa-langgraph-server` (solo de desarrollo) no
  entra.
- **Auditoría**: el actor pasa a ser siempre `operator:<correo>` del operador
  verificado. Desaparece el actor genérico del panel.
- **Barrido**: una prueba recorre `app.routes` y, para cada ruta bajo `/admin`, las
  dependencias anidadas (`route.dependant.dependencies`), como ya hace
  `tests/integration/test_device_bridge_inbound.py`. Falla si una ruta no depende de
  `require_panel_operator` ni está en la lista de rutas de servicio (spec 6.5). No mira
  códigos de estado: algunas rutas contestan 404 antes que 401
  (`tests/isolation/test_phone_cannot_reach_partner_or_admin.py` lo avisa).

## D12 — Fase 2: rutas de servicio

Ningún servicio automático llama a `/admin/*`: ni el worker, ni la consola, ni el
escritorio, ni la app, ni la tubería. Así que la lista de rutas que no actúan por un
operador es corta:

| Ruta | Por qué no lleva operador |
|---|---|
| `POST /admin/auth/login`, `/session`, `/logout` | Abren, resuelven y cierran la sesión: aún no la hay, o va en el cuerpo. |
| `GET /admin/integrations/tiktok/callback` | La abre el navegador del dueño del negocio al volver de TikTok, y se confía en el `state` firmado, no en el token de servicio. |

Lo que sí llama a `/admin/*` con el token de servicio son guiones y pruebas que lanza
una persona a mano. En la fase 2 pasan a entrar como operador (login y la sesión en la
cabecera) o se retiran:

| Quién | Qué hace | Fase 2 |
|---|---|---|
| `scripts/ops/prueba-plantilla-muna.sh` | Crea y revoca una clave de partner | Entra como operador |
| `apps/api/tests/release/test_release_smoke.py` | Lee clientes y métricas de aislamiento | Entra como operador |
| `apps/api/tests/release/test_booking_brake_staging.py` | Lee conversaciones (manual) | Entra como operador |
| `apps/api/RUNBOOK.md` | Un `curl` de ejemplo | Se reescribe |
| `scripts/smoke_test_block_n.sh` | Llama a rutas que ya no existen | Se retira |

## D13 — El orden de despliegue

- **Fase 1a** (envío del 2026-11-26): la parte de la API es solo el archivo de la
  matriz, que no cambia ninguna respuesta, así que el orden da igual. Los roles de
  producción se revisaron el 2026-11-25 en solo lectura: nadie pierde acceso (spec 5.1).
  En staging, Luis decide si las cuentas `qa_operator` pasan a `admin`.
- **Fase 1b**: la migración del rol por defecto va con la API; la interfaz, con el
  panel. El orden da igual: la migración no cambia ninguna cuenta.
- **Fase 2**: primero el panel empieza a mandar la sesión (la API de antes la ignora),
  después la API empieza a exigirla. Al revés, el panel quedaría sin poder llamar a la
  API durante el despliegue.
