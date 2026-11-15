# Investigación: Aparcar el router y gobernar el precio por modelo

Cada decisión dice qué se eligió, por qué y qué se descartó. Las rutas son del repo.

## D1 — Un solo registro de los modelos por defecto

**Decisión.** `apps/worker/src/nexus_worker/platform_models.py` gana
`default_models() -> dict[str, str]`, que devuelve un mapa `uso → modelo` con todo lo
que la plataforma resuelve por defecto en el proceso que lo llama:

- **Del worker** (`WorkerSettings`): `classify`, `classify_fallback`, `respond` y
  `respond_fallback` (`bootstrap.py:271`, la reserva es el mismo modelo), `extract`
  y `simulation`.
- **De `PLATFORM_MODELS`**, con su variable de entorno: `build`, `read_source`,
  `sector`, `customer_sim` y `judge`.
- **Del Playground**: `qa_classify` y `qa_respond`. Pasan a leer `classify` y
  `respond` (D13).
- **El freno de reservas**: `booking_brake`, que es `classify`
  (`booking_brake.py:384`).
- **De la API** (`nexus_api.config.Settings`): `improve`, `companion`,
  `transcribe`, `vision`, y `knowledge_embedding` si está configurado.

**Por qué.** El requisito 1.1 pide que un valor por defecto nuevo quede protegido
sin tocar la regla. Por eso el test del registro (T002) **barre**: recorre todos los
campos `*_model` de `WorkerSettings` y de `Settings`, y todas las claves de
`PLATFORM_MODELS`. Falla si alguno no está en `default_models()` ni en la lista de
exclusiones con su motivo (constitución §I: barrer, no enumerar). La API ya importa
la configuración del worker en tiempo de ejecución (`api/admin/sector_tests.py:255`
y `router_policies.py:257`), así que el registro sirve a los dos procesos sin dar
la vuelta a las dependencias del paquete.

**Descartado.**
- Variables `NEXUS_LLM_*` en la tarea de la API por Terraform: Luis lo descartó, y
  dos listas de variables divergen.
- Un módulo en `nexus_api`: tendría que importar `WorkerSettings` al cargar.
- `cheapest_model()`: no es un valor por defecto. Elige entre los activos en cada
  llamada, y marcar uno «No disponible» solo cambia su elección.

## D2 — El worker publica los modelos que usa de verdad

**Decisión.** El latido del worker (`nexus_worker/health.py`, `SETEX 60` cada 20 s
en `nexus:health:{service}:{instance}`) deja de escribir `"1"` y escribe un JSON:

```
{"v": 1, "models": default_models()}
```

La API lee esas claves. Las de valor `"1"`, las ilegibles o las de otra versión
cuentan como **sin publicar**.

**Regla de la API** (`services/model_usage.py`):

1. Calcula su propio `default_models()`.
2. Exige al menos un latido vivo con modelos publicados.
3. Exige que la parte del worker de cada latido coincida con la que calcula ella.
   La parte del worker es `WORKER_USES` (responder, clasificar, sus reservas, el
   freno de reservas, el calificador, extraer, simular y las tareas de
   `PLATFORM_MODELS`). Las claves que resuelve la API con su propio entorno
   (companion, visión, evaluaciones, Playground…) no se comparan: que el worker
   las vea distintas no es un desacuerdo.

Si falta cualquiera de las tres, rechaza la acción con `defaults_unverified` y dice
cuál falló. Para proteger se usa la **unión** de lo calculado y lo publicado.

**Por qué.** El valor del latido ya caduca solo: un worker parado deja de contar en
60 segundos. `/health/workers` (`nexus_api/health.py:98`) solo mira si la clave
existe, así que cambiarle el valor no lo rompe. Un worker de una versión anterior
escribe `"1"`, y durante el despliegue se rechaza: es lo seguro (requisito 1.5).

