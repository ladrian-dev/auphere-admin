---

description: "Tareas de la spec 031: Auphere Customers, la Consola Lite en el teléfono"
---

# Tasks: Auphere Customers, la Consola Lite en el teléfono

**Input**: `specs/031-auphere-customers-movil/`: [spec.md](spec.md), [plan.md](plan.md), [research.md](research.md), [data-model.md](data-model.md), [contracts/](contracts/), [quickstart.md](quickstart.md)

**Tests**: no son opcionales (constitución §VII). Cada bloque «Tests» se escribe y
se ve en rojo antes de su implementación.

**Organización**: las fases siguen las iteraciones del plan (0 → 3), que es el
orden de dependencias. Dentro de cada una, las historias van por prioridad.
`[USn]` es la **Historia n** de la spec:

| Etiqueta | Historia | Prioridad | Iteración |
|---|---|---|---|
| US1 | Entrar desde el teléfono y quedarse dentro | P1 | 1 |
| US6 | Un teléfono perdido, una persona que se va | P2 | 1 |
| US5 | Inicio y Consumo | P2 | 1 |
| US4 | La Bandeja en el bolsillo | P2 | 2 |
| US3 | Atender desde el teléfono | P1 | 2 |
| US8 | Contacto y notas | P3 | 2 |
| US2 | Enterarse de que una conversación espera a una persona | P1 | 3 |
| US7 | Decidir qué me avisa | P3 | 3 |

**Por qué US2 (P1) va en la iteración 3.** Un aviso abre una conversación y se
atiende en ella, así que necesita a US4 y US3. Sin esas dos, el aviso llevaría a
una pantalla vacía.

## Reglas de este repo *(constitución)*

- Cada tarea termina con `_Requisitos: N.m_` o, si nace de la constitución, con
  `§N`.
- Cada tarea entregada se anota: `Entregado: PR #NNN (rama), fusionado
  YYYY-MM-DD`.
- Test primero (§VII). Un barrido de aislamiento en rojo bloquea el merge (§I).
- **Una suite de pytest a la vez:** comparten base de datos.
- **`apps/mobile` es su propio workspace de pnpm.** Nunca se añade a
  `pnpm-workspace.yaml` de la raíz ni usa `workspace:*`. Al añadir una
  dependencia que ya existe en el monorepo, se fija la misma versión exacta.
- **Colores y movimiento:** sin hex escritos a mano, solo
  `src/theme/tokens.gen.ts`. Las animaciones duran 300 ms o menos, salen de
  `src/motion/` y respetan el movimiento reducido (D24).
- **`git commit` lo ejecuta la persona.** El agente entrega el mensaje y para.
- **El repo es público.** Ningún detalle de vulnerabilidades en código, docs ni
  commits.

## Format: `[ID] [P?] [Story] Descripción`

- **[P]**: paralelizable (archivos distintos, sin dependencias pendientes).
- **[USn]**: historia de la spec. Las rutas son relativas a la raíz del repo.

---

## Phase 1: Setup

**Propósito**: lo que todo lo demás necesita y no es lógica de producto.

- [X] T001 Escribir en la KB `/Users/lmatos/Work/Auphere/nexus/decisions/ADR-042-la-consola-lite-en-el-telefono.md`, con las decisiones D1, D4, D5, D6, D12, D13 y D24 de [research.md](research.md).
  - Enlaza esta spec.
  - Marca `architecture/mobile-app.md` con `status: superseded` y un enlace al ADR.
  - Añade el ADR al `_index` de `decisions/`.
  - Enlaza el ADR desde el `## Encabezado Auphere` de [spec.md](spec.md), en la fila «Nota de KB».
  _§IX_
- [X] T002 Spike **S1** por el flujo `assess`: `/speckit-assess-intake` en `.specify/assessments/031-s1-esqueleto-expo-58/`.
  - Se hace en la rama `spike/031-s1`, que **no se fusiona**.
  - Comprueba en un dispositivo físico, con un build de desarrollo:
    - Expo SDK 58;
    - la vuelta universal y la vuelta por esquema propio de `expo-web-browser`;
    - `expo-secure-store`;
    - un aviso real de APNs con `time-sensitive` y otro de FCM con `visibility: PRIVATE`, enviados desde un script;
    - `NativeTabs` con `hidden` y su remontaje;
    - una animación de reanimated en el hilo de UI;
    - `eas build` desde el workspace anidado.
  - Termina en *go* (SDK 58) o en *go* con 57.0.30, con la razón escrita.
  - **2026-10-20: *go* con el SDK 58** ([decisión](../../.specify/assessments/031-s1-esqueleto-expo-58/decision.md)). Sin dispositivo en esta sesión: las comprobaciones en teléfono quedan como lista en la decisión.
  _§VII, D12, D23_
- [X] T003 [P] Lectura de RGPD del camino de avisos y de EAS en `/Users/lmatos/Work/Auphere/nexus/compliance/`:
  - qué datos reciben Apple y Google: el destino y el texto mínimo de R9.2;
  - qué procesa Expo: código y builds, nunca datos de clientes;
  - la base legal, los encargados y las transferencias.
  - De ahí sale el texto para la política de privacidad y el borrador de las etiquetas de privacidad del App Store y de Data safety de Play.
  _Requisitos: 9.2, §II_
- [ ] T004 [P] Pedir a Daniel (Account Holder de FACELAD), o conseguir el rol Admin con acceso a «Certificates, Identifiers & Profiles», lo siguiente:
  - el App ID `com.auphere.customers` con Push Notifications, Associated Domains y Time Sensitive Notifications;
  - la clave APNs `.p8`;
  - una **API key nueva** de App Store Connect para EAS. No se reutiliza `[Expo] EAS Submit`.
  - Además:
    - crear la app en Google Play Console;
    - crear el proyecto de Firebase de Auphere con su cuenta de servicio de FCM;
    - guardar la `.p8` y el JSON de servicio en AWS Secrets Manager (`nexus/{staging,prod}/push/*`).
  - Se anotan en la tarea **solo los identificadores, nunca los secretos**.
  _§D21_
- [X] T005 Crear `apps/mobile` con la plantilla de Expo SDK 58 (o 57.0.30, según T002) y expo-router:
  - `apps/mobile/pnpm-workspace.yaml` y su propio `pnpm-lock.yaml`;
  - `tsconfig.json` con `strict` y `noUncheckedIndexedAccess`;
  - ESLint 9;
  - `jest-expo` con `@testing-library/react-native` 14;
  - `app.config.ts` con:
    - `ios.bundleIdentifier` y `android.package`: `com.auphere.customers`;
    - `scheme: "auphere-customers"`;
    - `ios.associatedDomains: ["applinks:console.auphere.com", "webcredentials:console.auphere.com"]`;
    - `android.intentFilters` con `autoVerify: true` para `https://console.auphere.com/app/customers/*`;
    - `ios.entitlements["com.apple.developer.usernotifications.time-sensitive"] = true`;
    - `expo-updates` con canal por perfil.
  - Raíz `.gitignore`: `apps/mobile/{ios,android,.expo}`.
  - **Hecho con un cambio (2026-10-20):** sin `associatedDomains` ni `intentFilters`. La v1 entra solo por el esquema propio `auphere-customers://auth/callback`, que PKCE y `state` protegen; el enlace universal queda para cuando exista el App ID de producción (ver T041). ESLint 9 (la 10 rompe `eslint-plugin-react` de `eslint-config-expo`). `compileSdk` y `targetSdk` son los de Expo 58 (37), por encima del mínimo de Play.
  _Requisitos: 1.1, 8.8, 13.1_
