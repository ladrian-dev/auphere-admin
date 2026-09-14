# Especificación: la cuota cobra por carril

**Rama**: `007-pesos-de-cuota-por-carril` · **Creada**: 2026-09-14 · **Estado**: Borrador

**Entrada**: descripción del usuario — sustituir el `quota_weight` único por
modelo por **tres pesos, uno por carril** (entrada, lectura de caché y salida),
derivados del precio de su propio carril, para que el multiplicador que
cobramos sobre el coste de proveedor sea uniforme y **nunca caiga por debajo de
1,50x en ningún carril de ningún modelo del catálogo**.

Esta spec cierra lo que [[nexus/decisions/ADR-037-membresias-y-consumo-de-la-app]]
dejó explícitamente abierto — *«las cifras finales de precio y de pool las cierra
una medición del turno real, y hasta entonces son provisionales»* — y **corrige
dos afirmaciones de ese ADR que la medición demuestra falsas** (§«El defecto»).

## Encabezado Auphere *(obligatorio)*

| Campo | Valor |
|---|---|
| **Superficie de confianza** | **`0`** — API de la consola. **No abre ninguna nueva.** No hay llamante nuevo, ni credencial nueva, ni camino nuevo al modelo: cambia el número de factores dentro de una función pura que ya tiene dos |
| **Garantías de aislamiento tocadas** | **1. Postgres RLS** — `model_profiles` sigue siendo catálogo de plataforma sin `tenant_id`; la spec **añade columnas a esa tabla** y por tanto vuelve a pasar por la puerta que `tests/isolation/test_pool_not_exposed_to_tenant.py` vigila: ningún nombre del plano económico puede aparecer en el esquema de las rutas de cliente final. Esa lista `FORBIDDEN` cita hoy `quota_weight` por su nombre y **queda incompleta en cuanto existan los tres pesos** · **6. Log + trace tagging** — cada débito sigue dejando asiento en `usage_ledger` con la cifra nueva |
| **Nota de KB que la justifica** | `[[nexus/decisions/ADR-037-membresias-y-consumo-de-la-app]]` — «Qué NO decide esta ADR», primer punto, y las consecuencias que esta spec refuta |
| **Qué se mide** | **Modelo, y nada más.** La unidad sigue siendo la que devuelve el cálculo de cuota; lo que cambia es que el peso deja de ser uno y pasa a ser el del carril. No entra reloj de máquina ni herramienta de pago |

> **Por qué no abre superficie (§II):** no hay superficie que abrir. Todo ocurre
> dentro del libro, del catálogo y de los dos puntos de cálculo que ya existen.
> La única adición al mundo son dos columnas en una tabla de plataforma.

## Clarifications

### Session 2026-09-14

- Q: ¿Qué multiplicador único sobre el coste de proveedor fija la spec? → A: **2,2x**, margen 54,5 %. Enmienda a la baja el 65 % que el ADR-037 dio por decidido, para que la corrección no llegue a los tres clientes con tráfico como un +28,4 % de factura.
- Q: ¿Qué pasa con los créditos comprados y las bolsas incluidas en curso el día del despliegue? → A: **sólo consumo nuevo**. Nada se revalora ni se recalcula: las unidades compradas siguen siendo las mismas y desde el despliegue rinden el trabajo de la tarifa nueva.
- Q: La columna del peso admite hoy tres decimales y el carril de caché del modelo más barato se queda en 2,00x. ¿Qué se hace? → A: **ampliar la escala**, para que el carril más barato dé el objetivo exacto y no sólo pase el suelo.

## El defecto que esta spec corrige

Un solo peso por modelo, aplicado **al total** de la llamada, no puede
representar tres precios distintos. Los proveedores cobran la salida entre 5x y
6x la entrada, y la lectura de caché a una décima parte en Anthropic y en la
familia GPT-5.6 pero a **la mitad** en `gpt-4o`. Con un factor único, el
multiplicador que cobramos sobre el coste sale distinto en cada carril, y en el
carril caro sale **por debajo de uno**.

Vendemos a 10 USD por millón de unidades de cuota. Multiplicadores de hoy
(cobrado ÷ coste de proveedor), con el suelo exigido de **1,50x**:

