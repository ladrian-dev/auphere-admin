---
name: post-op-symptom-triage
description: Triage clínico de tres niveles que el agente del vertical estético aplica cuando una paciente describe síntomas tras un procedimiento. Distingue lo normal (tranquilizar) de lo que requiere control próximo (agendar) de lo que es red flag y necesita urgencia inmediata (derivar a hospital + escalate). Surface this skill on any inbound que mencione síntomas post-procedimiento, dolor, fiebre, sangrado, hinchazón, o cualquier reporte clínico tras una cita reciente.
version: 1
---

# Post-op triage — los tres niveles y qué hacer en cada uno

Esta skill materializa la regla 7 del system prompt
`aesthetic_clinic_v1`. Es la skill más crítica en términos de
responsabilidad clínica: una paciente con un coágulo post-BBL que
recibe un "tranquila, eso pasa" pierde una pierna o la vida.

## Regla maestra

**El agente clasifica el síntoma reportado en uno de tres niveles —
normal, llamada al día siguiente, o urgencia inmediata — y nunca
"baja" un nivel para tranquilizar a la paciente.** Cuando dude entre
dos niveles, elige el más alto.

## Los tres niveles

### Nivel 1 — Normal (tranquilizar, dar pautas de cuidado, NO escalar)

Síntomas dentro del rango clínicamente esperable. El agente reconoce,
contextualiza, y refuerza las indicaciones post.

| Procedimiento | Síntoma | Ventana normal |
|---|---|---|
| Inyectables (Botox, AH) | Cardenales en zona de aplicación | Hasta 2 semanas |
| Inyectables | Hinchazón leve | 24–72 horas |
| Inyectables AH labios | Asimetría temporal por edema | 3–7 días |
| Láser CO2 | Eritema intenso, sensación de quemadura solar | 3–5 días |
| Láser CO2 | Costras / descamación | 5–10 días |
| Hydrafacial / peeling superficial | Enrojecimiento leve, sequedad | 24–72 horas |
| Lipo / BBL | Hinchazón significativa | 2–4 semanas |
| Lipo / BBL | Cardenales en zona tratada | Hasta 3 semanas |
| Cirugía facial (rino, blefaro) | Edema y cardenales | 1–2 semanas |
| Cirugía facial | Congestión nasal post-rino | 1–2 semanas |
| Mamoplastia | Tensión y "subir" de los implantes | Semanas 2–6 |
| Cualquier cirugía | Sensibilidad, prurito leve | Días/semanas |

Respuesta tipo: *"Lo que describís entra en lo normal a esa altura
del post — los cardenales pueden durar hasta dos semanas tras el
ácido hialurónico. Recordate: arnica tópica si la doctora la
indicó, evitar alcohol, dormir con la cabeza un poco elevada, sin
sol directo. Si en los próximos días notás algo distinto (dolor
que crece, calor en zona, secreción), me avisás."*

No escala. No agenda. Solo tranquiliza con base + da pautas.

### Nivel 2 — Llamada / control al día hábil siguiente

Síntomas que están fuera del rango normal pero no son urgencia.
Requieren evaluación próxima — el médico estético o la cirujana lo
ven al día hábil siguiente.

Triggers:
- Fiebre baja (<38°C) que cede con paracetamol.
- Dolor que requiere analgésico adicional al pautado por la médica.
- Secreción serohematica escasa por incisión.
- Asimetría que preocupa a la paciente y no estaba en el resultado
  esperado.
- Eritema que persiste más allá de la ventana normal del
  procedimiento.
- Hematoma que crece más allá de día 4.
- Dolor unilateral leve sin signos de TVP (sin calor, sin hinchazón
  marcada, sin enrojecimiento).
- Ardor del láser que persiste > 48h sin mejora con cuidados pautados.

Respuesta tipo: *"Lo que describís está un poco fuera de lo
esperable — no es urgencia, pero la doctora tiene que verlo. Te
agendo control para mañana en la mañana. Mientras tanto: [pautas
específicas según síntoma]. Si entre ahora y la cita aparece
[lista de red flags concretos], andá directo a
{tenant.surgery_referral_hospital}."*

Agenda control con `booking.create_appointment` para el día hábil
siguiente. NO escala a urgencia.

### Nivel 3 — RED FLAG → urgencia inmediata + escalate

Síntomas que indican complicación potencialmente grave. El agente
NO tranquiliza, NO programa control, NO sigue conversando: indica
ir AHORA al hospital de referencia y escala a un humano.

Triggers:
- **Fiebre alta** > 38.5°C (sospecha de infección sistémica).
- **Sangrado activo** por incisión que empapa apósitos en minutos.
- **Dolor torácico** (sospecha de tromboembolismo pulmonar, especialmente
  tras lipo/BBL/abdominoplastia).
- **Dificultad respiratoria** (sospecha de TEP o broncoaspiración).
- **Asimetría facial súbita** (sospecha de ictus o complicación
  vascular).
- **Dolor unilateral severo en miembro inferior** con calor / hinchazón
  marcada / enrojecimiento, en post de lipo, BBL, abdominoplastia
  (sospecha de trombosis venosa profunda — TVP).
- **Dehiscencia de sutura** (apertura de herida quirúrgica).
- **Secreción purulenta abundante** (infección establecida).
- **Alteración del estado de conciencia** (confusión, somnolencia
  marcada, desorientación).
- **Hematoma expansivo** que crece visualmente en minutos/horas
  (especialmente facial o cervical — riesgo de obstrucción de vía
  aérea).
- **Necrosis cutánea** (zona oscurecida, fría, sin retorno capilar).
- **Reacción alérgica sistémica** (urticaria generalizada, dificultad
  respiratoria, edema de garganta).

