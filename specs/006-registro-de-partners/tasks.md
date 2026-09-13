---
description: "Tareas de implementación — el registro de partners"
---

# Tareas: el registro de partners

**Entrada**: [spec.md](spec.md) · [plan.md](plan.md) · [research.md](research.md) ·
[data-model.md](data-model.md) · [contracts/signup.md](contracts/signup.md) ·
[quickstart.md](quickstart.md)

**Tests**: **no son opcionales.** Constitución §VII: cada criterio de aceptación
nace como test, se ve en rojo, y sólo entonces se implementa.

**Y una regla más de esta casa**: cada guarda se verifica **por mutación** — se
rompe a propósito lo que vigila y se comprueba que el test cae. Un test que pasa
no prueba que vigile. Las tareas que añaden una guarda lo dicen explícitamente.

**Organización**: por historia de usuario, para que cada una se pueda implementar
y probar sola.

---

## Phase 1: Setup

- [ ] T001 Crear la migración `apps/api/alembic/versions/0118_signup_and_identities.py` con `public.signup_requests` y `console_auth.principal_identities`, sus `CHECK` de `status`/`provider` y los cuatro índices de [data-model.md](data-model.md). `down_revision = "0117_billing_events"`. _Requisitos: 1.1, 5.3_
- [ ] T002 [P] Declarar el modelo `SignupRequest` en `apps/api/src/nexus_api/db/models/signup.py`: `email varchar(255)` en minúsculas, `token_hash char(64)`, `status` en `('pending','consumed','expired','revoked')`, `expires_at` a **24 h**, `provider varchar(20)` nullable, `created_ip_hash char(64)` nullable. Exportarlo en `db/models/__init__.py`. _Requisitos: 1.1, 1.3, 1.5_
- [ ] T003 [P] Añadir `PrincipalIdentity` a `apps/api/src/nexus_api/db/models/console_identity.py`: `principal_id` FK con `ON DELETE CASCADE`, `provider varchar(20)`, `subject varchar(255)`, `email_at_link varchar(255)`, único en `(provider, subject)`. _Requisitos: 5.2, 5.3_
- [ ] T004 Añadir a `apps/api/src/nexus_api/config.py` los ajustes nuevos: `signup_enabled` (bandera, defecto `False`), `signup_token_ttl_hours` (24), `google_client_id`, `google_client_secret`, `google_redirect_uri`. Los dos últimos **sin defecto utilizable**, y rechazados por el validador de arranque si llevan `change-me`, igual que `composio_webhook_secret`. _Requisitos: 1.7, 5.1_

**Checkpoint**: la base sabe guardar una solicitud y un vínculo de proveedor. Nada del producto ha cambiado todavía.

---

## Phase 2: Foundational — bloquea TODAS las historias

**Por qué esta fase existe y va primero.** El Requisito 7 pide limitar por IP, y
hoy eso **no se puede cumplir**: nada reenvía la IP del cliente, así que detrás
del BFF la API ve la misma IP para todo el mundo (research R3). Construir el
formulario de alta encima de un limitador que no limita sería entregar la
contención en falso.

- [ ] T005 **[TEST, en rojo]** Escribir `apps/api/tests/unit/test_client_ip.py`: con `X-Nexus-Client-IP` presente se usa esa IP; ausente, se devuelve el marcador de cubo único y **no** `request.client.host`; con un valor que no es IP, se trata como ausente. _Requisitos: 7.1_
- [ ] T006 Implementar `apps/api/src/nexus_api/core/client_ip.py` con una única función de lectura. **No se lee `X-Forwarded-For`**: lo puede poner cualquiera que alcance la API, y obliga a adivinar cuántos proxies hay delante. _Requisitos: 7.1_
- [ ] T007 Hacer que el BFF ponga la cabecera en `apps/console/src/lib/` (donde se acuña el token de servicio), en **todas** las llamadas pre-sesión. _Requisitos: 7.1_
- [ ] T008 Cambiar `check_login_rate_limit` en `apps/api/src/nexus_api/api/console/auth.py` para que la IP salga de `core/client_ip`. **Esto cambia el comportamiento del login en producción**: empieza a limitar por IP de verdad, que es lo que su docstring ya prometía. _Requisitos: 7.1_
- [ ] T009 **[VERIFICACIÓN POR MUTACIÓN]** Romper `client_ip` para que devuelva siempre una constante y comprobar que T005 se pone rojo. Dejar la evidencia en la tarea. _Requisitos: 7.1_
- [ ] T010 Desplegar la Fase 2 sola a staging y observar los límites del login antes de seguir. Producción tiene 3 clientes con tráfico: un limitador que de golpe empieza a contar de verdad se mira antes de apilarle un formulario público encima. _Requisitos: 7.1_

