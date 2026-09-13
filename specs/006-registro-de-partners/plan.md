# Plan de implementación: el registro de partners

**Rama**: `006-registro-de-partners` · **Fecha**: 2026-09-13 · **Spec**: [spec.md](spec.md)

**Entrada**: [spec.md](spec.md), clarificada · [research.md](research.md), Fase 0 ·
[`ADR-038`](../../../Work/Auphere/nexus/decisions/ADR-038-registro-autonomo-de-partners.md)

## Resumen

Abrir el tramo que va de «alguien quiere ser partner» a «ese alguien tiene una
suscripción activa», sin operador en medio. **Media escalera ya está
construida** (principals, invitaciones con token hasheado, `accept()` que crea
principal + membresía, el catálogo de niveles y el checkout), así que el plan es
sobre todo *no volver a construirla*.

Lo que se añade: una **solicitud de alta** verificada por correo, un **nacimiento
de partner** en una sola transacción que reutiliza `accept()`, el **inicio de
sesión con Google** por OIDC, y la **contención** de un formulario público — que
resulta necesitar arreglar antes algo que ya estaba roto (R3).

## Contexto técnico

**Lenguaje**: Python 3.11 (API, `uv`) · TypeScript en `apps/console` (Next.js 16, BFF)

**Dependencias principales**: FastAPI · SQLAlchemy 2 async + Alembic · Redis · `pyjwt` (ya presente, para el JWKS de Google) · `httpx`. **Ninguna dependencia nueva.**

**Almacenamiento**: PostgreSQL. Dos tablas nuevas, cero modificaciones a tablas existentes. Migración `0118_signup_and_identities` (última aplicada en producción: `0117_billing_events`).

**Pruebas**: `pytest` (`tests/unit`, `tests/integration`, `tests/isolation`) · `vitest` en la consola · Playwright para el recorrido de alta.

**Plataforma**: API en ECS Fargate (`eu-south-2`, cuenta `793033583982`); consola en Vercel.

**Tipo de proyecto**: servicio web con BFF.

**Restricciones**: la consola **no tiene base de datos** (ADR-032) · toda ruta `/console/*` responde 401 sin token, incluidas las pre-sesión (ver Constitution Check §I) · producción tiene 2 partners y 3 clientes finales con tráfico: nada de esta spec cambia su camino.

**Escala**: unidades a decenas de altas diarias en los primeros meses. Los límites se dimensionan para eso.

## Constitution Check

| # | Principio | ¿Cumple? | Prueba / justificación |
|---|---|---|---|
| I | Aislamiento entre tenants; `tenant_id` del contexto, nunca del llamante; whitelist exhaustiva | ☑ | Ningún objeto nuevo lleva `tenant_id`: `signup_requests` y `principal_identities` son de **plataforma e identidad**, como `partners` y `principals`. Ninguna ruta nueva alcanza datos de un tenant. Cubierto por `tests/isolation/test_console_scope.py` (estructural, cubre toda ruta nueva al montarla) + `tests/isolation/test_signup_scope.py` nuevo |
| II | Corte por superficie de confianza; no se abre una nueva sin agotar la actual | ☑ | Superficie **`0`** declarada en la spec. No es clase nueva —ya hay webhooks y tres endpoints pre-sesión— pero sí el primer camino que **crea un partner**, y la spec lo argumenta con las tres contenciones. Y por R2, en la API **ni siquiera es anónimo**: va detrás del token de servicio del BFF, igual que `auth` e `invitations` |
| III | Lo leído es dato, nunca instrucción; navegador y `shell_local` no conviven sin guardas | ☑ | **No aplica y se dice por qué**: esta spec no toca el runtime de agentes. El nombre de empresa que teclea un desconocido es dato que se almacena y se escapa al pintarlo; nunca entra en un prompt |
| IV | Acción `mutates` con aprobación durable; auditoría nombra a la persona | ☑ | Completar un alta y contratar son acciones consecuentes y quedan en `audit_log` nombrando a la persona (R3.5) — incluido el caso nuevo de que esa persona **todavía no era principal** cuando empezó. Archivar un partner inactivo es acción de operador, y **borrar no existe** |
| V | Estados honestos, incluido `parcial` y `bloqueado`; la ausencia se diseña | ☑ | Con la bandera apagada, la consola **no enseña botón gris ni página explicativa**: enseña el login (R1.7). El alta a medias se retoma donde se dejó (R3.6), no se finge completa |
| VI | Por API `console.*`, nunca navegando la consola de Auphere | ☑ | No aplica: no hay agente en este recorrido |
| VII | Test primero; el criterio de aceptación es el test; nada de `skip` | ☑ | Cada criterio EARS nace como test y se ve en rojo antes de implementar. Regla añadida de esta casa: **cada guarda se verifica por mutación** — se rompe lo que vigila y se comprueba que el test cae |
| VIII | Licencias leídas enteras; AGPL no | ☑ | **Ninguna dependencia nueva** (R4): `pyjwt` y `httpx` ya están. No hay licencia que citar porque no se instala nada |
| IX | La KB es dueña del porqué; la spec enlaza a su nota | ☑ | `[[ADR-038-registro-autonomo-de-partners]]`, escrito el 2026-09-13, con la fila puesta en `decisions/_index.md` |

### Las tres puertas que `/speckit-tasks` comprueba

