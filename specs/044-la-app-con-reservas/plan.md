# Implementation Plan: La app con Reservas

**Branch**: `044-la-app-con-reservas` | **Date**: 2026-10-22 | **Spec**: [spec.md](spec.md)

**Input**: `specs/044-la-app-con-reservas/spec.md` · [research.md](research.md) ·
[contracts/app-needs.md](contracts/app-needs.md) · KB
`[[research/2026-10-22-reservas-y-consola-customers]]`

## Summary

**Qué se construye.** Auphere Customers (`apps/mobile`) gana la pestaña
**Reservas** en sus dos modos y las mejoras del lienzo de Claude Design, con las
formas de la 042. Sin tocar la API, el worker ni la consola: lo que la app
necesita lo construyen las specs 043 y 045 (`consolas-web`), y la app lo lee por
`/console/lite/*` con el `ClientPrincipal` de siempre.

- **Reservas** (P1–P3): Día (Servicios en lista o cuadrícula; Aforo con cifras,
  tira de franjas y grupos por hora), Semana, Mes, la hoja de cada reserva con
  sus acciones, Nueva reserva, la llegada sin reserva con su «+» flotante (Aforo,
  Día, hoy), Lista de espera, Ajustes de reservas y Bloquear horas.
- **Mejoras**: Inicio (reservas sin confirmar en la atención, filas que llevan a
  su sitio, «Hoy en Reservas»), Bandeja (grupo fijo de las que esperan, pie),
  conversación (desde cuándo espera, «Devolver» a un toque, respuestas en chips),
  contacto (próxima reserva), Consumo («Te alcanza hasta…»), avisos por módulo y
  silencio fuera de horario, Entrar (nota de Google), la pantalla de permiso
  (aviso de ejemplo y H15).
- **Builds 1.1.0**: iOS `staging` → TestFlight; Android `staging` → Play pista
  interna con Firebase, con la lista de lo que crea Luis.

**Cómo.** Todo Reservas pasa por un adaptador con dos fuentes (HTTP y datos de
ejemplo de desarrollo) contra el contrato propuesto (D1, D2). Las pantallas son
puras sobre el modelo de `data-model.md` y se prueban sin red. Nada nativo
nuevo: el cliente de desarrollo de la 042 sirve (D15).

## Technical Context

| | |
|---|---|
| **Language/Version** | TypeScript 6 (estricto, `noUncheckedIndexedAccess`), React 19.3, React Native 0.88 |
| **Primary Dependencies** | Expo SDK 58, expo-router 58 (`NativeTabs`, `Stack.Toolbar`, `formSheet`), react-native-screens 4.30, Reanimated 4.7, `expo-glass-effect` (042), `expo-symbols`, React Query 5, openapi-fetch. **Ninguna nueva** |
| **Storage** | Ninguno: memoria de React Query, como la 031 |
| **Testing** | jest-expo + RNTL 14 (`apps/mobile/__tests__`), test primero por requisito · capturas en «13 26» (iOS 26.0.1) y Pixel 9 (API 36) en `evidence/capturas/` · gates de UI del workspace (`ui-states-checklist`, `a11y-audit`, `responsive-audit`, `design-tokens`) |
| **Target Platform** | iOS 16.4+ (vidrio en 26+) · Android targetSdk 36 |
| **Project Type** | móvil: la app Expo en su propio workspace de pnpm |
| **Performance Goals** | Cambiar de día o de periodo sin esqueleto si el dato ya está (React Query `placeholderData`) · animaciones ≤ 300 ms |
| **Constraints** | Sin hex escrito a mano (ESLint) · formas de la 042 · horas de pared del negocio (D3) · nada de los clientes finales en disco · los datos de ejemplo nunca fuera de `__DEV__` · `docs/app-movil.md` en el mismo commit |
| **Scale/Scope** | 1 pestaña nueva con 3 pantallas y 4 hojas; 7 pantallas tocadas; 3 primitivas nuevas (`Toast`, `Fab`, `Pill`) |

## Constitution Check

*Rellenado antes de la Fase 0 y comprobado otra vez tras el diseño: en verde.*

| # | Principio | ¿Cumple? | Prueba / justificación |
|---|---|---|---|
| I | Aislamiento entre tenants; `tenant_id` del contexto, nunca del llamante; whitelist exhaustiva | ☑ | La app no manda `tenant_id` ni `customer_id` (el contrato no los tiene); la agenda del negocio la filtra la RLS de la API y su barrido en `tests/isolation/` es de la 043 (`test_lite_client_vs_client.py`, `test_lite_route_scope.py`). En la app, nada de clientes finales en disco: `__tests__/reservas-no-disk.test.ts` comprueba que el adaptador no escribe en el almacén |
| II | Corte por superficie de confianza | ☑ | Superficie `0`, ya abierta por la 031. Ninguna nueva |
| III | Lo leído es dato, nunca instrucción | ☑ | Los textos del cliente final (nombre, historial) se pintan como texto; no hay agente en el teléfono |
| IV | Acción `mutates` con aprobación durable; auditoría nombra a la persona | ☑ | Las escrituras son de la persona que toca, con su sesión; la API audita quién (`by`). Cancelar pide confirmación (clarificación 2). Nada automático |
| V | Estados honestos; la ausencia se diseña | ☑ | Cinco estados más sin red en cada pantalla (R16.1); sin módulo no hay pestaña (R1.2); un ajuste no editable se lee, sin control apagado (R8.6); sin `waiting_since` no se inventa el tiempo (R10.2); los datos de ejemplo llevan su marca (R18) |
| VI | Por API, nunca navegando la consola | ☑ | Todo por `/console/lite/*` |
| VII | Test primero; el criterio de aceptación es el test; nada de `skip` | ☑ | Cada requisito nace como prueba de RNTL o de modelo en rojo; lo que solo se ve en el teléfono tiene su captura en `evidence/` |
| VIII | Licencias | ☑ | Ninguna dependencia nueva (D15) |
| IX | La KB es dueña del porqué | ☑ | `[[research/2026-10-22-reservas-y-consola-customers]]`; la nota enlaza a `specs/044-…/` (tarea de cierre) |

