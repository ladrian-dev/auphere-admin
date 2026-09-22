# Specification Quality Checklist: La conversación es el producto

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-09-20
**Feature**: [spec.md](../spec.md)

## Content Quality

- [x] No implementation details (languages, frameworks, APIs)
- [x] Focused on user value and business needs
- [x] Written for non-technical stakeholders
- [x] All mandatory sections completed

## Requirement Completeness

- [x] No [NEEDS CLARIFICATION] markers remain
- [x] Requirements are testable and unambiguous
- [x] Success criteria are measurable
- [x] Success criteria are technology-agnostic (no implementation details)
- [x] All acceptance scenarios are defined
- [x] Edge cases are identified
- [x] Scope is clearly bounded
- [x] Dependencies and assumptions identified

## Feature Readiness

- [x] All functional requirements have clear acceptance criteria
- [x] User scenarios cover primary flows
- [x] Feature meets measurable outcomes defined in Success Criteria
- [x] No implementation details leak into specification

## Encabezado Auphere (plantilla propia)

- [x] Superficie de confianza declarada (`0`, ninguna nueva)
- [x] Garantías de aislamiento declaradas (ninguna de las 7; se nombra el eje
      cliente-dentro-del-tenant y la RLS por `principal_id`)
- [x] Nota de KB citada en las dos direcciones (constitución §IX)
- [x] Qué se mide, declarado (nada nuevo)

## Notas de la validación

**Dos iteraciones.** La primera versión no pasaba tres ítems:

1. **«No implementation details»** — la Historia 1 decía *«el historial del turno
   devuelve también el prompt»*, que es cómo, no qué. Reescrita como lo que la persona
   ve al reabrir; el cómo baja al supuesto correspondiente.
2. **«Success criteria are technology-agnostic»** — había un CE que hablaba de
   renderizar Markdown en menos de X ms. Sustituido por CE-003, que mide que se lee sin
   descifrar sintaxis. El rendimiento entra por el caso límite del mensaje enorme, que
   es donde importa de verdad.
3. **«Scope is clearly bounded»** — el panel de Entorno plegable estaba a la vez dentro
   (Historia 6) y fuera. Resuelto en «Fuera de alcance» con una condición explícita:
   entra sólo si la Historia 6 lo necesita.

**Cero marcas `[NEEDS CLARIFICATION]`, y es una decisión, no un descuido.** Las tres
preguntas que se plantearon se contestaron con lo que el repositorio ya tiene decidido:

- *¿Editar un mensaje conserva la versión anterior?* No: R5.1 dice que la conversación
  no queda con dos versiones mezcladas. Es lo coherente con §V — una pantalla que
  enseña dos versiones de lo mismo miente sobre cuál se usó.
- *¿La salida del comando se enseña en vivo o al terminar?* En vivo (R3.1): el dato ya
  viaja así, y esperar al final convierte un build de tres minutos en tres minutos de
  silencio.
- *¿Buscar alcanza a conversaciones archivadas?* No se decide aquí: la Historia 7 es P3
  y la spec no introduce archivado. Si el plan lo necesita, lo dirá.

**Riesgo abierto para `/speckit-plan`, escrito aquí para que no se pierda**: el supuesto
de que completar el registro de la conversación es *ampliar lo que se devuelve* y no
*crear un almacén*. Si resulta ser lo segundo, la Historia 1 cambia de tamaño y hay que
volver a esta spec antes de seguir.

---

## Revalidación tras `/speckit-plan` (2026-09-20)

La Fase 0 encontró **una frase que no se podía implementar** y la spec se
enmendó en consecuencia:

- **R3.2** decía «no debe persistir la salida en ningún sitio del que se pueda
  volver a leer». Leído literal prohibía también la clave efímera por la que la
  pantalla la recibe, y con ella R3.1 era imposible. Ahora dice «de forma
  durable», con un plazo declarado de quince minutos. La enmienda queda dentro
  de la propia spec, con su fecha y su porqué.

El resto del checklist sigue en verde. Y **el riesgo que quedó abierto se cerró
a favor**: el mensaje de la persona ya se persiste, así que la Historia 1 es
ampliar lo que se devuelve y no crear un almacén. No hace falta volver a la spec
por ese motivo.
