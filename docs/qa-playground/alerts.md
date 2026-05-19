# QA Playground — Alerts contract

Referencia: ADR-020 (Fase 6, Bloque E).
Runbook: [`runbook.md`](./runbook.md).

Este documento es el **contrato** de las alertas del QA Playground.
Define las señales, los umbrales, el canal de aviso y el dueño. La
implementación del sink (Slack / PagerDuty / digest diario) no vive
aquí — vive en la capa de observabilidad cuando llegue. Hasta entonces,
los contadores ya están expuestos en proceso (ver
`apps/api/src/nexus_api/core/metrics.py`) y se leen vía
`counters.snapshot()` desde un dashboard interno.

## Métricas emitidas

| Métrica | Tipo | Labels (sufijos en el counter) | Hook |
|---|---|---|---|
| `qa.thread.created` | counter | `:tenant=<uuid>`, `:operator=<uuid>` | `POST /qa/threads` |
| `qa.side_effect.blocked` | counter | `:tool=<name>` | `make_qa_audit_writer()` |
| `qa.audit.write_failed` | counter | `:tool=<name>` | `make_qa_audit_writer()` (except) |
| `qa.run.duration_ms.sum` / `.count` | counter pair (suma + nº de runs) | — | Pendiente runtime live |

Notas:
- El backend actual es la clase `Counters` in-process. Cuando el
  exporter Prometheus aterrice (no en este alcance), las mismas claves
  se exponen 1:1; no hace falta cambiar nada en las llamadas.
- Los histograms reales (`p95`, `p99`) requieren un backend que los
  soporte. La pareja `.sum / .count` permite calcular **promedio** ya
  hoy; los percentiles esperan al runtime live + Prometheus.

## Traces Langfuse

`qa_run_metadata(operator_id, tenant_id, qa_thread_id)` en
`apps/worker/src/nexus_worker/runtime/qa_pipeline.py` devuelve la
metadata canónica para tagear el run en Langfuse:

```python
{
  "qa": True,
  "qa.operator_id": "<uuid>",
  "qa.tenant_id":   "<uuid>",
  "qa.thread_id":   "<uuid>",
}
```

El `LangGraph Server` debe pasarla como `metadata` en el `RunnableConfig`
de cada invocación. Sin eso, los runs QA se mezclan con producción y el
dashboard filtrado `qa = true` queda vacío.

## Contrato de alertas

| Alerta | Trigger | Canal | Dueño | Cuándo escalar |
|---|---|---|---|---|
| `qa_audit_write_failed_rate` | `qa.audit.write_failed` rate > 0 over 5min | **Page on-call (Slack #ops-page)** | Plataforma | Inmediato — la persistencia rota = los operators no ven evidencia de side-effects bloqueados. |
| `qa_side_effect_blocked_anomaly` | `qa.side_effect.blocked` ≥ 3× la mediana de los últimos 7 días, por tool | **Daily digest (#ops-daily)** | Plataforma | Solo si la anomalía persiste 24h. Puede ser un agente nuevo agresivo, no necesariamente un bug. |
| `ucm_shadow_diff_nonzero_rate` | `ucm.shadow_diff != equivalent` rate > 1% over 1h | **Silent log (structured)** | Plataforma (revisión semanal) | Si > 5% sostenido → escalar a #ops-daily. Es shadow validation; no afecta producción todavía. |
| `qa_run_duration_p95` | `qa.run.duration_ms` p95 > 30s over 1h | **Daily digest (#ops-daily)** | Plataforma | No escala salvo > 60s sostenido. Probable LLM provider degradado. |
| `qa_thread_created_spike` | `qa.thread.created` > 100 / 5min para un mismo `operator_id` | **Silent log** | Plataforma | Detecta scripts / loops por error. No es de seguridad — el operator está autenticado. |

### Reglas de oro

1. **`qa.audit.write_failed` es la única señal pageable.** El resto
   son daily-digest o silent-log. El operator del Playground está en
   sandbox por construcción — las alertas existen para detectar
   degradación de observabilidad, no incidentes de seguridad. Los
   incidentes de seguridad reales se enforcen vía RLS / WITH CHECK
   y vía la suite isolation, no vía alertas.

2. **Los counters por-label** (`:tenant=`, `:operator=`, `:tool=`)
   permiten partir cualquier alerta por dimensión sin re-instrumentar.
   El alerting layer debe poder leer `counter.snapshot()` y
   pattern-match las claves.

3. **Sin alertas sobre métricas que requieren histograms** hasta que
   exista el backend. Hoy, p95 / p99 no son observables.

4. **El sink (Slack, PagerDuty, email)** queda fuera de este
   documento. El contrato es: "esta métrica en esta condición = esta
   acción"; el plumbing es de otra capa.

## Smoke check manual (sin Prometheus)

Hasta que el exporter aterrice, este snippet en `python -c` es
suficiente para verificar que los contadores se mueven:

```python
from nexus_api.core.metrics import counters
print({k: v for k, v in counters.snapshot().items() if k.startswith("qa.")})
```

Esperado tras una sesión QA real:
- `qa.thread.created >= 1`
- `qa.side_effect.blocked >= 0` (cero si el agente no llamó tools)
- `qa.audit.write_failed == 0` (cualquier valor > 0 = page)

## Pendiente (no bloquea Fase 6)

- [ ] Exporter Prometheus sobre `Counters.snapshot()` montado en
      `/metrics`. Hoy no existe.
- [ ] Histogram real para `qa.run.duration_ms` (requiere backend).
- [ ] Wiring del runtime live para emitir `qa.run.duration_ms.{sum,count}`
      cuando un turn cierra. Vive con la pieza SSE pendiente del
      cierre de Fase 5.
- [ ] Sink real de alertas (Slack webhook + cron diario).
