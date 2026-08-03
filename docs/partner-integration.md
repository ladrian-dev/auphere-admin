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

**El 422 es estricto a propósito.** Un agente solo se promueve si puede
trabajar el día uno, así que la provisión rechaza dos casos que antes
pasaban silenciosos:

- **Datos del negocio sin rellenar** — si algún valor del seed queda como
  `<<… pendiente>>`, el agente le dictaría ese literal a un admin como si
  fuera la cuenta bancaria real. El `detail` nombra cada pendiente.
- **Whitelist de admins vacía** — en verticales `admin_only` (como
  `cobranza_v1`) el agente solo responde a los teléfonos autorizados; sin
  ninguno, el número quedaría conectado y mudo. Manda al menos un teléfono
  E.164 con 7+ dígitos.

Placeholders obligatorios de `cobranza_v1`:

```
policies.admin_access.admin_phones          ["+584241234567", …]
policies.payment.pago_movil.banco           policies.payment.pago_movil.telefono
policies.payment.pago_movil.cedula          policies.payment.transferencia.banco
policies.payment.transferencia.numero_cuenta  policies.payment.transferencia.titular
policies.payment.transferencia.cedula_rif   policies.payment.binance.pay_id
```

(`agent.name` es opcional — por defecto "Sofía".)

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

### 3.3 Consultar el estado de un negocio

`GET /v1/partners/clients/{external_client_ref}`

```json
{
  "external_client_ref": "…", "name": "Bodegón El Ávila",
  "timezone": "America/Caracas", "status": "active",
  "whatsapp_connected": true, "display_phone_number": "+584241234567",
  "agent_configured": true, "agent_version": 1,
  "agent_seed_template": "cobranza_v1", "admins_count": 2,
  "ready": true, "missing": []
}
```

Esto es lo que tu UI consulta para decidir qué mostrar. `missing` enumera
lo que falta (`agent`, `whatsapp`, `admins`, `activation`) y `ready` es
true solo cuando el agente ya puede atender. **No uses `POST
/v1/partners/clients` para consultar estado**: es idempotente pero rota
las credenciales del connector en cada llamada.

### 3.4 Conectar el WhatsApp del negocio (sin operador de Auphere)

`GET /v1/partners/whatsapp/signup-config` devuelve `app_id`,
`coexistence_config_id`, `cloud_api_config_id` y `graph_api_version`: con
eso tu frontend abre Facebook Login for Business con la Meta App de
Auphere. **Usá el `coexistence_config_id`** — el negocio conserva su app
móvil de WhatsApp Business.

Con el `code` que devuelve Meta, tu backend cierra el flujo:

`POST /v1/partners/clients/{external_client_ref}/whatsapp/signup`

```json
{ "code": "<oauth code>", "waba_id": "<waba>", "phone_number_id": "<opcional>", "mode": "coexistence" }
```

→

```json
{
  "status": "connected", "display_phone_number": "+584241234567",
  "mode": "coexistence", "tenant_status": "active",
  "tenant_activated": true, "activation_blocked_reason": null
}
```

Esta llamada registra el número, suscribe el webhook, guarda las
credenciales cifradas **y activa al negocio** si tiene agente y tu
partner tiene `auto_activate`. Si `tenant_status` sigue en
`provisioning`, `activation_blocked_reason` dice por qué: `no_agent` (el
negocio no tiene agente — revisá la provisión) u `operator_review` (tu
partner no auto-activa; lo revisa Auphere).

El `code` es de un solo uso y expira rápido: mandalo apenas lo recibís y,
si Meta lo rechaza (`400`), reabrí el popup en vez de reintentar el mismo.

### 3.5 Administradores del negocio

`GET` / `PUT /v1/partners/clients/{external_client_ref}/admins`

```json
{ "admins": [
  { "phone": "+584241234567", "name": "Ana", "role": "full" },
  { "phone": "+584249990000", "name": "Luis", "role": "readonly" }
] }
```

El `PUT` **reemplaza** la lista completa y promueve una versión nueva del
agente (auditada y reversible). Solo esos teléfonos pueden hablar con el
agente; cualquier otro queda registrado pero sin respuesta ni acuse de
lectura. `readonly` puede consultar pero no registrar pagos, crear
cuentas ni ningún cambio. Los teléfonos se normalizan a E.164; uno
inválido devuelve `400` nombrándolo.

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

Hay dos caminos para conectar WhatsApp y son intercambiables: el
**server-to-server** (§3.4, todo desde tu app con tu secret key) o el
**iframe** (`connectWhatsApp()` del SDK). Los dos corren la misma
orquestación y los dos activan al negocio. Elegí uno: el primero si ya
tenés tu propia UI de onboarding, el segundo si preferís no tocar el
popup de Meta.

1. **Tu admin crea el negocio** → tu backend llama
   `POST /v1/partners/clients` (con placeholders + credenciales) →
   agente clonado, tenant en `provisioning`.
2. **Registrar admins** → `PUT …/admins` con los teléfonos que podrán
   hablar con el agente (§3.5). Si ya los mandaste como placeholder en el
   paso 1, esto es solo para editarlos después.
3. **Conectar WhatsApp** → `POST …/whatsapp/signup` (§3.4) o
   `auphere.connectWhatsApp()` → el dueño autoriza en Meta → registramos
   el número, suscribimos el webhook y guardamos las credenciales
   cifradas → si `auto_activate`, el negocio pasa a **ACTIVE** y el
   agente empieza a responder.
4. **Plantillas** → aprobá las plantillas de recordatorio en la WABA del
   negocio (§6). Sin esto el agente contesta y consulta, pero no puede
   enviar recordatorios a los deudores.
5. **Broadcasts** → el botón de campañas aparece solo con WhatsApp
   conectado; tu app pasa la audiencia; el widget muestra plantillas
   aprobadas + preview y dispara. Respetamos opt-outs, ventana de 24h y
   el cap por envío del partner.

En cualquier momento, `GET /v1/partners/clients/{ref}` (§3.3) te dice en
cuál de estos pasos está cada negocio.

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
| `422` "Faltan datos del negocio" | Quedó un `<<… pendiente>>` sin rellenar | Mandá los placeholders que nombra el detail (§3.1) |
| `422` "whitelist quedó vacía" | Vertical `admin_only` sin `admin_phones` usables | Al menos un teléfono E.164 con 7+ dígitos |
| Conectó WhatsApp pero el agente no responde | `tenant_status` quedó en `provisioning` | Mirá `activation_blocked_reason`: `no_agent` → revisar la provisión; `operator_review` → lo activa Auphere |
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
