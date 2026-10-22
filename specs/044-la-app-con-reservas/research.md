# Research — spec 044, la app con Reservas

Las decisiones del plan, con su porqué y lo que se descartó. Las fuentes son
las de la spec: la nota de KB `research/2026-10-22-reservas-y-consola-customers`
(con `lecturas/app-movil.md` y `lecturas/reservas-dominio.md`) y el código de
`apps/mobile` en la rama de la 042.

## D1 · Construir contra un contrato propuesto, con un adaptador

**Decisión.** La app define en `contracts/app-needs.md` lo que necesita y lo
envía a `consolas-web`. Todo Reservas pasa por **un adaptador**
(`src/api/reservas.ts`) con dos fuentes que cumplen la misma interfaz: la HTTP
(rutas de §2–§7 del contrato) y la de ejemplo (D2). Las pantallas solo ven el
modelo de `data-model.md`.

**Por qué.** La API de Reservas se construye a la vez (spec 043) y su contrato
no estaba congelado cuando empezó esta. Si cambia una ruta o un campo, cambia
un archivo, no doce pantallas.

**Resultado (2026-10-22, T047).** El contrato de la API llegó congelado a
media jornada y difería bastante (prefijo, `If-Match`, eventos, bloqueos por
franjas, nombres de avisos): se absorbió en el adaptador y en seis sitios de
pantalla que dependían de la forma; la tabla está al final de
`contracts/app-needs.md`.

**Descartado.** Esperar al contrato (la jornada no da); generar tipos de un
`openapi.json` que aún no tiene las rutas (no compilaría hasta que exista).
Las rutas nuevas se llaman con `authedFetch` y se pasan a `openapi-fetch`
tipado cuando el `openapi.json` las traiga (tarea de reconciliación).

## D2 · Datos de ejemplo solo en desarrollo

**Decisión.** `EXPO_PUBLIC_RESERVAS_DEMO=services|capacity` en un build de
desarrollo activa una fuente en memoria con dos negocios chilenos: «Barbería
Norte» (Providencia, Servicios, precios en CLP) y «Casa Lucía» (Aforo, 64
comensales). La fuente añade `reservas` a la navegación de `/me`, responde la
configuración, las reservas, la ocupación, los huecos, la lista de espera y las
escrituras (con su latencia y sus errores), y guarda los avisos en memoria. Cada
pantalla de Reservas enseña «Datos de ejemplo». Fuera de `__DEV__` el código de
ejemplo no se importa (`require` condicional) y la variable se ignora.

**Por qué.** Clarificación 3: lo que alguien prueba como real no enseña datos que
no existen (§V). Y hace falta algo concreto para probar y capturar mientras la
API no está.

## D3 · La hora es la del negocio

**Decisión.** Fechas y horas de Reservas son hora de pared del negocio (`date`,
`HH:MM`) y «ahora» sale de `now` del servidor, avanzado con el reloj del
teléfono desde que se leyó. Se pintan sin convertir. Lo demás de la app (la
Bandeja) sigue en la hora del teléfono, como en la 031.

**Por qué.** Una agenda de una barbería de Santiago se lee en la hora de
Santiago aunque el teléfono esté en Madrid. Evita además depender de las zonas
horarias de Hermes para pintar una cuadrícula.

## D4 · Inicio cuenta Reservas desde el día de hoy, no desde `home`

**Decisión.** «N reservas de hoy sin confirmar» y «Hoy en Reservas» se calculan
en el teléfono con la misma lectura que la pestaña (`reservations?from=hoy&to=hoy`
y, en Aforo, la ocupación de hoy). No se pide un bloque nuevo en `LiteHomeOut`.

**Por qué.** Un solo número para la misma cosa (042 R5.1, CE-005 de esta spec):
lo que dice Inicio es lo que se ve al tocar «Ver reservas». Y le quita trabajo a
la 045.

## D5 · La pestaña Reservas y sus pantallas

