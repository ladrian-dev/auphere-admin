# Decision Gate: membresías, consumo y cobro

- **Slug**: membresias-y-consumo-stripe
- **Decided**: 2026-09-11
- **Verdict**: **go**, **partido en dos specs**, y la primera empieza por cargar
  tres tarifas
- **Artifacts reviewed**: [`intake.md`](./intake.md) · [`research.md`](./research.md)
  · [`problem.md`](./problem.md) · [`concept.md`](./concept.md)
- **Superficie de confianza (§II)**: **no se abre ninguna nueva.** Se trabaja
  entera sobre la `0` (API de la consola). Al contrario: **se cierra una que
  está abierta hoy** — `POST /console/wallet/purchased` permite a un partner
  acreditarse saldo sin pago, y solo está contenida por un `if
  settings.is_prod` que devuelve 404. Cuando el crédito entre por el webhook,
  esa llamada sobra y se borra.

## Scorecard

| Criterio | Nota | Evidencia |
|---|---|---|
| Demanda | 5/5 | Hay un libro contable completo y ninguna forma de que entre un dólar. La única recarga viva en producción lleva token de admin |
| Encaje con lo construido | **5/5** | Los dos cubos, el débito idempotente, la renovación por caducidad, los avisos al 80/100 %, la lista de modelos por partner, el recibo con su FX y las pantallas de las tres superficies **ya existen**. Lo que falta es un período, un peso, un webhook y dos líneas |
| Riesgo | 2/5 | Dinero e impuestos. El riesgo técnico es bajo; el fiscal no lo es, y no lo resuelve un ingeniero |
| Coste | 2/5 | `large`, y lo caro son las siete decisiones y el ADR, no el código |
| Reversibilidad | 3/5 | El período y el peso se revierten con una migración. **Un precio publicado y cobrado, no**: un plan de 20 $ que sube a 30 $ se paga en confianza |
| Dependencias externas | 3/5 | Cuenta de Stripe (existe la de Facelad, según K2), y **una asesoría fiscal que hoy no está contratada** |
| Licencias | 5/5 | `stripe` (PyPI) es **MIT**, 15.6.1 del 2026-09-01. Principio VIII satisfecho. No está instalada; entra como dependencia nueva con su párrafo citado en el plan |

## Verdict & Rationale

**Go, y partido en dos.** Meter «cargar tres tarifas», «cambiar el período del
pool», «arreglar el medidor doble», «inventar tres planes» y «conectar Stripe»
en una sola spec produce una spec que nadie puede revisar y un PR que nadie
puede revertir. Y hay una dependencia dura entre las dos mitades: **sin las
tarifas de Sol, Terra y Luna cargadas, ningún número de margen de esta
evaluación es comprobable en producción.** Hoy `_turn_cost_usd` devuelve `None`
en cada turno de teammate.

- **Spec A · «el medidor dice la verdad»** — sin Stripe, sin precio, sin
  producto nuevo. Cierra C1 y C2 (tarifas y `meter_prices`), pasa el `included`
  a semanal con ancla por partner, mete el peso por modelo dentro de
  `quota_tokens()`, y hace que `budget_out` lea del wallet en vez de sumar
  `companion.runs`. Es **mayoritariamente supresión**, se puede desplegar sola,
  y deja el margen visible. Cierra D5 del plan de pendientes.
- **Spec B · «la membresía y el cobro»** — las tres membresías con sus topes de
  teammates y de personas, Stripe Checkout, webhook idempotente, la escalera de
  impago, y las dos líneas nuevas del recibo. Depende de A.

Lo que **no** se hace en esta evaluación es empezar. Toca dinero, y eso no se
improvisa al final de otra tarea.

## El orden de la próxima sesión

1. **Cargar las tarifas de Sol, Terra y Luna.** Están verificadas y fechadas en
   el §3.2 de [`research.md`](./research.md); es una migración con el mismo
   reprecio idempotente que ya usan la `0072` y la `0076`. Va primero porque es
   lo único que convierte «el margen es del 62 %» en un dato comprobable.
2. **Medir el turno de verdad.** El turno de referencia (9 900 tokens de cuota)
   es un supuesto. Una consulta sobre `companion.runs` de producción lo confirma
   o lo corrige, y todos los tamaños de pool del `concept.md` dependen de él.
   Si el turno real es la mitad, los planes dan el doble de trabajo del que
   prometen; si es el doble, el plan de 20 $ da 25 turnos a la semana y no se
   puede vender.
3. ~~**Decidir las siete de `concept.md`** (D1-D7) con Luis, y escribir el **ADR
   que enmienda ADR-022**.~~ **Hecho el 2026-09-11**:
   [[nexus/decisions/ADR-037-membresias-y-consumo-de-la-app]], con banner de
   enmienda en ADR-007 y ADR-022 y el índice de decisiones al día.
4. **Hablar con un asesor fiscal** antes de escribir la Spec B. Es lo único de
   toda la lista que no depende de nosotros y que puede cambiar el producto.
   **No bloquea la Spec A.**
5. `/speckit-specify` para la Spec A.

> **Estado el 2026-09-11**: hechos el 3 y arrancando el 5. El 1 entra dentro de
> la Spec A (es código y necesita spec detrás, regla nº1). El 2 está aparcado
> como tarea de fondo y **solo bloquea las cifras de la Spec B**.

## Decidido con Luis el 2026-09-11

Cuatro de las ocho preguntas quedaron cerradas antes de escribir el ADR, porque
las cuatro cambiaban lo que había que escribir.

