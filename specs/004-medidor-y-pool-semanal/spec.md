# Especificación: el medidor dice la verdad

**Rama**: `004-medidor-y-pool-semanal` · **Creada**: 2026-09-11 · **Estado**: Borrador

**Entrada**: traspaso de
[`.specify/assessments/membresias-y-consumo-stripe/decision.md`](../../.specify/assessments/membresias-y-consumo-stripe/decision.md)
— veredicto **go** del 2026-09-11, **partido en dos specs**. Ésta es la **Spec A**:
sin Stripe, sin precio de venta y sin producto nuevo. Con las cinco decisiones
que Luis cerró ese día (tres niveles de catálogo · cifras provisionales · suelo
gratuito para el Companion · peso por modelo dentro de la unidad · la semana
ancla en el día de alta del partner), recogidas en
[[nexus/decisions/ADR-037-membresias-y-consumo-de-la-app]].

## Encabezado Auphere *(obligatorio)*

| Campo | Valor |
|---|---|
| **Superficie de confianza** | **`0`** — API de la consola. **No abre ninguna nueva.** Todo ocurre dentro del libro que ya existe y de los endpoints que ya existen |
| **Garantías de aislamiento tocadas** | **1. Postgres RLS** — se toca el camino de lectura del presupuesto: hoy `budget_out` suma `companion.runs` recorriendo membresía a membresía bajo RLS por principal; pasa a leer `partner_wallets`, que lleva RLS FORCE por `partner_id`. Es **menos** superficie, no más, y aun así lleva su test · **6. Log + trace tagging** — cada renovación semanal y cada débito siguen dejando asiento en `usage_ledger` |
| **Nota de KB que la justifica** | `[[nexus/decisions/ADR-037-membresias-y-consumo-de-la-app]]` (D1, D4 y D5) · `[[nexus/PLAN-PENDIENTE-CORTE-2026-09-08]]` ítems **C1**, **C2** y **D5** · `[[teammates/10-decisiones]]` decisión 14 |
| **Qué se mide** | **Modelo, y nada más.** No entra reloj de máquina, no entra herramienta de pago. La unidad sigue siendo `quota_tokens()`; lo que cambia es que lleva un peso más dentro |

> **Por qué no abre superficie (§II):** no hay llamante nuevo, no hay credencial
> nueva y no hay camino nuevo al modelo. Esta spec **quita** un camino de lectura
> (la suma sobre `companion.runs` deja de ser el total) y le cambia el período a
> una columna que ya caduca. La única adición es un factor dentro de una función
> pura que ya tiene otro factor.

> **Esta spec cierra una deuda declarada, no inventa trabajo.** `metering/wallet.py`
> llama **D5** a lo que el Requisito 4 arregla, con estas palabras: *«`monthly_cap`
> sale de `partners.companion_monthly_token_cap`, que es el mismo número que gasta
> el Companion. Separar los dos bolsillos es D5.»*

## El defecto que esta spec corrige, en una imagen

Hoy, en producción, un partner puede ver esto **a la vez**:

| Pantalla | Dice |
|---|---|
| `/console/companion/budget` · `/console/teammates/usage` · Cuenta en la app | «Has usado el 20 % de tu tope» |
| Cualquier intento de turno del Companion | `409 wallet_empty` |

No es un fallo de pintura: son **dos contadores distintos sobre el mismo gasto**.
El de arriba suma filas de `companion.runs` —solo Companion y teammates—; el
libro suma además los turnos de canal de los clientes finales y las ejecuciones
en la máquina. Y el **mismo número** (`partners.companion_monthly_token_cap`)
dimensiona los dos.

La constitución §V dice que la pantalla no miente. Hoy miente, y se puede medir.

## Escenarios de usuario y pruebas *(obligatorio)*

### Historia 1 — Auphere puede ver su margen (Prioridad: P1)

