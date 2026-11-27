# Tareas: el informe del piloto

**Entrada**: [spec.md](spec.md), [plan.md](plan.md), [research.md](research.md), [contracts/console-api.md](contracts/console-api.md).

**Pruebas**: obligatorias (constitución §VII). Cada prueba se ve en rojo antes de su implementación.

**Base de pruebas**: `NEXUS_DATABASE_URL=postgresql+asyncpg://nexus:nexus@localhost:5433/nexus_test_083`, `NEXUS_REDIS_URL=redis://localhost:6379/13`. Antes de lanzar: `ps -eo pid,etime,command | grep "[p]ytest"`.

Formato: `[ID] [P?] Descripción` · `_Requisitos: n.m_`. `[P]` = puede ir en paralelo (otro fichero, sin dependencias).

## Fase 1 — Pruebas en rojo

- [X] **T001** `apps/api/tests/unit/test_083_cycles.py`: el constructor de ciclos, puro. Casos: fila sin eventos (un ciclo abierto); resolver y reabrir el contacto (dos ciclos); reabrir una persona (deshace: un ciclo); dos `resolved` seguidos; `reopened` sin `resolved` previo; la zona de Caracas a las 23:30 locales. _Requisitos: 2.1, 2.2, 1.7_
  - *Avance 2026-11-26:* 25 en verde. Rojo visto (error de colección sin `services/client_report.py`). Añadidas las de D15 (eco con la hora de Meta, rojo visto) y la que fija que el `Literal` de `cause` cubre todo código posible.
- [X] **T002** `apps/api/tests/integration/console/test_client_report.py`: la ruta con una siembra que fija cada bloque. _Requisitos: 1.5, 1.7, 2.3–2.6, 3.1–3.4, 4.1–4.5, 5.1–5.7, 6.1–6.5, 7.1–7.4, 10.4_
  - ciclos: contacto que escribe, resuelve, vuelve (2); un aviso que reabre y nadie contesta (0); ciclo empezado antes del periodo con mensaje dentro (0); mensaje a las 23:30 de Caracas (su día local); Playground (0); importado (0);
  - con persona: tomada y devuelta (Bandeja, evento + auditoría = una), panel de operador, eco de coexistencia, escalado del agente, puerta, freno corregido;
  - primera respuesta: 5 s, 70 s con `latency_ms`, un envío fallido que no cuenta, un ciclo sin envío del agente;
  - incidencias: el freno que pasó la conversación cuenta una vez con `booking_unbacked`; el texto del agente no sale; resuelta y abierta;
  - agenda: alta del agente, de persona, importación (no cuenta), cancelación del agente con actor `customer` (cuenta como agente), «no» del cliente (cuenta como cliente), liberada; recordatorios enviados, fallidos, omitidos y `stale` (no cuenta);
  - gasto: la misma cifra que la fila del cliente en Consumo; y `spend: null` cuando la lectura falla;
  - periodo: 422 con cada código; cliente sin Reservas → `agenda: null`; vacío → ceros y `null` en los porcentajes.
  - *Avance 2026-11-26:* 14 en verde. Rojo visto (11 de 11 sin la ruta). Añadidas: el eco que abre la fila (D15, rojo visto con el margen a cero), `autoclose` con la regla del cron y el gasto igual a la fila del cliente en `/console/usage/summary` (D12). Sin probar: la estimación de Meta (`spend.meta`).
- [X] **T003** `apps/api/tests/integration/improvement/test_suggestions.py`: Rendimiento y su lista, con historial sembrado (tomada y devuelta = pasada a una persona; día local). _Requisitos: 9.1–9.3_
  - *Avance 2026-11-26:* las dos nuevas en rojo con el `performance.py` de HEAD y en verde con el nuevo. El fichero entero, en verde.
- [X] **T004** `apps/api/tests/isolation/test_client_report_scope.py`: partner A con el `ref` de B → el mismo 404 que un `ref` inexistente; dos clientes del mismo partner con datos → el informe de uno no cuenta nada del otro; ningún texto de un mensaje, nombre o teléfono en la respuesta. _Requisitos: 10.1–10.4_
  - *Avance 2026-11-26:* 3 en verde, rojo visto sin la ruta.
