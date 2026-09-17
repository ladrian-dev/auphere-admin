# Specification Quality Checklist: la experiencia de la aplicación de escritorio

**Purpose**: Validate specification completeness and quality before proceeding to planning
**Created**: 2026-09-17
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

## Puertas propias de Auphere (constitución §Flujo de trabajo)

- [x] **Encabezado Auphere completo**: superficie `0` + tramo abierto de `3a`;
      garantías de aislamiento declaradas; nota de KB citada; qué se mide («nada
      nuevo»)
- [x] **Superficie declarada y justificada** (§II): no abre superficie nueva; con
      la absorción del puesto de trabajo, **retira** una partición
- [x] **Enmiendas declaradas**: la spec nombra en su encabezado las dos enmiendas
      de contrato (002, el puesto de trabajo como superficie propia; 003, la
      pantalla aprende dónde está la consola), en vez de colarlas
- [x] **Criterios en EARS** con numeración jerárquica (Requisito N, criterio N.m)
- [x] **§V cubierto de forma comprobable**: R4.1 exige los siete estados; R4.9 y
      R9.1–R9.2 recogen «la ausencia se diseña»
- [x] **§IV cubierto**: R10 (decidir con lo necesario delante, atribución visible)
- [x] **Sin cifra absoluta del pool** (004 R7): R9.6 lo dice explícitamente
- [x] **Sin credenciales ni datos de tarjeta**: R8.7, R9.10
- [x] **Texto de cliente final no se transcribe**: R12.5

## Validación ejecutada (2026-09-17)

Revisión ítem por ítem, primera iteración. Resultado: **todos pasan**. Tres notas
de la revisión, ya corregidas en la spec:

1. *Riesgo de detalle de implementación*: los términos «franja superior»,
   «controles de ventana del sistema», «partición» y «panel de contenido»
   describen **lo que la persona ve** o son parte del encabezado obligatorio de
   aislamiento, no elección de tecnología. Se conservan; no aparece ningún nombre
   de librería, canal, fichero ni API en el cuerpo de los requisitos.
2. *Ambigüedad de «rápido»*: sustituida por cifras verificables — ≤10 min
   (CE-001), <1 s para el armazón (CE-007), 4,5:1 y 3:1 de contraste (R2.4),
   24×24 px (R11.6), 200 % (R11.8), aviso al 80 % (supuesto 4, a confirmar
   contra la spec 004 en el plan).
3. *Ambigüedad de «un tiempo acotado»* en R7.4: se resuelve en el supuesto 5 —
   es el tiempo de espera que ya existe; lo que esta spec añade es que, al
   agotarse, se diga.

## Análisis de consistencia (`/speckit-analyze`, 2026-09-17)

Ejecutado con revisión independiente además de la comprobación mecánica. 23
hallazgos; **1 crítico y 5 altos corregidos** en spec, contratos, plan y tareas:

| Hallazgo | Qué pasaba | Corrección |
|---|---|---|
| **Crítico — secciones inalcanzables** | La lista canónica tenía 5 secciones de consola; la consola declara **10**. Al ocultar su barra lateral, inicio, conocimiento, auditoría, notificaciones y claves quedaban sin camino | Lista canónica = la navegación de la consola, con sus permisos (R1.2, contrato, T009) + test de paridad que falla si divergen (T010) |
| Alto — sin tests en dos racimos | 41 criterios sin tarea de test, entre ellos el camino de §IV (R10.4-10.7) y el teclado entero (R11.1-11.8) | Tareas de test añadidas para ambos racimos y para 6.2/6.4/6.5, 7.9/7.10, 8.4-8.6 y 9.11 |
| Alto — el tema no lo hacía nadie | R2.3 citado por tareas de tokens que no lo implementan | Par test/implementación propio (T045, T046) |
| Alto — prohibición mal redactada | Una tarea prohibía la palabra «sesión» en la pantalla que va a decir «tu sesión terminó» | Reescrita en los términos reales de R8.7: sin formulario de credenciales (T016) |
| Alto — tests que se rompen sin avisar | Cinco tareas cambiaban tests existentes sin declararlo, contra la regla del propio plan | Nueve tareas lo declaran ahora con nombre de fichero |
| Alto — suite rota en la tubería | El humo de Playwright dentro de `tests/` habría hecho rojo el paso que corre la tubería | Configuración de vitest que lo excluye (T004) |

Medios y bajos corregidos: la versión no admitida vive en **una sola** entidad;
ruta real del módulo de detección de la consola; umbral del 80 % cerrado contra
el que el producto ya usa; claves persistibles ampliadas con su test; retirada de
la barra enumerada entera; migas de pan aclaradas; cabecera del módulo que decía
«siete estados» teniendo ocho.

**Aceptado sin corregir**: seis criterios EARS siguen uniendo dos obligaciones en
una frase (son comprobables como par), y dos tareas siguen siendo grandes
(montar el armazón, cablear los avisos). Se parten durante la implementación si
se resisten.

## Notes

- Items marked incomplete require spec updates before `/speckit-clarify` or `/speckit-plan`.
- **Sin marcas `[NEEDS CLARIFICATION]`**: las cuatro decisiones que las habrían
  provocado (armazón, barra de 44 px, dirección del modo oscuro, corte en specs)
  se cerraron en la puerta de evaluación, con Luis, el 2026-09-17
  (`.specify/assessments/experiencia-app-escritorio/decision.md`). `/speckit-clarify`
  no es obligatorio; se puede pasar a `/speckit-plan`.
- **Cuatro condiciones de entrada al plan** vienen de la decisión y hay que
  resolverlas dentro de `/speckit-plan`, no antes: el spike de regiones de
  arrastre, la comprobación del mecanismo de avisos bajo la política de
  contenido, la verificación en pantalla del fallo de las hojas del puesto, y la
  licencia citada de cada dependencia nueva.
