# Research: membresías, consumo y cobro

- **Slug**: membresias-y-consumo-stripe
- **Fecha**: 2026-09-11
- **Alcance**: qué hay construido, cómo resolvieron esto los que ya lo
  resolvieron, y qué cuestan de verdad los modelos que vendemos.

> **Aviso de procedencia.** El §1 está **verificado leyendo el repositorio** el
> 2026-09-11; cada afirmación lleva su ruta. El §2 y el §3 salen de páginas
> públicas consultadas ese mismo día, con la fuente al pie; donde una cifra no
> se pudo verificar se dice, y no se rellena de memoria. El §4 es aritmética
> sobre el §3 con supuestos declarados.

---

## 1. Lo que ya existe en el repositorio

### 1.1 · El libro del partner: construido, transaccional y probado

`apps/api/src/nexus_api/db/models/partner_wallet.py` define tres tablas:

- **`partner_wallets`** — una fila por partner. `included_remaining` +
  `included_expires_at` (caduca) y `purchased_remaining` (no caduca). RLS
  ENABLE + FORCE por `partner_id` (migración `0094`).
- **`partner_allocations`** — el tope de cada cliente dentro del wallet, con
  `cap` y `remaining` y la invariante *la suma de `cap` no supera el wallet*.
- **`usage_ledger`** — un asiento por débito, con `idempotency_key` UNIQUE y
  `bucket ∈ {included, purchased}`.

`apps/api/src/nexus_api/metering/wallet.py` es el motor, y tiene las
propiedades que nadie quiere volver a construir:

- **Fail-closed explícito.** `read_wallet` devuelve `None` y registra si el
  libro no se lee; `allow_channel_turn` cierra la puerta ante wallet a 0, sin
  asignación, asignación a 0 **o libro ilegible**.
- **Débito bajo bloqueo de fila** (`with_for_update`), con el reparto
  `included` primero y `purchased` después (`split_spend`).
- **Idempotencia real**: un débito partido en dos cubos escribe
  `{key}:included` y `{key}:purchased`; el mismo turno no dobla.
- **Renovación por caducidad, no por calendario** (`renew_included_if_expired`):
  si el cron estuvo caído el día 1, renueva al volver. Y su compañero
  obligatorio `replenish_allocations`, que existe porque sin él «un cliente que
  gastó su cuota en septiembre sigue con 0 en octubre» — el modo de fallo que
  el propio módulo llama *silencio con saldo*.

Esto no se rehace. **Se le cambia el período al `included` y se le conecta una
entrada de dinero.** Nada más.

### 1.2 · La unidad: `quota_tokens()`, y ya lleva un peso dentro

`apps/api/src/nexus_api/metering/quota.py`, política C3:

```
quota = uncached_input + 0,1 × cache_read + output
uncached_input = max(0, prompt_tokens − cache_read)
```

Tres cosas que importan para lo que viene:

1. `cache_read` **ya pesa 0,1**, no 1. Es decir: **la unidad del medidor ya no
   es un token nativo, es un token ponderado.** Eso abre la puerta a ponderar
   también por modelo sin inventar una segunda unidad (§4.4).
2. `cache_write` **no entra** en la cuota, a propósito, para no inventar un
   quinto multiplicador.
3. Redondeo `ROUND_HALF_UP`, no el de Python. Está escrito porque alguien ya se
   quemó con `round(2.5) == 2`.

`quota_tokens()` se usa en los **tres** sitios que gastan: el Companion
(`api/console/companion.py:1287`), el consumidor de canal
(`apps/worker/.../metering/consumer.py:210`) y la ejecución local
(`services/local_workstation_metering.py`). Una sola función, tres superficies.

### 1.3 · El agujero que ya existe: dos cifras del mismo gasto

Esto es lo más importante del inventario, y no está escrito en ningún sitio
salvo en un docstring.

Hay **dos contadores** sobre el mismo dinero:

| | Fuente | Qué cuenta | Período |
|---|---|---|---|
| `/console/companion/budget` y `/console/teammates/usage` | filas de `companion.runs`, sumadas miembro a miembro bajo RLS (`sum_partner_companion_tokens`) | **solo** turnos de Companion y de teammates | mes natural UTC |
| `partner_wallets.included_remaining` | el libro, vía `debit_wallet` | Companion **y** turnos de canal de los clientes **y** ejecuciones locales | mes, por `included_expires_at` |

