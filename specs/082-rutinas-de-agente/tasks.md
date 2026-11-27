# Tareas: spec 082, rutinas, lo que un agente hace a su hora

**Entrada**: [spec.md](spec.md), [plan.md](plan.md), [research.md](research.md), [data-model.md](data-model.md) y [contracts/](contracts/).

**Reglas**:
- Primero la prueba: cada prueba se ve en rojo antes de su implementación.
- Base propia: `nexus_test_082`, Redis 12.
- Solo se corren las pruebas de lo tocado, nunca la suite completa.
- `[P]` = se puede hacer en paralelo con la anterior.
- Cada tarea cita sus requisitos. Una tarea sin trazabilidad no entra.

**Estado** (2026-11-27): T001 a T014 entregadas en el PR #74, rama
`082-rutinas-de-agente`, sin fusionar todavía. **T015 va a medias**: la elección
de herramientas está hecha y probada, el bucle que llama al modelo llega con el
manejador de la cola (T017). 70 pruebas en verde.

## Fase 1: Preparación

- [x] **T001** Exporta `NEXUS_DATABASE_URL` (`…/nexus_test_082`) y `NEXUS_REDIS_URL` (`…/12`), y comprueba que no hay ningún pytest vivo. Si las dependencias del worktree no están, `uv sync --extra dev` en `apps/api` y en `apps/worker`.
- [x] **T002** [P] Borra `apps/console/src/app/(console)/schedules/[id]/` y `.../new/`, las dos carpetas vacías que dejó una maqueta anterior. No están en git y responden a un modelo descartado.

## Fase 2: Fundación — el modelo (bloquea todo lo demás)

- [x] **T003** **Garantía 1.** Prueba de aislamiento `apps/api/tests/isolation/test_082_schedules_rls.py`, en rojo:
  - `schedules` y `schedule_runs` tienen `FORCE ROW LEVEL SECURITY` y su política por `tenant_id`.
  - Una sesión con el cliente A no ve ni una fila del cliente B, ni leyendo ni escribiendo.
  - La clave compuesta rechaza una rutina que apunte al agente de otro cliente.
  - Borrar un cliente no deja rutinas ni ejecuciones.
  - `due_schedules` devuelve solo identificadores y horas, nunca instrucción ni respuesta.

  _Requisitos: 1.1, 1.3, 1.4_
- [x] **T004** Migración `apps/api/alembic/versions/0244_schedules.py`: las dos tablas con sus `CHECK` e índices (incluido el parcial sobre `next_run_at`), los cuatro `CHECK` ampliados (`ck_jobs_kind`, `ck_usage_source`, `ck_client_wallet_entries_kind` y el del asiento), y la función `due_schedules` como `SECURITY DEFINER`. T003 en verde.

  _Requisitos: 1.1, 3.1, 7.7, 12.1_
- [x] **T005** [P] Modelos `apps/api/src/nexus_api/db/models/schedule.py` (`Schedule`, `ScheduleRun`), exportados en `models/__init__.py`.

  _Requisitos: 1.1, 15.2_
- [x] **T006** Vuelve a correr `tests/isolation/test_21_rls_covers_every_tenant_table.py`, `test_22_tenant_delete_leaves_nothing.py` y `test_43_force_and_composite_fk_sweep.py`: las dos tablas nuevas tienen que entrar solas en esos barridos.

  _Requisitos: 1.1, 1.4_
- [x] **T007** Unitarias de `apps/worker/tests/unit/test_082_when.py`, en rojo. Sobre `when.py`, sin base de datos:
  - diaria, semanal con varios días, mensual del 1 al 28 y una sola vez;
  - la hora local que no existe el día que el reloj se adelanta corre a la primera que sí existe;
  - la hora que ocurre dos veces se ejecuta una sola vez;
  - una rutina de `America/Santiago` a las 09:00 cambia de hora UTC entre invierno y verano austral;
  - cambiar la zona del negocio mueve las próximas;
  - `once` con la fecha ya pasada no devuelve ninguna.

  _Requisitos: 3.2, 3.4, 3.5, 3.7, 3.8_
