# Observabilidad sin deriva — plan de implementación

> **Para agentes:** se ejecuta en una sola sesión, tarea a tarea, con `- [x]`. Nada se aplica en AWS: solo `init`, `validate`, `fmt` y `plan -lock=false`. Los commits los hace Luis.

**Objetivo:** que un `terraform plan` sin `-target` en `infra/terraform/30-observability` no enseñe nada inesperado en staging ni en prod.

**Arquitectura:** los valores que difieren por entorno pasan a `staging.tfvars` y `prod.tfvars`, y sus variables pierden el `default`: olvidar el fichero es un error, no una destrucción. Lo que existe a mano en prod entra con bloques `import`. Staging deja de tener suscriptor, y el código lo dice.

**Tecnología:** Terraform >= 1.9 (CI valida con 1.9.8), proveedor AWS 6.x.

**Flujo (`docs/spec-driven-development.md`):** §7, «refactor interno sin cambio de comportamiento: `writing-plans` basta». No es un cambio de comportamiento del producto, así que la regla de §2 no se dispara, y no es ninguna de sus tres excepciones.

---

## Lo que se comprobó antes de escribir esto (2026-11-03)

| Hecho | Cómo |
|---|---|
| Staging sin `-var`: `1 add, 6 change, 11 destroy` | Plan |
| Staging con `-var grafana_enabled=true`: `1 add, 6 change, 0 destroy` | Plan |
| Prod: `10 add` (9 de la spec 051, que faltan en prod, y la suscripción) | Plan |
| **La suscripción sí está en el estado de los dos entornos, con un ARN muerto**, con `pending_confirmation = true`. La real tiene otro ARN. El refresco borra la entrada y el plan la crea | `resource_drift` del plan |
| **El repo es público, y la suscripción de prod tiene `ConfirmationWasAuthenticated = false`.** Con su ARN, `sns:Unsubscribe` no pide firma: ese ARN no puede ir en ningún archivo | `gh repo view`, `sns get-subscription-attributes` |
| El proveedor no tiene fuente de datos de suscripciones | `terraform providers schema` |
| El runbook, `alarms_db_auth.tf` y el arreglo de raíz se escribieron en agosto y nunca se confirmaron. Están en `nexus-respaldos/2026-10-24/nexus-muna-2*` | `tar tzf`, `grep` y `git log --all` |
| **Un `import` a la misma dirección se ignora sin avisar**: Terraform ve la dirección ocupada, y el plan sigue diciendo `create` | Plan de prueba en una copia en la carpeta temporal |
| Cambiar de dirección y añadir `removed { destroy = false }` sí importa | Plan de prueba: `1 to import`, `forget` del antiguo |
| Hay **6** filtros a mano en prod, no 4: también `-metering` y `-egress` | `aws logs describe-metric-filters` |
| `alert_email = null` vale con una variable sin `default` | Plan de prueba en staging |
| Sin `-var-file` el plan falla con `No value for required variable`; con el fichero de otro entorno, con `Resource precondition failed` (exit 1) | Planes de prueba |

## Archivos

| Archivo | Qué |
|---|---|
| `infra/terraform/30-observability/staging.tfvars` (nuevo) | Valores de staging |
| `infra/terraform/30-observability/prod.tfvars` (nuevo) | Valores de prod |
| `infra/terraform/30-observability/main.tf` | Variables sin `default`, guarda del topic, suscripción con `count` |
| `infra/terraform/30-observability/grafana.tf` | `grafana_enabled` sin `default` |
| `infra/terraform/30-observability/alarms.tf` | `actions_enabled` en todas las alarmas |
| `infra/terraform/30-observability/alarms_db_auth.tf` (nuevo) | Los 6 filtros y las 2 alarmas hechos a mano, solo en prod |
| `infra/terraform/30-observability/imports.tf` (nuevo) | Bloques `import` y `removed`; se borra tras aplicar en los dos entornos |
| `infra/terraform/README.md` | Cómo planificar y aplicar; Grafana ya no va «apagado por defecto» |
| `docs/runbooks/aurora-password-rotation.md` (nuevo) | El runbook que citan las dos alarmas y no estaba en git |
| `specs/051-correos-con-oficio/plan.md` | Nota: las dos trampas del `apply` quedan resueltas |
| `.github/workflows/deploy-grafana.yml` | Comentario que decía «apagado por defecto» |

