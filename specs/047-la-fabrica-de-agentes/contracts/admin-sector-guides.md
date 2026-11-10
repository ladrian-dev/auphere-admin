# Contrato — sectores sin guía y «Convertir en guía de Auphere» (`/admin/builder/*`)

Spec 047, enmienda del 2026-10-29: requisito 58.5 (T201), decisiones D47, D65 y D66.
Lo consume el panel de operador (`apps/admin`). Amplía `admin-api.md` §4.

## Qué resuelve

Cuando el sector de un cliente no tiene guía de Auphere (su sector guardado es
`otro`, con una etiqueta libre como «Gimnasio»), el constructor genera **para ese
cliente** una guía y sus 12 pruebas, marcadas «Generada» (58.4). Es del cliente
(RLS) y nunca se comparte.

Auphere ve aquí qué etiquetas sin guía se repiten más y puede **convertir** una
guía generada en guía de Auphere. Para convertirla:

1. una persona de Auphere la **revisa** (puede corregir la guía y las pruebas);
2. no puede llevar **datos del cliente**: ni su nombre, ni su web, ni teléfonos,
   correos, direcciones, sedes o personas del equipo. Ni ninguna URL, correo o
   teléfono de nadie. La API lo comprueba al revisar y otra vez al convertir.

Al convertir, la guía pasa a la plataforma con una clave nueva (`key`) y sus 12
pruebas entran en el catálogo de pruebas del sector (`sector_test_catalog`,
versión 1). Desde entonces, todo cliente de `otro` con la **misma etiqueta
normalizada** (`label_key`) recibe esa guía de Auphere en lugar de generar la suya.
La clave del sector guardado en la ficha sigue siendo `otro`: la lista cerrada de
claves (57.7) no cambia (D66).

## Convenciones

- **Autenticación**: todas las rutas piden `Authorization: Bearer <token del panel>`
  (`401` sin él o con otro). Las escrituras piden además `X-Operator-Id` (la persona
  del panel, ADR-034): `400` si falta o no es un operador.
- **Errores**: `{"detail": {"code": str, ...}}`, como el resto de `/admin/*`.
- **Auditoría**: cada escritura deja una fila en `audit_log` con
  `actor = "operator:<correo>"`, nunca el token.
- **Fechas**: ISO 8601 con zona.
- Ninguna respuesta lleva costes ni cuerpos de mensajes.

## Formas

### `Guide` — una guía del sector

La misma forma para las de Auphere (salidas de las plantillas o convertidas) y las
generadas para un cliente.

```json
{
  "ask": ["¿Atendéis sin cita?"],
  "procedures": [
    {"title": "Llegar sin cita", "when": "Alguien pregunta si puede pasarse ya", "steps": "…"}
  ],
  "risks": ["Una reacción alérgica después de un tratamiento"],
  "tools": ["reservas.find_slots", "reservas.create", "escalate.escalate_to_human"]
}
```

| Campo | Límite |
|---|---|
| `ask` — qué preguntar al negocio | 1–10 frases, cada una 1–300 caracteres |
| `procedures` — procedimientos típicos | 0–10; `title` 1–120, `when` 0–300, `steps` 1–1.500 |
| `risks` — lo que hay que pasar a una persona | 0–10 frases, cada una 1–300 |
| `tools` — herramientas que suele necesitar | 0–20 nombres del catálogo; nunca `booking.*` |

Campos de más: `422 invalid_guide`.

### `SectorTest` — una de las 12 pruebas

La forma del catálogo de pruebas del sector (`sector_catalog.SectorTest`):

```json
{
  "key": "llega_sin_cita",
  "name": "Llega sin cita",
  "persona": "Cliente que pasa por delante",
  "first_message": "¿Puedo pasarme ahora?",
  "plan": "Quiere ir ya; si no hay hueco, acepta el siguiente.",
  "expected_state": {"booking": {"created": true}},
  "criteria": [{"key": "no_inventa", "text": "No promete un hueco que no existe."}],
  "critical": true
}
```

`key` y cada `criteria[].key`: `^[a-z0-9_]{1,40}$`; `name` 1–120; `persona` ≤ 500;
`first_message` 1–2.000; `plan` ≤ 1.000; de 1 a 6 criterios (`text` 1–300). Exactamente
12 pruebas, sin claves repetidas.

Enmienda del 2026-10-30 (requisito 65.8, D74):
- `needs` es opcional: la lista de acciones que el agente tiene que poder hacer para
  que la prueba aplique, de `book`, `modify_booking`, `charge`, `collect`, `invoice`,
  `order`, `modify_order`, `send_media`, `remind` o `catalog`. Como mucho 5.
- `[]`: aplica a cualquier agente. Ausente o `null`: se deduce de `expected_state`
  (`booking` → `book`).