- [x] **T008** Implementa `apps/api/src/nexus_api/services/schedules/when.py`: función pura con `zoneinfo` que, dada la periodicidad, la hora local y la zona, devuelve las próximas ejecuciones en absoluto. T007 en verde.

  _Requisitos: 3.2, 3.4, 3.5, 3.7_
- [x] **T009** Integración `apps/api/tests/integration/schedules/test_crud.py`, en rojo: alta con sus validaciones (`name_required`, `instruction_required`, `weekdays_required`, `day_of_month_out_of_range`, `limit_reached`), cambio, pausa a mano, archivar, restaurar en pausa, y que no exista `DELETE`.

  _Requisitos: 2.1, 2.2, 2.3, 3.3, 12.1, 15.1, 15.3, 15.4, 15.5, 15.6_
- [x] **T010** Implementa `services/schedules/service.py`: alta, cambio, pausa y reanudación manual, archivar y restaurar, el tope de veinte activas, y **el estado efectivo** cruzando el de la fila con el del agente y el saldo de la bolsa. T009 en verde.

  _Requisitos: 2.1, 8.1, 8.3, 12.1, 15.1, 15.3, 15.4, 15.5, 15.6_
- [x] **T011** [P] Permisos `schedules:read` y `schedules:write` en `core/console_auth.py`, con los mismos roles que `agents:read` y `agents:write`, y su caso en las pruebas de permisos.

  _Requisitos: 11.1, 11.2, 11.3_
- [x] **T012** Rutas de `apps/api/src/nexus_api/api/console/schedules.py` según [contracts/console-api.md](contracts/console-api.md): lista con filtros y cuentas, alta, detalle, cambio, pausa, reanudar, archivar, restaurar y `preview`. La consola del cliente no recibe ninguna.

  _Requisitos: 1.2, 2.4, 2.5, 3.6, 11.4, 14.1, 14.2, 14.3_

## Fase 3: Historia 1 — escribirlo una vez y ver la respuesta (P1)

- [x] **T013** **Garantía 8.** Prueba de aislamiento `apps/api/tests/isolation/test_082_schedule_turn_has_no_end_customer.py`, en rojo. Barre el registro entero de herramientas: ninguna que tenga `conversation_id` entre sus obligatorios llega a ofrecerse en un turno de rutina, y ningún argumento del eje de cliente final queda al alcance del modelo. Una herramienta nueva con esa forma pone la suite en rojo.

  _Requisitos: 4.3, 4.4_
- [x] **T014** [P] **Garantía 2.** Unitaria `apps/worker/tests/unit/test_082_schedule_turn_tools.py`, en rojo:
  - la lista del turno es la intersección de siempre, nunca una suma;
  - «solo leer» deja solo lectura, «leer y escribir» deja escribir;
  - «preguntar antes de escribir» deja fuera sus escrituras y las anota en `withheld`;
  - una conexión sin activación no aporta nada.

  _Requisitos: 4.2, 4.5, 5.1, 5.2_
- [ ] **T015** Implementa `apps/worker/src/nexus_worker/runtime/schedule_turn.py`: bucle ReAct con el `AgentBundle` de la versión publicada, la política de operador y el conocimiento, el `dispatch` con lista blanca y el tope de iteraciones. Sin clasificador, sin enrutado por intención, sin formateo de burbujas y sin escalado. La lista de herramientas sale de `activations._load_tool_policy` con las dos restas. T013 y T014 en verde.

  **A medias.** `select_tools` y `tools_for_routine` están hechas y probadas: es la parte que sostiene las garantías 2 y 8. Falta el bucle que llama al modelo, que necesita el resolutor de modelo, la puerta de presupuesto y la medición, y se escribe junto a T017.

  _Requisitos: 4.1, 4.2, 4.3, 4.4, 4.5, 4.7_
- [ ] **T016** Integración `apps/api/tests/integration/schedules/test_run.py`, en rojo: «Ejecutar ahora» deja la ejecución con su respuesta, lo que usó, lo que tardó y lo que costó; una herramienta retenida la deja en `partial` con `withheld` relleno; la bolsa vacía devuelve `409 bag_empty`.

  _Requisitos: 4.7, 5.3, 6.1, 6.2, 6.4_
