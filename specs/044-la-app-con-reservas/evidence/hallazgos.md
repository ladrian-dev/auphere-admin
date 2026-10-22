# Evidencia y hallazgos — spec 044, la app con Reservas

Simulador «13 26» (iPhone 13, iOS 26), cliente de desarrollo con los datos de
ejemplo de Reservas (`EXPO_PUBLIC_RESERVAS_DEMO=services` y `capacity`, D2), el
2026-10-22. La API local no trae aún las rutas de la 043 (están en la rama de
`consolas-web`): todo lo de Reservas que se ve aquí es de ejemplo y la pantalla
lo dice («Datos de ejemplo»). Las mejoras de Bandeja, Inicio, Consumo y Ajustes
leen la API local real (cliente «Flor y Encanto»).

Android (T050) queda pendiente: ver al final.

## Hallazgos de la primera pasada en el simulador

Cada uno con su test en rojo antes del arreglo, salvo los que solo se ven en
pantalla (se dice), y con su captura de antes y después.

| # | Qué se vio | Sev. | Arreglo | Test | Capturas (antes → después) |
|---|---|---|---|---|---|
| R1 | La línea «Ahora» se quedaba en la hora de la lectura: el `useMemo` con un tic que no leía lo congelaba React Compiler | 3 | El reloj del teléfono es estado y se pasa a la cuenta (`useNowMs` en `reservas-hooks.ts`) | `reservas-now.test.tsx` | `…servicios-dia-ahora-claro` (11:20) → `…servicios-dia-ahora-avanza-claro` (11:23) |
| R2 | «1 h 30 min» se partía en la columna de la hora de la lista | 2 | `durationShort`: «1 h 30» donde la columna es estrecha | `reservas-dia.test.tsx` | → `…servicios-dia-duracion-corta-claro` |
| R3 | En la Cuadrícula, un bloque de media hora solo decía la hora | 2 | Una línea: «09:00 · Nombre» | `reservas-dia.test.tsx` | `…servicios-cuadricula-antes` → `…servicios-cuadricula-claro` |
| R4 | En el Mes, «Cerrado» se cortaba en «Cerra…» | 1 | Se encoge para caber en un séptimo del teléfono | `reservas-semana-mes.test.tsx` | `…servicios-mes-antes` → `…servicios-mes-claro` |
| R5 | La hoja decía el estado dos veces y el historial salía desordenado | 2 | El estado una vez (valor de la fila); el historial del más antiguo al más nuevo | `reserva-hoja.test.tsx` | `…reserva-hoja-completa-antes` → `…reserva-hoja-completa-claro` |
| R6 | Datos de ejemplo: se pedía confirmación antes de crear la reserva | 1 | El historial de ejemplo nunca va hacia atrás | `reservas-demo.test.ts` | (la misma hoja) |
| R7 | En «Nueva reserva», la última hora suelta se estiraba a todo el ancho | 1 | Huecos vacíos completan la fila de cuatro | `llegada-nueva.test.tsx` | `…reserva-nueva-servicios-ultima-hora-antes` → `…reserva-nueva-aforo-claro` |
| R8 | **La barra de pestañas se desordenaba** (etiquetas fuera de sitio) al cambiar de pestaña con una pantalla de la pila raíz encima: el enlace del contacto a su próxima reserva | 3 | Se reenvía el estilo de las etiquetas al volver a verse las pestañas y al montarlas (`useTabRelayout`), tras la transición | `tabs.test.tsx` | `…reserva-cancelada-aviso-y-barra-rota-antes`, `…barra-tras-enlace-antes` → `…barra-tras-enlace-despues` |
| R9 | La Bandeja se quedaba con el indicador de recarga girando y el título grande bajo la búsqueda tras una relectura en segundo plano | 2 | El indicador es del gesto de la persona, no de cada lectura (`usePullRefresh`, en las seis pantallas con recarga) | `pull-refresh.test.tsx` | `…bandeja-recarga-atascada-antes` |
| R10 | En iOS, el «+» de «Llegada sin reserva» flotaba 64 pt por encima de la barra y tapaba la tira de franjas | 2 | 16 pt sobre la barra (el margen inferior ya la cuenta) | solo se ve en pantalla | `…aforo-dia-fab-alto-antes` → `…aforo-dia-claro` |
| R11 | Una llegada sin nombre decía «Sin reserva» como nombre y como estado | 1 | Se llama «Sin nombre» | `reservas-dia.test.tsx` | `…aforo-sin-reserva-doble-antes` |
| R12 | En la lista de espera, un estado largo aplastaba el nombre en dos líneas | 1 | El nombre a todo el ancho y el estado debajo | `reservas-espera-ajustes.test.tsx` | `…espera-aforo-antes` → `…espera-aforo-axl` |
| R13 | En Ajustes de Aforo, los turnos aplastaban el día (sin nombre de día y repetidos) | 2 | Tramos de días («Lunes a sábado») con los turnos debajo | `reservas-espera-ajustes.test.tsx` | `…ajustes-aforo-2-antes` → `…ajustes-aforo-2-claro`, `…ajustes-aforo-horario-axl` |
| R14 | Una oferta recién hecha decía «16 min para responder» (son 15) | 1 | El reloj de la cuenta atrás nunca es anterior a la lectura de la lista | `reservas-now.test.tsx` | `…espera-ofrecida-16min-antes` |
| R15 | Con texto grande, el periodo partía «Seman/a» y las horas del mapa de calor «13:0/0» | 2 | Una línea que se encoge para caber | `reservas-semana-mes.test.tsx` | `…aforo-semana-axl-antes`, `…aforo-dia-axl-antes` → `…aforo-semana-axl`, `…aforo-dia-axl` |
| R16 | «Reintentar» (y la acción de un vacío) quedaba a la izquierda en todos los estados de error: venía de la 042 | 1 | Centrado bajo las palabras (`ui/states.tsx`) | `states.test.tsx` | `…reservas-error-reintentar-antes` → `…reservas-error-claro` |