**Checkpoint**: el limitador limita lo que dice limitar. Sin esto, el Requisito 7 no se puede cerrar.

---

## Phase 3 — Historia 1: se registra y acaba dentro de su consola (P1)

**Objetivo**: de la pantalla de entrada a owner de un partner nuevo, sin que nadie ejecute nada.

**Prueba independiente**: recorrido completo en staging con un correo nuevo, **sin credencial de operador en ninguna parte del camino**, terminando con la consola abierta y el partner en Free.

### Tests primero

- [ ] T011 [P] [US1] **[TEST, en rojo]** `apps/api/tests/unit/test_signup_service.py`: el alta crea partner + invitación + membresía `owner` en **una** transacción; si `accept()` lanza, no queda ni partner ni membresía ni solicitud consumida. _Requisitos: 3.1, 3.2_
- [ ] T012 [P] [US1] **[TEST, en rojo]** `apps/api/tests/integration/test_signup_flow.py`: los tres actos del contrato contra Postgres. Incluye que el partner nace **sin fila** en `partner_subscriptions` y con `console_enabled = true`. _Requisitos: 2.3, 3.3, 3.4_
- [ ] T013 [P] [US1] **[TEST, en rojo]** Indistinguibilidad: `POST /console/signup` con correo existente y con correo nuevo devuelven el **mismo código y el mismo cuerpo byte a byte**, y los `404` de token muerto (inexistente, caducado, usado, revocado) son los cuatro idénticos. _Requisitos: 1.2, 7.3_
- [ ] T014 [P] [US1] **[TEST, en rojo]** `apps/api/tests/isolation/test_signup_scope.py`: ninguna ruta nueva acepta `partner_id` ni `tenant_id`; un alta no puede colgar una membresía de un partner existente; ningún objeto nuevo lleva `tenant_id`. **Bloquea el merge.** _Requisitos: §I constitución_
- [ ] T015 [P] [US1] **[TEST, en rojo]** El rastro de auditoría nombra a la persona y la vía de entrada, y **no** contiene contraseña, token en claro ni IP en claro. _Requisitos: 3.5, 7.4_

### Implementación

