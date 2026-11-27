# Quickstart: comprobar la 082

Desde el worktree `.claude/worktrees/loving-hermann-d3c626`.

## Pruebas automáticas

```bash
ps -eo pid,etime,command | grep "[p]ytest"   # nadie más probando sobre la misma base
export NEXUS_DATABASE_URL=postgresql+asyncpg://nexus:nexus@localhost:5433/nexus_test_082
export NEXUS_REDIS_URL=redis://localhost:6379/12
cd apps/api
uv run pytest tests/isolation/test_082_reservations_changed_scope.py \
  tests/unit/test_082_reservations_live.py tests/unit/test_082_add_event_sweep.py \
  tests/unit/test_lite_inbox_media_and_stream.py \
  tests/integration/reservas/test_082_datos_al_dia.py \
  tests/integration/test_082_inbox_detail.py tests/integration/test_082_customer_name.py
cd ../..
./scripts/verify.sh lint
./scripts/verify.sh js
cd apps/console && pnpm exec playwright test -c e2e/datos-al-dia.config.ts
```

Resultado esperado: todo en verde. La prueba de navegador tarda unos minutos la primera vez (`next dev` compila).

## A mano (staging o desarrollo)

1. **Agenda.** Abre Reservas en un navegador.
   - Cancela una reserva: sale sin recargar.
   - Haz una reserva por WhatsApp con el agente: aparece en menos de 5 s.
   - Marca «No vino» con doble clic: la ficha queda ocupada, y solo sale una orden (sin 412 en los logs).
2. **Conocimiento.** En Agente › Conocimiento, sube un PDF.
   - Aparece en la lista con «Leyendo», y «Qué sabe» lo cuenta.
   - Pasa sola a «Lista».
   - Quítalo: «Qué sabe» deja de contarlo.
3. **Bandeja.** Con la consola en Reservas, escribe al número desde un teléfono.
   - Suena una vez.
   - El contador sube, también con la barra plegada (número en la esquina del icono).
   - La pestaña dice «(1) ».
4. **Reconexión.** Corta la red 30 s y vuelve. Lo que llegó mientras tanto aparece sin recargar.
5. **Resumen.** Escala una conversación y resuélvela: el panel ya no enseña el resumen.
6. **Avatar.** Los contactos sin nombre tienen icono de persona. Cada contacto conserva su color en la lista, el hilo y el panel. El `@usuario` se ve en el panel.
