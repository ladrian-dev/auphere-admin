# Fase 0 — Las seis decisiones de diseño

**Spec**: [spec.md](./spec.md) · **Plan**: [plan.md](./plan.md) · **Fecha**: 2026-09-11

La spec no dejó ninguna marca `[NEEDS CLARIFICATION]` abierta, así que esta fase
no resuelve ambigüedades de producto: resuelve **cómo** se construye lo ya
decidido, y deja escrito el porqué para que la sesión que implemente no vuelva a
derivarlo.

---

## D1 · Dónde vive el factor por modelo

**Decisión**: columna nueva `model_profiles.quota_weight numeric(6,3) NULL`.

**Razón**: el criterio **R3.3** lo exige como dato y no como cálculo — *«un
partner no puede ver cambiar su contador porque un proveedor ajeno cambió un
precio»*. Y el sitio natural es la tabla que ya es el catálogo de plataforma:
sin `tenant_id`, sin RLS, igual para todos, y que ya existe precisamente para que
cambiar una tarifa sea un `UPDATE` y no un despliegue (migración `0072`).

`NULL` significa **«este modelo no se sirve»**, no «peso 1». Es el mismo idioma
que la tabla ya habla con las tarifas: `NULL` es una ausencia declarada, nunca un
cero disfrazado.

**Alternativa rechazada — derivar el peso de la tarifa en cada lectura.** Es
tentador porque no añade columna y nunca se desincroniza. Se rechaza porque
convierte el contador del partner en una función del precio de lista de un
tercero: el día que OpenAI baje Sol un 20 %, el pool de todos los partners
pasaría a rendir más sin que nadie lo decidiera, y al subirlo, menos. Un contador
que se mueve solo no se puede explicar en soporte.

**Alternativa rechazada — tabla aparte `model_quota_weights`.** Una tabla de dos
columnas con la misma clave que `model_profiles` y el mismo ciclo de vida. Una
fila puede quedarse sin su pareja; una columna no.

### Los factores, calculados

Normalizados al cerebro medio del catálogo cerrado (Terra = 1,000), sobre el
turno de referencia del §4.1 del research de la evaluación (30 K de prompt con
80 % de acierto de caché y 1,5 K de salida = 9 900 tokens de cuota):

| `model_id` | $/M cuota | `quota_weight` |
|---|---:|---:|
| `openai/gpt-5.6-luna` | 0,35 | **0,100** |
| `anthropic/claude-haiku-4-5` | 1,61 | **0,457** |
| `openai/gpt-5.6-terra` | 3,52 | **1,000** |
| `anthropic/claude-sonnet-4-6` | 4,82 | **1,371** |
| `openai/gpt-4o` | 6,06 | **1,724** |
| `openai/gpt-5.6-sol` | 6,42 | **1,828** |
| `openai/whisper-1` | — | **NULL** (ver D1b) |

**Comprobado**: con los pesos a tres decimales, agotar 1 M de pool cuesta entre
**3,5144 $ y 3,5154 $** en los seis modelos — 0,03 % de desviación. Es la
propiedad que **R3.2** exige, y `numeric(6,3)` basta para conseguirla.

Un hallazgo que conviene no perder: **`gpt-4o` pesa 1,724, casi como Sol, y su
precio de entrada es la mitad**. La diferencia está en la caché — cobra la
lectura a 1,25 $ (la mitad de la entrada) en vez de a una décima parte. El factor
no mide «modelo caro»: mide **coste real por token de cuota**, caché incluida.
Es exactamente lo que hace falta y lo que un peso puesto a ojo habría fallado.

### D1b · El factor solo aplica al camino de cuota de LLM

`openai/whisper-1` se queda con `quota_weight` en `NULL` y **eso no lo deja fuera
de servicio**. La transcripción se mide por `voice.minutes` y **no pasa por
`quota_tokens()`**, así que la negativa de **R3.4** no la alcanza.

Hay que escribirlo en el código, porque es justo el tipo de cosa que alguien
"arregla" seis meses después poniéndole un 1,0 a whisper y rompiendo la
invarianza sin que salte ningún test.

---

## D2 · Cómo llega el factor a `quota_tokens()` sin romper su pureza

**Decisión**: parámetro explícito. `quota_tokens(..., model_weight: Decimal)`,
resuelto por quien llama desde el catálogo ya cacheado.

