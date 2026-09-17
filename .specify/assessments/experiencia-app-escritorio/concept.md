# Concept Exploration: la experiencia de la aplicación de escritorio

- **Slug**: experiencia-app-escritorio · **Fecha**: 2026-09-17
- **Entrada**: [`problem.md`](./problem.md) · [`research.md`](./research.md)

Cuatro decisiones abiertas (D1–D4) con opciones, y ocho transversales (T-1…T-8)
que hay que tomar igual, con recomendación. Ninguna opción reabre las
restricciones de `research.md` §5 sin decirlo.

---

## D1 · El armazón: ¿cómo conviven la consola y la pantalla de operar?

### Opción A — Una sola aplicación: el armazón es local, la consola es el panel de contenido **(recomendada)**

La vista local ocupa la ventana entera y es dueña del **chrome**: franja superior
con los semáforos integrados (`titleBarStyle:'hidden'` + `trafficLightPosition`) y
**sidebar único**. La `WebContentsView` de la consola se coloca **dentro del
rectángulo de contenido**, a la derecha del sidebar y bajo la franja superior,
cuando la sección activa es de administrar.

```
┌──────────────────────────────────────────────┐
│ ● ● ●   Auphere            ⌘K   [estado]     │  franja: la app (drag)
├───────────────┬──────────────────────────────┤
│ Hoy           │                              │
│ Pendientes  3 │   pantalla de operar (local) │
│ ─ Teammates   │        · o ·                 │
│   Sofía       │   consola embebida (vista)   │
│   Marco       │                              │
│ ─ Administrar │                              │
│   Clientes    │                              │
│   Consumo     │                              │
│   Facturación │                              │
│   Puesto      │                              │
│ ─────────────  │                              │
│ Adrián · Pro  │                              │
│ 34 % · máquina│                              │
└───────────────┴──────────────────────────────┘
```

- **Por qué encaja**: la consola sigue sin `preload` (002 R12.1) — no gana ningún
  canal; solo cambia **dónde se pinta** y que su propio armazón se oculta en modo
  embebido. Resuelve de una vez: una navegación, ⌘1/⌘2 innecesario, el paywall
  aterriza en el panel, «volver» deja de ser un problema.
