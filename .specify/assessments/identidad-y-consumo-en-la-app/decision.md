# Decision: la identidad y el consumo en la aplicación de escritorio

- **Slug**: identidad-y-consumo-en-la-app
- **Decided**: 2026-09-09
- **Verdict**: **go**
- **Artifacts reviewed**: [`intake.md`](./intake.md) · [`research.md`](./research.md)
  · [`problem.md`](./problem.md) · [`concept.md`](./concept.md)
- **Superficie de confianza (§II)**: `0` (API de la consola) más el tramo de
  emparejamiento sobre la `3a` ya abierta. **No abre superficie nueva.**

---

## Scorecard

| Criterio | Valoración | Justificación |
|---|---|---|
| **Validez del problema** | **strong** | No es una hipótesis: hoy no existe camino de producto para dar de alta una máquina, y el propio repositorio lo dejó escrito y se negó a taparlo (`enrol_device_dev.py`). Sin esto, las 73 tareas de la 001 son inalcanzables para cualquiera que no tenga una terminal contra la base |
| **Fuerza de la evidencia** | **strong** para lo que decide, **medium** para lo que se aparta | Todo el expediente es lectura de código de este repositorio con ruta y línea. El único hallazgo de confianza media —el Embedded Signup de Meta dentro de la cáscara— **ya no forma parte del alcance**: la conexión de canales se hace en la consola del navegador por decisión explícita. La evidencia que sostiene el `go` no depende de él |
| **Valor frente a no hacer nada** | **strong** | No hacer nada no es «más lento»: la instalación **se muere a las 12 horas** por la caducidad de la credencial, sin camino de renovación. La opción de seguir con el script de operador no existe como estado estable |
| **Viabilidad / apetito** | **adequate** | La Opción A cabe holgadamente. T-1b —el cambio de dueño del dispositivo— sube el apetito a `medium` y toca §I, lo que rebaja esta fila de `strong` a `adequate`: es asumible, no es gratis, y hay que hacerlo con la ceremonia completa |
| **Encaje estratégico** | **strong** | §II se cumple de frente: agota valor dentro de dos superficies ya pagadas y no abre ninguna nueva. La Opción A se eligió precisamente porque las otras dos abrían superficie (en la cáscara, la B; en el sistema operativo, la C) |
| **Postura de riesgo** | **adequate** | Los tres riesgos serios están nombrados y tienen dueño: §I con T-1b (se paga con tests de aislamiento), la ruptura del contador único (se ataja no construyendo nada), y la revocación rota del Requisito 6.3 (fuera de alcance, con camino propio y **dependencia declarada**). No es `strong` porque T-1b enmienda un requisito de una spec ya construida |

---

## Verdict & Rationale

**Go.** El problema es real, está documentado en el propio código y su coste de
inacción no es una degradación sino una caducidad: sin emparejamiento y sin
renovación, una instalación dura doce horas. La evidencia que sostiene la
decisión es lectura directa de este repositorio, no inferencia, y el único
hallazgo de confianza media quedó fuera del alcance por decisión explícita. Hay
una opción concreta —el código de emparejamiento— que resuelve el problema **sin
abrir superficie de confianza nueva**, que es lo que §II pide y lo que descarta a
sus dos alternativas.

El `go` no es incondicional: se firma con tres decisiones tomadas en esta puerta
y escritas abajo, y una de ellas —T-1b— **enmienda un requisito de la spec 001**.
Eso no se cuela: se declara, y la spec que salga de aquí tiene que decirlo en su
encabezado.

### Las tres decisiones que esta puerta toma

**D-1 · El dispositivo pasa a ser del partner, no del tenant (T-1b).**
`concept.md` recomendó lo contrario, apoyado en un supuesto que escribió para
poder derribarlo: *un cliente por máquina durante la beta 2*. El supuesto cayó
aquí. La aplicación es **la herramienta con la que un partner configura y
administra a sus clientes**, en plural. Con eso, T-1a no es deuda tolerable: es
pedirle a una persona que empareje la misma máquina una vez por cada cliente que
administre, para acabar con varias credenciales que la aplicación no puede llevar
a la vez.

