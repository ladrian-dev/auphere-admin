# Fase 0 — investigación

Seis decisiones, todas medidas contra el código el 2026-09-30. Una de ellas
(D5) depende de algo que vive fuera del repositorio y hay que comprobar en
staging antes de dar la iteración 1 por cerrada.

---

## D0 · Lo que ya existe y no hay que rehacer

| Pieza | Dónde | Estado |
|---|---|---|
| Enviar tarjetas de producto nativas (`product`, `product_list`, `catalog_message`) | `apps/worker/src/nexus_worker/streams/outbound.py` (`_to_meta_interactive`), a partir de `products` en `response.send_interactive`; `catalog_id` y `catalog_thumbnail_retailer_id` se inyectan del `config` del canal, nunca del LLM | **existe** |
| Guardar `catalog_id` en el canal | `signup.py` (`_upsert_channel`, `config["catalog_id"]`), solo por la vía de operador `POST /admin/tenants/{id}/integrations/meta/connect-owned` | existe, sin consola |
| Cliente de Meta | `nexus_channels.whatsapp_meta.meta_client.MetaClient` con `_get` / `_post` / `_delete`, reintentos y traducción de errores (`MetaAPIError` con `code`/`subcode`) | existe; **sin llamadas de catálogo** |
| Credenciales con las que hablar con Meta | por canal (`channels.config_encrypted`, `ChannelCredentialsRepository`) con respaldo por tenant (`MetaCredentialsRepository`); la misma pareja que usa desvincular (spec 021) | existe |
| La tarjeta del número, su endpoint de desvincular, la costura `build_meta_client` para tests y la auditoría por acción | spec 021 | existe |
| Capacidades con dependencia de integración | `api/console/capability_names.py::requires_connector` — hoy AgendaPro se declara «necesita la agenda» sin fila de conector | existe; hay que ampliarlo a «necesita catálogo» |
| Servidores de herramientas internos con credenciales del tenant | `apps/mcp/src/nexus_mcp/servers/woocommerce/tools.py` lee `tenant_connectors.credentials_ref` → `tenant_credentials` → descifra | patrón a copiar para leer el catálogo |

---

## D1 · Las tres llamadas de Meta

| Qué | Llamada | Permiso |
|---|---|---|
| Listar los catálogos del negocio | `GET /{business_id}/owned_product_catalogs?fields=id,name,product_count` | `catalog_management` (+ `business_management`) |
| Ver cuál tiene enlazado la cuenta de WhatsApp Business | `GET /{waba_id}/product_catalogs?fields=id,name` | `whatsapp_business_management` |
| Enlazar | `POST /{waba_id}/product_catalogs` con `catalog_id` | `catalog_management` + `whatsapp_business_management` |
| Desenlazar | `DELETE /{waba_id}/product_catalogs?catalog_id=…` | ídem |
| Leer productos (para la habilidad «buscar») | `GET /{catalog_id}/products?fields=retailer_id,name,price,availability,image_url,description&limit=…` (y `filter` por nombre) | `catalog_management` |

**Decisión**: cuatro métodos nuevos en `MetaClient` (`list_catalogs`,
`get_linked_catalog`, `link_catalog`, `unlink_catalog`) y uno de lectura de
productos (`search_products`) usado solo por la herramienta del agente. Todos
sobre `_get`/`_post`/`_delete` existentes; ninguna dependencia nueva.

`business_id` ya viaja en el alta (`signup.py`, sobre `data.business_id`) y
se guarda en `config` del canal — hay que confirmarlo en el test de D0 y, si
un canal viejo no lo tiene, leerlo de la credencial del tenant.

---

## D2 · El catálogo se lee de Meta, no de la tienda (clarificación Q1)

Alternativas: (a) que el agente busque en WooCommerce y confíe en que los
identificadores coinciden; (b) que lea el catálogo de Meta. El owner eligió
**(b)**: el catálogo ya tiene nombre, foto y precio, sirve a un negocio sin
tienda, y evita dos fuentes que discrepen.

