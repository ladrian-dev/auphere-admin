# Decision: la experiencia de la aplicación de escritorio

- **Slug**: experiencia-app-escritorio
- **Decided**: 2026-09-17
- **Verdict**: **go**
- **Artifacts reviewed**: [`intake.md`](./intake.md) · [`research.md`](./research.md)
  · [`problem.md`](./problem.md) · [`concept.md`](./concept.md)
- **Superficie de confianza (§II)**: `0` (API de la consola) y el tramo ya abierto
  de `3a`. **No abre superficie nueva**; con D2 **cierra** una partición
  (`auphere-bar`).
- **Qué se mide**: nada nuevo. El consumo que la app enseña sale del medidor de la
  spec 004.

---

## Scorecard

| Criterio | Valoración | Justificación |
|---|---|---|
| **Validez del problema** | **strong** | No es una hipótesis estética: cinco recorridos básicos no se completan, verificados en código con ruta y línea (entrar con Google sin llamador, hojas de la barra fuera de la vista, `loadURL` sin `try` que aborta el arranque, `/billing/gracias` inexistente, hilo fallido pintado como vacío). Y la propia app instalada lo enseña en la primera pantalla: dos estados vacíos que se contradicen |
| **Fuerza de la evidencia** | **strong** | Cuatro investigaciones con fuentes primarias —HIG y documentación de Electron leídas directamente, bundles de Claude, Codex, Slack y Figma inspeccionados en esta máquina, licencias leídas del archivo LICENSE— más una auditoría del propio repositorio con `archivo:línea` y una sesión de uso real. Lo no verificado está marcado en cada anexo y **nada que sostenga una decisión depende de ello** |
| **Valor frente a no hacer nada** | **strong** | Con el registro autónomo de la 006 ya en producción, una app que no se puede autoservir anula su propósito: hoy un partner nuevo no llega solo ni a entrar ni a emparejar. Y el único camino a pagar desde la app termina en un 404 |
| **Viabilidad / apetito** | **adequate** | El armazón (D1-A) es un cambio estructural que toca `apps/desktop`, `apps/console`, `packages/ui` y dos contratos. Cabe, pero no es barato, y depende de un spike de una hora sobre regiones de arrastre con vistas apiladas (electron#43320). La opción D de `concept.md` queda como plan B declarado |
| **Encaje estratégico** | **strong** | §II se cumple de frente: todo el valor cabe dentro de dos superficies ya pagadas y ninguna opción abre una nueva. §V deja de ser una aspiración escrita y pasa a ser comprobable estado por estado |
| **Postura de riesgo** | **adequate** | Tres riesgos con dueño: el rediseño que se revierte (mitigado decidiendo la navegación antes de construir pantallas), el cambio de tokens que alcanza a consola y admin (es el momento: el contraste está mal hoy), y las enmiendas de contrato de 002 y 003 (se declaran en la spec, no se cuelan). No es `strong` porque D2 enmienda una decisión de una spec ya construida |

---

## Verdict & Rationale

**Go.** El problema está documentado en el propio código y su coste no es
estético: es que la aplicación **no se puede usar sola**. Las specs 001–009
construyeron una cáscara correcta por dentro —aislamiento, máquinas de estado con
test, contención, firma y canal— y nadie la diseñó como producto; lo que falla
son las costuras entre las tres superficies y los recorridos que las cruzan.

La investigación cierra además la pregunta técnica que abría el encargo: **no hay
librería de escritorio que adoptar**. Los kits que imitan macOS o Windows están
muertos, los kits completos vivos traen su propia identidad, y las apps de
referencia —comprobado leyendo sus bundles— construyen su sistema sobre
primitivas headless. `@nexus/ui` sobre Base UI ya está en ese camino: lo que falta
es una capa de densidad de escritorio, un armazón nativo y seis piezas pequeñas
con licencia MIT o Apache-2.0.

El `go` no es incondicional: se firma con cuatro decisiones tomadas en esta
puerta, y dos de ellas **enmiendan contratos de specs ya construidas**. Eso no se
cuela: se declara en el encabezado de la spec que salga de aquí.

---

## Decisiones firmadas en esta puerta

| # | Decisión | Consecuencia que la spec debe declarar |
|---|---|---|
| **D1-A** | **Una sola aplicación**: el armazón es la vista local (chrome integrado + sidebar único) y la consola se pinta dentro del panel de contenido, en modo embebido | Toca `apps/console` (modo embebido por user-agent) y su `shell-detect`; añade dos canales de IPC sin credenciales (`app:console.location` de empuje, rectángulo del panel de invocación) → **enmienda de `specs/003-*/contracts/desktop-app-ipc.md`**. La consola **sigue sin `preload`**: 002 R12.1 intacta |
| **D2-A** | **La barra de 44 px se absorbe**: estado de la máquina al pie del sidebar y a Hoy; emparejar y directorios como diálogos de la app | **Enmienda de `specs/002-*/contracts/desktop-bar.md` y de su preload de siete funciones**: esas capacidades pasan al contrato de la pantalla. Se retira la partición `auphere-bar` (de cuatro a tres) y las prohibiciones de `no-own-auth` se trasladan a la vista de la app. Argumento: la barra fue la superficie mínima cuando la pantalla no existía; absorberla **reduce** superficie |
| **D3-A** | **Modo oscuro en tinta neutra cálida**, verde como acento | Cambia tokens compartidos: alcanza a `apps/console` y `apps/admin`. Exige test de contraste de pares (texto ≥4,5:1, no textual y foco ≥3:1) en ambos temas |
| **D4-A** | **Una spec, seis historias priorizadas e independientes** | `specs/010-experiencia-app-escritorio/` con un único `tasks.md`. Accesibilidad WCAG 2.2 AA y el glosario son requisitos ubicuos, no historias |

## Enmienda del 2026-09-18 — D1-A se revierte a medias

> Registrada como **[[ADR-040-la-consola-entra-entera-en-la-app-de-escritorio]]** en el KB.


**D1-A queda así: una sola ventana, pero la consola NO se pinta dentro del
panel.** Ocupa todo lo que hay bajo la franja, tal cual es, y se vuelve al
equipo con una acción explícita.

**Por qué.** Se construyó y se miró funcionando (0.1.5). En la misma ventana
había **dos barras laterales, dos buscadores, dos campanas y dos identidades**:
la de la aplicación y la de la consola. Y el glosario ya había empezado a
separarse —`nav.knowledge` decía «Playbook» donde la aplicación decía
«Conocimiento»—, que es el síntoma que predice el problema: dos navegaciones son
dos vocabularios que divergen.

El modo embebido se diseñó justo para eso: quitarle a la consola su armazón para
que cupiera dentro del otro. Es un cambio en `apps/console` **que existe sólo
para servir a la aplicación de escritorio**, y obliga a desplegar las dos a la
vez. Eso es acoplamiento entre dos aplicaciones para conseguir algo que la
consola ya hacía bien sola.

**Lo que se conserva de D1-A**: una sola ventana, un solo inicio de sesión, un
solo tema, y que la consola viva dentro de la aplicación en vez de en el
navegador. **Lo que cae**: el sidebar único con las secciones de administrar
espejadas, el panel de contenido compartido y el modo embebido.

| Antes (D1-A) | Ahora (D1-A′) |
|---|---|
| Sidebar único con `ADMINISTRAR` espejando las diez secciones de la consola | El sidebar es **Hoy · Pendientes · Teammates**, y nada más |
| La consola en el panel, sin su armazón (modo embebido por user-agent) | La consola **entera**, bajo la franja, con su barra, su buscador y su campana |
| Ir a una sección de administrar | **Una** puerta: «Abrir la consola», y una vuelta explícita |
| `apps/console` con `isDesktopShell()` | `apps/console` sin saber que existe la aplicación |

La franja se queda **siempre** visible: la ventana no tiene barra de título
nativa, así que es donde viven los semáforos, la región de arrastre y la vuelta.

**Lo que esto recupera**: `volver_a_la_app`, que la spec 009 diseñó y la 010
había borrado por innecesario. Lo era bajo D1-A; deja de serlo aquí.

**Lo que no cambia**: D2-A sigue en pie. El puesto de trabajo —emparejar esta
máquina, declarar sus directorios, desemparejarla— **no puede irse a la
consola**: la web no puede tocar tu disco. Se queda al pie del sidebar, y no
como «sección» sino como lo que la aplicación sabe hacer y la web no. La
preferencia de avisos del sistema, igual: es un permiso del sistema operativo.

**Consecuencia para el Requisito 9**: los topes ya no llevan a una «Cuenta» a
medias dentro de la aplicación. Llevan a la consola en su ruta exacta
(`/billing`), que es un destino más honesto y no obliga a reimplementar nada.

---

Y las ocho transversales de `concept.md` (T-1 cerrar oculta · T-2 un solo
derivado de pendientes · T-3 API de feedback · T-4 fuentes empaquetadas y CSP ·
T-5 un solo tema por `nativeTheme` · T-6 capa de densidad y foco ≥3:1 · T-7
glosario único · T-8 traspaso al navegador explícito).

## Qué queda fuera y por qué

- **Windows**: el armazón no le cierra la puerta, pero su build y su barra de
  título no entran.
- **`/billing/gracias`** (404 tras pagar): es un defecto de la 005 que afecta
  también a la consola web → flujo de bugs, abierto aparte.
- **Esquema `auphere://`**, checkout dentro de la ventana, reimplementar páginas
  de la consola y capacidades nuevas del agente: abrirían superficie o chocan con
  003 R12.6.

## Condiciones de entrada al plan

1. **Spike de una hora** sobre `app-region` con la consola como panel (issue
   electron#43320 abierto) **antes** de fijar el armazón en `plan.md`. Si falla,
   se aplica el plan B declarado (`concept.md` D1-D) y se escribe por qué.
2. **Comprobar `sonner` bajo CSP** (`style-src 'self'`) antes de elegirlo como
   mecanismo de toast.
3. **Confirmar en pantalla** el fallo P0-2 (hojas de la barra) — está deducido del
   código y **no se pudo observar**: en la sesión del 2026-09-17 la barra estuvo
   todo el rato en `reconectando`, estado que **no ofrece ninguna acción**, así
   que «Directorios» no llegó a existir. Se verifica en una máquina en
   `conectada` antes de fijar el diseño del diálogo.
4. **Diseñar el estado `reconectando` con causa y salida** (hallazgo del
   2026-09-17, observado): no hay gateway en `localhost:5476` —la app no instala
   ni arranca la edición (`main.ts`)— y la barra lleva **toda la sesión**
   diciendo `Adrians-MacBook-Pro.local · reconectando`, sin decir de qué se
   reconecta, desde cuándo, ni qué hacer. Mientras tanto la consola declara la
   máquina emparejada: dos superficies contando cosas distintas del mismo hecho.
   Entra en la historia P2 (estados honestos) y se cruza con T-2.
5. Toda dependencia nueva entra con su licencia citada en `plan.md` (la lista
   candidata ya está en `research.md` §3.2, leída del archivo LICENSE).