Y el **mismo número** dimensiona los dos: `renew_included_if_expired` recarga el
wallet con `partners.companion_monthly_token_cap`, que es también el cap contra
el que se compara la suma de runs. El propio `wallet.py` lo llama deuda:

> *«Deuda conocida: `monthly_cap` sale de `partners.companion_monthly_token_cap`,
> que es el mismo número que gasta el Companion. Separar los dos bolsillos es D5.»*

La consecuencia operativa, hoy, en producción: un partner cuyos clientes
consuman el wallet puede ver **`budget` al 20 %** y recibir a la vez un **409
`wallet_empty`** de `_require_wallet` (`companion.py:413`). Dos números del
mismo gasto que no cuadran, y una pantalla que no puede explicar por qué.

La buena noticia: **la unidad de ambos coincide**. `CompanionRun.input_tokens`
ya guarda la cuota, no el nativo (lo dice el comentario de `_turn_cost_usd`), así
que `sum(input + output)` sobre runs y `quota_tokens()` son el mismo número. Lo
que discrepa es el **alcance**, no la unidad. Eso hace la corrección barata.

### 1.4 · Facturación: la mitad de arriba está construida y no habla con la de abajo

`db/models/billing.py` — `BillingPlan`, `Invoice`, `InvoiceLine`. Su docstring
dice que Stripe llega después y que las columnas `stripe_*` están ausentes a
propósito. **Sigue siendo cierto el 2026-09-11**: un `grep -ri stripe` sobre
todo el repositorio devuelve comentarios, un test de fuga de credenciales y un
`slug` de método de pago de WooCommerce. **Cero código de Stripe.**

`services/partner_receipt.py` (465 líneas) emite un recibo en USD por partner y
mes, idempotente por `(partner_id, period_year, period_month)`, con tres modelos
de línea: `commission` (2,5 % de ventas cerradas por WhatsApp, con conversión
CLP→USD una sola vez al dólar observado del día), `subscription` (plan plano) e
`inactive` (línea a $0, para que el recibo enseñe la nómina completa). El paso
que marca `agent_sales.invoice_line_id` es auto-reparable.

**Lo que ese recibo no tiene: una línea de membresía y una línea de consumo.**
Hoy el consumo de tokens no aparece en ningún documento cobrable.

### 1.5 · La puerta del dinero: construida y cerrada a propósito

`POST /console/wallet/purchased` (`api/console/wallet.py:184`) suma al cubo
`purchased`. En producción devuelve **404 opaco**, y su docstring explica por
qué mejor de lo que lo haría esta evaluación:

> *«aquí quien se acredita saldo es el propio partner, y sin cobro de por medio
> eso es regalar producto. […] Esta puerta la abre **K2**: cuando exista Stripe,
> el crédito entrará por el webhook del pago confirmado —idempotente por
> `event.id`— y no por esta llamada, que entonces sobra.»*

La consola respeta el gate en el cliente:
`apps/console/src/app/(console)/usage/page.tsx` calcula
`canRecharge = canWrite && env().NODE_ENV !== "production"`.

La recarga de Auphere sí está abierta en producción desde el 2026-09-08:
`POST /admin/partners/{id}/wallet/purchased`, con token de admin y auditoría.

### 1.6 · Modelos y tarifas: el defecto es el caro y no tiene precio

`db/models/model_profile.py` guarda el precio **por millón de tokens** en
`numeric(12,6)`, con `NULL` = «medido y sin precio», que es la verdad, en vez de
un 0 que sería indistinguible de gratis.

Estado del catálogo, leído en las migraciones `0072`, `0076` y `0095`:

| `model_id` | Entrada | Salida | Caché lectura | Caché escritura | Cargado en |
|---|---:|---:|---:|---:|---|
| `anthropic/claude-sonnet-4-6` | 3,00 | 15,00 | 0,30 | 3,75 | 0072 |
| `anthropic/claude-haiku-4-5` | 1,00 | 5,00 | 0,10 | 1,25 | 0072 |
| `anthropic/claude-haiku-4-5-20251001` | 1,00 | 5,00 | 0,10 | 1,25 | 0072 |
| `openai/gpt-4o` | 2,50 | 10,00 | 1,25 | NULL | 0076 (2026-08-11) |
| `openai/whisper-1` | — | — | — | — | 0076, $0,006/min |
| **`openai/gpt-5.6-sol`** | **NULL** | **NULL** | **NULL** | **NULL** | 0095 |
| **`openai/gpt-5.6-terra`** | **NULL** | **NULL** | **NULL** | **NULL** | 0095 |
| **`openai/gpt-5.6-luna`** | **NULL** | **NULL** | **NULL** | **NULL** | 0095 |

