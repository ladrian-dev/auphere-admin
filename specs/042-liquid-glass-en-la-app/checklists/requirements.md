# Specification Quality Checklist: Liquid Glass en la app, y lo que la auditoría encontró

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-10-20
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

Validado en una pasada, el 2026-10-20.

- **Detalle de implementación.** Los nombres de librerías (Expo,
  expo-glass-effect) solo aparecen en la cita literal de la entrada. Los
  requisitos hablan de plataformas y de materiales del sistema: iOS 26,
  Android, Material 3 Expressive, «Reducir transparencia». Son el producto, no
  el cómo.
- **Lo que se decidió con criterio en vez de marcar, sin ninguna marca
  abierta.** Está en «Supuestos»:
  - la búsqueda se queda en la Bandeja;
  - el fondo mantiene el color de la marca;
  - el respaldo antes de iOS 26 es la app de hoy;
  - el iPhone SE de 4,7″ es la referencia de «sin desplazar».
- **Requisitos que fijan la forma.** R5.5 (lista agrupada o una cifra
  protagonista) y R7.1 (cápsulas en iOS 26) fijan la forma a propósito: son el
  «qué» de un rediseño, y vienen de hallazgos medidos (H3 y H6). El plan elige
  entre las dos opciones de R5.5.
- **Riesgo para planificar.** CE-002 y CE-004 a CE-007 solo se pueden cerrar en
  iOS con el equipo descrito en el último supuesto: Xcode 26.4 o posterior,
  disco y simuladores. El plan tiene que ponerlo como tarea bloqueante del pase
  visual, no como nota.