- Al añadir las pruebas a un agente, la que necesita una acción que sus
  herramientas no hacen queda «No aplica».

### `ClientDataFinding` — un dato del cliente encontrado

```json
{"pointer": "/guide/procedures/0/steps", "kind": "phone", "excerpt": "…llama al 612 345 678…"}
```

`kind`: `client_name` · `website` · `url` · `email` · `phone` · `address` ·
`location` · `staff`. `pointer` es JSON Pointer sobre `{"guide": …, "tests": […]}`.
`excerpt`, como mucho 80 caracteres alrededor del hallazgo.

### `GeneratedGuideSummary`

```json
{
  "tenant_id": "uuid",
  "client_name": "Gimnasio Norte",
  "guide_id": "uuid",
  "status": "generated" | "reviewed",
  "tests": 12,
  "created_at": "2026-10-30T09:12:00+00:00",
  "reviewed_at": null,
  "reviewed_by": null
}
```

### `GeneratedGuide`

```json
{
  "guide_id": "uuid",
  "tenant_id": "uuid",
  "client_name": "Gimnasio Norte",
  "sector_label": "Gimnasio",
  "label_key": "gimnasio",
  "status": "generated" | "reviewed" | "promoted" | "archived",
  "guide": Guide,
  "tests": [SectorTest],
  "client_data": [ClientDataFinding],
  "promotable": true,
  "reviewed_by": "operator:ana@auphere.com" | null,
  "reviewed_at": "…" | null,
  "promoted_to": "gimnasio" | null,
  "promoted_at": "…" | null,
  "created_at": "…"
}
```

`client_data` es la comprobación hecha al leer. `promotable` es `true` solo con
`status = "reviewed"`, `client_data` vacío y 12 pruebas.

### `SectorGuide` — una guía de Auphere

```json
{
  "key": "gimnasio",
  "label": "Gimnasio",
  "label_key": "gimnasio",
  "source": "template" | "promoted",
  "templates": ["barbershop_v1"],
  "version": 1,
  "tests": 12,
  "published_by": "operator:ana@auphere.com" | null,
  "published_at": "…" | null,
  "guide": Guide
}
```

`templates`: las plantillas de las que sale (solo `source = "template"`; si no,
`[]`). `tests`: cuántas pruebas tiene su versión vigente del catálogo.
`published_*`: `null` en las de plantilla.

## Rutas

| Método y ruta | Qué hace | Requisito |
|---|---|---|
| `GET /admin/builder/sector-guides` | Las guías de Auphere: las 6 de las plantillas y las convertidas | 58.1, 58.5 |
| `GET /admin/builder/sector-guides/missing?limit=` | Las etiquetas sin guía que más se repiten, con sus guías generadas | 58.5 |
| `GET /admin/builder/generated-guides/{tenant_id}/{guide_id}` | Una guía generada, para revisarla | 58.5 |
| `POST /admin/builder/generated-guides/{tenant_id}/{guide_id}/review` | Marcarla revisada, con correcciones opcionales | 58.5 |
| `POST /admin/builder/generated-guides/{tenant_id}/{guide_id}/promote` | «Convertir en guía de Auphere» | 58.5 |

### `GET /admin/builder/sector-guides`

`200` → `{"items": [SectorGuide]}`: primero las de plantilla en el orden de los
sectores, después las convertidas por fecha.

### `GET /admin/builder/sector-guides/missing?limit=20`

`limit`: 1–100, por defecto 20.

`200` →

```json
{
  "items": [
    {
      "label_key": "gimnasio",
      "label": "Gimnasio",
      "clients": 7,
      "guides": {"generated": 3, "reviewed": 1},
      "candidates": [GeneratedGuideSummary]
    }
  ],
  "clients_scanned": 54,
  "generated_at": "2026-10-30T10:00:00+00:00"
}
```

- Una fila por `label_key` de clientes cuyo sector guardado es `otro` y que **no**
  tiene guía de Auphere (ninguna convertida con esa etiqueta).
- `label`: la forma escrita más frecuente de esa etiqueta.
- `clients`: clientes cuyo sector guardado es hoy `otro` con esa etiqueta. Un cliente
  sin sector todavía no cuenta.
- `guides`: guías generadas vivas con esa etiqueta, por estado (`generated`,
  `reviewed`; las `archived` y `promoted` no cuentan).
- `candidates`: esas guías, las revisadas primero y después de la más nueva a la
  más vieja; como mucho 5.
- Orden: `clients` de mayor a menor; a igualdad, `label_key`. Entra también una
  etiqueta con guías generadas y `clients = 0` (el cliente cambió de sector
  después), al final.
- Sin etiquetas: `items: []`.

