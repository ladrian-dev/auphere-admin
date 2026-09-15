# Seis fallos de la app de escritorio, encontrados al usarla de verdad

> **Este documento se escribió con cinco y el título decía cuatro.** Al
> investigarlos aparecieron un sexto y una causa de cadena que no estaba
> prevista. El estado de cada uno, abajo.

**Fecha**: 2026-09-15 · **Versión**: `0.1.0`, la primera publicada por la cadena
de la spec 008 · **Encontrados por**: Luis, usando la aplicación instalada.

Ninguno se investigó a fondo: se anotan para una sesión dedicada. Lo que sí se
hizo es localizar en el código el punto probable de cada uno, porque ese
contexto estaba fresco y encontrarlo de nuevo cuesta más que escribirlo.

**Los cuatro son de la aplicación, no de la cadena.** El empaquetado, la firma,
la notarización y el canal funcionan — la app se instala y abre. Lo que falla es
lo que pasa después, y es la primera vez que alguien la usa instalada en vez de
desde el repositorio.

> **Estado de cada hipótesis**: lo marcado como **observado** viene del código;
> lo marcado como **hipótesis** hay que confirmarlo reproduciendo.

---

## Estado al 2026-09-15, tras la sesión de diagnóstico

| # | Fallo | Estado |
|---|---|---|
| 1 | Google no vuelve a la app | **Sin arreglar.** Mecanismo confirmado; necesita decisión de diseño |
| 2 | El banner de «sin emparejar» no se va | **Sin arreglar.** Confirmado: dos superficies leyendo dos fuentes |
| 3 | Crear teammate da error genérico | **ARREGLADO** · `.specify/bugs/teammate-tope-de-plan-mensaje-generico/` |
| 4 | No hay vuelta desde la consola | **Sin arreglar, y el diagnóstico de abajo es falso** — ver corrección |
| 5 | En otra máquina no funcionó | **Sin resolver.** Las dos hipótesis de abajo están descartadas |
| 5b | El paquete se traga su propia salida | **ARREGLADO** · `.specify/bugs/paquete-se-traga-su-propia-salida/` |
| 6 | El actualizador nunca se arma | **ARREGLADO** · `.specify/bugs/updater-no-arranca/` |

Los tres arreglados se publican juntos en **0.1.2**.

**El fallo 6 no estaba en esta lista y es el más grave de los tres arreglados**:
`electron-updater` es CommonJS y expone `autoUpdater` con un getter perezoso que
`cjs-module-lexer` no detecta, así que desde ESM el desestructurado daba
`undefined` y lanzaba. **v0.1.0 y v0.1.1 no preguntaron al canal ni una vez.**
Era inalcanzable salvo en un binario empaquetado *y* firmado.

**El 5b tampoco**: el `.dmg` de Intel pesa 1,0 GB contra 266 MB el de Apple
Silicon, porque cada arquitectura empaquetaba dentro de su `app.asar` la salida
del propio empaquetador — en x64, la app de arm64 ya firmada y un `.dmg` a medio
escribir de 987 MB. Detalle en `pendientes-tras-el-go-live.md` §2.1.

---

## 1 · Iniciar sesión con Google nunca vuelve a la aplicación

**Síntoma.** Desde la app, «entrar con Google» abre el navegador del sistema. El
inicio de sesión se completa allí. **La aplicación nunca se entera**: sigue como
si no hubiera sesión.

**Por qué, casi seguro.** *(observado)* `src/window-open-policy.ts` manda
**cualquier** `https:` al navegador del sistema:

```ts
if (parsed.protocol === "https:") return { action: "open_external", url };
```

La sesión de la consola vive en la partición `persist:auphere-console` de
Electron, y `session-gate.ts` la lee con `GET /api/session/whoami` **usando la
cookie de esa partición**. Si el login ocurre en Safari o Chrome, la cookie se
queda **en el navegador**: la partición de Electron no la ve nunca y `whoami`
sigue devolviendo 401.

