# Quickstart — cómo se comprueba la 076

Las rutas de archivo de las pruebas son las que propone el plan. `tasks.md` las fija.

## En local

Base y Redis propios, para no pisar a otra sesión:

```bash
export NEXUS_DATABASE_URL=postgresql+asyncpg://nexus:nexus@localhost:5433/nexus_test_076 NEXUS_REDIS_URL=redis://localhost:6379/13
```

```bash
./scripts/verify.sh lint
```

API: migración, servicios y endpoints.

```bash
cd apps/api && uv run pytest tests/unit/test_076_referral_whitelist.py tests/unit/test_076_phone_hash.py tests/unit/test_076_event_rules.py -x
```

```bash
cd apps/api && uv run pytest tests/integration/test_migration_0241_ad_conversions.py tests/integration/test_076_enqueue.py tests/integration/test_076_ad_measurement_endpoint.py tests/integration/test_076_ads_report.py tests/integration/test_076_lite_ad_origin.py -x
```

Aislamiento: las tres pruebas nuevas y los barridos que ven las tablas y rutas nuevas.

```bash
cd apps/api && uv run pytest tests/isolation/test_076_ad_click_customer_axis.py tests/isolation/test_076_conversion_events_tenant.py tests/isolation/test_076_logs_carry_no_click.py tests/isolation/test_21_rls_covers_every_tenant_table.py tests/isolation/test_43_force_and_composite_fk_sweep.py tests/isolation/test_22_tenant_delete_leaves_nothing.py tests/isolation/test_console_scope.py tests/isolation/test_lite_route_scope.py tests/isolation/test_lite_bodies_only_in_inbox.py -x
```

Worker: la nota del agente, el despachador, la retención y el contrato de nombres.

```bash
cd apps/api && uv run --with lupa pytest ../worker/tests/unit/test_076_ad_note.py ../worker/tests/unit/test_076_conversion_dispatcher.py ../worker/tests/unit/test_076_ad_click_retention.py ../worker/tests/unit/test_076_inbound_referral.py ../worker/tests/unit/test_bootstrap_split.py -x
```

Canales: el adaptador ya tiene su fixture `message_with_referral.json`.

```bash
cd apps/channels && uv run pytest tests/test_meta_webhook_adapter_2026.py -x
```

Consola y móvil:

```bash
cd apps/console && pnpm vitest run src/components/builder src/components/inbox "src/app/(console)/clients" src/i18n
```

```bash
cd apps/console && pnpm build
```

```bash
./scripts/verify.sh mobile
```

Antes de pasar a `develop`, todo junto:

```bash
./scripts/verify.sh
```

## En staging, con el número de Auphere

**Requisitos previos.** Algunos los hace Luis en Meta: el plan no crea nada allí.

1. **Luis** crea en Meta dos configuraciones de registro insertado de pruebas, copias de las de Cloud API y de Coexistencia con el permiso `whatsapp_business_manage_events`. Sus ids van en `NEXUS_META_CONFIG_ID_WA_EVENTS_TEST_CLOUD_API` y `NEXUS_META_CONFIG_ID_WA_EVENTS_TEST_COEXISTENCE` de la API de staging.
2. Se pone `NEXUS_AD_MEASUREMENT_TENANTS` con el tenant de Auphere en la API y el worker de staging.
3. Se pone `NEXUS_META_CAPI_TEST_EVENT_CODE` con el código de Events Manager → Orígenes de datos → Eventos de prueba.

**Escenarios**, en orden. Cada uno dice qué historia demuestra.

| # | Qué se hace | Qué tiene que pasar | Historia |
|---|---|---|---|
| 1 | Desde un anuncio de clic a WhatsApp de prueba de Auphere, se escribe al número | La Bandeja lite enseña «Desde un anuncio: <titular>», y el agente lo sabe si se le pregunta | 1 |
| 2 | Se escribe sin anuncio desde otro teléfono | La Bandeja no enseña nada de anuncios | 1 |
| 3 | En la página del número se activa «Resultados de anuncios» | Primero pide volver a conectar. Tras hacerlo con la configuración de pruebas, el diálogo pide confirmar y la sección queda «Activa», con el conjunto de datos vinculado | 3 |
| 3b | **Desconocido 0**: después de reconectar, se escribe al número y el agente contesta | El número sigue recibiendo y enviando, con el mismo PIN y la misma configuración. Si no, se aplica la alternativa de research D6 | 3 |
| 4 | **Desconocido 1**: con el escenario 3 hecho, se comprueba que la creación del conjunto de datos respondió 200 | Si no, se aplica la alternativa de research («Desconocidos») | 3 |
| 5 | Desde el chat del escenario 1, se pide una reserva al agente | En menos de una hora aparece un `Purchase` con el precio en los Eventos de prueba de Meta, una sola vez | 3 |
| 6 | Desde el chat del escenario 2 (sin anuncio), se pide una reserva | Aparece un `Purchase` sin clic. **Desconocido 3**: si Meta pide una Página, la sección dice «Vincula una página de Facebook a este número» | 3 |
| 7 | Se cancela desde la consola la reserva del escenario 5 | Aparece un `OrderCanceled` | 3 |
| 8 | Se crea una reserva desde la consola | No sale nada a Meta | 3 |
| 9 | Se abre la pestaña Anuncios del cliente en la consola de partners | Una fila con el anuncio de prueba, sus conversaciones y la reserva no cancelada con su importe | 2 |
| 10 | **Desconocido 2**: los escenarios 3 a 6 con un número en coexistencia, reconectado con su configuración de pruebas | Si funciona, se quita la exclusión de coexistencia (research D10) | 3 |
| 11 | Se desactiva la medición y se pide otra reserva | No sale nada, y la auditoría nombra a quien la desactivó | 3 |

## La solicitud a Meta (historia 4)

Cuando los escenarios 1 a 9 pasan:

1. Se graba el vídeo: inicio de sesión con la sesión cerrada, reconexión con la configuración de pruebas y su pantalla de permisos, chat desde el anuncio, reserva del agente y evento en Eventos de prueba. En 1080p o más, interfaz en inglés o con rótulos, y sin audio.
2. **Luis** cambia la descripción guardada en el borrador de revisión (`submission_id=1125440307039671`) por una que cuente este uso.
3. **Luis** sube el vídeo, revisa las respuestas de tratamiento de datos (sin Railway), marca las certificaciones y envía.
4. Con el acceso avanzado concedido, **Luis** añade el permiso en Meta a las configuraciones de Cloud API y de Coexistencia. Se quitan las dos variables `NEXUS_META_CONFIG_ID_WA_EVENTS_TEST_*`.
5. Con el nivel completo de la API de marketing (1.500 llamadas correctas en 15 días), se pone `NEXUS_AD_MEASUREMENT_GENERAL_AVAILABILITY=true` en producción, que pasa por Terraform.

## Docs que cambian en el mismo commit que el código

- `docs/canales.md`: el origen de anuncio de WhatsApp, la medición por número y su disponibilidad.
- `docs/consola-lite.md`: «Desde un anuncio» en la Bandeja.
- `docs/console.md`: la pestaña Anuncios y la sección «Resultados de anuncios» del número.
- `docs/reservas.md`: los eventos de conversión al crear y cancelar.