Lee cliente a cliente con su contexto puesto (RLS FORCE): nunca una consulta que
cruce clientes sin él.

### `GET /admin/builder/generated-guides/{tenant_id}/{guide_id}`

`200` → `GeneratedGuide`. `404 unknown_guide` si el cliente no existe o la guía no
es suya.

### `POST /admin/builder/generated-guides/{tenant_id}/{guide_id}/review`

Cabeceras: `X-Operator-Id`. Cuerpo (todo opcional; campos de más, `422`):

```json
{"guide": Guide, "tests": [SectorTest], "note": "Quitado el teléfono del paso 2"}
```

- `guide` y `tests`, si llegan, **sustituyen** a los de la guía generada (en el
  cliente). `note`: 0–300.
- Comprueba los datos del cliente sobre lo que queda guardado.

| Respuesta | Cuándo |
|---|---|
| `200` → `GeneratedGuide` | Revisada: `status = "reviewed"`, `reviewed_by`, `reviewed_at` |
| `400` | Sin `X-Operator-Id` o no es un operador |
| `404 unknown_guide` | El cliente no existe o la guía no es suya |
| `409 guide_not_reviewable` | La guía está `promoted` o `archived` |
| `422 invalid_guide` | `guide` no tiene la forma |
| `422 invalid_test` · `twelve_tests_required` · `duplicate_key` | `tests` no vale (o la guía guardada no tiene 12 y no llegan otras) |
| `422 client_data_found` | Quedan datos del cliente: `{"detail": {"code", "findings": [ClientDataFinding]}}`. No se escribe nada |

Se puede revisar otra vez una ya revisada (por ejemplo, tras corregirla).

**Auditoría**: en el cliente, `generated_guide.reviewed`, `target =
"generated_guide:<id>"`, `before_json = {"status"}`, `after_json = {"status",
"edited": bool, "note"}`.

### `POST /admin/builder/generated-guides/{tenant_id}/{guide_id}/promote`

Cabeceras: `X-Operator-Id`. Cuerpo:

```json
{"key": "gimnasio", "label": "Gimnasio", "reason": "Siete clientes, revisada por Ana"}
```

- `key`: `^[a-z_]{2,40}$`; no puede ser la de un sector de plantilla, `otro` ni la
  de otra guía de Auphere.
- `label`: 1–40, se limpia como la etiqueta del sector; su forma normalizada
  (`label_key`) no puede tener ya guía de Auphere.
- `reason`: 3–300.

| Respuesta | Cuándo |
|---|---|
| `201` → `SectorGuide` (`source = "promoted"`, `version = 1`) | Convertida |
| `400` | Sin `X-Operator-Id` o no es un operador |
| `404 unknown_guide` | El cliente no existe o la guía no es suya |
| `409 guide_not_reviewed` | La guía está `generated` (sin revisar) o `archived` |
| `409 guide_already_promoted` | Ya se convirtió |
| `409 guide_key_taken` | La clave ya es de un sector o de otra guía de Auphere |
| `409 guide_label_taken` | Esa etiqueta ya tiene guía de Auphere |
| `422 client_data_found` | Como en `review`. No se escribe nada |
| `422 twelve_tests_required` · `invalid_test` · `invalid_guide` | La guía guardada no vale |
| `422` (validación) | `key`, `label` o `reason` fuera de su forma |

En una sola transacción:

1. la guía de Auphere (`sector_guides`, de plataforma: sin `tenant_id` ni nada que
   apunte al cliente);
2. sus 12 pruebas, versión 1 de `key` en `sector_test_catalog`;
3. la guía generada del cliente pasa a `promoted`, con `promoted_to = key`.

Las suites que ya existen no cambian. El cliente del que salió conserva sus
pruebas «Generada» hasta que una persona las cambie.

**Auditoría**: dos filas. En el cliente, `generated_guide.promoted` (`after_json =
{"promoted_to", "reason"}`). De plataforma (`tenant_id` nulo),
`sector_guide.promoted` (`target = "sector_guide:<key>"`, `after_json = {"key",
"label", "tests": 12, "reason"}`), sin nada del cliente.

## Lo que la pantalla tiene que poder enseñar

- **Cargando**: la lista se calcula al momento, cliente a cliente; puede tardar
  algunos segundos con muchos clientes.
- **Vacío**: `items: []` → no hay sectores sin guía.
- **Error**: cualquier `5xx`, o `401` si caducó el token del panel.
- **Parcial**: una etiqueta con `clients > 0` y `candidates: []` (aún no se generó
  ninguna guía para ella: no hay nada que convertir).
- **Ideal**: la lista, y en cada candidata «Revisar» → la guía con `client_data`
  marcado en su sitio, y «Convertir en guía de Auphere» solo con `promotable`.