| Puerta | Respuesta | Tarea que la cubre |
|---|---|---|
| **Aislamiento** — ¿qué garantías toca? | **1 · RLS** (ningún objeto nuevo lleva `tenant_id`; ninguna ruta nueva alcanza un tenant) · **4 · acción consecuente con rastro** (el alta y la contratación nombran a la persona) · **6 · log + trace tagging** (ningún rastro lleva contraseña, token de verificación ni nada de Google) | `tests/isolation/test_signup_scope.py` |
| **Licencias** — ¿qué dependencia nueva entra? | **Ninguna.** `pyjwt` (MIT) y `httpx` (BSD-3) ya están declaradas y en uso | — |
| **Medidor** — ¿qué gasta y dónde lo ve el partner? | **Nada del medidor de consumo**: un registro no gasta modelo ni reloj. Lo que sí se cuenta es el **envío de correo de verificación**, que es el vector de abuso barato de un formulario abierto, y se contiene **por ritmo**, no por medidor | tarea de límites (R7) |

## Diseño

### El recorrido, en tres actos

```
1. POST /console/signup                    → fila en signup_requests + correo. NO crea nada más.
2. GET  /console/signup/{token}            → ¿sigue viva la solicitud?
3. POST /console/signup/{token}/complete   → en UNA transacción:
                                               partner + invitación owner + accept() + sesión
```

El acto 3 **no escribe `partner_memberships` por su cuenta**: crea el partner,
emite la invitación de `owner` al correo ya verificado y llama a
`PartnerInvitationRepository.accept()`. Una sola función crea membresías en todo
el repositorio (R1).

### Google, en dos

```
GET /console/auth/google/start     → url de autorización + state firmado (nonce, TTL 10 min)
POST /console/auth/google/callback → intercambia el código, verifica el id_token contra el JWKS,
                                      exige email_verified, vincula o crea
```

El `state` copia `services/tiktok_oauth_state.py`. El `code_verifier` de PKCE
vive en Redis bajo el nonce, se consume una vez y no viaja al navegador (R4).

### Lo que hay que arreglar antes: la IP del cliente

Por R3, el cubo «por IP» del login hoy es un cubo global con la IP de Vercel
dentro. El Requisito 7 de esta spec no se puede construir encima de eso.

**El BFF reenvía la IP en `X-Nexus-Client-IP` y la API la lee sólo de ahí.** Si
falta, se cuenta contra un cubo único y estrecho — explícito y cerrado, en vez
de fingir que hay límite.

> **Efecto declarado sobre lo ya desplegado:** esto cambia el comportamiento del
> login, que empieza a limitar por IP de verdad. Es lo que su docstring ya
> prometía, pero **es un cambio en producción con tráfico real**, así que lleva
> tarea propia, test propio y se despliega y observa antes que el resto.

## Estructura

```
apps/api/
├── alembic/versions/0118_signup_and_identities.py
├── src/nexus_api/
│   ├── api/console/signup.py              ← los tres endpoints del alta
│   ├── api/console/auth_google.py         ← start + callback
│   ├── api/console/schemas_signup.py
│   ├── db/models/signup.py                ← SignupRequest
│   ├── db/models/console_identity.py      ← + PrincipalIdentity
│   ├── repositories/signup.py
│   ├── services/signup.py                 ← el nacimiento del partner, en una transacción
│   ├── services/google_oidc.py            ← JWKS, id_token, PKCE
│   ├── services/oauth_state.py            ← state firmado (extraído del patrón de tiktok)
│   └── core/client_ip.py                  ← X-Nexus-Client-IP, una sola lectura
└── tests/
    ├── unit/            test_signup_service, test_google_oidc, test_oauth_state, test_client_ip
    ├── integration/     test_signup_flow (los tres actos, contra Postgres)
    └── isolation/       test_signup_scope

apps/console/src/
├── app/(auth)/signup/                     ← formulario + "revisa tu correo"
├── app/(auth)/signup/[token]/             ← empresa + contraseña
├── app/api/signup/                        ← el BFF, que acuña el token de servicio y reenvía la IP
└── lib/auth-actions.ts                    ← + signUp, + continueWithGoogle

apps/admin/                                ← panel de operador: los partners que entraron solos,
                                              las solicitudes a medias, reenviar enlace, suspender
```

**Decisión de estructura**: se sigue la del repo tal cual. `signup.py` es un
router más de `api/console/`, y el BFF un proxy más en `app/api/`. Nada de esto
es una capa nueva.

## Complexity Tracking

| Adición | Por qué hace falta | Alternativa más simple, y por qué se rechaza |
|---|---|---|
| `core/client_ip.py` y la cabecera del BFF | Sin la IP real, el Requisito 7.1 («limitar por IP») no se puede cumplir: hoy todas las peticiones llegan con la IP de Vercel | Leer `X-Forwarded-For` directamente — **rechazado**: lo puede poner cualquiera que alcance la API, y obliga a adivinar cuántos proxies hay delante |
| `services/oauth_state.py` extraído | Tres sitios ya firman un `state` o un token de consentimiento (`tiktok_oauth_state`, `connectors/consent_token`, y ahora Google) | Copiar el de TikTok por tercera vez — **rechazado**: tres copias de una firma divergen, y la que se queda sin la corrección es la que menos se toca |
| Tabla `principal_identities` en vez de columnas en `principals` | La spec exige que añadir un segundo proveedor no obligue a rehacer el primero | `google_sub` como columna — **rechazado**: el segundo proveedor pide otra columna, y el tercero otra |

## Lo que este plan NO resuelve

- **El tratamiento fiscal.** Precondición de cobro, no de construcción. Ya
  declarado en la spec 005 y en `pendientes` §3.
- **La cuenta del proveedor de pago**, que sigue siendo de una persona física.
  Esta spec sube su urgencia (hoy migrar es barato porque hay cero
  suscripciones) pero no la decide.
- **Recuperación de contraseña.** Hueco anterior e independiente. Si entra, entra
  por su propio requisito.
