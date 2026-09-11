# Concept: la membresía, el pool semanal y quién manda sobre el tope

- **Slug**: membresias-y-consumo-stripe
- **Fecha**: 2026-09-11
- **Apetito**: `large` — pero no por el código. El código es una columna de
  período, un peso por modelo, dos columnas de tope, un webhook y dos líneas de
  recibo. Lo que lo hace grande es que toca **dinero, impuestos y una ADR
  aprobada**, y que hay que decidir siete cosas antes de escribir una línea.

## La forma

Dos bolsillos y una caída de uno al otro:

```
MEMBRESÍA ─── pool semanal (caduca) ────┐
                                        ├──► teammates
CRÉDITOS ──── saldo comprado (no caduca)┘
       └────────────────────────────────────► clientes finales
```

- El **pool** es de la aplicación: lo gastan los teammates y el Companion.
  Caduca cada semana y se repone solo.
- Los **créditos** son de la plataforma: los gastan los agentes de los clientes
  finales **siempre**, y los teammates **cuando el pool se agota**. No caducan,
  porque se pagaron.
- **Ambos son el mismo libro**: `partner_wallets.included_remaining` y
  `partner_wallets.purchased_remaining`. Esas dos columnas existen hoy con esa
  semántica exacta. Lo único que cambia es el **período** del primero y **quién
  puede gastarlo**.

Esto cierra, por decisión de producto, la deuda **D5** del plan de pendientes:
*«separar el bolsillo del Companion del de los clientes»*.

## Las membresías

**Tres niveles de catálogo, y un suelo que no es un nivel.** Un partner tiene
**una** membresía y sube o baja de nivel; no se acumulan. El pool va en **tokens
de cuota equivalentes a Terra** (D3 explica por qué «equivalentes»).

> **Las cifras de esta tabla son provisionales**, y lo son a propósito. Salen de
> un turno de referencia **supuesto** de 9 900 tokens de cuota. Lo que queda
> fijado es la **estructura** —tres niveles, pool semanal, caída a créditos,
> 65 % de margen objetivo sobre el crédito y ningún plan deficitario a fondo—;
> los números se cierran después de medir el turno real contra
> `companion.runs`. Si el turno real es el doble, el plan de 20 $ da 25 turnos a
> la semana y no se puede vender.

| | Consola (sin membresía) | **Base** | **Equipo** | **Estudio** |
|---|---:|---:|---:|---:|
| Precio | **0 $** | **20 $/mes** | **60 $/mes** | **150 $/mes** |
| Pool semanal | 100 000 | 500 000 | 2 000 000 | 6 000 000 |
| Pool al mes (×4,33) | 0,43 M | 2,17 M | 8,66 M | 26,0 M |
| Turnos de trabajo/semana ≈ | — | ~50 | ~200 | ~600 |
| Companion de la consola | **sí** | sí | sí | sí |
| Teammates | **0** | 2 | 6 | 12 |
| Personas colaborando | 1 | 1 | 3 | 8 |
| Ejecución en la máquina | no | **sí** | **sí** | **sí** |
| Techo de ejecución configurable | — | no (defecto de plataforma) | sí, por persona | sí, por persona |
| Cerebros disponibles | Luna | Luna · Terra | + **Sol** | + Sol |
| **Coste a fondo** | 1,52 $ | 7,62 $ | 30,48 $ | 91,45 $ |
| **Margen bruto de modelo a fondo** | — | **62 %** | **49 %** | **39 %** |

«Turno de trabajo» = el turno de referencia del §4.1 de
[`research.md`](./research.md): 30 K de prompt con 80 % de acierto de caché y
1,5 K de salida ≈ **9 900 tokens de cuota**.

### El suelo de la consola no es un cuarto plan

Es lo que trae **toda cuenta de partner**, tenga membresía o no, y existe por una
razón estructural: **el Companion vive en la consola, no en la aplicación.** Un
partner de agencia que opera clientes finales y no ha comprado la app tiene hoy
el Companion encendido; atarlo a una membresía de escritorio se lo quitaría.

- El pool del suelo **solo lo gasta el Companion de la consola**. No da
  teammates, no da ejecución en la máquina, y solo ofrece el cerebro barato.
- **No se suma al plan: lo reemplaza.** El pool semanal es el del plan vigente;
  sin plan, el del suelo. Sumar obligaría a explicar dos bolsas dentro del mismo
  bolsillo, que es justo lo que D3 evita.
