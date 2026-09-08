# Especificación: [NOMBRE DE LA FEATURE]

**Rama**: `[###-nombre-feature]` · **Creada**: [FECHA] · **Estado**: Borrador

**Entrada**: descripción del usuario: "$ARGUMENTS"

## Encabezado Auphere *(obligatorio)*

<!--
  Estos cuatro campos existen para que la constitución sea comprobable.
  Una spec sin ellos no pasa a /speckit-plan.
-->

| Campo | Valor |
|---|---|
| **Superficie de confianza** | [`0` API consola · `1` navegador · `2` VM · `3a` ejecutar en máquina del partner · `3b` controlar escritorio] |
| **Garantías de aislamiento tocadas** | [ninguna, o la lista de `architecture/agent-isolation.md`] |
| **Nota de KB que la justifica** | `[[nota]]` en `/Users/lmatos/Work/Auphere/...` |
| **Qué se mide** | [modelo · reloj de máquina · herramienta de pago · nada] |

> Si la superficie es distinta de la que ya está abierta, la spec explica en una
> frase por qué no se puede dar este valor dentro de la actual (constitución §II).

## Escenarios de usuario y pruebas *(obligatorio)*

<!--
  Historias PRIORIZADAS y cada una INDEPENDIENTEMENTE PROBABLE: si solo se
  implementa una, tiene que entregar valor por sí sola.
-->

### Historia 1 — [título breve] (Prioridad: P1)

[El recorrido en lenguaje llano]

**Por qué esta prioridad**: [qué valor entrega y por qué va primero]

**Prueba independiente**: [cómo se prueba sola y qué valor demuestra]

**Escenarios de aceptación**:

1. **Dado** [estado inicial], **cuando** [acción], **entonces** [resultado esperado]
2. **Dado** [estado inicial], **cuando** [acción], **entonces** [resultado esperado]

---

### Historia 2 — [título breve] (Prioridad: P2)

[…]

---

### Casos límite

- ¿Qué pasa cuando [condición de frontera]?
- ¿Cómo se comporta ante [escenario de error]?
- ¿Qué ve el usuario cuando la capacidad **no está disponible**? (constitución §V:
  la ausencia se diseña — ni botón apagado ni pantalla que explique lo que no tienes)

## Requisitos *(obligatorio)*

<!--
  FORMATO EARS, como en las specs de Kiro. Cada criterio es una frase
  comprobable, con un solo verbo normativo (DEBE), y se convierte en un test.

    WHEN  <disparador>            THEN el sistema DEBE <respuesta>
    IF    <condición no deseada>  THEN el sistema DEBE <respuesta>
    WHERE <característica presente> EL sistema DEBE <respuesta>
    WHILE <estado>                el sistema DEBE <respuesta>
    El sistema DEBE <respuesta>            (requisito ubicuo, sin disparador)

  Numeración jerárquica: Requisito N, criterio N.m. Las tareas citan `_Requisitos: N.m_`.
  Ambigüedad → [NEEDS CLARIFICATION: pregunta concreta]. Cero marcas antes de planificar.
-->

### Requisito 1 — [nombre corto]

**Historia de usuario:** Como [rol], quiero [capacidad], para [beneficio].

#### Criterios de aceptación

1. WHEN [disparador] THEN el sistema DEBE [respuesta observable].
2. IF [condición no deseada] THEN el sistema DEBE [respuesta], y NO DEBE [lo que no puede pasar].
3. WHERE [característica está presente] EL sistema DEBE [respuesta].

### Requisito 2 — [nombre corto]

**Historia de usuario:** Como […]

#### Criterios de aceptación

1. WHEN […] THEN el sistema DEBE […].

### Entidades clave *(si la feature toca datos)*

- **[Entidad]**: qué representa, atributos clave, **a qué tenant pertenece** y
  por qué columna la alcanza la RLS. Sin detalle de implementación.

## Criterios de éxito *(obligatorio)*

Medibles y sin tecnología dentro.

- **CE-001**: [métrica, p. ej. "el partner encarga una tarea, cierra la pestaña y la tarea termina"]
- **CE-002**: [métrica]

## Fuera de alcance

Lo que alguien podría suponer incluido y no lo está, con la razón en media línea.

- [Cosa] — [por qué no]

## Supuestos

- [Supuesto sobre usuarios, alcance, datos o dependencias]