Y `config.py:273`: `llm_companion_model: str = "openai/gpt-5.6-sol"`.

Júntese todo:

> **El Companion —y por tanto cada teammate— corre hoy sobre Sol, que es el más
> caro de los tres modelos que vende el producto, y cuya tarifa está a NULL.**
> `_turn_cost_usd` devuelve `None` en cada turno. **El margen de teammates no es
> malo: es invisible.**

Es exactamente el ítem **C1** de [[nexus/PLAN-PENDIENTE-CORTE-2026-09-08]] («los
tres siguen con `price_input`, `price_output` y `max_context` a NULL. Son los
tres modelos que vende el producto»). El §3.2 de este documento trae las cifras
verificadas que lo cierran.

`meter_prices` (migración `0083`) tiene **6 filas y todas son `media.*`**, con
precios marcados `provisional 2026-08` en su propia columna `note`. Ítem **C2**.

### 1.7 · Lo construido y desconectado, o construido y sin usar

- **`partner_model_allowlist`** (migración `0098`, RLS FORCE por partner,
  sembrada con los tres modelos G1). Es **el mecanismo de «qué cerebro da cada
  plan», ya hecho**, y hoy solo se usa como techo administrativo.
  `services/model_choices.py` ya traduce la tarifa a una etiqueta relativa
  `bajo · medio · alto · desconocido` dentro de la oferta que esa persona ve.
- **`billing_plans`** existe con `code`, `name`, `monthly_amount_cents`,
  `active` — y hoy solo lo consume el recibo para clientes de suscripción. Es la
  tabla donde vive un plan; no hay que crearla.
- **`usage_records.source`** separa `channel` de `qa` desde la migración `0079`,
  para no cobrar al cliente las pruebas del operador. La misma idea hará falta
  para separar consumo de teammate de consumo de cliente.
- **Avisos**: `usage_alerts` (tope comercial de mensajes; **avisa, no corta**) y
  `wallet_alerts` (saldo; **el saldo sí corta**, con dos niveles: wallet del
  partner y asignación de cada cliente). Ambos idempotentes por umbral y mes.
  Verificados en vivo en staging el 8-sep según el plan de pendientes.

### 1.8 · Lo que no existe

- **Tope de teammates**: no hay columna ni comprobación. `grep` sobre
  `max_teammates` no devuelve nada.
- **Tope de personas**: tampoco. `partners.max_clients` (por defecto 5) limita
  **clientes finales**, no miembros ni teammates.
- **Cualquier concepto de membresía**: no hay tabla, ni estado, ni columna.
- **Período semanal**: `next_period_end()` devuelve el día 1 del mes siguiente.
  Todo el aparato es mensual.
- **Reloj de máquina medido**: §3 de [[teammates/08-coste-y-precio]] lo dice —
  «el medidor cuenta tokens; hay que meter las horas de VM en el mismo
  contador». No aplica todavía (no hay VM), pero la unidad tendrá que admitirlo.

### 1.9 · Lo que las tres superficies enseñan hoy

- **Consola `/usage`**: wallet (`included`, `purchased`, `available`,
  `reserve`), asignaciones por cliente, series por medidor, proyección del mes,
  exportación a CSV, y el botón de recarga **oculto en producción**.
- **Consola `/billing`**: correo de facturación y la lista de recibos con
  estado, total, vencimiento y descarga.
- **Admin `partners/[id]/`**: pestañas `wallet`, `usage`, `limits`, `models`,
  `receipts`, `audit`. La superficie de operación ya está.
- **App, pantalla Cuenta** (`apps/desktop/src/app/routes/account.tsx`): el
  medidor `role="meter"` con `budget`, el reparto por teammate, y —esto es
  importante— **la línea «gastado en otro sitio»**, que resta lo atribuido del
  total y explica la diferencia. Su propio encabezado dice por qué: *«dos cifras
  que no suman y nadie diciendo por qué es la manera de que nadie vuelva a
  creerse ninguna»*. Esa línea se escribió para el problema del §1.3.

Lo que la app **no** enseña: el wallet. Enseña el cap del Companion. Si el pool
pasa a ser el wallet, la pantalla ya tiene la forma; le cambia la fuente.

---