- [ ] **T017** Manejador `apps/worker/src/nexus_worker/jobs/handlers/schedule_run.py` y el tipo `schedule_run` en `JOB_KINDS` y en el registro. Corre el turno, cierra la fila de la ejecución y publica lo medido. **El efecto consecuente, una sola vez por ejecución**, con el mismo mecanismo que ya usa el turno de canal.

  _Requisitos: 4.6, 6.1, 7.1_
- [ ] **T018** **Medidor.** `services/wallet/schedules.py` con `charge_schedule`, calcado de `charge_tests`: cobra de la bolsa con el asiento `debit_schedule` y la `usage_ref` de la ejecución, **no suma al tope del agente**, y pausa a los agentes si la bolsa llega a cero. Más la entrada `"schedule": "schedules"` en `USAGE_LINE_BY_SOURCE`.

  _Requisitos: 9.1, 9.2, 9.4_
- [ ] **T019** [P] Integración `test_run_charges.py`: la misma ejecución no se cobra dos veces, y el asiento cae en `debit_schedule` y no en `debit_turn`.

  _Requisitos: 9.1, 9.2_
- [ ] **T020** Rutas `POST …/{id}/run` y `POST …/agents/{agent_id}/schedules/try`, las dos con `202`. La segunda ejecuta sin crear rutina.

  _Requisitos: 6.1, 6.2, 6.3_
- [ ] **T021** Consola: la página `/schedules` con elegir cliente, la lista y el panel lateral del alta, con el nombre de tope 60, la instrucción con su contador de 2.000 y las próximas ejecuciones de `preview`. «Probar ahora» y «Ejecutar ahora».

  _Requisitos: 2.1, 2.2, 2.3, 2.4, 2.5, 3.6, 6.1, 6.3, 14.1_

## Fase 4: Historia 2 — que se repita sola, a la hora del negocio (P2)

- [ ] **T022** Integración `apps/api/tests/integration/schedules/test_dispatch.py`, en rojo: con el reloj en la hora del negocio nace una ejecución con `trigger: "schedule"`, con el reloj en otra zona no nace ninguna, `next_run_at` queda en la siguiente, y una rutina `once` queda sin próxima al terminar.

  _Requisitos: 3.2, 3.8_
- [ ] **T023** [P] Unitaria del disparo doble: dos barridos simultáneos sobre la misma rutina crean una sola ejecución, por el `UNIQUE (tenant_id, schedule_id, scheduled_for)`.

  _Requisitos: 7.7_
- [ ] **T024** Implementa `apps/worker/src/nexus_worker/streams/schedule_dispatch_cron.py` y regístralo en la familia del scheduler en `bootstrap.py`. Lee lo vencido con `due_schedules`, abre una transacción por ejecución con su cliente puesto, crea la fila y encola el trabajo. No llama al modelo. T022 y T023 en verde.

  _Requisitos: 3.2, 7.7_
- [ ] **T025** `next_run_at` se recalcula al guardar, al cambiar la rutina, al cerrar cada ejecución y cuando cambia la zona del negocio.

  _Requisitos: 3.7, 3.8_

## Fase 5: Historia 3 — el historial y lo que cuesta (P3)

- [ ] **T026** Integración `test_runs_history.py`, en rojo: el hilo pagina por cursor con el más reciente primero, cada ejecución trae la instrucción con la que corrió, y editar la rutina no toca las ya hechas.

  _Requisitos: 15.2_
- [ ] **T027** Ruta `GET …/{id}/runs` y la lectura del detalle.

  _Requisitos: 4.7_
- [ ] **T028** **Medidor, segunda parte.** La partida `schedules` en `services/wallet/usage_lines.py`: entrada en `LINES`, `PAYER` a `client_bag` y su asiento en `_BAG_ENTRY`. Con su prueba de que la suma de las partidas cuadra con lo cobrado de la bolsa.

  _Requisitos: 9.3, 9.6_
- [ ] **T029** [P] La partida en la pantalla de Consumo del partner, junto a Conversaciones, Construcción y pruebas, Meta y Companion.

  _Requisitos: 9.6_
- [ ] **T030** Consola: el hilo del detalle, una tarjeta por ejecución con su respuesta, lo que usó y lo que costó, y el panel de consumo partido en conversaciones y rutinas sobre la bolsa. Importes con el componente `Money`, «12,80 US$».

  _Requisitos: 9.3, 9.5_
