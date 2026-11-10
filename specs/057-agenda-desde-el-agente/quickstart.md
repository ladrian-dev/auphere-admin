# Cómo comprobarlo

## En local

```bash
docker compose up -d
cd apps/api && uv run alembic upgrade head
```

Pruebas de lo tocado (la memoria del proyecto pide una suite de pytest a la vez):

```bash
cd apps/api && uv run pytest tests/isolation/test_057_agenda_from_agent.py tests/isolation/test_console_scope.py -x
cd apps/api && uv run pytest tests/unit -k "agenda or missing or gives_appointments or forbids_agenda" -x
cd apps/api && uv run pytest tests/integration -k "agenda or draft_job or turn_on" -x
cd apps/worker && uv run pytest tests/unit -k "agenda or hand_off or booking_brake or intent_tool_filter" -x
pnpm --filter console test -- agenda builder-new agent-connectors proposals missing
./scripts/verify.sh lint
```

Recorrido en la consola (`llm_use_inmemory`, sin proveedor):

1. Cliente nuevo sin Reservas. «Nuevo agente», descripción con «citas»: el interruptor sale
   encendido con su porqué y pide el modo, con «Por servicio y profesional» elegido.
2. Generar. En Acceso, Reservas está encendido y las personas del cliente siguen sin poder entrar.
   La v1 lleva las 9 `reservas.*` y el procedimiento de reservar.
3. Sin profesionales: publicar avisa de lo que falta y deja publicar. En el probador, pedir una
   cita: el agente pide servicio, día y hora y pasa a una persona, sin decir que no hay huecos.
4. Añadir un profesional en Reservas. Sin publicar, el siguiente mensaje busca huecos y reserva.
5. Otro agente sin agenda: Conectores → «Agenda (Reservas)» → Activar. El borrador gana las 9 y
   aparece la propuesta con el antes y el después. «Editar» la aplica y abre el bloque.
6. Desactivar: el borrador pierde las 9; Reservas sigue encendido; la propuesta quita las citas.

## En staging (Spa Jemma)

- La ficha del agente ya no dice «No tenemos herramienta para: reservar citas».
- Con el texto viejo, la revisión avisa `forbids_agenda` señalando el procedimiento «Recoger una
  solicitud de cita», el disparador «porque la agenda no está activa» y las dos reglas.
- Pedir la propuesta: reescribe esas piezas y las dos habilidades `appointment_*_intake`.
- Registros: `builder.job` con `kind=agenda_text`; ningún `agenda.not_ready_turn` (Spa Jemma está
  listo: 4 profesionales, 15 servicios).
