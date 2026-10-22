# Quickstart: cómo se verifica la spec 042

Lo que hay que ver, en qué orden y con qué, historia por historia. Lo que
pide un dispositivo o un runtime que no está en la máquina queda marcado.

## Requisitos previos

- **La tubería local en verde**, siempre primero:

  ```bash
  ./scripts/verify.sh mobile
  ```

- **El build de simulador de iOS 26** (D16), compilado en la nube e instalado
  en el runtime local 26.0.1. Se hace una vez por iteración:

  ```bash
  cd apps/mobile && eas build -p ios --profile development-simulator
  ```

  El simulador de referencia es **«13 26»** (iPhone 13, iOS 26.0.1, runtime
  `com.apple.CoreSimulator.SimRuntime.iOS-26-0`): Luis pidió el 2026-10-21
  medir en un iPhone 13 y no en el SE, y en esta máquina solo cabe un
  simulador arrancado a la vez (disco). Los dos de antes («SE 26», «17 26»)
  se borraron; las dos capturas de Inicio del SE se conservan como histórico.
  Si hay que recrearlo:

  ```bash
  xcrun simctl create "13 26" "iPhone 13" com.apple.CoreSimulator.SimRuntime.iOS-26-0
  ```

  Después, `xcrun simctl boot "13 26"`, `xcrun simctl install booted <ruta
  del .app>` y `pnpm start` para Metro. Las capturas se toman con `xcrun
  simctl io <udid> screenshot`; en un build de desarrollo, apagar antes el
  botón flotante del dev client (menú → «Tools button»), que tapa el botón
  de Ajustes.

- **El emulador de Android** de la 031, con la pila local arriba. El build de
  desarrollo de Android está en EAS (`eas build -p android --profile
  development`, 2026-10-21, build `f6f47ac2`; la primera vez crea el keystore
  de desarrollo en la cuenta). El APK de desarrollo (~280 MB) no cabe en los
  6 GB de datos por defecto del AVD del Pixel 9: el pase del 2026-10-21 se
  hizo en un AVD temporal con la misma imagen y `disk.dataPartition.size=8G`,
  borrado al terminar. `adb reverse tcp:8081` y `tcp:8000` se caen a ratos:
  si la app dice «No hay conexión», volver a ponerlos
  (`docker compose up -d`).
- **Las skills de revisión** en `apps/mobile/.claude/skills/`
  (`npx skills experimental_install` si faltan).

### Cambiar la apariencia del simulador sin tocar la pantalla

```bash
xcrun simctl ui booted appearance dark
```

```bash
xcrun simctl ui booted increase_contrast enabled
```

```bash
xcrun simctl ui booted content_size accessibility-extra-extra-extra-large
```

«Reducir transparencia» y «Reducir movimiento» se activan en el simulador:
Ajustes › Accesibilidad › Pantalla y tamaño del texto, y › Movimiento.

## 1. Spike S2 (D18), antes de nada

En `.specify/assessments/042-s2-vidrio-en-el-pie/`, con el build de arriba.
Una captura o un vídeo corto por fila de la tabla de D18, y una línea con el
resultado. Lo que decide: D3 (vidrio que sigue la altura), D4 (teclado), D6
(búsqueda), D7 (hoja), D2 (botones de barra) y D5 (transparencia).

## 2. Historia 2 · Inicio dice cada cosa una vez (CE-001, R5)

- `pnpm test --ci -- inicio`: el número de espera aparece una vez; sin nada
  pendiente no hay cifra a cero; sin módulo de Consumo no hay fila navegable;
  con saldo bajo y espera, dos filas con un dato cada una.
- En el emulador de Android y en «13 26», con tres clientes de semilla:
  con dos conversaciones esperando, sin nada pendiente, con saldo bajo.
- **CE-002 (Inicio)**: en «13 26», al tamaño de texto por defecto, la atención
  y el dinero se ven sin desplazar. Captura `evidence/capturas/ios26-se-inicio-claro.png`.

## 3. Historia 5 · Saber a dónde lleva cada cosa (R6, R8, R9)

- `pnpm test --ci -- consumo ajustes-avisos`: el selector no existe sin gasto;
  la fila externa dice el destino; cerrar sesión y borrar están en grupos
  distintos y solo el borrado va en peligro; el pie del borrado existe.
- A mano, en Android: contar las formas de ir a otro sitio en Inicio, Consumo
  y Ajustes. Tienen que ser dos: chevrón y enlace externo.
- Con el teléfono en inglés, el botón de atención dice «Answer now» (R9.3), y
  la consola web lo mismo.

## 4. Historia 1 · Atender con el hilo a la vista (CE-002, CE-003, CE-004, R2)

