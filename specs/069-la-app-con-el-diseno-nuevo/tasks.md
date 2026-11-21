# Tasks: La app con el diseño nuevo (069)

**Input**: [spec.md](spec.md) · [plan.md](plan.md)
**Regla de ejecución**:
- test primero (constitución VII);
- `pnpm verify` en verde antes de dar una fase por hecha;
- después de cada verde, un parche en `.claude/commits/069/`;
- los archivos compartidos tienen una sola mano (plan, D11);
- `[P]` = paralelo, porque toca archivos de otra área.

## Fase 1 — Preparación

- [x] T001 Rama y worktree `069-la-app-con-el-diseno-nuevo` desde `origin/develop` (70d8da81); base en verde: 38 suites, 442 tests. _Requisitos: 20.2_
- [x] T002 Comprobar que no se añade ninguna ruta de API: `openapi.json` igual al de `develop` al cerrar. _Requisitos: encabezado (aislamiento)_
- [x] T003 Dependencias con su licencia leída: `react-native-svg` 15.16.0 (MIT), `@shopify/react-native-skia` 2.14.0 (MIT) y `lucide-react-native` 1.77.0 (ISC). Nota en `docs/licenses/`. _Requisitos: 1.3, 5.1_
- [x] T004 Interruptor de Helvena (`APP_HELVENA=1` y TTF en `assets/fonts/helvena/`, ignorados por git). **Apagado en todos los builds** hasta leer la licencia. _Requisitos: 1.4, 1.5_
- [x] T005 Versión 1.3.0 y su test. _Requisitos: 22.1_

## Fase 2 — Sistema (bloquea las pantallas)

- [x] T010 Roles de app y de marca en `scripts/gen-tokens.mts`, y `tokens.gen.ts` regenerado. Test: `controlBorder` ≥ 3:1 sobre `card`, `background` y `muted`, en claro y oscuro (`v13-revision-aa`). **Corregido al cierre:** estaba marcada sin el rol ni su test (revisión, H11). _Requisitos: 1.1, 1.2, 3.5_
- [x] T011 `theme/fonts.ts` (`DISPLAY_FONT`) y estilos `display` en `type.ts`. Ningún peso por encima de 600: test en `v13-nada-se-pierde`, que barre la escala y todo `src` (añadido al cierre, analyze S2). _Requisitos: 1.4–1.7_
- [x] T012 Escala de radios en `theme/theme.ts`. _Requisitos: 1.10_
- [x] T013 `ui/icon.tsx` con Lucide detrás de la misma API; `ui/brand-icons.tsx` con WhatsApp, Instagram y Messenger. Los iconos del sistema siguen en el cromo nativo. _Requisitos: 1.3_
- [x] T014 `motion/micro.ts`: dibujar el ✓, cifra que corre, latido, llegada y fundido, con su alternativa para Reducir movimiento (tests). _Requisitos: 2.1, 2.4, 2.5_
- [x] T015 Toast con barra de tiempo y «Deshacer»: 6 s (decisión 8 de `log.md`), y 20 s con lector de pantalla (revisión, H10). _Requisitos: 2.1(6), 3.3_
- [x] T016 Piezas:
  - chip con ✓ que se dibuja;
  - tarjeta resumen;
  - fila compacta con insignia de canal;
  - vacío que tranquiliza;
  - tarjeta sin conexión con «Lo guardado a las HH:MM»;
  - diálogo con icono en su tono: **no se hizo**, porque se usan las alertas del sistema (decisión 7 de `log.md`).

  _Requisitos: 2.1, 3.1, 3.2_
- [x] T017 Modo de datos de ejemplo: `DEMO` en `config.ts`, transporte en `client.ts`, `demoEvents` en `sse.ts` y Reservas con `reservas-demo`. Test: fuera de `__DEV__` nunca está activo. _Requisitos: 23.1–23.3_
- [x] T018 Textos por área (`i18n/v13-*.{es,en}.ts`) registrados. _Requisitos: 1.1_

