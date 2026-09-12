# Especificación: la membresía y el cobro

**Rama**: `005-membresias-y-cobro` · **Creada**: 2026-09-12 · **Estado**: Borrador

**Entrada**: traspaso de
[`.specify/assessments/membresias-y-consumo-stripe/decision.md`](../../.specify/assessments/membresias-y-consumo-stripe/decision.md)
— veredicto **go** del 2026-09-11, partido en dos specs. Ésta es la **Spec B**, y
depende de la **Spec A** (`004-medidor-y-pool-semanal`), ya implementada y en
verde. Con las cuatro decisiones que Luis cerró el 2026-09-12: el saldo comprado
sobrevive doce meses a la baja · la factura de Stripe es el documento fiscal ·
`max_clients` sigue independiente del plan · solo USD.

## Encabezado Auphere *(obligatorio)*

| Campo | Valor |
|---|---|
| **Superficie de confianza** | **`0`** — API de la consola. **No abre una clase nueva**: el repositorio ya recibe webhooks de terceros (Meta, TikTok). Pero éste **acredita saldo**, así que la spec lo trata con el cuidado de lo que mueve dinero — ver el recuadro de abajo |
| **Garantías de aislamiento tocadas** | **1. Postgres RLS** — el estado de suscripción y el saldo son del **partner**, y ningún objeto nuevo lleva `tenant_id` · **4. Acción consecuente con rastro** — suscribirse, cambiar de plan y comprar crédito son acciones de una **persona** y la auditoría la nombra · **6. Log + trace tagging** — cada evento de Stripe deja rastro, y ninguno lleva dato de tarjeta |
| **Nota de KB que la justifica** | `[[nexus/decisions/ADR-037-membresias-y-consumo-de-la-app]]` (D1, D2, D3, D6, D7) · supersede parcialmente `[[ADR-022-stripe-integration-v1]]` §1-§5 y §8-§10 y conserva sus §13-§15 |
| **Qué se mide** | **Nada nuevo.** El medidor es el de la Spec A y no se toca. Esta spec **pone precio** a lo que aquél mide y **mete dinero** en el cubo comprado |

> **Por qué el webhook no abre superficie nueva, y qué lo contiene igualmente.**
> Un llamante externo que escribe en la plataforma ya existe: el webhook de Meta
> entrega mensajes de cliente final desde 2026. Lo que este webhook tiene de
> distinto no es la clase, es la **consecuencia**: acredita saldo, y el saldo es
> lo único que decide si un turno pasa.
>
> Tres cosas lo contienen, y las tres son requisitos de esta spec:
> **firma verificada antes de mirar el cuerpo**; **idempotencia por el
> identificador del evento**, porque un reintento del proveedor no puede doblar
> un ingreso; y **la conciliación va en una sola dirección** — un pago
> confirmado suma, y **nada que venga de fuera resta nunca**. Lo de fuera puede
> equivocarse a nuestro favor; que pueda equivocarse en contra del partner es
> otra cosa.

> **El tope sigue siendo de la plataforma.** Ésta es la decisión que más
> arrastra (ADR-037 D3) y esta spec no la toca: el proveedor de pago **cobra**;
> quien deja pasar o no un turno es el libro. Los créditos del proveedor se
> aplican **al cerrar la factura**, así que un saldo que solo se conoce al
> cierre del período no puede parar nada.

> **Precondición de DESPLIEGUE, no de especificación.** Esta spec se puede
> escribir, construir y probar entera sin resolver el tratamiento fiscal. Lo que
> **no** se puede es cobrarle a alguien sin él: ADR-022 dejó los impuestos
> apagados para un canal de dos agencias con inversión del sujeto pasivo, y una
> membresía de 20 $ vendible a cualquiera es otro problema — B2C posible, IVA
> europeo y ventanilla única, IVA chileno. Es asesoría, no ingeniería, y bloquea
> el primer cobro real. Ver §Fuera de alcance.

## Lo que la Spec A dejó hecho, y que aquí no se repite