## 2. Cómo lo resolvieron los que ya lo resolvieron

Interesa el patrón, no la copia. Los seis convergen en la misma arquitectura, y
las diferencias son de calibración.

### 2.1 · El patrón común, en cinco piezas

1. **Suscripción plana con cuota incluida.** Nadie vende tokens a un usuario
   final; se vende un asiento con una bolsa dentro.
2. **La bolsa se reinicia por ventana, y hay más de una ventana.** Anthropic
   usa dos a la vez: una sesión de cinco horas y un tope semanal. La ventana
   corta es para que nadie queme el mes en una tarde; la larga es para acotar el
   coste del mes.
3. **Al agotarse, no se corta: se ofrece pagar.** El patrón universal es caer a
   consumo a **tarifa de API**, es decir, sin margen o con poco, y con un tope
   de gasto que **pone el propio cliente**.
4. **En pantalla se enseña una barra y una fecha de reinicio**, no dólares por
   turno. Ninguno de los seis pone el importe de cada interacción delante del
   usuario.
5. **El margen no sale del tope: sale de la distribución.** El plan se fija
   contra el uso mediano, no contra el máximo. La ventana existe para que el
   máximo sea finito y se repita un número conocido de veces al año.

### 2.2 · Anthropic — Claude Pro / Max / Team

- Pro **$17/mes anual o $20/mes mensual**; Max **desde $100/mes**; asiento Team
  estándar **$20 anual / $25 mensual**, asiento premium **$100 / $125**;
  Enterprise **$20/asiento** con *«usage billed at API rates»*.
  (claude.com/pricing, consultado 2026-09-11)
- **Dos ventanas**: sesión de cinco horas y tope semanal. El reinicio semanal
  cae en *«un horario fijo asignado a tu cuenta»* — **anclado al cliente, no a
  un lunes global** — y es visible en Ajustes › Uso.
- Al llegar al tope: avisos de capacidad restante, y la opción de **usage
  credits** facturados *«a tarifas de API estándar»* bajo **un tope de gasto
  mensual que fija el propio usuario**.
- Dato de calibración: el 6 de mayo de 2026 duplicaron permanentemente los
  límites de cinco horas y quitaron la reducción en hora punta; el refuerzo
  temporal del +50 % semanal pasó a un **+25 % permanente el 14 de septiembre de
  2026**. Es decir: **los topes se mueven, y se mueven hacia arriba**. Un
  número escrito en una tabla de precios envejece; uno en una columna, no.

### 2.3 · OpenAI — ChatGPT Business / Enterprise

- Business **$25/usuario/mes mensual o $20 anual**, mínimo 2 asientos; asiento
  premium **$125 / $100**. (Rebaja aplicada el 2 de abril de 2026.)
- **La suscripción y la API se facturan por separado**: un asiento de Business
  no incluye uso de API. Es la separación más limpia del grupo, y es la que
  P1 reproduce: la membresía de la app no es el consumo de los agentes.
- Codex pasó el 2 de abril de 2026 a **precio por uso**: el asiento trae una
  base y lo que pase de ahí se paga con **workspace credits**.

### 2.4 · Cursor — el caso que más se parece al nuestro

- Hobby gratis · **Pro $20** · **Pro+ $60** · **Ultra $200**. Asiento Teams
  premium **$120/mes**, introducido en junio de 2026, *«5× el uso por 3× el
  precio»*.
- **Pro incluye $20 de uso de modelos de terceros; Pro+ $70; Ultra $400.** El
  incluido *funciona como una cartera de crédito: un saldo que se reinicia por
  ciclo, se consume a tarifa por ítem, y cae a facturación bajo demanda cuando
  se vacía*.
- **Dos bolsas separadas**: la de sus modelos propios, generosa; y la de
  modelos de terceros (Claude, GPT) a tarifa de API, que es *la que se vacía*.
  Al vaciarse, o cambias a sus modelos o enciendes consumo bajo demanda a la
  misma tarifa de API, facturado a mes vencido.
- **La lectura para nosotros**: Cursor vende $20 de uso por $20. El margen de
  ese plan a fondo es **cero**, y depende por completo de que la mediana esté
  muy por debajo. Es exactamente la calibración que §4 no va a copiar.

### 2.5 · Lovable — el que cobra el crédito por encima de su coste

- **Pro $25/mes con 100 créditos mensuales**; Business $50/mes con 100 créditos
  más gobierno y SSO. Gratis: 5 créditos diarios, hasta 30 al mes.