**Y no basta con permitir la navegación dentro.** *(hipótesis, verificar)*
Google **bloquea OAuth en webviews embebidos** desde 2021; abrirlo dentro de la
cáscara probablemente devuelva `disallowed_useragent`. Si es así, esto no es un
`if` mal puesto: es que **falta el camino de vuelta**, y hay que elegir uno —
callback a `localhost` como hacen Claude Code y Codex CLI, un esquema propio
(`auphere://`), o un código de un solo uso como el del emparejamiento.

**Dónde mirar**: `src/window-open-policy.ts`, `src/session-gate.ts`,
`src/electron/main.ts` (el `setWindowOpenHandler`), y cómo la consola dispara el
login de Google.

**Gravedad: alta.** Es la puerta de entrada. Con correo y contraseña quizá
funcione —hay que comprobarlo—, pero si un partner usa Google, no puede entrar.

---

## 2 · El banner de «máquina sin emparejar» no se va al emparejar

**Síntoma.** Se empareja la máquina con el código y el emparejamiento funciona,
pero el banner superior sigue diciendo que no está emparejada.

**Por qué, probablemente.** *(observado)* `AppRuntime.pair()`
(`src/app-runtime.ts:262`) termina con:

```ts
this.setBar({ kind: "pair_ok", machine: { … } });
```

Es decir, actualiza **la barra**. Pero la decisión de «esta máquina no está
emparejada» la toma `SessionGate.evaluate()`, que mira el almacén de
credenciales, y **`gate.refresh()` sólo se llama desde `onSessionLost`**
(`src/electron/main.ts:282`). Nadie lo llama después de emparejar, así que la
puerta se queda en `pair_needed` hasta el siguiente cambio de la cookie.

**Hipótesis a confirmar**: si el banner es de la pantalla de operar y no de la
barra, son dos superficies leyendo dos fuentes distintas del mismo hecho — y el
arreglo no es sólo añadir un `refresh()`, sino decidir cuál de las dos manda.

**Dónde mirar**: `src/app-runtime.ts` (`pair`), `src/session-gate.ts`,
`src/electron/main.ts:207` (`bar:pair`), y quién pinta el banner.

---

## 3 · Crear un teammate falla con «inténtalo más tarde»

**Síntoma.** Se intenta crear un teammate desde la app y devuelve un error
genérico.

**No hay hipótesis todavía.** Un mensaje genérico puede tapar cosas muy
distintas: permiso, tope del plan, la API respondiendo 5xx, o la app llamando a
una ruta que no existe. **Lo primero es leer los logs**, no adivinar.

**Cómo empezar**: reproducirlo con las herramientas de desarrollo abiertas para
ver la petición real y su respuesta; y mirar los logs de la API en producción
para ese momento. Con el código y el cuerpo de la respuesta, el diagnóstico es
inmediato.

**Ojo con un detalle del plan**: un partner en Free tiene `max_teammates = 0`
(migración `0116`). Si la cuenta de prueba está en Free, **el error podría ser
correcto y el problema ser el mensaje**, que no dice que el plan no lo permite.
Merece comprobarse antes que nada: es la explicación más barata.

---

## 4 · Desde la consola no hay forma de volver a la aplicación

**Síntoma.** El botón «ir a la consola» cambia la vista, y una vez allí no hay
camino de vuelta a la pantalla de la aplicación.

**Por qué.** *(observado)* La cáscara tiene tres superficies y las cambia con
`showSurface(...)` en el proceso principal. La vista de la consola **no tiene
`preload`**, y eso es deliberado (spec 002, R3.5): sin `preload` no hay canal
entre la página cargada y la cáscara, que es lo que impide que la consola —o
cualquier cosa que cargue— le hable al proceso principal.

**Consecuencia: el botón de vuelta no puede estar dentro de la consola.** Tiene
que vivir en algo que sí sea de la cáscara — la barra del puesto, el menú de la
aplicación, o un atajo de teclado. No es un botón que se olvidó: es que **no
puede** estar donde uno lo buscaría, y eso hay que diseñarlo.