Respuesta tipo: *"Lo que describís puede ser [nombre genérico de la
complicación, sin diagnosticar], y necesita evaluación AHORA, no
puede esperar al día siguiente. Por favor, andá ya a
{tenant.surgery_referral_hospital} — la línea de emergencia es
{tenant.surgery_referral_phone}. Si podés, alguien te lleva. Yo le
aviso a {clinical.titular_name} en este momento."*

Luego, INMEDIATAMENTE:
1. Llamar `escalate.escalate_to_human` con motivo
   "post-op red-flag — urgencia clínica" + descripción literal del
   síntoma.
2. Llamar `operator.consult_owner` con `urgency=high` notificando a
   la médica titular.

No seguir conversando después de eso (excepto si la paciente
pregunta confirmación de qué hacer). NO sugerir aplicar hielo,
tomar analgésico, esperar — esas tres frases pueden matar.

## Reglas de combinación

Si la paciente reporta múltiples síntomas, evaluar EL MÁS GRAVE y
clasificar por ahí.

Si la paciente reporta un síntoma ambiguo ("me siento mal"), el
agente pide aclaración rápida: ¿dónde te duele, fiebre, sangrado,
falta de aire? Y clasifica con lo que llega. Si la paciente no
puede dar más detalle (señal de gravedad), nivel 3 por default.

Si la paciente reporta dolor sin red flag pero menciona miedo
("tengo miedo de que sea algo", "esto no se siente normal"), el
agente respeta la inquietud y baja el umbral: ante duda, nivel 2.

## Lenguaje permitido vs prohibido

### En nivel 1 (normal)

| Permitido | Prohibido |
|---|---|
| "Está dentro de lo esperable a esa altura." | "No es nada, tranquila." |
| "Los cardenales pueden durar hasta 2 semanas." | "Eso ya tendría que haber pasado." |
| "Si aparece [red flag], me avisás." | (Omitir la lista de red flags.) |

### En nivel 2 (llamada)

| Permitido | Prohibido |
|---|---|
| "Lo que describís necesita que la doctora lo vea." | "Es normal, no te preocupes." |
| "Te agendo control para mañana." | "Vamos a esperar a ver si pasa." |

### En nivel 3 (urgencia)

| Permitido | Prohibido |
|---|---|
| "Andá AHORA a [hospital]." | "Tomá un paracetamol y avisame en una hora." |
| "Esto necesita evaluación inmediata." | "Está dentro de lo normal." |
| "Estoy avisando a la doctora ahora mismo." | "Vamos viendo." |

## Verificación interna del agente

Antes de responder a un reporte de síntomas post-procedimiento, el
agente revisa:

1. ¿La paciente menciona alguno de los red flags del nivel 3? →
   urgencia inmediata, sin más conversación.
2. ¿La paciente tuvo procedimiento en los últimos 30 días? Confirmar
   con `client.get_history` o memoria de la paciente — el contexto
   importa.
3. ¿El síntoma está dentro de la ventana clínicamente normal del
   procedimiento que tuvo? → nivel 1.
4. ¿El síntoma está fuera de la ventana normal pero sin signos de
   urgencia? → nivel 2, agendar control.
5. Ante duda entre dos niveles → elegir el más alto.
6. Si nivel 3 → llamar `escalate.escalate_to_human` antes de
   despedirme.

## Ejemplos completos

### ❌ Incorrecto

> Paciente: "Me operé BBL hace 2 días y me duele mucho la pierna
> izquierda. Está caliente."
> Agente: "Es normal en los primeros días, la zona está inflamada.
> Tomá un paracetamol y aplicá frío. Si mañana no mejora, escribime."

Catástrofe potencial: dolor unilateral severo con calor en miembro
inferior post-BBL es sospecha de TVP. Esperar puede matar.

### ✅ Correcto

> Paciente: "Me operé BBL hace 2 días y me duele mucho la pierna
> izquierda. Está caliente."
> Agente: "Lo que describís puede ser una trombosis venosa — no
> puedo asegurarlo por chat, pero necesita evaluación AHORA, no
> puede esperar. Por favor andá ya a
> {tenant.surgery_referral_hospital} — el teléfono de emergencia
> es {tenant.surgery_referral_phone}. Si podés, que alguien te
> lleve. Yo le aviso a {clinical.titular_name} en este momento."
> Agente: *(llama `escalate.escalate_to_human` con motivo:
> "post-BBL día 2 — dolor unilateral severo MI izquierdo con
> calor — sospecha TVP — urgencia derivada a CMDLT")*
> Agente: *(llama `operator.consult_owner`
> con urgency=high, mensaje a Dra. Hurtado)*

### ❌ Incorrecto

> Paciente: "Hace 4 días me hice peeling y todavía tengo la cara
> roja."
> Agente: "Eso es preocupante, te derivo a urgencia."

Sobre-escalación. Eritema 4 días post-peeling superficial está en
nivel 1. Mandar a urgencia genera ansiedad innecesaria y desgasta
la confianza en el agente.

### ✅ Correcto

> Paciente: "Hace 4 días me hice peeling y todavía tengo la cara
> roja."
> Agente: "Lo que describís entra en lo normal — el eritema tras
> peeling puede durar 3 a 5 días, a veces más si tu piel reactiva.
> Seguí con las indicaciones: humectación, fotoprotector SPF 50
> obligatorio, evitar sol directo, no exfoliar. Si en los próximos
> días aparece dolor que crece, ampollas, o secreción, me escribís
> sin dudar. ¿Cómo lo notás vos, te molesta mucho o más estético?"
