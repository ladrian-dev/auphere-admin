# Guía de integración para partners — Auphere API

> Cómo un partner SaaS integra Auphere para que **cada negocio (cliente
> final) del partner** tenga su propio agente de WhatsApp con sus datos
> aislados, conecte su propio número y envíe campañas de plantillas — todo
> desde la app del partner, server-to-server, sin operador de Auphere en
> el medio.
>
> Audiencia: el equipo de desarrollo del partner + el operador Auphere
> que da de alta al partner. Arquitectura de referencia: ADR-028.
>
> Es una API HTTP: no hay SDK que instalar ni nada que montar en tu
> frontend. Tu backend habla con `api.auphere.com` con tu secret key.

---

## 1. Modelo mental

| Concepto del partner | Concepto en Auphere |
|---|---|
| Partner (tu plataforma SaaS) | `partner` con secret API key (`ak_live_…`) |
| Negocio / cliente final | `tenant` aislado (RLS), referenciado SOLO por **tu** id (`external_client_ref`) |
| WhatsApp del negocio | Canal Meta Cloud API propio del tenant (WABA del negocio) |
| Agente del negocio | `agent_config` clonado del **blueprint** del partner (seed template) |
| Campañas / recordatorios | `broadcast` de plantilla HSM a 1..N destinatarios |

Reglas de oro:

1. **La secret key nunca sale de tu backend.** Nunca la pongas en tu
   frontend: todas estas llamadas son server-to-server.
2. **Nunca conoces nuestros `tenant_id`.** Hablas con tu propio
   `external_client_ref`; nosotros mapeamos.
3. **Los destinatarios y variables los mandas tú.** Tu CRM es la fuente de
   verdad; nosotros validamos, encolamos, entregamos y reportamos.
4. **Dos scopes, dos capacidades.** `provision` da de alta y configura
   negocios; `broadcasts` les manda mensajes a sus clientes finales. Podés
   tener una key para cada cosa.

## 2. Requisitos previos

**Del partner:**
- Backend capaz de guardar la secret key (env/secret manager, jamás en el
  bundle del frontend).
- Un id estable por negocio (`external_client_ref`) — UUID recomendado.
- Para conectar WhatsApp: poder abrir el popup de Meta desde tu web (JS
  SDK de Facebook con NUESTRO `app_id`, que te damos por API).

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
3. Emitir la **API key** con los scopes que corresponda (`provision`,
   `broadcasts`, o ambos). El plaintext se muestra UNA vez — entregarlo
   por canal seguro.
4. Ajustar límites si aplica: `broadcast_recipient_cap` (default 250) y
   el rate limit de campañas por minuto.

## 3. Contrato de API (backend del partner)

Base: `https://api.auphere.com` (prod). Auth: `Authorization: Bearer ak_live_…`.

### Versiones

La superficie vive bajo un prefijo de versión. Hoy hay dos y **sirven
exactamente lo mismo**:

| Versión | Estado | Para qué |
|---|---|---|
| `/v2` | **actual** | Integraciones nuevas. Es donde ocurrirán los cambios |
| `/v1` | **congelada** | Su forma no va a cambiar. Responde con `Deprecation` y `Link: </v2>; rel="successor-version"` |

Migrar de `/v1` a `/v2` es cambiar el prefijo: mismos caminos, mismos
cuerpos, mismos códigos. No hay fecha de apagado de `/v1` — cuando la haya
se acordará contigo y saldrá en la cabecera `Sunset` antes de aplicarse.

Los ejemplos de abajo usan `/v1` porque es lo que hay integrado hoy.

### Respuestas de error comunes a toda la superficie

| Código | Cuándo |
|---|---|
| `400` | El cuerpo no se pudo leer (JSON ilegible) |
| `401` | Falta la clave, o no es válida |
| `403` | Clave válida sin el scope necesario, o partner suspendido |
| `422` | El cuerpo se leyó y no cumple el esquema |
| `429` | Límite de peticiones superado. Reintentar con espera |

El límite es **por superficie y por partner**: agotar la cuota de
aprovisionamiento no afecta a tus envíos, ni al revés.

### Endpoints

