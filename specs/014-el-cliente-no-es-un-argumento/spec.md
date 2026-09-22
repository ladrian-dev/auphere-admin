# Especificación: El cliente del turno lo resuelve el servidor

**Rama**: `develop` (retroactiva) · **Creada**: 2026-09-22 · **Estado**: Retroactiva, cerrada

**Entrada**: spec **retroactiva** de un hotfix P0 aplicado el 2026-09-20.

> ## Por qué esta spec llega después del código
>
> `docs/spec-driven-development.md` §2 admite tres excepciones a la regla de que
> no entra código sin spec. Ésta es la primera: **hotfix P0, datos en riesgo**.
> «Se arregla primero. La spec retroactiva se escribe **en las 48 h siguientes**,
> o se revierte.»
>
> El arreglo se aplicó el **2026-09-20**; esta spec se escribe el **2026-09-22**,
> dentro del plazo. Lo que documenta ya está en `develop` y verificado:
> `.specify/bugs/el-cliente-no-es-un-argumento/`.
>
> Una spec retroactiva no sirve para justificar lo hecho: sirve para que la regla
> que se rompió quede escrita donde se buscan las reglas, y para decidir lo que
> el hotfix dejó abierto — que aquí es **una garantía de aislamiento nueva**.

## Encabezado Auphere *(obligatorio)*

| Campo | Valor |
|---|---|
| **Superficie de confianza** | `0` — no se abrió ninguna. El arreglo **cierra** superficie |
| **Garantías de aislamiento tocadas** | Ninguna de las 7 existentes. **Esta spec propone la octava** (§Requisito 2) |
| **Nota de KB que la justifica** | `[[research/2026-09-19-auditoria-clase-mundial/incidente-cliente-como-argumento]]` (privada: el detalle explotable no va al repositorio) |
| **Qué se mide** | Nada |

## Escenarios de usuario y pruebas *(obligatorio)*

### Historia 1 — Nadie ve la agenda de otro cliente del mismo negocio (Prioridad: P1)

Dos personas distintas escriben por WhatsApp a la misma clínica. Cada una habla
con el mismo agente, y cada una ve **lo suyo**: sus citas, su historial, su sitio
en la cola. Ninguna puede leer ni tocar lo de la otra, aunque lo pida, aunque lo
pida con astucia, y aunque el modelo se deje convencer.

**Por qué esta prioridad**: hasta el 2026-09-20 sí se podía. Doce herramientas de
`booking.*`, `client.*` y `queue.*` tomaban `customer_id` como **argumento del
modelo**, y a un modelo lo escribe quien le manda el mensaje.

**Prueba independiente**: dos clientes del mismo tenant, una consulta cada uno.

**Escenarios de aceptación**:

1. **Dado** dos clientes del mismo negocio con citas, **cuando** uno pregunta por
   sus citas, **entonces** ve las suyas y solo las suyas.
2. **Dado** el identificador de una cita ajena, **cuando** se intenta cancelarla o
   moverla, **entonces** se responde como si esa cita no existiera.
3. **Dado** un turno sin cliente resuelto, **cuando** se pide una lectura,
   **entonces** no se devuelve la agenda del negocio.

---

### Historia 2 — Una tarea que la plataforma siempre pudo completar (Prioridad: P1)

Una persona pide hora y **la consigue**. Hasta el arreglo no podía: reservar
exigía un identificador que el runtime **nunca le da al modelo**, así que o se lo
inventaba —violando la clave ajena— o no reservaba.

**Por qué esta prioridad**: es el mismo defecto visto por el otro lado. La
seguridad y la función se arreglan con el mismo cambio.

**Escenarios de aceptación**:

1. **Dado** una conversación con cliente resuelto, **cuando** se reserva,
   **entonces** la cita queda a nombre de esa persona.
2. **Dado** un turno sin cliente, **cuando** se intenta reservar, **entonces** se
   rechaza diciendo por qué, en vez de elegir a alguien.

---

### Casos límite

- **Un turno de operador**, sin cliente al otro lado: leer devuelve vacío y
  escribir se rechaza. La asimetría es deliberada (§Requisito 1).
- **Una herramienta nueva** que mañana necesite saber de quién es algo: tiene que
  encontrar el camino hecho, o repetirá el defecto.
- **Herramientas que no tienen eje de cliente** —disponibilidad, espera estimada—
  no cambian: no hay nada que resolver.

## Requisitos *(obligatorio)*

### Requisito 1 — El cliente es estado de ambiente, no un argumento

**Historia de usuario:** Como cliente final de un negocio, quiero que el agente
solo pueda actuar sobre lo mío, para que hablar con él sea seguro.

#### Criterios de aceptación

1. El sistema DEBE resolver el cliente del turno **en servidor**, desde el
   contexto de la petición, y NO DEBE aceptarlo como argumento en ninguna
   herramienta de cara al cliente final.
2. WHEN una herramienta de lectura se invoca sin cliente resuelto THEN el sistema
   DEBE devolver vacío, y NO DEBE devolver datos del negocio entero.
3. WHEN una herramienta de escritura se invoca sin cliente resuelto THEN el
   sistema DEBE rechazarla diciendo por qué.
4. WHEN se pide un objeto que pertenece a otro cliente THEN el sistema DEBE
   responder **igual** que si no existiera, sin distinguir los dos casos.
5. WHERE una herramienta no tiene eje de cliente EL sistema DEBE dejarla intacta.