| modelo | peso | entrada | caché | salida |
|---|---|---|---|---|
| `openai/gpt-5.6-sol` | 1,828 | 4,57x | 4,57x | **0,91x** |
| `anthropic/claude-sonnet-4-6` | 1,371 | 4,57x | 4,57x | **0,91x** |
| `openai/gpt-4o` | 1,724 | 6,90x | **1,38x** | 1,72x |
| `openai/gpt-5.6-terra` | 1,000 | 5,00x | 5,00x | **0,83x** |
| `anthropic/claude-haiku-4-5` | 0,457 | 4,57x | 4,57x | **0,91x** |
| `openai/gpt-5.6-luna` | 0,100 | 5,00x | 5,00x | **0,83x** |

**Los seis modelos del catálogo incumplen la regla.** Cinco venden la salida por
debajo de coste; el sexto no pierde dinero pero se queda en 1,38x en caché, bajo
el suelo. No hay ninguno que cumpla.

### Dónde duele, y por qué duele justo ahí

La bolsa incluida paga el trabajo de teammates y del Companion — el consumo de
cliente final sale de los créditos comprados. **El trabajo de teammate es pesado
en salida**, que es exactamente el carril que se vende por debajo de coste. Con
un turno de 5 K de prompt, 4 K de caché y 3 K de salida sobre
`claude-sonnet-4-6`, un partner que agote su bolsa todas las semanas del mes
cuesta:

| plan | precio | nos cuesta | margen |
|---|---|---|---|
| Pro | 20 $ | 17,73 $ | **11 %** |
| Team | 60 $ | 70,94 $ | **−18 %** |
| Business | 150 $ | 212,81 $ | **−42 %** |

Y a Business se le vende «12 teammates» para que lo haga.

### Las dos afirmaciones del ADR-037 que la medición refuta

1. **«Ningún nivel es deficitario aunque se agote entero todas las semanas del
   mes — 62 % de margen en el de entrada, 39 % en el alto.»** Falso con el turno
   de teammate real: 11 % y −42 %. El cálculo del ADR usó la mezcla de referencia
   (30 K de prompt, 80 % de acierto de caché, 1,5 K de salida), que no es la
   mezcla del trabajo que la bolsa paga.
2. **«Con el peso, agotar el pool cuesta lo mismo sea cual sea el cerebro.»**
   Cierto **sólo en el punto de calibración**, y esa es la causa raíz de todo lo
   demás. Coste real de agotar un millón de unidades, desviación entre los seis
   modelos del catálogo:

   | mezcla | desviación hoy |
   |---|---|
   | referencia (30 K / 24 K / 1,5 K) | 0,03 % |
   | teammate (5 K / 4 K / 3 K) | **78,38 %** |
   | salida pura (0 / 0 / 1 K) | **106,88 %** |

   La propiedad que el código documenta como garantía es una coincidencia
   calibrada en un punto. Fuera de él, el peor caso de un plan vuelve a decidirlo
   el partner al elegir modelo y mezcla — que es exactamente lo que la 004 quiso
   impedir.

### Y una tercera cosa, que no es un error del ADR sino de lo que se implementó

Los márgenes que el ADR-037 afirma —62 % en el nivel de entrada, 39 % en el
alto— son **exactamente** los que salen con un multiplicador de 2,857x, es decir
con el 65 % de margen objetivo que `billing/pricing.py` declara en su propio
comentario. Los pesos que la migración `0115` cargó no producen ese
multiplicador en ningún carril. **El 65 % no estaba sin decidir: estaba decidido
y sin implementar.**

Esta spec no lo implementa tampoco, y lo dice con todas las letras: fija **2,2x**
(54,5 %) porque llevar el multiplicador a 2,857x subiría un 28,4 % la factura del
consumo de clientes finales, y hay tres clientes reales con tráfico. Es una
enmienda deliberada a la baja del ADR-037, no un olvido — y por eso R7 exige que
el ADR se corrija en el mismo commit en vez de quedar diciendo otra cosa.

## Escenarios de usuario y pruebas *(obligatorio)*

### Historia 1 — Ningún carril se vende por debajo del suelo (Prioridad: P1)

