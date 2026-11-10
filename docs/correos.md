# Correos de la plataforma

Cómo envía correo la plataforma desde la spec 051 (`specs/051-correos-con-oficio/`). Estado al **2026-10-30**: construido; las plantillas están publicadas en Resend; falta el paso por staging.

---

## 1 · En una frase

Todo correo es un **tipo** del catálogo (`services/email_catalog.py`) y se envía con **una plantilla publicada en Resend**. El código pone el asunto y las variables; **el cuerpo vive en Resend**, y ahí se edita.

```
sitio que envía ──► send_localized / send_template ──► modo «resend» ──► POST api.resend.com/emails {template: {id: alias, variables}}
                                                     ├► modo «access» ──► igual que «resend» si el tipo es de acceso; si no, al registro
                                                     └► modo «log»    ──► email.suppressed en el registro (nada sale)
```

No hay HTML en el código. Si un sitio necesita mandar algo que el catálogo no tiene, se añade un tipo (§5), no se escribe un correo a mano. Un barrido lo vigila: `tests/unit/test_email_no_inline_html.py`.

---

## 2 · Quién envía de verdad: el modo por entorno

| Entorno | `NEXUS_EMAIL_DELIVERY` | Qué pasa |
|---|---|---|
| producción | `auto` (por defecto) → `resend` | Sale todo. **Con `log` o `access`, la API y el worker no arrancan.** |
| staging | `auto` → `access` | Salen **solo los correos de acceso**. Todo lo demás queda en el registro. |
| local, CI | `auto` → `log` | No sale nada; todo queda en el registro. |

**Los correos de acceso** son los que alguien necesita para seguir operando:

- confirmar el alta;
- «ya tienes cuenta»;
- la invitación al equipo, también la de propietario que emite un operador desde el panel (spec 052), y la de cliente;
- restablecer la contraseña;
- el aviso de que la contraseña cambió.

**En staging, crear un partner en el panel escribe de verdad a la dirección que se ponga** (spec 052): es un correo de acceso.

Los provoca siempre una persona, a propósito. Lo que staging **no** envía es lo automático: recibos, cobros, alertas de saldo y consumo, avisos de la consola y alertas internas. Son los correos que escribirían a un cliente real sin que nadie lo pidiera. Cada ficha del catálogo dice si es de acceso (`EmailSpec.access`).

**La clave de Resend ya no decide si se envía; decide el modo.** Staging tenía la clave en su secreto y escribía a personas reales desde el dominio de producción. Quitar la clave lo habría apagado del todo, en silencio, y el día que alguien la volviera a poner habría vuelto a escribirlo todo. Staging **necesita** la clave para los correos de acceso.

**Para probar en staging una plantilla que no es de acceso**, se pone `NEXUS_EMAIL_DELIVERY=resend`. No basta con desplegar: la variable no está en ninguna definición de tarea, así que hay que añadirla en el bloque de staging de `common_env` (`infra/terraform/20-services/taskdefs.tf`) y aplicar Terraform. El arranque lo deja escrito como `warning` (`email.delivery_mode` con `real_email_outside_production=true`), para que se encuentre y se quite. `NEXUS_EMAIL_DELIVERY=log` apaga también los de acceso.

---

### La monitorización no va por Resend

Las alertas del vigilante de la plataforma —cola atascada, mensajes en la DLQ, ráfaga de errores de turno, modelo sin responder en las pruebas, servicio sin latido, caché degradada, fallos de envío a Meta— y la conciliación diaria con Meta **ya no salen por Resend** (spec 051, requisito 9). Quedan en el registro de `/nexus/<entorno>/scheduler` con nivel de error:

- `platform_alert`, con `kind`, `subject` y `detail`;
- `ops.meta_reconciliation`, con el día y los canales afectados.

Quien avisa a una persona es una alarma de CloudWatch por cada tipo (`infra/terraform/30-observability/alarms.tf`). En producción, el aviso es un correo de AWS que sale del topic `nexus-prod-alerts`, cuya única suscripción es `contacto@ladrian.dev`.

