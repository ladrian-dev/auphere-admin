# Specification Quality Checklist: el medidor dice la verdad

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-09-11
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

## Notes

### Sobre «no implementation details» en este repositorio

Los requisitos (§Requisitos) están escritos **sin** nombres de tabla, de función
ni de endpoint: dicen «el libro del partner», «la misma función que ya aplica el
factor de la lectura de caché», «el registro de ejecuciones». Los nombres
concretos aparecen solo en el **Encabezado Auphere**, en la sección que describe
el defecto y en los Supuestos — que es exactamente lo que el override de
plantilla de este repositorio pide: el encabezado obligatorio exige nombrar las
garantías de aislamiento tocadas, y las Entidades clave exigen decir *«a qué
tenant pertenece y por qué columna la alcanza la RLS»*. El estándar local manda
sobre el genérico.

### La marca que hubo, y cómo se cerró

El criterio **3.4** salió con `[NEEDS CLARIFICATION]`: qué factor aplicar a un
modelo sin factor declarado. Tres salidas con consecuencias opuestas —comerse el
margen en silencio, cobrarle de más al partner por un olvido nuestro, o negarse—
y ningún defecto obviamente correcto.

**Resuelta con Luis el 2026-09-11: negarse a servirlo**, con error legible. Es
fail-closed, como ya es todo el camino del libro, y es lo que el sistema **ya
hace** con el catálogo de modelos, así que no introduce un modo de fallo nuevo.

### Lo que la revisión añadió

La conversación sobre la conversión de mensual a semanal destapó una decisión de
presentación que no estaba en el traspaso: **el partner ve una barra de consumo,
no la cifra de tokens**. Entró como **Requisito 7**, y arrastra dos consecuencias
que se escribieron con él:

- El criterio 4.3 pasó de «las tres devuelven el mismo total» a «las tres derivan
  del mismo dato»: lo que cada superficie **pinta** puede diferir; lo que **lee**,
  no.
- El saldo **comprado** queda fuera de la abstracción (criterio 7.6): eso es
  dinero que el partner pagó y tiene derecho a verificar en unidades.

Y una tercera, más útil de lo que parece: como el partner no ve el número, el
tamaño del pool **deja de ser un compromiso público** y se puede ajustar cuando
la medición del turno real diga algo distinto (CE-009).

### Estado

**Checklist completo.** Cero marcas abiertas. Lista para `/speckit-clarify` —que
tiene cuatro preguntas esperando, todas de la Spec B— o directamente para
`/speckit-plan`.