- Cuesta **1,52 $ al mes por partner que no paga nada** si lo agota entero. Es
  coste de adquisición, es acotado y es visible en el mismo libro que todo lo
  demás — no es un regalo invisible.
- **Reutiliza el número que ya existe.** 100 000 semanales ≈ 433 000 al mes ≈ el
  `companion_monthly_token_cap` de 500 000 que hoy es el defecto. El suelo no es
  un concepto nuevo: es el tope de hoy, con el período nuevo y el alcance
  arreglado.

### Por qué la ejecución local va en los tres

Porque no nos cuesta nada y es la razón de existir del producto. La máquina es
del partner y ya está pagada; `services/local_workstation_metering.py` lo
garantiza por construcción —*«esta función no recibe ninguna duración, así que
no se puede facturar tiempo ni por accidente»*—. Quitarla del plan de entrada
dejaría un plan de 20 $ que no hace lo que la aplicación existe para hacer. Lo
que sí escala con el plan es **el control**: el techo de ejecución por persona
de la spec 001 (`services/local_exec_policy.py`, `most_restrictive`) es una
función de equipo, y un equipo de una persona no lo necesita.

### Por qué no el doble por el doble

| De → a | Precio | Pool | Teammates | Personas |
|---|---:|---:|---:|---:|
| Base → Equipo | ×3 | **×4** | ×3 | ×3 |
| Equipo → Estudio | ×2,5 | **×3** | ×2 | ×2,7 |

El pool crece **más rápido que el precio** en los dos escalones, y eso es
deliberado:

1. **El coste fijo por partner no crece con el pool.** El libro, los avisos, la
   renovación, el sitio en la base, el correo del recibo y la atención de la
   primera semana cuestan lo mismo para un partner de 20 $ que para uno de 150 $.
   Un precio estrictamente proporcional al pool cobraría ese fijo tres veces.
2. **El margen porcentual baja y el absoluto sube.** 62 % de 20 $ son 12,4 $;
   39 % de 150 $ son 58,6 $ — casi cinco veces más margen absoluto. Es lo que
   paga un soporte que no escala con la factura.
3. **Y si fuera el doble por el doble, apilar planes sería igual de bueno que
   subir de plan.** Con este escalado no lo es: tres Base cuestan 60 $ y dan
   1,5 M semanales; Equipo cuesta 60 $ y da 2 M. Subir siempre gana, que es lo
   que se quiere.
4. **El suelo está en 62 % y el techo del riesgo en 39 %.** Ningún plan es
   deficitario aunque se agote entero todas las semanas del mes. Cursor vende
   20 $ de uso por 20 $ —margen cero a fondo— y depende por completo de que la
   mediana sea baja. Nosotros no dependemos de eso.

### Lo que NO incluye ninguno de los tres

- **Consumo de los clientes finales.** Eso son créditos, siempre, en los tres
  planes. El pool es de la aplicación.
- **SSO, SCIM ni marca del partner.** Son CP-35 a CP-37, de Fase 2.
- **Más clientes finales.** `partners.max_clients` **sigue siendo independiente
  del plan**, y conviene decidirlo así explícitamente: atar el número de clientes
  a la membresía de la aplicación convertiría la membresía en un proxy del
  negocio de agencia, que es justo el modelo de ADR-022 del que esto se separa.
- **SLA.** No existe hoy; prometerlo aquí sería venderlo.
- **Acumulación del pool no gastado.** D1.

## Precio del consumo y margen

### La tarifa

**10 $ por millón de tokens de cuota (equivalente Terra).** Coste 3,52 $ →
**65 % de margen bruto**. Se vende en paquetes prepagados; el saldo no caduca.

**El mismo precio para el crédito comprado que para el del pool.** Lovable cobra
la recarga un 20 % más cara que el incluido; Cursor cobra igual. Se elige igual
por una razón de pantalla: dos precios para el mismo token obligan a explicar
cuál se está gastando en cada momento, y la pantalla ya tiene bastante con
explicar de qué bolsillo sale.

Consecuencia que hay que aceptar y decir en voz alta: el pool de Base «vale»
21,7 $ a tarifa de crédito y cuesta 20 $. **La membresía no es un descuento
sobre tokens** — es el precio de la aplicación, de los asientos y de la
ejecución en la máquina, con una bolsa dentro para que un partner nuevo pueda
trabajar el primer día sin comprar nada.