---

### Tarea 1: valores por entorno

- [x] Crear `staging.tfvars`: `state_bucket`, `grafana_enabled = true`, `grafana_image_tag = "staging"`, `alert_email = null`.
- [x] Crear `prod.tfvars`: `state_bucket`, `grafana_enabled = false`, `alert_email = "contacto@ladrian.dev"`.
- [x] Quitar el `default` de `grafana_enabled` y de `alert_email`, y añadir `nullable = false` en la primera. Las descripciones dicen que el valor sale de `<workspace>.tfvars`, porque es lo que se lee en el aviso interactivo.

### Tarea 2: staging sin suscriptor

- [x] Sustituir la guarda del topic:

```hcl
precondition {
  condition     = (var.alert_email != null) == local.alert_actions_enabled
  error_message = "alert_email no cuadra con el workspace ${terraform.workspace}: prod tiene que tener destinatario y staging ninguno. Lo normal es haber pasado el -var-file de otro entorno: usa ${terraform.workspace}.tfvars."
}
```

- [x] Renombrar la suscripción, porque `email` está ocupada por el ARN muerto:

```hcl
resource "aws_sns_topic_subscription" "alert_email" {
  count = var.alert_email == null ? 0 : 1

  topic_arn = aws_sns_topic.alerts.arn
  protocol  = "email"
  endpoint  = var.alert_email

  lifecycle {
    ignore_changes = [confirmation_timeout_in_minutes, endpoint_auto_confirms]
  }
}
```

- [x] Poner `actions_enabled = local.alert_actions_enabled` en las 6 alarmas que no lo tienen. El local se queda tal cual en `alarms.tf`: lo lee `test_platform_alarms_contract.py`, y ampliarlo a todas las alarmas es lo que decidió Luis.

### Tarea 3: traer lo que existe en prod

- [x] En `alarms_db_auth.tf`, los filtros con `for_each` sobre `api, egress, metering, runner, scheduler`, y el de `leader.term_failed`, con `default_value = "0"` y `unit = "Count"`, como están en AWS. Solo en prod, por `terraform.workspace`.
- [x] Las 2 alarmas, con la descripción literal de AWS y sus `ok_actions`: cambiarlas ahora sería un cambio mezclado con un import.
- [x] En `imports.tf`, un `removed` para `aws_sns_topic_subscription.email` y un `import` por cada recurso, con `for_each` sobre `terraform.workspace`.
- [x] El `id` de la suscripción sale de `var.alert_subscription_arn_to_import`, sin `default`: `null` en `staging.tfvars` y ausente de `prod.tfvars`, que recibe el valor por `TF_VAR_`.

### Tarea 4: runbook

- [x] Recuperar `docs/runbooks/aurora-password-rotation.md` del respaldo y corregirlo contra hoy: la rotación apagada, el arreglo de raíz sin confirmar, y `infra/scripts/refresh_app_secret.sh`. Cada comando se ejecuta en lectura antes de citarlo, y lo que escribe se marca como no ejecutado.

### Tarea 5: documentación

- [x] `infra/terraform/README.md`: sección de cómo aplicar `30-observability`, con planes en `*.tfplan` (git los ignora; `*.plan` no, y hay uno versionado en `20-services`).
- [x] Reescribir la sección de Grafana y el paso 3 de «Orden de aplicación».
- [x] Nota en `specs/051-correos-con-oficio/plan.md`. Comentario de `deploy-grafana.yml`.

### Tarea 6: verificar

- [x] `terraform fmt -check -recursive` en `infra/terraform`, y `terraform validate` con `init -backend=false`, con 1.15.8 y con la imagen `hashicorp/terraform:1.9`, sobre una copia.
- [x] `uv run pytest tests/unit/test_platform_alarms_contract.py` en `apps/worker`.
- [x] Plan de staging: esperado `0 add, 6 change, 0 destroy`, más el `forget` de la suscripción.
- [x] Plan de prod: esperado `9 import, 9 add, 2 change, 0 destroy`, más el `forget`. Los 2 cambios, solo `tags_all`.
- [x] Sin `-var-file` y con el fichero cruzado: los dos fallan.
- [x] Plan de solo lectura de `20-services` en staging y prod, para anotar la deriva en el informe sin arreglarla.