Hoy el Companion —y por tanto cada teammate— corre sobre `openai/gpt-5.6-sol`, y
esa fila entró en la migración `0095` con las cinco columnas de tarifa a `NULL`.
Cada turno se mide y **no se valora**: `_turn_cost_usd` devuelve `None` y
`usage_records.cost_usd` se queda vacío. No es que el margen sea malo; es que no
existe el dato.

**Por qué esta prioridad**: es lo más barato de la lista y desbloquea todo lo
demás. Sin esto, ninguna cifra de margen es comprobable, y decidir precios sobre
un coste que la plataforma no sabe calcular es decidir a ciegas.

**Prueba independiente**: se despliega sola. Se comprueba pidiendo el coste de un
mes con tráfico y viendo que no quedan filas sin valorar para los modelos que el
producto vende.

**Escenarios de aceptación**:

1. **Dado** un mes con turnos de Companion ya registrados y sin valorar,
   **cuando** se aplica la carga de tarifas, **entonces** esas filas quedan
   valoradas y el informe de coste responde `complete = true`.
2. **Dado** un turno nuevo sobre cualquiera de los tres modelos del catálogo
   cerrado, **cuando** termina, **entonces** su coste en dólares es un número y
   no una ausencia.
3. **Dado** un modelo **sin** tarifa cargada, **cuando** se mide su consumo,
   **entonces** el coste sigue siendo una ausencia declarada y el informe lo
   cuenta aparte — nunca un cero.

---

### Historia 2 — Una sola cifra, y es verdad (Prioridad: P1)

El partner mira su consumo en tres sitios: la consola, el panel que Auphere opera
y la pantalla Cuenta de la aplicación. Los tres tienen que decir lo mismo, del
mismo período, en la misma petición.

**Por qué esta prioridad**: es el defecto que rompe la confianza en todo lo
demás. Un medidor que se contradice consigo mismo no puede sostener un cobro por
consumo, y la decisión 14 de la KB lo exige explícitamente.

**Prueba independiente**: se prueba sin tocar precios ni períodos — basta gastar
por dos caminos distintos (un turno de Companion y un turno de canal de un
cliente) y comprobar que el total sube por los dos y que las tres superficies lo
ven igual.

**Escenarios de aceptación**:

1. **Dado** un partner cuyo cliente final ha consumido hasta vaciar el libro,
   **cuando** el partner abre su consumo, **entonces** ve el pool agotado —y no
   un tope al 20 %—, y el motivo del bloqueo coincide con lo que la pantalla dice.
2. **Dado** el mismo partner y el mismo instante, **cuando** se piden las tres
   lecturas, **entonces** las tres devuelven el mismo total.
3. **Dado** un gasto que no procede de ningún teammate, **cuando** se mira el
   reparto por teammate, **entonces** la diferencia entre el total y lo atribuido
   se nombra en pantalla en vez de desaparecer.

---

### Historia 3 — El pool se reinicia cada semana, y la semana es la mía (Prioridad: P2)

El consumo incluido pasa de mensual a semanal, y cada partner renueva en su
propio día —el de su alta—, no en un lunes común.

**Por qué esta prioridad**: es lo que acota el peor caso. Una ventana semanal
convierte un exceso en algo que se repite un número conocido de veces al año, en
vez de en un mes perdido. Va después de la Historia 2 porque cambiar el período
de un contador que ya se contradice consigo mismo es apilar un problema sobre otro.

**Prueba independiente**: se prueba con el reloj: gastar, adelantar hasta pasado
el límite semanal del partner, y ver que el pool vuelve solo sin que nadie corra
nada a mano.

**Escenarios de aceptación**:

1. **Dado** un partner que agotó su pool, **cuando** pasa su límite semanal,
   **entonces** el pool vuelve a estar lleno sin intervención.
2. **Dado** un partner que gastó la mitad, **cuando** pasa su límite semanal,
   **entonces** el pool vuelve a su tamaño completo y **lo no gastado no se suma**.