### Las tres puertas que `/speckit-tasks` comprueba

| Puerta | Respuesta | Tarea que la cubre |
|---|---|---|
| **Aislamiento** | Ninguna garantía tocada en la app. La superficie nueva (la agenda del negocio, los avisos de Reservas) es de la API y su test es de la 043. La app comprueba que nada de Reservas va a disco | T013 (`reservas-no-disk.test.ts`) |
| **Licencias** | Ninguna dependencia nueva | Ninguna |
| **Medidor** | Nada gasta en la app | Ninguna |

**Complejidad que hay que justificar:** el adaptador con dos fuentes (D1, D2).
Ver Complexity Tracking.

## Decisiones

En [research.md](research.md), con su porqué. En corto:

| # | Decisión |
|---|---|
| D1 | Contrato propuesto (`contracts/app-needs.md`) y un adaptador `src/api/reservas.ts`; rutas nuevas por `authedFetch` hasta que `openapi.json` las traiga |
| D2 | Datos de ejemplo chilenos solo en `__DEV__` con `EXPO_PUBLIC_RESERVAS_DEMO`, con la marca a la vista |
| D3 | Horas de pared del negocio y «ahora» del servidor |
| D4 | Inicio cuenta Reservas desde la lectura del día, no desde `home` |
| D5 | Pila de la pestaña (`index`, `espera`, `ajustes`) y cuatro hojas en la pila raíz |
| D6 | Los dos «+»: barra con `calendar.badge.plus` en iOS y flotante extendido en Android para «Nueva reserva»; «+» flotante solo para la llegada |
| D7 | Aviso breve opaco, anunciado, 4–6 s |
| D8 | Lista primero; Cuadrícula con columnas de 120 pt y aviso con texto grande |
| D9 | Aforo con cifras en lista agrupada, tira de franjas y mapa de calor de cinco niveles |
| D10 | Mes en rejilla y flechas en Semana y Mes |
| D11 | Mejoras con las formas de la 042 (tabla de choques) |
| D12 | Avisos por grupo, tres de Reservas, silencio si la API lo trae, canal y categoría nuevos; H15 |
| D13 | Etiquetas de la barra de pestañas con tamaño fijo (H25) |
| D14 | 1.1.0 y builds de `staging` para TestFlight y Play interna |
| D15 | Sin dependencias nuevas |

## Project Structure

### Documentation (this feature)

```text
specs/044-la-app-con-reservas/
├── spec.md · plan.md · research.md · data-model.md · quickstart.md · tasks.md
├── contracts/app-needs.md     # lo que la app pide a la API (043/045)
├── checklists/requirements.md
└── evidence/                  # capturas, hallazgos, builds.md
```

### Source Code

```text
apps/mobile/
├── app.config.ts · eas.json · package.json      # 1.1.0, perfiles (D14)
├── src/api/
│   ├── reservas.ts            # NUEVO: modelo, adaptador HTTP, mapeo del contrato (D1)
│   ├── reservas-demo.ts       # NUEVO: fuente de ejemplo, solo __DEV__ (D2)
│   ├── reservas-hooks.ts      # NUEVO: lecturas y escrituras con React Query
│   ├── endpoints.ts · hooks.ts · query.ts        # campos de 045, claves, invalidaciones
├── src/lib/
│   ├── modules.ts             # + reservas
│   └── reservas-model.ts      # NUEVO: «ahora», cerrado, llega tarde, resúmenes, niveles (puro)
├── src/features/reservas/     # NUEVO: day-services, day-grid, day-capacity, week, month,
│                              #        header (periodo, tira de días), sheet, new, walk-in,
│                              #        waitlist, settings, block, pills, demo-mark
├── src/app/(app)/reservas/    # NUEVO: _layout, index, espera, ajustes
├── src/app/reserva/           # NUEVO: [id], nueva, llegada, bloquear (hojas)
├── src/features/home/         # atención + Hoy en Reservas
├── src/features/inbox/        # grupo de espera, pie, tarjeta, chips
├── src/features/usage/        # Te alcanza hasta
├── src/features/notices.ts · src/push/*        # tipos, grupos, canal, categoría, ruta
├── src/ui/{toast,fab,pill}.tsx                 # NUEVO
├── src/i18n/app.{es,en}.ts    # palabras nuevas
└── __tests__/                 # una prueba por requisito
docs/app-movil.md              # spec viva
```

**Structure Decision**: todo dentro de `apps/mobile` y la documentación de la
spec; `docs/app-movil.md` en el mismo commit. Ningún archivo de `apps/api`,
`apps/worker`, `apps/mcp` ni `packages/*` (son de `consolas-web`).

## Complexity Tracking

| Qué | Por qué hace falta | Alternativa más simple descartada |
|---|---|---|
| Adaptador con dos fuentes (HTTP y ejemplo) | La API de Reservas se construye a la vez; hay que construir, probar y capturar antes de que exista, y absorber su contrato final en un solo sitio | Esperar a la API (no cabe en la jornada) o datos de ejemplo dentro de cada pantalla (doce sitios que limpiar después, y riesgo de que lleguen a un build) |