Auphere fija un multiplicador único sobre el coste de proveedor y lo cobra igual
en los tres carriles de todos los modelos. Un partner que agote su bolsa deja de
costar más de lo que paga, y deja de hacerlo **sea cual sea la mezcla** de
entrada, caché y salida que produzca su trabajo.

**Por qué esta prioridad**: es dinero saliendo hoy, todos los días, en
producción, con tres clientes reales con tráfico. Las otras dos historias son
consecuencias de ésta.

**Prueba independiente**: se recorre el catálogo entero, se calcula el
multiplicador de cada carril de cada modelo, y ninguno queda por debajo del
suelo. Se demuestra sola, sin desplegar nada y sin tocar a ningún partner.

**Escenarios de aceptación**:

1. **Dado** el catálogo de modelos con sus tarifas de proveedor cargadas,
   **cuando** se calcula lo que se cobra por un token de cada carril de cada
   modelo, **entonces** el cociente contra la tarifa de ese mismo carril es el
   multiplicador objetivo en todos ellos, y en ninguno es inferior al suelo.
2. **Dado** un turno pesado en salida, **cuando** se le cobra cuota,
   **entonces** lo cobrado cubre el coste del turno con el margen objetivo, y no
   por debajo.
3. **Dado** un modelo del catálogo al que le falta la tarifa de un carril,
   **cuando** se intenta derivar su peso, **entonces** el sistema se niega a
   servir por el carril de cuota y lo dice con el motivo, en vez de suponer un
   peso neutro.

---

### Historia 2 — El partner no ve un salto en su factura (Prioridad: P2)

El consumo de los clientes finales del partner —el grueso de su factura— es
pesado en prompt y ligero en salida. Al cambiar de un peso al peso de cada
carril, lo que se le cobra por ese trabajo se mueve en torno al **−1 %**: un
partner con tres barberías a 7.200 turnos al mes cada una pasa de 1.125,36 $ a
1.111,97 $. La corrección no llega como una subida de precio.

**Por qué esta prioridad**: el cambio es correcto pero sólo es defendible si no
se cobra a nadie de más por sorpresa. Verificarlo es parte de entregarlo.

**Prueba independiente**: se toma la mezcla típica de cliente final y se compara
la cuota vieja con la nueva para cada modelo del catálogo.

**Escenarios de aceptación**:

1. **Dado** un turno de cliente final de 10 K de prompt, 8 K de caché y 1 K de
   salida, **cuando** se le aplica la cuota nueva, **entonces** la cifra cobrada
   no sube más de un 2 % en ningún modelo del catálogo, y **baja** en los que el
   producto sirve hoy.

> **Medido durante la implementación, y no era lo que esta historia suponía.**
> El cambio del turno de cliente final sigue el **ratio salida/entrada** que
> cobra el proveedor, porque el peso único de la 0115 se calibró con una mezcla
> en la que la salida casi no pesaba: `gpt-4o` (ratio 4,0x) **−16,0 %**; `sol`,
> `sonnet` y `haiku` (5,0x) **−1,2 %**; `terra` y `luna` (6,0x) **+1,9 %**. Los
> dos que suben tenían la salida subvencionada **de más** y ahora pagan lo suyo.
> Un 1,9 % es invisible en una factura, y la alternativa —dejarles el peso
> viejo— sería conservar el defecto justo donde más se nota.
2. **Dado** un partner con consumo de cliente final ya registrado, **cuando** se
   recalcula su factura con los pesos nuevos, **entonces** el importe no sube.

---

### Historia 3 — Cambiar una tarifa no rompe el suelo en silencio (Prioridad: P3)

Las tarifas de proveedor viven en la base de datos precisamente para que
cambiarlas sea una fila y no un despliegue. Con los pesos también en la base,
actualizar un precio sin actualizar su peso deja el multiplicador de ese carril
donde nadie lo mira. El sistema tiene que delatarlo.

**Por qué esta prioridad**: es el modo de fallo que devuelve el sistema al
estado que esta spec corrige, y la primera vez que ocurra no habrá nadie
mirando. Va después porque no hay dinero saliendo hasta que alguien toque una
tarifa.

**Prueba independiente**: se altera la tarifa de un carril de un modelo sin
tocar su peso y se comprueba que la incoherencia se detecta.

**Escenarios de aceptación**:

