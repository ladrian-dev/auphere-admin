---
name: pre-op-screening
description: Cuestionario obligatorio que el agente del vertical estético ejecuta ANTES de agendar un inyectable o una consulta quirúrgica. Cinco preguntas que detectan contraindicaciones absolutas (embarazo, lactancia) y antecedentes que la médica necesita conocer antes de aceptar a la paciente (anticoagulantes, isotretinoína reciente, queloides, edad). Surface this skill on any intent that ends en booking de procedimiento medspa o consulta pre-quirúrgica.
version: 1
---

# Pre-op screening — cuestionario obligatorio antes de agendar

Esta skill es el filtro de seguridad clínica del vertical
`aesthetic_clinic_v1`. Materializa la regla 5 del system prompt.

Antes de llamar `booking.create_appointment` para un inyectable o
una consulta pre-quirúrgica, el agente DEBE haber recibido respuesta
a las cinco preguntas de screening. No es opcional. No es "se lo
preguntamos cuando llegue". Si la paciente embarazada agenda Botox
y se entera en clínica, ya gastamos su tiempo y nuestra disponibilidad
y posiblemente perdimos a una paciente con respuesta empática.

## La regla

**El agente NO confirma una cita de inyectable, láser, peeling
químico, criolipólisis, radiofrecuencia, o consulta de cirugía
estética sin antes haber tomado y registrado las cinco respuestas.**

Para hydrafacial, depilación láser cosmética suave, y faciales
manuales, el screening completo no es obligatorio — solo edad y
embarazo. Para todo lo demás, las cinco preguntas.

## Las cinco preguntas

Hacelas en una sola interacción si la paciente no las disparó antes,
en tono conversacional — no como interrogatorio. Idealmente en un
solo turno: una lista breve, esperar respuesta, registrar.

1. **¿Sos mayor de 18?**
2. **¿Estás embarazada o amamantando?**
3. **¿Tomás anticoagulantes actualmente?** (warfarina, aspirina diaria,
   clopidogrel, dabigatrán, rivaroxabán, apixabán, etc.)
4. **¿Tomaste isotretinoína en los últimos 6 meses?** (Roacutan,
   Acnotin, Isoacne, Curacné, similares — tratamiento de acné severo)
5. **¿Tenés antecedente de queloides o cicatrización anómala?**

Pregunta extra para procedimientos inyectables o láser:

6. **¿Tenés alguna alergia conocida a fármacos, anestésicos o
   componentes cosméticos?** (lidocaína, látex, AINEs, etc.)

## Cómo interpretar cada respuesta

### Edad < 18 → consentimiento obligatorio (regla 6 del prompt)

Si la paciente declara menos de 18 años, NO agendás hasta confirmar
que asistirá con padre/madre o tutor con consentimiento escrito.
La skill `medical-claims-discipline` aplica también — no improvisás
"bueno, pero con autorización de tu mamá te agendo igual".

Respuesta tipo: *"Para menores de edad necesitamos consentimiento
escrito de tu mamá, papá o tutor. ¿Podés venir acompañada de alguno
de ellos a la consulta inicial? Así lo conversamos todos juntos
con la doctora."*

### Embarazo / lactancia → contraindicado para inyectables

Inyectables (toxina botulínica, ácido hialurónico, bioestimuladores),
peelings con retinoides o profundos, láser ablativo, sedación,
isotretinoína — todos contraindicados.

Lo que SÍ es seguro en embarazo (con criterio médico): hydrafacial
suave sin retinoides, faciales manuales, masaje, depilación con
cera/manual (no láser).

Respuesta tipo: *"Felicitaciones por el embarazo. Los inyectables
y la mayoría de tratamientos con principios activos no se aplican
durante embarazo ni lactancia, por precaución. Lo que sí podemos
hacer ahora son tratamientos suaves de cuidado facial (hydrafacial
sin retinoides, faciales manuales). ¿Querés que te agende uno, o
preferís retomar los tratamientos después?"*

NO escala — refusa con alternativa. El agente puede ofrecer la
opción segura.

### Anticoagulantes → derivar a consulta

Pacientes en anticoagulación crónica tienen mayor riesgo de
hematoma con inyectables y láser. NO contraindicado absoluto pero
requiere evaluación médica antes de proceder.

Respuesta tipo: *"Tomar [anticoagulante] no significa que no
podamos hacer el procedimiento, pero la doctora necesita evaluarlo
en consulta porque hay que ajustar protocolo. ¿Te agendo la
consulta?"*

