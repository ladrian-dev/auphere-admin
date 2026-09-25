# Contrato: API de leads

Mismo origen (sin CORS). JSON. Español en mensajes de usuario; códigos de error estables.

## `POST /api/leads`

**Request** (`Content-Type: application/json`), esquema `LeadSchema` (ver data-model.md):
```json
{
  "name": "Ana Pérez", "company": "Farmacia Central", "email": "ana@farmacia.com",
  "role": "Gerente", "phone": "+58 412 0000000",
  "interest": "automatizacion_operativa",
  "consentContact": true, "consentMarketing": false,
  "resultSnapshot": { "scoreTotal": 68, "range": "oportunidad_prioritaria", "leadTier": "caliente",
    "segment": { "profile": "decisor_negocio", "maturity": "inicial", "opportunityCategories": ["automatizacion_operativa"], "intent": "alta", "complexity": "piloto_baja" },
    "recommendationIds": ["clasificacion-solicitudes", "recordatorios-y-seguimiento", "asistente-interno-conocimiento"] },
  "campaign": "ia-empresas-2026", "utm": { "source": "qr", "medium": "evento" },
  "idempotencyKey": "3f6d…", "fax": ""
}
```

**Responses**
| HTTP | Body | Cuándo |
|---|---|---|
| 200 | `{ "ok": true, "stored": true, "delivered": true, "mode": "live", "id": "<resend id>" }` | guardado en Supabase y correo enviado |
| 200 | `{ "ok": true, "stored": true, "delivered": false, "mode": "live" }` | guardado; correo no configurado o fallido (fallo parcial registrado) |
| 200 | `{ "ok": true, "stored": false, "delivered": true, "mode": "live" }` | correo enviado; base no configurada o fallida |
| 200 | `{ "ok": true, "stored": false, "delivered": false, "mode": "demo" }` | `NEXT_PUBLIC_DEMO_MODE=true` o sin Supabase ni Resend |
| 200 | `{ "ok": true, "delivered": true, "duplicate": true }` | misma `idempotencyKey` ya procesada (ventana 10 min) |
| 200 | `{ "ok": true }` | honeypot relleno (respuesta indistinguible para bots; no se envía nada) |
| 400 | `{ "ok": false, "error": "invalid", "fields": { "email": "…" } }` | validación Zod |
| 429 | `{ "ok": false, "error": "rate_limited" }` | > 5 envíos / 10 min por IP |
| 502 | `{ "ok": false, "error": "delivery_failed" }` | fallaron todos los destinos configurados |
| 503 | `{ "ok": false, "error": "unavailable" }` | Resend a medias (falta `LEADS_TO`/`LEADS_FROM`) y sin Supabase |

## Copia a hoja de cálculo (webhook)
Si `LEADS_WEBHOOK_URL` está definido: `POST` JSON plano (ver `flattenLeadRow` en `src/lib/leads/store.ts`) con cabecera `X-Leads-Secret`. La respuesta añade `sheet: true|false`. Nunca cambia el código HTTP.

## Base de leads (Supabase)
Orden: insert en `public.leads` (REST, `Prefer: resolution=ignore-duplicates`) → correo → `PATCH email_delivered/email_id`. Esquema en `apps/amacrux-event/supabase/migrations/0001_leads.sql`; vista legible `leads_panel`.

Reglas: nunca se registra el cuerpo completo; los logs solo llevan `campaign`,
`range`, `interest` y el código de resultado. El cliente trata 5xx/red como
"reintentable" y 4xx como "corrige el formulario".

## Correo a Amacrux
- Para: todas las direcciones de `LEADS_TO` (separadas por comas: Amacrux y Auphere) · De: `LEADS_FROM` · Reply-To: email del lead.
- Asunto: `[Diagnóstico IA] <empresa> · <nivel> · <categoría top>`.
- Cuerpo (texto y HTML simple): contacto, consentimientos, campaña/UTM,
  respuestas resumidas (etiquetas legibles), puntuación total y desglose,
  etiqueta interna, 3 recomendaciones con confianza y primer paso, fecha/hora.

## `GET /api/health`
`200 { "status": "ok", "app": "amacrux-event", "mode": "demo" | "live" }`