- [X] **T005** [P] `apps/console/src/components/report/__tests__/client-report.test.tsx`: los cinco estados (cargando, vacío, error con reintento, parcial con el gasto que falta, ideal), sin Reservas no hay agenda, la nota del cierre por inactividad, el encabezado de impresión y el tema claro al imprimir. _Requisitos: 8.1–8.7, 2.6, 6.5, 7.4_
  - *Avance 2026-11-26:* en verde. Rojo visto (no existía `client-report.tsx`). Cubre además los filtros (atajos, otro cliente, `min`/`max`, periodo imposible) y «Imprimir».
- [X] **T006** [P] `apps/console/src/components/report/__tests__/report-model.test.ts`: el periodo por defecto (30 días hasta hoy en la zona), la validación (al revés, más de 92 días, futuro), las columnas de la gráfica y los porcentajes. _Requisitos: 1.4, 1.5, 2.6_
  - *Avance 2026-11-26:* en verde, rojo visto (no existía `report-model.ts`).
- [X] **T007** [P] `apps/console/src/components/clients/v2/__tests__/`: la pestaña «Informe» aparece con los dos permisos y no sin ellos; `activeTab` la reconoce. _Requisitos: 1.1, 1.6_
  - *Avance 2026-11-26:* `client-header-report.test.tsx`, 4 en verde. Rojo visto en 3 (la cuarta, «sin permisos no existe», ya pasaba). Fija también que la cabecera del cliente no se imprime.

## Fase 2 — Backend

- [X] **T008** `services/improvement/performance.py`: `client_zone`, `build_spans`, los filtros de mensaje, `period_cycles` y `handed_to_person()` por historial. T001 en verde. _Requisitos: 2.1–2.5, 3.1–3.4, 4.1–4.5_
  - *Avance 2026-11-26:* hecho por la sesión anterior; esta añadió D15 (`SIGNAL_SLACK`, `owns_signal`) y arregló un error de `mypy --strict` en `person_signals`.
- [X] **T009** `services/improvement/performance.py`: `agent_performance` con ciclos y día local; `agent_conversations` con resultado y motivo por historial. T003 en verde. _Requisitos: 9.1–9.3_
  - *Avance 2026-11-26:* T003 en verde.
- [X] **T010** `services/client_report.py`: incidencias, freno, agenda, recordatorios y gasto. _Requisitos: 5.1–5.7, 6.1–6.5, 7.1–7.4_
  - *Avance 2026-11-26:* T002 en verde.
- [X] **T011** `api/console/client_report.py` y su montaje: la ruta, sus modelos y la validación del periodo. T002 y T004 en verde. _Requisitos: 1.5–1.7, 10.1–10.4_
  - *Avance 2026-11-26:* T002, T004 y la barrida `test_console_scope.py` en verde (1 730 en la tanda conjunta, sin skips).

## Fase 3 — Consola

- [X] **T012** `lib/backend/client-report.ts` y `backendFor`; `i18n/lanes/report.ts` y `messages.ts`. _Requisitos: 1.2, 8.5_
  - *Avance 2026-11-26:* `tsc` y las pruebas de `src/i18n` en verde. La clave de la pestaña (`clients.v2.tab.report`) vive en el carril `report`, no en `business`.
- [X] **T013** `components/report/{report-model.ts,report-filters.tsx,client-report.tsx}`. T005 y T006 en verde. _Requisitos: 1.2–1.5, 8.1–8.7_
  - *Avance 2026-11-26:* T005 y T006 en verde, `tsc` y eslint limpios.
- [X] **T014** La pestaña (`routes-v2.ts`, `client-header-v2.tsx`, `clients/[ref]/layout.tsx`), la página (`clients/[ref]/report/{page,loading,error}.tsx`) y la impresión en el marco (`console-shell-v2.tsx`). T007 en verde. _Requisitos: 1.1, 1.6, 8.7_
  - *Avance 2026-11-26:* T007 y las pruebas del marco en verde, `tsc` y eslint limpios. **Sin `next build` ni pasada viva** (T015 y T017): la impresión del marco no se ha visto en un navegador.

## Fase 4 — Cierre

