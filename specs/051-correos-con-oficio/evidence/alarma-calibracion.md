# Calibración de las alarmas de la plataforma (R9.4 a R9.9)

Medido el 2026-11-03 en la cuenta 793033583982, `eu-south-2`, con los `platform_alert` de `/nexus/<entorno>/scheduler`. Producción, 90 días, con el primer registro el 21 de agosto; staging, 30 días, que es su retención. Ningún otro grupo los registra: `api`, `runner`, `metering` y `egress` dieron 0.

```
filter event = "platform_alert" | fields @timestamp, kind | sort @timestamp asc | limit 10000
```

`ops.meta_reconciliation` dio 0 registros en los dos entornos. El cron no existe aún en `main`, y en staging no ha encontrado diferencias en estos 30 días.

## Cuántos avisos habría dado cada ventana

Un aviso es un paso de OK a ALARM. La ventana es `period × evaluation_periods`, con `period = 300`. La simulación cuenta uno cada vez que el registro llega tras más tiempo que la ventana desde el anterior del mismo tipo, así que es un techo: CloudWatch agrupa en tramos de 5 minutos y podría dar menos.

| Entorno | Tipo | Registros (hoy, un correo cada uno en prod) | Ventana 1 h | 2 h | **3 h** | 6 h |
|---|---|---:|---:|---:|---:|---:|
| prod | `dlq_entries` | 1630 | 1579 | 1 | **1** | 1 |
| prod | `cache_ratio_low` | 26 | 24 | 20 | **20** | 19 |
| staging | `dlq_entries` | 69 | 60 | 2 | **2** | 2 |
| staging | `worker_dead` | 44 | 29 | 28 | **28** | 28 |
| staging | `cache_ratio_low` | 3 | 2 | 2 | **2** | 2 |
| staging | `queue_backlog` | 1 | 1 | 1 | **1** | 1 |

- **La ventana de 1 h no sirve.** El vigilante repite cada hora y casi siempre la supera por segundos: pasa en 1578 de los 1629 huecos de `dlq_entries` en producción, y ninguno llega a 2 h. Cada una de esas veces la alarma podría volver a OK y avisar otra vez.
- **Se eligen 3 h y no 2 h** para aguantar una repetición perdida: dos repeticiones seguidas ya distan 2 h.
- **`cache_ratio_low` da 20 avisos del 21 de agosto al 15 de octubre, y ninguno desde entonces.** Es casi el mismo ritmo que el correo, y es una señal de coste, no una avería. Si resulta molesto, se sube su umbral en el vigilante. No lo cambia esta enmienda.

## Por qué una alarma por tipo

Con una sola alarma para todos los tipos y la misma ventana, producción habría dado 4 avisos: 3 de `cache_ratio_low` antes del 27 de agosto y 1 de `dlq_entries` ese día (la primera entrada, a las 22:01 UTC). Después se queda en ALARM para siempre y **se come los otros 17 avisos de `cache_ratio_low`**. Un `worker_dead` en esas semanas tampoco habría avisado.

## Por qué en staging no avisan

Los 44 `worker_dead` de staging son casi todos el aparcamiento (`20-services/staging_parking.tf`): los servicios paran a las 03:00 y arrancan a las 09:00, hora de Madrid, y el `scheduler` ve al `runner` y al `egress` sin latido desde hace unas 6 h justo al despertar. Serían 28 correos falsos en 30 días. Además, el topic de staging tiene 0 suscriptores: 44 mensajes publicados en 90 días, 1 entregado.

## Los filtros, contra una línea real

Con `aws logs test-metric-filter`. La primera línea es real, copiada de `/nexus/prod/scheduler` y recortada solo en `detail`; la segunda sigue la forma de `_alert()` en `meta_reconciliation_cron.py`, porque aún no hay ninguna registrada.

| Línea | `platform_alert` | `ops.meta_reconciliation` |
|---|---|---|
| `{"kind": "dlq_entries", …, "event": "platform_alert", "level": "error", …}` | coincide | no |
| `{"day": "2026-11-02", …, "event": "ops.meta_reconciliation", "level": "error", …}` | no | coincide |
| `{"event": "platform_watcher.start", …}` | no | no |
| `INFO: texto plano` | no | no |

## El canal de aviso

| | Producción | Staging |
|---|---|---|
| Suscripciones del topic | 1 confirmada, `contacto@ladrian.dev` (correo) | 0 |
| Publicados, 90 días | 30 | 44 |
| Entregados, 90 días | 24 | 1 |
| Fallidos, 90 días | 0 | 0 |

## El plan de Terraform, sin aplicar

Terraform 1.15.8, con `-lock=false` y `-target` sobre los cuatro recursos de la enmienda. En los dos entornos: **9 a crear, 0 a cambiar, 0 a destruir**, y el topic sin cambios.

| | Producción | Staging |
|---|---|---|
| Filtros | `nexus-prod-platform-alert`, `nexus-prod-meta-reconciliation` | `nexus-staging-…` |
| Alarmas | 6 `nexus-prod-platform-alert-*` y `nexus-prod-meta-reconciliation` | las mismas, `nexus-staging-…` |
| `actions_enabled` | `true` | `false` |
| Dimensiones | solo `kind`; la conciliación, ninguna | igual |
| Ventana | 300 s × 36, 1 punto | igual |

Lo que añadiría un `apply` sin `-target`, que no es de esta enmienda:

| Entorno | Sin `-target` | Efecto |
|---|---|---|
| prod | `aws_sns_topic_subscription.email` a crear | Existe en AWS y no en el estado. Con el mismo destino, SNS debería devolver la suscripción existente |
| staging | 6 alarmas pierden `ok_actions` y `aws_sns_topic_subscription.email` a crear | Manda un correo de confirmación que alguien tendría que abrir |
| staging, sin `-var grafana_enabled=true` | **11 recursos de Grafana a destruir** | Grafana está en marcha en staging |

## Lo que no está comprobado

- **La ventana en AWS.** Las cifras de arriba son una simulación de cómo evalúa CloudWatch. Se comprueba en T035, con el `dlq_entries` de staging: la alarma tiene que seguir en ALARM entre dos repeticiones.
- **Los 15 minutos de R9.4.** Se miden en T036.
- **`ops.meta_reconciliation` en producción.** No se puede probar hasta que `develop` llegue a `main`.

## Después de esta calibración: la DLQ ya no repite

El arreglo `dlq-sin-salida` (2026-11-03) hace que `dlq_entries` se registre por cada tanda de entradas nuevas, no cada hora. Las cifras de arriba siguen valiendo para los tipos que repiten. Con las mismas 25 muertes de producción, la DLQ da 6 registros en vez de 1658 y 1 aviso por el incidente, y un mensaje nuevo con esas 25 dentro da un aviso más en vez de ninguno. La ventana de 3 h no cambia. Ver `.specify/bugs/dlq-sin-salida/assessment.md`.
