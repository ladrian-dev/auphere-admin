# Los hallazgos de la auditoría y los criterios de éxito — spec 042

Cada hallazgo de `research/2026-10-20-liquid-glass-app-movil` (KB) con el
requisito que lo cierra y la captura que lo demuestra. Sin captura no se
cierra. Lo que depende de Luis queda escrito con su razón, nunca como `skip`.

## Hallazgos

| # | Hallazgo | Sev. | Requisito | Captura que lo cierra | Estado |
|---|---|---|---|---|---|
| H1 | Inicio repite tres veces que alguien espera | 3 | R5.1–R5.3 | `capturas/ios26-se-inicio-claro.png`: «2» una vez en el contenido, más la insignia de la pestaña | cerrado 2026-10-21 |
| H2 | Inicio y Consumo duplican el dinero | 3 | R5.4 | `capturas/ios26-se-inicio-claro.png`: un solo grupo de dinero; Consumo con sus filas (`consumo.test.tsx`) | cerrado 2026-10-21 (captura de Consumo pendiente, T048) |
| H3 | Rejillas de tarjetas iguales | 2 | R5.5 | `capturas/ios26-se-inicio-claro.png`: lista agrupada y una cifra por bloque; `Metric` retirado | cerrado 2026-10-21 |
| H4 | El panel de «Tomar el control» tapa el hilo | 2 | R2 | | abierto |
| H5 | Tres maneras de ir a otro sitio | 2 | R6 | | abierto |
| H6 | Formas de la web | 2 | R7.1, R7.2 | | abierto |
| H7 | Ajustes junta cerrar sesión con borrar la cuenta | 2 | R8 | | abierto |
| H8 | Con el texto grande, la jerarquía se invierte | 2 | R4.6 | | abierto |
| H9 | Escala de texto de la consola | 1 | R7.3 | | abierto |
| H10 | Consumo abre repitiendo su título | 1 | R9.1 | | abierto |
| H11 | Gráfico vacío con selector de periodo | 1 | R9.2 | | abierto |
| H12 | «Attend» en inglés | 1 | R9.3 | | abierto |
| H13 | La insignia de atención cuenta otra cosa | 3 | R5.2 | `capturas/ios26-se-inicio-claro.png`: sin insignia junto al título | cerrado 2026-10-21 |

### Hallazgos nuevos del pase en simulador (2026-10-21)

| # | Hallazgo | Sev. | Requisito | Captura | Estado |
|---|---|---|---|---|---|
| H14 | **El título grande es invisible en iOS 26.** «Hola, Valeria» no se pinta: queda un hueco vacío bajo la barra de estado. Es el aviso del código de react-native-screens que recoge la D1 (fondo de color + título grande en iOS 26). Afecta a lo que hoy está en `develop`, en cualquier build hecho con Xcode 26 o 27. | 3 | R1.1, R4.6 (T064, T060) | Antes: `capturas/ios26-se-inicio-claro.png`. Después: `.specify/assessments/042-s2-vidrio-en-el-pie/evidence/09-inicio-reposo.png` (sin fondo en la cabecera, el título vuelve) | cerrado 2026-10-21 (T064); captura en `evidence/capturas/` pendiente de la pasada de US4 |
| H16 | **Tras «Reintentar» un error de `/me`, el contenido de Inicio y la Bandeja queda empujado ~120 pt bajo la cabecera transparente.** En reposo y tras un pull-to-refresh está bien; es el remontaje de las pestañas con la cabecera sin fondo (iOS 26 + react-native-screens). | 2 | R1.1 (T069) | `.specify/assessments/042-s2-vidrio-en-el-pie/evidence/06-inicio-rt.png` (primer intento) frente a `09-inicio-reposo.png` | abierto; US4 |
| H15 | **En un iPhone de 4,7″, «Ahora no» de la pantalla de avisos queda bajo el pliegue.** La hoja de la 031 (R10) enseña el título, los tres avisos y la nota de privacidad, y la acción secundaria solo aparece desplazando; la persona puede no saber que puede declinar. | 2 | Fuera de esta spec (031 R10.1). Propuesta: la nota de privacidad después de las acciones, o las acciones fijas al pie | `scratchpad` del pase (sin captura en evidencia; se repite al abrir su tarea) | abierto; para la 031 o una spec propia |

## Criterios de éxito

| CE | Qué | Evidencia | Estado |
|---|---|---|---|
| CE-001 | El número de espera, una vez en Inicio | `capturas/ios26-se-inicio-claro.png` y `inicio.test.tsx` (CE-001) | cerrado 2026-10-21 |
| CE-002 | Sin desplazar en «SE 26»: Inicio y la conversación en espera | Inicio: `capturas/ios26-se-inicio-claro.png`. Con dos avisos (espera y saldo), la atención entera y la fila del saldo se ven; «Gasto del mes» queda bajo la barra de pestañas. **Se vuelve a medir cuando H14 devuelva el título grande**, que ocupa el hueco que hoy está vacío. La conversación: pendiente (iteración 2) | parcial |
| CE-003 | Dos toques desde Inicio hasta escribir | | abierto |
| CE-004 | Panel → cuadro en ≤ 300 ms, sin fotograma vacío | | abierto |
| CE-005 | Contraste sobre vidrio en las ocho combinaciones | `a11y.md` | abierto; el vidrio tintado (26.1) pendiente de Luis |
| CE-006 | Revisión heurística sin severidad 3 o 4 | `revision.md` | abierto; las capturas de iOS < 26 pendientes de Luis |
| CE-007 | Nada imita el vidrio en Android ni en iOS < 26 | | abierto; iOS < 26 pendiente de Luis |
| CE-008 | Ninguna cifra difiere de la consola | `pnpm test --ci` | abierto |

## Skills de revisión instaladas (T004)

Instaladas en `apps/mobile/.claude/skills/` el 2026-10-20 (fuera de git;
`npx skills experimental_install` las restaura desde `skills-lock.json`).

| Skill | Versión declarada | Hash (`skills-lock.json`) |
|---|---|---|
| `ux-heuristics` | 1.6.0 | `078959463a4d…` |
| `impeccable` | 4.7.0 | `84572f92d75b…` |
| `design-critique` | sin versión declarada | `55100e100ac2…` |
| `apple-design` | sin versión declarada | `0190417d092a…` |
| `ui-ux-pro-max` | sin versión declarada | `27b1e8c953e2…` |

## Lo que depende de Luis

| Qué | Por qué | Cómo se cierra |
|---|---|---|
| Vidrio claro o tintado (iOS 26.1) | Runtime local 26.0.1; otro son ~7,5 GB con 7,7 GB libres | iPhone con 26.1 o runtime nuevo |
| Respaldo en iOS anterior a 26 | No hay runtime de iOS 18 en la máquina | iPhone con iOS 18 o runtime nuevo |
| El build de simulador en EAS | Usa su cuenta y sus minutos de build | `eas build -p ios --profile development-simulator` |
