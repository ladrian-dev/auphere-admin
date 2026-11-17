# Investigación: Conector de Quédate

**Fuentes**:
- la página «API Agent (para IA)» del panel de Quédate, en dev y en producción, leída el 2026-11-16;
- llamadas reales a dev con la clave de Luis, el mismo día;
- el `openapi.json` v2.1.0 de la API general, congelado en `apps/mcp/tests/fixtures/quedate/openapi-2.1.0.json`;
- el código de `develop` @ `af8b5e3c`.

Detalle de la investigación en la KB: `[[research/2026-11-16-quedate-api-del-agente]]`.

> La investigación del 2026-11-13 (registro con `/register`, contraseña generada y clave por persona) queda sustituida por esta. Sus decisiones D3, D4, D6, D8 y D11 ya no valen.

## Lo que se comprobó en dev el 2026-11-16

Se crearon un anfitrión ficticio («Prueba Auphere Nexus») y un anuncio de prueba, que acabó oculto.

| Llamada | Resultado |
|---|---|
| `GET /agent/catalogs` | 200: 26 estados, 484 ciudades, 1.288 sectores, 7 tipos de propiedad, 10 comodidades y la tasa BCV (278 KB) |
| `POST /agent/hosts` | 201: `id`, `name`, `first_name`, `last_name`, `email`, `phone`, `document_type`, `document_number`, `kyc_verified` y `kyc_status` (`pending_documents`) |
| `POST /agent/hosts` con el mismo correo | 422 `VALIDATION_ERROR`, `errors.email = ["The email has already been taken."]` |
| `GET /agent/hosts/{id}` | 200, aunque no está documentada: añade `kyc_document_status`, `kyc_selfie_status` y `listings` |
| `GET /agent/hosts/{id}` de otra clave del mismo usuario | 403 `FORBIDDEN` |
| `GET /agent/hosts/{id}/kyc-link` | 200: `kyc_url` (en `dev.quedate.net`) y `expires_in_days: 7` |
| `POST /agent/hosts/{id}/kyc` vacío | 422 `document_image` obligatorio. No se envió ningún documento |
| `POST /agent/listings` | 201 `status: draft` |
| `POST /agent/listings/{id}/media` con 3 PNG | 200, con `total_photos` y la lista `media` |
| `PATCH …/status` a `published` | **200 con el anfitrión sin KYC** |
| `PATCH …/status` a `pending_approval` y luego a `hidden` | 200 |
| `GET /agent/listings/{id}` | 200 (el 14 de noviembre daba 500): incluye `user_id`, que es el anfitrión |
| `GET /agent/listings?host_id=…` | Ignora el filtro |
| `GET /agent/hosts?per_page=1&page=1` | Paginador de Laravel: `data.data`, `total`, `per_page`, `last_page` |
| La clave «agent» contra la API general (`/me`, `/my/listings`, `/admin/api-keys`) | 200: el alcance no se aplica |

## Pasada real de las herramientas (T060, 2026-11-16)

Las 27 herramientas reales contra Quédate dev, con la clave de alcance `agent:onboarding`, un almacén de vínculos en memoria y datos ficticios. Fuera de la suite: el guion vive en el scratchpad de la sesión y no se versiona.

| Paso | Resultado |
|---|---|
| Ubicaciones (estado → ciudad → sector) y opciones de anuncio | ids reales del catálogo |
| `register_me` y repetirlo | crea un anfitrión; la segunda vez, `already_linked` sin llamar a Quédate |
| `my_host` | `kyc_document_status: locked` antes de subir nada |
| `my_verification_link` dos veces | el mismo enlace (`dev.quedate.net/validate-kyc/…`), `reused: true` |
| `upload_my_identity` | 200, documento `pending` |
| `create_my_listing`, 3 fotos, `submit_my_listing`, `hide_my_listing` | `draft` → 3 fotos (WebP) → `pending_approval` → `hidden` |
| `list_hosts`, `get_host`, `list_listings` con filtro, `get_managed_listing` | solo lo de la clave |
| `get_host` de un id ajeno | «la clave de este negocio no alcanza…» (403) |
| `key_check` | clave buena → `ok`; clave falsa → `rejected` |

Observado: **cada llamada a `kyc-link` genera un enlace nuevo**. La de la persona lo reutiliza durante su vigencia (3.7); la de equipo pide uno nuevo cada vez, y no sabemos si invalida el anterior. Queda en «Lo que se le pide a Quédate».

Quedan en dev, sin poder borrarse: el anfitrión «Prueba Nexus 5594», su anuncio oculto y una imagen sintética como documento en revisión.

## D1 — Qué API

- **Decisión**: la API del agente (`/api/v1/agent/*`) para todo lo del anfitrión, y la general, sin clave, para lo público (buscar, ver, cotizar, modo de reserva).
- **Razón**: es la que Quédate hizo para esto. Aísla por clave, no borra y crea anfitriones sin contraseña.

## D2 — Entorno