3. **Dado** que el proceso de renovación estuvo caído tres días, **cuando**
   vuelve, **entonces** renueva de inmediato a quien le tocaba, y no espera otra
   semana.
4. **Dado** un partner dado de alta un viernes, **cuando** pasa su primera
   semana, **entonces** ha tenido siete días completos, no los que faltaban para
   el domingo.

---

### Historia 4 — El pool cuesta lo mismo con cualquier cerebro (Prioridad: P2)

Un token de cuota no cuesta lo mismo en un modelo que en otro: entre el más
barato y el más caro del catálogo que vende el producto hay **dieciocho veces**
de diferencia. Con el pool plano, el peor caso de cada plan lo decide el partner
al elegir cerebro, no nosotros al ponerle precio.

**Por qué esta prioridad**: sin esto no se puede publicar un precio defendible.
Con las cifras provisionales del concepto, el plan alto agotado entero en el
cerebro caro cuesta **166,90 $ contra un precio de 150 $**.

**Prueba independiente**: se prueba sin cobrar nada — agotar un pool del mismo
tamaño con cada uno de los tres cerebros y comprobar que el coste en dólares
coincide.

**Escenarios de aceptación**:

1. **Dado** un pool de tamaño fijo, **cuando** se agota enteramente con el
   cerebro barato, con el medio y con el caro, **entonces** el coste real en
   dólares es el mismo en los tres casos.
2. **Dado** el mismo trabajo hecho con el cerebro caro y con el barato,
   **cuando** se mira el contador, **entonces** el caro ha consumido más pool, y
   la pantalla ya publica esa diferencia como etiqueta relativa.
3. **Dado** un turno cualquiera, **cuando** se compara lo que descuenta del pool
   con lo que dice la atribución por teammate, **entonces** coinciden — el peso
   se aplica una sola vez y en un solo sitio.

---

### Casos límite

- **Partner sin libro.** Hoy `read_wallet` devuelve ausencia y el turno se
  deniega. Sigue igual: fail-closed, y la pantalla lo dice.
- **Partner recién creado, antes de su primera renovación.** Nace con pool y con
  su límite semanal puesto; no hay ventana en la que exista sin saldo por no
  haber pasado todavía un cron.
- **El proceso de renovación lleva días caído.** Renueva por caducidad, no por
  calendario: al volver, repone a todos los vencidos en un solo paso.
- **Modelo sin tarifa cargada.** El consumo se cuenta y no se valora. Para el
  **peso** hay que decidir qué hacer: ver Requisito 3.4.
- **Cambio de peso a mitad de semana.** Lo ya debitado no se recalcula: un
  asiento es un hecho contable. El peso nuevo aplica a lo que venga.
- **Tenant sin partner** (cliente directo, pruebas antiguas). El libro no aplica
  y el turno pasa, como hoy.
- **Capacidad no disponible** (§V): cuando el pool está agotado y no hay crédito,
  **no** se pinta un botón apagado ni una pantalla que explique lo que no se
  tiene. Se usa el estado que ya existe —`en pausa por tope`— con el motivo y el
  sitio donde se arregla.

## Requisitos *(obligatorio)*

### Requisito 1 — Toda tarifa que el producto vende está cargada y fechada

**Historia de usuario:** Como Auphere, quiero que cada turno que cobramos tenga
un coste calculable, para poder saber si ganamos dinero antes de ponerle precio.

#### Criterios de aceptación

1. El sistema DEBE tener tarifa de entrada, de entrada cacheada y de salida para
   los tres modelos del catálogo cerrado que el producto vende.
2. WHERE un proveedor no cobra la escritura de caché, EL sistema DEBE dejar esa
   tarifa ausente y NO DEBE ponerla a cero — un cero diría «medido y gratis», que
   no es lo mismo que «no se cobra».
