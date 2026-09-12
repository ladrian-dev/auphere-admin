# Fase 1 · Cómo se verifica

**Spec**: [spec.md](./spec.md) · **Plan**: [plan.md](./plan.md)
**Fecha**: 2026-09-12

**61 comprobaciones, V01–V61**, mapeadas a los 48 criterios de los 8 requisitos
más las puertas estructurales. Cada una nace como test **y se ve en rojo
antes de implementar** (§VII). Una que haga `skip` no cubre nada.

---

## Prerrequisitos

```bash
docker compose up -d
curl -s http://localhost:8000/health     # → {"status":"ok"}
cd apps/api && uv sync                   # trae `stripe` 15.6.1 (MIT)
uv run alembic upgrade head              # hasta 0117
```

**Claves de prueba**: en `.env` local, las del **modo de prueba** de la cuenta.
Nunca las reales — este entorno cobra de verdad si se le dan las de producción.

**Reenvío de eventos al local**: la CLI del proveedor entrega los avisos a
`localhost` y **firma con un secreto propio** que hay que poner en
`BILLING_WEBHOOK_SECRET`. Si se usa el secreto de la cuenta, todas las firmas
fallan y parece un fallo del código.

**Relojes de prueba**: son lo que hace verificable el requisito 5 **contra el
proveedor de verdad**. Sin ellos, la escalera solo se recorre esperando un mes.

> **En local no hay cuenta conectada, y es una decisión** (2026-09-12): las
> credenciales se ponen en staging y producción, no en las máquinas de
> desarrollo. Consecuencia honesta para este documento: **en local la escalera
> se verifica simulando el estado que el proveedor enviaría** —que es
> exactamente lo que prueban V30 a V37— y **el recorrido con relojes reales es
> una comprobación de staging**, no de la suite local.
>
> Lo que la simulación cubre entero: el mapeo exhaustivo, qué se pausa, qué
> sobrevive y qué vuelve solo. Lo que **no** cubre y hay que mirar en staging:
> que Stripe emita de verdad los estados que esperamos y en ese orden — sobre
> todo el paso a `unpaid`, que depende de una casilla del panel.

---

## R1 · Los niveles existen y limitan

| # | Qué se comprueba | Cómo | Suite |
|---|---|---|---|
| **V01** | Hay cuatro niveles con pool, teammates y personas, y **ninguno con un tope nulo** | Consulta a `membership_tiers` tras 0116 | integración |
| **V02** | Crear el teammate `n+1` falla, **dice el tope y cómo se sube**, y **no archiva ninguno** | Nivel Pro, 2 teammates, se intenta el tercero; se cuentan los existentes después | integración |
| **V03** | Añadir la persona `n+1` falla igual | Idéntico sobre `partner_memberships` | integración |
| **V04** | En Free **no hay** botón de teammate ni de ejecución en la máquina — **ni apagados** | Render de la consola; se busca que el control **no exista** | vitest |
| **V05** | Cambiar el pool de un nivel **con un `UPDATE`** surte efecto sin reiniciar | Se cambia `weekly_pool_tokens`, se concede el nivel, se lee el pool | integración |
| **V06** | Un partner por encima del tope tras bajar **conserva todo** y solo se le bloquea crear | 5 teammates, se baja a un nivel de 2 | integración |
| **V07** | `partners.max_clients` **no cambia** al conceder un nivel | Se fija en 9, se concede Business, sigue en 9 | integración |
| **V58** | **La cifra absoluta del pool no sale por `/console/billing/membership`**, ni en `tier` ni en `catalog`; salen los topes y un `consumption_multiple` calculado. El panel de operador **sí** ve la cifra | integración |
| **V59** | **`invoice.finalization_failed` está manejado**: alerta al operador con `last_finalization_error` y **no** degrada al partner. La suscripción sigue `active` y el estado nuestro no se mueve | integración |
| **V60** | Toda sesión de Checkout se abre con `client_reference_id = partner_id`, y el manejador **resuelve el partner desde el aviso**, no buscando por `stripe_customer_id` | integración |
| **V61** | El arranque **avisa** de que hay que comprobar a mano que la cuenta manda las suscripciones a `unpaid` tras agotar reintentos. Stripe **no expone ese ajuste por API** (comprobado 2026-09-12), así que no se puede verificar: lo que se comprueba es que el aviso existe y que el runbook lo cubre. Sin ese ajuste el escalón intermedio de D6 no existe | unidad |

