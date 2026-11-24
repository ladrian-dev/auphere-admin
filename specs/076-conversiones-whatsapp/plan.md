# Implementation Plan: Conversiones de anuncios de WhatsApp

**Branch**: `076-conversiones-whatsapp` | **Date**: 2026-11-24 | **Spec**: [spec.md](./spec.md)

**Input**: Feature specification from `/specs/076-conversiones-whatsapp/spec.md`

## Summary

Siete requisitos sobre código que ya existe. Se añaden tres tablas, dos bucles del worker y ninguna dependencia:

1. **Origen de anuncio.**
   - El webhook deja pasar el `referral` de Meta al stream, con lista blanca y topes.
   - El worker guarda cada clic en `customer_ad_referrals`.
   - El agente lo recibe cercado como dato, solo dentro del ciclo actual de la conversación.
   - Un cron borra el identificador del clic a los 90 días.
2. **Bandeja lite.** La conversación enseña «Desde un anuncio: <titular>». La consola de partners no tiene Bandeja con conversaciones; eso se corrigió en la spec al planificar.
3. **Informe.** Una pestaña «Anuncios» del cliente en la consola de partners: por anuncio, conversaciones, reservas del agente e importe, en 7, 30 o 90 días.
4. **Medición por número.**
   - Una sección propia en la página del número, con confirmación de qué sale a Meta.
   - Comprueba el permiso del token con `debug_token`, y crea u obtiene el conjunto de datos de Meta.
   - Si falta el permiso, pide volver a conectar. Reconectar deja de chocar con la cuota de números.
5. **Qué se encola.** Dentro de la transacción de quien crea el resultado:
   - reserva del agente: `Purchase`, o `LeadSubmitted` si no tiene precio;
   - pedido de WooCommerce del agente: `OrderCreated`;
   - cancelación de una reserva con evento: `OrderCanceled`, que espera a que salga el original.
   - Se atribuye con el último clic del mismo contacto y del mismo número.
   - Sin nada de quien tiene una baja activa en ese número.
6. **Cómo se envía.** Un despachador en `egress`, copiado del de push:
   - un evento por petición, con clic o teléfono en SHA-256;
   - reintentos acotados y nada de más de 6 días y 23 horas;
   - logs sin el clic ni el teléfono.
7. **El permiso en Meta.** Dos configuraciones de pruebas solo para staging, una por modo, que la API elige según el número. Los pasos de Luis en Meta están en el quickstart.

Las decisiones y sus alternativas están en [research.md](./research.md). Las tablas, en [data-model.md](./data-model.md). Las fronteras, en [contracts/api-y-eventos.md](./contracts/api-y-eventos.md).

## Technical Context

**Language/Version**: Python 3.11 (API, worker, canales, herramientas) · TypeScript 5 con React 19 (consola)

**Primary Dependencies**: FastAPI, SQLAlchemy 2 async, Alembic, Pydantic 2, httpx y tenacity (`MetaClient`), structlog · Next.js 16 App Router, `@nexus/ui`, Zod. **Ninguna nueva.** El SHA-256 es `hashlib`.

**Storage**: PostgreSQL con RLS FORCE por `tenant_id`. Una migración: `0241_ad_conversions`, con tres tablas y una fila de vocabulario de auditoría.

**Testing**: pytest (API: `tests/unit`, `tests/integration`, `tests/isolation`; worker: `tests/unit`; canales) · Vitest con Testing Library (consola)

**Target Platform**: AWS ECS (API, `runner`, `scheduler`, `egress`) · Vercel (consola)

**Project Type**: servicio web con worker y consola

**Performance Goals**:
- El despachador barre cada 60 s y hace una llamada a Meta por evento. El volumen es de reservas y pedidos del agente, no de mensajes.
- El informe es una consulta por cliente, sobre a lo sumo 90 días, con los índices de `customer_ad_referrals` y `reservations`.
- La nota del agente es una lectura indexada más por turno.

**Constraints**:
- Nada sale a Meta de un número sin la medición activa (está apagada por defecto) ni de un tenant fuera de la lista o de la apertura general.
- La app móvil de hoy sigue funcionando: solo se regeneran sus tipos.
- Nada se crea en Meta desde el código.

**Scale/Scope**: 7 requisitos y 46 criterios. Unos 35 archivos de código y 20 de pruebas, en `apps/api`, `apps/worker`, `apps/channels`, `apps/mcp` y `apps/console`.

## Constitution Check

*PUERTA: se rellena antes de la Fase 0 y se vuelve a comprobar después del diseño.*