- **Créditos de plan $0,25; de recarga $0,30** (Business: $0,50 y $0,60). Es
  decir, **la recarga cuesta un 20 % más que el incluido** — al revés que
  Cursor, que los cobra igual.
- **Los créditos del plan hacen rollover** mientras la suscripción siga viva,
  sujetos a su caducidad original; **las concesiones diarias no**. Recargas:
  12 meses de vida.
- **Miembros ilimitados en todos los planes**, y lo dicen explícitamente:
  *«invitar a más gente no cambia el coste de tu suscripción»*. El límite es el
  consumo, no los asientos. Es una postura, y es la contraria a P4.

### 2.6 · Microsoft Copilot — separar el asiento del agente

- Microsoft 365 Copilot es un **añadido por usuario** sobre una licencia base
  que hay que tener; precio estándar **$21/usuario/mes** en la promoción vigente
  hasta el 30 de septiembre de 2026, **$25,20** con compromiso mensual.
- Los **agentes** que se construyen en Copilot Studio no van por asiento: van
  por **Copilot Credits**, a **$200/mes por un paquete de 25.000 créditos** o
  **$0,01 por crédito** a demanda.
- **La lectura**: Microsoft separa explícitamente *la persona que usa* (asiento)
  de *el agente que trabaja* (créditos). Es P1 dicho por otro.

### 2.7 · Grok / xAI — el escalón de precio más ancho

- X Premium **$8/mes**, SuperGrok Lite **$10**, SuperGrok **$30**, X Premium+
  **$40/mes o $395/año**, SuperGrok Heavy **$300/mes**.
- API: Grok 4.6 a **$2,00 entrada / $0,50 cacheada / $6,00 salida** por millón
  bajo 200 K de contexto, y **aproximadamente el doble por encima de 200 K**.
- **La lectura**: el precio del token puede depender del **tamaño del
  contexto**, no solo del modelo. Si algún día un teammate trabaja con contextos
  muy largos, el coste por token de cuota no es constante.

### 2.8 · Lo que ninguno hace, y conviene no inventar

- Ninguno enseña el **importe en dólares de cada turno** al usuario. Coincide
  con la decisión 14 de [[teammates/10-decisiones]].
- Ninguno **corta en seco sin avisar**: todos avisan con margen y ofrecen una
  salida (esperar, cambiar de modelo, pagar).
- Ninguno deja que el cliente **elija el modelo caro con la misma cuota** que el
  barato sin que eso se note en el contador. Cursor lo resuelve contando en
  dólares; nosotros tendremos que resolverlo de alguna manera (§4.4).

---

## 3. Lo que nos cuesta el consumo — precios verificados

### 3.1 · Anthropic, por millón de tokens

Tarifas publicadas en claude.com/pricing, **consultado el 2026-09-11**:

| Modelo | Entrada | Salida | Caché lectura | Caché escritura |
|---|---:|---:|---:|---:|
| Fable 5.1 | 10,00 | 50,00 | 0,25 | 12,50 |
| Opus 5 | 5,00 | 25,00 | 0,50 | 6,25 |
| Sonnet 5 | 2,00 | 10,00 | 0,20 | 2,50 |
| Haiku 4.5 | 1,00 | 5,00 | 0,10 | 1,25 |

Dos observaciones que valen dinero:

- **Haiku 4.5 coincide exactamente** con lo sembrado en la migración `0072`. Esa
  fila está bien y no hay que tocarla.
- **`claude-sonnet-4-6` no aparece en la tabla vigente.** El repositorio lo tiene
  a 3,00/15,00. **Sonnet 5 cuesta 2,00/10,00**: un tercio menos por el mismo
  trabajo. No se puede verificar hoy si la tarifa de Sonnet 4.6 sigue siendo
  3/15 —la página ya no lo lista—, así que **esa fila se queda como está y se
  marca como no verificada**, que es lo que el catálogo ya sabe expresar.

### 3.2 · OpenAI, por millón de tokens

Tarifas publicadas en developers.openai.com/api/docs/pricing, **consultado el
2026-09-11**:

| Modelo | Entrada | Entrada cacheada | Salida |
|---|---:|---:|---:|
| **`gpt-5.6-sol`** | **4,00** | **0,40** | **20,00** |
| **`gpt-5.6-terra`** | **2,00** | **0,20** | **12,00** |
| **`gpt-5.6-luna`** | **0,20** | **0,02** | **1,20** |
| GPT-6 Astra | 10,00 | 1,00 | 50,00 |
| `gpt-4o` | 2,50 | 1,25 | 10,00 |