**Descartado.**
- Una tabla nueva: necesita su propia caducidad y una migración.
- Un canal de Redis: se pierde lo publicado mientras la API no escucha.

## D3 — Dónde vive la protección

**Decisión.** La protección va en `nexus_api/services/model_usage.py`, con
`uses_of(key) -> ModelUses`. Devuelve dos cosas:

- los usos por defecto (D1 y D2);
- los agentes y clientes que lo usan: `scan_agents(default_respond=…)` con
  `fixed_on == key`, más los clientes con **cualquier** asignación a ese modelo en
  `tenant_model_bindings` (todos los roles).

`announce_retirement` y `mark_unavailable` (`services/model_lifecycle.py`) lo llaman
**antes** de abrir la transacción y lanzan `LifecycleError("model_in_use")`. El
endpoint lo traduce a `409` con el detalle (contrato §2). El panel recibe los mismos
usos en cada fila (`uses`), y por eso no ofrece las dos acciones: la ausencia se
diseña (§V). Aun así, la API las vuelve a comprobar (requisito 1.4).

**Por qué en el servicio y no en el endpoint.** El cron (`_retire_due`) y cualquier
script futuro pasan por el servicio.

**Por qué todos los roles de asignación.** Un cliente con el clasificador asignado a
un modelo pierde su clasificador si ese modelo cae. No queda mudo, porque hay
reserva, pero cambia de comportamiento sin que nadie lo decida.

## D4 — El camino de vuelta

**Decisión.**
- `cancel_retirement(key, actor, reason)`: `retiring → active`, con
  `retire_after = NULL` y la auditoría `deployment.retirement_cancelled`. Los avisos
  pendientes ya no salen, porque `run_lifecycle` solo recorre los `retiring`.
- `restore_available(key, actor, reason)`: `unavailable →` el estado que tenía,
  guardado en una columna nueva, `model_profiles.status_before_unavailable`. Si es
  NULL (marcado antes de esta spec), se lee el `before.status` de la última
  auditoría `deployment.unavailable`. Si tampoco existe, vuelve a `draft`, que no
  sirve a nadie. No pasa por `activate_deployment`: es deshacer, no activar.

Las dos acciones pasan por la publicación del catálogo (`publish_catalog_change`).

**Descartado.** Leer solo la auditoría: es frágil y no se consulta en una
transacción con `FOR UPDATE`.

## D5 — La retirada que llega con agentes dentro (1.8)

**Decisión.** En `_retire_due`, antes de mover a nadie, se calculan las propuestas.

- **Si alguna no tiene sustituto y «Automático» no puede atender a ese cliente**
  (`auto_servable`):
  - no se mueve ningún agente ni se retira el modelo;
  - se registra una vez al día la auditoría de plataforma
    `deployment.retirement_blocked`, con `agents = N`, deduplicada por fecha;
  - se emite el evento `model_lifecycle.retirement_blocked` (`warning`).
- **Si no**, sigue como hoy.

`DeploymentRow` gana `retirement_blocked_agents`: el número cuando el estado es
`retiring` y `retire_after <= now`. Modelos lo pinta como «Retirada detenida», fuera
de lo que oculta el requisito 2.

**Por qué.** Mover a «Automático» con el catálogo actual da `no_model`, comprobado en
producción con la vista previa. Es la mudez del riesgo, aplazada a una fecha.

## D6 — Fuera los avisos de precio (3.12)

**Decisión.** `add_price` deja de llamar a `_price_alerts`, y `run_lifecycle` deja de
emitir `model.price_change`. Se borran `_price_alerts`, `message_price_ratio`,
`PriceAlert` y `LifecycleReport.price_notices`, con sus tests, y
`NotificationKind.MODEL_PRICE_CHANGE` se queda sin emisor. `POST …/prices` deja de
devolver `alerts` (contrato §3).

`add_price` rechaza además una `valid_from` anterior a hoy con
`422 in_the_past` (4.4).

