# Contrato: herramientas `quedate.*` (enmienda del 2026-11-16)

- **API del agente**: `{base}/agent`, con `Authorization: Bearer <clave del cliente>`.
- **API general** (las públicas): `{base}`, sin clave.
- **`{base}`**: `https://api-v2.quedate.net/api/v1` (producción) o `https://dev-api.quedate.net/api/v1` (dev), según la conexión.
- **Todas las herramientas**:
  - comprueban antes la conexión y la disponibilidad para el partner (spec 060);
  - aceptan solo los argumentos de su esquema (`extra="forbid"`);
  - no reciben cliente, tenant, conversación ni clave.

## Catálogo y públicas

| Herramienta | Argumentos | Petición | Salida |
|---|---|---|---|
| `quedate.list_locations` | `state?`, `city?` | `GET /agent/catalogs` | Sin filtro, los estados; con `state`, sus ciudades; con `state` y `city`, sus sectores. Cada uno con `id` y `name`, como mucho 60 |
| `quedate.listing_options` | — | `GET /agent/catalogs` | `property_types` y `amenities` (`id` y `name`), `rental_types`, `booking_modes`, `document_types` y `bcv_rate` |
| `quedate.search_listings` | `q?`, `city?`, `state?`, `check_in?`, `check_out?`, `guests?`, `property_type?`, `min_price?`, `max_price?`, `rental_type?` | `GET /search/listings` (general, sin clave) | Hasta 10 alojamientos, con el total |
| `quedate.get_listing` | `listing` (UUID o slug) | `GET /listings/{listing}` (general) | Detalle recortado, sin contacto del anfitrión |
| `quedate.quote_stay` | `listing_id`, `check_in`, `check_out`, `guests` | `POST /checkout/quote` (general) | `available`, `total_usd`, `total_ves`, `nights` y `bcv_rate`, o el mensaje de Quédate |
| `quedate.booking_settings` | — | `GET /settings/public` (general) | `booking_mode` y `support_whatsapp` |

## Fotos de la conversación

| Herramienta | Argumentos | Salida |
|---|---|---|
| `quedate.recent_photos` | — | Las imágenes que la persona del turno mandó en su conversación en las últimas 24 horas, como mucho 20, cada una con `photo_id` y `sent_at` |

## De la persona que escribe (el anfitrión sale del vínculo)

| Herramienta | Argumentos | Efectos | Petición |
|---|---|---|---|
| `quedate.register_me` | `first_name`, `last_name`, `email`, `email_confirmed`, `document_type`, `document_number`, `date_of_birth`, `sex`, `nationality` (`VEN` por defecto). El teléfono sale del cliente final | escribe | `POST /agent/hosts`. Con 422 de correo tomado, se busca en `GET /agent/hosts` y se vincula solo si su teléfono es el del chat y nadie más del negocio lo tiene; si no, «ese correo ya es de otra cuenta» |
| `quedate.my_host` | — | — | `GET /agent/hosts/{vínculo}` |
| `quedate.my_verification_link` | — | escribe (estado) | `GET /agent/hosts/{vínculo}/kyc-link`. Se reutiliza mientras queden más de 24 h |
| `quedate.upload_my_identity` | `document_photo_id`, `selfie_photo_id?` | escribe | `POST /agent/hosts/{vínculo}/kyc` (multipart: `document_image`, `selfie_image`) |
| `quedate.create_my_listing` | los campos del anuncio (abajo) | escribe | `POST /agent/listings` con `host_id` del vínculo. Sin reintento |
| `quedate.add_my_listing_photos` | `listing_id`, `photo_ids` (1 a 20) | escribe | `POST /agent/listings/{id}/media` (multipart `files[]`). Sin reintento |
| `quedate.submit_my_listing` | `listing_id` | escribe | `PATCH /agent/listings/{id}/status` a `pending_approval` |
| `quedate.hide_my_listing` | `listing_id` | escribe | `PATCH /agent/listings/{id}/status` a `hidden` |
| `quedate.my_listings` | — | — | `GET /agent/listings`, filtrado por `user_id` del vínculo |

Antes de cualquier escritura, el anuncio tiene que estar en la lista de la clave con `user_id` igual al vínculo. Si no, se rechaza sin escribir.

## De equipo (cualquier anfitrión de la clave)

| Herramienta | Argumentos | Petición |
|---|---|---|
| `quedate.list_hosts` | `page?` | `GET /agent/hosts?per_page=10&page=` |
| `quedate.get_host` | `host_id` | `GET /agent/hosts/{id}` |
| `quedate.create_host` | `first_name`, `last_name`, `email`, `phone`, `document_type`, `document_number`, `date_of_birth`, `sex`, `nationality` | `POST /agent/hosts` |
| `quedate.host_verification_link` | `host_id` | `GET /agent/hosts/{id}/kyc-link` |
| `quedate.upload_host_identity` | `host_id`, `document_photo_id`, `selfie_photo_id?` | `POST /agent/hosts/{id}/kyc` |
| `quedate.list_listings` | `page?`, `host_id?` | `GET /agent/listings?per_page=10&page=`, con el filtro en servidor |
| `quedate.get_managed_listing` | `listing_id` | `GET /agent/listings/{id}` |
| `quedate.create_listing` | `host_id` y los campos del anuncio | `POST /agent/listings` |
| `quedate.add_listing_photos` | `listing_id`, `photo_ids` | `POST /agent/listings/{id}/media` |
| `quedate.submit_listing` | `listing_id` | `PATCH …/status` a `pending_approval` |
| `quedate.hide_listing` | `listing_id` | `PATCH …/status` a `hidden` |

## Campos del anuncio (contrato de la API del agente)

`title`, `description`, `property_type_id`, `sector_id`, `street_address`, `apartment_suite`, `latitude`, `longitude`, `price_per_night`, `max_guests`, `bedrooms`, `beds`, `bathrooms` y `amenities` (nombres del catálogo).

## Errores

| Respuesta de Quédate | Qué ve el modelo |
|---|---|
| 422 | El campo y el mensaje de Quédate |
| 403 | Herramientas de la persona: el vínculo pasa a revisión y se dice. Herramientas de equipo: «esta clave no alcanza ese anfitrión o anuncio» |
| 5xx o sin respuesta | «Quédate no responde». En crear y subir, además, «puede que se haya creado; compruébalo con la lista antes de repetir» |