Consecuencias, dichas enteras porque son caras:

- Toca el modelo de datos de la 001 (`partner_devices`, migración `0106`).
- **Enmienda el Requisito 6.3**, que hoy dice que la credencial va «acotada a su
  tenant». Pasa a ir acotada al **partner y a los tenants de ese partner**, con el
  tenant fijado por trabajo y no por la firma. El espíritu del requisito —no
  alcanza otro dispositivo, no alcanza a quien no le corresponde, cuatro
  operaciones y ni una más— **se conserva**; lo que cambia es el eje.
- Por tanto **toca §I de frente**, y la spec debe declarar las garantías afectadas
  y llevar test de aislamiento por cada una. `test_29` deja de valer tal cual y
  hay que reescribirlo: una credencial de dispositivo del partner A no puede
  alcanzar trabajo del partner B **ni de un tenant que no sea suyo**.
- El apetito sube de `small`–`medium` a **`medium`**.

**D-2 · La conexión de canales de Meta se hace desde la consola, en el
navegador.** Se acepta como limitación conocida y se retira del alcance el riesgo
que no estaba medido. Dos condiciones para que esto no se convierta en una
pantalla que miente:

- Dentro de la aplicación, **la ausencia se diseña** (§V): ni un botón apagado ni
  una pantalla que explique lo que no se tiene.
- La limitación se escribe donde se pueda encontrar, con su motivo, y se revisa
  cuando haya tiempo de hacerlo escalable y estable. No es un «ya veremos»: es
  una decisión con fecha de revisión.

**D-3 · El alcance firmado** es emparejamiento (Opción A) **+** renovación de la
credencial **+** leer `principal_id` (T-2), con D-1 dentro.

---

## If go — Handoff to `/speckit-specify`

- **Problema**: un partner que instala la aplicación no tiene ningún camino de
  producto entre «la acabo de abrir» y «la plataforma sabe quién soy y qué máquina
  es ésta»; hoy lo suple un operador ejecutando un script contra la base, y la
  credencial que reparte caduca a las 12 horas sin renovación posible.

- **Enfoque elegido**: **el código de emparejamiento.** La consola, dentro de la
  ventana, entrega un código corto y efímero al dar de alta la máquina; la
  aplicación lo pide en su única pantalla propia y lo canjea por su credencial de
  dispositivo. **El canal entre la página y la cáscara es la persona**, de modo
  que no hace falta abrir ninguno — ni `preload`, ni puente de contexto, ni
  esquema de URL propio.

- **En alcance**:
  1. El emparejamiento completo: emisión del código, su canje, y la pantalla de
     la aplicación con sus estados.
  2. **Renovación de la credencial de dispositivo**, para que una instalación
     sobreviva más de doce horas.
  3. **El dispositivo pertenece al partner** (D-1), con la enmienda del Requisito
     6.3 declarada y sus tests de aislamiento.
  4. **Leer `principal_id`** con el mecanismo ya probado del Companion
     (`0090_companion.py` + `core/principal_context.py`), para que la decisión 9
     —hilo privado por persona— sea cierta también aquí.
  5. **Qué es cerrar sesión y qué es desemparejar**, escrito como política con sus
     consecuencias.
  6. El consumo: **cargar `/usage`**. Como restricción, no como trabajo.

