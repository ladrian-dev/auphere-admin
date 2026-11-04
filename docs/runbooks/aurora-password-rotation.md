# Runbook · La contraseña de Aurora

Lo citan las alarmas `nexus-prod-db-auth-failures` y
`nexus-prod-scheduler-leader-failed`. Su caso es que un servicio se quede con una
contraseña de Aurora vieja. Esa contraseña rotó sola hasta que se apagó la rotación,
y el 2026-08-26 eso tiró producción durante 42 horas sin que nadie se enterase.

Se escribió la noche del incidente y nunca llegó a git. Se recuperó el 2026-11-03 de
`/Users/lmatos/Workspace/nexus-respaldos/2026-10-24/nexus-muna-2-sin-seguimiento.tgz`
y se corrigió contra lo que hay hoy.

## Estado a 2026-11-03

| Qué | Estado | Cómo se sabe |
|---|---|---|
| Rotación automática | **Apagada** en los dos secretos `rds!cluster-…`. Última vez: prod 2026-08-26, staging 2026-08-23 | `RotationEnabled = false`, `NextRotationDate` vacía. Ver el paso 1 |
| Decisión de qué hacer con ella | **Abierta**: «arreglarla o dejarla desactivada a sabiendas» | KB, `PLAN-PENDIENTE-CORTE-2026-09-08.md`, I3 |
| Arreglo de raíz | **No está en el código.** Se escribió en agosto y no se confirmó; las tareas de prod no llevan `NEXUS_DB_PASSWORD` | Búsqueda en todas las ramas, y `describe-task-definition` |
| Las 2 alarmas | En `OK` desde el 2026-08-27. Sin fallos de autenticación en los últimos 30 días | `describe-alarms` y la métrica `db_auth_failures` |

La descripción de la alarma dice «cada 7 dias». Era cierto cuando se creó. Hoy este
fallo solo aparece si alguien cambia la contraseña a mano o vuelve a encender la
rotación.

## Qué pasó el 2026-08-26

| Hora (UTC) | Qué |
|---|---|
| 26-ago 03:12 | Rota la contraseña maestra |
| 26-ago 04:08 | `scheduler`, `egress` y `metering` empiezan con `password authentication failed` en bucle |
| 26-ago 19:30 | Alguien actualiza las URLs de `nexus/prod/app` con la contraseña nueva |
| 26-ago 19:34 y 21:02 | Se reinician **solo** `api` y `runner`, que quedan sanos |
| 27-ago 22:00 | Se reinician los otros tres. Fin de la caída |

Consecuencias, todas silenciosas:

- Los **21 crons parados**. Cero recordatorios de cobranza dos días seguidos.
- **Egress mudo**: el agente contestaba y los mensajes se quedaban en `pending`.
- **Metering** mandando registros de consumo a la DLQ.

`GET /health/ready` devolvió `{"postgres":"ok","redis":"ok"}` todo el tiempo. Lo sirve
la API, que sí se había reiniciado: **salud en verde con media plataforma muerta.**

Detalle en la KB: `sessions/2026-08-26-muna-meta-verificada-agrupado-y-totales.md`.

## Por qué pasa

`nexus/<ws>/app` guarda la contraseña **incrustada dentro de las cuatro URLs**
(`NEXUS_DATABASE_URL`, `_DIRECT`, `_RO`, `DATABASE_URL`). Una task de ECS lee sus
secretos **al arrancar**, así que:

- si cambia la contraseña, las URLs del secreto quedan viejas;
- una task que no se reemplaza conserva la contraseña vieja en su entorno;
- una task que se reemplaza **después** de refrescar el secreto va bien.

PgBouncer no tiene ese problema de origen: toma la contraseña cruda del secreto de
RDS con `valueFrom` (`20-services/pgbouncer.tf`). Sí la coge solo al arrancar.

## Si suena la alarma

Todo con `AWS_PROFILE=nexus AWS_REGION=eu-south-2`. Los pasos 1 y 4 se ejecutaron tal
cual el 2026-11-03. **Los pasos 2 y 3 escriben y no se han vuelto a ejecutar desde
agosto.** Son lo que se hizo entonces, y su fuente es la KB y el propio script.

**1 · Confirmar que es esto.** Una task arrancada antes del último cambio de la
contraseña puede llevarla vieja; una arrancada después, no.

```bash
aws secretsmanager describe-secret --secret-id nexus/prod/app --query LastChangedDate --output text

rds=$(aws rds describe-db-clusters --db-cluster-identifier nexus-prod-aurora \
  --query 'DBClusters[0].MasterUserSecret.SecretArn' --output text)
aws secretsmanager describe-secret --secret-id "$rds" \
  --query '{cambio:LastChangedDate,rotacion:RotationEnabled,ultima:LastRotatedDate}'

for s in api runner scheduler egress metering pgbouncer; do
  t=$(aws ecs list-tasks --cluster nexus-prod --service-name "nexus-prod-$s" --query 'taskArns[0]' --output text)
  printf '%s: ' "$s"
  aws ecs describe-tasks --cluster nexus-prod --tasks "$t" --query 'tasks[0].startedAt' --output text
done
```