- **Decisión**: un campo no secreto, `environment`. Si es `dev`, `development` o `desarrollo`, el entorno es dev (`dev-api.quedate.net`); cualquier otro valor, también vacío, es producción (`api-v2.quedate.net`). Las dos direcciones están en el código.
- **Razón**:
  - El formulario de credenciales de la consola solo pinta campos de texto (`connector-card`, `connection-page`).
  - Un desplegable es trabajo de UI aparte.
  - Una dirección libre sería un SSRF desde nuestros servidores.

## D3 — Comprobar la clave

- **Decisión**: `GET /agent/hosts?per_page=1` en el entorno elegido.
- **Razón**:
  - `/me` es de la API general.
  - `/agent/catalogs` pesa 278 KB.
  - El listado paginado de una línea es la llamada autenticada más barata de la API del agente.
- **Límite**: no distingue el alcance `agent:onboarding` de `*`, porque Quédate no lo aplica. Va en lo que se le pide a Quédate.

## D4 — El vínculo de la persona

- **Decisión**: la tabla `customer_connector_accounts`, ya **sin credencial**. Guarda el identificador del anfitrión (`external_user_id`), un estado mínimo (`verification_link`) y `needs_review`.
- **Razón**: una sola clave alcanza a todos los anfitriones que creó. Para que una persona no toque a otra (garantía 8), su anfitrión tiene que salir de un vínculo resuelto en el servidor.

## D5 — Alta y duplicados

- **Decisión**:
  - Un candado por persona.
  - El alta no se reintenta.
  - Si el correo ya está tomado, se busca entre los anfitriones de la clave (`GET /agent/hosts`, paginado) y se vincula solo si su teléfono es el del cliente final del turno y nadie más del negocio lo tiene vinculado. El correo solo no prueba nada: cualquiera puede decir el de otra persona (/cso del 2026-11-16, 9/10). El teléfono sale del canal y la persona no lo escribe.
  - Un anfitrión, una persona por negocio: `UNIQUE (tenant_id, connector_slug, external_user_id)`.
  - Si el alta no responde, se audita `connector.customer_account_link_failed`. Repetir el alta lleva al caso anterior y vincula el anfitrión que quedó creado.
- **Razón**: Quédate no tiene idempotencia, pero el correo es único y lo devuelve como 422.

## D6 — Anuncios: crear, fotos y estado

- **Decisión**:
  - Crear un anuncio y subir fotos **no se reintentan**, porque Quédate no borra y un duplicado sería permanente. Un fallo sin respuesta queda en la auditoría.
  - El estado solo puede pasar a `pending_approval` o a `hidden`. **Nunca a `published`** (Luis, 2026-11-16).
- **Pertenencia**: antes de tocar un anuncio de la persona, se busca en la lista de la clave y su `user_id` tiene que ser el anfitrión vinculado. No se usa `GET /agent/listings/{id}`, que el 14 de noviembre daba 500.

## D7 — Fotos y documentos de la conversación

- **Decisión**: `quedate.recent_photos` da las imágenes que la persona del turno mandó en su conversación en las últimas 24 horas, como máximo las 20 más recientes, cada una con un `photo_id` (el id del mensaje) y su hora. Las herramientas de subida reciben esos `photo_id`. El servidor comprueba que son de esa conversación y lee los bytes del almacén de medios.
- **Razón**: Quédate no deja quitar una foto subida. La persona tiene que elegir. El modelo no ve URLs ni claves de S3.

## D8 — Datos personales y `test_51`

- **Decisión**: tres entradas nuevas en el inventario, y el techo pasa de 28 a 31:
  - `("quedate.register_me", "email")`: el correo de la propia persona;
  - `("quedate.create_host", "email")` y `("quedate.create_host", "phone")`: herramienta de operador, como `billing.create_account`.
- **Razón**: el resto de datos personales (`document_number`, `date_of_birth`, `first_name`, `last_name`) no están en el eje y se declaran en la spec.

## D9 — Herramientas de equipo

- **Decisión**: están. Qué agente las tiene lo decide el partner (Luis, 2026-11-16). Siguen el precedente de `billing.*`.
- **Riesgo conocido**: en develop nada impide ponerlas en un agente público. Es el defecto A3 de `test_51`, y `customer_reach` está sin fusionar.
- **/cso del 2026-11-16 (medio, 8/10, pendiente de la decisión de Luis)**: en un agente que contesta a cualquiera, `list_hosts` y `get_host` dan a quien escriba el correo y el teléfono de otros anfitriones del negocio. Lo que lo cierra es una puerta por remitente en el runtime, común a `billing.*`, `woocommerce.*` y estas, con su test de aislamiento: trabajo aparte, fuera de la 061.

## D10 — Recortes

- **Decisión**: listas de 10 elementos como máximo, con el total. Ubicaciones filtradas por estado y ciudad, 60 como máximo. Sin datos de contacto en lo público. En las herramientas de la persona no se devuelven correo, teléfono ni documento.