- [ ] T016 [US1] `apps/api/src/nexus_api/repositories/signup.py`: crear solicitud (token aleatorio, guardar sólo SHA-256), buscar por hash, consumir, caducar. El claro se devuelve una vez y nunca se registra. _Requisitos: 1.1, 1.3_
- [ ] T017 [US1] `apps/api/src/nexus_api/services/signup.py` — el nacimiento del partner. **No escribe `partner_memberships`**: crea el partner, emite la invitación de `owner` y llama a `PartnerInvitationRepository.accept()`, que sigue siendo el único camino a esa tabla. _Requisitos: 3.1, 3.2, 3.3_
- [ ] T018 [US1] Generar el `slug` del partner desde el nombre de empresa, con desambiguación. Dos agencias pueden llamarse igual; lo que no puede repetirse es la referencia técnica. _Requisitos: caso límite «el nombre de empresa ya existe»_
- [ ] T019 [US1] `apps/api/src/nexus_api/api/console/signup.py` con los tres endpoints de [contracts/signup.md](contracts/signup.md), **detrás de `require_console_service`** — si fueran anónimos, `test_console_scope.py` (regla 5: 401 sin token en toda ruta) se pondría en rojo. _Requisitos: 1.1, 1.2, 2.1, 3.1_
- [ ] T020 [US1] `apps/api/src/nexus_api/api/console/schemas_signup.py`. Ningún campo de respuesta permite enumerar correos. _Requisitos: 1.2_
- [ ] T021 [US1] Los dos correos en `apps/api/src/nexus_api/services/email.py`: el del enlace y el de «ya tienes cuenta». Misma respuesta HTTP, correo distinto. _Requisitos: 1.1, 1.2_
- [ ] T022 [US1] Límites de ritmo del alta sobre `core/rate_limit`, por correo y por IP (ésta ya real, Fase 2), más el tope de correos al mismo destinatario. _Requisitos: 7.1, 7.2_
- [ ] T023 [US1] **[TEST, en rojo]** Al superar el límite, la respuesta lleva el mismo código y `Retry-After` que el login **y no sale ningún correo**: cero mensajes nuevos en Mailhog después del 429. Es la mitad que contiene el abuso — un limitador que responde 429 *después* de haber mandado el correo pasaría cualquier test que sólo mire el código de estado. _Requisitos: 1.4_
- [ ] T024 [US1] Bandera `signup_enabled`: apagada, la consola **no enseña botón gris ni página explicativa** — enseña el login. La ausencia se diseña. _Requisitos: 1.7_
- [ ] T025 [US1] **[TEST, en rojo]** El registro es abierto **de verdad**: un alta se completa sin que intervenga nadie, el partner queda `active`, y no existe cola, estado ni columna de «pendiente de aprobación»; tampoco se exige revisión humana, dominio corporativo ni datos fiscales. Es un requisito **negativo**, y por eso hay que probarlo: añadir una puerta más adelante no rompería ningún otro test de esta spec. _Requisitos: 1.6, 2.4_
- [ ] T026 [P] [US1] `apps/console/src/app/(auth)/signup/` — formulario y pantalla de «revisa tu correo», con los 5 estados. _Requisitos: 1.1_
- [ ] T027 [P] [US1] `apps/console/src/app/(auth)/signup/[token]/` — nombre de empresa y contraseña, y **retomar donde se dejó** quien verificó y no llegó a nombrar la empresa. _Requisitos: 3.6_
- [ ] T028 [P] [US1] `apps/console/src/app/api/signup/` — el BFF: acuña el token de servicio y reenvía `X-Nexus-Client-IP`. _Requisitos: 1.1, 7.1_
- [ ] T029 [US1] **[VERIFICACIÓN POR MUTACIÓN]** Romper la atomicidad (quitar el `async with session.begin()`) y comprobar que T011 cae; hacer que la respuesta de correo existente difiera y comprobar que T013 cae. _Requisitos: 3.2, 1.2_

**Checkpoint**: alguien que nunca habló con el equipo está dentro de su consola. **Es el MVP.**

---

## Phase 4 — Historia 2: contratar un nivel desde dentro (P1)

**Objetivo**: que la pantalla de planes de la spec 005 sea alcanzable desde un alta autónoma.

**Prueba independiente**: un partner creado por la Historia 1 contrata Pro y la suscripción queda activa en el proveedor y en el libro, sin haber dado de alta ni un cliente.

- [ ] T030 [US2] **[TEST, en rojo]** Un owner recién registrado llega a la pantalla de planes sin ningún paso que exija operador, y tras confirmarse el pago queda en `current` con la persona nombrada en la auditoría. _Requisitos: 4.1, 4.2_
- [ ] T031 [US2] **[TEST, en rojo]** Un partner en Free **puede** crear clientes finales, y un turno de ese cliente **no pasa** sin saldo comprado ni plan — la puerta es el medidor de la spec 005, no un tope nuevo. _Requisitos: 4.3, Historia 2 esc. 3_
- [ ] T032 [US2] Enlazar la consola del partner nuevo con la pantalla de planes existente. **No se construye checkout**: ya existe. _Requisitos: 4.1_
- [ ] T033 [US2] Revisar que ningún punto del alta cobre nada: alta y contratación son dos actos, y el segundo es del owner. _Requisitos: 4.4_
- [ ] T034 [US2] Donde un tope de Free se alcance, la consola enseña lo que sí se puede hacer y el camino a contratar — **sin botón apagado ni pantalla que explique lo que no tienes**. _Requisitos: 4.3, §V constitución_

