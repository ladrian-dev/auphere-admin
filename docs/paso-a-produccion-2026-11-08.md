# Paso a producción del 2026-11-08: develop → main

`main` no se despliega desde el 22 de octubre (`daf0ca15`). Entra todo lo de
`develop` desde entonces: Reservas (043, 044, 048 y la enmienda de la agenda nativa),
la fábrica de agentes y las bolsas (047), Instagram y Messenger en beta (049),
WhatsApp al día (050), correos (051, 054), invitar al propietario (052) y las
correcciones del QA (055, 056). Además, los arreglos de hoy: el clasificador, el freno
de citas en el Playground y las pruebas, el gasto del mes con bolsas, el aviso de
escalado, el precio leído de la web y las plantillas de Reservas automáticas.

Migraciones: de la `0165` a la `0228` (las plantillas automáticas no traen ninguna). La tarea de migración es **bloqueante**: si
falla, `deploy-prod` no rueda ningún servicio y producción sigue como estaba.

---

## La regla: primero la API, después las consolas

Igual que en el paso de las specs 031–041 (`docs/paso-a-produccion-031-041.md`): la
consola nueva habla con rutas que la API vieja no tiene. Se pausa antes de fusionar y
se suelta al final.

---

## 0 · Antes de fusionar

- [ ] **`ci` en verde** en el PR `develop` → `main` (corre las suites completas: es la
  única vez que corren desde el 2026-11-03).
- [ ] **Alarmas de la plataforma** (spec 051): aplicar `30-observability` en producción
  **con `-target`**: sin él crea `aws_sns_topic_subscription.alert_email`, que ya existe
  en AWS y no en el estado. Recursos: `aws_cloudwatch_log_metric_filter.platform_alert`,
  `aws_cloudwatch_log_metric_filter.meta_reconciliation`,
  `aws_cloudwatch_metric_alarm.platform_alert`, `aws_cloudwatch_metric_alarm.meta_reconciliation`
  y las de `alarms.tf` que el plan diga que cambian. Confirmar que llega el aviso.
- [ ] **DLQ de entrada de producción**: `./scripts/ops/dlq.sh prod list` (quedaban 25
  entradas del incidente de Aurora de agosto). Decidir y vaciarla (`docs/dlq.md`).
- [ ] **Secreto** `NEXUS_CUSTOMERS_APP_TOKEN_SECRET` presente en `nexus/prod/app`.
- [ ] **Correo**: plantillas de correo publicadas y `scripts/check_email_templates.py` en
  verde (`docs/correos.md`). Mirar el cupo de Resend (100 al día, compartido con staging).
- [ ] **Aviso de escalado por WhatsApp**: el número de avisos de Auphere registrado en
  producción (panel → canales de Auphere) con `alert_escalation_v1` aprobada en su WABA, en
  el idioma configurado. Sin él, a un cliente cuyo número no tiene la plantilla solo le
  llega la campana y el correo.
- [ ] **Plantillas de Reservas**: se crean solas en la WABA de cada cliente con Reservas y
  número de Meta (`reservation-templates-cron`, cada 15 min). Meta tarda de minutos a 72 h en
  revisarlas: hasta entonces, fuera de la ventana de 24 h no sale ningún aviso de Reservas.
- [ ] **Google del negocio**: con la agenda nativa, una conexión de Google del negocio solo se lee
  y bloquea a todo profesional que aún no tiene la suya. Donde cada profesional conecte su
  calendario desde Reservas › Ajustes, conviene quitar la del negocio.
- [ ] **Avisar a Andrés**: la agenda nativa revierte sus commits del 3 y 4 de noviembre
  (un agente con Google conectado ya no reserva en Google).

## 1 · Copia de la base

- [ ] Snapshot manual del clúster Aurora de producción.

## 2 · Pausar las consolas

- [ ] Vercel → `auphere-console` → Settings → Git: desactivar los despliegues automáticos.

## 3 · Fusionar y desplegar la API

- [ ] Fusionar el PR `develop` → `main` y aprobar `deploy-prod` (entorno `production`).
- [ ] En `/nexus/prod/migrate`, después de `alembic upgrade head`, el **paso automático a
  Reservas** (es la primera vez que corre en producción):
  - `reservations.auto_pass_done`: cuántos pasaron, se publicaron e importaron.
  - `reservations.auto_pass_failed`: un cliente que no pasó; con `no_partner`, el cliente
    no tiene partner y se queda como estaba.
  - `reservations.auto_pass_not_ready`: un agente que reserva en Google y cuyo cliente aún
    no puede reservar (sin horario, equipo o servicios). Sigue como estaba y su partner
    recibe un aviso.
- [ ] Salud contra el ALB, con el certificado verificado:

```bash
curl --resolve api.auphere.com:443:51.95.216.39 https://api.auphere.com/health
```

## 4 · Soltar las consolas

- [ ] Reactivar los despliegues de `auphere-console` y redesplegar el último commit de
  `main`. Desplegar el Admin desde `main`.

## 5 · Comprobar en producción

- [ ] **Clasificador**: en `/nexus/prod/runner`, `classify.unknown_label_using_fallback`
  cerca de cero y `handler.turn_complete` con intenciones `book`, `info` y `escalate`.
- [ ] **Una reserva por WhatsApp** desde un teléfono de prueba en un cliente con Reservas:
  la cita aparece en Reservas, sale como «Ocupado» en el Google del profesional que lo tenga
  conectado y lleva su recordatorio.
- [ ] **Pedir hablar con una persona**: la conversación queda «Necesita humano» y llega
  el aviso (campana, correo y WhatsApp).
- [ ] **Plantillas de Reservas**: en Reservas › Ajustes, las seis en revisión o
  aprobadas; en la auditoría, `reservations.template_requested`.
- [ ] **Gasto del mes** en el Panel del cliente distinto de cero tras unas respuestas.

## Si algo va mal

| Síntoma | Causa y salida |
|---|---|
| Consola: «sin acceso» | La consola nueva habla con la API vieja: esperar a `deploy-prod` o volver a la consola anterior en Vercel |
| La migración falla | Producción sigue con la versión anterior; corregir y relanzar |
| Un agente no reserva | Mirar `classify.unknown_label_using_fallback` (clasificador) y `reservations.auto_pass_*` (si pasó a Reservas) |
| No llega el aviso de escalado por WhatsApp | `operator_alerter.*` en el scheduler: sin plantilla en el número del cliente ni número de Auphere |
| Recordatorios que no salen | La plantilla no está aprobada todavía: dentro de 24 h sale el texto, fuera, `no_template` |