1. **Dado** un modelo cuyo peso de un carril ya no corresponde a su tarifa,
   **cuando** se comprueba la coherencia del catálogo, **entonces** el sistema lo
   señala nombrando el modelo y el carril.
2. **Dado** un modelo nuevo que entra en el catálogo, **cuando** se le cargan sus
   tarifas, **entonces** no se puede servir por el carril de cuota hasta que
   tenga los tres pesos.

---

### Casos límite

- **Un peso que el redondeo deja por debajo del objetivo.** La columna que
  guarda el peso hoy admite tres decimales. El carril de caché de los modelos
  más baratos cae por debajo de esa resolución: el peso exacto del modelo más
  barato del catálogo es 0,0044 y se guardaría como 0,004, que es 2,00x en vez
  del objetivo. Sigue sobre el suelo — pero el siguiente modelo más barato que
  entre puede no estarlo, y nadie se enteraría.
- **Un modelo que no pasa por el carril de cuota.** `openai/whisper-1` se mide
  por minutos y no tiene peso. Debe seguir funcionando exactamente igual: la
  exigencia de los tres pesos es del carril de cuota de LLM, no del catálogo.
- **Un carril con tarifa nula.** Ningún proveedor del catálogo cobra por escribir
  en caché, y ese carril ya vale cero en la cuota. Debe seguir valiendo cero, y
  no convertirse en un cuarto peso.
- **Qué ve el partner cuando la capacidad no está disponible** (§V): un modelo
  sin pesos no se ofrece; no aparece apagado ni con una explicación de lo que no
  tiene. La ausencia se diseña.

## Requisitos *(obligatorio)*

### Requisito 1 — El peso es del carril, no del modelo

**Historia de usuario:** Como dueño del producto, quiero que cada carril se cobre
según lo que ese carril cuesta, para que el margen no dependa de la mezcla de
trabajo que haga el partner.

#### Criterios de aceptación

1. El sistema DEBE guardar, para cada modelo que se sirva por el carril de cuota
   de LLM, **tres pesos**: entrada, lectura de caché y salida.
2. El sistema DEBE derivar cada peso de la tarifa de proveedor de **ese mismo
   carril**, con un multiplicador único de **2,2x** para todos los carriles de
   todos los modelos, lo que fija el margen en **54,5 %** por construcción. Para
   el catálogo de hoy:

   | modelo | entrada | caché | salida |
   |---|---|---|---|
   | `openai/gpt-5.6-sol` | 0,880 | 0,0880 | 4,400 |
   | `anthropic/claude-sonnet-4-6` | 0,660 | 0,0660 | 3,300 |
   | `openai/gpt-4o` | 0,550 | 0,2750 | 2,200 |
   | `openai/gpt-5.6-terra` | 0,440 | 0,0440 | 2,640 |
   | `anthropic/claude-haiku-4-5` | 0,220 | 0,0220 | 1,100 |
   | `openai/gpt-5.6-luna` | 0,044 | 0,0044 | 0,264 |
3. WHEN se calcula la cuota de una llamada THEN el sistema DEBE aplicar a cada
   carril su propio peso, y NO DEBE aplicar un factor único al total.
4. WHERE la llamada tiene lectura de caché EL sistema DEBE cobrarla con el peso
   de caché del modelo, y NO DEBE aplicarle además el descuento plano que hoy
   aplica antes del peso.
5. El sistema DEBE seguir sin cobrar nada por la escritura en caché.
6. IF a un modelo del catálogo le falta alguno de los tres pesos THEN el sistema
   DEBE negarse a servir con él por el carril de cuota, nombrando el modelo, y NO
   DEBE suponer un peso neutro ni el de otro carril.
7. El sistema DEBE seguir sirviendo los modelos que no pasan por el carril de
   cuota de LLM aunque no tengan ningún peso.

### Requisito 2 — El suelo es un invariante, y se comprueba donde se guarda

**Historia de usuario:** Como dueño del producto, quiero que «nunca por debajo de
1,50x» sea algo que una prueba pueda poner en rojo, para no descubrirlo cuadrando
una factura.

#### Criterios de aceptación

1. El sistema DEBE tratar **1,50x** como suelo duro del cociente entre lo cobrado
   y la tarifa de proveedor, **por carril y por modelo**, nunca en promedio.
