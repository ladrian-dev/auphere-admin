---

description: "Tareas de la spec 062 — la consola aguanta una API lenta (hotfix P0)"
---

# Tasks: La consola aguanta una API lenta

**Input**: Design documents from `/specs/062-consola-resiliente/`

**Prerequisites**: [plan.md](plan.md), [spec.md](spec.md)

**Tests**: obligatorios (constitución §VII). Se escribieron antes del arreglo y se
vieron en rojo: 7 de 12. Las 5 que ya pasaban comprueban lo que no debe
repetirse.

## Phase 1: Mitigación en prod (configuración)

- [x] T001 Cambiar `NEXUS_BACKEND_URL` del proyecto `auphere-console` (Production) de `https://api.auphere.com` a `https://webhooks.auphere.com` y volver a desplegar. Hecho el 2026-11-17 a las 20:41 UTC (`dpl_6ajvEAgR2oLHU3fffxixRkforXuu`). Vuelta atrás: el valor anterior y volver a desplegar. _Requisitos: 4.1_
- [x] T002 Medir CE-2 con `/login` de prod y de staging alternados, 60 cargas de cada uno. Prod: p50 0,34 s, p90 0,84 s, máximo 1,59 s. Staging: p50 0,47 s, p90 0,71 s, máximo 1,24 s. _Requisitos: 4.1_
- [x] T003 Escribir el cambio en `infra/README-console.md`, sección «Producción». _Requisitos: 4.2_

## Phase 2: User Story 1 — Una API lenta no saca a nadie de su sesión (P1)

- [x] T004 [US1] Test en `apps/console/src/lib/__tests__/backend-resilience.test.ts`: el primer intento de la consulta de sesión agota su plazo, el segundo contesta y su token es distinto. Rojo antes de T006. _Requisitos: 1.1_
- [x] T005 [US1] `apps/console/src/lib/__tests__/session-retry.test.ts` (spec 056) sigue en verde sin cambios: 401 como «no hay sesión», 4xx sin repetir, 5xx, red y plazo agotado repetidos una vez. _Requisitos: 1.2, 3.3_
- [x] T006 [US1] `session()` usa el reintento de `request()`, marcándose como repetible y con plazo de 5 s; el 401 sigue siendo `null`. _Requisitos: 1.1, 1.2, 3.3_

## Phase 3: User Story 2 — Un corte de red no tumba la pantalla (P1)

- [x] T007 [US2] Tests en `backend-resilience.test.ts`:
  - lectura con `ECONNRESET`: se repite con un token nuevo;
  - plazo agotado y 502: se repiten;
  - dos fallos seguidos: llegan al llamante;
  - 4xx: no se repite;
  - si quien llama cancela, no se repite;
  - escritura con `UND_ERR_CONNECT_TIMEOUT`, suelto o agrupado: se repite;
  - escritura con `ECONNRESET` o 503: no se repite.

  Rojo antes de T008. _Requisitos: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6_
- [x] T008 [US2] `request(mint, path, opts)` en `apps/console/src/lib/backend.ts`:
  - acuña un token por intento;
  - un solo reintento, según `neverSent` o, si es repetible, según `passing`;
  - una línea `console.backend_retry` por reintento.

  Los 18 llamantes pasan `mintServiceToken` o `() => mintPrincipalToken(claims)`. _Requisitos: 1.1, 2.1–2.7_

## Phase 4: User Story 3 — Una lectura perdida no deja la página colgada (P2)

- [x] T009 [US3] Tests: una lectura lleva `signal`; una escritura, por defecto, no. _Requisitos: 3.1, 3.2_
- [x] T010 [US3] Plazo `READ_TIMEOUT_MS = 15_000` por intento en las lecturas, combinado con el `signal` de quien llama (`AbortSignal.any`). _Requisitos: 3.1, 3.2_

## Phase 5: Cierre

- [x] T011 En `apps/console`: `vitest run` (254 ficheros, 2278 pruebas), `tsc --noEmit`, `eslint --max-warnings 0`, `check-no-env-leaks` y `next build` con el entorno de la tubería. Todo en verde.
- [x] T012 Nota de KB `bugs/2026-11-17-consola-lenta-por-cloudflare.md`.
- [ ] T013 Commit en la rama (lo hace Luis), PR a `main` y, después, fusionar `main` en `develop`. `backend.ts` es igual en las dos ramas.
- [ ] T014 Tras desplegar, comprobar CE-1 y CE-3 durante un día:
  - `console_auth.replayed_jti` en `/nexus/prod/api`;
  - errores `fetch failed` y `TimeoutError` en Vercel;
  - líneas `console.backend_retry`.