- `pnpm test --ci -- atender hilo floating-surface`: la superficie es
  `GlassView` con vidrio y `View` sin él o con «Reducir transparencia»; los
  `testID` siguen; «Tomar el control» dispara la vibración de éxito.
- Maestro: `e2e/send-flaky.yaml` sigue pasando sin cambios.
- En «13 26», con una conversación en espera:
  - se ven el último mensaje, el motivo y «Tomar el control» sin desplazar
    (CE-002);
  - desde Inicio, dos toques hasta escribir (CE-003);
  - grabar el paso del panel al cuadro con «Grabar pantalla» del simulador y
    contar fotogramas: 240 ms, ningún fotograma sin controles, el hilo no
    salta (CE-004);
  - con «Reducir movimiento», es un fundido;
  - con el teclado abierto, el cuadro queda sobre el teclado y el último
    mensaje a la vista;
  - un hilo de un solo mensaje: el mensaje queda por encima de la superficie.
- Capturas: `ios26-13-conversacion-espera-{claro,oscuro}.png`,
  `ios26-13-conversacion-mia-teclado.png`.

## 5. Historia 3 · Legible siempre (CE-005, R4)

Para cada combinación, la misma pantalla con el contenido más desfavorable
debajo de la barra (una burbuja de color y una foto recibida en el hilo; la
Bandeja llena):

| | claro | oscuro |
|---|---|---|
| normal | ☑ 2026-10-21 | ☑ 2026-10-21 |
| «Reducir transparencia» | ☑ 2026-10-21 | ☑ 2026-10-21 |
| «Aumentar contraste» | ☑ 2026-10-21 | ☑ 2026-10-21 (H21 corregido en el pase) |
| texto al máximo | ☑ 2026-10-21 | ☑ 2026-10-21 |

- El contraste se mide sobre la captura, con el Medidor de color digital de
  macOS sobre el texto y su fondo, y la razón con `culori.wcagContrast` (ya
  está en `devDependencies`). Texto ≥ 4,5:1; iconos y controles ≥ 3:1. Se
  anota en `evidence/a11y.md`, por pantalla y combinación.
- El título crece con el texto y nunca queda más pequeño que el cuerpo (R4.6):
  Inicio en Android al 200 % (`android-inicio-oscuro-texto-200.png`) y en iOS
  en `accessibility-extra-extra-extra-large`.
- Cambiar oscuro, «Reducir transparencia» y «Aumentar contraste» con la app
  abierta: la app lo adopta sin reiniciar (R4.5).
- **Pendiente de Luis:** el vidrio claro o tintado (iOS 26.1) en un iPhone con
  26.1 o con un runtime nuevo (~7,5 GB).

## 6. Historia 4 · La navegación es de vidrio (CE-007, R1)

- En «13 26»: desplazar la Bandeja y ver las filas a través de las dos barras;
  la barra de pestañas se queda entera con la insignia a la vista (R1.5,
  enmendado el 2026-10-22: `ios26-13-h22-nunca-se-encoge.png`); los botones de la barra son
  cápsulas del sistema; Ajustes se abre a 0,6 y sube a 1; se cierra deslizando.
- Capturas: `ios26-13-bandeja-{claro,oscuro}.png`,
  `ios26-13-ajustes-hoja.png`.
- **CE-007, Android**: ninguna superficie imita el vidrio. Capturas
  `android-bandeja-{claro,oscuro}.png`.
- **CE-007, iOS < 26 (pendiente de Luis):** un iPhone con iOS 18 o un runtime
  nuevo. Las barras, el pie y las hojas se ven como en la 031.

## 7. Historia 6 · Formas y tacto (R7)

- `pnpm test --ci -- states`: al apoyar (`pressIn`) el botón cambia de fondo y
  no de opacidad; `disabled` baja el contraste del contenido.
- A mano, con Ajustes del sistema al lado: cápsulas, esquinas concéntricas en
  el botón de enviar, respuesta al apoyar el dedo; en Android, ondulación.
- Texto en iOS: cuerpo a 17 pt al tamaño por defecto; sin tracking en títulos.

## 8. Revisión heurística (CE-006)

Sobre todas las capturas de `evidence/capturas/`, con las skills:

1. `ux-heuristics`: severidades de 0 a 4; ninguna de 3 o 4 abierta.
2. `design-critique`: una crítica por pantalla.
3. `impeccable`, con `reference/ios.md` y `reference/audit.native.md`.

Los trece hallazgos de la auditoría se marcan cerrados en
`evidence/hallazgos.md`, cada uno con la captura que lo demuestra.

## 9. Lo que no cambia (R10)

- `pnpm test --ci` entero: las cifras, los estados, los nombres accesibles y
  los filtros siguen.
- `./scripts/verify.sh mobile` en verde, incluido `gen:check` tras regenerar
  el texto de D15 y `expo-doctor` tras instalar `expo-glass-effect`.