**Decisión.**

- `src/app/(app)/reservas/` es una pila como las demás pestañas: `index` (el
  día, la semana, el mes), `espera` (Lista de espera) y `ajustes` (Ajustes de
  reservas), apiladas dentro de la pestaña como en el diseño.
- Las cuatro hojas son rutas de la pila raíz con `formSheet`
  (`reserva/[id]`, `reserva/nueva`, `reserva/llegada`, `reserva/bloquear`),
  como el contacto de la 042: en iOS con paradas y asa, en Android hoja inferior
  con las esquinas de la app. El enlace desde el contacto o un aviso abre
  `/reservas?date=…&open=<id>`.
- Icono del módulo: `calendar` (SF) y `event` (Material).

**Por qué.** Reutiliza el patrón de hojas de la 042 (R1.7) y la pila de cada
pestaña; un aviso o un enlace llegan a una ruta, no a un estado.

## D6 · Los dos «+» (clarificación 4)

**Decisión.** iOS: «Nueva reserva» es un `Stack.Toolbar.Button` con
`calendar.badge.plus`, junto al menú `⋯` y Ajustes; el botón flotante redondo
«+» es solo «Llegada sin reserva» y solo en Aforo·Día·hoy. Android: botón
flotante extendido «Nueva reserva» (radio 16, Material 3) y, en Aforo·Día·hoy,
el flotante pequeño «+» de la llegada apilado encima, como en el diseño. El menú
`⋯` incluye también «Llegada sin reserva» en Aforo.

**Vidrio.** El flotante es un control que flota sobre el contenido: en iOS 26 es
un `GlassView` interactivo con el «+» en el color de acento; antes de 26, o con
«Reducir transparencia», un círculo opaco `primary`. Nunca va sobre otro vidrio
(la barra de pestañas está debajo, no detrás).

## D7 · El aviso breve (clarificación 5)

**Decisión.** Un proveedor `Toast` en la raíz: un aviso a la vez, opaco (texto
del sistema sobre la superficie inversa de la paleta), anclado encima de la barra
de pestañas, que se anuncia con `AccessibilityInfo.announceForAccessibility`.
Dura 4 s, 6 s si ofrece «Deshacer»; entra con un fundido y desplazamiento corto
(`durations.enter`), solo fundido con «Reducir movimiento».

**Por qué opaco.** Es contenido (una frase), no un control de navegación; el
vidrio es para barras y controles (AGENTS.md).

## D8 · La agenda: lista primero, cuadrícula como vista

**Decisión.** Servicios·Día abre en Lista; la Cuadrícula es una vista con una
columna por profesional (ancho mínimo 120 pt, desplazamiento horizontal si no
caben), 52 pt por hora multiplicado por la escala de texto hasta 1,6, y cada
bloque es un botón con la misma frase que la fila. Con el texto en tamaños de
accesibilidad (≥ 1,5) la Cuadrícula avisa de que la Lista se lee mejor y ofrece
cambiar, sin forzarlo.

**Por qué.** La lista es la vista que cuenta todo y escala sin perder nada; la
cuadrícula es una vista de conjunto que no puede escalar sin límite.

## D9 · Aforo: cifras, tira de franjas y grupos por hora

**Decisión.** Día: tres cifras en una lista agrupada de la 042 (no tarjetas en
rejilla, H3), la tira de franjas desplazable (cada franja un botón con
«13:30, 52 de 64 dentro»), y un `Group` por hora. Semana: mapa de calor de días
por franjas en cinco niveles de `positive` con la cifra dentro y el rayado de
bloqueado como patrón de bordes, con su leyenda. Mes: la rejilla común (D10).

**Niveles.** < 35 %, 35–60 %, 60–85 %, ≥ 85 % y lleno; el texto de la celda va
en `foreground` o `primaryForeground` según el fondo, y la cifra siempre se lee
(nunca el color solo, WCAG 1.4.1).

