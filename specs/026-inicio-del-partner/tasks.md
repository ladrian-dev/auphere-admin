# Tasks: el Inicio le dice al partner qué hacer hoy

**Input**: `/specs/026-inicio-del-partner/` · **Tests**: no opcionales (§VII).

Reglas: cada tarea cita requisitos, se anota al entregarse, test primero,
trabajo en desarrollo y staging (clarificación del owner).

## Iteración 1 · lo urgente, lo pendiente, la tendencia, el crédito y la cartera

- [ ] T001 Snapshot ampliado en `apps/api/src/nexus_api/services/console_home.py`: escaladas recientes (D2), pagos pendientes, sin responder 7 días, calidad roja, reautenticación, borrador sin publicar de más de un día, WABA del cliente, última actividad y serie diaria de 14 días (D5). _Requisitos: 1.2, 2.1, 5.1_
- [ ] T002 `credit_burn(partner_id, tenant_ids, since)` en `apps/api/src/nexus_api/metering/wallet.py` (D4). _Requisitos: 4.1, 4.2_
- [ ] T003 Bloques `attention`, `to_review`, `conversations_trend`, `credit`, `portfolio` en `schemas_home_usage.py` y `home.py`, con permisos por bloque y sin `tenant_id`. _Requisitos: 1–5, 9.2, 9.3_
- [ ] T004 Tests en `apps/api/tests/unit/test_endpoint_console_home_v2.py`: gravedad y enlaces, escaladas con ventana, pagos y sin responder, variación 7/7, crédito y días, cartera, permisos (facturación), aislamiento entre partners, Playground excluido. _Requisitos: 1–5, 9_
- [ ] T005 [P] `Sparkline` y `delta`/`trend` en `Metric` (`packages/ui`), con tests. _Requisitos: 3.1_
- [ ] T006 Página del Inicio nueva y bloques en `apps/console/src/components/home/`: Necesita tu atención, Por revisar ahora, tarjetas, gráfica diaria apilada, Tus clientes, Actividad reciente (`auditV2`). Fuera «Calculado en X ms». Textos sin punto y coma. _Requisitos: 1–7_
- [ ] T007 Tests vitest de cada bloque (vacío, con datos, error parcial) y a11y de `/`. _Requisitos: 7, 9.2_
- [ ] T008 Verificación en la consola local con `scripts/dev_seed_console_volume.py`, merge a `develop`, staging, evidencia.

## Iteración 2 · el valor (rollup)

- [ ] T009 Migración `tenant_daily_stats` + cron horario + relleno de 90 días. _Requisitos: 3, 9.1_
- [ ] T010 Selector de periodo, resueltas por el agente, ventas por moneda y tiempo de respuesta. _Requisitos: 3.1–3.5_

## Iteración 3 · avisos

- [ ] T011 Emitir `channel.degraded` y `template.rejected`. _Requisitos: 8.1_
