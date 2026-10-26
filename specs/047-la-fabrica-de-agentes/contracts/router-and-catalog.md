# Contrato — catálogo de modelos, perfiles, router y certificación

Requisitos 39 a 42. Los candidatos de este documento salen de la nota
`research/2026-10-26-fabrica-de-agentes-v2/06` §4.1 y §5.1. **Son candidatos, no
decisiones**: ninguno se enruta sin certificar (requisito 42).

## 1. Taxonomía de tareas, versión 1

| Código | Tarea | Dónde ocurre | De conversación | Capacidades que exige |
|---|---|---|---|---|
| `classify` | Clasificar la intención | Cada turno | No | Salida estructurada estricta |
| `extract` | Extraer datos con esquema | Argumentos y extracciones | No | Salida estructurada estricta |
| `answer` | Responder desde el conocimiento | Turno sin herramientas | **Sí** | Contexto ≥ el del agente |
| `tool_turn` | Turno con herramientas | Turno ReAct | **Sí** | Herramientas; paralelas si las hay |
| `escalate` | Razonamiento escalado | Subllamada aislada | No | Razonamiento |
| `summarize` | Resumir (traspaso, memoria, informe) | Asíncrono | No | — |
| `translate` | Traducir | Turno | No | — |
| `vision` | Ver imágenes (comprobantes, cartas) | Multimedia, lectura de documentos | No | Visión |
| `transcribe` | Transcribir audio | Notas de voz | No | Audio |
| `embed` | Calcular embeddings | Conocimiento | No | Embeddings multilingües |
| `rerank` | Reordenar resultados | Conocimiento | No | Reranker |
| `moderate` | Moderar entrada y salida | Turno | No | Clasificador de políticas |
| `judge` | Juzgar | Juez del turno, pruebas, certificación | No | Salida estructurada; **familia distinta** a la juzgada |
| `build` | Construir | Constructor, preguntas, pruebas del sector, revisión | No | Salida estructurada estricta; contexto largo |
| `read_source` | Leer webs y documentos para la ficha | Alta y fuentes | No | Contexto largo barato; salida estructurada |

La taxonomía está versionada en el catálogo. Una tarea nueva es una versión
nueva, con su batería de certificación.

## 2. Despliegue (una fila del catálogo)

```json
{
  "id": "bedrock-eu:anthropic.claude-haiku-5-5",
  "model": "claude-haiku-5-5",
  "family": "anthropic-claude",
  "provider": "aws_bedrock",
  "route": "eu.anthropic.claude-haiku-5-5",
  "region": "eu-south-2",
  "residency": "eu",
  "retention": { "zero": true, "how": "data_retention_mode:none" },
  "license": null,
  "contract": { "dpa": true, "subprocessor_listed": true },
  "status": "active",
  "retire_after": null,
  "quota": { "tpm": null, "rpm": null, "verified_at": null },
  "capabilities": {
    "tools": true, "parallel_tools": true, "strict_structured_outputs": true,
    "vision": true, "audio": false, "cache_mode": "explicit", "cache_min_tokens": 512,
    "context_management": true, "reasoning_control": "effort",
    "tool_name_charset": "dotted_ok", "context_window": 200000, "max_output": 64000
  },
  "prices": [
    {
      "valid_from": "2026-10-26", "source": "https://…", "currency": "USD", "unit": "per_million_tokens",
      "input": 0.11, "cache_read": 0.011, "cache_write": 0.1375, "output": 0.55,
      "long_context_surcharge": { "above_tokens": 100000, "multiplier": 5, "applies_to": "whole_request" }
    }
  ],
  "meter_weights": { "w_in": null, "w_cache": null, "w_out": null }
}
```

Las cifras del ejemplo son ilustrativas (Haiku 5.5 en `eu.` = global × 1,1,
derivado en `06` §2.3, sin leer). Los precios reales se cargan con su fuente y su
fecha. `meter_weights` se calcula con la regla de ADR-037 (`w = 2,2 × precio /
10`); un despliegue sin pesos no se puede activar (`UnweightedModel`).

`status`: `draft` → `certifying` → `active` → `retiring` → `retired`, y
`unavailable` desde cualquiera (requisito 41.9).

**Activación** (requisito 41.2) — el admin rechaza, diciendo qué falta, si:
- `retention.zero` es falso;
- `contract.subprocessor_listed` es falso;
- `license` es de una lista excluida (`llama-4-*`, `qwen3.8-flash-next`) o no está leída (`license.read_at` nulo);
- faltan los pesos del medidor;
- no tiene certificación por clase en ninguna tarea.

## 3. Perfiles (políticas por tarea)

Cada perfil es un documento versionado, editable desde el admin. Forma:

```json
{
  "profile": "auto",
  "version": 3,
  "tasks": {
    "classify":  { "min_quality": 0.90, "max_cost_per_call_micros": 200,   "escalate_to": null,    "reasoning": "none", "judge_sampling": null },
    "tool_turn": { "min_quality": 0.92, "max_cost_per_call_micros": 4000,  "escalate_to": "medium", "reasoning": "low",  "judge_sampling": "by_risk" },
    "answer":    { "min_quality": 0.92, "max_cost_per_call_micros": 3000,  "escalate_to": "medium", "reasoning": "none", "judge_sampling": "by_risk" },
    "escalate":  { "min_quality": 0.95, "max_cost_per_call_micros": 60000, "escalate_to": null,    "reasoning": "medium" }
  },
  "turn_cost_ceiling_micros": 80000,
  "max_calls_per_turn": 12,
  "max_escalations_per_hour": 3,
  "latency_p95_ms": { "classify": 800, "tool_turn": 6000, "answer": 4000 }
}
```

