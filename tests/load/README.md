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

## Coste, y por qué la campaña va en dos fases

El tramo sostenido son 22.500 turnos, pero **el perfil completo son
~79.000**: el pico 10x (1 min de subida + 2 min arriba + 2 min de bajada a
250 rps) mueve más mensajes que los 15 minutos sostenidos enteros. A
Sonnet 4.6 con ~5k in / 200 out por turno eso es del orden de **$1.400** de
Anthropic real — la key de `nexus/staging/app` es una key de verdad.

De ahí la separación (decidida el 2026-08-09):

1. **Rampa de infraestructura, coste ~0.** Se corre contra los tenants
   sintéticos de `seed_synthetic.py`, que **no tienen `agent_configs`**: el
   turno muere en el runner antes de llamar al LLM. Valida exactamente lo
   que es infraestructura — ack del webhook, ALB, HMAC, XADD, claim del
   consumer, autoescalado de api/egress, chaos y los dos schedulers.
2. **Corrida de latencia, corta y pagada.** Un tenant con `agent_config`
   real y un TPM bajo para medir `turn_latency_ms` p95 y el coste por
   turno, y extrapolar.

Lo que la fase 1 NO demuestra: que `queue_oldest_pending_seconds` aguante
bajo turnos de verdad. Un turno que falla en 20 ms nunca hace cola. Ese
SLI solo cuenta medido en la fase 2 (o en una rampa completa pagada).

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