Registrá la respuesta en memoria del paciente para que la médica
lo vea antes de la cita.

### Isotretinoína últimos 6 meses → contraindicado para láser ablativo y peelings medios/profundos

La isotretinoína altera la cicatrización; los procedimientos
ablativos en pacientes que la tomaron recientemente pueden generar
cicatrices anómalas. Recomendación SVCPREM/ASPS: esperar 6 meses
desde la última dosis para procedimientos ablativos.

Respuesta tipo: *"Como tomaste isotretinoína recientemente, hay
algunos procedimientos (láser CO2, peelings medios o profundos)
que recomendamos esperar 6 meses desde la última dosis. Para
otros (hydrafacial, faciales) no hay restricción. ¿Cuál te
interesa específicamente? Así te oriento."*

### Queloides → derivar a consulta para cirugías y láser ablativo

Antecedente de queloide implica riesgo de cicatrización
hipertrófica. No contraindica todo, pero requiere conversación
clínica especialmente para cirugía estética y láser.

Respuesta tipo: *"Tener antecedente de queloides es algo importante
que la doctora va a querer conversar antes de cualquier procedimiento
que deje cicatriz. Para inyectables y faciales no es un tema. ¿Qué
te interesa?"*

### Alergia declarada → registrá + escalá si es relevante

Alergia a lidocaína: muy frecuente y limita anestésica. Llamá
`operator.consult_owner` para que el staff defina la alternativa
ANTES de confirmar la cita.

Alergia a látex: relevante para cirugía con guantes; staff debe
saberlo.

Alergia a AINEs: relevante para manejo post-procedimiento.

Cualquier alergia → siempre se registra en
`/memories/{customer_id}/` con la skill `phi-redaction` aplicada.

## Cuándo NO repetir el screening

Si la paciente ya pasó el screening en una conversación previa y
las respuestas están en `client.get_history()` o
`/memories/{customer_id}/`, el agente NO vuelve a hacer las cinco
preguntas. Cita lo que sabe ("veo en tu historial que ya nos
contaste sobre la alergia a lidocaína") y, máximo, confirma que
nada cambió ("¿algo nuevo del último año que tengamos que tener
en cuenta?").

Esto vale incluso cuando la paciente vuelve después de meses — la
memoria por paciente persiste; el agente la usa.

## Verificación interna del agente

Antes de llamar `booking.create_appointment` para inyectable o
consulta quirúrgica, el agente revisa:

1. ¿Tengo respuesta a las 5 preguntas del screening? (revisar
   history del turn + `/memories/{customer_id}/`)
2. ¿Alguna respuesta es contraindicación absoluta (embarazo +
   inyectable)? → refusar con alternativa segura, NO agendar.
3. ¿Alguna respuesta requiere derivación al staff
   (anticoagulación crónica, alergia a anestésico, queloides +
   cirugía)? → llamar `operator.consult_owner` ANTES de agendar.
4. ¿Es menor de edad? → exigir consentimiento, NO agendar hasta
   confirmar acompañamiento.

Si las 4 son "no problema" → proceder con
`booking.create_appointment`.

## Ejemplo completo de flujo correcto

> Paciente: "Hola, quería hacerme ácido hialurónico en los labios."
>
> Agente: "¡Hola! Te ayudo. Antes de agendar, te hago un screening
> corto para confirmar que el procedimiento es seguro en tu caso.
> ¿Podés contarme:
>  - ¿Edad?
>  - ¿Estás embarazada o amamantando?
>  - ¿Tomás anticoagulantes (aspirina diaria, warfarina, otros)?
>  - ¿Tomaste isotretinoína en los últimos 6 meses?
>  - ¿Tenés antecedente de queloides?
>  - ¿Alguna alergia conocida (lidocaína, látex, fármacos)?"
>
> Paciente: "Tengo 29, no estoy embarazada, no tomo nada, sin
> isotretinoína, sin queloides. Pero soy alérgica a la lidocaína."
>
> Agente: *(registra alergia en `/memories/{customer_id}/lidocaine_allergy.md`
> vía memory tool)*
> Agente: *(llama `operator.consult_owner`
> con motivo: "paciente alérgica a lidocaína para AH labios — confirmar
> protocolo anestésico alternativo antes de agendar")*
> Agente: "Genial, todo en regla. Anoté la alergia a lidocaína —
> esa la confirmo con el médico estético antes de cerrar la cita
> para definir la anestésica alternativa. ¿Te puedo escribir en un
> rato cuando me responda?"
