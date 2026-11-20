# Lista de calidad de la especificación: El modelo de cada agente

**Propósito**: validar que la spec está completa antes de planificar
**Creada**: 2026-11-19
**Spec**: [spec.md](../spec.md)

## Calidad del contenido

- [x] Sin detalles de implementación (lenguajes, frameworks, APIs), salvo los nombrados en las notas
- [x] Centrada en el valor para el usuario y el negocio
- [x] Escrita para quien decide, no para quien programa
- [x] Todas las secciones obligatorias completas

## Completitud de los requisitos

- [x] No queda ninguna marca [NEEDS CLARIFICATION]
- [x] Los requisitos se pueden probar y no son ambiguos
- [x] Los criterios de éxito se pueden medir
- [x] Los criterios de éxito no dependen de la tecnología
- [x] Todos los escenarios de aceptación están definidos
- [x] Los casos límite están identificados
- [x] El alcance está acotado
- [x] Dependencias y supuestos identificados

## Preparada para planificar

- [x] Cada requisito funcional tiene criterios de aceptación claros
- [x] Las historias cubren los flujos principales
- [x] La funcionalidad cumple los resultados medibles de los criterios de éxito
- [x] No se cuelan detalles de implementación en la spec

## Notas

- La spec nombra a propósito piezas del sistema que son contrato con specs anteriores o la causa concreta de un requisito:
  - el código `409 model_policy_managed` y la frase de Agente › Avanzado (spec 047, requisito 64);
  - el requisito 68 de la 047 (cobro de las pruebas);
  - `fallback_chain` (spec 016);
  - LiteLLM y su mapa de modelos (requisito 4.12: la plataforma ya depende de él y su conducta no es fija).

  No describen cómo se implementa esta spec; el cómo está en plan.md y research.md.
- Siete decisiones las tomó Luis el 2026-11-19: cuatro en una sola pregunta (oferta tras staging, ajuste vivo, reserva de la otra familia, los seis para todos) y tres después (cobrar todo al partner, un solo sitio, Haiku 5.5 por defecto salvo Jemma). Las demás están en «Supuestos», marcadas para su revisión.
- Iteraciones: la primera versión no tenía la puerta por entorno, la reserva cruzada, el turno que solo añade ni LiteLLM determinista. Entraron tras la revisión independiente del diseño y la sonda en el cable. Después entraron el escalón 2, el cuarto carril y el modelo por defecto. Cobertura final: 69 de 69 criterios y 8 de 8 criterios de éxito con tarea, 73 tareas.