### Tres escenarios completos

Supuestos comunes: modelo pagado a coste Terra (3,52 $/M cuota por el peso de
D3), crédito vendido a 10 $/M, Stripe 2,9 % + 0,30 $ por cobro. **No incluye
AWS**: el reparto por partner sale de [[nexus/PLAN-EJECUCION-COSTES-AWS-2026-09-08]]
y se cruza al escribir la spec.

**A · Partner pequeño** — plan Base, 1 persona, 2 teammates, 1 cliente final
pequeño (≈900 turnos de canal al mes ≈ 1,44 M de cuota).

| | Cuota | $ |
|---|---:|---:|
| Membresía Base | — | +20,00 |
| Créditos comprados (1,5 M) | — | +15,00 |
| Consumo de teammates (30 % del pool) | 0,65 M | −2,29 |
| Consumo del cliente final | 1,44 M | −5,07 |
| Comisión de Stripe (2 cobros) | | −1,62 |
| **Resultado** | | **+26,02 (74 %)** |

**B · Partner medio** — plan Equipo, 3 personas, 5 teammates, 4 clientes.

| | Cuota | $ |
|---|---:|---:|
| Membresía Equipo | — | +60,00 |
| Créditos comprados (6 M) | — | +60,00 |
| Consumo de teammates (60 % del pool) | 5,20 M | −18,30 |
| Consumo de los 4 clientes | 5,76 M | −20,28 |
| Comisión de Stripe (2 cobros) | | −4,08 |
| **Resultado** | | **+77,34 (64 %)** |

**C · El que se pasa** — plan Base, 1 persona, agota el pool **todas** las
semanas y sigue trabajando contra créditos.

| | Cuota | $ |
|---|---:|---:|
| Membresía Base | — | +20,00 |
| Créditos comprados (1,73 M, un 80 % más de pool) | — | +17,30 |
| Pool consumido a fondo | 2,17 M | −7,62 |
| Consumo sobre créditos | 1,73 M | −6,09 |
| Comisión de Stripe (2 cobros) | | −1,68 |
| **Resultado** | | **+21,91 (59 %)** |

### Por qué un usuario pesado no se come el margen

Tres límites independientes, y **dos ya están construidos**:

1. **La ventana semanal acota el peor caso** y lo hace repetible un número
   conocido de veces al año. Es el mecanismo que Anthropic usa y por el que
   existe su tope semanal.
2. **La caída es a saldo prepagado, no a factura.** No hay nada que reclamar
   después: o hay saldo o no hay turno. `_require_wallet` y `allow_channel_turn`
   ya cierran esa puerta hoy, y son fail-closed hasta cuando el libro no se
   puede leer.
3. **El peso por modelo acota el coste por token** (D3). Sin él, el escenario C
   en Sol costaría 13,90 $ en vez de 7,62 $ y el plan Estudio a fondo sería
   deficitario.

## Las decisiones que no son técnicas

### D1 · ¿Cuándo empieza la semana, y qué pasa con lo que sobra?

**La semana se ancla al partner, no a un lunes global.** Anthropic lo hace así
—*«un horario fijo asignado a tu cuenta»*— y hay dos razones propias: un lunes
global concentra toda la renovación de la plataforma en un tick, y un partner
que se da de alta un viernes tendría una primera «semana» de dos días.

**Lo que no se gasta, no se acumula.** Razón: acumular convierte un peor caso
semanal acotado en un pico mensual de 4× — que es exactamente lo que la ventana
semanal existe para evitar. Y contablemente, crédito sin gastar que sobrevive es
un pasivo; el pool no se ha pagado como crédito, se ha pagado como suscripción.

**Los créditos comprados sí sobreviven**, siempre, sin caducidad. La asimetría ya
está en el modelo de datos: `included_expires_at` existe y `purchased_remaining`
no tiene columna de caducidad, y el docstring de `partner_wallet.py` lo dice en
una línea: *«`included` caduca; `purchased` no»*. **La decisión ya está tomada
en el esquema; lo único que cambia es el período.**

Mecánicamente cuesta casi nada: `next_period_end()` pasa a calcular el siguiente
límite semanal desde el ancla del partner, y `renew_included_if_expired` **no se
toca**, porque ya dispara por caducidad y no por calendario. El cron horario que
existe sirve igual.

### D2 · ¿Manda Stripe sobre el tope? — **No. El tope es de la plataforma.**

