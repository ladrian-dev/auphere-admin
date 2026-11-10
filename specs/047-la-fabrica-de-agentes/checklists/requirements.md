# Specification Quality Checklist: La fábrica de agentes

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-10-26
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

- Iteración 1 (2026-10-26): en verde. 33 historias (13 P1, 17 P2, 3 P3),
  56 requisitos en 17 bloques, 14 criterios de éxito y cero marcas
  `[NEEDS CLARIFICATION]`.
- «Sin detalles de implementación» lleva la excepción de siempre en este repo.
  El encabezado Auphere nombra la superficie y las garantías, y algunos
  requisitos nombran piezas que **son** el entregable o la regla que se protege,
  no una elección de cómo hacerlo:
  - Embedded Signup v5 y los avisos de coexistencia de Meta (requisito 30);
  - `store=false` y `data_retention_mode: none` (requisitos 41 y 56), que son la
    garantía 7;
  - `llm.route_decision`, `usage_records` y `pinned_model` (requisito 40), que son
    las garantías 4 y 6;
  - `RESPOND_MODELS` y `HOP_MODEL_IDS` (requisito 39), lo que hay que sacar del código;
  - `test_console_scope.py` y `tests/isolation/` (requisito 56);
  - los proveedores iniciales (requisito 41.5), que son la petición del owner.
- Las cuatro decisiones del owner (WhatsApp, bolsa, perfiles y papeles) y las
  decididas en la spec están en §Clarifications. Su porqué y lo descartado, en
  `research.md`.
- Dos decisiones de la spec se apartan de la recomendación de la investigación
  porque el owner eligió otra opción: los perfiles con paso directo y la ausencia
  de papeles en el cliente. La spec sigue la decisión del owner.
- Iteración 2 (2026-10-26, tras `/speckit-analyze`):
  - la spec pasa a ser la 047, porque el 046 es de la spec de Andrés;
  - se alinea con las decisiones del owner del 2026-10-24 en esa spec:
    «Próximamente» en el catálogo de canales (constitución 1.2.0), modo prueba al
    conectar, una pregunta en lugar de «Cloud API / Coexistencia», y «A todos»
    exige agente publicado y saldo;
  - se corrigen cinco puntos frente a la constitución: `system_prompt_rendered`
    sigue siendo la verdad del runtime, la ficha y el conocimiento van como datos
    vallados, los barridos barren, el estado «reconectando», y sin botones apagados.
