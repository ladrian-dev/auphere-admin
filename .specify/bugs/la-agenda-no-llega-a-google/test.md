# Bug Verification: la agenda no llega a Google Calendar y nadie se entera

- **Slug**: la-agenda-no-llega-a-google
- **Tested**: 2026-11-04
- **Assessment**: ./assessment.md
- **Fix**: ./fix.md
- **Result**: partial

## Summary

Las pruebas pasan con un doble del proveedor, y la pantalla se ha visto en Chromium contra
una API simulada. Es `partial` porque **no se ha hecho ninguna llamada de verdad a Google ni
a Composio**: los nombres y argumentos salen de su documentación pública, y esa
documentación no describe la forma de las respuestas.

## Checks Performed

| Check | Command / Action | Result | Notes |
|---|---|---|---|
| Pruebas de la API, antes | `pytest tests/integration/reservas/test_la_agenda_llega_a_google.py` | fail | 31 failed, 5 passed. Con solo los nombres nuevos añadidos para que el archivo se pudiera cargar, y parte del rojo es la falta del argumento `tz` |
| Pantalla, antes | `vitest run …/settings/__tests__/staff-calendars.test.tsx` | fail | 19 de 19 en rojo |
| Lo tocado de la API, con el barrido de aislamiento | `pytest` de `test_la_agenda_llega_a_google`, `test_calendar_sync`, `test_api_services`, `test_api_capacity`, `tests/isolation/test_reservas_client_vs_client`, `tests/unit/test_composio_live_list_tools`, `tests/unit/connectors/test_composio_client` | pass | 106 passed |
| Otros que llaman a `move_booking` | `pytest` de `test_tools`, `test_worker_offers`, `test_concurrency` | pass | 15 passed |
| Worker | `pytest apps/worker/tests/unit/test_bootstrap_split.py` | pass | 5 passed |
| Consola | `vitest run` de `staff-calendars`, `actions`, `waitlist-and-settings`, `services-agenda`, `capacity` | pass | 5 archivos, 79 pruebas, con axe en la sección |
| Lint y formato | `ruff check`, `ruff format --check` de los 9 archivos Python | pass | |
| Tipos de Python | `mypy` de los 6 archivos de la API y del cron | pass | Encontró `log_id` al pasar a `to_thread`. Corregido |
| Tipos y lint de la consola | `tsc --noEmit -p tsconfig.json`, `eslint --max-warnings 0` de lo tocado | pass | |
| En un navegador | Chromium con `next dev` y una API simulada temporal, fuera del repo | pass | Ver abajo |
| Llamada real a Google | | not-run | No es posible desde aquí |
| Staging | | not-run | Sin desplegar |
| Suites completas | | not-run | Se corrió lo que cubre el cambio, como se pidió |

`test_a_client_only_touches_what_is_its_own` y la comprobación de que el estado se corrige sin
esperar a la pasada se escribieron después del arreglo: no se vieron en rojo. Pasaban antes
del arreglo, y por tanto no prueban nada de él: `test_deleting_speaks_the_arguments_of_the_provider`,
`test_a_move_that_changes_nothing_does_not_touch_the_event`,
`test_saving_the_same_calendar_again_leaves_the_events_alone`,
`test_an_all_day_block_takes_the_slots_of_the_day` y
`test_an_answer_without_an_id_does_not_write_it_again`.

## Auditoría de UI

`staff-calendars.tsx` en siete situaciones: ideal, sin conector, hay que volver a conectar, Google
no responde, cuenta sin calendarios, error de lectura y equipo vacío. Son 78 comprobaciones.

| Comprobación | Resultado |
|---|---|
| axe (WCAG 2.0 a 2.2 AA, con contraste) sobre la sección, en claro y en oscuro | 0 violaciones en las siete |
| Sin desbordar a 320, 360, 414, 768, 1024, 1280, 1440 y 1920 px | Las siete |
| 200 %, como viewport de 640×450 | Sin desbordar |
| Texto largo: palabra de 42 letras y token de 100 sin espacios en nombre y calendario | Se recortan con `truncate` y `title`, sin desbordar |
| Zonas de pulsación de 24×24 | Ninguna por debajo |
| Errores de la página | Ninguno |
| Elegir un calendario y desconectar, de verdad en la pantalla | `PUT …/calendar` con `a@agenda` y con `null` |
| Tokens: hex, `style={{}}`, paletas por defecto | Ninguno |

**Cinco estados:** cargando (esqueleto con `role="status"`, solo en jsdom: en el navegador se
esperó a que acabara), vacío, error con «Reintentar», parcial e ideal. El parcial: Google no
responde o falta el equipo, y lo asociado se sigue viendo.

**No se ha visto:**
- Con la API de verdad ni con una sesión real.
- Con un lector de pantalla, Safari, Firefox o un teléfono.
- El zoom real del navegador: se aproxima con el viewport.
- En inglés, en el navegador: solo en una prueba de componente.
- Tras guardar, el foco al cerrar el diálogo de desconectar: el botón que lo abrió desaparece.

## Output Excerpts

```
31 failed, 5 passed, 1 warning in 22.56s
106 passed, 1 warning in 67.15s (0:01:07)
15 passed, 1 warning in 17.36s
Test Files  5 passed (5)
     Tests  79 passed (79)
checks: 78
```

## Residual Risks

- **La forma de las respuestas de Composio es la mayor incógnita.** Si no se reconoce un
  listado, la lectura falla y lo dice la pantalla. Si al crear no se reconoce el id, se guarda
  `?`: no se duplica, pero ese evento no se podrá mover y vuelve como ocupado ajeno.
- **El texto de los errores es una suposición.** El 404 y el permiso se reconocen por la
  excepción del cliente o por el texto del error. Si Composio los redacta de otro modo,
  un evento borrado a mano quedaría reintentándose hasta 7 días y un permiso rechazado
  saldría como `read`, sin duplicar.
- `tests/integration/reservas/test_calendar_sync.py:202` pasa y no prueba R10.5 tal como está
  escrito: ver `assessment.md`.

## Recommendation

Mantener abierto hasta probarlo en staging con una cuenta de Google: asociar un calendario, crear
una reserva, moverla, cancelarla, borrar un «Ocupado» a mano y revocar el permiso.
