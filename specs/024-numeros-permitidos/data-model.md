# Modelo de datos — spec 024

Una columna nueva (con migración); todo lo demás son formas de entrada y
salida sobre datos que ya existen.

## 1 · `policies.admin_access` (existe; sin cambio de forma)

```json
{"admin_only": true,
 "admin_phones": ["+56991919125", "+34666261967"],
 "admins": [{"phone": "+56991919125", "name": "Daniel, ventas", "role": "full"},
            {"phone": "+34666261967", "name": null, "role": "full"}]}
```

Reglas que la consola respeta al escribirlo (`services/agent_audience.py`):

- `admin_phones` en E.164 (`to_e164`), sin duplicados, en el orden en que
  el partner los escribió.
- `admins` una entrada por teléfono; `name` opcional (≤ 120); `role` se
  conserva si ya existía para ese teléfono, si no `full`.
- `mode == "everyone"` → `admin_only = false`; los números se conservan.
- `mode == "list"` con cero números útiles (`usable_admin_phones`) → no se
  guarda (422).

## 2 · `audience` en Ajustes del agente (nuevo, derivado)

```python
class AudienceNumber(BaseModel):
    phone: str            # E.164 en salida; en entrada, lo que escribió el partner (≤ 32)
    name: str | None = None   # ≤ 120

class AudienceOut(BaseModel):
    mode: Literal["everyone", "list"]
    numbers: list[AudienceNumber]
    locked: bool          # la plantilla es de solo administradores

class AudienceIn(BaseModel):
    mode: Literal["everyone", "list"]
    numbers: list[AudienceNumber] = []   # ≤ 50
```

`AgentSettingsOut.audience: AudienceOut` (siempre presente) y
`AgentSettingsIn.audience: AudienceIn | None` (ausente = no tocar
`admin_access`, para no romper a quien ya llama al PUT con solo
`settings`).

Derivación en lectura, sobre la versión que se edita:

| `admin_access` | `audience.mode` | `numbers` |
|---|---|---|
| ausente o `admin_only` falso | `everyone` | los `admin_phones` guardados, si los hay |
| `admin_only` verdadero | `list` | `admin_phones` con el `name` de `admins` |

`locked` = `seed_template_ref` del cliente carga y su
`policies_default.admin_access.admin_only` es verdadero.

## 3 · `messages.skipped_reason` (nuevo)

| Columna | Tipo | Valor |
|---|---|---|
| `skipped_reason` | `varchar(40)`, nula | `not_admin` cuando el gate de solo administradores suprimió la respuesta; nula en todo lo demás |

Migración `0136_message_skipped_reason` (id ≤ 32 caracteres): `ADD COLUMN`
nula, sin relleno (los mensajes anteriores no tienen motivo conocido y no
se inventa). Índice parcial `(conversation_id) WHERE skipped_reason IS NOT
NULL` para el conteo por conversación.

La escribe el worker (`dispatcher.py`) sobre el entrante que acaba de
persistir, en la misma sesión, antes de devolver `skipped: not_admin`.

## 4 · Cliente (lista y ficha)

```python
class ClientAudienceOut(BaseModel):
    mode: Literal["everyone", "list"]
    count: int            # números útiles en la versión ACTIVA
```

`ClientSummaryOut.audience: ClientAudienceOut | None` (nula sin versión
activa) y, por herencia, `ClientOut`. Se lee de la versión **activa**: lo
que atiende, no lo que se edita. La lista de clientes lo obtiene en una
consulta por página (`agent_configs` activas de los tenants del partner).

## 5 · Conversación (lista y estadísticas)

```python
class UnansweredOut(BaseModel):
    count: int
    reason: Literal["not_admin"]
```

`ConversationOut.unanswered: UnansweredOut | None` (nula si cero) y
`ConversationStatsOut.unanswered_messages: int`. Se cuentan mensajes
entrantes con `skipped_reason = 'not_admin'`.

## 6 · Consola

- `Audience`, `AudienceNumber`, `ClientAudience`, `Unanswered` en
  `lib/backend/agent-tools-types.ts` y tipos de cliente/conversación.
- Espejo zod: `audience: {mode, numbers[]}`; el área de texto se guarda en
  el formulario como `audience_text` y se parsea a `numbers` al validar
  (`audience-lines.ts`: una línea = `teléfono · nombre` o `teléfono`, y
  comas entre teléfonos; teléfono = `+` opcional y de 7 a 15 cifras tras
  quitar espacios, puntos y guiones).
- Claves i18n nuevas (todas usadas): `agentSettings.section.audience`,
  `agentSettings.audience.everyone`, `.list`, `.numbers`,
  `.numbers.hint`, `.numbers.eg`, `.locked`, `.err.empty`, `.err.phone`;
  `clients.audience.only` («Responde solo a {n} números»),
  `clients.audience.badge` («Solo {n} números»);
  `conv.unanswered` («{n} sin responder · número no permitido»),
  `conv.stats.unanswered`.