- **Las tres filas NULL del catálogo se pueden cerrar hoy**, con fuente y fecha.
  Es el ítem C1 del plan de pendientes, y deja de ser una decisión: es un
  `UPDATE`.
- **La caché de OpenAI descuenta exactamente 0,1×** en los tres modelos que
  vendemos (0,40/4,00 · 0,20/2,00 · 0,02/0,20). El peso `0,1` de `quota_tokens()`
  **coincide con la factura real**, lo cual es una suerte que conviene escribir
  antes de que alguien lo cambie sin saberlo.
- **OpenAI no cobra la escritura de caché**, que es justo lo que la migración
  `0076` ya razonó para `gpt-4o` al dejar esa columna en NULL. Mismo criterio
  para los tres nuevos.
- No se verificó hoy la tarifa de Whisper (`$0,006/min`, cargada el 2026-08-11).
  Se deja como está y se anota para revisar.

### 3.3 · Lo que confirma el plan de pendientes

El ítem **C4** decía: *«Sol cuesta 4/20 $/Mtok y Sonnet 4.6 cuesta 3/15: el
modelo que vendemos es más caro que el que usa producción»*. **Verificado.** Y
con `llm_companion_model = "openai/gpt-5.6-sol"` la frase se agrava: no es que
lo vendamos más caro, es que **lo usamos** para cada turno de teammate.

---

## 4. Aritmética: de tokens de cuota a dólares

### 4.1 · El turno de referencia

Toda la conversión depende de la forma del turno, así que se declara y se usa la
misma en todas partes. Sale del §1.1 de [[teammates/08-coste-y-precio]]: *«la
entrada domina; la salida es la parte pequeña»*.

| Componente | Tokens |
|---|---:|
| `prompt_tokens` | 30.000 |
| de ellos `cache_read` (acierto del 80 %) | 24.000 |
| `uncached_input` | 6.000 |
| `output_tokens` | 1.500 |

`quota = 6.000 + 0,1 × 24.000 + 1.500 = **9.900**` ≈ 10 K por turno de trabajo.

**Esto es un supuesto, no una medida.** Se puede comprobar contra
`companion.runs` en producción antes de escribir la spec, y debería hacerse.

### 4.2 · Coste por millón de tokens de cuota

| Modelo | Entrada | Caché | Salida | **$/M cuota** |
|---|---:|---:|---:|---:|
| `gpt-5.6-sol` | 0,0240 | 0,0096 | 0,0300 | **6,42** |
| `gpt-5.6-terra` | 0,0120 | 0,0048 | 0,0180 | **3,52** |
| `gpt-5.6-luna` | 0,0012 | 0,0005 | 0,0018 | **0,35** |
| Sonnet 5 (referencia) | 0,0120 | 0,0048 | 0,0150 | 3,21 |
| Haiku 4.5 (referencia) | 0,0060 | 0,0024 | 0,0075 | 1,61 |

(Columnas intermedias en dólares por turno de referencia; la última es el total
dividido entre 9.900 y llevado a millón. **La escritura de caché queda fuera**
por dos razones que se refuerzan: OpenAI no la cobra, y `quota_tokens()` ya la
excluye del tope a propósito. Para los modelos de Anthropic eso subestima el
coste real en torno a un 15 %, y conviene tenerlo escrito.)

**Sol cuesta 18× lo que Luna por el mismo token de cuota.** Ése es el número que
decide toda la sección de márgenes.

### 4.3 · Contraste con el tope por defecto de hoy

`partners.companion_monthly_token_cap` vale **500.000** por defecto, y su
comentario dice *«≈300-500 turnos de Companion»* — o sea, un turno de Companion
de consola son ~1.200-1.600 tokens de cuota. El turno de **teammate** del §4.1
es **seis veces mayor**. No es contradicción: son dos trabajos distintos. Pero
significa que **el tope por defecto de hoy da unos 50 turnos de teammate al
mes**, y eso es lo que hay que corregir al dimensionar el pool.

### 4.4 · El problema que la aritmética destapa

Si el pool es **plano en tokens de cuota**, el coste del mismo pool varía 18×
según el modelo que elija el partner. A tamaños de pool razonables (§ del
`concept.md`) eso hace que **el plan más caro sea deficitario si se agota
entero en Sol**.

