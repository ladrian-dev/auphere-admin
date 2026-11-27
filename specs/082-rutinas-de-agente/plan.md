# Implementation Plan: rutinas, lo que un agente hace a su hora

**Branch**: `082-rutinas-de-agente` | **Date**: 2026-11-27 | **Spec**: [spec.md](spec.md)

**Input**: Feature specification from `specs/082-rutinas-de-agente/spec.md`

## Summary

Dos tablas nuevas por cliente, un disparador en el scheduler, un tipo de trabajo más en la cola y **un turno de agente sin conversación**. Lo último es la única pieza que no tiene suelo: todo lo demás se apoya en algo que ya corre en producción.

1. **El modelo** (`schedules`, `schedule_runs`): la rutina y cada una de sus ejecuciones, por cliente, con RLS forzada y clave compuesta al agente. La ejecución guarda la instrucción con la que corrió, así el historial no miente cuando alguien edita la rutina.
2. **El turno sin cliente final** (`runtime/schedule_turn.py`): un bucle ReAct con el mismo `AgentBundle`, la misma política de operador, el mismo conocimiento y el mismo `dispatch` con lista blanca que el canal. Sin clasificador, sin enrutado por intención, sin burbujas y sin escalado, porque no hay nadie al otro lado. La lista de herramientas sale de `activations._load_tool_policy` y se le quitan dos cosas: las que exigen `conversation_id` y, mientras no exista la pregunta desde la consola, las que piden aprobación.
3. **El disparador** (`streams/schedule_dispatch_cron.py`): un barrido por vencimiento sobre `next_run_at`, no un recorrido por cliente. Crea la fila de la ejecución y encola el trabajo. El `UNIQUE (tenant_id, schedule_id, scheduled_for)` es lo que impide que dos réplicas disparen la misma.
4. **El dinero** (`source = "schedule"`, partida `schedules`, asiento `debit_schedule`): el medidor ya separa por origen y la bolsa ya cobra con `usage_ref` idempotente. Es ampliar tres listas y una migración de `CHECK`, no un mecanismo nuevo.
5. **La consola** (`/console/clients/{ref}/schedules`, página `/schedules`): lista, alta, detalle y la pestaña Rutinas de la ficha del agente.

## Technical Context

**Language/Version**: Python 3.11 (API, worker y MCP con uv). TypeScript con Next.js en la consola.

**Primary Dependencies**: FastAPI, SQLAlchemy async, Alembic, LangGraph solo para lo que ya existe del turno de canal, el registro MCP propio (`nexus_mcp`) y Redis para el stream de trabajos. **No entra ninguna dependencia nueva**: la aritmética de zonas horarias la da `zoneinfo`, de la biblioteca estándar.

**Storage**: PostgreSQL con RLS forzada. Dos tablas nuevas por cliente y una migración, la **0245**, que además amplía cuatro `CHECK` existentes: `ck_jobs_kind`, `ck_usage_source`, `ck_client_wallet_entries_kind` y el estado de los trabajos no se toca.

**Testing**: pytest.
- Integración de la API: `apps/api/tests/integration/schedules`.
- Unitarias del worker: `apps/worker/tests/unit` (el cálculo del siguiente disparo y el filtro de herramientas del turno).
- Aislamiento: `apps/api/tests/isolation/test_082_*.py`, más las suites estructurales que ya barren toda tabla por cliente (`test_21`, `test_22`, `test_43`), que recogen las dos tablas nuevas sin tocarlas.
- Consola: Vitest y Testing Library en `apps/console/src/__tests__`.
- La base es propia: `nexus_test_082`, Redis 12.

**Target Platform**: los servicios `api`, `runner` y `nexus-scheduler`. El disparador va en la familia del scheduler, que es singleton y ya envuelve cada tic en un advisory lock.

**Project Type**: web service multi-tenant con consola propia.

**Performance Goals**: el barrido no recorre clientes: lee de un índice parcial sobre `next_run_at` y despacha lo vencido. Con 10.000 rutinas activas, un tic tiene que resolverse en menos de 200 ms cuando no vence ninguna. La ejecución en sí hereda el plazo de la cola de trabajos.

**Constraints**: una ejecución no empieza pasada su ventana de gracia de una hora, ni aunque le queden intentos. El disparador no llama al modelo: solo crea filas y encola. Ninguna consulta del barrido ve datos de un cliente: el descubrimiento va por una función `SECURITY DEFINER` que devuelve identificadores y horas, nada más.

**Scale/Scope**: unos 14 ficheros de código y sus pruebas, más la página de la consola.

## Constitution Check

*PUERTA: se rellena antes de la Fase 0 y se vuelve a comprobar después del diseño.*