2. WHEN se comprueba el invariante THEN el sistema DEBE hacerlo sobre el valor
   **tal como queda guardado**, después de cualquier redondeo, y NO sobre el
   valor exacto antes de redondear.
3. IF algún carril de algún modelo del catálogo queda por debajo del suelo THEN
   la comprobación DEBE fallar nombrando el modelo y el carril.
4. El sistema DEBE conservar resolución suficiente para que **el carril más
   barato del catálogo alcance el multiplicador objetivo**, no sólo el suelo. Con
   la resolución de hoy, el carril de caché de `openai/gpt-5.6-luna` se guardaría
   como 0,004 en vez de 0,0044, que son 2,00x en vez de 2,20x: sigue sobre el
   suelo, pero el siguiente modelo más barato que entre puede no estarlo.
5. WHEN se amplía la resolución THEN los pesos de los modelos que hoy ya caben
   sin pérdida DEBEN quedar con el mismo valor, para que el cambio de escala no
   mueva por su cuenta lo que nadie decidió mover.

### Requisito 3 — Una sola cifra, en los dos sitios que la calculan

**Historia de usuario:** Como operador, quiero que el débito de un turno sea el
mismo lo calcule quien lo calcule, para que el libro cuadre.

#### Criterios de aceptación

1. El sistema DEBE producir la misma cuota para una misma llamada en los dos
   puntos que hoy la calculan — el de la API y el del worker.
2. WHEN se cambia la fórmula THEN los dos puntos DEBEN cambiar a la vez, y una
   prueba DEBE fallar si divergen.
3. El sistema DEBE seguir desglosando la cuota por medidor nativo sin colapsar el
   detalle, de modo que cada carril siga siendo visible en el libro.

### Requisito 4 — Agotar la bolsa cuesta lo mismo con cualquier cerebro y cualquier mezcla

**Historia de usuario:** Como dueño del producto, quiero que el peor caso de cada
plan lo fije yo al ponerle precio, y no el partner al elegir modelo.

#### Criterios de aceptación

1. El sistema DEBE hacer que el coste real de agotar una cantidad dada de cuota
   sea el mismo para todos los modelos del catálogo **y para cualquier mezcla de
   carriles**, dentro de la tolerancia que imponga el redondeo.
2. WHEN se comprueba la propiedad con una mezcla pesada en salida THEN la
   desviación entre modelos DEBE quedar por debajo del 2 %.
3. La documentación que hoy afirma esta propiedad DEBE dejar de afirmarla como
   cierta sólo en el punto de calibración.

### Requisito 5 — Lo ya comprado y lo ya en curso no cambian de valor sin decidirlo

**Historia de usuario:** Como partner, quiero que lo que compré valga lo que
valía cuando lo compré, o que se me diga que no.

#### Criterios de aceptación

1. El sistema DEBE aplicar los pesos nuevos al consumo que ocurra a partir del
   despliegue.
2. El sistema NO DEBE recalcular retroactivamente el consumo ya asentado en el
   libro.
3. WHEN el cambio alcanza a una bolsa incluida en curso o a créditos comprados y
   no gastados THEN el sistema NO DEBE revalorarlos ni añadirles unidades: la
   misma unidad sigue siendo la misma unidad, y desde el despliegue rinde el
   trabajo que corresponde a la tarifa nueva.
4. El sistema NO DEBE mantener dos tarifas vivas a la vez. Un débito se calcula
   con los pesos vigentes en el momento del débito, y no con los que había cuando
   se compró el saldo.
5. WHERE un partner ve su consumo EL sistema DEBE seguir mostrando una sola
   unidad comparable, sin distinguir saldo comprado antes o después del cambio.
6. El sistema NO DEBE encarecer el turno típico de cliente final más de un 2 % en
   ningún modelo del catálogo, y DEBE abaratarlo en los modelos que el producto
   sirve por defecto.

### Requisito 6 — Una tarifa que cambia sin su peso se delata

**Historia de usuario:** Como operador, quiero enterarme de que un precio y su
peso dejaron de corresponderse antes de que eso cueste dinero.

#### Criterios de aceptación

1. WHEN la tarifa de un carril y el peso de ese carril dejan de corresponderse
   THEN el sistema DEBE señalarlo nombrando el modelo y el carril.