**Checkpoint**: el hueco se convierte en ingreso posible.

---

## Phase 5 — Historia 3: entrar con Google (P2)

**Objetivo**: registrarse y entrar con Google, elegido para que sirva a las integraciones que vienen.

**Prueba independiente**: alta completa con Google sin escribir una contraseña, y segundo inicio de sesión que aterriza en la **misma** cuenta.

### Tests primero

- [ ] T035 [P] [US3] **[TEST, en rojo]** `apps/api/tests/unit/test_oauth_state.py`: el `state` es tamper-evident, tiene nonce, caduca, y **un `state` vale una sola vez**. _Requisitos: 5.4_
- [ ] T036 [P] [US3] **[TEST, en rojo]** `apps/api/tests/unit/test_google_oidc.py`: **`email_verified: false` → 403 y cero filas nuevas**; `iss`/`aud`/`exp` verificados; firma que no valida contra el JWKS → rechazo. _Requisitos: 2.2, 5.1, 5.3_
- [ ] T037 [P] [US3] **[TEST, en rojo]** Vinculación: correo verificado que ya tiene cuenta se vincula a **esa** cuenta; no se crea una segunda cuenta ni una segunda membresía. Y el ancla es `(provider, subject)`: cambiar el correo del proveedor conservando el `sub` sigue resolviendo a la misma cuenta. _Requisitos: 5.2, 5.3_

### Implementación

- [ ] T038 [US3] Extraer `apps/api/src/nexus_api/services/oauth_state.py` del patrón de `services/tiktok_oauth_state.py` y hacer que **los dos** lo usen. Tres copias de una firma divergen, y la que se queda sin la corrección es la que menos se toca. _Requisitos: 5.4_
- [ ] T039 [US3] `apps/api/src/nexus_api/services/google_oidc.py`: URL de autorización con PKCE, intercambio del código, verificación del `id_token` con `PyJWKClient`. **Ninguna dependencia nueva** — `pyjwt` y `httpx` ya están. _Requisitos: 5.1_
- [ ] T040 [US3] El `code_verifier` en Redis bajo el nonce, TTL 10 min, consumido una vez. **No viaja al navegador.** _Requisitos: 5.4_
- [ ] T041 [US3] `apps/api/src/nexus_api/api/console/auth_google.py` con `start` y `callback` según el contrato. La sesión que sale es **la misma clase** que la del login con contraseña. _Requisitos: 5.1, 5.5_
- [ ] T042 [US3] **No se guarda ningún token del proveedor.** Dejarlo escrito en el módulo con la razón: sería una credencial almacenada sin lector, la misma figura que `NEXUS_WEBHOOK_HMAC_SECRET`. _Requisitos: 5.7_
- [ ] T043 [P] [US3] Botón «Continuar con Google» en el login y en el alta. Si el proveedor no responde, **contraseña sigue funcionando** y la página no se cuelga. _Requisitos: 5.6_
- [ ] T044 [US3] **[VERIFICACIÓN POR MUTACIÓN]** Quitar la comprobación de `email_verified` y comprobar que T036 cae; aceptar un `state` reutilizado y comprobar que T035 cae. _Requisitos: 5.1, 5.4_

**Checkpoint**: dos puertas a la misma cuenta, y la segunda no se puede forzar.

---

## Phase 6 — Historia 4: lo que ve el operador (P2)