| # | Principio | ¿Cumple? | Prueba / justificación |
|---|---|---|---|
| I | Aislamiento entre tenants; `tenant_id` del contexto, nunca del llamante; whitelist exhaustiva | ☑ | Garantías **1, 6 y 8**. Las tres tablas llevan FORCE RLS y FK compuestas, y las barren `test_21`, `test_43` y `test_22`. El conjunto de datos y el token salen de la fila del propio tenant, nunca del evento ni de la petición: `tests/isolation/test_076_conversion_events_tenant.py`. El clic de un contacto nunca se muestra, ni llega al agente, ni atribuye a otro: `test_076_ad_click_customer_axis.py`. Los logs llevan `tenant_id` y nunca el clic ni el teléfono: `test_076_logs_carry_no_click.py`. No hay herramientas nuevas, así que `test_51` no cambia. |
| II | Corte por superficie de confianza | ☑ | Superficie `0`, declarada en la spec. El flujo nuevo de datos hacia Meta lleva su lectura de RGPD en research D11. |
| III | Lo leído es dato, nunca instrucción | ☑ | El texto del anuncio llega al agente saneado (`_safe_ad_text`) y cercado con `TAG_AD_REFERRAL`, sin clic ni URL (research D2). Una prueba mete instrucciones, saltos y caracteres de formato en el anuncio. El stream solo admite claves de la lista blanca. |
| IV | Acción `mutates` con aprobación durable; la auditoría nombra a la persona | ☑ | No hay acciones nuevas del agente. Activar o desactivar la medición lo hace una persona en la consola, con confirmación explícita (requisito 4.8). Queda en `audit_log` con su actor, y la acción tiene su fila de vocabulario. |
| V | Estados honestos; la ausencia se diseña | ☑ | Sin la medición disponible, el bloque no existe (research D10). El estado dice el último error y qué hacer. El informe tiene cargando, error con reintento y vacío explicado. La Bandeja no pinta nada sin anuncio. |
| VI | Por API `console.*`, nunca navegando la consola | ☑ | Ningún agente navega nada. |
| VII | Test primero; el criterio de aceptación es el test; nada de `skip` | ☑ | Cada fase de `tasks.md` empieza por sus pruebas en rojo. El hash del teléfono se prueba con el ejemplo publicado por Meta. |
| VIII | Licencias leídas enteras | ☑ | Dependencias nuevas: ninguna. |
| IX | La KB es dueña del porqué; la spec enlaza a su nota | ☑ | `[[research/2026-11-24-conversiones-whatsapp]]`. La nota apunta a `specs/076-conversiones-whatsapp`. |

**Después del diseño:** se mantiene. El diseño añadió dos bucles del worker y un ajuste de disponibilidad, dentro de la superficie `0`. No añadió dependencias ni herramientas.

### Las tres puertas que `/speckit-tasks` comprueba

| Puerta | Respuesta | Tarea que la cubre |
|---|---|---|
| **Aislamiento** — ¿qué garantías toca? | **1**: tablas, conjunto de datos y token por tenant (requisito 6.5). **8**: clic y evento del mismo contacto (requisitos 1.6 y 6.6). **6**: logs con tenant y sin clic ni teléfono (requisito 6.7). | Una tarea por garantía en `tests/isolation/` (`test_076_*`), más los barridos existentes en verde |
| **Licencias** — ¿qué dependencia nueva entra? | Ninguna | No aplica |
| **Medidor** — ¿qué gasta y dónde lo ve el partner? | Nada nuevo. Meta no cobra la API de conversiones. La nota del anuncio es una línea del turno, que ya se mide en la bolsa. | No aplica |

**Complejidad que hay que justificar:** ver Complexity Tracking.

## Project Structure

### Documentation (this feature)

```text
specs/076-conversiones-whatsapp/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/api-y-eventos.md
├── checklists/requirements.md
└── tasks.md                          # lo crea /speckit-tasks
```

### Source Code (repository root)