> **CORRECCIÓN del 2026-09-15.** El razonamiento es bueno y la conclusión es
> falsa: **ya hay tres caminos de vuelta, y los tres están en la cáscara.** El
> menú «Ver → Equipo» con `Cmd+1` (`main.ts:151`), el clic en el icono de
> bandeja (`main.ts:333`), y el atajo global `Cmd+Shift+A` (`main.ts:343`).
>
> Así que el fallo no es que falte el camino: es que **no se encuentra**. Eso
> cambia el arreglo — no hay que inventar una superficie, hay que hacer visible
> la que existe. Sigue siendo diseño, pero otro.

**Dónde mirar**: `src/electron/main.ts` (`showSurface`, `showApp`),
`src/bar/bar.ts`, y `contracts/desktop-bar.md` de la spec 002 para las acciones
que la barra ya declara.

---

## 5 · **En otra máquina no funcionó** — y en la de Luis pidió la clave del llavero

**El más importante de los cinco**, porque los otros cuatro son fallos de una
aplicación que al menos arranca. Éste es la diferencia entre «tengo una app» y
«puedo entregársela a alguien».

**Síntomas.**

- En la máquina de Luis: **funciona**, y al arrancar **pidió la contraseña del
  llavero**.
- En otra máquina: **no funcionó**. *(falta saber qué significa exactamente —
  ver «Lo que hay que averiguar»)*

**El punto común es `safeStorage`.** *(observado)* La credencial de máquina se
guarda cifrada con `safeStorage` de Electron
(`src/electron/adapters.ts:23`), que en macOS **usa el llavero del usuario**.
Que pida la contraseña la primera vez es el comportamiento normal de macOS
cuando una aplicación pide acceso a una clave nueva del llavero.

**Y aquí está lo que explicaría «no funciona»** *(hipótesis fuerte)*. Si
`safeStorage.isEncryptionAvailable()` devuelve `false` —porque el usuario
canceló el diálogo del llavero, porque el llavero está bloqueado, o porque la
sesión no tiene acceso a él— entonces:

```ts
// bar-state.ts:126
if (!state.encryptionAvailable) return [];
```

**La barra no ofrece NINGUNA acción.** Ni «introducir código», ni nada. La
aplicación abre, se ve entera, y **no se puede hacer absolutamente nada con
ella**, sin un error que explique por qué. Encaja exactamente con «no funcionó».

> **CORRECCIÓN del 2026-09-15: esto es falso, y la hipótesis entera está
> descartada.** La barra **sí** dice por qué: `bar.ts:109` pinta la nota
> `noEncryption` — «Este sistema no ofrece cifrado para guardar la credencial: no
> se puede emparejar». Se queda sin acciones, pero no en silencio.
>
> Y sobre todo: **en esa máquina no apareció ningún diálogo del llavero**, así
> que `safeStorage` no llegó a pedir nada. La aplicación no llega a ese código.

Ese comportamiento es **deliberado y correcto** —guardar la credencial en claro
«mientras tanto» es la llave en el disco de otra persona, y el Requisito 15.2 de
la spec 001 lo prohíbe— pero está diseñado como un caso raro, no como el primer
contacto de alguien con el producto. Si la primera ejecución en una máquina
ajena cae aquí, el producto parece roto.

### Lo que hay que averiguar, y sin esto no se puede diagnosticar

1. **Qué significa «no funcionó»**: ¿no abre? ¿abre y no deja emparejar? ¿abre y
   la barra está vacía? ¿un diálogo del sistema? Cada respuesta lleva a un sitio
   distinto.
2. **Qué versión de macOS** tiene esa máquina. **Electron 44 exige macOS 13
   Ventura**; en macOS 12 la app instala y no abre — y ése es justo el pendiente
   (a) de `pendientes-tras-el-go-live.md`, el `minimumSystemVersion` que no está
   declarado y que haría que macOS lo dijera en vez de fallar en silencio.

   > **RESPONDIDO: macOS 26.** La candidata barata está descartada. El
   > `minimumSystemVersion` se declaró igualmente (T045 a), porque sigue siendo
   > correcto, pero no era esto.