**Razón**: `metering/quota.py` es hoy un módulo **puro** — sin base de datos, sin
red, sin reloj— y por eso su suite se ejecuta en milisegundos y no necesita
Postgres. Hacer que consulte el catálogo lo convertiría en un módulo con
dependencias y añadiría una consulta dentro del camino del turno.

**R3.1 se sigue cumpliendo**: el criterio dice que el factor se aplica *dentro de
la misma función* que ya aplica el de la lectura de caché, y eso es exactamente
lo que ocurre — la función recibe el número y lo aplica; no lo va a buscar.

**Coste por llamada: cero consultas.** `nexus_worker.metering.pricing.get_catalog()`
ya sirve el catálogo entero con TTL de 300 s, ya lo importa la API desde
`console/companion.py` para valorar el turno, y ya tiene `invalidate()`. Se le
añade `quota_weight` al `ModelPrice` y no hace falta nada más.

**Dónde se aplica el redondeo**: una sola vez, al final, con `ROUND_HALF_UP`,
igual que hoy. La función ya tiene `round_tokens_half_away` y el comentario que
explica por qué no se usa el `round()` de Python. El factor entra **antes** de
ese redondeo, no después, para no redondear dos veces.

---

## D3 · El período semanal y su ancla

**Decisión**: `next_period_end()` pasa a devolver el siguiente múltiplo de siete
días contado desde `partners.created_at`. **Sin columna de ancla nueva.**

**Razón**: `created_at` ya existe (viene de `TimestampMixin`), no cambia nunca, y
es exactamente lo que **R2.2** pide. Una columna de ancla sería un segundo estado
que hay que mantener sincronizado con el primero, y el modo de fallo —dos fechas
que discrepan— es el mismo que esta spec está eliminando en otro sitio.

**Lo que NO se toca, y es la mitad del ahorro**: `renew_included_if_expired()`.
Su docstring ya explica que dispara **por caducidad y no por calendario**, con la
razón: *«si el scheduler estuvo caído el día 1, renueva en cuanto vuelve, en vez
de esperar un mes»*. Eso hace que **R2.4 ya esté satisfecho antes de empezar**, y
que el cron horario existente sirva igual para semanas. El único cambio es qué
fecha se escribe en `included_expires_at`.

**Alternativa rechazada — lunes global.** Concentra toda la renovación de la
plataforma en un tick y le da una primera «semana» de dos días a quien se dé de
alta un viernes. Anthropic ancla por cuenta (*«un horario fijo asignado a tu
cuenta»*), y por esto.

### El tamaño del pool

Columna nueva `partners.weekly_pool_tokens bigint NOT NULL`, sembrada como
`round(companion_monthly_token_cap × 7 / 30.44)` — del orden de **115 000** donde
hoy hay 500 000 mensuales. **R2.6** pide preservar el volumen mensual; el
supuesto de la spec lo dice y la migración lo cumple.

Va en columna y no en constante porque **R2.9** exige poder cambiarlo sin
desplegar, y porque **R7.3** lo vuelve barato: el partner ve una barra, así que
ajustarlo cuando la medición del turno real diga algo distinto no es un anuncio.

### Qué pasa con `companion_monthly_token_cap`

**Deja de leerse. No se borra en esta spec.**

Borrar una columna y crear su sustituta en la misma migración deja un
`downgrade()` que no puede devolver los datos, y la regla del repositorio pide
`downgrade()` real probado contra un dump de producción. Se marca como deprecada
en el modelo, con el número de la migración que la eliminará en el comentario.

---

## D4 · Cómo se separan los bolsillos

**Decisión**: `debit_wallet(..., allow_included: bool = True)`. El consumidor de
canal pasa `allow_included=False`.

**Razón**: **R5.2** exige que el consumo de clientes finales no toque el incluido
en ningún caso. El reparto ya existe y está probado (`split_spend`, que gasta
incluido primero y comprado después); lo único que falta es poder decirle que el
primer cubo está cerrado para este llamante.

**Alternativa rechazada — una función nueva `debit_purchased_only()`.**
Duplicaría el bloqueo de fila, la comprobación de idempotencia por clave, la
escritura del asiento y el manejo de `IntegrityError`. Dos caminos de débito que
empiezan iguales acaban discrepando, que es la misma enfermedad que **R4** cura
en el camino de lectura. Un parámetro, un camino.

