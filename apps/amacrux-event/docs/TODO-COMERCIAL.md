# TODO comerciales pendientes de validación por Amacrux

Cada punto es un texto o decisión que Amacrux debe validar antes o después del evento. En el código, cada uno está marcado con un comentario `TODO_COMERCIAL` (buscar con `grep -rn TODO_COMERCIAL src`).

## Textos visibles

| Dónde | Qué validar |
|---|---|
| `src/components/welcome/Welcome.tsx` | Frase de propuesta de valor al pie de la bienvenida ("Amacrux convierte problemas reales…"). |
| `src/domain/copy.ts` | Texto del CTA único "Solicita una DEMO" (decidido por el usuario) y del texto de apoyo "Podemos ayudarte…". |
| `src/domain/opportunities.ts` | En las 24 oportunidades: `amacruxFit` (cómo empezaría Amacrux), `commercialCta` y las herramientas nombradas en `relatedTools` (incluye Amigable Cobro y Amigable Venta en tres de ellas). |
| `src/components/lead/LeadConfirmation.tsx` | Plazo de respuesta prometido ("te escribirán en los próximos días"). |
| `src/components/lead/LeadForm.tsx` | Vía alternativa de contacto cuando falla el envío (correo o WhatsApp de Amacrux). |
| `src/app/privacidad/page.tsx` | Responsable del tratamiento, dirección de contacto para derechos y base legal. |

| `src/components/ui/PartnerBanner.tsx` | Fórmula exacta del sello "Partner oficial de Auphere" (¿partner oficial, partner tecnológico, embedded partner?). |

## Configuración y marca

- Correo de Auphere que recibirá copia de cada lead (`LEADS_TO` admite varias direcciones separadas por comas).

- Correo destino de leads (`LEADS_TO`) y remitente verificado en Resend (`LEADS_FROM`). Ver `docs/CONFIG.md`.
- Licencia web de la tipografía Agrandir (hoy Outfit) y de SF Pro (hoy Inter). Ver `src/styles/tokens.css` y `docs/DECISIONS.md` D5.
- Exportar el logotipo en SVG desde `logo.ai` (hoy PNG @3x en `public/brand/`).
- Tono: el manual pide "mensajes disruptivos y lenguaje venezolano"; el brief pide tono consultivo y claro. Hoy: español neutro. Decidir cuánto acento local.
- Uso de las mascotas 3D del manual (no incluidas en esta versión).
- Identificador de campaña del evento para la URL del QR (hoy `ia-empresas-2026` como ejemplo).