| Ya construido | Consecuencia para esta spec |
|---|---|
| El pool **es** el cubo incluido del libro, semanal y anclado al alta del partner | El plan solo decide **su tamaño**, que ya es un dato que se cambia sin desplegar |
| Un solo medidor: la cifra que se enseña es la que decide | No hay contador nuevo. El cobro **no mide**; pone precio |
| Los clientes finales gastan solo el saldo **comprado** | Por eso comprar crédito es lo que mantiene atendiendo a los clientes, y la spec tiene que hacerlo fácil |
| El peso por modelo acota el peor caso de cada plan | Los precios de la tabla son **defendibles**: ningún nivel es deficitario aunque se agote entero |
| El partner ve barra y fecha; el operador ve cifras | El saldo **comprado** se enseña en unidades: es dinero que pagó |

---

## Escenarios de usuario y pruebas *(obligatorio)*

### Historia 1 — Un partner se suscribe y empieza a trabajar (Prioridad: P1) 🎯 MVP

Hoy no existe forma de pagar. Un partner que quiere la aplicación depende de que
alguien de Auphere le abra la puerta a mano, y la única recarga viva en
producción lleva credencial de administrador.

**Por qué esta prioridad**: sin esto no hay negocio. Todo lo demás de esta spec
—cambiar de plan, impagos, prorrateos— supone que alguien llegó a pagar una vez.

**Prueba independiente**: una persona elige un plan, paga, y su cuenta queda con
el nivel y el pool del plan **sin que nadie de Auphere intervenga**.

**Escenarios de aceptación**:

1. **Dado** un partner sin membresía, **cuando** elige un plan y completa el
   pago, **entonces** su cuenta pasa a ese nivel, su pool se ajusta al tamaño del
   plan y puede crear teammates hasta el tope del nivel.
2. **Dado** un pago que el proveedor confirma dos veces, **cuando** llegan los
   dos avisos, **entonces** la cuenta se acredita **una sola vez**.
3. **Dado** un aviso de pago cuya firma no verifica, **cuando** llega,
   **entonces** se rechaza sin mirar su contenido y queda registrado.
4. **Dado** un partner que abandona el pago a medias, **cuando** vuelve a la
   consola, **entonces** sigue en el nivel gratuito y no hay cobro ni cambio.

---

### Historia 2 — Comprar crédito para que los clientes sigan atendiendo (Prioridad: P1)

El consumo de los clientes finales sale del saldo comprado. Sin saldo, sus
agentes dejan de contestar — y hoy el partner no tiene forma de comprarlo.

**Por qué esta prioridad**: es la otra mitad del ingreso y la que sostiene el
servicio ya vendido. Un partner con clientes en producción y sin forma de
recargar es un incidente, no una carencia.

**Prueba independiente**: el saldo sube después de un pago confirmado, y **solo**
después.

**Escenarios de aceptación**:

1. **Dado** un partner con el saldo bajo, **cuando** compra un paquete de
   crédito y el pago se confirma, **entonces** su saldo sube en la cantidad
   comprada y sus clientes vuelven a atender sin tocar nada más.
2. **Dado** un pago iniciado y no completado, **cuando** se consulta el saldo,
   **entonces** **no ha subido**: se acredita con la confirmación, nunca con la
   intención.
3. **Dado** cualquier aviso del proveedor, **cuando** se procesa, **entonces**
   **nunca** resta saldo: la conciliación va en una sola dirección.

---

### Historia 3 — El impago degrada, y nada desaparece (Prioridad: P2)

Una tarjeta caduca. Lo que pase después decide si el partner vuelve o no.

**Por qué esta prioridad**: es la diferencia entre un cobro y una relación. Y es
donde más fácil resulta hacer daño: cancelar una tarea a medias o archivar un
teammate por un impago es perder trabajo de alguien por un problema de
facturación.

**Prueba independiente**: se simula cada escalón y se comprueba qué sobrevive.

**Escenarios de aceptación**:

1. **Dado** un cobro que falla, **cuando** llega el aviso, **entonces** el pool
   **no se repone** en su siguiente ciclo, el saldo comprado sigue gastándose, y
   la pantalla dice qué pasó y cuándo se reintenta.
2. **Dado** que los reintentos se agotan, **cuando** la cuenta queda impagada,
   **entonces** el trabajo nuevo se detiene con el estado que ya existe, y
   **ningún teammate se archiva, ninguna tarea se cancela y ninguna
   confirmación pendiente se pierde**.
3. **Dado** un partner impagado que paga, **cuando** el pago se confirma,
   **entonces** vuelve a estar al corriente **sin que nadie restaure nada a
   mano**.
4. **Dado** un partner que cancela, **cuando** termina su período pagado,
   **entonces** baja al nivel gratuito y conserva su historia entera.

---

### Historia 4 — Subir y bajar de plan sin perder nada (Prioridad: P2)

**Por qué esta prioridad**: subir de plan pasa justo cuando alguien se quedó sin
pool, y es el peor momento para castigarle.

**Prueba independiente**: se cambia de plan en los dos sentidos y se comprueba
qué pasa con el pool de la semana en curso y con el saldo comprado.

**Escenarios de aceptación**:

1. **Dado** un partner que se ha quedado sin pool a mitad de semana, **cuando**
   sube de plan, **entonces** el cambio es inmediato y su pool de **esta** semana
   se **completa** hasta el tamaño del plan nuevo — no se reinicia ni se queda
   como estaba.
2. **Dado** un partner que baja de plan, **cuando** lo hace, **entonces** el
   cambio se aplica **al final del período** y el pool de la semana en curso no
   se reclama.
3. **Dado** cualquier cambio de plan, **cuando** se aplica, **entonces** el saldo
   **comprado no se toca**.
4. **Dado** un partner que baja a un plan con menos teammates de los que tiene,
   **cuando** el cambio se aplica, **entonces** **no se archiva ninguno**: se le
   dice cuántos sobran y no puede crear más hasta estar por debajo.

---

### Historia 5 — El recibo dice lo que la factura no sabe (Prioridad: P3)

**Por qué esta prioridad**: el recibo mensual ya existe y funciona. Lo que cambia
es su papel — deja de ser el documento que se paga — y se le añade lo que ahora
hay que explicar.

**Prueba independiente**: se emite un mes y se comprueba que ya no promete un
cobro y que el desglose está.

**Escenarios de aceptación**:

1. **Dado** un mes cerrado, **cuando** se emite el recibo, **entonces** lleva una
   línea de membresía y una de consumo, y **no** dice «total a pagar» ni tiene
   vencimiento.
2. **Dado** un partner con comisiones en otra moneda, **cuando** se emite,
   **entonces** el detalle de la conversión sigue estando: es lo que el
   proveedor de pago no sabe.

---

### Casos límite

- **El aviso de pago llega antes que el de suscripción creada.** Los avisos no
  llegan en orden garantizado; acreditar en el orden equivocado no puede dejar un
  saldo huérfano.
- **Dos pestañas compran a la vez.** Dos pagos confirmados son dos ingresos; dos
  avisos del mismo pago, uno.
- **El proveedor está caído.** No se puede comprar; **el trabajo sigue** con lo
  que ya hay en el libro. Nada de lo que decide un turno depende de que el
  proveedor conteste.
- **Un partner con saldo comprado cancela y vuelve a los ocho meses.** Su saldo
  sigue ahí: caduca a los doce.
- **Un cambio de plan y una renovación semanal caen en el mismo instante.** El
  pool no puede quedar ni al doble ni a cero.
- **Un reembolso.** Está **fuera de alcance** en esta versión y la spec lo dice;
  lo que no puede es procesarse a medias.
- **Capacidad no disponible** (§V): un partner en el nivel gratuito **no ve un
  botón apagado** de «crear teammate». La ausencia se diseña.

## Requisitos *(obligatorio)*

### Requisito 1 — Los niveles existen y limitan

**Historia de usuario:** Como Auphere, quiero que cada nivel tenga topes reales,
para que el precio signifique algo.