- **Qué exige**:
  - `apps/console`: **modo embebido** por user-agent (`AuphereDesktop/x`) que
    oculta su sidebar y su cabecera. Toca `shell-detect` y sus tests.
  - Un canal de empuje nuevo (`app:console.location`) para que el sidebar marque
    la sección activa, y uno de invocación (`app:layout.content`) con el
    rectángulo del panel cuando la persona redimensiona el sidebar. **Enmienda**
    del contrato 003, sin credenciales (solo números y una ruta).
  - Disciplina de arrastre: la consola **nunca** solapa la franja superior
    (electron#43320). Spike de 1 h en el plan para confirmarlo.
- **Riesgos**: la consola tiene su propia estética y ritmo de despliegue; si el
  modo embebido se rompe, la sección administrar se ve doble. Mitigación: el modo
  embebido es una clase CSS servida por layout, con test en consola.

### Opción B — Dos superficies, con chrome común

Una cuarta vista fina arriba (chrome) con los semáforos, un conmutador
`Equipo | Consola` y el estado de la máquina. Cada superficie conserva su
navegación.

- **Pros**: no toca `apps/console`; menos IPC nuevo.
- **Contras**: siguen dos sidebars y dos vocabularios; la franja superior la pinta
  otra vista, justo el caso del issue #43320; el paywall sigue cambiando de mundo.
  **No cumple G1.**

### Opción C — Todo nativo; la consola al navegador

La app reimplementa lo de administrar o lo abre fuera.

- **Contras**: reimplementar choca con 003 R12.6 y duplica el trabajo de 001–007;
  abrir fuera pierde la sesión compartida (la cookie vive en la partición) y
  obliga a entrar dos veces. **Descartada.**

### Opción D — Pulir sin cambiar la estructura

Barra de título integrada, fuentes, estados y copy; seguir con ⌘1/⌘2.

- **Pros**: la mitad de coste; cero enmiendas de contrato.
- **Contras**: deja en pie «son tres apps pegadas», que es el problema 1. Sirve
  como plan B si D1-A se demuestra inviable en el spike.

---

## D2 · La barra del puesto de 44 px

### Opción A — Se absorbe en el armazón **(recomendada, coherente con D1-A)**

El estado de la máquina pasa al **pie del sidebar** (chip con punto y nombre) y a
la tarjeta «Tu máquina» de Hoy; **emparejar** es un diálogo de la app; **declarar
directorios**, una hoja de la app o un panel en Ajustes.

- **Resuelve P0-2** (las hojas no caben) por construcción, y P1-10 (la barra no se
  alcanza con teclado).
- **Qué exige**: mover `pair`, `unpair`, `pickDirectory` y el estado del puesto al
  contrato de la pantalla (**enmienda** de 002 y 003); retirar la partición
  `auphere-bar` (de cuatro a tres, con su test); trasladar las prohibiciones de
  `no-own-auth` a la vista de la app.
- **Argumento de seguridad**: la barra fue la superficie mínima de la 002 *porque
  la pantalla de operar no existía*. Desde la 003 existe, con `sandbox`,
  `contextIsolation`, preload de lista cerrada y `redact`. Absorberla **reduce**
  superficie (una partición y un preload menos) en vez de ampliarla. El código de
  emparejamiento lo teclea la persona y lo canjea el proceso principal: ninguna
  credencial cambia de sitio.

### Opción B — Sobrevive, arreglada

Se le permite crecer (el principal le da altura cuando abre una hoja) y se le
añade foco por teclado.

- **Pros**: no enmienda contratos; el trabajo es menor.
- **Contras**: mantiene una cuarta voz tipográfica y un segundo sistema de
  botones; el estado de la máquina sigue lejos de donde se decide; la franja
  inferior es justo donde la HIG pide no poner nada crítico.

---

## D3 · Dirección del modo oscuro

### Opción A — Tinta neutra cálida, verde como acento **(recomendada)**

Superficies derivadas de `rich-black` con croma muy bajo en el matiz verde de la
marca; el verde queda para primario, positivo, foco y datos.

- **Por qué**: arregla los pares medidos (hoy `--card` oscuro es
  `bangladesh-green`, con error a **1,24:1** y texto apagado a 3,83:1); es lo que
  hacen Linear (grises cálidos, «no compitas por atención que no te has ganado»)
  y Claude; y `brand-system.md` ya admite `--ink` como superficie inmersiva.
- **Coste**: toca tokens compartidos → cambia también consola y admin. Es un
  cambio visible, y es el momento de hacerlo (el contraste está mal hoy).

### Opción B — Verde inmersivo, corregido

Se mantiene el verde oscuro como superficie y solo se oscurece `--card` y se
recolocan los tonos de estado hasta pasar AA.

- **Pros**: cambio mínimo, la identidad actual se conserva tal cual.
- **Contras**: el verde saturado como fondo de trabajo de ocho horas compite con
  el contenido y deja poco margen para que el verde signifique algo.

En ambos casos el tema claro sigue en `bone` y el sistema decide por defecto
(`nativeTheme.themeSource`, T-5).

---

## D4 · El corte: ¿una spec o varias?

### Opción A — Una spec con historias priorizadas e independientes **(recomendada)**

`specs/010-experiencia-app-escritorio/`, con seis historias que entregan valor por
separado:

| Prioridad | Historia | Entrega sola |
|---|---|---|
| P1 | **Armazón y sistema visual**: chrome integrado, sidebar único, menús y atajos, fuentes, tokens de escritorio, ⌘K | Una app que se siente app, aunque el resto siga igual |
| P2 | **Estados honestos**: sin conexión ≠ sin sesión, arranque sin destello ni mentiras, error de hilo, estados del turno, cierre = ocultar | La pantalla deja de mentir |
| P3 | **Feedback estandarizado**: taxonomía, un solo contador, notificaciones con motivo, avisos de actualización | Se entiende qué pasa y qué falló |
| P4 | **Primer arranque y activación**: entrar desde la app (cierra 009-T029), emparejar sin salir, checklist, permisos en contexto | Un partner nuevo llega solo al primer valor |
| P5 | **Llevar a la acción**: topes de plan y consumo con destino exacto, traspaso al navegador y vuelta, Cuenta con plan y saldo | La app convierte en vez de explicar |
| P6 | **Pendientes y aprobaciones**: contexto para decidir, teclado, foco desde la notificación | Se aprueba sabiendo qué se aprueba |

Accesibilidad (WCAG 2.2 AA) y el glosario no son historias: son **requisitos
ubicuos** que cada historia cumple.

- **Pros**: un solo `tasks.md` (regla del repo), una sola revisión de coherencia,
  el armazón se decide una vez.
- **Contras**: spec grande (estimación: 90–120 tareas). Mitigación: las historias
  se implementan y verifican en orden, con `/speckit-analyze` antes de empezar.

### Opción B — Tres specs (armazón · recorridos · monetización)

- **Pros**: cada una cabe en una semana; menos riesgo de spec inabarcable.
- **Contras**: el armazón condiciona a las otras dos y las tres tocarían los mismos
  archivos; tres Constitution Checks para una sola decisión de producto.

### Los P0 que son defectos de specs anteriores

| P0 | Propuesta |
|---|---|
| P0-1 entrar con Google sin disparador | **Dentro de la spec** (historia P4): la pantalla que lo dispara es nueva; cierra `009-T029` y lo declara |
| P0-2 hojas de la barra invisibles | **Dentro** (D2-A las elimina por construcción) |
| P0-3 arranque y red | **Dentro** (historia P2) |
| P0-5 hilo que falla se pinta vacío | **Dentro** (historia P2) |
| P0-4 404 tras pagar | **Fuera**: es de la consola y afecta también a la web → flujo de bugs, ya abierto aparte |

---

## Decisiones transversales (no son opciones; hay que tomarlas)

- **T-1 · Cerrar la ventana oculta, no sale.** En macOS, `window-all-closed` deja
  la app viva con su icono de bandeja y sus avisos; «Salir» es explícito y avisa
  si hay trabajo vivo. Hoy el vacío del hilo promete justo eso y la app lo
  incumple.
- **T-2 · Un solo derivado de «lo que te espera»**, consumido por sidebar, Dock,
  bandeja del sistema y la vista Pendientes. Un único módulo puro con test.
- **T-3 · Una API de feedback** (`notify({ severidad, alcance, persistencia,
  acción })`) que elige el mecanismo según la taxonomía de `research.md` §1.4.
  Regla dura: **ningún error de datos o de agente en un toast**.
- **T-4 · Fuentes empaquetadas** (`@fontsource-variable/inter-tight` y
  `jetbrains-mono`, OFL-1.1) y **CSP en la vista de la app** con `font-src 'self'`.
  Cierra los dos huecos del anexo 02 §1.
- **T-5 · Un solo tema para la ventana**: preferencia de la cáscara (`theme` ya es
  persistible) aplicada con `nativeTheme.themeSource`, que arrastra a la consola
  embebida. Por defecto, Sistema.
- **T-6 · Capa de densidad de escritorio en `@nexus/ui`**: texto de UI 13 px, fila
  de sidebar 28 px (32 con avatar), control 28 px, objetivo mínimo 24 px, radios
  concéntricos, y un token de foco con **≥3:1 en ambos temas** que la app no
  sobrescribe. Iconos Lucide 16/20 px.
- **T-7 · Glosario único**: «teammate» (no «agente», no «Companion»), «pool
  semanal» (no «tope mensual»), «puesto de trabajo», «pendiente». El paquete
  `companion-ui` recibe el nombre del interlocutor por contexto.
- **T-8 · Traspaso al navegador explícito**: cuando una acción sale (entrar,
  pagar, comprar saldo), la ventana muestra un estado de espera con «Abrir de
  nuevo», «Copiar enlace» y «Cancelar», y **refresca al recuperar el foco**.
  Vale para Google y para Stripe.

---

## Apetito y coste

| Historia | Apetito | Nota |
|---|---|---|
| P1 armazón y sistema visual | **alto** | Es el cambio estructural; incluye el spike de arrastre y el modo embebido de la consola |
| P2 estados honestos | medio | Sobre todo proceso principal y rutas |
| P3 feedback | medio | Taxonomía + cableado del updater |
| P4 primer arranque | medio-alto | Depende de P1; cierra un pendiente de la 009 |
| P5 llevar a la acción | medio | Depende de la consola embebida (D1-A) |
| P6 pendientes | bajo-medio | Reutiliza tarjetas que ya existen |

**Superficie de confianza (§II)**: `0` (API de la consola) y el tramo ya abierto de
`3a`. **No abre superficie nueva**: no hay esquema propio, no hay oyente nuevo, no
hay credencial nueva; si se acepta D2-A, se **cierra** una partición.

**Qué se mide**: nada nuevo. No consume modelo ni reloj de máquina; el consumo que
la app enseña sale del medidor de 004.