- [X] **T015** Pruebas de lo tocado: `tests/unit/test_083_cycles.py`, `tests/integration/console/test_client_report.py`, `tests/integration/improvement/test_suggestions.py`, `tests/isolation/test_client_report_scope.py` y `tests/isolation/test_console_scope.py`; Vitest de lo tocado; `./scripts/verify.sh lint` y `./scripts/verify.sh js`.
  - *Avance 2026-11-26 (a medias):* pytest de lo tocado en verde (1 730 con `test_console_scope.py`); `ruff` y `mypy --strict src` limpios. Vitest: `src/components/report` y `src/components/clients/v2`, 98 en verde; `src/i18n` y `src/components/shell`, 178 en verde. `tsc` limpio, eslint de los ficheros tocados limpio.
  - *Cierre 2026-11-27:* `./scripts/verify.sh lint`, **15 de 15 en verde** (ruff, formato y `mypy --strict` de api, worker, channels, mcp y renderer). `./scripts/verify.sh js`: verde todo lo de la consola (lockfile, sin token de admin, `tsc`, eslint, **vitest 2 622 de 2 622**, **`next build` con `/clients/[ref]/report`**), `@nexus/ui` (332), companion-ui, desktop y el `next build` del panel. Fallaron dos pasos del panel (`tsc` y vitest), porque en un worktree recién instalado los `dist` de `apps/admin/packages/ucm-*` no existen y `verify.sh` llama a `tsc` sin el `pretypecheck` que los compila; la tubería sí lo corre. Con los `dist` ya compilados por el build, los dos en verde: `tsc` limpio y **vitest 861 de 861**. La 083 no toca `apps/admin`. Tras los arreglos de T017, otra vez `tsc`, eslint del informe y vitest de `report`, `clients/v2`, `i18n` y `shell`: **277 de 277**.
- [X] **T016** Puertas de interfaz: `ui-states-checklist`, `a11y-audit`, `responsive-audit` (360 px, 768 px, escritorio, zoom 200 %, texto largo) y `design-tokens`. _Requisitos: 8.6, 8.8_
  - *Cierre 2026-11-27, medido en el navegador (T017):*
    - **Estados**: cinco de cinco. Cargando con el esqueleto de los filtros, las cifras, la gráfica y dos bloques (`loading.tsx` y entre periodos, `aria-busy` y `role=status`). Vacío con ceros, «—» y la explicación. Error con «Reintentar». Parcial con el gasto sin leer y su propio «Reintentar». Ideal con Reservas, 14 incidencias y nombre alemán de 59 caracteres.
    - **Accesibilidad**: axe-core 4.13 (WCAG 2.0/2.1/2.2 A y AA y buenas prácticas) sin violaciones en claro, oscuro, 360 px, parcial, vacío y error. Ningún control por debajo de 24 × 24. Con movimiento reducido, las barras no se animan. El espaciado de texto de 1.4.12 no corta nada a 360 px. A teclado, el orden es cliente, desde, hasta, atajos, «Imprimir» y las tablas desplazables. **Del sistema de diseño, no de la 083**: el anillo de foco de `Input` y `NativeSelect` (`ring-ring/30`) da unos 1,3:1 sobre blanco.
    - **Responsive**: sin desplazamiento horizontal a 320, 360, 414, 640 (zoom 200 % de 1 280), 768, 1 024, 1 280, 1 440 y 1 920 px, con el nombre alemán. **Arreglado**: a 360 px las fechas se quedaban en el icono (37–41 px). Ahora tienen `min-w-36` y pasan a 149 px, con los atajos debajo. La gráfica de 30 columnas se desplaza dentro de `BlockChart`, como en Consumo.
    - **Tokens**: sin hex, `rgb`, estilos en línea ni paleta por defecto; espaciado en la rejilla de 4 px; radios del enum. Las únicas propiedades arbitrarias son `print-color-adjust`, `zoom` y `overflow-wrap`.