**Decisión**: herramienta nativa `catalog.search_products` (y
`catalog.get_product`) en un servidor interno nuevo `servers/meta_catalog`,
que resuelve el `catalog_id` del canal **por el que llegó la conversación** y
el token de esa credencial, y devuelve `{retailer_id, name, price, currency,
availability, image_url}`. La tarjeta se envía con el `response.send_interactive`
que ya existe: el agente pasa `retailer_id`s y el motor pone el `catalog_id`.
El LLM nunca ve el token ni el `catalog_id`.

---

## D3 · La consola adopta lo que Meta tiene (clarificación Q2)

Al cargar la lista de canales, para cada número activo con credencial la API
pregunta a Meta cuál es el catálogo enlazado de su WABA (**una** llamada por
WABA, no por número; cacheada 5 min en Redis por `waba_id`) y concilia:

| Meta | Nuestra base | Qué hace |
|---|---|---|
| tiene X | no tiene nada | guarda X (id y nombre) y lo enseña |
| tiene X | tiene Y | guarda X: la verdad es la de Meta |
| no tiene nada | tiene Y | borra Y y ofrece conectar |
| Meta no responde | tiene Y | enseña Y con «no se pudo comprobar»; no borra |

La conciliación es **lectura + escritura en nuestra base**; no toca Meta.
Sin credencial, o sin permiso, no se pregunta y la tarjeta lo dice (D5).

---

## D4 · Cambiar pide confirmación; desenlazar antes de enlazar (clarificación Q3)

Una WABA tiene **un** catálogo. Enlazar otro con uno ya puesto: Meta puede
rechazarlo o sustituirlo según la versión de la API; no lo damos por hecho.
**Decisión**: el endpoint de enlazar, si la WABA tiene otro catálogo, primero
lo desenlaza y luego enlaza el nuevo, en ese orden, y anota ambos pasos en la
auditoría (`after.meta = {unlinked, linked}`). Si el segundo paso falla, el
canal queda **sin catálogo** y la tarjeta lo dice: es un estado honesto y
reversible, mejor que fingir que el viejo sigue.

La confirmación vive en la consola (diálogo «Vas a sustituir A por B»), no en
la API: la API hace lo que se le pide.

---

## D5 · El permiso vive en el panel de Meta — lo que no controlamos

La configuración del Embedded Signup (`config_id`, `NEXUS_META_CONFIG_ID_WA_*`)
decide qué permisos trae el token. **No está en el repositorio.** Si no incluye
`catalog_management`, D1 falla con `code 10`/`200` (permiso) y la tarjeta
tiene que decirlo (Requisito 1.6) en vez de «error».

**Decisión**: la API distingue ese rechazo (`MetaAPIError.code in {10, 200,
190}` con mensaje de permiso) y devuelve `catalog_permission_missing`; la
consola lo traduce a «La conexión de WhatsApp no incluyó el permiso de
catálogo. Vuelve a conectar el número para concederlo». Los números
conectados antes del cambio en el panel de Meta necesitan reconectarse
(supuesto de la spec).

**Pendiente antes de cerrar la iteración 1, en staging**: el owner añade
`catalog_management` a la configuración del Embedded Signup en el panel de
Meta (las dos configuraciones: Cloud API y coexistencia), reconecta el
`+34653321693` y la lista de catálogos aparece. Sin eso, todo el plan queda
en «dice qué falta».

---

## D6 · La capacidad aparece solo con catálogo

`requires_connector` hoy devuelve un slug de conector. **Decisión**: ampliarlo
a un requisito de tipo `channel_catalog` (el canal que atiende tiene
`catalog_id`), para que `catalog.search_products` y «Enviar productos del
catálogo» (`response.send_interactive` con `products`) no aparezcan en
Capacidades sin catálogo, y aparezcan encendidos por defecto con él. Las
plantillas «de venta» son `woocommerce_sales_v1`, `inventario_v1` y
`restaurante_v1`; las demás las traen apagadas.

---

## Lo que la investigación corrigió de la spec

Nada de fondo. Un matiz: «Enviar productos del catálogo» no es una
herramienta nueva sino la misma `response.send_interactive` con `products`;
en Capacidades se enseña con nombre propio pero por dentro es un modo de la
que ya existe. Las tareas lo tienen en cuenta.
