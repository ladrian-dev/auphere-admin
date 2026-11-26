# Investigación: spec 080

La evidencia de producción está en la nota de KB `research/2026-11-26-beta-jemma-p0-p1.md`. Aquí van las decisiones de diseño.

## D1. ¿Desde cuándo cuenta una reserva del cliente para el freno?

- **Decisión:** desde `coalesce(conversations.context_from, conversations.attended_at)`, que es el inicio del ciclo actual. Cuenta si la reserva tiene un evento `created` o `moved` con `created_at` igual o posterior a ese instante y si su estado está en `LIVE_STATUSES`.
- **Por qué:**
  - `context_from` es el corte de la spec 064: lo pone la reapertura tras Resolver. Sin corte, el ciclo empieza en `attended_at`.
  - Mirar los eventos `created` y `moved`, en vez de `updated_at`, evita que una confirmación del cliente o un cambio de nota renueve una cita vieja.
  - La agenda manda: si la reserva se canceló después, ya no está viva y no cuenta.
- **Alternativas descartadas:**
  - Toda reserva viva y futura del cliente: «quedó reservada» quedaría respaldado por una cita de hace un mes. Para mantener una cita ya existe `reservas.list_mine`.
  - Atar la reserva a la conversación cuando se crea desde la consola: la reserva se hace desde la agenda, que no sabe de qué conversación viene, y necesitaría cambios de interfaz fuera de alcance.

## D2. ¿De dónde sale el cliente?

- **Decisión:** de `conversations.customer_id`. Se lee en la misma consulta que `attended_at` y `context_from`, dentro de `tenant_scoped_session`.
- **Por qué:** es el cliente que el servidor resolvió al persistir el entrante (garantía 8). El freno no recibe argumentos del modelo.
- **Sin cliente o sin inicio de ciclo:** solo cuenta lo de hoy (requisito 1.5). `conversations.customer_id` no admite nulos, así que en la práctica toda conversación tiene cliente. El caso sin cliente es el de un turno sin conversación, que ya devuelve «no respalda». Una reserva sin cliente (hecha sin teléfono) no es de nadie y no respalda ninguna conversación; lo cubre T002.

## D3. ¿Qué herramientas ganan `fallback` y `escalate`?

- **Decisión:** las nueve `reservas.*` de la categoría `book`: `services`, `find_slots`, `create`, `list_mine`, `reschedule`, `cancel`, `confirm_attendance`, `join_waitlist` y `answer_offer`.
- **Qué no entra:**
  - Las `booking.*` heredadas y las `client.*`: el caso observado es Reservas.
  - Los conectores en `escalate`: la prueba `test_connector_tool_excluded_on_escalate` lo fija como diseño y no se toca.
- **Por qué:** el catálogo (`reservas.services`) y las citas del cliente (`reservas.list_mine`) son lo mínimo para comprobar. Reservar, mover y cancelar son lo mínimo para seguir. El agente decide con las reglas de su negocio: el prompt de Jemma dice «Pedir otra profesional no cuenta».
- **Coste:** en Jemma, un turno `book` lleva unos 12.300 tokens de entrada y uno `fallback`, unos 9.900. La diferencia (unos 2.400 tokens) va en la parte cacheable del prompt.

## D4. Contrato de `find_slots` sin fecha

- **Decisión:**
  - `date` pasa a ser opcional en la entrada.
  - Sin fecha, la salida lleva `date: null`, `searched_from` y `searched_to`, y en cada `SlotOut` su `date` y su `weekday` (`monday` … `sunday`).
  - `too_soon` lleva `YYYY-MM-DD HH:MM`.
  - El tope es de **6 horarios**.
  - Con fecha, la forma no cambia: `SlotOut.date` y `SlotOut.weekday` son nulos y no se emiten (`exclude_none`).
- **Tope de 6:** cubre «los tres primeros», que es lo que piden las instrucciones habituales, más margen para varios profesionales en la misma hora, sin inflar la respuesta (cada horario lleva su lista de personas).
- **Día de la semana:** con Luna, el día lo calculaba el modelo. Darlo hecho evita un error y es barato.
- **Días recorridos:** se recorre día a día, desde `ctx.today(now)` hasta `today + agent_max_days_ahead`.
  - Se salta un día si `ctx.day_ranges(day)` está vacío.
  - En Servicios se llama a `services_free` y en Aforo a `capacity_day` + `capacity_fit`, como en la búsqueda con fecha.
  - Se para al llegar a 6.
- **Errores de entrada:** la validación del servicio y del profesional (`_pick`), `not_bookable`, `no_staff` y `too_large` van antes del recorrido y devuelven lo mismo que con fecha.
- **Sin nada libre en la ventana:** `why_closed="none_in_window"`, `slots=[]` y `closed=false` (el negocio no está cerrado: no hay hueco).
- **Alternativas descartadas:**
  - Que el modelo pase un rango: le seguiría tocando adivinar.
  - Agrupar por día (`days: [{date, slots}]`): cambia más la forma y no aporta frente a llevar `date` en cada horario.
  - Leer la ocupación de todo el rango de una vez en `core.py`: lo usan otras sesiones (082, 083) y el peor caso medido no lo exige (T008).

## D5. Descripción de la herramienta

- **Decisión:** la descripción dice que se llame **sin `date`** cuando el cliente no da día o pide lo antes posible, y con `date` cuando nombra un día. `first_fit` solo se menciona para Aforo.
- **Por qué:** con Luna el modelo eligió mañana en 2 de 2 casos. La instrucción tiene que estar en la herramienta, no en cada prompt de partner.

## D6. Cancelación hecha por el agente

- **Decisión:** `cancel_booking(..., by="customer", actor=Actor("agent", <nombre del agente>))`. El nombre sale como en `reservas.create`: `Agent.name` del agente del turno.
- **Por qué:**
  - `by` decide la política y no cambia: no se avisa al cliente porque la pidió él, y sí al negocio si es para hoy.
  - `actor` es quien la ejecutó, y es lo que leen el historial (`views.events_out`) y el informe de la 083.
- **Datos anteriores:** no se reescriben (requisito 4.2). La 083 explica cómo leerlos.

## D7. Playground y pruebas del agente

- **Decisión:** `simulation/registry._find_slots` acepta no recibir `date` y aplica la misma lógica sobre `world.slots(day, …)`, desde `world.now_at`, con el mismo tope y la misma forma (`FindSlotsOutput`).
- **Por qué:** el freno y las pruebas leen la forma de verdad. Si la simulación diera otra cosa, el modelo aprendería un contrato distinto en el Playground.