3. WHEN se cargan tarifas nuevas THEN el sistema DEBE revalorar el consumo ya
   medido que quedó sin valorar, y NO DEBE tocar el que ya tenía coste.
4. IF un consumo procede de un modelo sin tarifa THEN el sistema DEBE dejar su
   coste ausente y DEBE contarlo aparte, de modo que un total parcial se distinga
   de un total completo.
5. El sistema DEBE registrar, junto a cada tarifa, **de dónde salió y en qué
   fecha se consultó**, para que revisarla más adelante no exija volver a
   investigar de cero.
6. El sistema DEBE tener precio unitario para los medidores que hoy no lo tienen,
   o DEBE declarar explícitamente que no se valoran — pero NO DEBE dejar filas
   que desaparezcan en silencio de un total.

### Requisito 2 — El consumo incluido es semanal y la semana es la del partner

**Historia de usuario:** Como partner, quiero que mi consumo incluido se reponga
cada semana en mi propio día, para saber cuándo vuelvo a tener y no depender de
un calendario ajeno.

#### Criterios de aceptación

1. El sistema DEBE reponer el consumo incluido en ciclos de **siete días**.
2. El ciclo de cada partner DEBE anclarse en **su fecha de alta**, y NO DEBE
   coincidir forzosamente con el de otros partners.
3. WHEN el ciclo de un partner vence THEN el sistema DEBE reponer su consumo al
   tamaño completo, y lo no gastado NO DEBE acumularse.
4. WHILE el proceso de renovación esté detenido, el sistema DEBE reponer en
   cuanto vuelva a estar disponible, sin esperar al siguiente ciclo.
5. El consumo **comprado** NO DEBE caducar nunca, ni al renovar, ni al cambiar de
   período, ni al vaciarse el incluido.
6. WHEN se pasa del período mensual al semanal THEN el volumen mensual efectivo
   de cada partner NO DEBE cambiar: esta spec cambia el ritmo, no la cantidad.
7. WHEN un partner es dado de alta THEN el sistema DEBE dejarlo con consumo
   disponible y con su ciclo fijado en el mismo acto, y NO DEBE existir un
   intervalo en el que el partner exista sin saldo por no haber pasado todavía un
   proceso de fondo.
8. El sistema DEBE decir en pantalla **cuándo vuelve** el consumo, con fecha.
9. WHEN se cambia el tamaño del pool de un partner THEN el cambio NO DEBE exigir
   despliegue ni migración: es un dato, como ya lo es la tarifa de un modelo.

### Requisito 3 — La unidad de cuota pesa según el cerebro

**Historia de usuario:** Como Auphere, quiero que agotar un pool cueste lo mismo
sea cual sea el modelo elegido, para que el peor caso de un plan sea un número
que conozco de antemano y no una elección del cliente.

#### Criterios de aceptación

1. El sistema DEBE aplicar un factor por modelo al calcular cuánto consume una
   llamada, dentro de **la misma función** que ya aplica el factor de la lectura
   de caché, y NO DEBE aplicarlo en ningún otro sitio.
2. WHEN un pool de tamaño fijo se agota enteramente THEN el coste real en dólares
   DEBE ser el mismo con cualquiera de los modelos del catálogo, dentro del
   margen de redondeo.
3. Los factores DEBEN estar **declarados como dato**, y NO DEBEN derivarse
   automáticamente de la tarifa vigente: un partner no puede ver cambiar su
   contador porque un proveedor ajeno cambió un precio.
4. IF un modelo no tiene factor declarado THEN el sistema DEBE **negarse a
   servirlo**, con un error legible que nombre el modelo, y NO DEBE atenderlo
   con un factor supuesto. Un modelo sin factor es un error de configuración
   nuestro: servirlo con factor neutro nos come el margen en silencio, y
   servirlo al factor del más caro le cobra de más al partner por un olvido que
   no es suyo. Es además el comportamiento que el sistema **ya tiene** con el
   catálogo de modelos, así que no introduce un modo de fallo nuevo.
