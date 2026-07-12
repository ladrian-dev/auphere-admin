# Guía de integración para partners — Auphere Embed

> Cómo un partner SaaS integra Auphere en su plataforma para que **cada
> negocio (cliente final) del partner** tenga su propio agente de WhatsApp
> con sus datos aislados, conecte su número self-serve y envíe campañas
> (broadcasts) de plantillas desde la vista de su negocio.
>
> Audiencia: el equipo de desarrollo del partner + el operador Auphere
> que da de alta al partner. Arquitectura de referencia: ADR-028.

---

## 1. Modelo mental

| Concepto del partner | Concepto en Auphere |
|---|---|
| Partner (tu plataforma SaaS) | `partner` con secret API key (`ak_live_…`) |
| Negocio / cliente final | `tenant` aislado (RLS), referenciado SOLO por **tu** id (`external_client_ref`) |
| WhatsApp del negocio | Canal Meta Cloud API propio del tenant (WABA del negocio) |
| Agente del negocio | `agent_config` clonado del **blueprint** del partner (seed template) |
| Recordatorios masivos | `broadcast` de plantilla HSM a N destinatarios |

Reglas de oro:

1. **La secret key nunca sale de tu backend.** El browser solo ve *session
   tokens* efímeros (JWT, 15 min) scoped a UN negocio.
2. **Nunca conoces nuestros `tenant_id`.** Hablas con tu propio
   `external_client_ref`; nosotros mapeamos.
3. **Los destinatarios y variables los mandas tú.** Tu CRM es la fuente de
   verdad; el widget solo previsualiza y dispara.

## 2. Requisitos previos

**Del partner:**
- Backend server-to-server capaz de guardar la secret key (env/secret
  manager, jamás en el bundle del frontend).
- Frontend web (React o vanilla) donde montar `@auphere/embed`.
- Un id estable por negocio (`external_client_ref`) — UUID recomendado.
- Los orígenes (URLs) desde donde se embebe el widget (para CORS/CSP).

**De cada negocio que se conecta:**
- Acceso a su **Meta Business** (el login de Meta lo completa el dueño o
  quien administre su cuenta — es el único paso humano del flujo).
- Un número de teléfono para WhatsApp Business (nuevo o migrable a Cloud
  API).

**Del operador Auphere (una sola vez por partner):**
1. Crear el partner en el admin (`/partners` → Nuevo): nombre, slug,
   email de contacto.
2. Configurar el **blueprint** (PATCH del partner):
   - `default_seed_template` — vertical del agente (ej. `cobranza_v1`).
   - `default_connector_slug` — connector `api_key` que se instala con
     las credenciales que el partner envía al provisionar (ej.
     `amigable_cobro`). Opcional.
   - `auto_activate` — si el tenant pasa a ACTIVE solo al completar el
     signup de WhatsApp (default `true`).
3. Emitir la **API key** con los `allowed_origins` del partner. El
   plaintext se muestra UNA vez — entregarlo por canal seguro.
4. Ajustar límites si aplica: `broadcast_recipient_cap` (default 250),
   rate limits de mint/embed.

## 3. Contrato de API (backend del partner)

Base: `https://api.auphere.com` (prod). Auth: `Authorization: Bearer ak_live_…`.

### 3.1 Provisionar un negocio — al crearlo en tu admin

`POST /v1/partners/clients` — **idempotente** por `external_client_ref`.

```json
{
  "external_client_ref": "<tu-uuid-del-negocio>",
  "name": "Bodegón El Ávila",
  "timezone": "America/Caracas",
  "agent": {
    "placeholders": {
      "agent.name": "Mouna",
      "policies.admin_access.admin_phones": ["+584241234567"]
    }
  },
  "connector": {
    "credentials": { "entity_id": "<uuid>", "token": "<bearer>" },
    "meta": { "business_uuid": "<uuid-del-negocio-en-tu-api>" }
  }
}
```

Respuesta:

```json
{
  "external_client_ref": "…",
  "status": "provisioned",
  "whatsapp": { "status": "not_connected", "display_phone_number": null },
  "agent": { "status": "provisioned" },
  "connector_connected": true
}
```

Qué pasa por dentro: se crea el tenant aislado, se **clona el agente**
del blueprint (prompt + tools + policies, con tus placeholders) ya
promovido a v1, y se instala el connector con las credenciales cifradas.
El negocio queda en `provisioning` — su agente NO responde hasta que
conecte WhatsApp.

- `agent.placeholders` usa las claves del seed template (te las damos por
  vertical). `tenant.name`/`tenant.timezone` salen del propio negocio.
- Re-llamar con el mismo ref **nunca re-crea el agente** (respeta
  personalizaciones), pero **sí rota** las credenciales del connector.
- Errores: `422` con el placeholder/credencial que falta.

### 3.2 Mintear session token — cada vez que tu frontend lo pida

`POST /v1/widget-sessions`

```json
{ "external_client_ref": "<tu-uuid-del-negocio>" }
```

→ `{ "session_token": "eyJ…", "expires_in": 900, "whatsapp": { "status": "…" } }`

Expón esto en TU backend como un endpoint autenticado para tu frontend
(ej. `POST /api/auphere/session` que valida la sesión de tu usuario y
resuelve QUÉ negocio le corresponde). `whatsapp.status` te dice
server-side si renderizar el botón de campañas.

## 4. Frontend del partner (`@auphere/embed`)

```bash
npm install @auphere/embed
```