**Por qué borrar y no apagar con un flag.** Código sin llamante es lo que la
auditoría señaló: un flag apagado es otra pieza a medias.

## D7 — El multiplicador objetivo, como ajuste de plataforma

**Decisión.** La migración `0231_platform_settings`:

- crea `platform_settings`: `key text PRIMARY KEY`, `value jsonb NOT NULL`,
  `updated_at` y `updated_by`;
- siembra `('sale_multiplier', '2.2')`;
- no tiene RLS, como `model_profiles`: es un dato de plataforma sin cliente.

`nexus_api/metering/sale_policy.py` ofrece `target_multiplier()` con caché y la
misma caducidad que el catálogo (300 s), invalidada por `CATALOG_CHANGED`. Si la
lectura falla, devuelve `None`, nunca un valor inventado. Lo leen:

- `weight_drift`, que pasa a recibirlo como argumento en vez de leer la constante
  (`pricing_policy.py:233`);
- la comprobación al cargar el catálogo (`nexus_worker/metering/pricing.py:259`);
- `usage_overview.py:396`.

`QUOTA_FLOOR_MULTIPLIER` (1,5) sigue siendo una constante: el suelo no es un ajuste.
`QUOTA_TARGET_MULTIPLIER` se queda solo como valor de la siembra y de los tests.

**No se toca `_price_micros`** (`runtime/llm.py:661`): solo lo usa una llamada
enrutada, y el router no se toca (requisito 2.8).

**Descartado.** Una tabla de una sola fila para el multiplicador: una de clave y
valor sirve para el siguiente ajuste sin migración nueva.

## D8 — Editar los pesos

**Decisión.** Un endpoint propio, `PUT /admin/models/deployments/{id}/weights`, con
`{input, cache_read, output, reason}`. Rechaza:

- `partial_weights` (3.5);
- `below_floor`: cualquier carril con `peso × 10 < 1,5 × coste` del carril, con el
  carril en el detalle (3.4);
- `per_minute`: un modelo sin coste por tokens (3.11);
- `reason_required`.

Lo que guarda queda auditado como `deployment.weights_changed`, con antes y
después, y publica `CATALOG_CHANGED`.

`promote_subscriber.py` (worker) y `publish_catalog_change` (API) llaman además a
`metering.pricing.invalidate()`. El turno siguiente cobra con los pesos nuevos sin
esperar los 5 minutos de caché (3.2). El peso único antiguo no se toca: ya no cobra
(supuestos de la spec).

`PUT /admin/models/sale-policy` cambia el multiplicador. Rechaza un valor menor que
1,5. Con `apply_to_all = true`, en la misma transacción, pone a cada modelo con
coste por tokens los pesos propuestos, `round(m × coste ÷ 10, 6)`, y audita cada
uno.

**Descartado.** Reutilizar el `PATCH` general de despliegue: mezcla retención,
licencia y contrato, que el router aparcado no debe enseñar.

## D9 — Aparcar el router en el panel

**Decisión.** `apps/admin/src/lib/router-panel.ts` exporta
`ROUTER_PANEL_VISIBLE = false`, y es el único sitio. Lo leen:

- `nav.ts`, que filtra Router y Certificaciones, y con él la paleta de comandos;
- `router/page.tsx`, `router/anomalies/page.tsx` y `certifications/page.tsx`, que
  llaman a `notFound()`;
- `status/page.tsx`, que quita el bloque Router y las tres cifras del router;
- `models/*`, que quitan «Nuevo despliegue», «Activar», «Certificado en» y
  «Le falta».

La API y el worker no cambian por esto (requisito 2.8).

**Por qué una constante y no una variable de Vercel.** El menú se pinta en el
cliente, y una variable pública obligaría a configurar tres entornos. CE-005 pide
un solo ajuste, y una línea con un test que la fija lo es.

## D10 — La tabla de Modelos

**Decisión.** La tabla queda con cinco columnas:

