# Research: Diagnóstico IA de Amacrux (009)

Fase 0. Todas las incógnitas del contexto técnico quedan resueltas aquí.

## D1 — Wizard de tarjetas en lugar de chat libre
- **Decisión**: wizard visual por pasos con respuestas estructuradas.
- **Razón**: fiabilidad en evento (ruido, prisa, conexión móvil), cero latencia y
  coste de modelo, resultados deterministas y testeables, tiempo acotado.
- **Alternativas**: chat guiado con tarjetas (más "agente", más complejidad de
  estado y de copy sin ganar información); formulario largo (parece encuesta).

## D2 — Next.js 16 App Router, no Vite
- **Decisión**: Next.js 16 (misma versión que `apps/console`).
- **Razón**: el envío de leads necesita ejecutar en servidor sin exponer la clave
  de Resend (Req. 9.2); Route Handlers lo resuelven sin backend aparte. Mismo
  stack que el resto del monorepo y despliegue conocido en Vercel.
- **Alternativas**: Vite SPA + función serverless separada (dos despliegues);
  reutilizar `apps/console` (privada, `noindex`, CSP y auth propios).

## D3 — Workspace pnpm propio, sin `@nexus/ui`
- **Decisión**: `apps/amacrux-event/pnpm-workspace.yaml` con `packages: ["."]`,
  lockfile propio, tokens y componentes propios.
- **Razón**: no tocar el lockfile ni el CI raíz a dos días del evento; la marca
  es de Amacrux (no los verdes de Auphere); `@nexus/ui` tiene botones de 32 px y
  reglas de lint (radios `sm|md`, sin colores crudos) pensadas para una consola
  densa, no para una landing táctil. Migrable a repo propio copiando la carpeta.
- **Alternativas**: entrar en el workspace raíz con `@nexus/ui` (hereda marca y
  lint); ruta en `auphere-agency` (marca Auphere, otro repo).

## D4 — Tailwind 4 CSS-first con tokens propios
- **Decisión**: `@theme` en `src/styles/tokens.css` con la paleta del manual
  (`#01103f`, `#5bdfd2`, `#39383b`, blanco) y variantes derivadas; dark mode por
  `prefers-color-scheme` y `data-theme` opcional.
- **Razón**: patrón ya usado en el repo (sin `tailwind.config`), tokens
  sustituibles en un fichero (Req. 13.1).
- **Alternativas**: CSS Modules puros (más código para estados/responsive).

## D5 — Tipografías: Outfit + Inter vía `next/font/google`
- **Decisión**: display Outfit (sustituta de Agrandir), cuerpo Inter (sustituta
  de SF Pro), ambas OFL, autoalojadas por `next/font` (sin petición a Google en
  runtime).
- **Razón**: Agrandir y SF Pro no tienen licencia web libre; Outfit comparte el
  carácter geométrico y amable; Inter es la sustituta estándar de SF.
  `TODO_COMERCIAL: licenciar Agrandir si Amacrux quiere fidelidad total`.
- **Alternativas**: Unbounded/Manrope (más "display" pero más lejos de Agrandir).

## D6 — Motor determinista por reglas con interfaz de proveedor
- **Decisión**: `RecommendationProvider` con `RulesProvider`; `validateResult()`
  común. Catálogo en TypeScript tipado (no JSON) para que el compilador
  verifique enums.
- **Razón**: Req. 5; permite enchufar un `AiProvider` después sin tocar UI.
- **Alternativas**: llamada a modelo en runtime (coste, latencia, riesgo de
  invenciones en un evento).

## D7 — Entrega de leads: Resend desde Route Handler + modo demo
- **Decisión**: `POST /api/leads` con Zod, honeypot, rate limit en memoria por
  IP (5/10 min), idempotencia por clave de sesión (Map en memoria con TTL),
  Resend si hay `RESEND_API_KEY`; si no, `{ok:true, delivered:false}`.
- **Razón**: patrón probado en `auphere-agency/src/app/api/partner-application/route.ts`;
  Resend ya es el proveedor de correo del repo (`apps/api/.../email.py`).
- **Límite conocido**: rate limit e idempotencia en memoria no sobreviven a
  instancias serverless distintas; suficiente para el volumen del evento y
  documentado en `CONFIG.md`. El cliente además bloquea el doble envío.
- **Alternativas**: webhook n8n (flujo no preparado); solo local (datos se
  quedan en el móvil).

## D8 — Persistencia temporal en `sessionStorage`
- **Decisión**: clave `amacrux-diagnostico:v1`, valor validado con
  `StoredSessionSchema`; fallback a memoria si el acceso lanza.
- **Razón**: Req. 4; se borra al cerrar la pestaña (privacidad); el lead nunca
  se guarda.
- **Alternativas**: `localStorage` (persistiría entre visitantes del mismo
  móvil); estado en URL (expone respuestas, rompe con parámetros UTM).

## D9 — Analítica desacoplada
- **Decisión**: `track(name, props)` → adaptador por `NEXT_PUBLIC_ANALYTICS`
  (`noop` por defecto, `console` en desarrollo, `plausible` opcional con script
  externo cargado solo si está configurado).
- **Razón**: Req. 11; el repo no tiene proveedor; Plausible es el que usa
  `auphere-agency`.

## D10 — Rutas y campaña
- **Decisión**: `/` y `/eventos/[slug]` renderizan la misma bienvenida; la
  campaña y los UTM se leen en cliente y se guardan en la sesión (sin PII).
  `/diagnostico` mantiene el paso en estado interno, no en la URL.
- **Razón**: Req. 12 y 10.3.

## D11 — Rendimiento y carga
- **Decisión**: páginas estáticas (bienvenida, privacidad) y wizard como client
  component único con `dynamic` no necesario; sin librerías de animación;
  imágenes de marca PNG optimizadas por `next/image` con tamaños fijos; sin
  fuentes externas en runtime.
- **Razón**: objetivo < 3 s en 4G y < 120 kB de JS inicial.

## D12 — Puerto y nombre
- **Decisión**: `amacrux-event`, `next dev -p 3120` (console usa 3110, admin 3000).