| R17 | **Una renovación rechazada con un código que no era `phone_closed`** (`invalid_grant`: un token que la API no conoce, tras rehacer la base) **dejaba la app en «No se pudo cargar» para siempre**, sin volver a Entrar. Viene de la 031; salió al probar contra la API de la 043 | 3 | Cualquier 401/403 de la renovación cierra el teléfono, salvo `app_update_required` (`api/client.ts`) | `api-client.test.ts` | — |

Sev.: 3 rompe la tarea o miente, 2 se ve mal o confunde, 1 detalle.

La revisión con los gates de UI encontró más (G1–G5 y los 🟡): están en
`revision.md`.

## Capturas por pantalla y estado

Todas en `capturas/`, prefijo `ios26-13-`.

| Pantalla | Ideal | Otros estados | Oscuro | Texto grande (AX-L) |
|---|---|---|---|---|
| Inicio | `inicio-atencion-reservas-claro` (Servicios), `inicio-aforo-claro`, `inicio-hoy-en-reservas-estado-debajo-claro` | — | — | — |
| Reservas · Servicios · Día (lista) | `reservas-servicios-dia-claro`, `…-dia-ahora-avanza-claro`, `…-dia-duracion-corta-claro` | — | — | — |
| Reservas · Servicios · Día (cuadrícula) | `reservas-servicios-cuadricula-claro` | — | — | — |
| Reservas · Servicios · Semana / Mes | `reservas-servicios-semana-claro`, `reservas-servicios-mes-claro` | — | — | — |
| Reservas · Aforo · Día | `reservas-aforo-dia-claro` | vacío: `reservas-aforo-dia-vacio-claro`; error: `reservas-error-claro` | `reservas-aforo-dia-oscuro` | `reservas-aforo-dia-axl` |
| Reservas · Aforo · Semana (mapa de calor) | `reservas-aforo-semana-calor-claro` | — | `reservas-aforo-semana-calor-oscuro` | `reservas-aforo-semana-axl` |
| Menú `⋯` | `reservas-menu-servicios-claro`, `reservas-menu-aforo-claro` | — | — | — |
| Hoja de una reserva | `reserva-hoja-atendida-claro`, `reserva-hoja-sin-confirmar-claro`, `reserva-hoja-completa-claro` | cancelar: `reserva-cancelar-confirmacion-claro` | — | — |
| Nueva reserva | `reserva-nueva-servicios-lista-para-guardar-claro`, `reserva-nueva-aforo-claro` | guardada: `reserva-guardada-aviso-claro` | `reserva-nueva-aforo-oscuro` | — |
| Llegada sin reserva | `llegada-sin-reserva-cabe-claro` | registrada: `llegada-registrada-aviso-claro` | — | — |
| Lista de espera | `reservas-espera-servicios-claro` | — | — | `reservas-espera-aforo-axl` |
| Ajustes de reservas | `reservas-ajustes-servicios-{1,2}-claro`, `reservas-ajustes-aforo-{1,2}-claro` | — | — | `reservas-ajustes-aforo-horario-axl` |
| Bloquear horas | `bloquear-horas-aforo-claro` | — | — | — |
| Bandeja | `bandeja-esperan-arriba-claro`, `bandeja-pie-claro` | — | — | — |
| Conversación | `conversacion-espera-desde-claro`, `conversacion-atiendes-ventana-cerrada-claro`, `conversacion-menu-devolver-claro` | — | — | — |
| Contacto | `contacto-proxima-reserva-claro` → `contacto-abre-reserva-claro` | — | — | — |
| Consumo | `consumo-saldo-agotado-recarga-claro` | — | — | — |
| Ajustes (avisos) | `ajustes-avisos-sin-activar-claro` | — | — | — |

