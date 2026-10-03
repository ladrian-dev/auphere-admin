# Contrato: motor de recomendaciones

## Interfaz
```ts
interface RecommendationProvider { recommend(answers: Answers): Promise<Result> }
function validateResult(result: Result, answers: Answers): { ok: true } | { ok: false; violations: string[] }
```
`RulesProvider` es síncrono por dentro y determinista. `validateResult` se aplica
a cualquier proveedor y rechaza: menos/más de 3 recomendaciones, textos con
cifras de ahorro/ROI o "garantiz*", recomendaciones cuya complejidad supere la
capacidad declarada + 1, ausencia de `reasons`, PII en textos (patrón email/teléfono).

## Algoritmo (`engine.ts`)
1. `segment = segmentAnswers(answers)`; `score = scoreAnswers(answers, segment)`.
2. Para cada oportunidad: `points = 3·|frictions ∩ problemSignals| + 2·|goals ∩ desiredOutcomes| + 2·[profile ∈ applicableProfiles] + 1·[sector ∈ applicableSectors] + 2·[category ∈ segment.opportunityCategories]`.
3. Excluir si `technicalComplexity > capacityIndex(techCapacity) + 1` (sin_equipo 2, limitado 3, interno 4, especializado 5).
4. `points ×= 0.5` y añadir advertencia si `maturity ∉ maturityRange`; `×= 0.6` si `investment = explorar` y `technicalComplexity ≥ 4`.
5. Ordenar por `points` desc, luego `technicalComplexity` asc, luego índice de catálogo.
6. Tomar en orden saltando la tercera de una misma categoría hasta tener 3.
7. Si hay < 3 con `points > 0`, completar con `defaultsByProfile[segment.profile]` (confianza `orientativo`).
8. Confianza: `prioritario` si `|matchedFrictions| ≥ 2 ∧ points ≥ 9`; `relevante` si `|matchedFrictions| ≥ 1 ∧ points ≥ 5`; si no `orientativo`.
9. `reasons`: frases desde `matchedFrictions`/`matchedGoals` con etiquetas legibles; `warnings` desde madurez, datos en papel, sin equipo.
10. `intro`, `shortTerm`, `midTerm`, `cta` desde `copy.ts` según perfil, categoría top e intención.

## Scoring (`scoring.ts`)
Ver spec Req. 6.2 y plan de sesión §8 para los pesos; se codifican como tablas
constantes exportadas para que los tests las citen.