- [ ] **T031** [P] Consola: la lista con sus filtros por agente y por estado con sus cuentas, el «ninguna coincide» y el estado vacío de un cliente sin rutinas.

  _Requisitos: 14.2, 14.3, 14.4, 14.6_

## Fase 6: Historia 4 — que no se desmande (P4)

- [ ] **T032** Integración `test_failures.py`, en rojo:
  - un intento que falla lanza otro, hasta tres, y los tres cuelgan de **una sola** ejecución;
  - no se lanza ningún intento pasada la hora de gracia, queden o no;
  - tres **ejecuciones** seguidas fallidas pausan la rutina con su motivo, y el contador no cuenta intentos;
  - una ejecución que no llegó a empezar en su hora queda `skipped` con su motivo, nunca tarde.

  _Requisitos: 7.1, 7.2, 7.3, 7.4, 7.5, 7.6_
- [ ] **T033** Implementa los intentos y la ventana de gracia en `services/schedules/runs.py` y en el disparador. Cada intento es un trabajo nuevo. T032 en verde.

  _Requisitos: 7.1, 7.2, 7.3, 7.4, 7.6_
- [ ] **T034** [P] Integración `test_agent_state.py`, en rojo y luego en verde: un agente que deja de atender deja sus rutinas sin ejecutarse con el motivo escrito, vuelve a atender y vuelven solas, una rutina creada para un agente en pausa nace en pausa, y la pausa manual no la deshace el sistema. La bolsa vacía las para y el saldo las devuelve.

  _Requisitos: 8.1, 8.2, 8.3, 8.4, 15.3_
- [ ] **T035** El motivo de la pausa, visible en la lista sin abrir la rutina.

  _Requisitos: 14.5_

## Fase 7: Historia 5 — que te llegue sin entrar a mirar (P5)

- [ ] **T036** Los cuatro avisos nuevos en `NotificationKind` (`schedule.run.done`, `schedule.run.partial`, `schedule.run.failed`, `schedule.paused`) con su texto en el catálogo, y la emisión al cerrar cada ejecución. Una parcial o una fallida lo dicen, y no se anuncian como hechas.

  _Requisitos: 10.1, 10.2, 10.4_
- [ ] **T037** [P] El correo a quien creó la rutina cuando lo tiene encendido: aviso con enlace a la respuesta, por la plantilla genérica.

  _Requisitos: 10.3_

## Fase 8: Cierre

- [ ] **T038** **Auditoría.** Una escritura hecha por una rutina deja en `audit_log` la rutina que la originó y la persona que la creó, distinguible de la misma acción hecha en una conversación. El alta, la pausa, la reanudación y el archivo también.

  _Requisitos: 13.1, 13.2, 13.3_
- [ ] **T039** [P] Retención del historial: la misma ventana que los mensajes, sin tocar lo medido.

  _Requisitos: 12.2, 12.3_
- [ ] **T040** El recorrido de [quickstart.md](quickstart.md), de punta a punta, contra la base de la feature.

  _Requisitos: todos los de P1 y P2_
- [ ] **T041** Documentación viva: `docs/agentes.md` y `docs/console.md` recogen qué es una rutina, de qué bolsa sale y qué no puede hacer.

  _Requisitos: 2.4, 9.1_

## Dependencias

- La **fase 2** bloquea todo. Dentro de ella, T004 bloquea a T005 y a T009, y T008 bloquea a T012 (el `preview` necesita el cálculo).
- La **fase 3** es la única con trabajo de fondo: T015 es la pieza que no tiene suelo y de la que cuelgan las fases 4 a 7.
- Las **fases 4 a 7** son independientes entre sí: cualquiera puede esperar sin que lo anterior deje de servir.
- Dentro de cada fase, las pruebas van antes que su implementación, sin excepción.

## Lo que esta spec deja marcado como provisional

T014 y T015 implementan el criterio 5.1: mientras no exista la pregunta desde la consola, lo que pide aprobación se trata como bloqueado y la ejecución lo escribe. **Cuando llegue esa spec, esas dos tareas se revisan y la resta desaparece.** No es una decisión de producto: es un andamio con fecha.
