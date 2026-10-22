# T060 — Reservas en pantalla, los dos modos

Capturas del 2026-10-22 contra la consola y el panel de operador locales, con
los datos de `apps/api/scripts/dev_seed_reservas_demo.py` (dos clientes chilenos:
Peluquería Cultor en **Servicios** y Restaurante La Fonda en **Aforo**, tipo
restaurante). 1440 × 900 en claro y oscuro; `-390` es un teléfono de 390 px.

| Fichero | Qué enseña |
|---|---|
| `servicios-dia-*` | Agenda del día por profesional: pausa de Lucía, «sin confirmar» con borde discontinuo, la marca del agente |
| `servicios-semana-*`, `servicios-lista-*` | Semana y lista con filtros |
| `servicios-detalle-*` | El detalle lateral de una reserva sin confirmar (`?booking=`) con su historial y lo que se puede hacer |
| `servicios-espera-*`, `servicios-ajustes-*` | Lista de espera (con «Adelantar su reserva del…») y Ajustes (equipo, servicios, horario, recordatorios) |
| `aforo-panel-*` | El Panel con el bloque «Ocupación» y la fila «N reservas de hoy sin confirmar» |
| `aforo-semana-*` | El mapa de ocupación de la semana: niveles con tokens, «Lleno» en el sábado a las 21:00 |
| `aforo-dia-lleno-*`, `aforo-lista-lleno-*` | El día lleno: pico, lista por hora con Llegó / No vino, la lista de espera que no cabe |
| `aforo-espera-*`, `aforo-ajustes-*` | Lista de espera y Ajustes (aforo, estancia, máximo, guardadas, turnos) |
| `admin-acceso-*` | Panel de operador, pestaña Acceso: Reservas con el modo y el tipo de negocio |

## Gates de UI del workspace

- **Pase vivo (axe WCAG 2.2 AA + desbordes)**: `apps/console/e2e/lite.spec.ts`,
  que ahora audita `/reservas`, `?view=list`, `?tab=waitlist` y `?tab=settings`
  además de Panel, Bandeja, Consumo y teléfonos, en es/en y claro/oscuro, a
  360 px con el texto un 30 % más largo y a 1920 px. Con la persona de cada
  modo: **Servicios 45/45**; **Aforo 41/45**, y las 4 que fallaban (la lista
  por hora a 360 px) en verde tras el arreglo de abajo (repetidas las 17 de
  Reservas: 17/17).
- **Lo que destapó y se arregló en este mismo cambio**:
  - a 360 px con texto largo, el selector Día · Semana · Mes y Cuadrícula ·
    Lista se salía de la pantalla → el grupo parte en dos filas;
  - en la lista por hora de Aforo, los botones Llegó / No vino se salían → el
    grupo se ajusta al ancho de la fila;
  - en el día de Aforo, «21:00 · 32 de 36» se cortaba en la cifra → la hora es
    la cifra y «32 de 36 dentro», la pista (prueba en `capacity.test.tsx`).
- **Cinco estados**: cada pantalla tiene `loading.tsx` con las medidas finales y
  `error.tsx`; vacío, error, parcial e ideal están probados en
  `components/reservas/__tests__/*` y en `components/lite/__tests__/lite-reservas.test.tsx`
  (16 pruebas del bloque del Panel: ideal por modo, vacío, error sin ceros,
  parcial con «—», esqueleto).
- **Tokens**: sin hex, rgb ni paletas de Tailwind en los ficheros tocados; los
  `style=` que quedan son geometría que sale de los datos (alto de una franja,
  posición de una cita), no tema. Los tres anchos arbitrarios nuevos pasaron a
  la escala (`min-w-84`, `min-w-160`, `min-w-176`).

Para repetirlo: siembra, API con la consola encendida, `pnpm --dir apps/console
dev`, y `E2E_CLIENT_EMAIL=valeria@cultor.test` (o `carla@lafonda.test`) `pnpm
--dir apps/console test:e2e --project=lite` (ver `docs/reservas.md`, «Probarlo en local»).