| Alarma (`nexus-prod-…`) | Salta cuando |
|---|---|
| `platform-alert-queue-backlog` | la entrada más vieja de una cola lleva más de 5 min sin procesarse |
| `platform-alert-dlq-entries` | muere un mensaje de cliente nuevo, aunque queden viejos en la DLQ. Qué hacer: [`dlq.md`](dlq.md) |
| `platform-alert-turn-error-burst` | un negocio lleva más de 5 turnos fallidos en 10 min |
| `platform-alert-simulated-model-failure-burst` | un cliente lleva más de 5 turnos o pasadas sin respuesta del modelo en el chat de prueba o en las pruebas, en 10 min |
| `platform-alert-worker-dead` | un servicio lleva más de 3 min sin latido |
| `platform-alert-cache-ratio-low` | el prompt cache lee menos del 30 % en la hora |
| `platform-alert-meta-failure-burst` | más de 20 envíos a Meta fallan con el mismo código en 10 min |
| `meta-reconciliation` | la conciliación diaria encuentra mensajes de Meta sin guardar |

Cómo se comportan:

- **Un aviso por avería, no uno por hora.** El vigilante repite cada hora lo que sigue roto; la alarma avisa al empezar, sigue en ALARM y vuelve a OK tras 3 h sin registrarse. Volver a OK no manda nada.
- **La DLQ no repite: avisa por lo nuevo.** Registra una vez por cada tanda de entradas nuevas, así que vuelve a OK aunque queden entradas viejas y lo siguiente que muera vuelve a avisar. Si repitiera, una cola que nadie vacía dejaría la alarma encendida para siempre y un mensaje de hoy no avisaría a nadie.
- **Un tipo no tapa a otro.** Por eso hay una alarma por tipo: con la DLQ en ALARM, un `worker_dead` sigue avisando.
- **El correo dice qué mirar, no cuánto.** Lleva la consulta de Logs Insights y, el de la DLQ, el comando. Mientras la alarma sigue en ALARM no se vuelve a avisar: lo que muere en esas 3 h va en el mismo aviso.
- **Si cae el `scheduler` entero, no suena ninguna**, porque nadie registra. El correo de Resend tenía el mismo punto ciego. La DLQ avisa cuando vuelve, porque su marca no caduca.
- **En staging existen y no avisan a nadie.** Staging aparca sus servicios de noche y cada mañana registra un `worker_dead` que no es un fallo.

**El chat de prueba y las pruebas no cuentan para `turn_error_burst`.** Esa alerta escribe `platform.turn_error_burst`, y de ahí sale un WhatsApp al dueño del negocio: un partner que prueba su borrador no puede despertarlo. Por eso tienen su tipo, `simulated_model_failure_burst`, sin fila de auditoría (`apps/worker/src/nexus_worker/simulation/failures.py`). Al revés no se cubre todo: `turn_error_burst` solo cuenta los turnos de canal que lanzan una excepción, y un fallo del modelo en un canal no lanza, porque el handler responde con el texto de emergencia y pasa a una persona.

Un tipo nuevo necesita su línea en `platform_alert_kinds`; `apps/worker/tests/unit/test_platform_alarms_contract.py` falla si falta.

**Estado a 2026-11-03:** aplicadas en staging, donde no envían nada. Sin aplicar en producción: hay que aplicarlas allí al pasar la spec 051 a `main` (CE-006); hasta entonces, el aviso sigue siendo el correo de Resend de producción.

**Datadog no está montado.** La propuesta del 30 de octubre no consta aprobada, y en la cuenta de AWS no hay ningún filtro de suscripción, rol ni recurso suyo. Si se aprueba, será otra spec.

La ráfaga de errores de un negocio sigue avisando además por WhatsApp a los operadores, como antes. Las dos alertas internas que piden trabajo a una persona, la consulta de soporte y la petición de borrado de cuenta, siguen saliendo por correo de Resend.

---

## 3 · Qué queda en el registro

Cada correo retenido deja un `email.suppressed`:

| Campo | Qué es |
|---|---|
| `kind` | el tipo del catálogo |
| `template` | el alias de Resend que se habría usado |
| `to` · `subject` | destinatarios y asunto, ya construidos |
| `links` | **solo** las variables que la ficha marca como enlaces de acción (restablecer, invitación, alta…) |
| `owner` · `partner_id` · `tenant_id` · `client_ref` | de qué negocio es (garantía de aislamiento 6) |

**Ninguna otra variable se registra**: ni un nombre, ni un importe, ni el texto de una consulta.

**Los enlaces de acción sí se registran.** En staging, los correos de acceso salen de verdad y no pasan por aquí. En local y en CI, el registro es la única forma de completar un alta, una invitación o un restablecimiento. La spec 011 había descartado escribir el enlace en los registros «porque es cómo un secreto acaba en producción». Lo que lo hace aceptable ahora es la guardia de §2: producción no puede retener nada.

