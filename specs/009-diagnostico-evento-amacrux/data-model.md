# Data Model: Diagnóstico IA de Amacrux (009)

Sin base de datos. Estas entidades viven en memoria/`sessionStorage` del
navegador, en el cuerpo de la petición a `/api/leads` y en el correo a Amacrux.

## Enums (valores internos, en `src/domain/enums.ts`)

| Enum | Valores |
|---|---|
| `Profile` | `direccion` · `operaciones` · `innovacion` · `tecnologia` · `ingenieria` · `producto` · `marketing_ventas` · `consultoria` · `otro` |
| `Sector` | `comercio_retail` · `servicios_profesionales` · `salud_farmacia` · `hosteleria_turismo` · `industria_logistica` · `tecnologia_software` · `educacion` · `finanzas_seguros` · `sector_publico` · `otro` |
| `TeamSize` | `1_10` · `11_50` · `51_200` · `200_plus` |
| `CustomerType` | `b2b` · `b2c` · `publico` · `mixto` |
| `WorkLevel` | `inicial` · `explorando` · `adoptando` · `avanzado` · `escalando` |
| `AiUsage` | `no` · `pruebas_individuales` · `herramientas_puntuales` · `integrada` |
| `DataLocation` | `papel_chat` · `hojas_calculo` · `varios_sistemas` · `centralizada` |
| `Friction` (19) | `tareas_manuales` · `copiar_datos` · `emails_solicitudes` · `atencion_cliente` · `presupuestos` · `documental` · `extraccion_datos` · `reporting` · `ventas_leads` · `operaciones_logistica` · `planificacion_equipos` · `soporte_interno` · `desarrollo_software` · `testing_qa` · `documentacion_tecnica` · `busqueda_interna` · `visibilidad_datos` · `sin_tiempo_innovar` · `otro` |
| `Goal` (12) | `ahorrar_tiempo` · `reducir_errores` · `aumentar_ventas` · `mejorar_atencion` · `escalar` · `productividad` · `datos` · `acelerar_desarrollo` · `calidad_producto` · `decisiones` · `nuevos_servicios` · `reducir_costes` |
| `Urgency` | `explorar` · `proximos_meses` · `pronto` · `inmediato` |
| `TechCapacity` | `sin_equipo` · `limitado` · `interno` · `especializado` |
| `Investment` | `explorar` · `prueba` · `proyecto` · `estrategico` |
| `ProfileSegment` | `decisor_negocio` · `operaciones` · `tecnologico` · `ingenieria` · `producto_innovacion` · `marketing_ventas` · `consultor_independiente` |
| `MaturitySegment` | `explorador` · `inicial` · `en_adopcion` · `integrador` · `escalador` |
| `OpportunityCategory` (8) | `automatizacion_operativa` · `ia_conocimiento_soporte` · `automatizacion_comercial` · `procesamiento_documental` · `datos_reporting` · `ia_desarrollo` · `integraciones_orquestacion` · `producto_digital` |
| `IntentLevel` | `baja` · `media` · `alta` · `muy_alta` |
| `Complexity` | `quick_win` · `piloto_baja` · `proyecto_integracion` · `transformacion_proceso` · `solucion_estrategica` |
| `Confidence` | `orientativo` · `relevante` · `prioritario` |
| `ScoreRange` | `exploracion` · `oportunidad_inicial` · `oportunidad_prioritaria` · `alta_intencion` |
| `LeadTier` (interno) | `frio` · `tibio` · `caliente` · `muy_caliente` |

## Entidades

### Answers
| Campo | Tipo | Validación |
|---|---|---|
| profile | Profile | requerido |
| sector | Sector | requerido |
| teamSize | TeamSize | requerido |
| customerType | CustomerType | requerido |
| workLevel | WorkLevel | requerido |
| aiUsage | AiUsage | requerido |
| dataLocation | DataLocation | requerido |
| frictions | Friction[] | 1–3, sin duplicados |
| goals | Goal[] | 1–2, sin duplicados |
| urgency | Urgency | requerido |
| techCapacity | TechCapacity | requerido |
| investment | Investment | requerido |
| campaign | string? | `^[a-z0-9-]{1,64}$`; sin PII |
| utm | {source?, medium?, campaign?, content?}? | cada uno ≤ 64 chars alfanum/-/_ |

`AnswersSchema` (Zod) valida el conjunto; `PartialAnswers` para el estado del wizard.

### Segment
`{ profile: ProfileSegment; maturity: MaturitySegment; opportunityCategories: OpportunityCategory[] (ordenadas por señales); intent: IntentLevel; complexity: Complexity }`