5. WHEN se cambia un factor THEN el sistema NO DEBE recalcular consumo ya
   asentado: un asiento es un hecho contable y no cambia de valor a posteriori.
6. El sistema DEBE seguir publicando, para cada cerebro ofrecido, una indicación
   **relativa** de lo que cuesta dentro de la oferta que esa persona ve, y NO
   DEBE poner un importe en dólares en la fila de un turno.

### Requisito 4 — Un solo medidor: la cifra sale del libro

**Historia de usuario:** Como partner, quiero que el número que veo sea el mismo
que la plataforma usa para dejarme trabajar, para no descubrir por un error que
lo que la pantalla decía no era cierto.

#### Criterios de aceptación

1. El consumo mostrado DEBE derivarse del **libro del partner**, y NO DEBE
   derivarse de una suma sobre el registro de ejecuciones.
2. La suma sobre el registro de ejecuciones DEBE usarse **solo** para repartir el
   gasto entre teammates, y NO DEBE presentarse nunca como el total.
3. WHEN se consultan la consola, el panel de operador y la pantalla Cuenta en el
   mismo instante y para el mismo partner THEN las tres DEBEN derivar del mismo
   dato, del mismo período y del mismo libro. Lo que cada una **pinta** puede
   diferir (Requisito 7); lo que cada una **lee**, no.
4. IF el total del partner supera lo atribuido a sus teammates THEN la pantalla
   DEBE nombrar la diferencia, y NO DEBE ocultarla ni repartirla entre los
   teammates que sí aparecen.
5. IF el libro no se puede leer THEN el sistema DEBE seguir siendo fail-closed:
   saldo cero y sin llamada al modelo.
6. El sistema NO DEBE permitir que exista un segundo tope, de otro alcance, que
   se compare contra la misma cifra. Al terminar esta spec DEBE haber **un solo
   número** que decida si un turno pasa.

### Requisito 5 — Dos bolsillos, y cada uno lo gasta quien debe

**Historia de usuario:** Como partner, quiero que lo que consumen los agentes de
mis clientes no se coma el consumo de mi propia aplicación, para no quedarme sin
poder trabajar porque un cliente tuvo un día movido.

#### Criterios de aceptación

1. El consumo de los **teammates y del Companion** DEBE salir primero del
   incluido y, agotado éste, del comprado.
2. El consumo de los **agentes de clientes finales** DEBE salir **solo** del
   comprado, y NO DEBE tocar el incluido en ningún caso.
3. WHEN el incluido se agota a mitad de ciclo THEN el trabajo de los teammates
   DEBE continuar contra el comprado **sin intervención de nadie**.
4. IF no queda ni incluido ni comprado THEN el sistema DEBE detener el trabajo
   nuevo con el estado que ya existe para eso, DEBE mantener vivas las
   confirmaciones pendientes, y NO DEBE cancelar ni archivar nada.
5. La pantalla DEBE decir **de qué bolsillo** está saliendo el consumo en curso.
6. Cada débito DEBE seguir siendo idempotente: el mismo turno reprocesado NO DEBE
   descontar dos veces.

### Requisito 6 — El tope por cliente cambia de significado, y se dice

**Historia de usuario:** Como partner, quiero seguir pudiendo limitar lo que
gasta cada cliente, para que uno solo no se lleve todo mi saldo comprado.

#### Criterios de aceptación

1. El tope por cliente DEBE pasar a acotar el consumo **comprado**, y su
   disponibilidad DEBE calcularse contra ese cubo y no contra el incluido.
2. El tope por cliente DEBE seguir reponiéndose **mensualmente**, y NO DEBE
   seguir el ciclo semanal del incluido: es un límite de gasto que fija el
   partner, no una porción de lo incluido.