| # | Pregunta | Decisión |
|---|---|---|
| 1 | ¿«Máximo 3 membresías» son niveles o suscripciones? | **Tres membresías de catálogo** — `Pro` · `Team` · `Business`, más el nivel `Free` que no se factura. Un partner tiene una y sube o baja; no se acumulan |
| 2 | ¿Precios fijos o provisionales? | **Provisionales.** El ADR fija la estructura —tres niveles, pool semanal, caída a créditos, 65 % de margen objetivo, ningún plan deficitario a fondo— y las cifras se cierran tras medir el turno real |
| 3 | ¿Qué ve un partner sin membresía? | **Un nivel `Free` con pool mínimo que solo gasta el Companion de la consola.** Es un nivel del catálogo pero **no una membresía**: no se compra, no se factura y no cuenta contra el «máximo tres». Reutiliza el `companion_monthly_token_cap` de hoy |
| 4 | ¿El peso por modelo en la primera spec? | **Sí**, dentro de `quota_tokens()`. Verificado: con el peso, agotar el pool cuesta lo mismo con cualquier cerebro; sin él, Business a fondo en Sol cuesta 166,90 $ contra 150 $ de precio |
| 5 | ¿Dónde ancla la semana? | **En el día de alta del partner**, no en un lunes global. Reparte la renovación en vez de concentrarla en un tick, y un alta en viernes tiene una primera semana entera. `renew_included_if_expired` no se toca: ya dispara por caducidad |

La 3 la abrió la propia respuesta de Luis: si el Companion está incluido en la
membresía **y** la membresía es de la aplicación de escritorio, había que decir
qué pasa con el partner de agencia que opera clientes finales desde la consola y
no ha comprado la app. Hoy tiene el Companion encendido; atarlo a una membresía
de escritorio se lo quitaría.

## Preguntas que quedan para `/speckit-clarify`

Las cuatro son de la **Spec B** (la membresía y el cobro). La Spec A no depende
de ninguna.

1. **El crédito al cerrar la cuenta**: el saldo comprado no caduca — ¿qué pasa
   con él cuando un partner se va? ¿Se devuelve, se pierde, o se conserva N
   meses?
2. **El documento fiscal**: ¿la factura de Stripe sustituye al recibo mensual, o
   el recibo se queda como detalle de consumo anexo? Hoy el recibo dice «Total a
   pagar» y vence el día 5, y eso deja de ser cierto en cuanto Stripe cobre.
3. **`partners.max_clients`**: el concepto lo deja **independiente del plan**.
   ¿Se confirma, o el plan también sube el número de clientes finales?
4. **Moneda**: ¿solo USD en la primera versión, o CLP desde el principio? El
   recibo ya sabe convertir; Stripe fija la moneda del cliente en la primera
   factura y cambiarla exige crear un `Customer` nuevo (ADR-022 §7).

## Lo que la spec tendrá que probar, no solo hacer

- **Las tres superficies dan el mismo número.** Consola, panel de admin y
  pantalla Cuenta, en la misma petición y el mismo período. Es el test que hoy
  fallaría: `budget` al 20 % con el wallet vacío.
- **El pool se agota y el trabajo continúa** contra créditos, sin que nadie
  toque nada, y la pantalla dice de qué bolsillo sale.
- **Sin pool y sin créditos, la tarea queda `en pausa por tope`** con las
  confirmaciones vivas. Es el camino de la spec 003 con otro motivo.
- **Un impago no borra nada**: el teammate sigue en la nómina, la tarea en su
  estado, la confirmación pendiente viva. Un test por escalón de la escalera D4.
- **El mismo evento de Stripe entregado cinco veces suma saldo una vez.**
- **Un cambio de plan no toca `purchased_remaining`.** Ni al subir, ni al bajar,
  ni al cancelar.
- **Ninguna respuesta de cliente final menciona plan, pool, saldo ni precio.**
  En `tests/isolation/`, con el patrón estructural sobre el esquema OpenAPI que
  CP-21 ya usa para el contenido de conversación.
- **Cero filas sin valorar** para los modelos que vendemos: el `complete` de
  `/admin/cost` en `true` para un mes con tráfico.

## Una deuda que esta evaluación destapa y que no espera a la spec

`partner_wallets.included_remaining` se recarga con
`partners.companion_monthly_token_cap`, y ese mismo número es el cap contra el
que se compara la suma de `companion.runs`. El wallet lo gastan además los
turnos de canal de los clientes y las ejecuciones locales, que esa suma no ve.
**Hoy, en producción, un partner puede ver `budget` al 20 % y recibir un 409
`wallet_empty`.** No es un riesgo futuro: es el estado actual, está escrito como
deuda en `metering/wallet.py` y como ítem **D5** en el plan de pendientes del
8 de septiembre.

Mirar cuántos partners están en esa situación cuesta una consulta. Descubrirlo
por un ticket cuesta la confianza en el medidor, que es lo único que sostiene
cobrar por consumo.

## Estado del repositorio al abrir esto

`develop`, limpio, con las specs 001, 002 y 003 cerradas y la evaluación de
empaquetado documentada (`c0eabb6`). Última migración: `0113_teammate_changes`.
**Cero código de Stripe en todo el repositorio**, verificado el 2026-09-11: el
docstring de `db/models/billing.py` que dice que las columnas `stripe_*` están
ausentes a propósito sigue siendo cierto palabra por palabra.