Lo que no tiene captura y por qué:

- **Carga, parcial y sin red** de Reservas: por test (`reservas-dia.test.tsx`
  «the screen's states»); el retraso de los datos de ejemplo es demasiado corto
  para fotografiar el esqueleto.
- **Pantalla del permiso de avisos**: sale tras el primer inicio de sesión; se
  capturó en la pasada contra la API de la 043 (`api043-permiso-avisos-claro`).
  Los avisos activados, por test (`ajustes-avisos.test.tsx`, `push.test.tsx`).
- **Oscuro y AX-L de cada pantalla**: se hizo en las de más riesgo (Aforo, formulario,
  lista de espera, ajustes); el resto usa los mismos componentes de la 042, que
  pasaron esa prueba en su spec.
- El pegado del simulador estropea las tildes al escribir en un campo (es de la
  herramienta, no de la app): los nombres de prueba se escribieron sin tildes.

## Contra la API de la 043 (2026-10-22, tarde)

Con el código de la 043 del worktree de `consolas-web` sobre una base propia
(`nexus_app_movil_044`, migrada a 0174 y sembrada con `dev_seed_reservas_demo.py`;
cómo, en `quickstart.md`). Todas las llamadas de Reservas respondieron 200.

| Qué | Captura (`ios26-13-api043-…`) |
|---|---|
| Primera entrada: la pantalla de permiso de avisos con sus grupos | `permiso-avisos-claro` |
| Inicio de Peluquería Cultor: espera, 2 sin confirmar, saldo, «Hoy en Reservas» | `inicio-servicios-claro` |
| Servicios · Día: Lucía, Marcos y Nora; «Ahora» en hora de Santiago | `reservas-servicios-dia-claro` |
| La hoja con el historial de la API (`events`) | `reserva-hoja-claro` |
| «Marcar confirmada» con `If-Match`: 200, se relee y baja la cuenta | `confirmada-aviso-claro` |
| Aforo · Día de Restaurante La Fonda: 36 comensales, franjas y grupos | `reservas-aforo-dia-claro` |
| «Llegada sin reserva» fuera de servicio | `llegada-sin-servicio-claro` |

Detalle visto y no arreglado: el teléfono del cliente sale tal como lo guarda la
API (`+56991234503`); los datos de ejemplo lo traían con espacios. Darle formato
es de una spec de contactos, no de esta.

## Android (T050): a mano, en un dispositivo

Cerrada el 2026-10-22 por decisión de Luis: lo prueba él en un teléfono Android.
Sin compilar en el Mac, la forma de tener la app en el teléfono es el cliente de
desarrollo hecho en EAS (en la nube) y Metro en el Mac con los datos de ejemplo:

```bash
cd apps/mobile && eas build -p android --profile development
```

```bash
cd apps/mobile && EXPO_PUBLIC_RESERVAS_DEMO=capacity pnpm exec expo start --dev-client
```

(`services` para Servicios; o, contra la API de la 043, como en `quickstart.md`.)
El APK de `preview` habla con staging y no enseñará Reservas hasta que la 043 esté
desplegada allí.

Lo que solo se ve en Android y ningún test cubre:

1. **Los dos flotantes**: «Nueva reserva» extendido abajo a la derecha en todas
   las vistas de Reservas; en Aforo · Día · hoy, el «+» pequeño de la llegada
   apilado encima, sin tapar la última fila.
2. **El menú `⋯`** en la barra superior: hoja de acciones con «Llegada sin
   reserva» (Aforo), «Lista de espera», «Ajustes de reservas» y «Bloquear horas».
3. **Las hojas** (reserva, nueva, llegada, bloquear) como hoja inferior con las
   esquinas de la app; el teclado no tapa nombre ni teléfono en «Nueva reserva»;
   el gesto atrás las cierra.
4. **El aviso breve** encima de la barra de pestañas, y con TalkBack que se lea
   **una sola vez** (es el 🟢 abierto de `revision.md`).
5. **Oscuro**: el mapa de calor se lee en sus cinco niveles; el interruptor
   apagado de Ajustes se distingue de la fila.
6. **Texto al máximo** (Ajustes › Tamaño de fuente): el selector Día/Semana/Mes,
   las horas del mapa de calor y la columna de la hora no se parten.
7. **La barra de pestañas** con cuatro módulos: la etiqueta «Reservas» entera y su
   icono.
8. Con Firebase ya creado (`evidence/builds.md`): el canal «Reservas» en los
   ajustes de avisos del sistema.

Lo que se encuentre va como hallazgo aquí (R18 en adelante).
