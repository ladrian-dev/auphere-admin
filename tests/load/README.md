# tests/load — pruebas de carga WP-15

Corren contra **staging** (jamás prod). Requisitos: `k6` local
(`brew install k6` o `docker run --rm -i grafana/k6`), perfil AWS `nexus`,
y el seed sintético cargado (`scripts/seed_synthetic.py`).

## Rampa del webhook

```bash
k6 run tests/load/webhook_ramp.js \
  -e BASE_URL=http://<alb-dns> \
  -e META_APP_SECRET=<NEXUS_META_APP_SECRET de nexus/staging/app> \
  -e PHONE_NUMBER_ID=+56990000000 \
  -e TARGET_TPM=1500
```

Perfil: 2 min de calentamiento → **15 min sostenidos a TARGET_TPM** →
pico 10x durante 2 min → recuperación. Umbrales k6: ack p95 < 150 ms
(incluye red; el SLI real `webhook_ack_ms` p95 < 50 ms se lee en
CloudWatch) y error rate < 0,5%.

**Criterio de salida de Fase 1 (plan §WP-15)** — durante los 15 min
sostenidos, verificar en CloudWatch (namespace `Nexus`):

- `queue_oldest_pending_seconds` < 30 en ambos streams;
- `turn_latency_ms` p95 < 8 s;
- `webhook_ack_ms` p95 < 50 ms.

Ojo con el coste: 1.500 turnos/min × 15 min = **22.500 turnos con llamada
LLM real**. Ajustar `TARGET_TPM` al presupuesto de la key de staging, o
correr la rampa completa solo en la validación formal de la fase.

## Chaos: matar un runner a mitad de turno

```bash
AWS_PROFILE=nexus ./tests/load/chaos_kill_runner.sh staging
```

Con la rampa corriendo, mata una réplica del runner, espera la reposición
y ejecuta la verificación SQL de las dos invariantes (task efímera):
**cero salientes duplicados** (mismo wamid respondido 2 veces) y **cero
entrantes sin respuesta**. Exit != 0 = invariante violada.

## Dos schedulers sin duplicados (criterio del plan)

```bash
AWS_PROFILE=nexus aws ecs update-service --cluster nexus-staging \
  --service nexus-staging-scheduler --desired-count 2 --region eu-south-2
# ... 15 min después, revisar CloudWatch /nexus/staging/scheduler:
# cada tick debe loggear UNA ejecución (advisory lock WP-08), y volver a 1:
AWS_PROFILE=nexus aws ecs update-service --cluster nexus-staging \
  --service nexus-staging-scheduler --desired-count 1 --region eu-south-2
```