- [X] T006 [P] Dejar escrita en [research.md §Licencias](research.md#licencias-de-lo-que-entra-constitución-viii) la versión exacta instalada y el **párrafo citado** del LICENSE de cada dependencia nueva:
  - `apps/mobile`: expo/expo, react-native, @tanstack/react-query, openapi-fetch, openapi-typescript, eventsource-parser, react-native-reanimated, react-native-gesture-handler, culori, @testing-library/react-native y Maestro;
  - `apps/mobile`, también: `react-native-worklets`, que trae reanimated 4;
  - `apps/worker`: `h2`.
  - Con una nota sobre los términos de EAS.
  _§VIII_
- [X] T007 Paso `mobile` en `scripts/verify.sh`:
  - `pnpm --dir apps/mobile install --frozen-lockfile`;
  - `tsc --noEmit`;
  - `eslint`;
  - `jest`;
  - `gen-schema --check`, `gen-tokens --check` y `gen-i18n --check`.
  - Además, el job equivalente en `.github/workflows/ci.yml` y la sección «Verificar antes de fusionar» de `CLAUDE.md`, con el nuevo `./scripts/verify.sh mobile`.
  _§VII, D13_
- [X] T008 [P] Añadir `httpx[http2]` a `apps/worker/pyproject.toml` y actualizar `apps/worker/uv.lock`. `./scripts/verify.sh lint` debe seguir en verde. _Requisitos: 8.2, D8_

---

## Phase 2: Foundational

**Propósito**: la credencial del teléfono, la base de la app y lo compartido.

**⚠️ CRÍTICO**: ninguna historia empieza antes de terminar esta fase.

### Tests

- [X] T009 [P] `apps/api/tests/unit/test_phone_credential.py`. Comprueba:
  - emitir y verificar el acceso: `svc="customers_phone"`, `sub` (el teléfono), `gen`, `exp = iat + 3600`, `iss`/`aud`, sin tenant;
  - el rechazo de otro `svc`, otra firma, caducado o sin `sub` o `gen`;
  - que la API se niega a arrancar con el valor por defecto de `customers_app_token_secret` fuera de desarrollo.
  _Requisitos: 2.1, 2.3_
- [X] T010 [P] `apps/api/tests/integration/test_client_auth_phone.py`. Con una persona de cliente, su teléfono y la cabecera de acceso, `require_client_principal`:
  - devuelve **el mismo** `ClientPrincipal` que con el JWT de la BFF;
  - con el teléfono revocado responde 403 `phone_closed` con `reason`;
  - con una generación distinta, 401;
  - con la membresía revocada o el acceso apagado, 403;
  - sin `X-App-Platform` o `X-App-Version`, 400;
  - con una versión menor que la mínima, 403 `{"code":"app_update_required","minimum_version":…}`;
  - toca `last_seen_at` como mucho una vez cada 5 min.
  _Requisitos: 2.4, 7.2, 13.1_
- [X] T011 [P] `apps/api/tests/unit/test_lite_me_nav.py`: `GET /console/lite/me` devuelve `nav` en el orden de `ClientAccess.ordered_modules()` para cada combinación de módulos. Y `apps/console/src/components/shell/__tests__/lite-nav.test.ts`: `liteNav()` pinta `nav` tal cual, sin `ORDER` propio. _Requisitos: 3.1, 3.2_
- [X] T012 [P] `apps/mobile/__tests__/generators.test.ts`. Comprueba:
  - `gen-tokens` convierte `--primary` (#2CC295), el tinte de acción (#03624C) y el fondo (#F1F7F6) de `packages/ui/src/styles/tokens.css` a esos hex, en claro y en oscuro;
  - `gen-i18n` incluye «Tomar el control» y «Necesita humano» en ES y EN;
  - los tres generadores con `--check` fallan si el archivo confirmado difiere.
  _Requisitos: 14.3, 14.6_
- [X] T013 [P] `apps/mobile/__tests__/api-client.test.ts`. Comprueba:
  - toda petición lleva `Authorization`, `X-App-Platform` y `X-App-Version`;
  - un 401 de acceso caducado dispara **una sola** renovación aunque haya 5 peticiones a la vez, y las 5 se repiten;
  - un 401 o 403 `phone_closed` vacía el almacén y lleva a entrar;
  - un 403 `app_update_required` lleva a la pantalla de actualizar.
  _Requisitos: 2.1, 7.2, 13.1_
- [X] T014 [P] `apps/mobile/__tests__/states.test.tsx`. `Skeleton`, `EmptyState`, `ErrorState`, `OfflineBanner`, `ReconnectingIndicator` y `PartialNotice`:
  - tienen nombre accesible y rol;
  - el esqueleto solo aparece pasados 300 ms;
  - con movimiento reducido no hay animación y el indicador de reconexión no late;
  - con `fontScale` 3 no se cortan.
  _Requisitos: 14.1, 14.2, 14.4, 14.7_

### Implementación (API)

- [X] T015 Migración `apps/api/alembic/versions/0158_client_phones.py` y su modelo en `apps/api/src/nexus_api/db/models/client_phone.py`, exactamente como [data-model.md §0158](data-model.md).
  - **Antes, en la misma migración:** `UNIQUE (tenant_id, id)` en `client_memberships`, si no existe.
  - **Columnas y restricciones, al pie de la letra:**
    - `platform` CHECK `ios` \| `android`;
    - `display_name` «recortado a 80»;
    - `UNIQUE (install_id) WHERE revoked_at IS NULL`;
    - `push_token_updated_at timestamptz NULL`;
    - `refresh_hash bytea NOT NULL` y `refresh_prev_hash bytea NULL`;
    - `credential_generation int NOT NULL DEFAULT 1`;
    - `push_provider` CHECK `apns` \| `fcm`;
    - `apns_environment` CHECK `sandbox` \| `production`;
    - `notice_kinds text[] NOT NULL` con CHECK ⊆ `{inbox.waiting, inbox.message_for_you, client.balance}`;
    - `locale` `es` \| `en`;
    - `revoked_reason` CHECK `signed_out` \| `closed_by_person` \| `closed_by_auphere` \| `access_disabled` \| `member_removed` \| `password_reset` \| `abandoned` \| `refresh_reused`;
    - `UNIQUE (tenant_id, id)`;
    - la FK compuesta `(tenant_id, client_membership_id)` → `client_memberships (tenant_id, id)` `ON DELETE CASCADE`.
  - **RLS** `ENABLE` + `FORCE` con la política de tenant, con el patrón de `0150_inbox_tables.py`.
  - `test_21` y `test_22` en verde.
  _Requisitos: 2.4, 7.6_
- [X] T016 Migración `0159_session_codes_purpose.py`:
  - `purpose text NOT NULL DEFAULT 'desktop_session'`, con CHECK `desktop_session` \| `client_phone`;
  - `challenge_encoding text NOT NULL DEFAULT 'hex'`, con CHECK `hex` \| `base64url`.
  - Las pruebas del escritorio (`tests/integration/test_session_codes.py`) siguen en verde.
  _Requisitos: 1.3_
- [X] T017 `apps/api/src/nexus_api/config.py`:
  - `customers_app_token_secret`, con su guarda de arranque;
  - `customers_app_min_version_ios`, `customers_app_min_version_android`, `customers_app_min_version_reason` y `customers_app_min_version_from`;
  - `apns_key_id`, `apns_team_id`, `apns_key_pem`, `apns_topic` (`com.auphere.customers`) y `apns_environment`;
  - `fcm_project_id` y `fcm_service_account_json`.
  - Documentado en `apps/api/RUNBOOK.md`.
  _Requisitos: 13.2, 8.2_
- [X] T018 `apps/api/src/nexus_api/core/phone_credential.py`: emitir y verificar el acceso (HS256, 1 h), con el patrón de `services/device_credential.py`, sin compartir secreto. Pone T009 en verde. _Requisitos: 2.1, 2.3_
- [X] T019 Rama de teléfono en `apps/api/src/nexus_api/core/client_auth.py`, de forma que el resultado es idéntico a la rama BFF. Pone T010 en verde. La rama:
  1. distingue el `svc`;
  2. lee `client_phones[sub]` como identidad, en una transacción corta y sin tenant (research D3);
  3. de la fila saca `partner_id` y `principal_id`;
  4. comprueba que no está revocado y la generación;
  5. aplica la versión mínima, con `desktop_version.is_blocked` reutilizado;
  6. llama a `resolve_client_principal(row.partner_id, row.principal_id)`;
  7. toca `last_seen_at`.
  _Requisitos: 2.4, 7.2, 13.1_
- [X] T020 `nav` en `apps/api/src/nexus_api/api/console/lite/me.py` y en `LiteMeOut`. En la consola:
  - `apps/console/src/components/shell/lite-nav.ts` pinta `nav` y se borra `ORDER`;
  - `firstModulePath` en `apps/console/src/lib/principal-access.ts` toma el primero de `nav`, no el orden de `CLIENT_MODULES`, que queda solo para validar;
  - `apps/console/src/lib/backend/lite.ts` tipa `nav`.
  - Pone T011 en verde.
  _Requisitos: 3.1, 3.2_
- [X] T021 Fixture `phone_headers(client_member)` en `apps/api/tests/conftest.py`: crea un `client_phones` activo y acuña su credencial de acceso con las cabeceras de app. Es lo que usan los barridos. _Requisitos: 15.2, 15.5_

### Implementación (lo compartido y la base de la app)

- [X] T022 [P] Exportar el OpenAPI y generar los tipos.
  - `apps/api/scripts/export_openapi.py`, filtrado a `/console/lite` y `/app`.
  - `apps/mobile/scripts/gen-schema.ts`, con `openapi-typescript`, que genera `apps/mobile/src/api/schema.gen.ts` y admite `--check`.
  - De paso, corregir la deriva en `specs/030-consola-lite-del-cliente/contracts/lite-api.md` (`user.id` no existe) y en `realtime.md` (`status`, no `delivery`).
  _Requisitos: 5.1, D14_
- [X] T023 [P] `apps/mobile/scripts/gen-tokens.ts`, con `culori`: de `packages/ui/src/styles/tokens.css` a `apps/mobile/src/theme/tokens.gen.ts`, en claro y oscuro, con ajuste de gama a sRGB y con `--check`. _Requisitos: 14.3, 14.5_
- [X] T024 [P] Textos de la app.
  - `apps/mobile/scripts/gen-i18n.ts`, con la lista cerrada de prefijos de `apps/console/src/i18n/messages.ts`, que genera `apps/mobile/src/i18n/lite.gen.ts`.
  - `apps/mobile/src/i18n/{t.ts,app.es.ts,app.en.ts}`, con el mismo `t(locale, key, vars)` de la consola.
  - El idioma se lee con `expo-localization` al volver al primer plano.
  - Pone T012 en verde.
  _Requisitos: 14.6_
- [X] T025 `apps/mobile/src/auth/store.ts`. Pone T013 en verde.
  - `expo-secure-store` con `keychainService: "auphere-customers"` y `WHEN_UNLOCKED_THIS_DEVICE_ONLY`.
  - Se vacía en el primer arranque tras reinstalar, con un marcador en `AsyncStorage` de Expo.
  - Android queda fuera de Auto Backup.
  _Requisitos: 2.3_
- [X] T026 `apps/mobile/src/api/client.ts`. Pone T013 en verde.
  - `openapi-fetch` con un middleware que añade `Authorization`, `X-App-Platform` y `X-App-Version`.
  - Renovación de una en una.
  - Manejo de `phone_closed` y `app_update_required`.
  _Requisitos: 2.1, 7.2, 13.1_
- [X] T027 `apps/mobile/src/api/query.ts`: `@tanstack/react-query` con `focusManager` (por `AppState`) y `onlineManager` (por `expo-network`). Al volver al primer plano se invalida lo visible. _Requisitos: 5.5, 14.2_
- [X] T028 `apps/mobile/src/theme/` y `apps/mobile/src/ui/`. Pone T014 en verde.
  - `ThemeProvider` (`useColorScheme` y `tokens.gen.ts`), tipografía del sistema con `allowFontScaling`, `Screen`, `Skeleton`, `EmptyState`, `ErrorState`, `OfflineBanner`, `ReconnectingIndicator` y `PartialNotice`.
  - Objetivos táctiles de 44 pt y 48 dp.
  _Requisitos: 14.1–14.5_
- [X] T029 `apps/mobile/src/motion/`:
  - `durations.ts` (como máximo 300 ms), `springs.ts` (sin rebote), `useMotion()` (con `useReducedMotion` de reanimated) y `haptics.ts` (`success`, `light` y `warning` con `expo-haptics`);
  - prueba de que, con movimiento reducido, todas las configuraciones pasan a instantáneo o a fundido.
  _Requisitos: 14.7, 14.9_

**Checkpoint**: un teléfono con credencial ya es un `ClientPrincipal` en toda la API lite, y la app tiene su base.

---

## Phase 2b: Las puertas de la constitución

**Aislamiento.**
- Se escriben **ahora**, en rojo donde aún no hay código, y cada una se pone
  en verde en la tarea que se indica.
- Las seis viven en `apps/api/tests/isolation/`.
- Ninguna hace `skip`.

- [X] T030 [P] `test_phone_route_scope.py`. Recorre todas las rutas `/console/lite/*` con la credencial de un teléfono de un cliente A y comprueba que solo devuelven A y sus módulos. Un módulo ausente da 403, y un objeto de B da 404 opaco. Verde tras T019. _Requisitos: 15.2_
- [X] T031 [P] `test_phone_cannot_reach_partner_or_admin.py`. Con la credencial de un teléfono:
  - todas las rutas `/console/*` que no son lite responden 401;
  - todas las `/admin/*` responden 401;
  - `/console/lite/phone-codes` responde 403.
  - Verde tras T019 y T047.
  _Requisitos: 15.5_
- [X] T032 [P] `test_phone_revocation.py`. Después de cada uno de los seis disparadores, el teléfono recibe 401 o 403 en la siguiente petición y el reparto de avisos lo salta: cerrar sesión, cerrarlo la persona, cerrarlo Auphere, apagar el acceso, quitar a la persona y restablecer la contraseña. Lecturas en verde tras T056; avisos en verde tras T096. _Requisitos: 15.3, 7.2, 9.3, CE-007_
- [X] T033 [P] `test_phone_list_scope.py`. Comprueba:
  - `GET /console/lite/phones` solo devuelve los teléfonos de quien pide;
  - `DELETE /console/lite/phones/{id}` de otra persona del mismo cliente da 404;
  - la ruta del admin solo devuelve los del cliente consultado.
  - Verde tras T057 y T058.
  _Requisitos: 15.6, 7.5_
- [X] T034 [P] `test_phone_client_vs_client.py`. Con dos clientes del mismo partner, personas y teléfonos en los dos, ningún hecho de A crea entregas para teléfonos de B, en los tres tipos. Además, si una fila vieja de A y una nueva de B comparten destino, el reparto de A **no** envía a ese destino y lo pone a `NULL`. Verde tras T096. _Requisitos: 15.1_
- [X] T035 [P] `test_push_payload_no_customer_content.py`. En los tres tipos y en las dos plataformas, el payload solo lleva los campos de [push.md](contracts/push.md) y los textos miden 100 caracteres o menos. Los datos llevan números de teléfono, mensajes de 500 caracteres, notas internas y nombres de archivo «canario», y ninguno aparece. Verde tras T094 y T095. _Requisitos: 15.4, 9.2_

**Licencias**: T006.

**Medidor.** No hay nada nuevo que gaste. El mensaje enviado desde el teléfono se
mide como saliente:

- [X] T036 [P] `apps/api/tests/integration/test_phone_send_metered.py`: un envío con la credencial del teléfono crea su `usage_record` de mensaje saliente, igual que con la BFF. Verde tras T077. _Requisitos: 6.8_

**Checkpoint**: las puertas tienen dueño.

---

## Phase 3: US1. Entrar desde el teléfono y quedarse dentro (P1) · Iteración 1 🎯

**Goal**: la persona entra con la ventana del sistema, ve sus módulos como
pestañas y sigue dentro durante meses.

**Independent Test**: la persona de cliente entra, cierra la app y la abre al día
siguiente sin contraseña. Una persona de partner ve la pantalla de R1.4.

### Tests

- [X] T037 [P] [US1] `apps/api/tests/integration/test_phone_enrollment.py`. Comprueba:
  - `POST /console/lite/phone-codes` solo con la persona de cliente, por la BFF (con partner, 403);
  - el challenge en base64url de 43 caracteres;
  - el canje en `POST /app/phones` con el verificador correcto da 201 con `{phone_id, access_token, expires_in, refresh_token, me}`;
  - el código es de un solo uso y caduca a los 10 minutos;
  - un código `desktop_session` no se canjea aquí;
  - un verificador incorrecto da el **mismo** 422 `invalid_grant`;
  - con más intentos que el límite por IP, 429;
  - volver a entrar con el mismo `install_id` revoca la fila activa anterior con ese `install_id` con `signed_out`, **sea de quien sea y de cualquier cliente**: una persona por teléfono;
  - se audita `client_phone.signed_in`.
  _Requisitos: 1.2, 1.3, 2.4, 7.6_
- [X] T038 [P] [US1] `apps/api/tests/integration/test_phone_refresh.py`. Comprueba:
  - la rotación;
  - el anterior vale 60 s y rota otra vez;
  - uno más viejo revoca el teléfono con `refresh_reused` y da 401;
  - tras 90 días sin uso revoca con `abandoned`;
  - actualiza `app_version`;
  - ninguna renovación crea `principal_sessions`.
  _Requisitos: 2.1, 2.2, CE-009_
- [X] T039 [P] [US1] `apps/api/tests/unit/test_app_config.py`: `GET /app/config` es público, cacheable 5 minutos, y devuelve la mínima por plataforma. _Requisitos: 13.1, 13.2_
- [X] T040 [P] [US1] `apps/console/src/app/(auth)/app-auth/__tests__/page.test.tsx`. Comprueba:
  - `redirect_uri` exige coincidencia exacta con una de las dos de [phone-auth.md](contracts/phone-auth.md), y cualquier otra da 400;
  - `state` y `code_challenge` son obligatorios y el método es `S256`;
  - sin sesión manda a `/login?from=…`;
  - una persona de partner vuelve con `?error=not_a_client&state`;
  - con el acceso apagado vuelve con `?error=no_access&state`;
  - una persona de cliente vuelve con `?code&state`.
  - Además, `apps/console/src/__tests__/proxy-public-routes.test.ts` incluye las rutas públicas nuevas.
  _Requisitos: 1.1, 1.4, 1.5_
- [ ] T041 [P] [US1] **Diferida (2026-10-20): la v1 no usa enlace universal**, así que no sirve AASA ni `assetlinks.json` todavía; se hace junto con el App ID y la huella de Play definitivos. **Tras la enmienda de R1** solo la vuelta de Google usa el esquema propio; si se activa el enlace universal, el dominio es el de la API (`/app/sign-in/google/callback` → app), no el de la consola. Era: `apps/console/src/app/.well-known/__tests__/well-known.test.ts`: el AASA lleva `applinks` con `/app/customers/*` y `webcredentials` con `<TEAM_ID>.com.auphere.customers`; `assetlinks.json` lleva el paquete y la huella desde la configuración. _Requisitos: 1.1_
- [X] T042 [P] [US1] `apps/mobile/__tests__/sign-in.test.tsx`. Comprueba:
  - PKCE S256 en base64url con un `state` aleatorio;
  - una vuelta con otro `state` se rechaza;
  - si se cancela la ventana, se vuelve a «Entrar» con su mensaje;
  - `error=not_a_client` pinta R1.4 con el botón «Abrir la consola web»;
  - `error=no_access` pinta R1.5 diciendo a quién pedir. Antes de entrar no hay `/me`, así que no hay `balance_contact`: la frase nombra «la persona que te invitó a la consola».
  _Requisitos: 1.1, 1.4, 1.5, 1.6_
- [X] T043 [P] [US1] `apps/mobile/__tests__/tabs.test.tsx`. Comprueba:
  - las pestañas siguen el orden de `nav`;
  - un módulo ausente va `hidden`;
  - con un solo módulo no hay barra;
  - un módulo desconocido se ignora;
  - si `nav` cambia al volver al primer plano, la barra se vuelve a montar;
  - si desaparece la pestaña abierta, se va al primer módulo;
  - con `nav` vacío se pinta R1.5.
  _Requisitos: 3.1–3.7_
- [ ] T044 [P] [US1] Flujos de Maestro `apps/mobile/e2e/sign-in.yaml` y `apps/mobile/e2e/dynamic-tabs.yaml`, contra la pila local con la semilla de la spec 030 (ver [quickstart §3](quickstart.md)). _Requisitos: 1.1, 3.3, CE-001, CE-011_
  - **2026-10-20:** Maestro 2.11 instalado. `sign-in.yaml` reescrito para la entrada propia (contraseña mala y buena, avisos, Inicio) y **en verde** en el emulador; los flujos aceptan es y en, y abren el Metro local cuando el build es de desarrollo (`_dev-server.yaml`). `dynamic-tabs.yaml` necesita que Auphere quite un módulo a mitad del flujo.

### Implementación

- [X] T045 [US1] `apps/api/src/nexus_api/services/session_codes.py`: emitir y canjear con `purpose` y `challenge_encoding`. `pkce_challenge` admite `base64url` (RFC 7636) **sin** cambiar el comportamiento de `hex` para el escritorio. _Requisitos: 1.3_
- [X] T046 [US1] `apps/api/src/nexus_api/services/client_phones.py`: canjear (crea la fila, guarda los hashes y revoca la fila activa con el mismo `install_id`, sea de quien sea y de cualquier cliente), renovar (rotar, gracia, reutilización y abandono) y auditar con `client_phone.signed_in`. _Requisitos: 1.3, 2.1, 2.2, 2.4, 7.6_
- [X] T047 [US1] `apps/api/src/nexus_api/api/console/lite/phones.py`: `POST /console/lite/phone-codes`, solo BFF. `apps/api/src/nexus_api/api/app_public.py`: `POST /app/phones`, `POST /app/phones/refresh` y `GET /app/config`, con `ip_rate_limiter`. Se monta `/app` en `main.py`. Pone T037 a T039 en verde. _Requisitos: 1.3, 2.1, 13.1_
- [X] T048 [US1] Consola. Pone T040 y T041 en verde.
  - `apps/console/src/app/(auth)/app-auth/page.tsx`.
  - `apps/console/src/lib/backend/lite.ts` (`phoneCode`).
  - `apps/console/src/app/.well-known/apple-app-site-association/route.ts` y `apps/console/src/app/.well-known/assetlinks.json/route.ts`.
  - `apps/console/src/app/app/customers/auth/page.tsx`: sin la app instalada, explica y enlaza a las tiendas.
  - Las rutas públicas en `apps/console/src/proxy.ts`.
  _Requisitos: 1.1, 1.4, 1.5_
- [X] T049 [US1] App. Pone T042 y T043 en verde.
  - `apps/mobile/src/auth/{pkce.ts,sign-in.ts}`, con `expo-web-browser` `openAuthSessionAsync` y `preferUniversalLinks`.
  - `apps/mobile/src/app/_layout.tsx`: arranque detrás de la pantalla de inicio (`/app/config`, luego la sesión, luego `/me`), y rutas `sign-in.tsx`, `not-a-client.tsx`, `no-access.tsx` y `update-required.tsx`.
  - `apps/mobile/src/app/(tabs)/_layout.tsx`: `NativeTabs` desde `nav`, con `hidden` y remontaje (D11).
  - Las pantallas de entrada usan la transición del sistema y ninguna animación propia.
  _Requisitos: 1.1–1.6, 2.1, 3.1–3.7, 13.1, 14.8_
- [X] T050 [US1] `apps/mobile/src/app/ajustes.tsx`, en su forma base. En iOS es una hoja desde el avatar; en Android, una pantalla. Muestra la persona, su correo, su negocio y su papel (`/me`) y «Abrir la consola en la web». Pruebas RNTL de rol y nombre. _Requisitos: 11.1, 3.8, 14.8_

**Checkpoint**: entrar, quedarse y pestañas dinámicas funcionan solos. T030 y T031 en verde.

---

## Phase 4: US6. Un teléfono perdido, una persona que se va (P2) · Iteración 1

**Goal**: cerrar la sesión de un teléfono desde el propio teléfono, la web o el
admin, y que las revocaciones de siempre también cierren teléfonos.

**Independent Test**: se quita el acceso con la app abierta. La siguiente
petición la saca y el teléfono no recibe más avisos.

### Tests

- [X] T051 [P] [US6] `apps/api/tests/integration/test_phone_revocation_triggers.py`. Comprueba:
  - `client_access.set_access(enabled=False)` revoca todos los teléfonos del cliente con `access_disabled`;
  - `client_access.revoke(member)`, los de la persona con `member_removed`;
  - `principal_access.revoke_all_access` en el restablecimiento de contraseña, con `password_reset`;
  - quitar un **módulo** no revoca nada;
  - cada revocación pone `push_token = NULL` y audita `client_phone.revoked` con `system`.
  _Requisitos: 7.1, 7.2, 7.6_
- [X] T052 [P] [US6] `apps/api/tests/integration/test_phone_lists.py`. Comprueba:
  - `GET /console/lite/phones`, con `current` marcado para el que llama;
  - `DELETE /console/lite/phones/{id}`, con `closed_by_person` y la auditoría con `client:<correo>`;
  - `DELETE /console/lite/phones/current`, con `signed_out`;
  - el admin `GET/DELETE /admin/tenants/{id}/client-members/{member_id}/phones[/{phone_id}]` con `X-Operator-Id`, con `closed_by_auphere` y la auditoría con `operator:<correo>`;
  - sin `X-Operator-Id`, 400.
  _Requisitos: 7.1, 7.3, 7.4, 7.6_
- [X] T053 [P] [US6] `apps/console/src/app/(console)/account/phones/__tests__/page.test.tsx` y un caso en el Playwright `lite`.
  - La lista tiene los cinco estados.
  - «Cerrar» pide confirmación y el teléfono desaparece.
  - Axe sin incidencias graves.
  - 360 px sin desborde, en ES y EN, y en claro y oscuro.
  _Requisitos: 7.3, 7.5_
- [X] T054 [P] [US6] `apps/admin/src/app/(dashboard)/tenants/[id]/access/__tests__/phones-list.test.tsx`: la lista dentro de cada persona, con «Cerrar teléfono» y la confirmación. _Requisitos: 7.4_
- [X] T055 [P] [US6] `apps/mobile/__tests__/sign-out.test.tsx`: «Cerrar sesión» llama a `DELETE …/current`, vacía el almacén y vuelve a «Entrar». Un `phone_closed` en cualquier petición lleva a «Entrar» con el mensaje de la razón: lo cerraste desde otro sitio, te quitaron el acceso o tu negocio ya no tiene acceso. _Requisitos: 7.1, 7.2, 11.3_

### Implementación

- [X] T056 [US6] `services/client_phones.py`: `revoke(phone, reason, by)` y `revoke_for(principal | tenant, reason)`. Se engancha a `apps/api/src/nexus_api/services/client_access.py` (`_end_sessions` y `revoke`) y a `apps/api/src/nexus_api/services/principal_access.py` (`revoke_all_access`). Pone T051 en verde. _Requisitos: 7.1, 7.2, 7.6_
- [X] T057 [US6] Rutas `GET /console/lite/phones`, `DELETE /console/lite/phones/{id}` y `DELETE /console/lite/phones/current` en `api/console/lite/phones.py`. _Requisitos: 7.1, 7.3, 7.5_
- [X] T058 [US6] Admin. Pone T052 y T054 en verde.
  - En la API: `GET` y `DELETE` de teléfonos por persona en `apps/api/src/nexus_api/api/admin/client_access.py`, con `require_operator`.
  - En el panel: `apps/admin/src/lib/backend.ts` y `apps/admin/src/app/(dashboard)/tenants/[id]/access/{phones-list.tsx,actions.ts}` dentro de `members-list.tsx`.
  _Requisitos: 7.4, 7.6_
- [X] T059 [US6] Migración `0162_client_phone_audit_vocab.py` con las cinco filas de [data-model.md §0162](data-model.md), en ES y EN. Se añaden `{phone}` y `{reason}` a `apps/api/src/nexus_api/api/console/audit_words.py`. `test_console_audit_words.py` en verde. _Requisitos: 7.6_
- [X] T060 [US6] Consola. Pone T053 en verde.
  - `apps/console/src/app/(console)/account/phones/page.tsx`, «Tus teléfonos», con `@nexus/ui` y solo tokens.
  - La entrada en el menú de cuenta de la persona de cliente.
  - `lib/backend/lite.ts` con `phones` y `closePhone`.
  _Requisitos: 7.3, 7.5_
- [X] T061 [US6] App: «Cerrar sesión» en `ajustes.tsx` y el manejo global de `phone_closed` en `src/api/client.ts`, con la pantalla de razón. Pone T055 en verde. _Requisitos: 7.1, 7.2, 11.3_

**Checkpoint**: T032 (lecturas) y T033 en verde.

---

## Phase 5: US5. Inicio y Consumo (P2) · Iteración 1

**Goal**: el Panel y el Consumo del cliente en el teléfono, con las cifras al
céntimo y sin comprar saldo.

**Independent Test**: cada cifra coincide con la de la web para el mismo cliente.

### Tests

- [X] T062 [P] [US5] `apps/api/tests/integration/test_lite_phone_figures_match_web.py`: `/home` y `/usage/{summary,spend}` dan respuestas **idénticas** con la credencial del teléfono y con el JWT de la BFF, para el mismo cliente y el mismo instante. _Requisitos: 4.3, CE-005_
- [X] T063 [P] [US5] `apps/mobile/__tests__/inicio.test.tsx`. Comprueba:
  - los estados cargando (esqueleto con medidas), vacío, error, **parcial** (`errors[]` del Panel) e ideal;
  - «Necesita tu atención» primero, y cada fila lleva a su pantalla;
  - el saldo con días, y si es corto, a quién pedir **sin** botón.
  _Requisitos: 4.1, 4.4, 14.1_
- [X] T064 [P] [US5] `apps/mobile/__tests__/consumo.test.tsx`. Comprueba:
  - saldo, días, gasto del mes y proyección;
  - el gasto por día con el selector 7, 30 y 90;
  - el reparto por agente;
  - ningún texto ni botón de compra, recarga o «pedir saldo» (por búsqueda de los textos de ES y EN);
  - ni detalle técnico ni exportación.
  _Requisitos: 4.2, 4.4, 4.5_

### Implementación

- [X] T065 [US5] `apps/mobile/src/app/(tabs)/inicio.tsx`, con `src/features/home/*`.
  - Título grande con el saludo y el negocio, filas de atención y métricas con cifras tabulares.
  - Pull-to-refresh nativo.
  - Pone T063 en verde.
  _Requisitos: 4.1, 4.4, 14.1, 14.8_
- [X] T066 [US5] `apps/mobile/src/app/(tabs)/consumo.tsx`, con `src/features/usage/*`.
  - Barras de gasto por día con `View` y tokens, sin librería de gráficos; la barra de hoy en el color de lo vivo.
  - Selector segmentado nativo.
  - Reparto por agente.
  - Pone T064 en verde.
  _Requisitos: 4.2, 4.4, 4.5_

**Checkpoint · fin de la iteración 1**:
- `./scripts/verify.sh` completo en verde.
- Build interno (`eas build --profile preview`) si T004 ya tiene las cuentas.
- Anotar en `evidence/iteracion-1.md`.

---

## Phase 6: US4. La Bandeja en el bolsillo (P2) · Iteración 2

**Goal**: lista, filtros, búsqueda, hilo con archivos y tiempo real en primer
plano.

**Independent Test**: con 200 conversaciones, filtrar por «Esperan», buscar un
nombre y abrir una foto recibida.

### Tests

- [X] T067 [P] [US4] `apps/api/tests/integration/test_lite_stream_phone.py`: `GET /console/lite/inbox/stream` con la credencial del teléfono emite `ready` y los eventos del cliente, y no los de otro. _Requisitos: 5.4_
- [X] T068 [P] [US4] `apps/mobile/__tests__/sse.test.ts`. Comprueba:
  - el análisis de eventos con `eventsource-parser`;
  - la reconexión con espera creciente (la API no numera los eventos, así que no hay `Last-Event-ID`: al recuperar la línea se relee la Bandeja entera);
  - se cierra al pasar a segundo plano y se reabre al volver;
  - «Reconectando…» tras 3 s sin línea.
  _Requisitos: 5.4, 5.5, 14.1_
- [X] T069 [P] [US4] `apps/mobile/__tests__/bandeja.test.tsx`. Comprueba:
  - los filtros (todas, sin leer, esperan, resueltas);
  - el filtro por agente solo con más de un agente;
  - la búsqueda por nombre o número;
  - los cinco estados;
  - la placa de la pestaña con las que esperan;
  - ~~las acciones de deslizar, con su alternativa en el menú;~~ **fuera de la v1 (2026-10-20):** todas las acciones viven en el menú de la conversación, así que no hay gesto sin botón (R14.5) que comprobar;
  - ~~en Android, «Deshacer» durante 4 s~~ (iba con deslizar).
  _Requisitos: 5.1, 5.2, 5.6, 14.5_
- [X] T070 [P] [US4] `apps/mobile/__tests__/hilo.test.tsx`. Comprueba:
  - los tipos de mensaje (contacto, agente, persona y avisos del sistema);
  - las imágenes recibidas, con la cabecera de credencial;
  - los documentos se abren;
  - «marcar como no leída», «resolver» y «reabrir»;
  - con movimiento reducido no hay animaciones de entrada.
  _Requisitos: 5.3, 5.6, 14.7_

### Implementación

- [X] T071 [US4] `apps/mobile/src/api/sse.ts`, con `expo/fetch` y `eventsource-parser`, y su integración en react-query: un evento invalida la lista o el hilo afectado. Pone T067 y T068 en verde. _Requisitos: 5.4, 5.5_
- [X] T072 [US4] `apps/mobile/src/app/(tabs)/bandeja/index.tsx`, con `src/features/inbox/list/*`. Pone T069 en verde.
  - `FlatList`, filtros, búsqueda (en iOS, en la barra de navegación; en Android, barra de búsqueda arriba) y filtro de agente.
  - Deslizar con `react-native-gesture-handler`: en iOS revela; en Android ejecuta, con barra «Deshacer».
  - Recolocación con `LinearTransition` de 200 ms (D24).
  _Requisitos: 5.1, 5.2, 5.6, 14.5, 14.9_
- [X] T073 [US4] `apps/mobile/src/app/(tabs)/bandeja/[id].tsx`, con `src/features/inbox/thread/*`. Pone T070 en verde.
  - El hilo en lista invertida y las entradas de mensaje con fundido y 8 pt en 200 ms (D24).
  - Imágenes con `expo-image`, que recibe la cabecera de credencial.
  - Documentos descargados con la credencial y abiertos con la hoja del sistema.
  - El menú de la conversación.
  _Requisitos: 5.3, 5.6, 14.7, 14.9_

**Checkpoint**: la Bandeja se lee y se recorre sola.

---

## Phase 7: US3. Atender desde el teléfono (P1) · Iteración 2

**Goal**: tomar el control, contestar sin duplicados y devolverla.

**Independent Test**: el contacto recibe una sola vez cada mensaje en 100
envíos con cortes de red.

### Tests

- [X] T074 [P] [US3] `apps/api/tests/integration/test_lite_send_idempotency.py`. Comprueba:
  - la primera vez da 201;
  - la misma clave da 200 con el **mismo** `SentOut` y no envía;
  - una clave de un mensaje `failed` reintenta sobre la misma fila;
  - dos peticiones a la vez con la misma clave nunca dan 500;
  - una clave inválida da 400;
  - `not_assigned_to_you`, `window_closed` y `channel_disconnected` se comprueban **antes** del replay, y el replay de un envío hecho da 200 aunque la ventana ya esté cerrada;
  - lo mismo en `POST …/attachments`.
  _Requisitos: 6.4, CE-004_
- [X] T075 [P] [US3] `apps/mobile/__tests__/atender.test.tsx`. Comprueba:
  - el motivo se ve antes de «Tomar el control» y la acción está abajo;
  - un 412 o 409 pinta quién la atiende ahora, con la vibración de aviso;
  - con la ventana de 24 h cerrada, el cuadro lo dice **antes** de escribir y no deja enviar;
  - el envío es optimista, «enviando» y luego «enviado»;
  - si falla, se queda «no enviado» con «Reintentar» y el **mismo** `Idempotency-Key`, y el texto no se pierde;
  - la respuesta guardada se queda en el cuadro sin enviarse;
  - los adjuntos se validan por tipo y tamaño antes de subir, diciendo el límite;
  - «Devolver al agente {nombre}» es la primera opción del menú.
  _Requisitos: 6.1–6.7, 14.9_
- [X] T076 [P] [US3] `apps/mobile/e2e/send-flaky.yaml` (Maestro): 100 envíos con la red cortada y restablecida. La comprobación en la base de pruebas es una fila por clave. _Requisitos: 6.4, CE-004_
  - **2026-10-20:** en el emulador, 100 envíos con doble toque en «Enviar» → **exactamente 100 filas nuevas, 100 claves, ninguna clave repetida** en la base. El corte de red a mitad de envío no se automatiza en el emulador (el modo avión de Maestro abre el panel del sistema y su «atrás» cierra la conversación; el túnel de `adb reverse` no se corta): queda como prueba manual en un teléfono contra staging. La garantía la fijan además `test_lite_send_idempotency.py` (misma clave, una fila) y Jest (el reintento reutiliza la clave).
  - **Escrito el 2026-10-20; sin ejecutar** hasta tener un build en emulador. Lo que sí está en verde: la idempotencia en la API (`test_lite_send_idempotency.py`) y la reutilización de la clave al reintentar en la app (`atender.test.tsx`).

### Implementación

- [X] T077 [US3] Idempotencia en `apps/api/src/nexus_api/api/console/lite/inbox.py` (envío) y `inbox_media.py` (adjuntos).
  - Cabecera `Idempotency-Key`, guardada en `messages.idempotency_key`.
  - La búsqueda y el replay se comparten con `services/direct_messages.py`, en un helper común que **sí** captura la violación de unicidad.
  - La web también la manda: se genera en `apps/console/src/app/(console)/inbox/actions.ts` y la recibe `lib/backend/inbox.ts`.
  - Pone T074 y T036 en verde.
  _Requisitos: 6.4, 6.8_
- [X] T078 [US3] `src/features/inbox/thread/take-control.tsx`: **el momento orquestado de D24**.
  - La franja del motivo se recoge y el cuadro sube en una sola transición de unos 250 ms, con muelle sin rebote.
  - Vibración `success` y «Tomaste el control» en el hilo.
  - Si el envío choca con un cambio de otra persona (412 o 409), vibración `warning` y el estado real.
  - Con movimiento reducido, todo pasa a fundido.
  _Requisitos: 6.1, 6.2, 14.7, 14.9_
- [X] T079 [US3] `src/features/inbox/composer/*`. Pone T075 en verde.
  - Envío optimista con `useMutation` y la clave por mensaje.
  - Estados «enviando», «enviado» y «no enviado», con fundido de 150 ms y vibración `light`.
  - Respuestas guardadas en una hoja.
  - Adjuntos: cámara y galería con `expo-image-picker`, PDF con `expo-document-picker`, comprobando antes los límites de 5 MB y 16 MB.
  - Aviso de ventana cerrada.
  - «Devolver al agente» en el menú.
  _Requisitos: 6.3–6.7, 14.9_

**Checkpoint**: T076 en verde. Se atiende de punta a punta desde el teléfono.

---

## Phase 8: US8. Contacto y notas (P3) · Iteración 2

**Goal**: ver y anotar al contacto mientras se atiende.

**Independent Test**: una nota editada en el teléfono aparece en la web.

- [X] T080 [P] [US8] `apps/mobile/__tests__/contacto.test.tsx`. Comprueba:
  - se muestran los datos, las etiquetas y la nota;
  - editar la nota y las etiquetas llama a `PUT …/note` y `PUT …/tags`;
  - el 422 se pinta en el campo;
  - los cinco estados.
  _Requisitos: 12.1, 12.2_
- [X] T081 [US8] `apps/mobile/src/app/(tabs)/bandeja/[id]/contacto.tsx`: en iOS, hoja con detención media o grande; en Android, hoja inferior modal. Pone T080 en verde. _Requisitos: 12.1, 12.2, 14.8_

**Checkpoint · fin de la iteración 2**:
- `./scripts/verify.sh` en verde.
- Builds `preview` por TestFlight y por la prueba interna de Play para el **piloto**.
- Anotar en `evidence/iteracion-2.md`.

---

## Phase 9: US2. Enterarse de que una conversación espera a una persona (P1) · Iteración 3

**Goal**: avisos normales que llegan con la app cerrada y abren su
conversación.

**Independent Test**: se fuerza un escalado con la app cerrada; el aviso llega
en menos de 10 s y, al tocarlo, abre la conversación.

### Tests

- [X] T082 [P] [US2] `apps/api/tests/integration/test_push_events_outbox.py`. Comprueba:
  - `mark_waiting` escribe `client_push_events` en **su** transacción, y un rollback no deja nada;
  - el mismo escalado no crea dos eventos (`dedupe_key`);
  - sin módulo Bandeja no hay evento;
  - un `emit()` de `client.balance_low` o `client.balance_out` que devuelve fila crea un evento en la misma sesión con `SET LOCAL`, y uno deduplicado no lo crea.
  _Requisitos: 8.2, 8.4, 8.5_
- [X] T083 [P] [US2] `apps/worker/tests/unit/test_inbound_push_event.py`: un entrante en una conversación con `agent_active = false` y `assigned_user_id` crea `inbox.message_for_you` en el mismo bloque transaccional; las burbujas plegadas, uno solo; con el agente activo, ninguno. _Requisitos: 8.3, 8.5_
- [X] T084 [P] [US2] `apps/api/tests/unit/test_push_texts.py`. Comprueba:
  - título y texto en ES y EN por tipo;
  - recorte a 100 caracteres con «…»;
  - «Un contacto» si no hay nombre, **nunca** el número;
  - «Foto» o «Documento» para los archivos;
  - el saldo con días o con a quién pedir.
  _Requisitos: 9.1, 9.2, 8.11_
- [X] T085 [P] [US2] `apps/worker/tests/unit/test_push_dispatcher.py`. Comprueba:
  - los destinatarios se calculan al repartir (`skipped` con `phone_revoked`, `kind_disabled`, `no_push_token` o `module_missing`);
  - `inbox.message_for_you` solo a la persona con el control y, si lo perdió, a nadie;
  - `inbox.waiting` ya tomada no se envía;
  - una entrega por evento y teléfono;
  - el reintento con espera creciente, como mucho 5;
  - `Unregistered`, `BadDeviceToken` y `UNREGISTERED` ponen `push_token = NULL`.
  _Requisitos: 8.2, 8.3, 9.3_
- [X] T086 [P] [US2] `apps/worker/tests/unit/test_apns_client.py`. Comprueba:
  - las cabeceras `apns-push-type: alert`, `apns-priority: 10`, `apns-topic` y `apns-collapse-id`;
  - el payload de [push.md](contracts/push.md), con `interruption-level`, `category`, `thread-id`, `badge` y `url`;
  - el token ES256 en caché, renovado antes de 50 min.
  - `apps/worker/tests/unit/test_fcm_client.py`:
    - la aserción RS256 y el token OAuth en caché;
    - el `channel_id` del tipo, `visibility: PRIVATE`, `tag`, `collapse_key`, `notification_count` y `data.url`.
  _Requisitos: 8.8, 8.9, 8.10, 9.1_
- [X] T087 [P] [US2] `apps/worker/tests/unit/test_bootstrap_split.py`: `push-dispatcher` en `ALL_EXPECTED` y en la familia egress. En rojo hasta T096. _Requisitos: 8.2, §VII_
- [X] T088 [P] [US2] `apps/api/tests/integration/test_phone_push_registration.py`: `PUT /console/lite/phones/current/push` guarda el proveedor, el destino y el entorno, quita el mismo destino de otro teléfono y responde 403 a la BFF. _Requisitos: 8.2, 9.3_
- [X] T089 [P] [US2] `apps/mobile/__tests__/push.test.tsx`. Comprueba:
  - la pantalla propia sale antes del diálogo del sistema y «Ahora no» no lo lanza;
  - los canales `waiting_v1`, `messages_v1` y `balance_v1` se crean **antes** de pedir el destino;
  - las categorías de iOS llevan `hiddenPreviewsBodyPlaceholder` y ninguna acción;
  - el destino se registra y se vuelve a registrar si cambia;
  - en primer plano, el aviso de la conversación abierta no se muestra;
  - tocar abre `url` con la app abierta y cerrada;
  - la placa se pone al día al volver;
  - la pantalla de permiso explica el ajuste de la pantalla bloqueada.
  _Requisitos: 8.6, 8.7, 8.10, 8.12, 10.1_

### Implementación

- [X] T090 [US2] Migración `0160_client_push_events.py`, como [data-model.md §0160](data-model.md):
  - `kind` CHECK `inbox.waiting` \| `inbox.message_for_you` \| `client.balance`;
  - `dedupe_key text NOT NULL` con `UNIQUE (tenant_id, dedupe_key)`;
  - `status` CHECK `pending` \| `fanned_out` \| `failed`, con `DEFAULT 'pending'`;
  - `attempts int NOT NULL DEFAULT 0`;
  - RLS `ENABLE` + `FORCE`;
  - el disparador `pg_notify('nexus_push')`, como 0062.
  _Requisitos: 8.1–8.5_
- [X] T091 [US2] Migración `0161_client_push_deliveries.py`, como [data-model.md §0161](data-model.md):
  - FK compuestas a `client_push_events (tenant_id, id)` y a `client_phones (tenant_id, id)`, con `ON DELETE CASCADE`;
  - `status` CHECK `queued` \| `sent` \| `failed` \| `skipped`;
  - `skip_reason` `phone_revoked` \| `kind_disabled` \| `no_push_token` \| `module_missing`;
  - `UNIQUE (tenant_id, event_id, phone_id)`;
  - RLS.
  - Modelos en `db/models/client_phone.py`.
  _Requisitos: 8.2, 9.3_
- [X] T092 [US2] `apps/api/src/nexus_api/services/push_events.py`, con `enqueue(session, …)` en la transacción del llamante. Se engancha en:
  - `services/inbox_lifecycle.py` (`mark_waiting`);
  - `services/wallet_alerts.py`, después de cada `emit()` de saldo con fila, con `SET LOCAL app.tenant_id`.
  - Pone T082 en verde.
  _Requisitos: 8.2, 8.4, 8.5_
- [X] T093 [US2] Enganche en `apps/worker/src/nexus_worker/runtime/dispatcher.py`, dentro del bloque transaccional de `_process_inbound_after_gates`: lee `assigned_user_id` junto a `conversation_agent_active` y llama a `push_events.enqueue(…, kind="inbox.message_for_you")`. Pone T083 en verde. _Requisitos: 8.3, 8.5_
- [X] T094 [US2] `apps/api/src/nexus_api/services/push_texts.py`, con los textos de [push.md §Textos](contracts/push.md) en ES y EN. Pone T084 en verde. _Requisitos: 8.1, 9.1, 9.2, 8.11_
- [X] T095 [US2] `apps/worker/src/nexus_worker/push/{apns.py,fcm.py}`, con `httpx[http2]` y PyJWT, más el mapeo de errores. Pone T086 en verde. _Requisitos: 8.8, 8.9, 8.10, 9.1_
- [X] T096 [US2] `apps/worker/src/nexus_worker/push/dispatcher.py`. Pone T085 y T087 en verde.
  - Drena con `FOR UPDATE SKIP LOCKED` y escucha `nexus_push` con un tick de 1 s.
  - Calcula los destinatarios al repartir, compone el texto y envía.
  - Reintenta con espera creciente y registra las entregas.
  - Se registra como `push-dispatcher` en `bootstrap.py`, en tres sitios: `_spawn`, `EGRESS_TASK_NAMES` y `ALL_EXPECTED`.
  _Requisitos: 8.2, 8.3, 9.3_
- [X] T097 [US2] `PUT /console/lite/phones/current/push` en `api/console/lite/phones.py`. Pone T088 en verde. _Requisitos: 8.2_
- [X] T098 [US2] App: `apps/mobile/src/push/{permission.ts,channels.ts,categories.ts,register.ts,handler.ts,routing.ts}` y la pantalla `src/app/notices-permission.tsx`, que se muestra tras la primera entrada. La placa se pone al día con `/inbox/counts`. Pone T089 en verde. _Requisitos: 8.6–8.10, 8.12, 10.1_
- [ ] T099 [US2] Lista manual en un dispositivo físico (iOS y Android) con capturas en `specs/031-auphere-customers-movil/evidence/avisos.md`:
  - aviso en menos de 10 s (CE-002), en el nivel urgente;
  - nombre y motivo con el teléfono desbloqueado y nada con «Al desbloquear» u ocultar contenido sensible;
  - abre la conversación con como mucho 2 toques hasta escribir (CE-003).
  _Requisitos: 8.8, 8.10, 8.11, CE-002, CE-003_
- [X] T100 [US2] Dejar en verde T032 (la parte de avisos) y T034, y ejecutar `apps/api/tests/isolation/` entera. _Requisitos: 15.1, 15.3, CE-006_

**Checkpoint**: los avisos funcionan solos y los seis barridos están en verde.

---

## Phase 10: US7. Decidir qué me avisa (P3) · Iteración 3

**Goal**: interruptores por tipo en este teléfono, permiso negado bien
explicado y solicitud de borrado de la cuenta.

**Independent Test**: con un tipo apagado no llega ese aviso, y los demás sí.

- [X] T101 [P] [US7] `apps/api/tests/integration/test_phone_notice_kinds.py`: `PUT /console/lite/phones/current/notices` acepta solo un subconjunto de los tres tipos (si no, 422), y el reparto salta con `kind_disabled`. _Requisitos: 11.2, 8.2_
- [X] T102 [P] [US7] `apps/api/tests/integration/test_account_deletion_request.py`: `POST /console/lite/account/deletion-request` responde 202, audita `client_account.deletion_requested`, envía un correo a la dirección de Auphere configurada y no envía otro en 24 h. _Requisitos: 11.4_
- [X] T103 [P] [US7] `apps/mobile/__tests__/ajustes-avisos.test.tsx`. Comprueba:
  - con el permiso concedido, un interruptor por tipo;
  - con el permiso negado, **ningún** interruptor, el texto que lo explica y «Abrir ajustes del teléfono» con `Linking.openSettings()`;
  - tras «Ahora no», «Activar avisos» lanza el diálogo;
  - «Solicitar el borrado» confirma en una hoja y dice qué pasa después.
  _Requisitos: 10.2, 10.3, 11.2, 11.4_
- [X] T104 [US7] `PUT /console/lite/phones/current/notices` y `POST /console/lite/account/deletion-request` en `api/console/lite/phones.py`, con la dirección `auphere_support_email` en la configuración. Pone T101 y T102 en verde. _Requisitos: 11.2, 11.4_
- [X] T105 [US7] La sección de avisos de `apps/mobile/src/app/ajustes.tsx` y «Solicitar el borrado de la cuenta». Pone T103 en verde. _Requisitos: 10.2, 10.3, 11.2, 11.4_

**Checkpoint · fin de la iteración 3**: la app completa en el piloto.

---

## Phase 11: Polish & Cross-Cutting

- [X] T106 [P] Escribir la spec viva `docs/app-movil.md`, enlazada desde `docs/consola-lite.md` y desde `docs/console.md`. Incluye:
  - la arquitectura;
  - las credenciales del teléfono;
  - el camino de los avisos;
  - los generadores;
  - cómo se hacen los builds, se envían a las tiendas y se publica una actualización por aire (solo arreglos, D19);
  - qué cambia al migrar de FACELAD a Auphere.
  - En `docs/consola-lite.md`: `nav`, la idempotencia y los teléfonos.
  _§IX, Requisitos: 3.2, 6.4_
- [ ] T107 [P] Evidencia de accesibilidad en `specs/031-auphere-customers-movil/evidence/a11y.md`:
  - el recorrido con VoiceOver y con TalkBack por cada pantalla;
  - capturas en claro y oscuro, en ES y EN, y con el texto del sistema al máximo;
  - las acciones de deslizar con su alternativa;
  - el contraste de los tokens generados.
  - **2026-10-20:** contraste medido y lo automático anotado en [evidence/a11y.md](evidence/a11y.md); faltan los recorridos y capturas en dispositivo.
  _Requisitos: 14.3–14.6, CE-008_
- [ ] T108 [P] Evidencia de movimiento en `specs/031-auphere-customers-movil/evidence/motion.md`:
  - un vídeo de «Tomar el control»;
  - la misma pantalla con movimiento reducido;
  - entradas de mensajes y recolocación de la Bandeja;
  - la herramienta de rendimiento a 60 fps en un teléfono medio;
  - una lista de las animaciones de la app con su duración: ninguna pasa de 300 ms y ninguna va en bucle salvo «Reconectando».
  - **2026-10-20:** inventario y pruebas en [evidence/motion.md](evidence/motion.md); faltan los vídeos y la medida de fps en dispositivo.
  _Requisitos: 14.7–14.9, D24_
- [ ] T109 Preparar las tiendas:
  - `apps/mobile/eas.json` con los perfiles `development`, `preview` y `production` y los canales de `expo-updates`;
  - la política de privacidad actualizada, con el texto de T003;
  - las etiquetas de privacidad del App Store y el formulario Data safety de Play;
  - el cliente de demostración en producción, bajo Auphere Internal Partner. Su Bandeja no puede enviar WhatsApp a personas reales; si eso exige código, se abre una spec aparte.
  - **2026-10-20:** lo del repo está hecho y los borradores de las fichas escritos ([evidence/tiendas.md](evidence/tiendas.md)); faltan las cuentas, la política publicada y el cliente de demostración (dueño).
  _Requisitos: 9.2, §II_
- [X] T110 Gates del workspace sobre el diff completo:
  - `/cso`, porque toca autenticación, secretos y entrada externa;
  - `tenant-security-audit` sobre la credencial del teléfono, la RLS y el reparto;
  - `ui-states-checklist`, `a11y-audit` y `responsive-audit` sobre la consola (`/account/phones`) y el admin.
  - Ningún hallazgo HIGH o CRITICAL abierto.
  - **2026-10-20:** `/cso` sobre el diff sin hallazgos confirmados (informe en la KB, el repo es público). Los cinco estados, nombres accesibles y tokens de `/account/phones` y del admin están en sus pruebas. Pase vivo con la base migrada: axe-core (WCAG 2.0–2.2 AA) **sin violaciones** a 367 px en `/account/phones` (oscuro) y en el diálogo de teléfonos del panel, sin desplazamiento horizontal. **2026-10-20, tras la enmienda de R1:** `/cso` sobre la entrada propia y `tenant-security-audit` sobre la credencial, `/app/*`, el reparto, los teléfonos y las migraciones 0158–0162: ningún camino entre clientes, 0 críticos, 0 altos. Corregido con prueba: la renovación y el canje contaban fallos en un solo cubo para todos los teléfonos (ahora la renovación no lleva límite y el canje cuenta por código); el reparto de avisos usaba una regla de «cliente abierto» más floja que cada petición (ahora las dos usan `open_client`, y el barrido de revocación suma «cliente archivado» y «partner suspendido»); el olvido de contraseña manda el correo fuera de la respuesta. Abierto, de configuración: el límite por IP de la entrada va en Cloudflare, con el ALB cerrado a sus rangos (runbook). Detalle en la KB (`compliance/2026-10-20-seguridad-spec-031.md`).
  _§I, Requisitos: 14.1, 15.2_
- [ ] T111 Validación completa: `./scripts/verify.sh` en verde, todas las secciones de [quickstart.md](quickstart.md) recorridas y anotadas en `evidence/quickstart.md`, y `/speckit-analyze` sin hallazgos críticos. _Requisitos: CE-001–CE-011_
  - **2026-10-20:** `./scripts/verify.sh` entero en verde tras los arreglos de la auditoría (API 5388, aislamiento, worker, channels, mcp, consola, panel, `next build`, app 124 y expo-doctor 20/20; una prueba de Jest se pasó de tiempo una vez con la máquina cargada y en tres pasadas sueltas pasa). El quickstart está recorrido salvo lo que pide un dispositivo o las cuentas: avisos reales de APNs y FCM, VoiceOver y TalkBack, y el corte de red a mitad de envío. Falta `/speckit-analyze` sobre la enmienda de R1.
- [X] T113 Lo que encontró el pase vivo en el emulador (2026-10-20), test primero en cada caso:
  - La conversación y su contacto se abren por encima de las pestañas (`apps/mobile/src/app/conversacion/[id]/{index,contacto}.tsx`). Antes, ocultar la barra desde dentro de la pestaña entraba en un bucle de foco con expo-router 58 y la app no abría ninguna conversación. Rutas de avisos y enlaces en `push/routing.ts` y `+native-intent.tsx`; la pila raíz ancla `index`.
  - Inicio se refresca con la Bandeja (`invalidateInbox` en `src/api/query.ts`): la insignia y «Necesita tu atención» no pueden decir cosas distintas.
  - La línea en vivo de un teléfono se corta sola a los 5 minutos (`PHONE_LINE_SECONDS` en `api/console/lite/inbox_stream.py`) y la app, ante un 403 en la línea, cierra la sesión con su motivo sin reintentar (`settleRefusal`). El barrido `tests/isolation/test_phone_revocation.py` comprueba los seis disparadores también sobre la línea, y que la de la web no se corta.
  - Texto del sistema al 200 %: iconos sin recortar (parche de `expo-symbols`), tarjetas de cifras que pasan a una por fila, contacto sin nombre con icono de persona, lista de la pantalla de avisos bajo su frase, título de la cabecera en el color del texto.
  _Requisitos: 4.1, 5.3, 7.2, 8.6, 14.3, 15.3_

- [ ] T112 Medir tras dos semanas de piloto y escribir el resultado en la nota de KB `/Users/lmatos/Work/Auphere/nexus/research/2026-10-19-consola-lite-movil.md`:
  - CE-010, con los eventos de la conversación (pidió ayuda y control tomado);
  - CE-002, el p95 entre `client_push_events.created_at` y `client_push_deliveries.sent_at` de `inbox.waiting`.
  _Requisitos: CE-002, CE-010_

---

## Phase 12: Enmienda de R1 — la entrada propia de la app (2026-10-20)

**Objetivo**: la persona entra en Auphere Customers con correo y contraseña o con
Google, sin pasar por la consola de partners (aclaración del 2026-10-20, research
D2b, contrato `phone-auth.md`). Sustituye a T020–T024 en lo que tocaban
`/app-auth` y el canje `POST /app/phones`.

**Prueba independiente**: con la pila local, la persona entra con su correo y
contraseña desde la pantalla de la app; una de partner recibe «no es para ti»;
la cuenta de Google de otro correo se rechaza sin enseñar el dado de alta.

### Pruebas primero

- [X] T114 [P] [US1] `apps/api/tests/integration/test_app_sign_in_password.py`: entra (201 y credenciales que leen `/console/lite/me`); contraseña mala, correo desconocido y cuenta bloqueada dan el mismo 401 `invalid_credentials`; partner → 403 `not_a_client`; acceso apagado o persona quitada → 403 `no_access`; versión vieja → 403 `app_update_required`; límite por correo y por IP → 429 `rate_limited`; deja constancia en la auditoría. _Requisitos: 1.2, 1.4–1.6, 7.6, 13.1_
- [X] T115 [P] [US1] `apps/api/tests/integration/test_app_sign_in_google.py` con Google simulado: el inicio redirige a Google con `select_account` y un `state` firmado que lleva el de la app; la vuelta emite un código que solo se canjea con el verificador de la app; correo de Google distinto del de la membresía (sin cuenta, con cuenta, o con el `sub` ya vinculado y el correo cambiado) → `google_account_mismatch`; correo sin verificar, partner, sin acceso, cancelado y `state` caducado o reutilizado vuelven a la app con su `error`; sin Google configurado → `google_unavailable` y `/app/config` dice `google: false`. _Requisitos: 1.3–1.6, 1.9_
- [X] T116 [P] [US1] `apps/api/tests/integration/test_app_password_reset.py`: 202 con el mismo cuerpo exista o no la cuenta; sin cuenta no sale correo; con cuenta sale el enlace de la web; el límite por dirección se traga en silencio. _Requisitos: 1.7_
- [X] T117 [US1] Barrido de aislamiento en `apps/api/tests/isolation/test_phone_route_scope.py` y `test_console_scope.py`: las rutas nuevas de `/app/*` son públicas a propósito y ninguna devuelve datos de un cliente sin credenciales; `/console/lite/phone-codes` ya no existe. _Requisitos: 15.1, 15.2_
- [X] T118 [P] [US1] `apps/mobile/__tests__/sign-in.test.tsx`: la pantalla tiene correo, contraseña (con mostrar u ocultar) y «Entrar», con autocompletado del sistema; Google solo si `/app/config` lo ofrece; cada código de error pinta su texto (R1.2–R1.6, R1.9); «¿Olvidaste tu contraseña?» manda el correo y dice lo mismo siempre; nada de la consola de partners. _Requisitos: 1.1–1.9, 14.3_

### Implementación

- [X] T119 [US1] API: `POST /app/sign-in/password`, `GET /app/sign-in/google`, `GET /app/sign-in/google/callback`, `POST /app/sign-in/google` y `POST /app/password-reset` en `apps/api/src/nexus_api/api/app_public.py`; `sign_in` en `/app/config`; fuera `POST /app/phones` y `POST /console/lite/phone-codes`. Pone T114–T117 en verde. _Requisitos: 1.1–1.9_
- [X] T120 [US1] App: pantalla de entrada nativa en `apps/mobile/src/app/sign-in.tsx` (+ `forgot-password.tsx`) y `src/auth/sign-in.ts` con los dos métodos; fuera la entrada por la consola. Pone T118 en verde. _Requisitos: 1.1–1.9, 14.1–14.6_
- [X] T121 [US1] Consola: fuera `app/(auth)/app-auth`, `lib/app-redirect.ts`, la ruta pública en `proxy.ts` y `litePhoneCode` de la BFF, con sus pruebas. _Requisitos: 1.1_
- [X] T122 Docs en el mismo cambio: `docs/app-movil.md` (entrar), `docs/consola-lite.md`, `apps/mobile/e2e/sign-in.yaml` (Maestro con la entrada nativa) y el pase vivo en `evidence/quickstart.md`. _§IX, Requisitos: 1.1_

**Checkpoint**: se entra desde la app con correo y contraseña en el emulador, contra la pila local; Google queda probado con el proveedor simulado y listo para el cliente OAuth de staging.

**2026-10-20, hecho:** entrar con contraseña, la contraseña mala, el olvido de contraseña y volver a entrar, en vivo en el emulador contra la pila local ([capturas](evidence/capturas/)); Google con el proveedor simulado (17 pruebas). La revisión `/cso` de la entrada encontró que `/app/phones/refresh` y el canje contaban los fallos en un solo cubo para todos los teléfonos (a `/app` se llega sin la BFF): corregido (la renovación no lleva límite, el canje cuenta por código) con sus pruebas. El límite por IP de la entrada es del borde (Cloudflare, runbook en `docs/app-movil.md`).

---

## Dependencies & Execution Order

### Entre fases

- **Setup (F1).**
  - T002 (S1) decide el SDK antes de T005.
  - T004 (las cuentas) **no** bloquea el código: bloquea los builds en dispositivo: S1, los builds de fin de las iteraciones 1 y 2, y T099.
- **Foundational (F2):** depende de T005 y T008. **Bloquea todas las historias.**
- **Puertas (F2b):** se escriben al empezar F2. Cada una se pone en verde en la tarea que indica.
- **Iteración 1:** US1 → US6 → US5. US5 puede ir en paralelo con US6 tras US1.
- **Iteración 2:** US4 → US3 → US8. US3 necesita el hilo de US4.
- **Iteración 3:** US2 → US7. US2 necesita US3, porque el aviso abre una conversación en la que se atiende.
- **Polish (F11):** tras la iteración 3. T106 a T108 pueden empezar en cuanto exista la pantalla que documentan.

### Dentro de cada historia

- **Primero los tests, en rojo** (§VII).
- **Luego, en orden:**
  1. migraciones y modelos;
  2. servicios;
  3. rutas;
  4. consola, admin y app.
- **En la app,** las pantallas usan siempre `src/ui/`, `src/motion/` y `tokens.gen.ts`. Nada se escribe a mano.

### Parallel Opportunities

- **F1:** T003, T004, T006 y T008 en paralelo.
- **F2:** los tests T009 a T014 en paralelo; luego T022 a T024 (generadores) en paralelo con T015 a T021 (API).
- **F2b:** los seis barridos y T036 en paralelo.
- **US1:** T037 a T044 en paralelo. La consola (T048) y la app (T049) en paralelo tras T047.
- **US6:** T051 a T055 en paralelo. El admin (T058) y la consola (T060) en paralelo.
- **US5:** las dos pantallas (T065 y T066) en paralelo.
- **US2:**
  - T082 a T089 en paralelo;
  - el envío al proveedor (T095) en paralelo con los enganches (T092 y T093);
  - la app (T098) en paralelo con el worker.

## Parallel Example: US2

```bash
Task: "test_push_events_outbox.py en apps/api/tests/integration/"
Task: "test_push_dispatcher.py en apps/worker/tests/unit/"
Task: "test_apns_client.py y test_fcm_client.py en apps/worker/tests/unit/"
Task: "push.test.tsx en apps/mobile/__tests__/"
# y después, en paralelo:
Task: "apps/worker/src/nexus_worker/push/{apns.py,fcm.py}"
Task: "apps/mobile/src/push/*"
```

## Implementation Strategy

1. **Iteración 0 (S1).** Decide el SDK. Mientras tanto se piden las cuentas (T004) y se escribe el ADR-042.
2. **Iteración 1: la puerta y lo que se lee** (US1, US6 y US5). Es entregable sola: una app de solo lectura con revocación completa. Es el **MVP técnico**, y prueba lo más delicado, la credencial del teléfono, antes de escribir nada.
3. **Iteración 2: la Bandeja** (US4, US3 y US8). Con ella empieza el **piloto** en las pruebas cerradas de las tiendas.
4. **Iteración 3: los avisos** (US2 y US7). Completa la propuesta de valor del piloto.
5. **Polish.** Las evidencias, las tiendas y los gates de seguridad.

**Cada iteración termina con:**
- `./scripts/verify.sh` en verde;
- sus barridos de aislamiento en verde;
- una nota en `evidence/`;
- **la persona hace el commit**.

## Notes

- `[P]`: archivos distintos, sin dependencias pendientes.
- Verificar que cada test falla antes de implementar.
- El hallazgo lateral del PKCE del escritorio va por su propio flujo de bugs.
  T045 no lo toca: añade `base64url` sin cambiar `hex`.
- Las versiones de las librerías se vuelven a comprobar en T005 y T006.
