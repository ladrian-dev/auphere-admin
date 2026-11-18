# Guiones de reproducción — 063

Son la evidencia de `research.md` y el primer rojo de las tareas. No son código de
producto ni se importan desde ningún sitio.

| Guion | Dónde corre | Qué reproduce |
|---|---|---|
| `staging_language_in_block.py` | `ecs exec` en `nexus-staging-api` (contenedor `api`, `/app`) | La regla de idioma **dentro** del bloque de política. Pierde ante «Never answer in English» (0/2). Cuenta también los números sin agente y los clientes sin agente por defecto (D8). |
| `staging_language_last.py` | igual | La regla sin límite como **último** mensaje de sistema: 6/6, con la prohibición incluida. Cuenta las versiones activas con una prohibición de idioma. |
| `staging_language_last_limited.py` | igual | La regla con límite `es, en` como último mensaje: 4/4. |
| `local_foreign_names.py` | `cd apps/api && uv run python …` | Los cuatro casos de nombres de otros clientes (research §3). Hoy, «palabra corriente» da `invalid_draft`. |

Los de staging llaman al modelo real (`openai/gpt-5.6-sol`) fuera de un turno. No
facturan a nadie, pero cada caso son dos llamadas que paga Auphere. Se lanzan con
el script en base64 hacia `/tmp`, como se describe en la memoria de diagnóstico.
