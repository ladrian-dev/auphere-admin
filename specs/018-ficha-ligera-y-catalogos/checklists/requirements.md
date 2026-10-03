# Specification Quality Checklist: la ficha adelgaza y sus catálogos se navegan

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-09-27
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

## Notas de la validación (2026-09-27)

Tres cosas se corrigieron durante la revisión, y se dejan anotadas porque
explican por qué la spec dice lo que dice:

1. **«Un resumen completo» era incomprobable.** La anotación del owner pedía
   «todos los datos importantes»; un resumen que lo enseña todo deja de
   resumir y el criterio no se puede testear. R1.1 lo convierte en cuatro
   preguntas con nombre, y R1.2 pone el límite: la cifra en el bloque, el
   detalle a un clic.
2. **«Como Perplexity» no es un requisito.** La referencia visual se tradujo a
   comportamiento observable (R4.1–R4.7) y se dejó dicho en Supuestos que se
   usa como patrón de navegación, no como diseño a copiar.
3. **Las direcciones viejas no pueden romperse.** Fundir y renombrar pantallas
   deja URLs guardadas en correos y marcadores, así que CE-007, R2.3, R3.3 y
   R5.4 lo fijan explícitamente. La spec 017 ya sentó ese precedente con
   `/tools` y `/skills`.

**Riesgo comprobado y descartado (2026-09-27).** R1.3–R1.5 suponían que las
cifras del Resumen ya se pueden leer por cliente. Se verificó antes de cerrar
la spec, en vez de dejarlo como supuesto: el informe de consumo ya acepta
acotarse a un cliente, las estadísticas de conversación ya son por cliente —de
hecho el Resumen de hoy usa tres—, y canales y conectores se leen por cliente
desde la spec 016. **El Resumen se puede construir con lecturas que ya
existen**, así que esta spec es más barata de lo que parecía y el trabajo de
API que `/speckit-plan` tenga que dimensionar es, como mucho, juntar esas
lecturas en una.