| Columna | Qué enseña |
|---|---|
| Modelo | Nombre e id; chips de estado, «En uso» y «Retirada detenida» |
| Proveedor | Proveedor y residencia, en una celda |
| Coste por millón | Entrada / caché / salida, compacto |
| Venta por millón | Entrada / caché / salida, el multiplicador por carril y el chip «Desfasado» o «Bajo el suelo» |
| Acciones | «Precio» y un menú |

El menú ofrece «Pesos de venta», «Cancelar retirada» o «Volver a disponible», y al
final, separadas, «Retirar» y «No disponible». Estas dos solo aparecen si el modelo
no está en uso.

- **Cabecera:** el multiplicador objetivo con «Cambiar», y un texto que no promete
  protecciones (4.6).
- **Diálogo de coste:** precargado con el vigente y la fecha de hoy. Enseña el
  multiplicador por carril con el coste nuevo y los pesos actuales, y ofrece
  «Aplicar la propuesta de venta» (3.9 y 4.5).
- **Ancho:** cabe en el área de contenido a 1280 px. Se prueba con un test de
  componente que comprueba las columnas y con una captura en el pase vivo.

## D11 — Limpiezas

| Pieza | Decisión | Dónde |
|---|---|---|
| Rotar secret (5.1) | Fuera de la tabla y del formulario. La API conserva el campo: es una columna heredada | `auphere/channels/*` |
| Galería (5.2) | Se borra la carpeta | `qa/dev/ucm-gallery` |
| Beta (5.3) | `GET /admin/channels/whatsapp-login-beta` devuelve `configured` (= `meta_config_id_wa_login` no vacío). `channels-tabs.tsx` oculta la subpestaña sin él, y su página da `notFound()` | `whatsapp_login_beta.py`, `channels/*` |
| Juez (5.4, 5.5) | `judge_calibrated(session, model=…)` filtra por el `model_id` del despliegue juez, que es `default_models()["judge"]`. Lo llaman el worker (`agent_tests.py:427`) y la consola (`agent_tests.py:205`). La pantalla recibe `judge_model` y `judge_calibrated` | `services/testing/judge.py`, `api/admin/sector_tests.py` |
| Evaluación (5.6) | La API devuelve `bank_size = len(bank())`. La pantalla lo usa y deja de pintar `sector_pass_unedited_pct`; la API sigue guardándolo como NULL | `sector_tests.py`, `builder/eval/*` |
| Playground (5.7) | `QA_CLASSIFY_MODEL` y `QA_RESPOND_MODEL` salen de `default_models()` | `api/qa.py:569` |

## D12 — Números de Auphere

**Decisión.** La pantalla se rehace con `@nexus/ui` (`PageHeader`, `Table`,
`Dialog`, `EmptyState`), como Conectores:

- título «Números de Auphere», en español neutro y con los términos explicados
  («identificador del número en Meta»);
- un diálogo de alta y otro de edición, este con token, identificador y motivo;
- confirmaciones dentro de la página.

La API pasa `PATCH`, `POST` y desactivar a `require_operator` y audita con
`operator_actor(...)` y el motivo (6.4). Los 48 sitios restantes con
`admin:{token[:8]}` quedan fuera (spec).

## D13 — Pruebas

- **API:** pruebas de servicio para la protección, la vuelta, la retirada detenida,
  los pesos, el multiplicador y el registro; de endpoint para los códigos del
  contrato.
- **Worker:** la publicación del latido y la invalidación de precios.
- **Panel:** Vitest para el filtro del menú, las páginas con `notFound`, la tabla,
  la propuesta y el suelo, y el diálogo precargado.
- **Aislamiento:** `tests/isolation/test_model_usage_scan_rls.py` (T004).

Todas se escriben en rojo antes que su implementación (§VII). Las suites del worker,
`mypy --strict` y `next build` entran en la verificación final, como pide
`CLAUDE.md`.