### Score
`{ total: 0..100; range: ScoreRange; breakdown: { problemClarity 0-20, impact 0-20, urgency 0-15, capacity 0-15, maturity 0-10, fit 0-10, intent 0-10 }; leadTier: LeadTier }`
Invariante: `total === suma(breakdown)`; `range` por umbrales 30/55/75; `leadTier` = mapa 1:1 del rango.

### Opportunity (catálogo, `src/domain/opportunities.ts`)
| Campo | Tipo |
|---|---|
| id | string kebab, único |
| title | string |
| category | OpportunityCategory |
| applicableProfiles | ProfileSegment[] (vacío = todos) |
| applicableSectors | Sector[] (vacío = todos) |
| problemSignals | Friction[] |
| desiredOutcomes | Goal[] |
| maturityRange | [MaturitySegment, MaturitySegment] (inclusive, en orden explorador→escalador) |
| technicalComplexity | 1..5 |
| expectedTimeToPilot | string ("2–4 semanas") |
| problemSolved · howItWorks · benefitDescription | string |
| requiredInputs | string[] |
| recommendedFirstStep | string |
| amacruxFit | string |
| relatedTools | string[] |
| warning | string? |
| commercialCta | string |
| complexityLabel | Complexity |

Invariantes verificados por test: ≥24 entradas, 8 categorías con ≥3 cada una,
ids únicos, sin cifras de ROI en textos (regex de `%`, `€`, `$`, "garantiz").

### Recommendation
`{ opportunity: Opportunity; score: number; confidence: Confidence; reasons: string[] (≥1); warnings: string[]; matchedFrictions: Friction[]; matchedGoals: Goal[] }`

### Result
`{ version: 1; generatedAt: ISO string; summary: { profileLabel; sectorLabel; maturityLabel; opportunityLevelLabel; opportunityLevel: ScoreRange }; intro: string; recommendations: [Recommendation, Recommendation, Recommendation]; shortTerm: string; midTerm: string; warnings: string[]; cta: { label: string; intent: IntentLevel }; segment: Segment; score: Score }`
Invariantes: exactamente 3 recomendaciones; ≤2 por categoría; determinista.

### StoredSession (`sessionStorage["amacrux-diagnostico:v1"]`)
`{ version: 1; step: WizardStep; answers: PartialAnswers; startedAt: number; result?: Result; contactDecision?: "submitted" | "skipped" }`
Nunca contiene `Lead`. Si `version !== 1` o falla el parseo → descartar.

### Lead (solo en memoria y en la petición)
| Campo | Validación |
|---|---|
| name | 2–120 |
| company | 1–160 |
| email | formato email, ≤200, minúsculas |
| role | opcional, ≤120 (no se pide en el formulario reducido) |
| phone | opcional, 7–20, `[0-9+() -]` |
| interest | OpportunityCategory |
| consentContact | literal `true` |
| consentMarketing | boolean |
| resultSnapshot | `{ scoreTotal: 0..100; range; leadTier; segment; recommendationIds: string[3] }` |
| answers | `Answers` completo (sin PII), para el resumen del correo |
| campaign, utm | como en Answers |
| idempotencyKey | uuid v4 de la sesión |
| fax | honeypot, string vacío u omitido (si tiene contenido → éxito falso) |

### AnalyticsEvent
`{ name: AnalyticsEventName; props: { step?: string; profileCategory?: ProfileSegment; recommendationCategory?: OpportunityCategory; maturityLevel?: MaturitySegment; intentLevel?: IntentLevel; campaign?: string; ts: number } }`. Ningún otro campo se acepta (Zod `.strict()` en tests).

### Tabla `leads` (Supabase, v2)
Una fila por envío con consentimiento: contacto, consentimientos, campaña/UTM, `answers` (valores) y `answers_labels` (etiquetas), `score_total/score_range/lead_tier`, `segment`, `recommendations [{id,title,category,category_label}]`, `email_delivered/email_id`, `mode`. `idempotency_key` única. Esquema y vista `leads_panel` en `apps/amacrux-event/supabase/migrations/0001_leads.sql`.

## Transiciones del wizard (`WizardStep`)
`welcome → profile → company → work → frictions → goals → constraints → processing → result → lead → confirmation`
- `back`: paso anterior en la secuencia de preguntas (desde `result` vuelve a `constraints`).
- `skipContact`: `lead → result` con `contactDecision = "skipped"`.
- `restart`: cualquier paso → `welcome` con estado limpio (previa confirmación).
- `error`: overlay reversible que conserva `answers`.
