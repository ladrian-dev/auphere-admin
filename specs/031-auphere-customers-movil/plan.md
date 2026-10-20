# Implementation Plan: Auphere Customers, la Consola Lite en el teléfono

**Branch**: `031-auphere-customers-movil` | **Date**: 2026-10-19 | **Spec**: [spec.md](spec.md)

**Input**: `specs/031-auphere-customers-movil/spec.md` ·
[research.md](research.md) · KB
`[[research/2026-10-19-consola-lite-movil]]`

## Summary

**Qué se construye.** Una app nativa, **Auphere Customers**, hecha con Expo
SDK 58, en `apps/mobile` y en su propio workspace. Es otra cara de la Consola
Lite de la spec 030: las mismas rutas `/console/lite/*`, las mismas cifras y las
mismas acciones.

**Lo nuevo:**
- **El teléfono es una sesión que la API conoce.**
  - Se entra en la propia app (D2b, enmienda del 2026-10-20): correo y
    contraseña contra la API, o Google con el flujo web de Google alojado en la
    API y un código de un uso con PKCE que la app canjea. Nada pasa por la
    consola de partners.
  - La app guarda dos credenciales: acceso y renovación.
  - `require_client_principal` gana una rama de teléfono que acaba en el mismo
    `ClientPrincipal`, así que **ninguna ruta lite cambia su autorización**.
- **Los avisos son normales y salen de un outbox.**
  - El evento se escribe en la transacción del hecho.
  - Una tarea nueva del worker lo reparte por teléfono al enviar y compone el
    aviso con su título y su texto mínimo, en el idioma del teléfono.
  - Lo envía a APNs y FCM, y el sistema lo muestra tal cual. Sin código nativo
    propio.
- **Revocar es inmediato.** Cada petición del teléfono vuelve a comprobar la
  fila y la membresía. Se puede cerrar un teléfono desde la consola web, desde
  el admin y desde las revocaciones que ya existen.

**Dos arreglos que sirven también a la web:**
- envío idempotente con `Idempotency-Key`;
- el orden de los módulos, que sale de la API (`/me.nav`).

**Cuatro iteraciones, cada una entregable y en orden de riesgo:**

0. **Spike S1** por el flujo `assess`. No se fusiona. Confirma en dispositivo
   el SDK 58, la entrada con vuelta universal, avisos reales de APNs y FCM, las
   pestañas que se ocultan, reanimated y EAS desde el workspace anidado.
1. **La puerta y lo que se lee.** H1, H5 y H6: entrar, quedarse, pestañas
   dinámicas, Inicio, Consumo, versión mínima, revocar, y teléfonos en la web y
   en el admin.
2. **La Bandeja.** H3, H4 y H8: lista, hilo, tiempo real, tomar el control,
   enviar de forma idempotente, adjuntos, devolver, resolver, contacto y notas.
3. **Los avisos.** H2 y H7: permiso, canales y categorías, registro del
   destino, outbox, worker, envío a APNs y FCM, y Ajustes.

El **piloto en las pruebas cerradas** de las tiendas empieza al cerrar la
iteración 2. Los avisos lo completan en la 3.

## Technical Context