### Requisito 2 — La octava garantía

**Historia de usuario:** Como quien mantiene esto dentro de seis meses, quiero
que el eje cliente-dentro-del-tenant esté declarado donde se declaran los demás,
para no volver a descubrirlo por un incidente.

#### Criterios de aceptación

1. `architecture/agent-isolation.md` DEBE declarar el aislamiento **entre
   clientes finales dentro de un mismo tenant** como garantía, con su número.
2. La suite de aislamiento DEBE tener al menos un test colgado de esa garantía.
3. La garantía DEBE decir explícitamente **qué no la cubre**: la RLS, porque las
   dos filas son legítimamente del mismo tenant.

> **Por qué esto es lo importante de la spec retroactiva.** El arreglo ya está.
> Lo que sigue abierto es que `test_35` bloquea merges **sin colgar de ninguna
> garantía declarada**, y ese hueco —una frontera real que el documento de
> garantías no nombra— es exactamente por donde entró el defecto.

## Criterios de éxito *(obligatorio)*

- **CE-001**: un cliente final no puede leer ni modificar nada de otro cliente del
  mismo negocio, ni pidiéndolo directamente ni induciendo al modelo.
- **CE-002**: reservar, cancelar y consultar funcionan de punta a punta sin que el
  modelo nombre a nadie.
- **CE-003**: el documento de garantías y la suite de aislamiento dicen lo mismo:
  ninguna garantía sin test, ningún test de garantía sin garantía.

## Fuera de alcance

- **Idempotencia de las herramientas con efectos** — la clave la sigue inventando
  el modelo. Es un defecto distinto (P1-5 de la auditoría) con otro arreglo, y va
  en la spec 016.
- **Comprobación de solapes al reservar** — ídem.
- **Respuesta a incidente** — si hubo exposición real se decide con el recuento de
  producción, y eso no lo cierra una spec.

## Supuestos

- El mecanismo de contexto de cliente **ya existía** y estaba bien razonado:
  `core/tenant_context.py` lo documentaba como «making cross-customer lookups
  impossible». Esta spec no lo inventa: lo aplica donde faltaba.
- El aislamiento entre tenants no se toca y sus siete garantías siguen intactas.

---

## Registro de ejecución

Una spec retroactiva no tiene `plan.md` ni `tasks.md`: el Requisito 1 ya estaba
construido cuando se escribió. Lo que sí tenía trabajo pendiente era el
Requisito 2, y aquí está lo que costó.

**2026-09-22 — Requisito 1.** Verificado, sin cambios. Ya en `develop` desde el
2026-09-20.

**2026-09-22 — Requisito 2.1, la garantía.** `architecture/agent-isolation.md`
pasa de siete garantías a ocho. La octava se escribió con su invariante exacto
—«cuando el turno tiene un cliente resuelto, ninguna herramienta devuelve ni
modifica datos de otro cliente»— y separando lo que el invariante exige de lo
que `booking.*` hace de más. No lleva métrica, y el documento dice por qué:
su fallo no ocurre en runtime, ocurre al escribir una firma, así que un
contador marcaría 0 también el día que el defecto vuelva.

**2026-09-22 — Requisito 2.2, el test.** Aquí es donde la spec se ganó el
sueldo. `test_35` cubre el eje de reservas enumerando **cuatro modelos a mano**,
y una herramienta en un servidor donde nadie miró no aparece en esa lista. Así
que el test de la garantía no enumera: barre. `test_37_customer_axis_contract.py`
recorre lo que cada vertical semilla pone de verdad en la whitelist y pregunta a
cada firma si acepta que le digan a quién mirar.

**Salió rojo a la primera, y no en reservas.** El detalle está en la KB porque
este repositorio es público; lo que sí va aquí es la forma del arreglo, que es
la garantía aplicada a un servidor que se había quedado fuera:

- El eje de cliente deja de ser argumento donde lo era.
- Lo que pertenece a otra persona se responde **igual que si no existiera**, con
  un test que compara las dos respuestas carácter a carácter — la diferencia
  entre «no existe» y «no es tuyo» *es* el oráculo de enumeración.
- La regla de pertenencia vive en un módulo puro, sin red y sin base de datos,
  para que se pueda leer y probar de un vistazo. **Falla cerrado**: los dos
  errores posibles no cuestan lo mismo.
- Donde una familia de herramientas sí tiene uso de personal del negocio, el
  turno sin cliente resuelto **no se filtra**. Vaciarle la lista al dueño de su
  propio negocio no protege a nadie, y el invariante solo habla de turnos **con**
  cliente resuelto.
- El prompt del vertical afectado se actualizó en el mismo cambio, que es la
  regla de la spec viva.

Verde: 112 de MCP, 944 de la API (semillas + aislamiento), `mypy --strict`
limpio, `verify.sh lint` entero.

**Requisito 2.3** queda cubierto en el texto de la garantía: dice explícitamente
que la RLS no la cubre, y por qué — las dos filas son legítimamente del mismo
tenant.

### Lo que esta spec deja escrito para la próxima

Un arreglo que se aplica donde se vio el defecto deja el defecto donde no se
miró. Lo que encontró el segundo sitio no fue mirar con más cuidado: fue
**convertir la regla en un barrido** y dejar que el código dijera dónde más
vivía. Si mañana aparece una garantía nueva, su test se escribe así.