Hay tres salidas, y solo una respeta «un solo medidor»:

| Salida | Qué implica |
|---|---|
| **A · Pool plano + lista de modelos por plan** | El plan de 20 $ no ve Sol. Mecanismo ya construido: `partner_model_allowlist` (0098) es una fila por modelo y partner. Barato, pero convierte el modelo en una función del precio y eso se nota en la conversación de venta |
| **B · Peso por modelo dentro de `quota_tokens()`** | Un token de cuota de Sol pesa 1,8; de Terra, 1,0; de Luna, 0,1 (normalizado a Terra). **No es un segundo medidor**: es el mismo peso que ya lleva `cache_read` a 0,1, en la misma función, y por tanto las tres superficies siguen viendo la misma cifra. Acota el coste del pool **sea cual sea el modelo** |
| C · Contar en dólares, como Cursor | Rompe la decisión 14 («sin importe en dólares») y mete la volatilidad de las tarifas del proveedor dentro del contador que el partner mira |

**B es la recomendación**, con A como techo administrativo que ya existe y no
estorba. La razón de fondo: con peso por modelo, el peor caso del plan está
**acotado por construcción**; sin él, depende de una elección del partner que
nosotros no controlamos.

---

## 5. Stripe: qué hace, qué no hace, y por qué importa

Verificado en docs.stripe.com el 2026-09-11.

### 5.1 · Credit grants — lo más parecido a nuestro wallet

- Un *credit grant* rastrea créditos prepagados o promocionales de un cliente,
  con estados `pending · granted · depleted · expired · voided`.
- **Caducan solo si se fija `expires_at`.** Sin ese campo no caducan nunca.
- Se pueden emitir con `effective_at` futuro — es decir, **se puede programar
  una concesión semanal**.
- **Solo se aplican a *subscription items* con precio *metered* que reporten por
  Meters.** No se aplican a facturas sueltas, ni a líneas de precio *licensed*,
  ni a los `usage_records` antiguos.
- Límite duro: **100 concesiones sin usar por cliente**. Una concesión semanal
  que caduca cada semana nunca se acumula; una sin caducidad llegaría al límite
  en dos años. Es un argumento más para que el pool caduque.

### 5.2 · La frase que decide la pregunta difícil

> **«Credits apply to invoices only at the time of finalization.»**

Los créditos de Stripe se aplican **al cerrar la factura**. Un saldo que solo se
conoce cuando cierra el mes **no puede parar un turno**. Y los *billing
thresholds* disparan facturas, no cortes.

Añádase que los *meter events* son un canal de facturación con su propia
latencia de ingesta, y que la constitución exige fail-closed —*«si el libro no se
puede leer, el saldo es 0 y no hay LLM»*—, y la conclusión se escribe sola:
**el tope es de la plataforma; Stripe cobra.** El desarrollo está en el
`concept.md`, D2.

### 5.3 · Stripe Tax

Calcula y cobra IVA/GST/sales tax, vigila umbrales de registro y puede ayudar
con el registro y la presentación *«directamente o a través de socios»*. Lo que
**no** deja de ser obligación del comerciante: estar registrado donde toque y
remitir. ADR-022 §2 lo dejó **apagado en V1** con facturas sin IVA e inversión
del sujeto pasivo B2B, y esa decisión se tomó para un canal de dos agencias.
Una membresía de 20 USD vendida a cualquiera es otro animal fiscal.

### 5.4 · Licencia

`stripe` (PyPI), **licencia MIT**, versión 15.6.1 publicada el 2026-09-01.
MIT es un sí explícito por el principio VIII de la constitución y por la regla 7
de [[nexus/PLAN-CONSOLE-V1]]. **No está instalada hoy**: no aparece en
`apps/api/pyproject.toml`. Será dependencia nueva y su párrafo de licencia va
citado en el plan de la spec.

---

## 6. El elefante: ADR-022 está aprobado y describe otra cosa

[[nexus/decisions/ADR-022-stripe-integration-v1]] (2026-05-20, `status:
approved`, *«todas vinculantes salvo que una ADR posterior las supersede»*)
decide, entre otras:

- **Nada de *metered billing***: *«Auphere es fixed-tier per ADR-007. No
  vendemos por uso.»*
- Tipo A (partner): **un `Subscription Item` por cliente final**, con el precio
  según el *tier* del partner (70 % / 60 % / 50 % del PVP según tenga 1-4, 5-14
  o 15+ clientes), y cambio de *tier* automático los días 25-28.