| Endpoint | Scope |
|---|---|
| `POST /v1/partners/clients` | `provision` |
| `GET /v1/partners/clients/{ref}` | `provision` |
| `GET /v1/partners/whatsapp/signup-config` | `provision` |
| `POST /v1/partners/clients/{ref}/whatsapp/signup` | `provision` |
| `GET`/`PUT /v1/partners/clients/{ref}/admins` | `provision` |
| `GET /v1/partners/clients/{ref}/templates` | `broadcasts` |
| `POST /v1/partners/clients/{ref}/broadcasts` | `broadcasts` |
| `GET /v1/partners/clients/{ref}/broadcasts/{id}` | `broadcasts` |

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
```

(`agent.name` es opcional — por defecto "Sofía".)

> **Cambio (ADR-035, 2026-08-21):** los placeholders `policies.payment.*`
> **ya no existen**. Vivían en el prompt del vertical, que es compartido por
> todos los negocios, y los valores de ejemplo del seed llegaron a producción
> tal cual. Si los sigues mandando se ignoran; no hace falta que los quites,
> pero tampoco sirven de nada.
>
> El agente ahora responde que no tiene los datos de pago del negocio. Si
> necesitáis que los dicte, el camino es exponerlos en vuestra API y añadir
> una tool que los lea — no volver a meterlos en el prompt.

### 3.1.b Recordatorios de vencimiento

El barrido es **diario y automático** desde ADR-035: una pasada al día a
`policies.reminders.hour_local` (por defecto las 9) en la zona horaria del
negocio. Etapas: vence hoy, vence en 1-3 días, y 7+ días vencida.

Ajustes por negocio en `policies.reminders`:

| Campo | Default | Qué hace |
|---|---|---|
| `enabled` | `true` | interruptor del barrido |
| `hour_local` | `9` | hora local a la que corre |
| `max_overdue_days` | `30` | no persigue deudas más viejas |
| `max_per_run` | `50` | tope por barrido; lo excluido sale al día siguiente |

Requiere las dos plantillas (`recordatorio_pago_proximo`,
`recordatorio_pago_vencido`) APPROVED **en la WABA del negocio**, y que esa
WABA tenga método de pago en su Meta Business: sin él Meta acepta el envío y
luego lo falla con `131042` *Business eligibility payment issue*.

### 3.2 Enviar plantillas (campañas)

Dos llamadas, ambas con la key de scope `broadcasts`.

**Listar las plantillas del negocio** — lectura en vivo de SU WABA,
filtrada a APPROVED (ofrecer otra cosa da un envío que Meta rechaza):

`GET /v1/partners/clients/{external_client_ref}/templates`

```json
{ "templates": [
  { "name": "recordatorio_pago_vencido", "language": "es", "status": "APPROVED",
    "category": "UTILITY",
    "components": [{ "type": "BODY", "text": "Hola {{cliente}}, tienes {{monto}} pendiente desde {{fecha}}." }] }
] }
```

**Enviar** a uno o a muchos — es el mismo endpoint:

`POST /v1/partners/clients/{external_client_ref}/broadcasts`

```json
{
  "template_name": "recordatorio_pago_vencido",
  "language": "es",
  "idempotency_key": "factura-991-aviso-1",
  "recipients": [
    { "phone": "+584241234567",
      "variables": { "cliente": "Ana", "monto": "36.00", "fecha": "12/08" } }
  ]
}
```

→ `202 { "broadcast_id": "…", "accepted": 1, "rejected": [] }`

`202` significa **encolado y durable**, no entregado: el dispatcher se
encarga de enviar, reintentar y seguir el estado.

**Seguir el envío:**

`GET /v1/partners/clients/{external_client_ref}/broadcasts/{broadcast_id}`

```json
{ "broadcast_id": "…", "template_name": "recordatorio_pago_vencido",
  "counts": { "delivered": 1 },
  "recipients": [ { "phone": "+584241234567", "status": "delivered" } ] }
