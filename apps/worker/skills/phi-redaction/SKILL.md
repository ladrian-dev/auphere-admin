---
name: phi-redaction
description: Disciplina del agente sobre qué información clínica personal puede escribir en memoria (memory tool) y en logs persistidos, y qué debe redactar o evitar. Pensada para el vertical estético pero portable a cualquier vertical regulado (dental, fertilidad, psicología, etc.). Surface this skill on any intent que pueda terminar en write a `agent_memories` o que persista un mensaje del paciente con contenido clínico literal.
version: 1
---

# PHI redaction — qué se guarda y qué no

PHI = Protected Health Information. Aunque Venezuela no tiene un
HIPAA local, la disciplina vale para los mercados donde Auphere se
expande (RGPD en España, ISP en Chile, INVIMA en Colombia). Construir
con esta disciplina desde el piloto significa que el mismo agente se
porta a otros mercados sin reescritura.

Esta skill cubre dos superficies de escritura:

1. **Memory tool** (`agent_memories`): donde el agente persiste
   "lo que necesita recordar entre conversaciones".
2. **Mensajes persistidos** (`messages.body`): donde se guarda el
   contenido literal del intercambio para auditoría + búsqueda.

## Regla maestra

**Lo que vive a nivel tenant-wide no lleva nombres ni diagnósticos.
Lo que vive a nivel customer (`/memories/{customer_id}/`) puede
guardar preferencias, alergias declaradas y procedimientos previos,
pero NUNCA diagnósticos, medicación crónica, condiciones psiquiátricas
o detalles reproductivos sensibles.**

La memoria es para servir mejor a la paciente, no para construir un
expediente clínico. El expediente clínico vive en AgendaPro / EHR
del tenant, no en `agent_memories`.

## Dos niveles de scope

### Nivel 1 — `/memories/` tenant-wide

Lo que pertenece acá: políticas curadas por el operador, listas
canónicas de procedimientos, links a recursos.

Ejemplos válidos:
- `/memories/policies/cancellation.md` → texto de la política.
- `/memories/catalog/medspa_services.md` → lista de servicios.
- `/memories/scripts/post_inyectable_cuidados.md` → texto para
  reenviar tras inyectables.

**Prohibido a nivel tenant-wide**: cualquier mención de pacientes
individuales, sus condiciones, su historial. Si el operador escribe
algo así por error, la skill `escalation-policy` aplica para que el
agente lo flagueé.

### Nivel 2 — `/memories/{customer_id}/`

Lo que pertenece acá: información que esa paciente nos dio para
servirle mejor en futuras interacciones.

Ejemplos válidos:
- `/memories/{customer_id}/preferences.md`:
  - "Prefiere consultas de mañana"
  - "Trato formal (usar 'señora')"
  - "Comunica por WhatsApp, no por llamada"
- `/memories/{customer_id}/allergies.md`:
  - "Alérgica a lidocaína (declaró 2026-05-20)"
  - "Sin alergias declaradas"
- `/memories/{customer_id}/procedure_history.md`:
  - "Botox frente/entrecejo 2025-11-15"
  - "Consulta de rinoplastia 2026-03-10 — no concretó cirugía"

Ejemplos PROHIBIDOS incluso a nivel customer:
- "Tiene depresión / trastorno de ansiedad / TLP"
- "Toma sertralina 50mg, escitalopram 20mg, clonazepam por la noche"
- "Hizo 3 intentos de FIV el año pasado"
- "Sospecha de dismorfia corporal"
- "Está en pareja con un futbolista famoso"

La diferencia: alergia a lidocaína es necesaria para el servicio
seguro. Diagnóstico psiquiátrico no es necesario para agendar un
hydrafacial — la médica lo evalúa en consulta.

## Qué hacer con un mensaje del paciente que sí contiene PHI

Si la paciente escribe en chat: *"Tomo escitalopram 20mg, ¿puedo
hacerme Botox?"* — el contenido literal queda guardado en
`messages.body` (auditoría obligatoria de la conversación). El agente
NO altera ese mensaje.

Pero lo que el agente PERSISTE en memoria sobre esa paciente NO debe
duplicar el medicamento literal. Lo correcto:

- En memoria: "Declaró medicación psiquiátrica (2026-05-20). Confirmar
  con médica antes de proceder con cualquier procedimiento."
- En la respuesta al paciente: la skill `medical-claims-discipline`
  aplica — el agente NO opina sobre la interacción Botox–ISRS y
  deriva a consulta.

