# Pendientes tras el go-live del 2026-09-13

Lo que queda después de desplegar las cinco specs a producción. Cada punto lleva
lo que se verificó y dónde mirar, para que la próxima sesión no empiece
averiguando lo que ya se sabe.

**Estado de partida.** `main` en `89d93ef`, Alembic en `0117_billing_events`, los
cinco servicios de `nexus-prod` sanos, el cobro encendido en los dos entornos.
2 partners (`amacrux`, `facelad`) y 3 clientes finales, los tres con tráfico el
mismo día del despliegue y sin un solo error en tres horas de logs. Secuencia
completa en [`go-live-consola-y-teammates.md`](go-live-consola-y-teammates.md).

---

## 1 · Nadie puede contratar sin que un operador le abra la puerta

**Es el hueco más grande, y no es un fallo: es alcance que la spec 005 no cubría.**

El catálogo de membresías existe en producción —Pro 20 $, Team 60 $, Business
150 $, con sus `stripe_price_id` escritos— y el checkout funciona. Pero un
partner nuevo no puede llegar solo: el alta se hace con
`apps/api/scripts/seed_console_memberships.py`, que ejecuta un operador con
acceso a la VPC, y solo después esa persona puede entrar en la consola y
contratar.

Comprobado el 2026-09-13 contra la cuenta en modo live: **0 suscripciones, 0
clientes**. Las 4 sesiones de checkout que aparecen son de abril, del otro
negocio que aloja la cuenta, expiradas y sin pagar.

Falta el tramo entre «alguien quiere ser partner» y «ese alguien tiene una
suscripción activa»: registro, verificación, creación del partner y de su primer
principal, y el enlace con el nivel contratado. Es **comportamiento de producto
nuevo**, así que entra por `/speckit-specify`, no por un parche.

Preguntas que la spec tendrá que cerrar, y que hoy no tienen respuesta en el
repositorio: ¿el registro es abierto o por invitación? ¿Quién verifica que un
partner es quien dice? ¿Se contrata antes o después de tener clientes dados de
alta? ¿Qué ocurre con un registro que nunca paga?

## 2 · La app de escritorio no se puede distribuir

**T057 de la spec 001, bloqueada fuera del plan.** No está firmada ni
notarizada: en la máquina solo hay un certificado «Apple Development», que no
sirve para distribuir, y los OV de Windows tienen plazo de entrega.

Se instala en las máquinas del equipo salvando el aviso del sistema. **A un
partner no se le puede entregar así.** Para el piloto con Facelad puede bastar;
para vender, no.

Lo que hay hecho: `pnpm --filter @nexus/desktop build && … package` produce el
paquete, los endpoints `/device/pair` y `/device/poll` responden en producción
(422 y 405 a una petición vacía: existen y validan), y
`NEXUS_DEVICE_TOKEN_SECRET` está aprovisionado —llevaba meses en Terraform sin
estar en el secreto de prod, y se puso el 2026-09-13—.

## 3 · El tratamiento fiscal

Sigue siendo lo que era, con una diferencia: **ya no es teórico.** `sk_live_`
está en producción, el catálogo live existe y el checkout resuelve precios. La
distancia entre «desplegado» y «cobrando de verdad» es un clic de un partner.

IVA europeo con ventanilla única e IVA chileno para una membresía de 20 $
vendible a cualquiera. Es asesoría, no ingeniería, y no la cierra ningún commit
([`billing.md` §Precondición](billing.md)).

## 4 · La cuenta del proveedor es de una persona física

Verificado el 2026-09-13: `business_name` «Andres Matos», `business_type`
`individual`, país `ES`. Decisión consciente para arrancar.

Dos consecuencias prácticas, no opiniones:

- **Aloja otro negocio.** En el catálogo live conviven «5 Invitaciones» y
  «Diseños ilimitados». Sus `checkout.session.completed` llegan a nuestro
  endpoint y el worker los marca `failed` por huérfanos —correcto y
  deliberado— pero generará ruido en los logs de producción. Si molesta, el
  sitio de la decisión es el filtrado por `client_reference_id`, no el endpoint.
- **Mover la cuenta más tarde cuesta más que ahora.** Rehacer el catálogo contra
  otra cuenta es un comando; migrar suscripciones vivas no lo es. Hoy hay cero.
  Runbook:
  [`runbook-migracion-cuenta.md`](../specs/005-membresias-y-cobro/runbook-migracion-cuenta.md).

## 5 · Deuda de verificación y de limpieza

| | Detalle |
|---|---|
| **T039/T043** (spec 001) | La suite de contención en Windows, con rutas relativas NT. Nunca se ha ejecutado |
| **`companion-evals-live` en rojo** | Falla en `main` desde el 2026-09-12, dos días seguidos. Ajeno a este despliegue y sin mirar |
| **`nexus-state.md`** | Sin tocar desde el 2026-08-07. Describe un mundo anterior a las specs 002–005 y a este go-live. Es el documento de estado canónico del vault |
| **`test-api` inestable** | El paso de pytest ha ido 765s, 784s, 840s, 849s, 1140s y 1978s. El pico de 1978s tumbó un deploy por timeout (arreglado subiendo la espera a 90 min), y el run siguiente volvió a 15m48s. Nadie sabe de dónde sale la variabilidad |
| **`infra/railway/` y `deploy.yml`** | Muertos desde el corte a AWS del 2026-08-19. `CLAUDE.md` los declara «dead weight, kept until someone removes them» |
| **Comentario obsoleto** | `deploy-prod.yml` dice que «api.auphere.com sigue apuntando a Railway». Es falso desde el 2026-08-19 |
| **`NEXUS_WEBHOOK_HMAC_SECRET`** | Aprovisionado en Terraform y en `populate_app_secret.sh`, que afirma que «los partners ya firman con este valor». Ningún código lo lee: se retiró de `Settings` el 2026-09-13. O alguien lo usa y falta el verificador, o sobra en infra |

## 6 · Cosas que quedaron probadas y conviene no volver a tocar a ciegas

Para que nadie las «arregle» sin saber por qué están así:

- **El orden secreto → Terraform → despliegue.** Una definición de tarea que
  pide una clave ausente del secreto no arranca, y el apply se lleva los cinco
  servicios. Hay un script para añadir claves sin borrar las que ya están:
  `infra/scripts/add_app_secret_keys.sh`, que además valida la forma de
  `whsec_`, `sk_`, `pk_` y los `_BASE_URL`.
- **El `apply` va siempre con su `-var-file`.** Sin él, el plan propone
  `https_enabled = true -> false`, que destruye el listener HTTPS. En `prod`,
  además, `state_bucket` se pasa con `-var` a propósito.
- **El webhook del proveedor lo crea el script, no el asistente del panel.** El
  asistente pone la URL sin ruta y marca sus eventos, no los ocho nuestros.
- **Container Insights está apagado** por decisión del 2026-09-08 (~106 USD/mes
  y nada lo leía). Verificado el 2026-09-13: dejó de emitir en los dos clusters.
