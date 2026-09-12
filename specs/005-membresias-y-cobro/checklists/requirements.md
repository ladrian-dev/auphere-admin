# Specification Quality Checklist: la membresía y el cobro

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-09-12
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

### Sobre «no implementation details»

Esta spec es **deliberadamente más agnóstica que la 004**, y es una decisión, no
un descuido. La 004 nombraba funciones y tablas porque el encabezado Auphere
obliga a declarar las garantías de aislamiento tocadas y las entidades exigen
decir por qué columna las alcanza la RLS.

Aquí, además, hay una razón de fondo: **ninguna de las siete secciones de
requisitos nombra al proveedor de pago.** No es pudor — es que el criterio de
aceptación que dice *«el mismo pago notificado cinco veces acredita una vez»*
sigue siendo el correcto con cualquier pasarela, y el que dijera *«el webhook de
Stripe con `event.id`»* dejaría de poder leerse el día que se evalúe otra. El
proveedor concreto, su nombre y su versión de API viven en el plan, que es donde
esa elección se justifica con su licencia.

### Cero marcas abiertas, y por qué

Las cuatro preguntas que la evaluación dejó para esta spec se cerraron con Luis
el 2026-09-12 **antes** de escribirla: crédito conservado doce meses tras la
baja · la factura del proveedor es el documento fiscal · `max_clients`
independiente del plan · solo dólares. Entran en la spec como dato.

### Lo que NO es una marca de clarificación, aunque lo parezca

El **tratamiento fiscal** está sin resolver y aparece tres veces en la spec. No
es una ambigüedad de requisitos: es una **precondición de despliegue** que se
resuelve con asesoría y configurando el proveedor, no escribiendo código ni
decidiendo alcance. Marcarlo como `[NEEDS CLARIFICATION]` habría bloqueado el
plan por algo que el plan no puede resolver.

Los **precios y tamaños** tampoco: la decisión de producto es que son
provisionales y viven como dato. La spec fija la estructura; las cifras se
cierran al medir el turno real, y R1.5 exige que cambiarlas no requiera
despliegue precisamente para que eso sea barato.

### Lo que añadió `/speckit-analyze` (2026-09-12)

**R1.8 no estaba y hacía falta.** El análisis encontró que la pantalla de planes
iba a publicar la cifra absoluta del pool —porque el catálogo la lleva— y que
eso deshacía lo que la Spec A R7.3 acababa de construir: que ajustar el tamaño
de un pool no se perciba como un recorte ni como un regalo. Las cifras son
provisionales por decisión de producto, así que el ajuste **va a pasar**.

No era un `[NEEDS CLARIFICATION]` que se pasara por alto: era un hueco que solo
se ve cuando el contrato de la API está escrito. La decisión, con lo que hacen
los seis referentes, está en research §D9.

### Estado

**Checklist completo.** 8 requisitos, **48 criterios**.