```text
apps/api/
├── alembic/versions/0241_ad_conversions.py              # nuevo: 3 tablas + vocabulario
├── src/nexus_api/
│   ├── config.py                                        # disponibilidad y test_event_code
│   ├── core/tenant_context.py                           # conversation_context
│   ├── core/guardrails/untrusted.py                     # TAG_AD_REFERRAL
│   ├── db/models/ad_conversion.py                       # nuevo
│   ├── api/webhooks/meta.py                             # referral_json en el stream
│   ├── services/ad_conversions.py                       # nuevo: atribución, reglas, encolar, informe
│   ├── services/ad_measurement.py                       # nuevo: disponibilidad, permiso, conjunto de datos
│   ├── services/reservations/core.py                    # ganchos en create_booking y cancel_booking
│   ├── api/console/channel_config.py                    # bloque ad_measurement y PUT
│   ├── api/console/ads.py                               # nuevo: informe
│   ├── api/console/whatsapp.py                          # la cuota no cuenta el número que se reconecta
│   ├── api/console/lite/inbox.py                        # ad_origin
│   └── api/console/audit_words.py                       # etiqueta de la acción nueva
└── tests/{unit,integration,isolation}/                  # test_076_*.py

apps/channels/src/nexus_channels/whatsapp_meta/
└── meta_client.py                                       # token_scopes, ensure_dataset, send_conversion_event

apps/worker/
├── src/nexus_worker/
│   ├── config.py                                        # retención y ritmo del despachador
│   ├── streams/consumer.py                              # _to_event lee referral_json
│   ├── runtime/dispatcher.py                            # InboundEvent.referral; guarda el clic
│   ├── persistence/ad_referrals.py                      # nuevo
│   ├── runtime/pipeline.py                              # _ad_note y conversation_context
│   ├── conversions/dispatcher.py                        # nuevo: bucle de egress
│   ├── streams/ad_referral_retention_cron.py            # nuevo: cron del planificador
│   └── bootstrap.py                                     # los dos bucles, en sus conjuntos
└── tests/unit/                                          # test_076_*.py y test_bootstrap_split.py (ALL_EXPECTED)

apps/mcp/src/nexus_mcp/servers/
├── reservas/tools.py                                    # _turn usa la conversación del turno
└── woocommerce/tools.py                                 # encolar OrderCreated

apps/console/src/
├── lib/backend/channel-config.ts · lib/backend/ads.ts · lib/backend/inbox.ts · lib/backend.ts
├── app/(console)/clients/[ref]/agents/channel-actions.ts          # activar y desactivar
├── app/(console)/clients/[ref]/ads/{page,loading,error}.tsx       # nuevo
├── components/builder/channel-page.tsx                            # monta la sección
├── components/builder/ad-measurement-section.tsx                  # nuevo
├── components/ads/ads-report.tsx                                  # nuevo
├── components/clients/v2/client-header-v2.tsx · components/shell/routes-v2.ts   # pestaña
├── components/inbox/{thread-header,contact-panel}.tsx
└── i18n/lanes/{builder,inbox,ads}.ts

apps/mobile/src/api/{openapi.json,schema.gen.ts} · apps/mobile/src/i18n/lite.gen.ts   # regenerados

infra/terraform/                                         # variables nuevas, solo staging al principio

docs/canales.md · docs/consola-lite.md · docs/console.md · docs/reservas.md   # en el mismo commit que lo que describen
```

**Structure Decision**: no hay estructura nueva. Cada cambio va en el archivo que ya tiene esa responsabilidad.

Los archivos nuevos son:
- la migración y su modelo;
- dos servicios de la API (`ad_conversions`, `ad_measurement`);
- el router del informe;
- la persistencia de clics;
- los dos bucles del worker;
- y la sección y el informe de la consola.

`conversions/` es una carpeta nueva del worker, al lado de `push/`, porque copia su patrón de egress.

## Orden de entrega

Cada historia se puede fusionar sola, en el orden de la spec:

1. **Historia 1, origen de anuncio (P1).**
   - La migración entra entera aquí, con las tres tablas, para no encadenar migraciones.
   - Incluye: stream, worker, nota del agente, Bandeja lite y retención.
   - No necesita nada de Meta.
2. **Historia 2, informe (P2).** Solo lee lo de la historia 1 y las reservas.
3. **Historia 3, medición en Meta (P2).**
   - **Primero, los desconocidos de research**, en staging con las configuraciones de pruebas que crea Luis:
     - que reconectar un número vivo es seguro;
     - crear el conjunto de datos con acceso estándar;
     - eventos con y sin clic;
     - coexistencia.
   - Si el primero sale que no, se aplica su alternativa antes de seguir.
   - Después: medición, encolar, despachador y la reconexión sin choque de cuota.
4. **Historia 4, el permiso (P3).** Vídeo y solicitud, que son pasos de Luis en Meta (quickstart), y la apertura general por Terraform.

## Complexity Tracking

| Añadido | Por qué hace falta | Alternativa más simple descartada |
|---|---|---|
| `conversation_context` en `core/tenant_context.py`, y que `reservas._turn` lo use primero | Sin él, un pedido de WooCommerce no sabe de qué número viene. Y una reserva sin `conversation_id` del modelo cae a «la última conversación de la persona», que puede ser de otro número del mismo negocio: el evento iría a otra cuenta de WhatsApp | Leer `nexus_worker.runtime.turns.current_turn()` desde las herramientas: obliga a que la API dependa del worker |
| La cuota no cuenta el número que se reconecta | Sin eso, un cliente en su tope de números no puede volver a autorizar el suyo (409) y nunca puede activar la medición | Subir la cuota a mano a cada cliente que active: opaco y propenso a errores |
| Un despachador en `egress` en vez de reutilizar `reservation_outbox` | Esa cola no llama a nada externo, sus tipos están limitados con CHECK y su recorrido salta a los tenants sin Reservas, que es justo el caso de WooCommerce | Un tipo más en `reservation_outbox`: mete una llamada HTTP dentro de su transacción y no ve a los tenants sin Reservas |
