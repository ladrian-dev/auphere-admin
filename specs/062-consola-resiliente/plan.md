# Implementation Plan: La consola aguanta una API lenta

**Branch**: `062-consola-resiliente` | **Date**: 2026-11-17 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/062-consola-resiliente/spec.md`. Hotfix P0: el plan se escribe a la vez que el arreglo.

## Summary

Hay dos cambios.

1. **Configuración, ya aplicada en prod el 2026-11-17 a las 20:41 UTC.** En el
   proyecto `auphere-console` de Vercel, `NEXUS_BACKEND_URL` pasa a
   `https://webhooks.auphere.com` (requisito 4), y se volvió a desplegar el mismo
   código (`dpl_6ajvEAgR2oLHU3fffxixRkforXuu`).
2. **Código.** `request()` en `apps/console/src/lib/backend.ts` recibe la función
   que acuña el token, en vez del token ya acuñado. Así cada intento lleva el suyo
   (requisito 1). Dentro de `request()`, un solo reintento (requisito 2) y un plazo
   por intento para las lecturas (requisito 3). `session()` deja su bucle propio y
   usa este, marcándose como repetible y con su plazo de 5 s.

Sin migraciones ni dependencias nuevas, y sin cambios en la API.

## Technical Context

**Language/Version**: TypeScript (Next.js 16, Node 24 en Vercel)

**Primary Dependencies**: `fetch` global de Node (undici). Ninguna nueva.

**Storage**: ninguno.

**Testing**: Vitest (`apps/console/src/lib/__tests__/backend-resilience.test.ts`, nuevo; `session-retry.test.ts`, sin cambios y en verde).

**Target Platform**: Vercel Fluid compute, `iad1`.

**Constraints**:
- La API consume cada `jti` la primera vez (`core/console_auth.py`, `_verify_bearer`).
- Hay escrituras legítimamente largas (el constructor), así que las escrituras no llevan plazo propio.

## Decisiones

- **D1. Qué es «no llegó a salir».** Son los códigos que undici pone en `cause`
  cuando la conexión no se abrió. `ECONNRESET` no está, porque puede pasar después
  de enviar la petición. Una escritura solo se repite si es seguro que no llegó.
- **D2. Plazo de lectura: 15 s por intento.** Entre el 2026-11-03 y el 16, la API
  de prod respondió todo en 10,3 s como mucho (máximo diario del ALB), con un p99
  por debajo de 0,33 s. Las lecturas que llaman a terceros (conectores,
  integraciones, uso) son GET normales, sin esperas largas.
- **D3. Un solo reintento.** Más intentos multiplicarían las llamadas justo cuando
  la red está mal. Con uno, una pantalla tarda como mucho unos 30 s en una
  lectura perdida.
- **D4. `webhooks.auphere.com` como provisional.**
  - Es solo DNS, va al mismo ALB y su certificado ya está en el listener (`extra_certificate_arns` en `prod.tfvars`). El listener HTTPS reenvía todo sin reglas de host, y el ALB no tiene WAF.
  - La API no depende del host ni de cabeceras de Cloudflare: la consola de staging habla así con su API desde siempre.
  - Las otras apps (panel de admin, móvil, escritorio, widget) y los webhooks de Meta no cambian.
  - El definitivo es un host propio, fuera de alcance.

## Constitution Check

| Principio | Cumple | Cómo |
|---|---|---|
| I. Aislamiento | Sí | No cambia el principal ni la verificación: cada intento acuña un token del mismo principal, que dura 60 s, y la API vuelve a comprobar la membresía. Ninguna garantía tocada. |
| II. Corte por superficie | Sí | Superficie 0: la consola ya existe y no se abre ninguna. |
| III. Lo leído es dato | No aplica | No hay entrada de terceros ni del modelo. |
| IV. Acción consecuente con humano | Sí | Una escritura nunca se repite si pudo haberse hecho (2.3). |
| V. La pantalla no miente | Sí | Si el segundo intento falla, el error llega a la pantalla como hoy (2.6). Lo que cambia es que un fallo pasajero ya no se muestra como fallo. |
| VI. Por API | Sí | Todo va por la API, como hoy. |
| VII. Test primero | Sí | `backend-resilience.test.ts` se escribió antes: 7 pruebas en rojo, que pasaron a verde con el arreglo. |
| VIII. Licencias | No aplica | No hay dependencias nuevas. |
| IX. La KB es dueña del porqué | Sí | `bugs/2026-11-17-consola-lenta-por-cloudflare`. |

## Verificación

- `apps/console`:
  - `vitest run`: 254 ficheros, 2278 pruebas en verde.
  - `tsc --noEmit`, `eslint --max-warnings 0`, `check-no-env-leaks` y `next build` (con el entorno de la tubería): en verde.
- **Prod, tras el cambio de `NEXUS_BACKEND_URL`:** CE-2 medido el 2026-11-17, en tanda alternada con staging. Prod dio p50 0,34 s, p90 0,84 s y máximo 1,59 s; staging, p50 0,47 s, p90 0,71 s y máximo 1,24 s. Sin errores en Vercel durante 20 minutos.