| # | Principio | ¿Cumple? | Prueba / justificación |
|---|---|---|---|
| I | Aislamiento entre tenants; `tenant_id` del contexto, nunca del llamante; whitelist exhaustiva | ☑ | **Garantía 1.** `schedules` y `schedule_runs` nacen con `FORCE ROW LEVEL SECURITY` y clave compuesta, y las recogen `test_21` (toda tabla por cliente tiene RLS), `test_22` (borrar un cliente no deja nada) y `test_43` (FORCE y claves compuestas). **Garantía 2.** La lista de herramientas del turno es la misma intersección de `activations.tool_policy`, más dos restas, nunca una suma: lo barre `test_082_schedule_turn_tools.py`. **Garantía 8.** Sin conversación no hay `conversation_id` que inyectar, así que toda herramienta que lo exija queda fuera por construcción, y `test_082_schedule_turn_has_no_end_customer.py` lo comprueba herramienta a herramienta sobre el registro entero. |
| II | Corte por superficie de confianza; no se abre una nueva sin agotar la actual | ☑ | Superficie `0`, la que ya está abierta. La ejecución corre en el mismo worker, con el mismo grafo de herramientas y el mismo proxy de modelos. No hay navegador, ni ejecución local, ni canal nuevo. |
| III | Lo leído es dato, nunca instrucción | ☑ | La instrucción de la rutina la escribe el partner en la consola y viaja como mensaje de operador, igual que la política del agente. Lo que devuelven las herramientas entra como resultado, nunca como instrucción. El turno no lee ninguna web. |
| IV | Acción `mutates` con aprobación durable; auditoría nombra a la persona | ☑, **y es la fila que hay que mirar con lupa** | Una rutina **no inventa permisos**: hereda el de la activación de cada conexión, que es la aprobación durable y la concedió una persona con nombre, registrada en `audit_log`. La lista cerrada de acciones que nunca son automáticas (borrar un cliente, rotar claves, apagar la revelación de IA) no la toca ninguna herramienta de agente. Además, en esta spec las conexiones puestas en «preguntar antes de escribir» no ofrecen sus escrituras al turno (requisito 5.1), así que lo único que escribe sin preguntar es lo que una persona puso expresamente en «leer y escribir». Cada escritura queda en `audit_log` con la rutina que la originó y quien la creó (requisito 13). |
| V | Estados honestos, incluido `parcial` y `bloqueado`; la ausencia se diseña | ☑ | `partial` es un estado de primera clase de la ejecución, no una etiqueta: una ejecución a la que le faltó una herramienta nunca aparece como hecha (requisitos 5.3 y 10.4). El cliente sin rutinas enseña qué es una rutina y cómo crear la primera, sin botones apagados (requisito 14.4). |
| VI | Por API `console.*`, nunca navegando la consola de Auphere | ☑ | No aplica: aquí no hay ningún agente operando la plataforma. |
| VII | Test primero; el criterio de aceptación es el test; nada de `skip` | ☑ | Cada criterio de la spec se cita en `tasks.md` y se ve en rojo antes de implementar. |
| VIII | Licencias leídas enteras | ☑ | Ninguna dependencia nueva. |
| IX | La KB es dueña del porqué; la spec enlaza a su nota | ☑ | **No hay nota, y es a propósito** *(Pedro, 2026-11-27)*: esta pieza se decidió trabajando, no en la KB. El porqué está en la tabla de decisiones de la spec y en el `research.md` de esta carpeta, con quién decidió cada cosa y cuándo. |

### Las tres puertas que `/speckit-tasks` comprueba

| Puerta | Respuesta | Tarea que la cubre |
|---|---|---|
| **Aislamiento** — ¿qué garantías toca? | **1** (dos tablas nuevas por cliente), **2** (la lista de herramientas del turno) y **8** (el turno no tiene cliente final, y se refuerza: ni siquiera hay conversación que inyectar). | `test_082_schedules_rls.py`, `test_082_schedule_turn_tools.py` y `test_082_schedule_turn_has_no_end_customer.py`, más `test_21`, `test_22` y `test_43`, que recogen las tablas nuevas al volver a correr. |
| **Licencias** — ¿qué dependencia nueva entra? | Ninguna. `zoneinfo` es de la biblioteca estándar. | — |
| **Medidor** — ¿qué gasta y dónde lo ve el partner? | **Modelo**. Cada ejecución es un turno de agente, medido por tokens con `source = "schedule"`, cobrado de la bolsa del cliente con el asiento `debit_schedule` y mostrado como partida `schedules`. El partner lo ve en dos sitios: sobre la bolsa del cliente dentro de Rutinas, y como partida propia en la pantalla de Consumo, junto a las otras cuatro (criterio 9.6). | La tarea del medidor, la de la partida en `usage_lines.py` y la de la columna en la pantalla de Consumo. |

