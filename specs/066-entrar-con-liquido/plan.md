# Implementation Plan: Entrar con el líquido vivo

**Branch**: `066-entrar-con-liquido` | **Date**: 2026-11-20 | **Spec**: [spec.md](spec.md)

## Summary

Es un cambio solo de la consola, dentro de `apps/console/src/app/(auth)` y un componente nuevo. No toca la API, la base de datos ni `@nexus/ui`.

1. **El marco partido** (`(auth)/layout.tsx`): dos columnas desde 900 px y una franja por debajo. El idioma sale de `getT()`, el logo es `BrandLockup` y «Beta» es neutro. El layout no se vuelve a montar al navegar entre `/login`, `/forgot` y `/reset/*`, y por eso el líquido sigue (R1.3).
2. **`components/auth/liquid-backdrop.tsx`** (cliente):
   - el shader de la demo portado tal cual: WebGL 1, un quad, ruido fbm con deformación y los seis verdes de Auphere;
   - puntero con suavizado, hasta cuatro ondas y el dedo invisible;
   - `ResizeObserver` a media resolución con DPR ≤ 2;
   - `IntersectionObserver` y `visibilitychange` para parar;
   - `matchMedia("(prefers-reduced-motion: reduce)")` para pintar un cuadro quieto;
   - limpieza al desmontar con `WEBGL_lose_context`.

   La lógica pura (avance del puntero, dedo invisible, cola de ondas, tamaño del lienzo) va en `liquid-backdrop-model.ts` para probarla sin WebGL.
3. **Carga diferida**: `next/dynamic(..., { ssr: false })` desde un envoltorio cliente. El servidor pinta el fondo de respaldo (CSS) y el lienzo aparece encima con un fundido de opacidad (R2.8). Sin cambio de tamaño, así que no hay desplazamiento de diseño.
4. **Entrar**: botón de mostrar/ocultar en el campo de contraseña y separador «o». El correo pasa a Recuperar por `sessionStorage` (clave `nexus-console.forgot-email`) al pulsar el enlace.
5. **Recuperar**: el estado «enviado» repite el correo escrito y añade «Cambiar» y «Reenviar el enlace» con una cuenta atrás de 30 s. Usa la misma `requestPasswordResetAction`, que siempre contesta igual.
6. **Contraseña nueva**: los campos nueva y repetir, las reglas en vivo y mostrar/ocultar compartido. Se mantienen el aviso previo, D-5 y el enlace muerto.
7. **Textos**: un carril nuevo `i18n/lanes/auth-entrar.ts` con ES/EN, añadido a `messages`.
8. **Estilos**: `app/(auth)/auth.css`, importado desde el layout. Tiene las manchas de respaldo, los keyframes, el degradado del titular y reducir movimiento y transparencia. Todo lo demás va con utilidades de Tailwind.

## Technical Context

- **Language/Version**: TypeScript, Next.js 16, React 19 (`apps/console`).
- **Primary Dependencies**: `@nexus/ui` (`BrandLockup`, `Form`, `Input`, `Button`) y `lucide-react` (iconos `Eye`, `EyeOff`, `Check`, `Circle`). **Sin dependencias nuevas**: WebGL es una API del navegador.
- **Testing**:
  - vitest con jsdom: el modelo del líquido, el respaldo sin WebGL, reducir movimiento, mostrar/ocultar, el correo por `sessionStorage`, el estado «enviado» con la cuenta atrás y las reglas de contraseña;
  - Playwright con axe en `e2e/auth-entrar.e2e.ts`, con una API simulada propia (`e2e/auth-mock.mjs`, `e2e/auth-entrar.config.ts`).
- **Target**: navegadores de escritorio y móvil. A 320 px no hay desplazamiento horizontal (WCAG 1.4.10).

## Constitution Check

| Principio | Cómo se cumple |
|---|---|
| I. Aislamiento | No toca ninguna frontera: páginas públicas sin sesión ni datos de tenant. Sin test de aislamiento nuevo. Se protege el oráculo de la 011 con un test (T009). |
| II. Superficie | `0`, ya abierta. No se abre ninguna. |
| III. Lo leído es dato | No aplica: no hay agente ni contenido leído. |
| IV. Acción consecuente | No hay acciones nuevas. Restablecer mantiene su aviso previo. |
| V. La pantalla no miente | Respaldo sin WebGL, «enviado» que no promete más de lo que sabe, reglas que se ven antes de fallar, D-5 intacta. |
| VI. Por API | No aplica. |
| VII. Test primero | Cada requisito tiene su test (tasks.md). Rojo antes de verde. |
| VIII. Licencias | Ninguna dependencia nueva. El shader es propio (de la demo de la consola). |
| IX. KB ↔ repo | Nota `nexus/UX-CONSOLA-PARTNERS-2026-11-20` en la KB, que enlaza a esta carpeta. |

## Rendimiento

- Unos 7 KB de JS más, solo en las páginas de `(auth)` y cargados después de pintar.
- A media resolución, un portátil a 1440 px pinta unos 360×400 píxeles por cuadro con cuatro octavas de ruido. Cuando la pestaña no se ve, el coste es cero.
- **Riesgo**: GPUs integradas viejas. Mitigación: DPR ≤ 2 y media resolución. Si un cuadro tarda más de 50 ms durante 30 cuadros seguidos, se queda en un cuadro quieto (como con reducir movimiento).
