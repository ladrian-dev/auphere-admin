# Specification Quality Checklist: El teammate sabe quién es, qué día es y qué puede hacer de verdad

**Purpose**: Validar que la spec está completa antes de planificar
**Created**: 2026-09-22
**Feature**: [spec.md](../spec.md)

## Content Quality

- [x] Sin detalle de implementación (lenguajes, frameworks, APIs)
- [x] Centrada en valor de usuario y necesidad de negocio
- [x] Escrita para alguien que no programa
- [x] Todas las secciones obligatorias completas

## Requirement Completeness

- [x] No quedan marcas `[NEEDS CLARIFICATION]`
- [x] Los requisitos son comprobables y sin ambigüedad
- [x] Los criterios de éxito son medibles
- [x] Los criterios de éxito no nombran tecnología
- [x] Todos los escenarios de aceptación están definidos
- [x] Los casos límite están identificados
- [x] El alcance está acotado
- [x] Dependencias y supuestos identificados

## Feature Readiness

- [x] Cada requisito funcional tiene criterios de aceptación claros
- [x] Los escenarios de usuario cubren los recorridos principales
- [x] La feature cumple los criterios de éxito declarados
- [x] No se cuela implementación en la especificación

## Notas de la validación

Tres pasadas. Lo que cambió en cada una:

**Pasada 1 — se colaba implementación en cinco sitios.** El borrador nombraba
`SYSTEM_PROMPT`, `system_prompt_for`, `for_teammate`, `unknown_tool` y
`cache_control` dentro de los requisitos. Todos ellos son **dónde** está el
problema, no **qué** hace falta. Reescritos en el espacio del problema: «el
texto compartido con el Companion», «el mismo cálculo que decide qué
herramientas recibe», «cuando el modelo nombra una herramienta que no existe»,
«los puntos de corte del caché». Las rutas con línea siguen estando donde les
toca — en `research.md` y en `decision.md` de la evaluación.

**Pasada 2 — dos criterios no eran comprobables.**

- R2.3 decía «el teammate debe saber qué le falta». *Saber* no se prueba. Ahora
  dice que **debe decírselo con su motivo y decir qué lo cambiaría**, que sí.
- R3.3 decía «el coste no debe crecer significativamente». *Significativamente*
  es exactamente la palabra que esta lista existe para cazar. Ahora dice que lo
  que se paga de más **debe ser solo el tamaño de los dos bloques nuevos**.

**Pasada 3 — dos criterios de éxito nombraban tecnología.** CE-005 hablaba de
«el catálogo `TOOLS_BY_NAME`» y CE-007 de «entradas de caché de Anthropic». El
primero pasó a «lo que se le enseña son solo las del teammate»; el segundo, a
«el texto compartido se sigue cacheando una vez para todos», que se puede
verificar sin saber de quién es el caché.

### Cero marcas de clarificación, y por qué no es sospechoso

Una spec sin `[NEEDS CLARIFICATION]` suele significar que nadie miró bien. Aquí
significa otra cosa: **las cinco preguntas abiertas se resolvieron antes de
llegar aquí**, y cada una tiene su rastro:

| Pregunta | Dónde se cerró |
|---|---|
| El número de la spec | Decisión de Luis, 2026-09-22 (D-A) |
| El texto del partner y §III | Decisión de Luis, 2026-09-22 (D-B) → Requisito 7 |
| La zona horaria | D-F, resuelta al comprobar que ni el partner ni la persona tienen columna de zona |
| Dónde va cada bloque | D-C, con el conflicto identidad↔entorno resuelto separándolos |
| El caché | **Medido antes de especificar**, y la medida cambió D-C |

### Una cosa que la lista no cubre y conviene decir

Los requisitos 1.4 y 3 hablan del coste del caché, que **suena** a
implementación. Se quedan porque no lo son: el hallazgo de la evaluación es que
la forma obvia de poner la identidad en su sitio **multiplica por N el coste de
cachear el texto compartido**, y eso es un efecto que el partner paga. Un
requisito que lo ignore deja la puerta abierta a entregar algo correcto y caro.
Lo que no dice es **cómo** se evita — eso es del plan.
