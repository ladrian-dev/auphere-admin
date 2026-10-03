# Implementation Plan: la ficha adelgaza y sus catálogos se navegan

**Branch**: `018-ficha-ligera-y-catalogos` | **Date**: 2026-09-27 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/018-ficha-ligera-y-catalogos/spec.md`

## Summary

La consola sabe hacer todo lo que tiene que hacer; lo que cuesta es
encontrarlo. Esta spec no añade capacidades: **junta lecturas que ya existen en
un Resumen que contesta**, quita dos pestañas que no se ganaban su sitio, y
construye **una sola vez** el patrón de navegación que Habilidades, Conectores y
Canales van a necesitar cuando tengan decenas de elementos en vez de seis.

El enfoque técnico sale de la Fase 0 y cabe en una frase: **no se toca la API**.
El Resumen pide en paralelo cuatro lecturas que ya están —y pedirlas por
separado es justo lo que hace que el fallo de una no tumbe la pantalla—, el
renombrado es copy, y el patrón de catálogo se extrae de la pantalla de
Capacidades, que ya tiene tres cuartas partes de él.

## Technical Context

**Language/Version**: TypeScript 5.9 (consola, Next.js 16 App Router) · Python
3.14 en local / 3.11 en CI (API, solo lecturas ya existentes)

**Primary Dependencies**: `@nexus/ui` (Base UI + Tailwind v4) · ninguna nueva

**Storage**: N/A — esta spec no crea ni migra tablas

**Testing**: vitest (consola y `@nexus/ui`) · Playwright (`a11y.spec.ts`,
`record.spec.ts`) · pytest solo para la barrida de aislamiento

**Target Platform**: navegador, desde 360 px; la consola está en Vercel

**Project Type**: aplicación web con BFF (consola) sobre API propia

**Performance Goals**: el Resumen resuelve en **cuatro lecturas por ficha**, en
paralelo, y ninguna crece con el número de clientes del partner (R1.8)

**Constraints**: cero violaciones serias o críticas de axe; sin desbordes a
360 px ni a 1920 px con el texto al 130 %; ES y EN; ninguna dirección de hoy
puede responder «no existe» (CE-007)

**Scale/Scope**: 3 pantallas rehechas (Resumen, y el patrón en Habilidades,
Conectores y Canales), 2 pestañas retiradas, 2 renombrados, 1 componente nuevo
en el sistema de diseño

## Constitution Check

| # | Principio | ¿Cumple? | Prueba / justificación |
|---|---|---|---|
| I | Aislamiento entre tenants; `tenant_id` del contexto, nunca del llamante; whitelist exhaustiva | ✅ | No se añade endpoint. La garantía que sí hay que probar es que **juntar** cuatro lecturas no abre una puerta: `tests/isolation/test_console_scope.py` extendido con el Resumen de un cliente ajeno → 404 opaco, e idéntico al de un cliente que no existe |
| II | Corte por superficie de confianza; no se abre una nueva sin agotar la actual | ✅ | Superficie `0` declarada en la spec. No se abre ninguna: se lee lo que ya se leía |
| III | Lo leído es dato, nunca instrucción | ✅ | No entra texto de terceros en ningún prompt. El Resumen pinta cifras propias |
| IV | Acción `mutates` con aprobación durable; auditoría nombra a la persona | ✅ | La única escritura es editar nombre y zona horaria, que ya existe (`PATCH /console/clients/{ref}`) con su auditoría. No se crea ninguna escritura nueva |
| V | Estados honestos, incluido `parcial` y `bloqueado`; la ausencia se diseña | ✅ | R1.6 (un bloque que falla lo dice y los demás siguen), R1.7 (sin actividad ≠ cero), R4.3 (vacío por filtro ≠ catálogo vacío), R4.7 (un canal que no existe **no** se enseña apagado) |
| VI | Por API `console.*`, nunca navegando la consola de Auphere | ✅ | Todo por los endpoints `/console/*` de la tabla de contratos |
| VII | Test primero; el criterio de aceptación es el test; nada de `skip` | ✅ | Cada iteración abre con sus tests en rojo. Los criterios EARS de la spec son los nombres de los tests |
| VIII | Licencias leídas enteras; AGPL no | ✅ | **Ninguna dependencia nueva.** `scripts/verify.sh locks` lo comprueba |
| IX | La KB es dueña del porqué; la spec enlaza a su nota | ✅ | `[[nexus/sessions/2026-09-27-spec-017-iteracion-2]]` y `[[nexus/PLAN-ACCION-CONSOLA-2026-09-22]]` |

### Las tres puertas que `/speckit-tasks` comprueba

| Puerta | Respuesta | Tarea que la cubre |
|---|---|---|
| **Aislamiento** — ¿qué garantías toca? | Ninguna nueva. Se comprueba que componer cuatro lecturas en el Resumen no delata a un cliente ajeno, ni por respuesta ni por forma del error | `T-ISO` en `tests/isolation/test_console_scope.py` |
| **Licencias** — ¿qué dependencia nueva entra? | **Ninguna** | `T-LIC`: `scripts/verify.sh locks` |
| **Medidor** — ¿qué gasta y dónde lo ve el partner? | **Nada.** El Resumen lee unidades que el medidor de la spec 004 ya registra; no escribe ninguna | `T-MET`: test de que el Resumen no produce `UsageRecord` |

**Complejidad que hay que justificar:** una sola cosa, y está abajo.

## Project Structure

### Documentation (this feature)

```text
specs/018-ficha-ligera-y-catalogos/
├── plan.md              # este fichero
├── spec.md              # qué y por qué
├── research.md          # Fase 0 — seis decisiones
├── data-model.md        # Fase 1 — modelo de lectura (sin tablas nuevas)
├── contracts/README.md  # Fase 1 — ningún endpoint nuevo; el contrato es de componente
├── quickstart.md        # Fase 1 — cómo se comprueba sobre la app real
├── parity.md            # inventario de lo que no puede desaparecer (lo abre /speckit-tasks)
└── tasks.md             # lo genera /speckit-tasks
```

### Source Code (repository root)

```text
packages/ui/src/
├── components/
│   └── catalog-browser.tsx        # NUEVO — buscador + pestañas + filtro + grupos
├── components/__tests__/
│   └── catalog-browser.test.tsx   # NUEVO
└── stories/prototypes/
    ├── client-summary.stories.tsx # NUEVO — prototipo iteración 1
    └── catalog.stories.tsx        # NUEVO — prototipo iteración 2

apps/console/src/
├── app/(console)/clients/[ref]/
│   ├── page.tsx                   # el Resumen, rehecho
│   ├── settings/page.tsx          # pasa a redirección permanente
│   ├── agent/page.tsx             # absorbe los ajustes
│   ├── agent/settings/page.tsx    # pasa a redirección permanente
│   ├── capabilities/page.tsx      # usa CatalogBrowser; se llama Habilidades
│   ├── integrations/page.tsx      # usa CatalogBrowser; se llama Conectores
│   └── channels/page.tsx          # usa CatalogBrowser
├── components/
│   ├── clients/summary/           # NUEVO — los cuatro bloques
│   └── clients/client-nav-model.ts# once pestañas → nueve
└── i18n/lanes/                    # copy: Habilidades, Conectores, cabeceras

apps/api/tests/isolation/
└── test_console_scope.py          # el Resumen entra en la barrida
```

**Structure Decision**: monorepo ya existente. El único fichero nuevo fuera de
la consola es el componente de catálogo, que vive en `packages/ui` porque lo
usan tres pantallas distintas (decisión 2 de la Fase 0). La API **no se toca**
salvo por un test.

## Iteraciones

El mismo ritual de la spec 017: prototipo aprobado → tests en rojo → código →
suites en verde → paridad → evidencia → log en la KB → merge → staging.

| # | Historias | Entrega |
|---|---|---|
| **1** | H1, H2, H5 | El Resumen contesta; dos pestañas menos; la puesta en marcha pesa menos |
| **2** | H3 | `CatalogBrowser` y las tres pantallas que lo usan |
| **3** | H4 | Habilidades, Conectores y las dos cabeceras que se explican |

La 3 es la más barata y va al final a propósito: renombrar antes de que las
pantallas estén en su forma definitiva obligaría a tocar el copy dos veces.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| Un componente nuevo en el sistema de diseño (`CatalogBrowser`) que la spec no nombra | La spec pide que los tres catálogos se recorran con el mismo gesto (R4.6). Sin una pieza compartida, «igual» dura hasta el segundo cambio | Copiar el patrón en las tres pantallas es más barato hoy y más caro en la tercera: es exactamente lo que pasó con Herramientas y Habilidades antes de la spec 017 |