## Fase 3 — Arreglos visibles (test en rojo primero)

- [x] T020 [P] Contacto con canal e identificador reales. _Requisitos: 12.1, 21.2_
- [x] T021 [P] Gasto del mes en la moneda de la bolsa. _Requisitos: 21.1, 8.1_
- [x] T022 [P] Precio de servicio por unidad menor y con decimales. _Requisitos: 14.4, 21.1_
- [x] T023 [P] Teléfono obligatorio en Nueva reserva y en la lista de espera (salvo en persona). _Requisitos: 15.1, 16.1_
- [x] T024 [P] Ventana del agente vencida y «Se cerró por inactividad». _Requisitos: 11.5, 11.7_

## Fase 4 — Pantallas (áreas en paralelo después de la Fase 2)

- [x] T030 [P] **Inicio**: cuatro tarjetas, lo último, quien espera y la tarjeta calma. Sin las tarjetas de los módulos que no tiene el cliente. _Requisitos: 8.1–8.5_
- [x] T031 [P] **Bandeja**:
  - grupos por día;
  - filas compactas;
  - chips con ✓ y selector de canal;
  - quien espera primero;
  - deslizar con «Deshacer» y acciones accesibles;
  - llegada en vivo;
  - páginas;
  - pie sin canal;
  - filtro por agente.

  _Requisitos: 9.1–9.8, 3.4_
- [x] T032 [P] **Búsqueda**: pestaña de búsqueda en iOS 26 si la API de `NativeTabs` lo permite, y cabecera de la Bandeja en todas. _Requisitos: 10.1–10.3_ (hecha en la cabecera de la Bandeja). **Abierto para la 070:** la pestaña de búsqueda nativa de iOS 26, que pide expo-router 58.0.26 o posterior y el simulador (decisión 10 de `log.md`).
- [x] T033 [P] **Conversación**:
  - cabecera;
  - dock;
  - «Tomar el control» (coreografía y toast «Devolver»);
  - enviar (micro 7);
  - «Corregir»;
  - menú con vaciar y eliminar;
  - publicación del comentario.

  Se conserva todo lo de hoy. _Requisitos: 11.1–11.8_
- [x] T034 [P] **Contacto**: primera vez, conversaciones y próxima reserva. _Requisitos: 12.1, 12.2_
- [x] T035 [P] **Reservas**:
  - tira de días;
  - lista y cuadrícula;
  - hueco libre → Nueva reserva;
  - Semana y Mes;
  - Aforo;
  - estados del calendario.

  _Requisitos: 13.1–13.7_
- [x] T036 [P] **Una reserva**: acciones de la API, cancelar con aviso y oferta, mover y pedir confirmación. _Requisitos: 14.1–14.4_
- [x] T037 [P] **Nueva reserva y lista de espera**: horas de mañana y tarde, confirmar antes de cerrar, ofertas con «Parar». _Requisitos: 15.1–15.4, 16.1–16.3_
- [x] T038 [P] **Ajustes de reservas y de la Bandeja**: antelación, recordatorios y cierre por inactividad. Lo de la web como lectura. _Requisitos: 17.1–17.3_
- [x] T039 [P] **Consumo**: cuánto dura, cifra que corre y sin recarga. _Requisitos: 18.1–18.3_
- [x] T040 [P] **Ajustes**: canales conectados, confirmación del urgente, privacidad, soporte y borrado. _Requisitos: 19.1–19.3_
- [x] T041 **Entrar**: el líquido de la 066 en Skia (`scripts/gen-liquid.mts` → `liquid.gen.ts`), errores por campo y estado sin conexión. _Requisitos: 5.1–5.5_
- [x] T042 **Recuperar y preaviso de avisos**: dirección, cambiar y reenviar a los 30 s; ejemplo real antes del permiso del sistema. _Requisitos: 6.1–6.3, 7.1–7.3_
- [x] T043 **Android en Material 3**: superficies tonales en lugar de vidrio, y las mismas funciones. _Requisitos: 4.1–4.3_