En staging, con Logs Insights sobre los grupos de la API y del worker:

```
fields @timestamp, kind, template, subject, links.RESET_URL, links.ACCEPT_URL
| filter event = "email.suppressed"
| sort @timestamp desc
```

En local:

```bash
docker compose logs api | grep email.suppressed
```

---

## 4 · Las plantillas

- **Dónde**: en la cuenta de Resend, con alias `auphere-<plantilla>-<es|en>`. Son 20 plantillas: 19 para clientes y partners, en español y en inglés, y una interna solo en español. En total, 39 alias.
- **El texto inicial** de cada una está en `specs/051-correos-con-oficio/contracts/catalogo.md`, y la guía de redacción en `contracts/redaccion.md`. El HTML inicial está en `evidence/plantillas-iniciales/`. **La versión vigente es la de Resend**: si se cambia allí, esos documentos no se actualizan.
- **Formato**: HTML de correo (tablas, estilos en línea, alternativa para Outlook), no el editor visual. El editor visual no se puede publicar por API sin abrir cada plantilla en el panel (`research.md` R10).
- **Idioma**: cada correo sale en el de la cuenta de consola de quien lo recibe (`console_auth.principals.locale`). Sin cuenta conocida, en español. Un correo a varias personas sale una vez por idioma.
- **Remitentes**: `Auphere <billing@auphere.com>` para recibos y cobros; `Auphere <notifications@auphere.com>` para todo lo demás. Las respuestas van a `support@auphere.com`, salvo la petición interna de borrado de cuenta, que responde a quien la pidió.
- **El asunto lo pone el código**, en el idioma del envío, y pisa el de la plantilla. Así sale entero en el registro de staging y su regla (≤ 60 caracteres, que diga de qué va) se prueba.
- **Escapado**: el código escapa toda variable de texto antes de enviarla. La documentación de Resend no dice si lo hace. La única variable que lleva marcado es la de líneas (`EmailLines`), que el código escapa línea a línea y une con `<br>`.

### Cambiar el texto de una plantilla

1. Editarla en el panel de Resend, **en los dos idiomas**, siguiendo `contracts/redaccion.md`.
2. Publicarla.
3. Pasar la comprobación:

   ```bash
   cd apps/api && NEXUS_RESEND_API_KEY=re_… uv run python scripts/check_email_templates.py
   ```

   Falla si una plantilla:

   - no existe, no está publicada o declara variables distintas de las del código;
   - no lleva la firma o tiene más de un botón;
   - usa una muletilla de la lista o una palabra de dentro («tope», «bolsa», «máquinas»);
   - o, en el aviso de contraseña cambiada, lleva algún enlace que no sea `mailto:`.

**No va en CI**: CI no tiene la clave de Resend, y no debe tenerla. Se ejecuta antes de pasar a producción.

### Lo que no se puede cambiar solo en Resend

Las **variables**. Si una plantilla necesita una variable nueva, la tiene que enviar el código: se añade a la ficha del tipo y a cada sitio que lo envía. La comprobación falla mientras la plantilla y el código no coincidan.

---

## 5 · Añadir un tipo de correo

1. El texto, en los dos idiomas, en una fila nueva de `contracts/catalogo.md`.
2. Un miembro de `EmailKind` y su ficha en `CATALOG`:
   - variables;
   - cuáles son enlaces de acción;
   - de qué negocio es (`partner`, `client` o `none`);
   - remitente.
3. Las plantillas `auphere-<tipo>-es` y `-en` en Resend, publicadas.
4. El sitio que envía llama a `send_localized(EmailKind.X, to=…, compose=…, partner_id=…)`.
   - **Si el tipo es de un partner, `partner_id` es obligatorio**; si es de un cliente, `tenant_id` o `client_ref`.
   - Lo comprueba un barrido: `tests/isolation/test_55_email_owner_tagging.py`.
5. La comprobación de plantillas, en verde.

### Avisos de la consola

Los avisos de la consola (`console_notifications.emit`) que salen por correo usan las plantillas genéricas `partner_notice` y `client_notice`. Su texto por tipo de aviso vive en el código, en `services/email_notices.py`, porque son casi treinta con la misma forma (`research.md` R6 bis).

Un tipo de aviso nuevo que pueda salir por correo **necesita su fila allí**. Si no la tiene, sale el texto genérico y queda `email.notice_without_copy` en el registro. La prueba `test_email_notices.py` falla antes de que eso llegue a producción.