## D10 · Mes y navegación entre periodos

**Decisión.** El mes es una rejilla de 7 columnas (lunes primero) con la barra de
ocupación y «N %» o «Cerrado»; Semana y Mes tienen «‹ ›» para el anterior y el
siguiente (el diseño no tenía flechas en Mes: sin ellas no se llega al mes
siguiente).

## D11 · Mejoras sin romper la 042

| Diseño | Decisión |
|---|---|
| Título «Inicio» | Se queda «Hola, {nombre}» y el nombre del negocio (031/042) |
| Tres cifras en tarjetas | Filas con chevrón de la 042: conversaciones → Bandeja, saldo → Consumo |
| Insignia junto a «Necesita tu atención» | No (042 H13) |
| Atención sin saldo bajo | Se mantiene el saldo (030 R4.5) y se suman las reservas |
| Búsqueda en el contenido | Búsqueda nativa (042 D6) |
| Motivo entero en la tarjeta | Dos líneas y «Leer más» (042 R2.3, H19); se añade la espera |
| Respuestas guardadas en chips | Sí, con el borrador vacío; la hoja sigue para todas |
| Ajustes y Contacto apilados | Hojas (042 R1.7) |
| Cerrar sesión y borrado juntos | Grupos separados (042 R8) |
| Selector de periodo siempre | Solo con gasto (042 R9.2) |
| «Papel: Propietaria» | Sigue «Persona del negocio» (030 descartó papeles) |

## D12 · Avisos

**Decisión.** `NOTICE_KINDS` gana tres de Reservas (`needs: "reservas"`) y un
`group` (Bandeja, Reservas, Saldo); Ajustes y la pantalla de permiso agrupan por
él. La pantalla de permiso enseña un aviso de ejemplo y un tipo por grupo
(«Cambios en las reservas de hoy» resume los tres) y pone las acciones fijas al
pie, con la nota de privacidad encima del contenido desplazable (cierra 042 H15).
El silencio fuera de horario es un interruptor más del grupo de avisos, solo si
la API trae `quiet_outside_hours`. Canal de Android `reservations_v1`
(importancia por defecto) y categoría de iOS `reservations` sin acciones.

## D13 · H25: las etiquetas de la barra con texto grande

**Decisión.** Las etiquetas de `NativeTabs` no escalan más allá del tamaño
grande del sistema: en iOS la barra del sistema usa el visor de contenido grande
al mantener pulsado. Se fija `labelStyle` con el tamaño del sistema
(`fontSize` fijo de 10 pt en iOS, el de Material en Android) para que el texto
del teléfono no las recorte.

**Por qué.** Es lo que hace la barra de Apple: las etiquetas no crecen; el visor
de contenido grande es la alternativa accesible.

## D14 · Versión 1.1.0 y builds

**Decisión.** `version` 1.1.0 en `app.config.ts` y `package.json`;
`runtimeVersion` sigue la versión de la app (`appVersion`), así que pasa a 1.1.0
y ninguna actualización por aire llega a la 1.0.0 (que no tiene
`expo-glass-effect`). Android: el perfil `preview` fija `buildType: "apk"`; el
`staging` hace AAB para la pista interna; `submit.staging.android` lleva
`track: internal` y `serviceAccountKeyPath` desde un secreto de archivo de EAS
(`GOOGLE_SERVICE_ACCOUNT_KEY`). Nada se lanza sin que Luis lo pida.

## D15 · Sin dependencias nuevas

Todo se hace con lo que ya hay: React Native, expo-router, react-native-screens,
Reanimated, `expo-glass-effect` (042) y `expo-symbols`. No entra ningún paquete:
la puerta de licencias queda en «ninguna» y el cliente de desarrollo instalado en
los simuladores sigue sirviendo (sin compilar nativo).

## Licencias (constitución §VIII)

Ninguna dependencia nueva (D15).