**El valor por defecto es `True`** a propósito: los dos llamantes que sí pueden
gastar incluido (Companion/teammates y ejecución local) no cambian ni una línea.
El que cambia es el que tiene que cambiar.

---

## D5 · De dónde saca `budget_out` sus números

**Decisión**: del libro.

| Campo | Antes | Después |
|---|---|---|
| `cap` | `partners.companion_monthly_token_cap` | `partners.weekly_pool_tokens` |
| `used` | `SUM(input+output)` sobre `companion.runs` del mes | `max(0, cap − included_remaining)` |
| `remaining` | `cap − used` | `included_remaining` (el dato, no el cálculo) |
| `resets_at` | primer día del mes siguiente | `included_expires_at` |
| `period` | `YYYY-MM` | semana ISO, `YYYY-Www` |

**Razón**: es **R4.1** literal. Y tiene una propiedad que la versión anterior no
podía tener: `remaining` deja de ser una resta y pasa a ser **la columna que la
plataforma consulta para dejar pasar o no**. El número que se enseña y el número
que decide son el mismo entero de la misma fila.

`sum_partner_companion_tokens` **no se borra**: baja a ser lo que **R4.2** dice,
la atribución por teammate. Sigue recorriendo membresías bajo RLS porque el
reparto sí es por persona; lo que desaparece es su papel de total.

**Consecuencia de contrato**, detallada en
[`contracts/budget-object.md`](./contracts/budget-object.md): `period` cambia de
formato. Lo consumen `/console/companion/budget`, `/console/teammates/usage`, la
aplicación de escritorio y `packages/companion-ui`. El contrato de la spec 003
(`specs/003-teammates-app-escritorio/contracts/teammates-api.md`) describe ese
objeto y hay que actualizarlo **en el mismo commit**, como pide el `CLAUDE.md`
del repositorio.

---

## D6 · Qué se quita de la pantalla, y qué no se quita de la respuesta

**Decisión**: el objeto de presupuesto **sigue llevando `used` y `cap`**; lo que
cambia es que **la interfaz del partner deja de pintarlos**.

**Razón**: **R7.2** dice que el panel de operador necesita las cifras absolutas
para diagnosticar y conciliar, y **R7.1** dice que el partner ve proporción y
fecha. Si se quitaran del objeto, el panel de operador necesitaría un segundo
endpoint con los mismos datos — es decir, exactamente el segundo camino de
lectura que **R4** está eliminando.

Así que el recorte es de **presentación**, y se escribe donde se decide la
presentación:

- `apps/desktop/src/app/routes/account.tsx` — la línea `account.usage.line`
  («X de Y tokens») pasa a porcentaje y fecha. **El `role="meter"` y sus tres
  valores se quedan**: ahí siguen estando `aria-valuenow` y `aria-valuemax`,
  porque **R7.4** exige que un lector de pantalla reciba lo mismo que quien ve la
  barra, y una barra sin valores no dice nada.
- `apps/console/src/app/(console)/usage/page.tsx` — mismo criterio para el pool.
  **El saldo comprado sigue en unidades** (R7.6): eso es dinero que el partner
  pagó.

**Esto no viola §V.** «La pantalla no miente» no obliga a enseñar cada entero que
la plataforma conoce; obliga a que lo que se enseña sea cierto y a que las
ausencias sean deliberadas. Una barra con su fecha de reposición es cierta, y el
dato exacto sigue disponible para quien tiene que cuadrar una factura.

---

## Lo que esta fase NO tuvo que investigar

Se anota porque ahorra tiempo a quien lea el plan buscando lo que falta:

- **Cuánto cuesta cada modelo.** Verificado y fechado en el §3.2 del research de
  la evaluación, consultado el 2026-09-11.
- **Si el cron sirve para semanas.** Sirve: dispara por caducidad.
- **Si el débito es idempotente.** Lo es, por `usage_ledger.idempotency_key`
  UNIQUE, y con reparto entre cubos sufijando la clave.
- **Si hay dependencias nuevas.** No hay ninguna.
- **Cuánto vale el turno real.** Sigue siendo un supuesto, y **no bloquea esta
  spec**: aquí no se fija ningún precio ni ningún tamaño de plan. Bloquea las
  cifras de la Spec B.