## Fase 5 — Cierre

- [x] T050 La red de «nada se pierde»: los 442 tests de partida siguen o se enmiendan con motivo en `log.md`. Un test por cada función del Requisito 20, con el mapa en `log.md` (analyze S1). Dos huecos cerrados al cierre con `v13-nada-se-pierde`: la pantalla de «Actualizar» y el menú de adjuntos. _Requisitos: 20.1, 20.2_
- [x] T051 `pnpm verify` y `./scripts/verify.sh mobile` en verde. _Requisitos: todos_
- [x] T052 Emulador de Android en claro y oscuro con datos de ejemplo, con capturas en `evidence/` (**hecho**). **Simulador de iOS 26** (**hecho la mañana del 2026-11-21**, iPhone 13 con iOS 26.0): es puerta de la 070 (analyze H3; R22.5).
  - Con texto grande, «Conversaciones» cabe en una línea en iOS: el guion de corte es solo de Android. La cápsula de Contacto sale entera.
  - Cuatro arreglos con su test: botones con icono, «Pedir confirmación» partido, imagen que no carga y «Salir sin guardar». Además, la caída de las categorías de avisos. Todo en `log.md`, «iOS en el simulador».
  - Lo que sigue abierto en iOS pasa a T060 (búsqueda nativa, VoiceOver) y a T061 (la caída y «Salir sin guardar» en un build de EAS).

  _Requisitos: 1, 3, 4, 22.5_
- [x] T053 Puertas del workspace: `ui-states-checklist`, `a11y-audit`, `responsive-audit` y `design-tokens`, sobre lo construido. _Requisitos: 3_
  - Informe en `revision.md`.
  - Los siete fallos AA (H04, H06–H10, H12) están arreglados, cada uno con su test.
  - Lo que queda abierto está en `log.md`, tabla de la revisión.
  - **Pendiente:** una pasada viva con TalkBack, y otra con VoiceOver cuando haya simulador. `responsive-audit` corrió al cierre en el emulador: siete pantallas a 360 dp de ancho y texto a 1,3, en español (`evidence/android-estrecho-grande-*.png`).
- [x] T054 `docs/app-movil.md` (spec viva) y `apps/mobile/AGENTS.md` (iconos y letra). _Requisitos: encabezado (Lo que enmienda)_
- [x] T055 `quickstart.md` para probarla mañana, `log.md` y el guion de commits en `.claude/commits/069/` del checkout principal (fuera del worktree a propósito: el guion entra en él). _Requisitos: —_
- [ ] T057 **Puerta de la 070:** tocar un aviso real con la app cerrada y con la app en segundo plano, en un build de preview o staging de Android (revisión, H01). Al llegar, la barra de pestañas tiene sus iconos y la tarjeta «Atender a…» de Inicio se ve entera, sin quedar bajo la barra. Mirar también un arranque en frío de release: en desarrollo los iconos llegan unos segundos tarde. Si falla, Inicio necesita en Android un `paddingBottom` del alto de la barra más 16. _Requisitos: 7, 8.4_
- [ ] T058 **Puerta de la 070:** recorrer en Android lo del Requisito 20 que no se vio en el emulador (mapa en `log.md`):
  - Aforo: Llegó, No vino, la llegada sin reserva, los bloqueos y la Semana de ocupación;
  - Ajustes de reservas;
  - los avisos con sus enlaces;
  - «Actualizar», «Sin acceso», «No es cliente» y Entrar con Google;
  - el filtro por agente;
  - las respuestas guardadas;
  - el motivo del envío fallido.

  Con un negocio de Aforo de ejemplo o en staging. _Requisitos: 4.2, 20.1; SC-002_