- [X] **T017** Pasada viva con el servidor de desarrollo: la pestaña, los filtros, los estados y la emulación de impresión. _Requisitos: 8.7, CE-004_
  - *Cierre 2026-11-27:* `next dev` en el 3183 contra una API simulada del contrato (fuera del repo, como las de `e2e/*-mock.mjs`), con un cliente por estado. Los atajos cambian la dirección y quedan pulsados (`aria-pressed`). El selector de cliente lleva a otro informe con las mismas fechas. «Ver las 14» alterna 10 ↔ 14 con `aria-expanded`. Sin Reservas no hay agenda. «Por debajo del objetivo» va en palabras, sin ámbar.
  - **Impresión, con el PDF A4 de Chromium y márgenes de 10 mm**: partiendo del tema oscuro, `beforeprint` pasa a claro y `afterprint` lo devuelve. Salen el encabezado propio y las barras en color, y no salen el marco, las pestañas ni los filtros. **Arreglado**: 30 días salían en **tres A4** (CE-004 pide dos). Los bloques con `break-inside-avoid` dejaban huecos, y la lista de recientes se partía en filas de 58–78 px. Ahora el informe se imprime con `print:[zoom:0.9]` y filas compactas (`[&_td]:print:py-1`, `[&_th]:print:h-auto`, `[&_th]:print:py-1`), con prueba en rojo antes (`client-report.test.tsx`, CE-004). Resultado: Jemma, nombre alemán y sin Reservas en **dos A4**; vacío en una; 92 días en tres, con la gráfica entera. `print:[&_td]:py-1` (el orden al revés) Tailwind no lo genera.
  - Sin verificar: la impresión desde el diálogo de un navegador real (Safari y Firefox incluidos), solo el motor de PDF de Chromium. En `next dev`, la CSP bloquea los trozos de `loading.tsx`, también el de `(console)/loading.tsx`, que no es de la 083.
- [X] **T018** Documentación viva: `docs/console.md` (la pestaña Informe y qué mide) y el enlace a esta carpeta desde la nota de KB. _Constitución §IX_
  - *Cierre 2026-11-27:* `docs/console.md`, sección «Informe del cliente» (quién la ve, filtros, qué mide cada bloque, lo que no lleva, estados, impresión y pruebas) y el párrafo «Cómo cuenta Rendimiento» (la regla nueva y la de antes). Enlace a la spec, al guion y a la sección desde `research/2026-11-26-beta-jemma-p0-p1.md`.
- [X] **T019** El guion de commits en `.claude/commits/2026-11-26-083.sh`.
  - *Cierre 2026-11-27:* tres commits, sin atribuciones ni `uv.lock`: la spec; el backend con `docs/console.md`; y la consola. `bash -n` limpio y comprobado contra `git status`: cubre los 32 cambios y solo deja fuera `HANDOFF.md`. Sin ejecutar: lo corre Luis.

## Dependencias

T001–T007 primero (en rojo). T008 → T009 → T010 → T011. T012 → T013 → T014. T015–T019 al final.

## Decisiones de la implementación (2026-11-26, sin Luis; las revisa al final)

- **D15** (en la spec): una señal de persona hasta 10 minutos antes de que empiece un ciclo, y fuera del anterior, es de ese ciclo. El eco de la app del negocio lleva la hora de Meta, anterior a la fila o la reapertura que provoca.
- **El bloque del freno** solo sale si el cliente tiene Reservas o si el freno actuó en el periodo: sin Reservas no puede actuar, y un bloque a cero sería ruido (§V).
- **Las incidencias recientes**: se enseñan las 10 últimas, con «Ver las N» para el resto (hasta 100). Al imprimir salen solo esas 10, para que 30 días quepan en dos A4 (CE-004).
- **La columna del cliente final** en la agenda se llama «Contacto», como en la Bandeja, para no confundirla con el cliente del partner.
- **Las cifras de arriba** usan una tarjeta propia con los mismos tokens que `Metric`: las notas (objetivo, veredicto, por conversación) se parten en varias líneas en vez de cortarse.
- **Un periodo imposible en la dirección** (escrito a mano) abre el periodo por defecto, sin redirigir. Los campos no dejan pedirlo y la API contesta 422.
- **La clave de la pestaña** (`clients.v2.tab.report`) va en el carril `report`, no en `business`.
- **Imprimir al 90 % con filas compactas** (2026-11-27, T017): es lo mínimo con lo que 30 días caben en dos A4 con márgenes de 10 mm, también con nombres alemanes. Probados antes: apilar las dos tablas de incidencias (peor), dejar que los bloques se partan (no quita páginas) y zoom 0,85 solo (el caso alemán sigue en tres). En pantalla no cambia nada.
- **Las fechas con `min-w-36`** (2026-11-27, T016): a 360 px comparten fila con los atajos. Con `min-w-0` se quedaban en el icono del calendario.