Las cifras son el punto de partida que el admin ajusta. «Calidad» es la nota
certificada de la batería (0–1) de §5.

**Candidatos iniciales por perfil** (`06` §5.1), por certificar:

| Tarea | Económico | Equilibrado | Máximo | Automático |
|---|---|---|---|---|
| `tool_turn` / `answer` | Haiku 5.5 `eu.`, razonamiento bajo · alternativa abierta: gpt-oss-120b | Haiku 5.5 `eu.`, razonamiento medio | Sonnet 5.5 `eu.` | El certificado más barato, fijado por conversación |
| `classify` | gpt-oss-20b · Nova Micro | gpt-oss-20b | Haiku 5.5 `eu.` | gpt-oss-20b |
| `escalate` | No escala: pasa a una persona | Sonnet 5.5, en subllamada | Opus 5.5 `eu.` | Sonnet 5.5, por señales |
| `vision` | Gemma 4 26B | Haiku 5.5 `eu.` | Sonnet 5.5 `eu.` | Haiku 5.5 `eu.` |
| `transcribe` | whisper-large-v3 (Scaleway) | Ídem | Ídem o Voxtral | Ídem |
| `judge` | GPT-6 Luna, muestreo del 10 % | GPT-6 Luna o gpt-oss-120b, 100 % | 100 % + juez Sonnet fuera de línea | Según el riesgo del turno |
| Coste orientativo por mensaje | ≈ 0,002 $ | 0,003–0,005 $ | ≈ 0,045 $ | ≈ 0,003 $ |

Las tareas `build`, `read_source`, `embed`, `rerank`, `moderate`, `summarize`,
`extract` y `translate` no dependen del perfil del agente: usan la política
«plataforma», que también se edita en el admin.

**Restricción soberana** (requisito 54.6): filtra el catálogo a proveedores
europeos y pesos abiertos (por ejemplo, DeepSeek V4 Flash o Qwen3.6-35B en
Scaleway para responder, gpt-oss-20b para clasificar y Gemma 4 26B para ver).

## 4. Elección (requisito 40.2)

```text
candidatos = despliegues del catálogo
  │ filtro duro: status=active ∧ permitido(partner, cliente) ∧ capacidades(tarea)
  │              ∧ residencia(cliente) ∧ retention.zero ∧ ¬excluido(soberana)
  │ calidad:     cert_clase(despliegue, tarea).nota ≥ perfil.min_quality
  │              ∧ (tarea de conversación ⇒ cert_agente(despliegue, agente) vigente)
  │ orden:       precio estimado de la llamada ↑, con latencia p95 ≤ objetivo
  ▼
cadena = [elegido, alternativa 1, alternativa 2]   (proveedores distintos, misma residencia)
```

- **Afinidad**: en las tareas de conversación, `pinned_model` en el checkpoint del
  hilo (`TenantScopedPostgresSaver`), con caducidad ≥ la caché del proveedor. Si el
  agente tiene «memoria propia» o el hilo pasó por Recepción, la clave es por agente
  dentro del estado del hilo.
- **Escalado**: subllamada aislada con resumen y salida tipada; el bucle principal
  no cambia de modelo.
- **Sin cadena con la residencia del cliente**: motivo `no_model` y aviso
  `ops.router_anomaly`.
- **Tarea sin certificados**: modelo de reserva de la tarea, si cumple la residencia.
- **Registro**: `llm.route_decision` (`events.md` §5) y, en `usage_records`, la
  tarea y el id de la decisión.

## 5. Certificación

### 5.1 Por clase (despliegue × tarea)

| Métrica | Cómo |
|---|---|
| `pass3` | Acierto en las 3 repeticiones de cada caso |
| `reasks` | Repreguntas por caso |
| `unsupported_claims` | Afirmaciones sin fuente |
| `tool_args_valid` | Argumentos de herramienta válidos al primer intento |
| `language_drift` | Respuestas en otro idioma sin que nadie lo pida |
| `latency_p50_ms`, `latency_p95_ms` | Con y sin razonamiento |

**Batería**: los casos del driver de evaluación, el paquete `es` de τ-bench 2.0 y
un dominio propio de reservas, con personas de España, México, Argentina,
Colombia y Chile, con tú y usted. Lleva versión. La nota de la tarea es una
combinación ponderada (`pass3` manda) que el admin publica con la versión de la
batería.

**Caducidad**: al cambiar la versión del modelo, el proveedor, la región, la
cuantización o la batería. Un cambio de precio no la caduca.

### 5.2 Por agente (despliegue × agente)

- La suite del agente (requisito 21) con ese despliegue en las tareas de conversación.
- Certifica si todas las críticas pasan 3 de 3 y la nota no baja más de 2 puntos
  frente a la referencia (el despliegue con el que está publicado).
- Caduca al publicar una versión con otro AgentSpec, al cambiar su suite o al
  caducar la certificación por clase.
- Quién paga: el partner («Construcción y pruebas») si la lanzó él al cambiar la
  calidad; Auphere, fuera de las partidas, si la lanzó Auphere (despliegue nuevo
  más barato, retirada).

### 5.3 Juez

El juez de una certificación o de una suite es de una familia distinta a la del
despliegue juzgado. Evalúa una dimensión por criterio, admite «No sé», y antes de
bloquear una publicación se calibra contra etiquetas humanas en español
(requisito 21.8).