V04 es el que más se falla: lo fácil es pintar el botón con `disabled`. La
constitución (§V) pide que **la ausencia se diseñe**, no que se apague.

---

## R2 · Suscribirse es cosa del partner

| # | Qué se comprueba | Cómo | Suite |
|---|---|---|---|
| **V08** | Una persona con permiso de facturación contrata **sin que intervenga Auphere** | Recorrido de consola con reloj de prueba | integración |
| **V09** | **Ningún dato de tarjeta** en base de datos, log ni traza | `capture_logs` + rejilla de patrones (PAN, CVC) sobre todo el camino | aislamiento |
| **V10** | Al confirmarse el pago, **nivel y pool se aplican en el mismo acto** | Se dispara `invoice.paid`, se leen los dos en la misma transacción | integración |
| **V11** | Abandonar el pago a medias **no cambia nada** | Sesión abierta y no completada; se compara el estado antes/después | integración |
| **V12** | La auditoría **nombra a la persona**, no al proceso | Se lee el asiento: lleva identidad de consola | aislamiento |
| **V13** | La consola **no lleva ninguna credencial del proveedor** | `grep` en `apps/console` por las variables de clave — igual que el que ya existe para `NEXUS_ADMIN_TOKEN` | unidad |

---

## R3 · Comprar crédito, y que solo cuente lo confirmado

| # | Qué se comprueba | Cómo | Suite |
|---|---|---|---|
| **V14** | El saldo sube **solo** con pago confirmado | Compra completa → `purchased_remaining` sube | integración |
| **V15** | Una **sesión abierta** no acredita nada | Se abre y no se paga | integración |
| **V16** | El mismo pago notificado **cinco veces** acredita una | Cinco reenvíos del mismo evento | integración |
| **V17** | `completed` y `async_payment_succeeded` de **la misma sesión** acreditan una | Los dos eventos, distintos ids | integración |
| **V18** | **Ningún aviso externo resta saldo** | Recorrido de todos los eventos con el saldo en 50 000; nunca baja | integración |
| **V19** | `POST /console/wallet/purchased` **ya no existe** | Petición → `404`, y `grep` confirma que la ruta no está en el código | integración |
| **V20** | El partner ve el saldo comprado **en unidades** | Render de Consumo | vitest |

V18 es la comprobación de D3 y merece ser exhaustiva: **recorre todos los tipos
de evento**, no solo el reembolso. La avería que previene no es un caso, es una
clase.

---

## R4 · El aviso es de fiar o no se procesa

| # | Qué se comprueba | Cómo | Suite |
|---|---|---|---|
| **V21** | Firma inválida → `400`, **sin tocar nada**, con rastro | Cuerpo válido, firma alterada | integración |
| **V22** | Sin cabecera de firma → `400` | | integración |
| **V23** | El evento **se registra antes** de actuar | Se fuerza un fallo del trabajo; la fila existe con `status='failed'` | integración |
| **V24** | Responde en **< 500 ms** | Se mide con el trabajo encolado, no ejecutado | integración |
| **V25** | Idempotente por identificador de evento | UNIQUE, verificado con entrega concurrente | integración |
| **V26** | Un aviso **fuera de orden** no deja el estado incoherente | `subscription.updated` antes que `invoice.paid` | integración |
| **V27** | Ningún registro del camino del pago lleva **tarjeta ni contenido de conversación** | Al estilo de `test_wallet_events_are_logged.py`, que ya vigila esto para el libro | aislamiento |
| **V28** | El importe **se recupera de la API**, no se lee del cuerpo | Cuerpo con importe manipulado; se acredita el real | integración |
| **V29** | **No estamos suscritos a `invoice.created`** | Se comprueba la lista de eventos manejados | unidad |

