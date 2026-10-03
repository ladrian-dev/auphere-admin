# Implementation Plan: el catálogo en el número

**Branch**: `022-catalogo-en-el-numero` | **Date**: 2026-09-30 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `/specs/022-catalogo-en-el-numero/spec.md`

## Summary

El catálogo de Commerce Manager de Meta se enlaza al número de WhatsApp
**desde la tarjeta del número**, sin operador: la consola lista los catálogos
del negocio, el partner elige, y la API lo enlaza a la cuenta de WhatsApp
Business y lo guarda en el canal. La tarjeta adopta lo que Meta ya tenga,
cambiar pide confirmación, y desconectar deshace el enlace. Con catálogo, el
agente gana dos capacidades —buscar en el catálogo y enviar el producto como
tarjeta nativa— que sin catálogo no existen. El motor que envía las tarjetas
ya estaba; lo nuevo es cómo llega el catálogo al canal, que el agente pueda
leerlo, y que la consola lo cuente con la verdad.

## Technical Context

**Language/Version**: Python 3.14 (API, worker, MCP, canales) · TypeScript 5 / Next.js 16 (consola)

**Primary Dependencies**: FastAPI · SQLAlchemy async · el cliente de Meta existente (`nexus_channels.whatsapp_meta.meta_client`) · el registro de servidores internos de `apps/mcp` — **ninguna nueva**

**Storage**: PostgreSQL con RLS; tres claves más en `channels.config` (`catalog_id`, `catalog_name`, `catalog_checked_at`); una fila de vocabulario de auditoría; filas de `tool_catalog` para las dos herramientas. Redis para la caché de «catálogo enlazado» por WABA (5 min)

**Testing**: pytest (`unit`, `isolation`, `integration`) con Meta simulado por la costura `build_meta_client`; vitest en la consola; en staging con número real para D5

**Target Platform**: API y worker en AWS, consola en Vercel

**Project Type**: monorepo — servicio web + worker + consola

**Performance Goals**: la tarjeta del número no espera a Meta más de una vez por WABA cada 5 min; enlazar termina en menos de 3 s con Meta sano

**Constraints**: lo que Meta devuelve es dato (constitución III) · cambiar catálogo pide confirmación (IV) · sin catálogo la capacidad no aparece (V) · el token nunca llega al LLM ni a la consola

**Scale/Scope**: un catálogo por WABA; hoy tres clientes vivos en producción, uno con catálogo pendiente (Flor y Encanto)

## Constitution Check

| # | Principio | ¿Cumple? | Prueba / justificación |
|---|---|---|---|
| I | Aislamiento; `tenant_id` del contexto, nunca del llamante | ☑ | El catálogo cuelga del canal (RLS por `tenant_id`). Los catálogos que se listan salen del token del propio canal. Test en `tests/isolation/test_channel_catalog_scope.py`: un tenant no lista, no enlaza ni ve el catálogo de otro |
| II | Corte por superficie de confianza | ☑ | Superficie `0`. Tres llamadas más al mismo Meta con el mismo token |
| III | Lo leído es dato, nunca instrucción | ☑ | Nombres de catálogo y de producto se enseñan como texto; el `retailer_id` es un identificador que el motor reenvía, no interpreta. El token y el `catalog_id` nunca entran en el prompt |
| IV | Acción `mutates` con aprobación; auditoría nombra a la persona | ☑ | Enlazar, cambiar y desconectar auditan `console.channel.catalog` con `before/after`; cambiar pide confirmación en la consola (D4) |
| V | Estados honestos; la ausencia se diseña | ☑ | La tarjeta adopta la verdad de Meta (D3); sin permiso dice qué falta (D5); sin catálogo la capacidad no aparece (D6); «no se pudo comprobar» es un estado, no un silencio |
| VI | Por API `console.*`, nunca navegando la consola | ☑ | El Companion no entra |
| VII | Test primero | ☑ | Cada bloque tiene su test rojo antes; el de «Meta sin permiso» es el primero, porque es el modo de fallo que no controlamos |
| VIII | Licencias | ☑ | Ninguna dependencia nueva |
| IX | La KB es dueña del porqué | ☑ | Enlaza a la sesión del 2026-09-29/30; garantía 1 no cambia |

### Las tres puertas que `/speckit-tasks` comprueba