Ésta es la que más arrastra, así que va con todas las letras.

**Stripe cobra. La plataforma corta.** Cuatro razones, la primera decisiva:

1. Los *credit grants* de Stripe **se aplican al cerrar la factura** —*«credits
   apply to invoices only at the time of finalization»*—. Un saldo que solo se
   conoce al cierre del período no puede parar un turno. Los *billing thresholds*
   disparan facturas, no cortes.
2. Los *credit grants* solo se enganchan a precios *metered* reportados por
   *Meters*, que es un canal de facturación con su propia latencia de ingesta.
   Entre el turno y el evento hay segundos o minutos; el libro decide en la
   misma transacción.
3. **Fail-closed.** La política del repositorio es que si el libro no se lee, el
   saldo es 0 y no hay LLM. Con Stripe como fuente de verdad, «Stripe caído»
   significaría «nadie trabaja» o, peor, «todos trabajan gratis».
4. **Ya está construido y es mejor**: `debit_wallet` bloquea la fila, reparte
   entre cubos, escribe asiento y es idempotente por clave. Stripe no tiene nada
   equivalente porque no es su trabajo.

La consecuencia que hay que aceptar: **dos libros que tienen que conciliar.** El
nuestro es la verdad para dejar pasar o no; el de Stripe es la verdad para el
dinero. La conciliación va en **una sola dirección**: un pago confirmado suma
`purchased`, idempotente por `event.id`. **Nada en Stripe debita nunca nuestro
wallet.** Es exactamente lo que K2 ya especificó.

### D3 · ¿Un solo medidor sigue siendo un solo medidor? — Sí, y hay que arreglar el que ya hay

La constitución (§V) y la decisión 14 lo exigen. Hoy **ya está roto**: `budget`
suma `companion.runs` y el wallet suma todo, con el mismo número dimensionando
los dos (§1.3 de [`research.md`](./research.md)).

**La regla, y es una supresión, no una adición:**

> El pool **es** `partner_wallets.included_remaining`. `budget_out(used, cap)`
> toma su `used` y su `cap` **del wallet**, no de la suma de runs.
> `sum_partner_companion_tokens` deja de ser el total y pasa a ser **solo la
> atribución** — quién gastó, no cuánto se gastó.

Con eso, `/console/companion/budget`, `/console/teammates/usage` y la pantalla
Cuenta leen el mismo entero de la misma fila, y desaparece el caso de «budget al
20 % y 409 `wallet_empty`». La línea «gastado en otro sitio» de `account.tsx`
sigue haciendo falta y sigue diciendo la verdad: la diferencia entre lo atribuido
a teammates y el total del partner.

**Y el peso por modelo va dentro de `quota_tokens()`, no fuera.** La unidad ya no
es un token nativo: `cache_read` pesa 0,1 desde C3. Añadir un factor por modelo
—normalizado a Terra: **Luna ×0,1 · Terra ×1,0 · Sol ×1,8**— es el mismo tipo de
peso, en la misma función, y por tanto **las tres superficies siguen viendo el
mismo número**. Si el peso viviera fuera —en el cobro, o en la consola— habría
dos cifras otra vez, y ésa es la definición del problema que se está evitando.

**La propiedad que lo justifica**, y conviene escribirla porque es el argumento
entero en una línea: **con el peso puesto, agotar el pool cuesta lo mismo sea
cual sea el cerebro.** Comprobado: vaciar el pool de Base cuesta 7,61 $ en Luna,
7,61 $ en Terra y 7,61 $ en Sol; vaciar el de Estudio, 91,32 $ en los tres. Sin
el peso, ese mismo pool de Estudio cuesta 91 $ en Terra y **166,90 $ en Sol**,
contra un precio de 150 $. El peso no es una sutileza contable: es lo que
convierte el peor caso de cada plan en un número que conocemos de antemano en
vez de en una elección del partner.

Consecuencia de honestidad: el pool deja de ser «tokens» a secas. Se nombra y se
explica una vez —*«tokens de cuota, equivalentes al cerebro Terra»*— y la
etiqueta relativa `bajo · medio · alto` que `services/model_choices.py` ya
publica por teammate es donde el partner ve qué le cuesta cada cerebro.

### D4 · Impagos y degradación — nada desaparece

Escalera, de menos a más, reutilizando estados que ya existen:

| Estado | Qué pasa |
|---|---|
| **Al corriente** | Pool + créditos |
| **Pago fallido** (`invoice.payment_failed`) | El pool **no se repone** en su siguiente renovación semanal. Los créditos comprados siguen funcionando. Aviso en consola y en la app, con el motivo y la fecha del siguiente intento |
| **Impagado** (reintentos agotados) | El pool queda a 0. **Los teammates no se archivan y las tareas no se cancelan.** Lo que está en marcha termina; lo nuevo recibe el mismo 409 `budget_paused` que ya existe, con otro texto. La consola sigue leyéndose entera |
| **Cancelada** | Igual que impagado, y además la suscripción se cierra a fin de período (Subscription Schedule, `proration_behavior='none'`). **Nada se borra**: §IV de la constitución, *«borrar no existe: se archiva»* |

Lo que **no puede pasar bajo ninguna circunstancia**: que un teammate
desaparezca de la nómina, que una tarea se cancele en silencio, o que una
confirmación pendiente se evapore. La spec 003 ya garantiza que las
confirmaciones sobreviven a una pausa por tope (`pausaPorTope`, Requisito 9.3);
aquí se reutiliza esa garantía con otro motivo, y se prueba con otro test.

### D5 · Prorrateo y créditos comprados

- **Subir de plan: inmediato.** Stripe con `create_prorations`, y el pool de la
  semana en curso se **completa** hasta el tamaño del plan nuevo
  (`included_remaining += nuevo − viejo`, nunca negativo). **No se reinicia**:
  reiniciar castigaría a quien sube precisamente porque se quedó sin pool.
- **Bajar de plan: al final del período**, con Subscription Schedule y
  `proration_behavior='none'` — el mecanismo que ADR-022 §2 ya eligió para esto.
  El pool de la semana en curso no se reclama.
- **Los créditos comprados no los toca ningún cambio de plan.** Ni al subir, ni
  al bajar, ni al cancelar. Se pagaron. Que no tengan columna de caducidad hoy
  es la decisión, y conviene escribirla para que nadie añada una.
- **Abierto**: qué pasa con el saldo comprado al **cerrar la cuenta**. Se
  devuelve, se pierde, o se conserva N meses por si vuelve. Va a
  `/speckit-clarify`.

### D6 · Qué ve el cliente final — nada, y se prueba

El cliente final no tiene consola ni aplicación (decisión 2 del 2026-08-27), así
que no hay pantalla en la que pudiera verlo. Estructuralmente tampoco hay
superficie: la membresía es un objeto **de partner**, sin `tenant_id`, y
`partner_wallets` lleva RLS FORCE por `partner_id` mientras `usage_records` la
lleva por `tenant_id`. Son dos planos que no se cruzan.

Lo que hay que **probar**, no afirmar: que ninguna respuesta de un endpoint
orientado a cliente final menciona plan, pool, saldo ni precio. El patrón existe
— CP-21 hace exactamente esa prueba estructural sobre el esquema OpenAPI para el
contenido de conversación, y `apps/edition/tests/test_no_end_client_credentials.py`
ya incluye `STRIPE_SECRET_KEY` en su lista de credenciales prohibidas. Se copia
el patrón, no se inventa.

### D7 · Impuestos y el recibo que ya existe

**Stripe Tax calcula, cobra y vigila umbrales; no asume la obligación.** Estar
registrado donde toque y remitir sigue siendo nuestro. ADR-022 apagó Stripe Tax
para un canal de dos agencias con inversión del sujeto pasivo B2B; una membresía
de 20 $ vendible a cualquiera cambia el problema —B2C posible, IVA europeo y
ventanilla única, IVA chileno—. **Esto necesita asesoría fiscal, no una decisión
de ingeniería**, y es el riesgo no técnico más grande de toda la evaluación.

Lo que hay que guardar **pase lo que pase con Stripe Tax**: el recibo mensual
(`services/partner_receipt.py`) ya existe, ya es idempotente por
`(partner, año, mes)`, ya maneja el cambio CLP→USD una sola vez al dólar
observado del día, y ya se envía por correo. **Le faltan dos líneas**: la de
membresía y la de consumo.

Y una decisión para que no haya dos documentos que se contradigan: **la factura
de Stripe es el documento fiscal; nuestro recibo pasa a ser el detalle de
consumo que la acompaña**, no una segunda factura. Hoy el recibo dice «Total a
pagar» y vence el día 5; en cuanto Stripe cobre, eso sería mentira.