```

Estados por destinatario: `pending` → `sent` → `delivered` → `read`, o
`failed` / `rejected` (con `reason`).

Lo que aplicamos por vos en cada envío:

- **Idempotencia** — repetir el mismo `idempotency_key` devuelve `200`
  con el resultado original en vez de enviar dos veces. Usá un id de tu
  dominio (factura, recordatorio), no un random.
- **Variables nombradas** — las claves deben coincidir con los
  `{{nombre}}` de la plantilla. Las posicionales (`{{1}}`) se rechazan
  con `422`.
- **Opt-out** — quien respondió BAJA/STOP se descarta y aparece en
  `rejected`.
- **Cap por envío** — `250` destinatarios por defecto (el tier inicial
  de Meta); por encima, `413`. Trocealo o pedinos subirlo.
- **Plantilla viva** — se verifica contra Meta en el momento del envío,
  no contra una copia nuestra.

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

## 4. El flujo completo de un negocio nuevo

1. **Tu admin crea el negocio** → tu backend llama
   `POST /v1/partners/clients` (con placeholders + credenciales) →
   agente clonado, tenant en `provisioning`.
2. **Registrar admins** → `PUT …/admins` con los teléfonos que podrán
   hablar con el agente (§3.5). Si ya los mandaste como placeholder en el
   paso 1, esto es solo para editarlos después.
3. **Conectar WhatsApp** → `POST …/whatsapp/signup` (§3.4) → el dueño
   autoriza en Meta → registramos el número, suscribimos el webhook y
   guardamos las credenciales cifradas → si `auto_activate`, el negocio
   pasa a **ACTIVE** y el agente empieza a responder.
4. **Plantillas** → aprobá las plantillas del negocio en SU WABA (§5).
   Sin esto el agente contesta y consulta, pero no puede enviar
   recordatorios a los deudores.
5. **Campañas** → `POST …/broadcasts` (§3.2) con la audiencia que salga
   de tu CRM. Respetamos opt-outs y el cap por envío.

En cualquier momento, `GET /v1/partners/clients/{ref}` (§3.3) te dice en
cuál de estos pasos está cada negocio.

## 5. Plantillas HSM

Cada negocio envía desde SU propia WABA, así que las plantillas se
aprueban **por negocio** en Meta. Hoy la creación del set inicial de
plantillas es asistida por el operador Auphere tras el signup (la
provisión automática de un catálogo por partner está en el roadmap).
`GET …/templates` solo devuelve las que ya están APPROVED.

## 6. Métricas y facturación

El uso queda atribuido al partner vía el mapeo negocio→tenant:
`GET /admin/partners/{id}/usage` (panel Auphere) agrega por cliente:
estado, WhatsApp conectado, versión/seed del agente, broadcasts,
destinatarios, mensajes in/out y costo de modelo — la base de la
facturación por negocio activo.

## 7. Seguridad (resumen para tu equipo)

- **Secret key**: solo backend; rotación con ventana de gracia y
  revocación inmediata desde el panel Auphere. Guardamos SHA-256, no la
  key (no es reversible ni la podemos recuperar: si se pierde, se rota).
- **Scopes mínimos**: `provision` y `broadcasts` son independientes. Una
  key de integración filtrada no puede mandarle mensajes a los clientes
  finales de nadie.
- **Aislamiento**: el `tenant_id` no se acepta nunca del request — sale
  del mapeo `(partner, external_client_ref)`. Cada consulta corre bajo
  RLS de ese tenant, así que un negocio no puede ver datos de otro ni un
  partner los de otro. El ref de otro partner devuelve `404` opaco: no
  revelamos si existe.
- **Sin superficie de navegador**: la API no tiene CORS habilitado. Todo
  es server-to-server; nada de esto se llama desde un frontend.
- **Auditoría**: cada provisión, signup, cambio de admins y campaña deja
  una fila append-only con la key que lo hizo y la IP de origen.

## 8. Troubleshooting

| Síntoma | Causa probable | Acción |
|---|---|---|
| `401` en cualquier llamada | Key revocada/expirada o checksum inválido | Verificar la key; pedir rotación |
| `403 API key lacks required scope` | La key no tiene el scope del endpoint (§3) | Pedir una key con `broadcasts` (o `provision`) |
| `422` al provisionar | Placeholder del seed sin valor / credenciales vacías | El detail dice exactamente qué falta |
| `422` "Faltan datos del negocio" | Quedó un `<<… pendiente>>` sin rellenar | Mandá los placeholders que nombra el detail (§3.1) |
| `422` "whitelist quedó vacía" | Vertical `admin_only` sin `admin_phones` usables | Al menos un teléfono E.164 con 7+ dígitos |
| Conectó WhatsApp pero el agente no responde | `tenant_status` quedó en `provisioning` | Mirá `activation_blocked_reason`: `no_agent` → revisar la provisión; `operator_review` → lo activa Auphere |
| Meta rechaza el OAuth code | Code expirado o reusado | Cerrar y reintentar el flujo |
| `409` al conectar número | El número ya está mapeado a otro tenant | Contactar al operador Auphere (offboard previo) |
| Broadcast `413` | Audiencia > cap del partner | Trocear el envío o pedir aumento de cap |
| Broadcast `409 whatsapp_not_connected` | El negocio aún no conectó su número | Completar el signup (§3.4) |
| Broadcast `429` | Superaste el rate limit de campañas | Espaciar los envíos o pedir aumento |
| `422` "positional parameters" | La plantilla usa `{{1}}` en vez de `{{cliente}}` | Recrearla en Meta con parámetros nombrados |
| Plantilla no aparece | No está APPROVED en la WABA del negocio | Esperar aprobación de Meta / revisar en el panel |

## 9. Checklist de go-live de un partner

- [ ] Partner creado + blueprint configurado (seed, connector, auto_activate).
- [ ] API key emitida con los scopes acordados (`provision`, `broadcasts`).
- [ ] Provisión llamada desde el alta de negocios del partner.
- [ ] Flujo de Embedded Signup montado en la app del partner (§3.4).
- [ ] Negocio piloto E2E: provisión → admins → signup → `ready: true` →
      campaña de prueba a un número propio.
- [ ] Plantillas iniciales aprobadas en la WABA del piloto.