| | |
|---|---|
| **Language/Version** | Python 3.14 (API y worker) · TypeScript 5 (consola, admin y app). Sin código nativo propio: la app usa los módulos de Expo |
| **Primary Dependencies** | **App:** Expo SDK 58 (React Native 0.88, React 19.3.0), expo-router con pestañas nativas, expo-web-browser, expo-secure-store, expo-notifications, expo-updates, @tanstack/react-query 5, openapi-fetch, eventsource-parser, react-native-reanimated, react-native-gesture-handler y expo-haptics. **Worker:** `httpx[http2]`, que trae `h2`. Todo lo demás ya está. Licencias en [research.md](research.md#licencias-de-lo-que-entra-constitución-viii) |
| **Storage** | Postgres, con RLS forzada en las tablas nuevas. Migraciones **0158–0162** ([data-model.md](data-model.md)). En el teléfono, solo el almacén seguro y la caché de react-query en memoria. Nada de los clientes finales en disco, salvo la caché de imágenes del sistema |
| **Testing** | pytest (`apps/api/tests/{unit,integration,isolation}`, `apps/worker/tests`) · vitest + Playwright/axe (consola) · vitest (admin) · jest-expo + RNTL 14 (app) · Maestro (de punta a punta en simulador y emulador) · lista manual de VoiceOver y TalkBack en `evidence/` |
| **Target Platform** | iOS 16.4+ y Android con targetSdk 36 (lo que exige Play desde el 31-08-2026). API y worker en AWS `eu-south-2`; consola y admin en Vercel |
| **Project Type** | móvil + API: monorepo con API, worker, dos apps Next.js, escritorio y ahora una app Expo |
| **Performance Goals** | Aviso de espera en el teléfono en menos de 10 s, p95 (CE-002) · cambios de la Bandeja en menos de 5 s en primer plano (R5.4) · revocación efectiva en la siguiente petición; avisos ya cortados en el siguiente reparto (CE-007 pide menos de 15 min) · arranque en frío hasta Inicio en menos de 2 s en un teléfono medio |
| **Constraints** | El cliente nunca es argumento. En el camino de Apple y Google, solo el texto mínimo del aviso (R9). Movimiento con presupuesto: 300 ms o menos, una sola coreografía y movimiento reducido respetado (D24). Sin hex escritos a mano: tokens generados. ES/EN, claro/oscuro, texto del sistema al máximo, WCAG 2.2 AA y objetivos de 44 pt y 48 dp. Cuenta de FACELAD con migración prevista |
| **Scale/Scope** | Decenas de clientes con Lite al principio, de 1 a 10 personas por cliente y de 1 a 2 teléfonos por persona. Unas 12 pantallas en la app |

## Constitution Check

*Rellenado antes de la Fase 0 y comprobado otra vez tras el diseño: sigue en verde.*

| # | Principio | ¿Cumple? | Prueba / justificación |
|---|---|---|---|
| I | Aislamiento entre tenants; `tenant_id` del contexto, nunca del llamante; whitelist exhaustiva | ☑ | Las tablas nuevas llevan RLS `ENABLE`+`FORCE` y FK compuestas. La fila del teléfono se lee como identidad, como ya se hace con la membresía, y la credencial no lleva tenant (research D3). Seis barridos nuevos en `apps/api/tests/isolation/`: `test_phone_route_scope.py`, `test_phone_client_vs_client.py`, `test_phone_revocation.py`, `test_push_payload_no_customer_content.py`, `test_phone_cannot_reach_partner_or_admin.py` y `test_phone_list_scope.py` (R15) |
| II | Corte por superficie de confianza; no se abre una nueva sin agotar la actual | ☑ | Superficie `0`, ya abierta. El camino de salida a Apple y Google lleva solo el texto mínimo del aviso (R9), con Apple y Google como encargados y su lectura de RGPD (D21). Las iteraciones van de lo que se lee a lo que escribe, y después a lo que sale fuera |
| III | Lo leído es dato, nunca instrucción | ☑ | El texto del aviso lo compone el servidor a partir de datos, recortado, y no tiene efectos. Nada de lo que manda la app (`display_name`, la versión o el idioma) cambia permisos |
| IV | Acción `mutates` con aprobación durable; auditoría nombra a la persona | ☑ | Las acciones las hace una persona en su nombre, como en la spec 030. Entrar y cerrar teléfonos se audita con `client:<correo>` u `operator:<correo>`, y la revocación automática con `system` y su razón. Un teléfono revocado se archiva, no se borra |
| V | Estados honestos, incluido `parcial` y `bloqueado`; la ausencia se diseña | ☑ | Cada pantalla tiene cargando, vacío, error, reconectando y parcial (el Panel ya trae `errors`). Sin red, se lee lo último y se marca como no actualizado. Sin módulo no hay pestaña; sin permiso de avisos no hay interruptores muertos; persona de partner y acceso apagado tienen sus propias pantallas (R1.4 y R1.5) |
| VI | Por API `console.*`, nunca navegando la consola | ☑ | La app usa la API. La ventana del sistema solo se usa para entrar, que es lo que pide RFC 8252 |
| VII | Test primero; el criterio de aceptación es el test; nada de `skip` | ☑ | Cada tarea empieza con su prueba en rojo. Los seis barridos no se saltan. Lo que solo se ve en dispositivo (el aviso real y la pantalla bloqueada) tiene un flujo de Maestro o una lista manual con su evidencia |
| VIII | Licencias leídas enteras | ☑ | La tabla está en research. Se descartaron dos plugins por llevar una «MIT modificada». EAS es un servicio, con sus términos leídos |
| IX | La KB es dueña del porqué; la spec enlaza a su nota | ☑ | `[[research/2026-10-19-consola-lite-movil]]`, que ya enlaza a esta spec en su frontmatter. Falta escribir el **ADR-042** («La Consola Lite en el teléfono»), que sustituye a `architecture/mobile-app.md`: es la primera tarea |

### Las tres puertas que `/speckit-tasks` comprueba

| Puerta | Respuesta | Tarea que la cubre |
|---|---|---|
| **Aislamiento** | Garantía **1** (RLS en `client_phones`, `client_push_events` y `client_push_deliveries`) y tres ejes nuevos: teléfono de un cliente ↔ avisos de otro; teléfono, persona o acceso revocado ↔ lecturas y avisos posteriores; lo que viaja a Apple y Google ↔ el mínimo de R9.2. Además, el teléfono ↔ las rutas de partner y admin, y la lista de teléfonos ↔ otra persona | Seis barridos (R15.1–R15.6), uno por eje, más `test_21` y `test_22` sobre las tablas nuevas |
| **Licencias** | Ver [research.md §Licencias](research.md#licencias-de-lo-que-entra-constitución-viii). Todo es MIT, Apache-2.0 o BSD, más EAS como servicio | Una tarea de instalación por workspace, con el párrafo citado |
| **Medidor** | Nada nuevo que gaste. Los mensajes enviados desde el teléfono pasan por el mismo `send_message` y se miden como saliente del cliente (R6.8). Enviar a APNs y FCM no tiene coste por aviso. EAS y las cuentas de las tiendas son coste de Auphere, no del partner | La prueba de R6.8 en la iteración 2 |

## Decisiones

Están todas en [research.md](research.md), con su porqué y sus alternativas. En
corto:

| # | Decisión |
|---|---|
| D1 | La API comprueba la sesión del teléfono: una rama de `require_client_principal` que acaba en el mismo `ClientPrincipal` |
| D2 | ~~Se entra por `/app-auth` en la consola~~ → **D2b**: entrada propia de la app. Contraseña en `POST /app/sign-in/password`; Google por `GET /app/sign-in/google` (API) y canje en `POST /app/sign-in/google`, con `session_codes` `purpose=client_phone` y PKCE S256 en base64url |
| D3 | La fila del teléfono se lee como identidad, igual que la membresía; la credencial no lleva tenant |
| D4 | Dos credenciales: acceso de 1 h y renovación rotativa que caduca tras 90 días sin uso |
| D5 | Avisos normales: el aviso viaja completo con el texto mínimo y el sistema lo muestra tal cual (owner) |
| D6 | Outbox `client_push_events` en la transacción del hecho, más la tarea `push-dispatcher` del worker |
| D7 | Lo que se ve con el teléfono bloqueado lo decide el ajuste del teléfono. El aviso va marcado como privado y la app explica el ajuste (R8.10) |
| D8 | APNs y FCM v1 con `httpx[http2]` y PyJWT |
| D9 | `Idempotency-Key` sobre `messages.idempotency_key`, sin el 500 de la carrera |
| D10 | `/me.nav`, una sola fuente del orden de los módulos |
| D11 | Pestañas nativas declaradas, montadas tras leer `nav` y ocultas si faltan |
| D12 | Expo SDK 58, con 57.0.30 de respaldo |
| D13 | `apps/mobile` en su propio workspace de pnpm; lo compartido entra generado |
| D14 | Tipos con openapi-typescript desde el OpenAPI de la API, comprobados en CI |
| D15 | Tokens OKLCH convertidos a hex sRGB con culori, comprobados en CI |
| D16 | El patrón `t()` de la consola, con el vocabulario lite generado desde `messages.ts` |
| D17 | SSE propia sobre `expo/fetch` y `eventsource-parser`, solo en primer plano |
| D18 | Versión mínima por configuración, servida en `/app/config` |
| D19 | `expo-updates` incluido, pero solo para arreglos |
| D20 | Sin servicio de errores de terceros en la v1 |
| D21 | Team de FACELAD, una API key nueva de App Store Connect, y las claves de APNs y FCM en Secrets Manager |
| D22 | Cómo se prueba cada capa |
| D23 | Spike S1 antes de construir |
| D24 | Experiencia y movimiento: nativo primero y una sola coreografía («Tomar el control»), con envío optimista, entradas suaves, esqueletos, vibraciones con significado y movimiento reducido |

## Contratos

- [contracts/phone-auth.md](contracts/phone-auth.md): entrar, renovar, salir,
  configuración pública y archivos de dominio.
- [contracts/lite-api-phone.md](contracts/lite-api-phone.md): qué cambia en
  `/console/lite/*` (autenticación, `nav`, idempotencia, tiempo real, medios),
  los teléfonos en la web y en el admin, y las revocaciones.
- [contracts/push.md](contracts/push.md): tipos, textos, puntos de enganche, el
  reparto en el worker y el payload.

## Project Structure

### Documentation (this feature)

```text
specs/031-auphere-customers-movil/
├── spec.md
├── plan.md              # este archivo
├── research.md          # Fase 0: decisiones D1–D23 y licencias
├── data-model.md        # Fase 1: migraciones 0158–0162
├── quickstart.md        # Fase 1: cómo se valida
├── contracts/
│   ├── phone-auth.md
│   ├── lite-api-phone.md
│   └── push.md
├── checklists/requirements.md
└── tasks.md             # Fase 2, lo genera /speckit-tasks
```

### Source Code (repository root)

```text
apps/api/src/nexus_api/
├── core/
│   ├── client_auth.py              # + rama de teléfono en require_client_principal
│   └── phone_credential.py         # NUEVO: emitir y verificar el acceso; renovación
├── services/
│   ├── client_phones.py            # NUEVO: canjear, renovar, revocar, listar
│   ├── push_events.py              # NUEVO: escribir en el outbox (mismo tx)
│   ├── push_texts.py               # NUEVO: título y texto mínimo, en ES y EN
│   ├── session_codes.py            # + purpose y codificación base64url
│   ├── client_access.py            # _end_sessions también revoca teléfonos
│   ├── principal_access.py         # revoke_all_access también los de cliente
│   ├── inbox_lifecycle.py          # mark_waiting → push_events
│   └── wallet_alerts.py            # emit de saldo → push_events
├── api/
│   ├── app_public.py               # NUEVO: /app/sign-in/{password,google}, /app/password-reset, /app/phones/refresh, /app/config
│   ├── console/lite/phones.py      # NUEVO: /console/lite/phones*, phone-codes y account/deletion-request
│   ├── console/lite/me.py          # + nav
│   ├── console/lite/inbox.py       # + Idempotency-Key en send
│   ├── console/lite/inbox_media.py # + Idempotency-Key en attachments
│   └── admin/client_access.py      # + teléfonos por persona
├── db/models/client_phone.py       # NUEVO: ClientDevice, ClientPushEvent, ClientPushDelivery
├── config.py                       # + customers_app_* (secreto, versión mínima, APNs y FCM)
└── alembic/versions/0158…0162_*.py

apps/api/tests/
├── unit/        # credenciales, renovación, idempotencia, nav y textos de aviso
├── integration/ # canje de punta a punta, revocaciones y outbox
└── isolation/   # los seis barridos de R15

apps/worker/src/nexus_worker/
├── bootstrap.py                    # + push-dispatcher (_spawn, EGRESS_TASK_NAMES)
├── push/dispatcher.py              # NUEVO: drenar el outbox, repartir, componer y enviar
├── push/apns.py                    # NUEVO: HTTP/2 con token ES256
├── push/fcm.py                     # NUEVO: HTTP v1 con aserción RS256
└── runtime/dispatcher.py           # + evento inbox.message_for_you en el tx del entrante
apps/worker/tests/unit/test_bootstrap_split.py   # + push-dispatcher en ALL_EXPECTED

apps/console/src/
├── (retirado por D2b) app/(auth)/app-auth — la app ya no entra por la consola
├── app/(console)/account/phones/page.tsx        # NUEVO: «Tus teléfonos»
├── components/shell/lite-nav.ts                 # pinta /me.nav (fuera ORDER)
└── lib/backend/lite.ts                          # + phones

apps/admin/src/app/(dashboard)/tenants/[id]/access/
└── members-list.tsx (+ phones-list.tsx)         # teléfonos por persona

apps/mobile/                         # NUEVO, con su pnpm-workspace.yaml y su lockfile
├── app.config.ts                    # com.auphere.customers, esquema auphere-customers,
│                                    # entitlement time-sensitive
├── src/app/                         # rutas de expo-router
│   ├── _layout.tsx                  # arranque: /app/config, sesión, guardas (Stack.Protected)
│   ├── index.tsx                    # aterrizaje: el primer módulo de /me.nav
│   ├── sign-in.tsx · not-a-client.tsx · no-access.tsx · update-required.tsx
│   ├── notices-permission.tsx · ajustes.tsx · +native-intent.tsx
│   ├── (app)/_layout.tsx            # NativeTabs desde /me.nav (D11)
│   ├── (app)/inicio/ · consumo/     # una pila nativa por pestaña (_layout + index)
│   ├── (app)/bandeja/               # la lista (index)
│   └── conversacion/[id]/           # index · contacto (hoja), por encima de las pestañas
├── src/api/                         # cliente openapi-fetch + schema.gen.ts + sse.ts
├── src/auth/                        # entrada (contraseña, Google con PKCE), almacén seguro, renovación de una en una
├── src/push/                        # permiso, canales, categorías, registro y toques
├── src/motion/                      # D24: transición de «Tomar el control», entradas, vibraciones
├── src/theme/tokens.gen.ts          # D15
├── src/i18n/{lite.gen.ts,app.es.ts,app.en.ts}   # D16
├── scripts/{gen-schema,gen-tokens,gen-i18n}.ts
├── __tests__/                       # jest-expo + RNTL
└── e2e/*.yaml                       # flujos de Maestro

scripts/verify.sh                    # + paso «mobile»: tsc, eslint, jest y los tres gen --check
```

**Structure Decision.** La app vive en `apps/mobile`, con su propio workspace.
La API gana dos módulos de rutas: `app_public` (fuera de `/console`, porque el
barrido de `test_console_scope` exige un 401 sin token en todo `/console`) y
`console/lite/phones`. El worker gana una tarea de la familia egress. La
consola gana tres páginas y deja de duplicar el orden de los módulos. El admin
gana una lista dentro de «Acceso».

## Complexity Tracking

| Lo que se añade | Por qué hace falta | Alternativa más simple descartada |
|---|---|---|
| Un prefijo nuevo `/app/*`, público | Canjear y renovar no pueden llevar el JWT de la BFF. `test_console_scope` exige un 401 sin token en todo `/console` | Meterlo en `/console` con una lista de excepciones. Debilita un barrido que hoy no tiene ninguna |
| Dos credenciales en vez de una | No forzar a entrar cada 12 h (R2.1) | Un token único de 12 h, como el escritorio. Incumple R2.1 |
| Un workspace de pnpm más | Hay dos versiones de React incompatibles (D13) | El workspace raíz. Duplica React o fuerza a subir la consola |
| Tres generadores con comprobación en CI | Los tipos, los tokens y el vocabulario no pueden escribirse dos veces | Copiarlos a mano. Divergen, como ya divergieron `lite-api.md` y el código |

## Riesgos y dependencias externas

- **Cuentas.** Hace falta Daniel (Account Holder de FACELAD) o un Admin con
  acceso a «Certificates, Identifiers & Profiles» para el App ID con sus
  capacidades (avisos, Associated Domains y Time Sensitive), el certificado de
  distribución y la clave de APNs. **Bloquea S1 en dispositivo y el piloto, no
  el código.**
- **Firebase.** Hace falta un proyecto de Auphere con su cuenta de servicio
  para FCM.
- **Revisión de las tiendas.** Hace falta un cliente de demostración en
  producción, bajo Auphere Internal Partner, cuya Bandeja no envíe WhatsApp
  reales.
- **Hallazgo lateral.** Puede que el PKCE del escritorio no cuadre (hex frente a
  base64url). Va por el flujo de bugs, aparte, y no bloquea esta spec.
- **Migrar de FACELAD a Auphere.** Cambia el prefijo del llavero, el Team ID del
  AASA y la clave de APNs: todas las personas vuelven a entrar una vez. Está
  aceptado en los supuestos de la spec.
- **Privacidad de los avisos.** Apple y Google ven el nombre del contacto y un
  texto corto. Lo aceptó el owner al pedir avisos normales. La política de
  privacidad y las etiquetas de las tiendas tienen que decirlo.