## Alcance

**Dentro**: el período semanal del `included` con ancla por partner; el peso por
modelo dentro de `quota_tokens()`; `budget_out` leyendo del wallet; la tabla de
membresías con sus topes de teammates y de personas; la comprobación de esos
topes; Stripe Checkout para alta y para compra de créditos; el webhook con firma
verificada, log de eventos e idempotencia por `event.id`; la escalera de impago;
las dos líneas nuevas del recibo; **las tarifas de Sol, Terra y Luna cargadas
con fuente y fecha** (ítem C1) y las filas de `meter_prices` que faltan (C2); y
el ADR nuevo que enmienda ADR-022.

**Y lo primero de todo, antes de tocar el cobro**: cerrar el ítem C1. Cargar tres
tarifas es un `UPDATE` y una migración, y sin él **todo cálculo de margen de esta
evaluación sigue siendo un supuesto en producción**. No tiene sentido construir
una escalera de planes sobre un coste que la plataforma no sabe calcular.

**Fuera**: el reloj de máquina (no hay VM); el cobro al cliente final del partner
(sigue sin Connect); SSO, SCIM y marca del partner; la venta directa de ADR-007;
la landing; y cualquier cambio a `partners.max_clients`.

## Lo que se reutiliza

| Pieza | Qué evita construir |
|---|---|
| `partner_wallets` con sus dos cubos | El modelo de datos entero de pool + créditos |
| `renew_included_if_expired` | La renovación: **ya dispara por caducidad, no por calendario**, así que sirve igual para semanas |
| `debit_wallet` / `usage_ledger` | Débito atómico, reparto entre cubos, idempotencia y asiento |
| `quota_tokens()` | La unidad, y el precedente de que la unidad lleva pesos dentro |
| `partner_model_allowlist` (0098) | «Qué cerebros da cada plan»: una fila por modelo y partner, con RLS |
| `wallet_alerts` | Los avisos al 80 % y al 100 %, con dedupe por umbral y período |
| `partner_receipt.py` + `partner_receipt_email.py` | El recibo, su idempotencia, su FX y su correo |
| Consola `/usage` y `/billing`, admin `partners/[id]/*` | Las pantallas de operación, ya con sus cinco estados |
| `account.tsx` y su línea «gastado en otro sitio» | La forma de explicar la diferencia entre atribución y total |
| Estado `pausaPorTope` de la spec 003 | La degradación sin que nada desaparezca |
| ADR-022 §13-§15 | Webhook, log de eventos y claves de idempotencia, ya diseñados |

## Riesgos

| Riesgo | Qué lo contiene |
|---|---|
| El pool semanal se convierte en un tercer contador que discrepa | D3: el pool **es** el wallet; `budget_out` lee de ahí; `sum_partner_companion_tokens` baja a atribución. Test que compara las tres superficies en la misma petición |
| Un partner elige el cerebro caro y se come el margen | El peso por modelo (D3) acota el coste del pool sea cual sea la elección; la lista de modelos por plan (0098) es el techo de respaldo |
| El webhook dobla un ingreso | Idempotencia por `event.id` en tabla propia, como ADR-022 §13; y el libro es idempotente por su parte |
| Stripe cae y nadie puede trabajar | El tope es de la plataforma (D2): sin Stripe se sigue gastando pool y créditos; solo no se puede comprar más |
| El margen se calcula sobre tarifas inventadas | C1 y C2 van **antes** que el cobro. Una tarifa NULL se ve: `cost_usd` queda NULL y `complete` sale `false` |
| Alguien añade caducidad a los créditos comprados | Escrito en la spec como invariante, con test |
| Un impago archiva un teammate o cancela una tarea | D4, con test por cada estado de la escalera |
| Vender en la UE sin registro fiscal | Asesoría antes del primer cobro. Stripe Tax vigila umbrales pero no remite |
| ADR-022 queda contradicha en silencio | ADR nuevo que la supersede en sus §1-§5 y §8-§10, en el mismo PR que la spec |
| `partner_allocations` se queda sin semántica | Al pasar los clientes a gastar solo `purchased`, la asignación deja de ser porción del wallet y pasa a ser **tope mensual de gasto por cliente**. `allocatable_for` se calcula contra `purchased`; `replenish_allocations` sigue siendo mensual. Decidirlo, no descubrirlo |
