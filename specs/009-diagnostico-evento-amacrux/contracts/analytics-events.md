# Contrato: eventos de analítica (anónimos)

`track(name, props)` en `src/lib/analytics.ts`. Adaptadores: `noop` (defecto), `console`, `plausible`.

| Evento | Cuándo | Props permitidas |
|---|---|---|
| `landing_viewed` | montaje de la bienvenida | campaign |
| `assessment_started` | pulsar "Empezar" | campaign |
| `question_answered` | al avanzar de pantalla | step, campaign |
| `assessment_completed` | al confirmar la última pantalla | profileCategory, maturityLevel, intentLevel, campaign |
| `result_viewed` | montaje del resultado | profileCategory, maturityLevel, intentLevel, recommendationCategory (top), campaign |
| `recommendation_selected` | expandir una recomendación | recommendationCategory, campaign |
| `contact_form_viewed` | montaje del formulario | intentLevel, campaign |
| `lead_submitted` | respuesta 200 del API | intentLevel, recommendationCategory, campaign |
| `contact_skipped` | "Prefiero no dejar mis datos" | intentLevel, campaign |
| `assessment_restarted` | confirmar reinicio | step, campaign |
| `error_shown` | cualquier estado de error visible | step, campaign |

Todas llevan `ts` (epoch ms). Ningún otro campo. Prohibido: nombre, empresa,
email, teléfono, texto de respuestas, ids de sesión.