- Cobro **prepago**: el cargo del día 1 cubre el mes que empieza.
- **Stripe Tax apagado**, USD y CLP, descuento anual del 10 %.
- Tablas `stripe_events_log`, `stripe_idempotency_keys`,
  `billing_setup_charges`, y columnas `stripe_*` en `partners` y `tenants`.

**P1–P3 no caben dentro de eso.** Una membresía de la aplicación con pool
semanal y caída a créditos prepagados **es** facturación por uso, y el número de
teammates y de personas no es el número de clientes finales. El propio plan de
pendientes lo dice en su §5: *«K1 · modelo de precio. ADR-022 es de mayo y
describe algo que el código no factura.»*

Lo que sí se conserva de ADR-022, y hay que conservarlo porque es trabajo de
diseño ya hecho y bien hecho:

- **Idempotencia por `event.id`** y la tabla de log de eventos.
- **Claves de idempotencia** en toda mutación saliente, con su patrón de nombre.
- **Subscription Schedules** con `proration_behavior='none'` para que un cambio
  de plan se aplique el día 1 — que es exactamente lo que hace falta para bajar
  de plan (D5 del `concept.md`).
- **Firma verificada + persistir + encolar + 200 en <500 ms** en el webhook.
- **Anclaje del ciclo al día 1** y prorrateo nativo al alta a mitad de mes.

Conclusión: **hace falta un ADR nuevo que supersede los §1-§5 y §8-§10 de
ADR-022 y conserve los §13-§15.** No es un detalle de trámite: sin eso, la spec
contradice una decisión aprobada, y el principio IX obliga a que la KB sea dueña
del porqué.

---

## Fuentes

- [Claude pricing](https://claude.com/pricing) — planes y tarifas de API, consultado 2026-09-11
- [Using Claude Code with your Pro or Max plan](https://support.claude.com/en/articles/11145838-using-claude-code-with-your-pro-or-max-plan) — límites compartidos y *usage credits* a tarifa de API, consultado 2026-09-11
- [Claude Code usage limits (2026)](https://www.morphllm.com/claude-code-usage-limits) — ventana de cinco horas, tope semanal anclado a la cuenta, consultado 2026-09-11
- [Claude usage limits 2026: every change, dated](https://www.explainx.ai/blog/claude-usage-limits-2026-timeline-explained) — duplicación del 6-may-2026 y paso del +50 % al +25 % permanente el 14-sep-2026, consultado 2026-09-11
- [OpenAI API pricing](https://developers.openai.com/api/docs/pricing) — tarifas de Sol, Terra y Luna, consultado 2026-09-11
- [ChatGPT Business FAQ](https://help.openai.com/en/articles/8542115-chatgpt-business-faq) — asientos, y separación entre suscripción y API, consultado 2026-09-11
- [Cursor pricing](https://cursor.com/pricing) — Hobby/Pro/Pro+/Ultra, consultado 2026-09-11
- [Cursor pricing explained 2026 (Vantage)](https://www.vantage.sh/blog/cursor-pricing-explained) — $20/$70/$400 de uso incluido, dos bolsas y consumo bajo demanda, consultado 2026-09-11
- [Lovable pricing](https://lovable.dev/pricing) — concesiones diarias, caducidad y miembros ilimitados, consultado 2026-09-11
- [Lovable pricing 2026 (Softr)](https://www.softr.io/blog/lovable-pricing) — $25/100 créditos, recarga a $0,30, rollover, consultado 2026-09-11
- [Microsoft Copilot pricing 2026 (GoSearch)](https://www.gosearch.ai/blog/microsoft-copilot-pricing/) — asiento y Copilot Credits, consultado 2026-09-11
- [Grok pricing 2026 (FelloAI)](https://felloai.com/grok-pricing/) — planes y tarifas de API por tamaño de contexto, consultado 2026-09-11
- [Stripe · Billing credits](https://docs.stripe.com/billing/subscriptions/usage-based/billing-credits) — credit grants, caducidad, aplicación en el cierre de factura, límite de 100, consultado 2026-09-11
- [Stripe Tax](https://docs.stripe.com/tax) — cálculo, cobro, vigilancia de umbrales y presentación, consultado 2026-09-11
- [stripe · PyPI](https://pypi.org/project/stripe/) — licencia MIT, 15.6.1 del 2026-09-01, consultado 2026-09-11
