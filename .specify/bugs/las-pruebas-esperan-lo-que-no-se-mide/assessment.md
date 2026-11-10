# Bug Assessment: las pruebas esperan lo que nadie mide, y el juez no tiene la ficha

- **Slug**: las-pruebas-esperan-lo-que-no-se-mide
- **Created**: 2026-11-05
- **Source**: pasada real en staging tras desplegar `6169814a`, agente «Prueba del constructor» de Jemma's Hair
- **Verdict**: valid
- **Severity**: high

## Symptom

Agente recién creado, 8 pruebas: pasan 2. Las cuatro que escribió el constructor fallan 0 de 3 con el agente respondiendo bien: «¿También hacen cortes para hombres?» contesta lo que dice la ficha y falla con `/status: se esperaba "answered" y quedó null; /handoff: se esperaba false y quedó null`.

Dos del sector salen «Inestable» y «No sé» con respuestas correctas. Y la pantalla dice «Nunca pasa a una persona por su cuenta» en un agente cuya descripción pide lo contrario.

## Reproduction

`apps/api/tests/unit/test_tests_check_what_is_measured.py` y `apps/api/tests/integration/builder/test_tests_check_what_is_measured.py`.

## Root cause

- El prompt del constructor y el de las guías generadas decían `"expected_state": object`, sin decir qué claves existen. El modelo las inventa (`status`, `handoff`, `appointment_created`, `payment_confirmed`) y `World.final_state` no las tiene: `check_state` da rojo siempre. Una crítica en rojo cierra la puerta.
- El juez recibía la conversación y los criterios, y no la ficha. «Dice el horario de la ficha, sin inventar» solo puede salir «No sé» o variar entre pasadas.
- `escalation.triggers` también estaba sin vocabulario en el prompt, y el parser tiraba lo que no conocía. Un disparador en palabras se perdía entero.