#### Criterios de aceptación

1. El sistema DEBE ofrecer **tres niveles de pago** y un nivel gratuito, y cada
   uno DEBE llevar su tamaño de pool, su número de teammates y su número de
   personas.
2. El sistema DEBE impedir crear un teammate por encima del tope del nivel, con
   un error que diga **cuál es el tope y cómo se sube**, y NO DEBE archivar
   ninguno existente para hacer sitio.
3. El sistema DEBE impedir añadir una persona por encima del tope del nivel, con
   el mismo criterio.
4. WHERE el nivel es el gratuito, EL sistema NO DEBE permitir teammates ni
   ejecución en la máquina, y NO DEBE pintar controles apagados para ninguna de
   las dos.
5. Los topes y el tamaño del pool DEBEN ser **datos**: cambiarlos NO DEBE exigir
   despliegue ni migración.
6. IF un partner queda por encima de un tope tras bajar de plan THEN el sistema
   DEBE decírselo y bloquear la creación de nuevos, y NO DEBE retirar nada de lo
   que ya tenía.
7. `partners.max_clients` NO DEBE depender del nivel.

### Requisito 2 — Suscribirse es cosa del partner

**Historia de usuario:** Como partner, quiero contratar y pagar yo mismo, para
no depender de que alguien me abra la puerta.

#### Criterios de aceptación

1. El sistema DEBE permitir a una persona con permiso de facturación contratar
   un nivel **sin intervención de Auphere**.
2. El sistema NO DEBE manejar, almacenar ni registrar datos de tarjeta en ningún
   punto: el dato de pago vive en el proveedor.
3. WHEN un pago de suscripción se confirma THEN el sistema DEBE aplicar el nivel
   y ajustar el pool **en el mismo acto**.
4. IF una persona abandona el pago a medias THEN el sistema NO DEBE cambiar nada
   de su cuenta.
5. El sistema DEBE registrar quién contrató, cambió o canceló, **nombrando a la
   persona** y no al proceso (§IV).
6. La consola NO DEBE guardar ninguna credencial del proveedor de pago.

### Requisito 3 — Comprar crédito, y que solo cuente lo confirmado

**Historia de usuario:** Como partner, quiero comprar saldo para que mis clientes
sigan atendiendo, y que se acredite solo cuando de verdad he pagado.

#### Criterios de aceptación

1. El sistema DEBE permitir comprar crédito en paquetes, y el saldo comprado DEBE
   subir **solo** con un pago confirmado.
2. El sistema NO DEBE acreditar saldo por una intención de pago, por una sesión
   abierta ni por ninguna llamada del propio partner.
3. WHEN el mismo pago se notifica más de una vez THEN el sistema DEBE acreditar
   **una sola vez**.
4. El sistema NO DEBE **restar** saldo por ningún aviso externo: la conciliación
   con el proveedor va en una sola dirección.
5. La puerta que hoy permite a un partner acreditarse saldo sin pago DEBE
   **desaparecer**, no quedarse apagada por entorno.
6. WHEN el saldo sube THEN el partner DEBE poder verlo **en unidades**, porque es
   dinero que pagó.

### Requisito 4 — El aviso del proveedor es de fiar o no se procesa

**Historia de usuario:** Como Auphere, quiero que nadie pueda acreditarse saldo
falsificando un aviso.

#### Criterios de aceptación

1. El sistema DEBE verificar la firma del aviso **antes** de interpretar su
   contenido, y IF no verifica THEN DEBE rechazarlo y dejar rastro.
2. El sistema DEBE registrar cada aviso recibido antes de actuar sobre él, de
   modo que reprocesar sea posible sin volver a pedirlo.
3. El sistema DEBE responder al proveedor **deprisa** y hacer el trabajo aparte:
   un aviso no puede perderse porque el trabajo tardó.
4. El sistema DEBE ser idempotente por el identificador del aviso.
5. IF un aviso llega en un orden inesperado THEN el sistema NO DEBE dejar el
   saldo ni el nivel en un estado incoherente.