```tsx
import { createAuphere } from "@auphere/embed";
import { AuphereBroadcastButton } from "@auphere/embed/react";

const auphere = createAuphere({
  partnerSlug: "<tu-slug>",
  fetchSession: async () => {
    const r = await fetch("/api/auphere/session", { method: "POST" });
    return r.json(); // ← tu backend mintea con la secret key
  },
  appearance: { colorPrimary: "#2CC295", radius: "12px" },
  locale: "es",
});

// 1) Conectar WhatsApp (ajustes/onboarding del negocio, o desde tu admin)
await auphere.connectWhatsApp({
  onConnected: ({ displayPhoneNumber }) => refreshUI(),
  onExit: () => {},
});

// 2) Botón de campañas (solo se muestra si el negocio está conectado)
<AuphereBroadcastButton
  auphere={auphere}
  recipients={clientesDelNegocio.map((c) => ({
    phone: c.telefonoE164, // +58424…
    variables: { cliente: c.nombre, saldo_pendiente: c.saldo, fecha: c.vence },
  }))}
>
  Enviar recordatorios
</AuphereBroadcastButton>
```

Notas:
- El widget corre en un iframe de `embed.auphere.com` — tus scripts no
  ven credenciales y nosotros deployamos mejoras sin que actualices npm.
- Las claves de `variables` deben coincidir con los *named parameters*
  de la plantilla aprobada (posicionales `{{1}}` no están soportados).
- `connectWhatsApp()` abre el popup de Meta: quien lo complete necesita
  acceso al Meta Business **del negocio**. Tu admin puede lanzar el
  flujo en nombre del negocio si tiene ese acceso delegado.

## 5. El flujo completo de un negocio nuevo

1. **Tu admin crea el negocio** → tu backend llama
   `POST /v1/partners/clients` (con placeholders + credenciales) →
   agente clonado, tenant en `provisioning`.
2. **Conectar WhatsApp** → tu UI llama `auphere.connectWhatsApp()` → el
   dueño autoriza en Meta → registramos el número, suscribimos el
   webhook y guardamos las credenciales cifradas → si `auto_activate`,
   el tenant pasa a **ACTIVE** y el agente empieza a responder.
3. **Broadcasts** → el botón de campañas aparece solo con WhatsApp
   conectado; tu app pasa la audiencia; el widget muestra plantillas
   aprobadas + preview y dispara. Respetamos opt-outs, ventana de 24h y
   el cap por envío del partner.

## 6. Plantillas HSM

Cada negocio envía desde SU propia WABA, así que las plantillas se
aprueban **por negocio** en Meta. Hoy la creación del set inicial de
plantillas es asistida por el operador Auphere tras el signup (la
provisión automática de un catálogo por partner está en el roadmap).
El widget solo ofrece plantillas ya APPROVED.

## 7. Métricas y facturación

El uso queda atribuido al partner vía el mapeo negocio→tenant:
`GET /admin/partners/{id}/usage` (panel Auphere) agrega por cliente:
estado, WhatsApp conectado, versión/seed del agente, broadcasts,
destinatarios, mensajes in/out y costo de modelo — la base de la
facturación por negocio activo.

## 8. Seguridad (resumen para tu equipo)

- Secret key: solo backend; rotación con ventana de gracia y revocación
  inmediata desde el panel Auphere. Storage SHA-256 (no reversible).
- Session token: 15 min, scoped a un negocio, muere si se revoca la key,
  se suspende el partner o se elimina el mapeo (re-check por request).
- Aislamiento: el `tenant_id` se elige solo en el mint (gateado por el
  mapeo del partner) y el surface del widget lo lee solo del JWT firmado
  → un negocio no puede ver datos de otro, ni un partner los de otro.
- CORS/CSP: solo los `allowed_origins` de tu key pueden embeber el
  widget; todo lo demás recibe `frame-ancestors 'none'`.

## 9. Troubleshooting

| Síntoma | Causa probable | Acción |
|---|---|---|
| `401` al mintear | Key revocada/expirada o checksum inválido | Verificar la key; pedir rotación |
| `403 Session token lacks widget:connect` | Token minteado con scopes viejos | Re-mintear (los scopes van en el JWT) |
| `422` al provisionar | Placeholder del seed sin valor / credenciales vacías | El detail dice exactamente qué falta |
| Widget no monta / iframe en blanco | Origin no está en `allowed_origins` | Agregar el origin exacto (esquema+host+puerto) en el panel |
| Meta rechaza el OAuth code | Code expirado o reusado | Cerrar y reintentar el flujo |
| `409` al conectar número | El número ya está mapeado a otro tenant | Contactar al operador Auphere (offboard previo) |
| Broadcast `413` | Audiencia > cap del partner | Trocear el envío o pedir aumento de cap |
| Plantilla no aparece | No está APPROVED en la WABA del negocio | Esperar aprobación de Meta / revisar en el panel |

## 10. Checklist de go-live de un partner

- [ ] Partner creado + blueprint configurado (seed, connector, auto_activate).
- [ ] API key emitida con `allowed_origins` de producción.
- [ ] Endpoint de sesión implementado en el backend del partner.
- [ ] Provisión llamada desde el alta de negocios del partner.
- [ ] `@auphere/embed` montado (signup + botón de campañas).
- [ ] Negocio piloto conectado E2E (signup → activo → broadcast de prueba).
- [ ] `embed.auphere.com` en los dominios permitidos de la app de Meta.
- [ ] Plantillas iniciales aprobadas en la WABA del piloto.
