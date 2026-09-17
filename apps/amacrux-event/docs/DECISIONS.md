# Decisiones técnicas — Diagnóstico IA de Amacrux

Fuente de verdad del *cómo*. El *porqué* del producto vive en la KB
(`Auphere/partnerships/amacrux-diagnostico-evento`) y la spec en
`specs/009-diagnostico-evento-amacrux/`.

| # | Decisión | Razón | Alternativa descartada |
|---|---|---|---|
| D1 | Wizard de tarjetas, no chat libre | Fiabilidad en evento, cero latencia, resultados reproducibles | Chat guiado (más estado, sin más información) |
| D2 | Next.js 16 App Router | El envío de leads necesita servidor sin exponer la clave; mismo stack que el monorepo; Vercel | Vite + función aparte (dos despliegues) |
| D3 | Workspace pnpm propio, sin `@nexus/ui` | No tocar lockfile/CI raíz; marca Amacrux; botones táctiles grandes | Entrar al workspace raíz |
| D4 | Tailwind 4 CSS-first con `src/styles/tokens.css` | Patrón del repo; tokens sustituibles en un fichero | CSS Modules |
| D5 | Fuentes Outfit + Inter (OFL) vía `next/font` | Agrandir y SF Pro (manual de marca) no tienen licencia web libre. `TODO_COMERCIAL: licenciar Agrandir` | Unbounded/Manrope |
| D6 | Motor determinista con `RecommendationProvider` + `validateResult` | Coste cero, consistencia; IA enchufable después con validación | Modelo en runtime |
| D7 | Leads por Resend desde `/api/leads` + modo demo | Patrón probado en `auphere-agency`; Resend ya es el proveedor del repo | Webhook n8n; solo local |
| D8 | `sessionStorage` versionado, lead nunca persistido | Se borra al cerrar; privacidad | `localStorage`; estado en URL |
| D9 | Analítica tras `track()` con adaptador `noop/console/plausible` | El repo no tiene proveedor; sin PII | Acoplar a un SDK |
| D10 | `/` y `/eventos/[slug]`; paso del wizard fuera de la URL | URL corta para el QR; sin PII en URLs | Paso en query string |
| D11 | Sin librerías de animación; imágenes con tamaño fijo | < 3 s en 4G; < 120 kB de JS | GSAP/Framer |
| D12 | Puerto 3120, paquete `amacrux-event` | Console usa 3110, admin 3000 | — |
| D13 | `src/lib/env.server.ts` sin el paquete `server-only` | `server-only` lanza al importarse en Vitest; el script `check-no-env-leaks` y el test de no acoplamiento cubren la misma garantía | `server-only` con mocks en cada test |

| D15 | Wordmark cromado de Amacrux en la cabecera sobre fondos oscuros (home y tema oscuro): generado con Higgsfield (gpt_image_2_5 con el wordmark oficial como referencia + recorte de fondo) en `public/brand/wordmark-chrome.png`; en tema claro sigue el navy. El isotipo cromado se probó en el home y se retiró a petición del usuario (`isotipo-chrome.png` queda disponible). El sticker de partner no se muestra en la bienvenida | Petición del usuario | Wordmark plano blanco |
| D16 | Flujo v2: el formulario de contacto es la puerta al resultado (12 preguntas → contacto → resultado); quien revisa respuestas no lo repite | Decisión del usuario; riesgo aceptado de menor finalización frente al principio "valor antes que datos" del brief | Contacto opcional tras el resultado (v1) |
| D17 | Base de leads en Supabase (Postgres) escrita desde `/api/leads` por la API REST con la service role, sin SDK; tabla `leads` + vista `leads_panel` legible; solo leads con consentimiento | Consultable, exportable, gratuito para este volumen y sin nueva dependencia; se guarda primero y el correo es el aviso | Airtable, Sheets vía n8n (más frágil en el evento), solo correo |
| D18 | Cal.com descartado por el usuario; el botón y su variable se retiraron | — | — |
| D19 | **El correo es el único destino**, a `contacto+event@auphere.com`, y lleva toda la información que se habría almacenado, incluida una fila CSV de 40 columnas para pegar en una hoja. Supabase y el webhook quedan implementados y apagados | Decisión del usuario (2026-09-17): el equipo mapea a mano y no quiere una cuenta más que mantener para un evento | Supabase como registro consultable (D17), webhook a n8n |
| D20 | En producción, el modo demo exige la bandera explícita: sin destinos y sin `NEXT_PUBLIC_DEMO_MODE=true`, `/api/leads` responde `503` | Antes, una variable olvidada en Vercel hacía que el endpoint contestara `ok:true` y tirara el lead sin que nadie se enterara | Seguir cayendo en demo y confiar en revisar `/api/health` |
| D21 | Límite de envíos: 60 por IP / 10 min (era 5), y si la entrega falla el visitante puede ver su diagnóstico igualmente | En un evento la sala comparte la IP del wifi; con 5, a partir del sexto asistente nadie podía enviar **ni ver su resultado**, porque el formulario es la puerta (D16) | Mantener 5 y confiar en que el serverless reparta las instancias |
| D14 | Sticker holográfico 3D rectangular de Auphere generado con Higgsfield (gpt_image_2_5 con el logo real como referencia, recorte de fondo, upscale 4K) + texto "Partner oficial de" fuera del sticker; enlace a auphere.com | Decisión del usuario tras dos iteraciones (pin esmaltado y tarjeta plana). El logo se pasa como referencia para que el modelo no lo deforme. Web: 720 px (`public/brand/partner-sticker.png`); 4K y transparente en `kb/Auphere/brand/assets/` | Tarjeta plana CSS |

## Licencias (constitución §VIII)

| Paquete | Licencia | Párrafo que permite el uso como servicio |
|---|---|---|
| next, react, react-dom, zod, react-hook-form, @hookform/resolvers, resend, tailwindcss, @tailwindcss/postcss, vitest, vite, @vitejs/plugin-react, jsdom, @testing-library/react, @testing-library/jest-dom, @testing-library/user-event, eslint, eslint-config-next, @types/node, @types/react, @types/react-dom, server-only (no usado en runtime) | MIT | "Permission is hereby granted, free of charge, to any person obtaining a copy of this software […] to deal in the Software without restriction, including without limitation the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software" |
| typescript | Apache-2.0 | §2 "each Contributor hereby grants to You a perpetual, worldwide, non-exclusive, no-charge, royalty-free, irrevocable copyright license to reproduce, prepare Derivative Works of, publicly display, publicly perform, sublicense, and distribute the Work" |
| Fuentes Outfit e Inter (Google Fonts, autoalojadas por `next/font`) | SIL OFL 1.1 | "The OFL allows the licensed fonts to be used, studied, modified and redistributed freely as long as they are not sold by themselves" |

Ninguna dependencia AGPL, BSL, Elastic ni "Apache modificada".

## Límites conocidos

- Rate limit e idempotencia de `/api/leads` viven en memoria del proceso: en
  serverless pueden no compartirse entre instancias. Suficiente para el volumen
  del evento; el cliente además bloquea el doble envío.
- Los logotipos son PNG @3x (no hay SVG); pedir el vector a Amacrux.