6. Ningún registro del camino del pago DEBE llevar datos de tarjeta ni contenido
   de conversación.

### Requisito 5 — El impago degrada por escalones, y nada se pierde

**Historia de usuario:** Como partner al que le ha caducado la tarjeta, quiero no
perder mi trabajo mientras lo arreglo.

#### Criterios de aceptación

1. El sistema DEBE tener estados de cuenta explícitos: **al corriente**, **pago
   fallido**, **impagada** y **cancelada**.
2. WHILE la cuenta esté en **pago fallido**, el pool NO DEBE reponerse en su
   siguiente ciclo, y el saldo comprado DEBE seguir gastándose con normalidad.
3. WHEN la cuenta pasa a **impagada** THEN el trabajo nuevo DEBE detenerse con el
   estado que ya existe para quedarse sin saldo, y el sistema **NO DEBE**
   archivar teammates, **NO DEBE** cancelar tareas y **NO DEBE** invalidar
   confirmaciones pendientes.
4. WHEN una cuenta impagada recibe un pago confirmado THEN DEBE volver a estar al
   corriente **sin intervención manual**.
5. WHEN una cuenta se cancela THEN DEBE bajar al nivel gratuito al terminar el
   período pagado, conservando su historia completa.
6. El sistema DEBE avisar **antes** de que el servicio se degrade, no después.
7. La pantalla DEBE decir en qué estado está la cuenta y qué lo arregla, sin
   pintarlo como un error del partner.

### Requisito 6 — Cambiar de plan no cuesta nada de lo ya pagado

**Historia de usuario:** Como partner que se ha quedado corto, quiero subir de
plan y seguir trabajando ahora mismo.

#### Criterios de aceptación

1. WHEN un partner sube de nivel THEN el cambio DEBE ser inmediato.
2. WHEN un partner sube de nivel a mitad de ciclo THEN su pool de ese ciclo DEBE
   **completarse** hasta el tamaño del nivel nuevo, y NO DEBE reiniciarse ni
   quedarse como estaba.
3. WHEN un partner baja de nivel THEN el cambio DEBE aplicarse **al final del
   período**, y el pool del ciclo en curso NO DEBE reclamarse.
4. Ningún cambio de nivel DEBE alterar el **saldo comprado**.
5. IF un cambio de nivel coincide con una reposición de ciclo THEN el pool
   resultante NO DEBE quedar duplicado ni a cero.

### Requisito 7 — El crédito comprado sobrevive doce meses a la baja

**Historia de usuario:** Como partner que se va y vuelve, quiero que el saldo que
pagué siga ahí.

#### Criterios de aceptación

1. El saldo comprado NO DEBE caducar **mientras la cuenta esté viva**.
2. WHEN una cuenta se cancela THEN su saldo comprado DEBE conservarse **doce
   meses** y caducar después.
3. IF la cuenta se reactiva dentro de ese plazo THEN el saldo DEBE volver a estar
   disponible **sin que nadie lo reponga a mano**.
4. El sistema DEBE decirle al partner, al cancelar, **cuánto saldo conserva y
   hasta cuándo**.
5. WHEN el saldo caduca THEN DEBE quedar rastro de cuánto caducó y cuándo.

### Requisito 8 — El recibo deja de ser la factura

**Historia de usuario:** Como partner, quiero un documento que me explique en qué
se fue el consumo, y una factura que sirva para mi contabilidad.

#### Criterios de aceptación

1. El recibo mensual DEBE llevar una línea de **membresía** y una de **consumo**.
2. El recibo NO DEBE decir «total a pagar» ni llevar fecha de vencimiento: ya no
   es el documento que se paga.
3. El recibo DEBE conservar el desglose por cliente y el detalle de la conversión
   de moneda de las comisiones — es lo que el proveedor de pago no sabe.
4. El partner DEBE poder llegar a sus facturas del proveedor desde la consola.
5. Los dos documentos NO DEBEN contradecirse en el importe del período.

