# Configuración

Todas las variables están en `.env.example`. Ninguna clave se expone al navegador: solo las que empiezan por `NEXT_PUBLIC_` llegan al cliente, y ninguna de ellas es secreta.

| Variable | Dónde | Valor | Efecto |
|---|---|---|---|
| `NEXT_PUBLIC_SITE_URL` | cliente | `https://<dominio>` | Metadata y Open Graph |
| `NEXT_PUBLIC_DEMO_MODE` | cliente y servidor | `true` / `false` | `true`: la entrega de leads se simula y la confirmación lo dice. Se activa también si falta `RESEND_API_KEY` |
| `NEXT_PUBLIC_ANALYTICS` | cliente | `noop` (defecto) / `console` / `plausible` | Adaptador de analítica. Sin proveedor no se carga ningún script |
| `NEXT_PUBLIC_PLAUSIBLE_DOMAIN` | cliente | dominio | Solo con `plausible` |
| `SUPABASE_URL` | servidor | `https://<ref>.supabase.co` | Base de leads (registro consultable) |
| `SUPABASE_SERVICE_ROLE_KEY` | servidor | service role key | Escritura en la base. Nunca en el cliente |
| `LEADS_WEBHOOK_URL` | servidor | URL https del webhook de n8n | Copia de cada lead a Google Sheets (fila plana). Best-effort |
| `LEADS_WEBHOOK_SECRET` | servidor | texto aleatorio | Cabecera `X-Leads-Secret` que n8n comprueba |
| `RESEND_API_KEY` | servidor | clave de Resend | Aviso por correo de cada lead |
| `LEADS_TO` | servidor | `amacrux@…, auphere@…` | Destinos del correo, separados por comas. `TODO_COMERCIAL: validar con Amacrux` |
| `LEADS_FROM` | servidor | `Nombre <correo@dominio-verificado>` | Remitente verificado en Resend |

## Dónde se guardan los leads: Supabase
1. Crear un proyecto en [supabase.com](https://supabase.com) (plan gratuito; región `us-east-1`, la más cercana a Venezuela).
2. SQL Editor → pegar y ejecutar `supabase/migrations/0001_leads.sql`. Crea la tabla `leads` (con RLS y sin políticas: solo la service role accede) y la vista `leads_panel`.
3. Project Settings → API: copiar **Project URL** → `SUPABASE_URL` y **service_role key** → `SUPABASE_SERVICE_ROLE_KEY`. Ponerlas solo en Vercel (Production) o en `.env.local`; nunca en el cliente ni en git.
4. Consultar: Table Editor → `leads_panel` (columnas legibles: contacto, empresa, rol, sector, fricciones, objetivos, nivel, recomendaciones, campaña). Filtros y exportación CSV desde el propio panel. La tabla `leads` guarda además las respuestas con valores internos, el segmento y si el correo salió.
5. Cada envío guarda **una** fila (la `idempotency_key` es única: un reintento no duplica). Se guardan solo leads enviados con consentimiento; los abandonos no se registran.

## Copia en Google Sheets (vía n8n)
El servidor envía cada lead (tras guardarlo y avisar por correo) como JSON plano al webhook de n8n: `fecha, nombre, empresa, correo, telefono, rol, sector, tamano_equipo, clientes, como_trabajan, uso_ia, datos, fricciones, objetivos, urgencia, apoyo_tecnico, inversion, puntuacion, nivel, etiqueta_interna, recomendacion_1..3, campana, consentimiento_contacto, modo, idempotency_key`. Flujo listo para importar: `docs/n8n-leads-sheet.json` (Webhook → comprobar `X-Leads-Secret` → aplanar → **dos** nodos Google Sheets *Append row*, hoja de Auphere y hoja de Amacrux → responder). Pasos:
1. Crear las dos hojas de Google (una por organización) con una pestaña llamada `Leads` y, en la fila 1, las cabeceras de `docs/leads-sheet-headers.csv` (27 columnas, en ese orden).
2. En n8n de Amacrux: Workflows → Import from file → `n8n-leads-sheet.json`. En cada nodo Google Sheets, elegir la credencial OAuth de la cuenta dueña de esa hoja y pegar la URL de la hoja. En el nodo `¿Secreto válido?`, sustituir `CAMBIA-ESTE-SECRETO` por un texto aleatorio.
3. Activar el flujo y copiar la URL de producción del webhook (termina en `/webhook/amacrux-leads`).
4. En Vercel: `LEADS_WEBHOOK_URL=<esa URL>` y `LEADS_WEBHOOK_SECRET=<el mismo secreto>`; redesplegar.
Si el webhook falla, el lead ya está en Supabase y en el correo; la respuesta al visitante no cambia (`sheet:false` en el JSON y un aviso en los logs).

## Modos de entrega (`GET /api/health` los muestra)
- **demo**: `NEXT_PUBLIC_DEMO_MODE=true`, o sin Supabase ni Resend configurados. `POST /api/leads` responde `{ok:true, stored:false, delivered:false, mode:"demo"}` y solo registra un aviso sin datos personales.
- **live**: hay base de leads y/o correo. Orden: primero se guarda en Supabase, después se envía el correo (a todas las direcciones de `LEADS_TO`), y se anota en la fila si el correo salió. Si al menos un destino funciona → `200 {stored, delivered}`; si fallan todos los configurados → `502` (el formulario ofrece reintentar).
- **misconfigured**: Resend con clave pero sin destino o remitente **y** sin Supabase → `503`.

## Protecciones del endpoint
- Validación Zod estricta (campos desconocidos → 400).
- Honeypot `fax`: si llega relleno, responde éxito y no envía.
- Rate limit: 5 envíos / 10 min por IP. Idempotencia por `idempotencyKey` (uuid por sesión de formulario) durante 10 min.
- **Límite conocido**: rate limit e idempotencia viven en memoria del proceso. En serverless con varias instancias pueden no compartirse. Para el volumen del evento es suficiente; el cliente además bloquea el doble envío.

## Logs
El servidor nunca registra nombre, empresa, correo ni teléfono: solo `campaign`, `range`, `interest` y el resultado (`delivered`, `demo`, `invalid`, `rate_limited`, …).

## Borrar o anonimizar leads
Los leads no se guardan en ningún sistema propio: viven en el buzón `LEADS_TO` (y en el registro de envíos de Resend, que conserva metadatos y contenido según su política). Para atender una solicitud de borrado: eliminar el correo del buzón y, en el panel de Resend, borrar el email por su `id` (aparece en la respuesta del endpoint y en los logs de Resend). Los datos en el navegador del visitante se borran al cerrar la pestaña o con "Reiniciar".

## Cambiar el destino de los leads
`src/lib/leads/repository.ts` define `LeadRepository`. Para un webhook o CRM, implementa otra clase (o cambia el Route Handler) sin tocar el formulario.