3. WHEN un cliente agota su tope THEN DEBE dejar de consumir **solo ese cliente**,
   y los demás DEBEN seguir atendiendo.
4. El sistema DEBE seguir avisando antes de que un cliente deje de atender, con
   los umbrales que ya existen.
5. La suma de topes NO DEBE poder superar el saldo sobre el que se calculan.

### Requisito 7 — El partner ve una barra y una fecha, no una cifra de tokens

**Historia de usuario:** Como partner, quiero ver cuánto me queda y cuándo
vuelve, sin tener que entender qué es un token, para saber si puedo seguir
trabajando hoy.

#### Criterios de aceptación

1. La pantalla del partner DEBE presentar el consumo incluido como **proporción
   consumida** y **fecha de reposición**, y **NO DEBE presentar en ningún sitio
   de esa pantalla** la cifra absoluta del pool ni la del gasto contra él — ni
   como dato principal ni como detalle secundario. La prohibición alcanza solo
   al **pool incluido**: el saldo comprado (7.6), la ventana de contexto y el
   detalle del turno no entran.
2. El panel de operador DEBE seguir enseñando **las cifras absolutas**: Auphere
   necesita el número para diagnosticar, conciliar y decidir precios.
3. WHEN Auphere cambia el tamaño del pool de un partner THEN el partner NO DEBE
   percibirlo como un recorte o un regalo de una cantidad concreta; lo que ve es
   su proporción y su fecha.
4. La indicación DEBE ser accesible como medidor con sus tres valores —mínimo,
   actual y máximo— y con un texto alternativo que diga lo mismo, para que quien
   navegue con lector de pantalla reciba la misma información que quien ve la
   barra.
5. WHEN el consumo incluido se agota THEN la pantalla DEBE decirlo con el estado
   correspondiente y DEBE nombrar de qué bolsillo está saliendo el trabajo a
   partir de ese momento (Requisito 5.5).
6. IF el partner tiene saldo **comprado** THEN el sistema DEBE poder mostrar su
   cantidad, porque eso es dinero que el partner pagó y tiene derecho a
   verificar. La abstracción de la barra aplica al pool incluido, **no** al saldo
   comprado.

> **Por qué.** Es lo que hacen los seis referentes del §2 de la evaluación:
> ninguno enseña cifras crudas de consumo al usuario final; enseñan una barra y
> un reinicio. Y tiene una consecuencia operativa concreta: permite ajustar el
> tamaño del pool según lo que la medición vaya diciendo, sin que cada ajuste sea
> un anuncio. La contrapartida —y por eso está el criterio 6— es que lo comprado
> sí se mide en unidades, porque ahí el partner no está consumiendo una
> asignación: está gastando algo que pagó.

### Entidades clave

- **Libro del partner** — el saldo de un partner, con dos cubos: el **incluido**
  (caduca al cerrar su ciclo semanal) y el **comprado** (no caduca nunca).
  Pertenece a un **partner**, no a un tenant; la RLS lo alcanza por
  `partner_id`. Un cliente final no tiene forma de nombrarlo.
- **Asiento de consumo** — el registro de cada débito, con su clave de
  idempotencia, el cubo del que salió y a qué cliente se imputó. Hecho contable:
  no se reescribe.
- **Tope por cliente** — cuánto del saldo comprado puede consumir un cliente
  final del partner. Pertenece al par (partner, tenant).
- **Perfil de modelo** — qué modelos existen, qué cuestan y **cuánto pesan** en la
  unidad de cuota. Catálogo de plataforma: igual para todos, sin RLS.
- **Ciclo del partner** — cuándo vence y se repone el incluido. Ancla en la fecha
  de alta del partner.

## Criterios de éxito *(obligatorio)*

- **CE-001**: Consola, panel de operador y pantalla Cuenta devuelven **el mismo
  total** del mismo período para el mismo partner. Es la comprobación que hoy
  falla.