V28 es el principio III hecho test. V29 es la mina de las 72 horas.

---

## R5 · El impago degrada por escalones, y nada se pierde

| # | Qué se comprueba | Cómo | Suite |
|---|---|---|---|
| **V30** | Los cuatro estados existen y el CHECK rechaza un quinto | | integración |
| **V31** | En **pago fallido** el pool no se repone y el saldo comprado **sí se gasta** | Reloj de prueba a la semana siguiente | integración |
| **V32** | En **impagada** el trabajo nuevo para con el estado que ya existe para quedarse sin saldo | Se comprueba que es **el mismo** estado de la spec 003, no uno nuevo | integración |
| **V33** | En impagada **no se archiva ningún teammate, no se cancela ninguna tarea, no se invalida ninguna confirmación pendiente** — y una pendiente **se puede responder** | Se cuentan las tres cosas antes y después, y se responde la confirmación | integración |
| **V34** | Un pago confirmado devuelve a **al corriente sin intervención** | | integración |
| **V35** | Cancelar baja a Free **al terminar el período pagado**, con la historia intacta | Reloj de prueba | integración |
| **V36** | El aviso llega **antes** de la degradación | Se comprueba el orden de notificación contra el cambio de estado | integración |
| **V37** | La pantalla dice **en qué estado está y qué lo arregla**, sin culpar al partner | Render de los cuatro estados | vitest |

V33 es **el corazón de la spec**. La tentación de liberar recursos de una cuenta
impagada es enorme y la constitución la prohíbe (§IV, «borrar no existe»). La
mitad de responder la confirmación pendiente es la que la Spec A ya tuvo que
arreglar una vez, quitando `_require_wallet` de `resume_run`.

---

## R6 · Cambiar de plan

| # | Qué se comprueba | Cómo | Suite |
|---|---|---|---|
| **V38** | Subir es **inmediato** | El pool nuevo está disponible en el mismo turno | integración |
| **V39** | Subir a mitad de ciclo **completa**: 100 000 gastados de 500 000, al subir a 1 000 000 quedan **900 000** | Aritmética exacta, no aproximada | unidad |
| **V40** | Bajar se aplica **a fin de período** y no reclama el pool en curso | Reloj de prueba | integración |
| **V41** | **Ningún** cambio de nivel altera `purchased_remaining` | Se prueban las cuatro transiciones | integración |
| **V42** | Cambio de nivel **coincidiendo** con la reposición: ni duplicado ni a cero | Se fuerza el mismo instante | unidad |

V39 y V42 son unitarias a propósito: son aritmética, y la aritmética del dinero
se prueba sin base de datos para que el fallo señale la fórmula.

---

## R7 · El crédito sobrevive doce meses

| # | Qué se comprueba | Cómo | Suite |
|---|---|---|---|
| **V43** | Con la cuenta viva, `purchased_expires_at` es **`NULL`** y el saldo no caduca | Se avanza un año | integración |
| **V44** | Al cancelar se fija a **12 meses** | | integración |
| **V45** | Reactivar dentro del plazo **vuelve a dejarlo a `NULL`**, sin reponer a mano | | integración |
| **V46** | Al cancelar se le dice **cuánto conserva y hasta cuándo** | Respuesta de la API + render | vitest |
| **V47** | Al caducar **queda asiento** de cuánto y cuándo | El trabajo de fondo deja fila en `usage_ledger` con su motivo | integración |

V47 distingue esto de D3: aquí sí se resta, pero lo decide **una regla nuestra**
con fecha nuestra, y **deja apunte**. Una resta sin apunte sería la avería que
D3 previene.

---

## R8 · El recibo deja de ser la factura