- [ ] T059 Hallazgos de la revisión que rompen un DEBE y piden decisión de Luis (analyze S8):
  - **H03:** el dock de «espera» repite el motivo y pone ámbar fuera del icono (R1.2). Propuesta: una franja «{agente} pidió ayuda: {motivo}» con «Atender a {nombre}», el ámbar solo en la mano.
  - **H05:** la barra de Android solo rotula la pestaña elegida (R4.1, Material 3). Propuesta: etiquetas siempre visibles, si `NativeTabs` lo expone en expo-router 58; si no, un issue.
  - **H20:** dos escalas de radio (R1.10). Propuesta: `radius.sm/md` → `RADII` y `SHEET_RADIUS` → `RADII.sheet`, 31 usos, en un cambio aparte.

  _Requisitos: 1.2, 1.10, 4.1_
- [ ] T061 **Puerta de la 070:** iOS con builds de EAS, no con el de Xcode 26.0.1 de este Mac (`log.md`, «iOS en el simulador»).
  - **La caída de las categorías de avisos** (fallo de Expo expo/expo#52462, sin arreglo publicado):
    - la prueba que separa las causas, **hecha la tarde del 2026-11-21**: con el build `development-simulator` de EAS (Xcode 27.1) en el mismo simulador, 0 caídas en 21 arranques, también con el código de `develop` y con recarga. El fallo es del build local con Xcode 26.0.1; no es un P0 (`log.md`, «Con el build de EAS»);
    - después, diez arranques en frío del build de staging de la 069 en un iPhone real, con la app recién instalada;
    - si alguno se cae, registrar las categorías en nativo (config plugin con `UNUserNotificationCenter.setNotificationCategories` y los textos en `InfoPlist.strings`) y quitar la llamada de JS;
    - si sale un expo-modules-jsi con el arreglo, subirlo es otro cambio, con su lockfile y su `/cso`.
  - **«Salir sin guardar» (R15.3):** en ese build de staging, deslizar Nueva reserva un segundo después de elegir una hora. En desarrollo, la hoja se cerraba antes de la pregunta y lo elegido se perdía. Si pasa también ahí, quitar el gesto de cerrar en cuanto se toca el formulario, no al cambiar el dato.

  _Requisitos: 15.3, 20, 22.5_
- [ ] T060 Lo que quedó abierto dentro de tareas ya marcadas, y lo aplazado de `/cso` (analyze S6, S7, N3):
  - una pasada viva con TalkBack, y otra con VoiceOver cuando haya simulador (de T053). En TalkBack, confirmar que el aviso con «Deshacer» se oye **una sola vez**: en Android lo dice su región viva y en iOS el anuncio (`ui/toast.tsx`);
  - la pestaña de búsqueda nativa de iOS 26, con expo-router 58.0.26 o posterior (de T032). Sigue sin probar: el simulador de la mañana del 2026-11-21 tiene expo-router 58.0.25;
  - fijar `lucide-react-native` a `1.77.0` exacta (`cso.md`, L1);
  - teléfonos y cuentas del negocio de ejemplo claramente inventados antes de hacer capturas de tienda: hoy tienen formato de móvil real (`cso.md`, L4; R23.3);
  - que `app.config.ts` falle si Helvena se enciende fuera de desarrollo mientras no haya licencia (`cso.md`, I2);
  - los 26 avisos de `pnpm audit` en herramientas de build, anteriores a la 069, en una tarea aparte (`cso.md`, I3).

  _Requisitos: 3, 10.2, 23.3_
- [ ] T056 Medir en un teléfono real el arranque frente a la 1.2.0, la Bandeja con 1.000 conversaciones y los fps del líquido en un Android de gama media. **Queda para Luis**: esta noche no hay dispositivo. **Es puerta de la 070**: sin estas medidas, no hay envío. _Requisitos: 22.2–22.5_
