# Quickstart — cómo se comprueba la 064

## En local

Base y Redis propios, para no pisar a otra sesión:

```bash
export NEXUS_DATABASE_URL=postgresql+asyncpg://nexus:nexus@localhost:5433/nexus_test_064 NEXUS_REDIS_URL=redis://localhost:6379/12
```

```bash
./scripts/verify.sh lint
```

```bash
cd apps/api && uv run pytest tests/unit/test_reservations_settings.py tests/unit/test_064_correction.py tests/unit/test_064_context_cut.py tests/unit/test_064_inbox_settings.py -x
```

```bash
cd apps/api && uv run pytest tests/integration/reservas/test_064_notice.py tests/integration/reservas/test_064_correction.py tests/integration/test_064_conversation_cycle.py tests/integration/test_migration_0236_context_and_autoclose.py -x
```

```bash
cd apps/api && uv run pytest tests/isolation/test_reservas_customer_axis.py tests/isolation/test_064_context_and_autoclose.py -x
```

Las del worker van aparte de las de la API:

```bash
cd apps/api && uv run --with lupa pytest ../worker/tests/unit/test_064_history_cut.py ../worker/tests/unit/test_064_inbox_autoclose_cron.py ../worker/tests/unit/test_bootstrap_split.py -x
```

```bash
cd apps/console && pnpm vitest run src/components/reservas src/components/inbox "src/app/(console)/reservas" src/i18n
```

```bash
cd apps/console && pnpm build
```

Qué tiene que salir:

| Requisito | Prueba en local |
|---|---|
| 1 | Que `apply_patch` acepte los siete valores y rechace otro con su campo. Que el valor por defecto siga en 60. Que `find_slots` devuelva en `too_soon` las horas libres dentro de la antelación y en `slots` las demás, en Servicios y en Aforo, y `too_soon` vacío sin antelación. Que la consola pinte el control en los dos modos y guarde al cambiar. |
| 2 | Que una `done` de Servicios traiga `noshow` hasta 7 días y no después. Que `undo` sobre un `noshow` pasado deje `done`. Que en Aforo no aparezca. Que no se encole ningún aviso. Que el resumen del mes cuente el estado final. Que la pantalla relea sola con la pestaña visible, no relea oculta, relea al volver, y conserve la última lectura buena con su aviso si la relectura falla. |
| 3 | Que los dos diálogos no dejen guardar sin teléfono o con uno sin `+` o con menos de 8 dígitos. Que la llegada sin reserva no lo pida. Que mover una reserva sin teléfono funcione. Que la API siga aceptando una reserva sin teléfono (la app de hoy). Que una reserva a mano solo se enlace al contacto del mismo negocio con ese número exacto. |
| 4 | Que resolver ponga `cut_on_reopen`. Que el contacto que vuelve corte en `closed_at`, y que una persona que reabre no corte. Que un aviso sin respuesta y vigente quede dentro, y uno caducado fuera. Que una resuelta antes del despliegue no corte. Que el worker lea desde `greatest(attended_at, context_from)` y añada la nota con el nombre saneado. Que la Bandeja siga enseñando el hilo entero. |
| 5 | Que la ruta de ajustes lea y guarde los cinco valores y rechace otro. Que `close_inactive` cierre solo lo que lleva el agente y pasó el plazo, con su evento. Que el cron esté en las tres listas de `bootstrap.py`. Que la consola diga «Se cerró por inactividad». Que un cliente no lea ni cambie el ajuste de otro. |

## En el navegador, con la consola en local

1. **Antelación.** Reservas → Ajustes: aparece «Citas que da el agente» con el
   valor actual. Cambiarlo a «Sin antelación» y recargar: se mantiene.
2. **Teléfono.** «Nueva reserva»: sin teléfono, «Guardar» no se activa y el
   campo dice por qué. Con `600123456` dice que falta el prefijo. Con
   `+34 600 123 456` guarda.
3. **Corregir.** Abrir una cita «Atendida» de ayer: ofrece «No vino». Marcarla y
   deshacer: vuelve a «Atendida», nunca «Confirmada».
4. **Relectura.** Con la agenda abierta, cambiar el estado de una cita desde
   otra pestaña: aparece sin recargar en menos de un minuto. Con un diálogo
   abierto y texto escrito, la relectura no lo cierra.
5. **Bandeja.** «Ajustes» en la cabecera: el desplegable guarda. Una
   conversación cerrada por inactividad dice «Se cerró por inactividad» en el
   hilo.

Puertas de interfaz antes de dar por hecha cada pantalla: `ui-states-checklist`,
`a11y-audit`, `responsive-audit` y `design-tokens`.

## En staging, después de desplegar `develop`

Con los clientes de prueba del partner interno (Spa Jemma).

1. **CE-001.** En Ajustes, «Sin antelación». Pedir por WhatsApp una cita «cuanto
   antes»: el agente ofrece la próxima hora libre de la rejilla.
2. **CE-002.** Con 2 horas de antelación y una hora libre dentro, pedirla cinco
   veces: ninguna respuesta dice que no hay disponibilidad.
3. **CE-004 y CE-005.** Dejar terminar una cita con la agenda abierta: pasa a
   «Atendida» sola. Al día siguiente, marcar «No vino» y mirar la cifra del mes.
4. **CE-007.** Resolver una conversación y volver a escribir desde ese número
   cinco veces, resolviendo entre una y otra: el agente no usa nada de lo
   anterior y saluda por el nombre.
5. **CE-008.** Poner el cierre a 24 horas y mirar al día siguiente.
6. **CE-009.** Con la app móvil de hoy contra staging: crear una reserva sin
   teléfono, abrir una cita «Atendida» y cancelar otra.

## Antes de fusionar

```bash
./scripts/verify.sh lint
```

Y las pruebas de lo tocado, de arriba. Las suites completas corren de camino a
`main`.