3. **Qué arquitectura**, y si se instaló el `.dmg` correcto: el de Intel va **sin
   sufijo** (`Auphere-0.1.0.dmg`) y el de Apple Silicon lleva `-arm64`.
4. **Si apareció el diálogo del llavero y qué se contestó.** Cancelarlo deja
   `isEncryptionAvailable()` en `false` para esa sesión.
5. **Si era una cuenta de usuario recién creada o gestionada** (MDM, cuenta de
   invitado): esos casos tienen llaveros con comportamientos distintos.

### Por qué importa más que los otros cuatro

En la máquina de Luis hay dos cosas que **ningún partner tendrá**: el
certificado de firma en el llavero y el proyecto entero. Esta es la primera señal
de que la aplicación se comporta distinto fuera de aquí — que es exactamente lo
que **T021 de la spec 008** existe para detectar, y que sigue sin ejecutarse
formalmente en un Mac limpio.

---

### Lo que se averiguó el 2026-09-15, y lo que queda

Las cinco preguntas se respondieron. La máquina es **Intel de verdad**
(`uname -m` → `x86_64`), con el `.dmg` correcto y **completo** (1.017.906.539
bytes, el tamaño publicado exacto), **macOS 26**, sin diálogo del llavero y sin
otra instancia corriendo.

Y la aplicación está bien firmada y notarizada **en esa máquina**:

```
/Applications/Auphere.app: accepted
source=Notarized Developer ID
origin=Developer ID Application: FACELAD SpA (CBSWMG766P)
/Applications/Auphere.app: valid on disk
/Applications/Auphere.app: satisfies its Designated Requirement
```

**Eso responde T021 de la spec 008, en verde**: la notarización vale fuera de la
máquina de Luis, que era la duda.

Lo que sigue sin respuesta es por qué se cierra. El proceso sale con **código 1 a
los ~290 ms**, sin ventana, **sin imprimir una sola línea** ni siquiera con
`ELECTRON_ENABLE_LOGGING=1`, y sin dejar informe de caída — así que no es una
caída: es una salida. Descartados: versión de macOS, arquitectura, paquete
equivocado, descarga truncada, Gatekeeper, firma, `safeStorage` y el cerrojo de
instancia única de `main.ts:437`.

Lo único objetivamente roto que le quedaba a ese binario es su `app.asar` de
**1,98 GB** con un `.dmg` a medio escribir dentro (fallo 5b). No está demostrado
que sea la causa. **0.1.2 es el experimento**: cambia esa variable y deja las
demás quietas.

---

## Cómo abordarlo

Los cuatro son **cambios de comportamiento del producto**, así que van por el
flujo de bugs del repo (`/speckit-bug-assess` → `-test` → `-fix`), no por una
spec nueva. El 3 puede resultar no ser un fallo, y por eso va primero: es el más
barato de descartar.

Orden sugerido, por lo que desbloquea:

1. **El 5, primero y con diferencia.** Sin saber por qué falla en otra máquina,
   arreglar los demás es pulir algo que no se puede entregar. Y empieza por
   preguntar, no por programar: las cinco respuestas de arriba probablemente
   señalen la causa sin tocar código.
2. **El 3**, porque puede ser el mensaje y no el fallo. Media hora de logs.
3. **El 1**, porque sin entrar no se puede usar nada más. Es el único que
   probablemente necesite una decisión de diseño, no un arreglo.
4. **El 2**, acotado y con el punto localizado.
5. **El 4**, que es diseño de navegación más que avería.

**Y hay un arreglo que sirve para dos de ellos**: declarar
`minimumSystemVersion: "13.0"` (pendiente (a)) convierte «la app no abre y no sé
por qué» en un mensaje de macOS que nombra la versión. Si la otra máquina era
macOS 12, eso solo ya explica el 5.