- [ ] T045 [US4] **[TEST, en rojo]** Un partner creado por esta vía aparece en el panel con fecha, vía de entrada y nivel; un registro a medias se distingue de un partner activo. _Requisitos: 8.1, 8.2_
- [ ] T046 [US4] Vista en `apps/admin` con los partners recién nacidos y las solicitudes pendientes. _Requisitos: 8.1_
- [ ] T047 [US4] Reenviar enlace de verificación y suspender partner **sin ejecutar ningún script dentro de la VPC**. _Requisitos: 2.5, 8.2_
- [ ] T048 [US4] Comprobar que el alta por invitación existente sigue funcionando intacta: un partner atendido por el equipo no tiene por qué pasar por el formulario. _Requisitos: 8.3_

---

## Phase 7 — El registro que no llega a ninguna parte

- [ ] T049 **[TEST, en rojo]** Una solicitud caducada no deja partner ni cuenta; el mismo correo puede volver a intentarlo; un token usado dos veces se comporta como uno inválido. _Requisitos: 6.1, casos límite_
- [ ] T050 Cron de caducidad de `signup_requests`. **Declararlo en `bootstrap.py` Y en su contrato de nombres** — esto ha roto la tubería dos veces, las dos por lo mismo. _Requisitos: 1.5, 6.1_
- [ ] T051 Archivado por inactividad: 180 días sin sesión de ningún miembro y sin ningún cliente final, con aviso por correo antes. **Nunca por no pagar.** _Requisitos: 6.3, 6.4_
- [ ] T052 Desarchivar conservando lo suyo cuando el owner vuelve, sin pedirle que se registre de nuevo. **Borrar no existe.** _Requisitos: 6.2, 6.5_

---

## Phase 8 — Cierre

- [ ] T053 Ejecutar [quickstart.md](quickstart.md) entero, incluida la comparación de **tiempos** de respuesta entre correo existente y nuevo — un canal lateral temporal deja el `CE-004` abierto aunque el cuerpo sea idéntico. _Requisitos: CE-001 … CE-006_
- [ ] T054 Verificar entregabilidad real del correo a los tres dominios más frecuentes del ICP. Si cae en spam, es un hallazgo con su corrección, no una suposición que se arrastra. _Requisitos: 1.1, research R8_
- [ ] T055 Actualizar la **spec viva**: `docs/partner-integration.md` y lo que describa el alta, **en el mismo commit** que cambia el comportamiento. Un PR que cambia comportamiento documentado y no toca su documento se devuelve. _Requisitos: §3 de docs/spec-driven-development.md_
- [ ] T056 `./scripts/verify.sh` completo. No la mitad: lo que se olvida en este repo es el worker, `mypy --strict`, el paquete compartido y el `next build`. _Requisitos: puerta 8_

---

## Dependencias

- **Phase 1** → **Phase 2**. La Fase 2 bloquea todo lo demás: sin IP real, el Requisito 7 no se puede cerrar y la Historia 1 entregaría la contención en falso.
- **US1** no depende de ninguna historia. Es el MVP.
- **US2** depende de US1 (hace falta un partner que contrate).
- **US3** es independiente de US2 y **no bloquea a US1**: el alta con contraseña tiene que funcionar sin Google (CE-006).
- **US4** es independiente; gana valor con volumen.
- **Phase 7** puede ir en paralelo a US2–US4; el cron de T050 no depende de nada de ellas.

## Paralelismo

- Fase 1: T002 y T003 en paralelo tras T001.
- US1: T011–T015 (los cinco tests) en paralelo. T026, T027 y T028 en paralelo entre sí.
- US3: T035, T036 y T037 en paralelo.

## Estrategia

**MVP = Phase 1 + Phase 2 + US1.** Eso ya cierra el hueco que `pendientes` §1
describe: nadie tiene que ejecutar nada para que un partner exista.

US2 es lo que lo convierte en ingreso y va inmediatamente después. US3 y US4
son incrementos que no bloquean nada.

**La Fase 2 se despliega y se observa sola** antes de apilarle el formulario
encima: cambia el comportamiento del login en una producción con 3 clientes
reales con tráfico.
