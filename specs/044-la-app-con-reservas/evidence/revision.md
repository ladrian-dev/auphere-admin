# Revisión con los gates de UI — spec 044 (T048)

Los cuatro gates del workspace (`ui-states-checklist`, `a11y-audit`,
`responsive-audit`, `design-tokens`) sobre todo lo nuevo o tocado de
`apps/mobile`, el 2026-10-22, en lectura de código (es una app nativa:
Playwright y axe no aplican) más las capturas del simulador de
`hallazgos.md`. Cada punto, con lo que se hizo: test en rojo primero, arreglo,
y captura cuando se ve.

## 🔴 Bloqueantes: los cinco, arreglados

| # | Qué | Arreglo | Test | Captura |
|---|---|---|---|---|
| G1 | Si fallaba la lectura de huecos, «Nueva reserva» decía «No quedan huecos ese día» (mentira) y no dejaba reintentar | Error propio con «Reintentar» (`slotsError`, `onRetrySlots`) | `llegada-nueva.test.tsx` | — |
| G2 | Al cambiar de día o semana, el periodo anterior (`placeholderData`) se pintaba como el nuevo: «No hay reservas este día» o cifras a 0 hasta que llegaba la lectura | `showsOtherPeriod`: la cabecera se queda y el contenido es esqueleto | `reservas-dia.test.tsx` | — |
| G3 | Los errores de la hoja de una reserva y de «Llegada sin reserva» solo salían en el aviso breve, que vive en la raíz, **debajo** del `formSheet` de iOS | El error se dice dentro de la hoja (`error` en `ReservaSheet` y `WalkIn`); al acertar, la hoja se cierra y el aviso queda a la vista | `reserva-hoja.test.tsx`, `llegada-nueva.test.tsx` | `ios26-13-reserva-confirmada-desde-hoja-aviso-claro` |
| G4 | Ajustes de reservas desmontaba sus controles al guardar: el lector de pantalla perdía el sitio (WCAG 2.4.3) | Montados siempre; mientras guarda, desactivados | `reservas-espera-ajustes.test.tsx` | — |
| G5 | Contraste (WCAG 1.4.3): días cerrados en `subtle` (3,5–3,6:1 en claro) y la celda «llena» del mapa de calor (4,2:1) | Días cerrados en `mutedForeground` (≥ 6,8:1) y tachados, no solo por color; celda llena sobre `accentDeep` (5,0:1) | `reservas-dia.test.tsx`, `reservas-semana-mes.test.tsx` | `ios26-13-reservas-servicios-dia-domingo-cerrado-claro` |

## 🟡 Arreglados

- **Interruptor apagado** a 1,1:1 (oscuro) y 1,2:1 (claro) de su fila (WCAG
  1.4.11): una sola fuente, `ui/switch-colors.ts`, con el carril en `subtle`
  (≥ 3:1 en los dos temas, calculado en `switch-colors.test.ts`). También en los
  Ajustes de la app (042). Captura: `ios26-13-reservas-ajustes-interruptor-apagado-claro`.
- **La franja de «ahora»** solo se distinguía de la elegida por el color (el
  mismo verde en oscuro): su nombre empieza por «Ahora» y su borde es
  discontinuo.
- **VoiceOver no oía «Cabe…»** al cambiar los comensales
  (`accessibilityLiveRegion` no existe en iOS): el selector es un control
  `adjustable` con su valor, y el mensaje se anuncia al cambiar.
- **Doble toque** en la hoja de una reserva y en la lista de espera: los botones
  esperan mientras la acción va de camino.
- **Vacío con filtro**: con un profesional o una franja elegidos, dice que es
  esa persona o esa hora la que no tiene reservas, con «Ver todo el equipo».
- **Sin red y sin nada leído**: lo dice en vez de un esqueleto que no acaba.
- **La llegada sin reserva** con la ocupación en error se quedaba cargando; ahora
  da error y «Reintentar» relee las tres lecturas.
- **Texto grande en las filas** de Servicios e Inicio: la hora crece en vez de
  partirse, y en «Hoy en Reservas» el estado va bajo el nombre. Captura:
  `ios26-13-inicio-hoy-en-reservas-estado-debajo-claro`.
- **Español fijo** en inglés: «a las» al guardar y «ayer» en la lista de espera.

## 🟢 Arreglados de paso

- Chips de respuestas guardadas: 36 pt con `hitSlop` hasta el objetivo de la app.
- `radius.md * 1.5` → `CARD_RADIUS` en la tira de días y en las horas libres.

## Lo que queda abierto

- 🟢 `notices-permission.tsx`: `CARD_RADIUS + 6` fuera de la escala (es de la
  042 H15; cambiarlo mueve la pantalla de permiso, que no tiene captura nueva).
- 🟢 El aviso breve se anuncia y además es región viva: en Android puede leerse
  dos veces. Se verá en la pasada de Android.
- 🟢 Las horas de la Cuadrícula a 1,4× no caben en su margen de 44 pt; con
  texto ≥ 1,5 la Cuadrícula ya ofrece la Lista (D8).
- **Sin verificar aquí**: Android entero (T050: a mano por Luis en un
  dispositivo, con la lista de `hallazgos.md` §Android), VoiceOver y TalkBack en vivo,
  «Reducir transparencia», oscuro y texto grande de las pantallas de Servicios,
  la hoja y la conversación.

Ningún 🔴 abierto.