Si ninguna task es anterior a esos cambios, no es la contraseña: lee el error en el
registro del servicio.

**2 · Refrescar las URLs del secreto.**

```bash
AWS_PROFILE=nexus ./infra/scripts/refresh_app_secret.sh prod
```

Parte del secreto que hay, reescribe solo la contraseña de las cuatro URLs, y aborta
sin escribir si falta una clave que piden las tasks. No imprime valores.
**No uses `populate_app_secret.sh` para esto**: compone el JSON desde cero, y el
2026-08-19 se llevó así las 3 claves de la consola y ninguna task nueva arrancaba.

**3 · Forzar el despliegue de TODOS los servicios.** Es el paso que se hizo a medias
en agosto.

```bash
for s in api runner scheduler egress metering pgbouncer; do
  aws ecs update-service --cluster nexus-prod --service "nexus-prod-$s" --force-new-deployment
done
```

Rodar `pgbouncer` antes que los demás abre un hueco: el 2026-08-19 dejó 1316 líneas de
`password authentication failed` en PgBouncer y 30 en la API, todas dentro de esa
ventana, y ninguna después. Con tráfico real, rueda `api` y `pgbouncer` a la vez o
acepta el hueco a sabiendas.

**4 · Verificar de verdad**, no por `/health/ready`.

```bash
desde=$(python3 -c 'import datetime as d;print((d.datetime.now(d.timezone.utc)-d.timedelta(minutes=30)).strftime("%Y-%m-%dT%H:%M:%SZ"))')
hasta=$(python3 -c 'import datetime as d;print(d.datetime.now(d.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))')

# 0.0 si nadie ha fallado el login en la última media hora
aws cloudwatch get-metric-statistics --namespace Nexus --metric-name db_auth_failures \
  --statistics Sum --period 300 --start-time "$desde" --end-time "$hasta" --query 'sum(Datapoints[].Sum)'

aws cloudwatch describe-alarms --alarm-names nexus-prod-db-auth-failures nexus-prod-scheduler-leader-failed \
  --query 'MetricAlarms[].[AlarmName,StateValue]' --output text
```

Y que no queden mensajes atascados. Esta consulta es de agosto y no se ha vuelto a
ejecutar: las columnas siguen existiendo en el modelo, pero Aurora no es alcanzable
desde fuera del VPC.

```sql
SELECT status, count(*) FROM messages
WHERE direction = 'outbound' AND created_at > now() - interval '2 days'
GROUP BY 1;
```

## Detección

En `infra/terraform/30-observability/alarms_db_auth.tf`:

| Alarma | Qué mira | Umbral |
|---|---|---|
| `nexus-prod-db-auth-failures` | `password authentication failed` en `api`, `runner`, `scheduler`, `egress` y `metering` | Cualquier ocurrencia en 5 min |
| `nexus-prod-scheduler-leader-failed` | `leader.term_failed` en el scheduler | Más de 5 en 5 min (roto, 59; sano, 0) |

Las dos avisan a `nexus-prod-alerts` al saltar y al volver a OK. Para ver que la
suscripción sigue confirmada, esto tiene que devolver un ARN y no `PendingConfirmation`:

```bash
aws sns list-subscriptions-by-topic --topic-arn arn:aws:sns:eu-south-2:793033583982:nexus-prod-alerts \
  --query 'Subscriptions[].[Protocol,SubscriptionArn]' --output text
```

Se descartó una alarma de «el scheduler no completa tareas»: un scheduler sano puede
pasar una hora sin terminar un cron, y saltaba en falso. El fallo de liderazgo es
inmediato y denso.

## Antes de volver a encender la rotación

Encenderla tal como está hoy reabre el incidente: la contraseña sigue dentro de las
URLs, y cada rotación exigiría los pasos 2 y 3 enteros.

El arreglo de agosto hace que `NEXUS_DB_PASSWORD` llegue a todos los servicios por
`valueFrom` desde el secreto de RDS, y que `Settings._inject_db_password` pise con ella
la contraseña de las tres URLs. Está en
`/Users/lmatos/Workspace/nexus-respaldos/2026-10-24/nexus-muna-2.patch` (base
`19c050ea`), mezclado con cambios de cobranza; su prueba,
`test_db_password_injection.py`, está en el `.tgz` de al lado. Lleva dos meses sin
compilarse contra el código actual.

No cubre `DATABASE_URL` a secas, que usa `release.sh`: esa sigue leyendo el secreto de
la app, y hay que refrescarla igualmente.