### Entidades clave

- **Nivel de membresía** — un plan del catálogo con su precio, su tamaño de pool
  y sus topes de teammates y de personas. **De plataforma**: igual para todos,
  sin `tenant_id`.
- **Suscripción del partner** — qué nivel tiene, en qué estado está y hasta
  cuándo. Pertenece al **partner**; la RLS la alcanza por `partner_id`.
- **Aviso de pago recibido** — el registro de lo que el proveedor nos contó, con
  su identificador para no procesarlo dos veces. **Operacional**, sin
  `tenant_id`: no es de nadie en particular y no puede llevar dato de tarjeta.
- **Compra de crédito** — cuánto se compró, cuándo se confirmó y qué asiento
  generó. Pertenece al **partner**.
- **Caducidad del saldo comprado** — desde cuándo cuenta el plazo de doce meses.
  Pertenece al libro del partner.

## Criterios de éxito *(obligatorio)*

- **CE-001**: Un partner nuevo contrata, paga y **está trabajando** sin que nadie
  de Auphere intervenga.
- **CE-002**: El mismo pago notificado cinco veces acredita **una vez**.
- **CE-003**: Ningún aviso externo reduce el saldo de un partner, nunca.
- **CE-004**: Con el proveedor de pago caído, **el trabajo continúa** con el
  saldo que ya hay; solo no se puede comprar más.
- **CE-005**: Tras un impago completo, el partner conserva **todos** sus
  teammates, **todas** sus tareas y **todas** sus confirmaciones pendientes.
- **CE-006**: Un partner que paga tras un impago vuelve a trabajar sin que nadie
  toque una fila.
- **CE-007**: Subir de plan sin pool disponible devuelve pool **en el acto**.
- **CE-008**: Ningún cambio de plan modifica el saldo comprado.
- **CE-009**: Un partner que cancela y vuelve a los once meses recupera su saldo.
- **CE-010**: El recibo del mes y la factura del proveedor coinciden en el
  importe del período.
- **CE-011**: No existe ninguna vía por la que un partner se acredite saldo sin
  pago confirmado.

## Fuera de alcance

- **Reembolsos y notas de crédito.** Necesitan decidir qué pasa con el saldo ya
  gastado y con la comisión de la pasarela; es su propia conversación.
- **El tratamiento fiscal.** No es alcance de ingeniería: **es la precondición de
  desplegar**. Se decide con asesoría y se aplica configurando el proveedor.
- **Facturación al cliente final del partner.** El partner factura a su cliente
  por su cuenta; Auphere cobra al partner. Sin cambios respecto a ADR-022.
- **Monedas distintas del dólar.** La moneda queda fijada por cliente en su
  primera factura y cambiarla exige rehacerlo; se añade cuando un partner real lo
  pida.
- **Descuento anual.** El precio mensual primero.
- **Cobro del alta (setup).** Sigue siendo el circuito manual de ADR-022 §5.
- **SSO, SCIM y marca del partner.** Fase 2, y no dependen de esto.
- **Cambiar el medidor.** Es la Spec A y está hecha.

## Supuestos

- **Los precios y tamaños de la tabla son provisionales**, y por eso son datos y
  no constantes. La estructura —tres niveles, pool semanal, caída a crédito— es
  lo que queda fijado; las cifras se cierran cuando se mida el turno real.
- **Existe una cuenta con el proveedor de pago** y el equipo puede configurarla.
  Es la única dependencia externa de esta spec.
- **El partner que contrata tiene permiso de facturación.** El modelo de
  permisos de la consola ya distingue ese rol.
- **El nivel gratuito no se factura**, así que un partner en él no tiene
  suscripción ni aparece en el proveedor de pago hasta que contrata.
- **La escalera de reintentos la gestiona el proveedor.** Lo que decide esta spec
  es qué pasa **en la plataforma** en cada escalón, no cuántas veces se reintenta
  una tarjeta.
- **Un aviso del proveedor puede llegar dos veces y en desorden.** Se asume desde
  el diseño y no como caso raro.