- **Fuera de alcance**:
  - Un flujo de login propio de la aplicación (el de la consola basta —
    research D-1).
  - El puente de contexto y el esquema de URL propio, descartados **con motivo
    escrito**, no aplazados en silencio.
  - Registro / autoservicio de partners — depende de la decisión §2.3 de la KB,
    que sigue **abierta**. Esta spec no la cierra por la puerta de atrás.
  - Reimplementar pantallas de la consola (Requisito 15.1).
  - Conectar canales de Meta desde la aplicación (D-2).
  - Arreglar la revocación de dispositivo que hoy no funciona — **dependencia
    declarada**, con camino propio.
  - Cualquier cifra de consumo calculada por la aplicación.
  - Precio y facturación · superficie `3b` · navegador embebido · beta 5.

- **Métricas de éxito** (de `problem.md`, con las bases medidas):
  - Altas sin intervención de operador: **100 %** *(base: 0 %)*.
  - Accesos a la base de producción para dar de alta: **cero** *(base: uno por
    instalación)*.
  - Vida útil de una instalación sin repetir el alta: **indefinida mientras la
    persona conserve acceso** *(base: 12 h)*.
  - Emparejamientos necesarios por máquina: **uno**, con independencia de cuántos
    clientes administre el partner *(base: uno por cliente)*.
  - Dispositivos con dueño legible por consulta: **100 %** *(base: la columna
    existe y nadie la lee)*.
  - Contadores de consumo distintos: **exactamente uno** *(base: uno — métrica de
    no-regresión)*.

- **Preguntas que viajan abiertas a la spec**:
  - [NEEDS CLARIFICATION: **la forma del código de emparejamiento** — longitud,
    caducidad, un solo uso y resistencia a fuerza bruta. Se decide con el mismo
    cuidado que una invitación, y el precedente está en
    `api/console/invitations.py`.]
  - [NEEDS CLARIFICATION: **qué renueva la credencial y cada cuánto**, sin ampliar
    las cuatro operaciones que el Requisito 6.3 autoriza. Si renovarla obliga a
    una quinta, la premisa cambia y hay que decirlo en la spec.]
  - [NEEDS CLARIFICATION: **¿cerrar sesión desempareja la máquina?** Y si no, qué
    la desempareja — sabiendo que hoy archivarla no detiene el puente hasta que la
    revocación se arregle por su camino.]
  - [NEEDS CLARIFICATION: **cómo se acota la credencial del partner a sus
    tenants** sin que el `tenant_id` llegue nunca del llamante (§I). Es el corazón
    de la enmienda del Requisito 6.3 y de los tests de aislamiento nuevos.]
  - [NEEDS CLARIFICATION: **qué ve una persona en una máquina compartida** — qué
    dispositivos, qué hilos y qué aprobaciones. Es la decisión 9 aplicada al
    puesto de trabajo.]

  Las cinco son de `/speckit-clarify`, y **ninguna spec pasa a `/speckit-plan` con
  una sola abierta**.

---

## Advertencia de método que esta evaluación hereda

La 001 se dejó dos huecos —la cáscara de Electron y el otro extremo del puente—
porque la comprobación de cobertura mapea **criterios citados en tareas**, y un
requisito citado por una tarea que no lo entrega puntúa como cubierto.
**Cobertura por cita no es cobertura por capacidad**, y ya han sido dos veces.

Esta evaluación abrió un tercer caso del mismo patrón sin buscarlo: el Requisito
6.3 dice «revocable por sí sola», está citado por `T071` y `T074`, y **nada mira
`revoked_at`** en el camino del puente. Va fuera de alcance, pero se anota aquí
para que la spec que salga de este `go` compruebe su cobertura **por capacidad**:
por cada criterio, qué se puede hacer que antes no se podía, y qué test lo
demuestra en rojo antes de existir.

---

## Enlace de vuelta a la KB (§IX, obligatorio en las dos direcciones)

Pendiente al cerrar la spec: `[[14-mvp-y-fases]]` §3 y `[[10-decisiones]]`
—decisiones 2 y 9, y la §2.3 declarada como dependencia— deben apuntar a la
carpeta `specs/NNN-*` que salga de este `go`. Una decisión de KB sin spec delante
es una decisión que nadie ha ejecutado.
