# Specification Quality Checklist: La máquina se registra con la sesión

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-09-22
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

## Notas de la validación

Tres cosas que costaron una pasada y conviene que queden escritas, porque la
tentación de resolverlas mal es real:

**1. Los nombres de tabla del apartado «Entidades clave».** La plantilla de este
repositorio los pide explícitamente —«a qué tenant pertenece y por qué columna la
alcanza la RLS»—, así que `partner_devices` y `principal_sessions` aparecen a
propósito. No es filtración de implementación: es el encabezado Auphere haciendo
comprobable la constitución §I.

**2. Cero marcas de clarificación, y no por comodidad.** Las dos preguntas que
podían llevarlas —el umbral de frescura y el tope de máquinas— se resolvieron con
un número escrito en Supuestos y su razón. Dejarlas abiertas habría bloqueado
`/speckit-plan`, y ninguna de las dos carece de un valor por defecto defendible:
una hora es el estándar de re-autenticación, y cinco máquinas no estorba a nadie
que trabaje normal. **Un supuesto con su razón es revisable; una marca abierta
solo aplaza.**

**3. Los criterios de éxito no hablan de milisegundos.** Cuentan pasos, asientos
y cosas que dejan de valer, que es lo que esta capacidad cambia. CE-003 se
redactó dos veces: la primera decía «las sesiones se invalidan», que es un
estado interno; la segunda dice «cero sesiones válidas comprobado en la siguiente
petición **sin esperar a ninguna caducidad**», que es lo que alguien puede
verificar sin mirar dentro — y que además es exactamente el defecto de hoy.

## Notes

- Items marked incomplete require spec updates before `/speckit-clarify` or `/speckit-plan`.