| Puerta | Respuesta | Tarea que la cubre |
|---|---|---|
| **Aislamiento** | Ninguna garantía cambia de promesa. Test nuevo porque entra una lectura de Meta por credencial de canal y un servidor interno que resuelve credenciales por conversación | `T-ISO` en `tests/isolation/` |
| **Licencias** | Ninguna dependencia nueva | `T-LIC` |
| **Medidor** | Nada nuevo: enviar una tarjeta ya cuenta como mensaje de canal; leer el catálogo no se mide (una llamada a Meta, como las de plantillas) | `T-MET` |

## Project Structure

### Documentation (this feature)

```text
specs/022-catalogo-en-el-numero/
├── plan.md · research.md · data-model.md · quickstart.md
├── contracts/catalog.md
└── tasks.md          # lo crea /speckit-tasks
```

### Source Code (repository root)

```text
apps/channels/src/nexus_channels/whatsapp_meta/
└── meta_client.py                           # list_catalogs, get_linked_catalog, link_catalog, unlink_catalog, search_products

apps/api/
├── alembic/versions/0134_audit_vocab_catalog.py      # console.channel.catalog
├── alembic/versions/0135_catalog_tools.py            # tool_catalog: catalog.search_products, catalog.get_product
├── src/nexus_api/
│   ├── api/console/channels.py              # GET …/catalogs · PUT/DELETE …/catalog · conciliación al listar
│   ├── api/console/schemas_channels.py      # catalog en ChannelDetailOut; CatalogOut
│   ├── api/console/capability_names.py      # requires «channel_catalog»
│   └── api/console/capabilities_client.py   # la capacidad solo con catálogo
└── tests/
    ├── unit/test_endpoint_console_catalog.py
    ├── unit/test_capabilities_catalog.py
    └── isolation/test_channel_catalog_scope.py

apps/mcp/src/nexus_mcp/servers/meta_catalog/  # search_products, get_product (credencial del canal de la conversación)
apps/worker/                                   # nada nuevo: send_interactive ya envía products

apps/console/src/
├── lib/backend/channels.ts                  # catalog, listCatalogs, setCatalog, clearCatalog
├── app/(console)/clients/[ref]/channels/actions.ts
├── components/channels/channel-card.tsx     # «Catálogo: …» · conectar / cambiar / desconectar
├── components/channels/catalog-picker.tsx   # la lista y la confirmación de cambio
├── components/channels/whatsapp-connect.tsx # ofrece el catálogo al terminar el alta
└── i18n/lanes/channels.ts
```

**Structure Decision**: un servidor interno nuevo (`meta_catalog`) porque la
herramienta necesita credenciales del canal, y ahí es donde viven las que las
necesitan. Todo lo demás crece sobre lo que hay.

## Fase 1 — diseño

| Artefacto | Qué fija |
|---|---|
| [`research.md`](research.md) | Las seis decisiones, incluida la que depende del panel de Meta (D5) |
| [`data-model.md`](data-model.md) | Las claves del canal, el vocabulario, las herramientas, la caché |
| [`contracts/catalog.md`](contracts/catalog.md) | Los cuatro endpoints y sus códigos |
| [`quickstart.md`](quickstart.md) | Qué se prueba en local con Meta simulado y qué exige staging |

### El orden de entrega

1. **Meta y la API**: cliente, endpoints, conciliación, auditoría, aislamiento.
   Con Meta simulado se cierra entera en local; con número real solo se
   confirma el permiso (D5).
2. **La tarjeta**: catálogo, conectar, cambiar con confirmación, desconectar,
   los tres estados de error. Historia 1 completa.
3. **El agente**: servidor `meta_catalog`, `tool_catalog`, capacidad
   condicionada, plantillas de venta. Historia 3.
4. **El alta lo ofrece**: Historia 2, sobre la tarjeta ya hecha.

## Complexity Tracking

| Añadido | Por qué hace falta | Alternativa más simple, y por qué no |
|---|---|---|
| Conciliación con Meta al listar canales (D3) | La tarjeta tiene que decir la verdad de Meta, y el catálogo se puede enlazar o quitar desde Commerce Manager | Enseñar solo lo nuestro: mentiría el primer día para Flor y Encanto y para la demo |
| Caché de 5 min por WABA | Sin ella, cada visita a Canales es una llamada a Meta por número | Sin caché: aceptable con tres clientes, no con treinta |
| Servidor interno `meta_catalog` | La herramienta necesita el token del canal por el que llegó la conversación; ese patrón ya vive en `apps/mcp` | Llamar a Meta desde el worker: rompería el corte «el worker no habla con proveedores salvo para enviar» |
| Un requisito de capacidad nuevo (`channel_catalog`) | `requires_connector` solo sabe de conectores | Fingir un conector «Catálogo de Meta»: la spec lo descarta a propósito |