- **CE-002**: Agotar un pool del mismo tamaño con el cerebro barato, el medio y
  el caro cuesta **lo mismo** en dólares, dentro del redondeo.
- **CE-003**: Un mes con tráfico real no deja **ninguna** unidad de consumo sin
  valorar para los modelos que el producto vende.
- **CE-004**: Un partner que agota su consumo incluido **sigue trabajando** con
  su saldo comprado sin que nadie intervenga, y sabe de qué bolsillo sale.
- **CE-005**: Un partner sin consumo de ningún tipo ve su trabajo **en pausa con
  motivo**, conserva sus confirmaciones pendientes y no pierde ninguna tarea.
- **CE-006**: Tras siete días desde su alta, el consumo incluido de un partner
  vuelve a estar completo **sin que nadie ejecute nada a mano**.
- **CE-007**: El volumen mensual que cada partner podía consumir **no cambia** al
  pasar de mes a semana.
- **CE-008**: No queda en el sistema **ningún segundo tope** de alcance distinto
  comparándose contra la misma cifra.
- **CE-009**: El tamaño del pool de un partner se puede cambiar **sin desplegar
  nada**, y el partner no ve ese cambio como una cantidad que sube o baja.
- **CE-010**: Un modelo sin factor declarado **no atiende ni un turno**, y el
  error dice cuál es y qué le falta.

## Fuera de alcance

- **Stripe, cobro y webhooks** — es la Spec B, y depende de ésta.
- **Las tres membresías, sus precios y sus topes de teammates y de personas** —
  Spec B. Aquí el tamaño del pool sigue saliendo de donde sale hoy.
- **El suelo gratuito para partners sin membresía** — no hay membresías todavía,
  así que no hay «sin membresía». Entra con la Spec B.
- **La escalera de impago** — no se puede deber lo que no se cobra.
- **Las dos líneas nuevas del recibo mensual** — Spec B.
- **El reloj de máquina** — no existe la VM. La unidad queda preparada para
  admitirlo sin ser otro contador, pero no se mide aquí.
- **`partners.max_clients`** — se mantiene independiente del plan, por decisión
  del ADR-037.
- **Medir el turno real en producción** — es una tarea de diagnóstico aparte y
  solo bloquea las **cifras** de la Spec B, no esta spec.

## Supuestos

- **El volumen mensual se preserva.** Al pasar de mensual a semanal, el pool de
  cada partner se siembra de modo que el total del mes equivalga al de hoy —del
  orden de 115 000 semanales donde hoy hay 500 000 mensuales—. Esta spec cambia
  el ritmo de reposición, no la generosidad del producto: cambiar ambos a la vez
  haría imposible saber cuál de los dos causó lo que se observe después. **El
  número exacto deja de ser sensible** precisamente por el Requisito 7: el
  partner ve una barra, así que ajustarlo cuando la medición diga algo distinto
  no es un anuncio, es un dato.
- **El ancla es la fecha de alta del partner**, que ya se registra. No hace falta
  pedir ni inventar una fecha nueva.
- **Los factores por modelo se normalizan al cerebro medio del catálogo**, de
  forma que el número que el partner ve siga pareciéndose a «tokens» para el uso
  corriente.
- **Las tarifas de los tres modelos del catálogo cerrado están verificadas** con
  fuente y fecha en el §3.2 de
  [`research.md`](../../.specify/assessments/membresias-y-consumo-stripe/research.md),
  consultadas el 2026-09-11. La tarifa de transcripción por minuto **no** se
  volvió a verificar ese día y se deja como está.
- **El proceso de renovación existente sirve sin cambios**, porque dispara por
  caducidad y no por calendario. Esta spec le cambia el cálculo del siguiente
  vencimiento, no su disparador ni su frecuencia.
- **El estado de pausa por tope ya existe** y se reutiliza con otro motivo, en
  vez de inventar uno nuevo.