| # | Qué se comprueba | Cómo | Suite |
|---|---|---|---|
| **V48** | El recibo lleva línea de **membresía** y de **consumo** | | integración |
| **V49** | **No dice «total a pagar» ni lleva vencimiento** | Se comprueba la ausencia, y que `PAYMENT_DUE_DAY` ya no se usa para el recibo | integración |
| **V50** | Conserva el **desglose por cliente** y la conversión de las comisiones en CLP con su tipo de cambio | | integración |
| **V51** | Se llega a las facturas del proveedor **desde la consola** | | vitest |
| **V52** | Los dos documentos **no se contradicen** en el importe del período | Se comparan | integración |

---

## Las puertas estructurales

| # | Qué se comprueba | Suite |
|---|---|---|
| **V53** | `partner_subscriptions` tiene RLS **ENABLE + FORCE** por `partner_id`, y un partner no ve la fila de otro | aislamiento |
| **V54** | Contratar, cambiar, comprar y cancelar dejan **rastro que nombra a la persona** (§IV) | aislamiento |
| **V55** | **Ningún registro** del camino del cobro lleva dato de tarjeta (§ garantía 6) | aislamiento |

> **V09, V27 y V55 son la misma comprobación**, enunciada desde tres requisitos
> distintos (R2.2 «ningún dato de tarjeta», R4.6 «ningún registro del camino del
> pago» y la garantía 6). Se implementan en **un solo test**, `T023`. Se dejan
> las tres entradas porque cada requisito tiene que poder rastrearse hasta una
> comprobación, pero **no son tres tests**.
| **V56** | `stripe` está en el BASELINE de `test_no_new_dependencies.py`, **no hay ninguna otra dependencia nueva**, y no se importa fuera de `nexus_api/billing/` | unidad |
| **V57** | **El camino del turno no importa `nexus_api.billing`** — con el proveedor caído el trabajo continúa con el saldo que ya hay (CE-004) | unidad |

> **V57 no nació con el quickstart: la encontró `/speckit-analyze`.** CE-004
> —«con el proveedor caído el trabajo continúa»— era el único criterio de éxito
> sin comprobación, y es el que protege de la avería peor de esta spec: una
> consulta al proveedor colada en el camino del turno apaga a **todos** los
> agentes el día que Stripe tenga una incidencia. Es la misma forma del
> `_require_wallet` que la Spec A tuvo que quitar de `resume_run`.

---

## Ejecutar

```bash
cd apps/api && uv run pytest tests/unit/ -x
```

```bash
cd apps/api && uv run pytest tests/isolation/ -x
```

```bash
cd apps/api && uv run pytest tests/integration/
```

```bash
pnpm --filter @nexus/console test
```

**Un test de aislamiento en rojo bloquea el merge.** No se negocia.

---

## El recorrido de humo, con reloj de prueba

El que hay que hacer a mano una vez antes de dar la feature por terminada,
porque encadena lo que los tests prueban por separado:

1. Partner nuevo → es **Free**, sin teammates, sin controles apagados.
2. Contratar **Pro** → nivel y pool en el mismo acto; la auditoría **nombra a la
   persona**.
3. Crear 2 teammates → el tercero falla diciendo el tope.
4. Comprar 50 $ de crédito → sube **una vez**; reenviar el aviso cinco veces no
   lo sube más.
5. Gastar la mitad del pool, **subir a Team** → el pool **se completa**, no se
   reinicia, y el crédito comprado **no se mueve**.
6. Reloj de prueba: **falla el cobro** → pago fallido. **Nada desaparece.**
7. Agotar reintentos → impagada. **La confirmación pendiente se puede
   responder.** El crédito comprado sigue gastándose.
8. Pagar → vuelve a al corriente **solo**.
9. Cancelar → Free a fin de período; la consola dice **cuánto crédito conserva y
   hasta cuándo**.
10. El recibo del mes: dos líneas, **sin «total a pagar»**, y el importe cuadra
    con la factura del proveedor.

Si el paso 7 pierde una confirmación pendiente, la feature no está terminada por
mucho que las suites estén verdes.