## Cómo escribir entradas de memoria

Cada write a `agent_memories` debería:

1. Resumir, no copiar literal.
2. Incluir la fecha de la declaración entre paréntesis.
3. Usar lenguaje neutro ("declaró", "comentó", "registró") en lugar
   de afirmaciones médicas ("tiene", "padece", "diagnóstico de").
4. Marcar lo que requiere confirmación del staff ("pendiente confirmar
   con médica").

### ❌ Mal escrito

```
/memories/{customer_id}/health.md:
La paciente es bipolar tipo 2, toma 600mg de carbonato de litio
diario y 200mg de lamotrigina. También está embarazada de 8 semanas
pero pidió que no se lo digamos a nadie en la clínica.
```

Problemas múltiples:
- Diagnóstico psiquiátrico literal (no necesario para el servicio).
- Medicación con dosis (no necesario).
- Embarazo (relevante clínicamente — debe estar) PERO marcado como
  secreto, lo que es imposible de cumplir con el equipo médico.

### ✅ Bien escrito

```
/memories/{customer_id}/clinical_alerts.md:
- Declaró medicación psiquiátrica crónica (2026-05-20). Confirmar
  con médica antes de cualquier procedimiento.
- Declaró embarazo (2026-05-20). Inyectables y otros procedimientos
  con principios activos quedan contraindicados hasta posparto y
  fin de lactancia. Tratamientos seguros: hydrafacial suave,
  faciales manuales.
- Pidió confidencialidad sobre el embarazo. Aclarar que el equipo
  médico necesita saberlo para servirla con seguridad — derivar
  a consulta para conversarlo.
```

## Cuándo el agente NO escribe a memoria

- Información ambigua o malentendida ("creo que dijo que toma algo").
- Suposiciones del agente ("seguramente tiene ansiedad por cómo
  escribe").
- Datos que la paciente declaró bajo presión o desplome emocional.
- Información de terceros (su madre, su pareja).
- Cuando la paciente declara explícitamente "esto no lo guardes".

En esos casos, el agente puede mencionar el dato en la respuesta del
turno actual pero NO lo persiste.

## Logs y auditoría

`messages.body` y `traces` se persisten igual — eso es no negociable
para auditoría y soporte. La disciplina aplica a `agent_memories` y a
los campos derivados que el agente controla (`appointment.notes`,
`customer.metadata`, etc.).

Si en algún momento se decide aplicar redacción al `messages.body`
también, se hace en pipeline antes del write, no en el agente. Esta
skill no cubre ese flujo.

## Verificación interna del agente

Antes de escribir a `agent_memories`, el agente revisa:

1. ¿Lo que voy a escribir es un dato necesario para servir mejor a
   esta paciente en futuras interacciones? Si no es claro → no lo
   escribo.
2. ¿Estoy a punto de escribir un diagnóstico literal, dosis, o
   condición psiquiátrica/reproductiva sensible? → reescribir en
   forma neutra ("declaró medicación psiquiátrica — confirmar con
   médica") o no escribir.
3. ¿La paciente pidió no guardar este dato? → respetar el pedido,
   pero aclararle que el equipo médico necesita conocer cualquier
   tema relevante para su seguridad.
4. ¿La escritura es a `/memories/` tenant-wide? → NUNCA debe
   incluir referencias a pacientes individuales.
5. ¿Estoy fechando la entrada? → siempre incluir fecha de
   declaración entre paréntesis.

## Ejemplo completo de flujo correcto

> Paciente: "Hola, quiero hacerme Botox la próxima semana. Te
> aclaro que tomo sertralina 100mg, fluoxetina 20mg, y bromazepam
> cuando estoy ansiosa."
>
> Agente: *(pre-screening confirma resto de datos)*
> Agente: *(memory write):*
> ```
> /memories/{customer_id}/clinical_alerts.md:
> - Declaró medicación psiquiátrica crónica (2026-05-26). Confirmar
>   con médico estético antes de proceder. No contraindica Botox
>   per se, pero requiere conversación clínica.
> ```
> Agente al paciente: "Anoté que tomás medicación psiquiátrica
> crónica para que el médico estético lo evalúe antes de aplicar.
> No es contraindicación absoluta, pero la doctora prefiere conversarlo
> con vos directo. ¿Te agendo la consulta?"
> Agente: *(llama `operator.consult_owner` para coordinar)*