2. IF la incoherencia hace caer ese carril por debajo del suelo THEN el aviso
   DEBE distinguirse del de una divergencia que sigue sobre el suelo.

### Requisito 7 — Lo que se documenta cambia con lo documentado

**Historia de usuario:** Como quien lea esto dentro de un año, quiero que los
documentos digan lo que el código hace.

#### Criterios de aceptación

1. WHEN esta spec se implemente THEN la decisión de KB que fija estas cifras DEBE
   actualizarse en el mismo commit: las dos afirmaciones que esta spec refuta, y
   el margen objetivo, que baja del **65 %** declarado al **54,5 %** que esta spec
   fija.
2. El comentario que declara el margen objetivo junto al precio de venta DEBE
   decir la misma cifra que el ADR y que esta spec. Hoy declara 65 % y ningún
   carril lo cobra.
3. La documentación viva del medidor DEBE describir los tres pesos y el suelo.
4. La comprobación de aislamiento que enumera los nombres del plano económico
   DEBE incluir los nombres nuevos.

### Entidades clave

- **Perfil de modelo**: el catálogo de plataforma. Guarda, por modelo, las
  tarifas de proveedor de cada carril y —desde esta spec— el peso de cada
  carril. **No pertenece a ningún tenant** y no lleva `tenant_id`: la RLS no lo
  alcanza porque no hay puerta que abrir, y `tests/isolation/test_pool_not_exposed_to_tenant.py`
  es lo que impide que alguien abra una.
- **Unidad de cuota**: lo que come la bolsa. Sigue siendo una sola unidad
  comparable entre modelos; lo que cambia es cómo se deriva de los tokens
  nativos.

## Criterios de éxito *(obligatorio)*

- **CE-001**: ningún carril de ningún modelo del catálogo se vende por debajo de
  1,50x el coste de proveedor, comprobado sobre los valores tal como quedan
  guardados.
- **CE-002**: un partner que agote su bolsa todas las semanas del mes deja margen
  positivo en los tres planes de pago.
- **CE-003**: la factura del consumo de clientes finales no sube más de un 2 %
  en ningún modelo, y baja en los que el producto sirve — en la mezcla típica,
  un 1,2 %.
- **CE-004**: el coste de agotar una cantidad dada de cuota varía menos de un 2 %
  entre los modelos del catálogo con una mezcla pesada en salida, donde hoy
  varía un 78 %.
- **CE-005**: existe una prueba que se pone en rojo si alguien añade al catálogo
  un modelo cuyo peso deje un carril bajo el suelo.
- **CE-006**: el margen resultante es del 54,5 % en todos los carriles de todos
  los modelos, y la cifra que declaran el ADR y el código coincide con ésa.

## Fuera de alcance

- **El tamaño de las bolsas de cada plan.** Las bolsas crecen ×4 y ×12 sobre Pro
  mientras los precios crecen ×3 y ×7,5, y por eso el peor caso empeora según
  sube el plan. Es una **decisión comercial del dueño**, no una corrección de un
  defecto, y se presenta aparte.
- **El precio de venta por millón de unidades.** No se toca.
- **Reprecificar consumo histórico.** El libro ya asentado no se recalcula (R5.2).
- **Windows, empaquetado y todo lo del escritorio.** Es la spec siguiente.

## Supuestos

- Las tarifas de proveedor cargadas en el catálogo son correctas y están
  fechadas; esta spec deriva de ellas y no las revisa.
- El precio de venta por millón de unidades de cuota se mantiene en su valor
  actual, de modo que el multiplicador se consigue moviendo el peso y no el
  precio. Bajar el margen objetivo de 65 % a 54,5 % es una decisión tomada en
  `/speckit-clarify` el 2026-09-14, no una consecuencia de la aritmética.
- La mezcla de referencia del turno de teammate (5 K de prompt, 4 K de caché,
  3 K de salida) y la de cliente final (10 K / 8 K / 1 K) son representativas
  para comparar el antes y el después. No se usan para calibrar nada — con pesos
  por carril el margen deja de depender de la mezcla, que es justamente el punto.
- Ningún proveedor cambia tarifas durante la implementación; si lo hace, R6 es
  lo que lo detecta.