## Project Structure

### Documentation (this feature)

```text
specs/082-rutinas-de-agente/
├── plan.md              # Este fichero
├── research.md          # Fase 0: lo que ya existe y las decisiones de diseño
├── data-model.md        # Fase 1: las dos tablas y lo que se amplía
├── quickstart.md        # Fase 1: cómo verlo funcionar en local
├── contracts/
│   └── console-api.md   # Fase 1: las rutas de consola
└── tasks.md             # Fase 2: lo produce /speckit-tasks, no este plan
```

### Source Code (repository root)

```text
apps/api/
├── alembic/versions/0245_schedules.py          # las dos tablas, los CHECK ampliados, la función del barrido
├── src/nexus_api/
│   ├── db/models/schedule.py                   # Schedule y ScheduleRun
│   ├── services/schedules/
│   │   ├── when.py                             # el siguiente disparo: función pura, con zona y cambio de hora
│   │   ├── service.py                          # alta, cambio, pausa, archivo y el estado efectivo
│   │   └── runs.py                             # crear la ejecución, cerrarla, el contador de fallos
│   ├── services/wallet/schedules.py            # charge_schedule, el molde de charge_tests
│   └── api/console/schedules.py                # las rutas de consola
└── tests/
    ├── integration/schedules/
    └── isolation/test_082_*.py

apps/worker/src/nexus_worker/
├── runtime/schedule_turn.py                    # el turno sin cliente final
├── jobs/handlers/schedule_run.py               # el tipo de trabajo nuevo
└── streams/schedule_dispatch_cron.py           # el barrido por vencimiento

apps/console/src/app/(console)/schedules/       # la página, el alta y el detalle
```

**Structure Decision**: no hay estructura nueva. Cada pieza cae donde ya vive su familia: los modelos y servicios en `nexus_api`, el turno en `runtime`, el manejador en `jobs/handlers` junto a los otros nueve, el barrido en `streams` junto a los demás crons, y la página en el grupo `(console)`. Las dos carpetas vacías que dejó una maqueta anterior en `apps/console/src/app/(console)/schedules/` se borran: no están en git y responden a un modelo que Pedro descartó.

## Fases

Las cinco historias de la spec, en orden, y cada una entregable sola.

| Fase | Historia | Qué entra | Qué se puede enseñar al acabar |
|---|---|---|---|
| **0** | — | La migración 0245, los modelos, el servicio del alta y las rutas de lectura y escritura. | Nada que ejecute. Es el suelo de las dos siguientes. |
| **1** | P1 | El turno sin cliente final, el manejador de la cola, el cobro y «Ejecutar ahora». | El partner escribe la instrucción, pulsa y lee la respuesta. Es lo que hoy se hace a mano. |
| **2** | P2 | `when.py`, `next_run_at`, el barrido y la ventana de gracia. | La misma rutina, repetida sola, a la hora del negocio. |
| **3** | P3 | El hilo del historial, el panel de consumo partido y la lista con sus filtros. | Lo que gasta un cliente en rutinas, defendible ante el cliente. |
| **4** | P4 | Los intentos, la pausa por fallos, la pausa heredada del agente y el tope. | Se puede dejar sola. |
| **5** | P5 | La campana y el correo. | No hace falta entrar a mirar. |

Las fases 0 y 1 son el trabajo de fondo. De la 2 en adelante son piezas que se apoyan en lo ya hecho, y cualquiera de ellas puede esperar sin que lo anterior deje de servir.

## Complexity Tracking

| Añadido | Por qué hace falta | Alternativa más simple, y por qué no |
|---|---|---|
| Función `SECURITY DEFINER` para descubrir lo vencido | El barrido tiene que mirar a todos los clientes a la vez, y con RLS una sesión sin cliente no ve nada. La función devuelve solo identificadores y horas, nunca contenido. | Recorrer cliente a cliente, como el cron de cobranza. Se descartó porque ese recorrido cuesta una consulta por cliente y por tic, y aquí los tics son por minuto, no por hora. |
| `next_run_at` materializado en la fila | Permite el barrido por índice y que dos réplicas no se pisen. | Calcular al vuelo en cada tic. Se descartó porque obliga a leer todas las rutinas activas en cada tic para saber cuáles vencen. |
| `schedule_runs.instruction` duplica el texto de la rutina | El requisito 15.2: el historial tiene que conservar la instrucción con la que se ejecutó. | Versionar la rutina en una tabla aparte. Se descartó por desproporcionado: el texto son 2.000 caracteres como mucho y se escribe una vez por ejecución. |
