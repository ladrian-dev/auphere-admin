# Especificación: volver a la aplicación, y entrar con Google

**Rama**: `009-volver-y-entrar-desde-la-app` · **Creada**: 2026-09-15 · **Estado**: Borrador

**Entrada**: los fallos 1 y 4 de
[`docs/bugs-app-escritorio-2026-09-15.md`](../../docs/bugs-app-escritorio-2026-09-15.md),
encontrados al usar la primera versión publicada (v0.1.0) instalada.

## Encabezado Auphere *(obligatorio)*

| Campo | Valor |
|---|---|
| **Superficie de confianza** | **Ninguna nueva de las cinco** (`0`–`3b`): la consola ya se carga dentro de la cáscara desde la spec 002. Lo que se amplía es **la frontera interna de la cáscara**: la lista cerrada de seis funciones del `preload` de la barra, que es lo que impide que la página cargada le hable al proceso principal (spec 002, R3.5). Esa lista es una superficie de confianza aunque no lleve número, y esta spec la abre por primera vez desde que se cerró |
| **Garantías de aislamiento tocadas** | **Ninguna de las 7 de `architecture/agent-isolation.md`.** No hay tenant, ni RLS, ni herramienta, ni prompt, ni checkpointer. La prueba que esta spec sí debe traer no es de aislamiento entre tenants sino de **no suplantación**: un código de sesión no puede servir para entrar como otra persona, ni dos veces, ni fuera de su ventana |
| **Nota de KB que la justifica** | `[[ADR-039-volver-y-entrar-desde-la-app-de-escritorio]]` — escrito el 2026-09-15 para esta spec, porque no existía ninguna nota sobre cómo entra una persona en la aplicación de escritorio. Recoge las dos alternativas descartadas (callback a `127.0.0.1` y esquema `auphere://`) con su razón, y las cuatro decisiones de detalle. **Su origen es el uso y no la investigación**, y así lo dice |
| **Qué se mide** | **Nada nuevo.** No consume modelo, ni reloj de máquina, ni herramienta de pago |

> **Por qué se abre la lista de seis ahora (§II).** Porque no hay forma de dar
> este valor dentro de lo ya abierto, y se comprobó antes de proponerlo. La
> barra **no puede** cambiar de superficie ni traer una sesión sin un canal al
> proceso principal: ése es exactamente el propósito de no dárselo. El precedente
> del repositorio va en contra y por eso se argumenta en el Requisito 2 en vez de
> pasarlo por alto: en `bar.ts:125` se decidió **no** añadir un `checkForUpdate`
> porque «el botón no lo justifica». Aquí lo que está en juego no es un botón:
> es que una persona pueda entrar y pueda volver.
>
> Y se abre **por su mitad barata primero**: la Historia 1 no toca autenticación
> y se puede entregar sola.

## Clarifications

### Session 2026-09-15

- Q: ¿El código de un solo uso sirve sólo para terminar un inicio de sesión con Google, o es el camino general para traer cualquier sesión de la consola a la aplicación? → A: **Sólo Google.** La consola enseña el código únicamente al volver del callback; entrar con correo y contraseña sigue funcionando dentro de la cáscara y no se toca.
- Q: Cuando alguien teclea el código en la barra, ¿qué queda exactamente dentro de la aplicación: una sesión nueva y propia, o una copia de la que ya tiene abierta en el navegador? → A: **Una sesión nueva y propia**, acuñada por el mismo camino por el que la consola ya emite sesiones, con su propia caducidad. Las dos sesiones son independientes.
- Q: Si alguien lee el código en una pantalla ajena y lo teclea en su propia máquina antes de que caduque, ¿debe funcionarle? → A: **No. El código queda atado a la máquina que lo pidió**, con la misma huella que el emparejamiento ya manda (hostname + plataforma).
- Q: La constitución §IX exige citar la nota de KB que justifica la spec, y no existe. ¿Qué hacemos con ese hueco? → A: **Escribir un ADR corto en la KB.** Hecho: `[[ADR-039-volver-y-entrar-desde-la-app-de-escritorio]]`, con la decisión, las alternativas descartadas y su razón.

## Estado real, contrastado el 2026-09-15

| Hecho | Estado |
|---|---|
| Entrar con correo y contraseña dentro de la cáscara | **Funciona.** `auth-actions.ts` es un *server action* que no sale del origen |
| Entrar con Google | **Roto.** El botón hace `window.location.assign()`, `will-navigate` lo manda al navegador del sistema y la cookie se queda allí |
| Volver a la app desde la consola | **Hay tres caminos y ninguno se ve**: menú «Ver → Equipo» (`Cmd+1`), icono de bandeja, atajo global `Cmd+Shift+A` |
| Un mecanismo de código de sesión | **No existe.** Se buscó `session_code`, `login_code`, `one_time` y `magic`: nada reutilizable |
| Primitivas de código reutilizables | **Sí, y no son pocas.** `core/pairing_codes.py` trae alfabeto sin ambigüedades (sin `I`, `L`, `O`, `U`), 8 caracteres, TTL de 10 min, hash y normalización; y `PairingRateLimiter` trae 5 intentos por ventana de 10 min con espera creciente hasta 15 min |

**Esto acota el problema y conviene tenerlo delante**: nadie está fuera de la
aplicación. Quien usa correo y contraseña entra hoy. El fallo 1 es «quien usa
Google no puede entrar».

## Escenarios de usuario y pruebas *(obligatorio)*

### Historia 1 — volver a la pantalla del equipo (Prioridad: P1)

Alguien está operando en la app, pulsa «ir a la consola» para mirar algo de un
cliente, y quiere volver a su equipo. Hoy la consola ocupa la ventana entera y
no hay nada visible que lo devuelva: los tres caminos que existen viven en el
menú, en la bandeja y en un atajo, y ninguno se le ocurre a quien acaba de
instalar la aplicación.

**Por qué esta prioridad**: es la mitad barata. No toca autenticación, no toca la
plataforma, y entrega valor sola. Además desbloquea la Historia 2 — cuando el
código de sesión se teclee en la barra, la persona tendrá que volver.

**Prueba independiente**: se instala solo esta mitad, se va a la consola y se
vuelve sin tocar el teclado ni el menú. Si funciona, el fallo 4 está cerrado.

**Escenarios de aceptación**:

1. **Dado** que la consola ocupa la ventana, **cuando** la persona mira la barra
   del puesto, **entonces** ve una acción de vuelta a la pantalla del equipo.
2. **Dado** que está en la pantalla del equipo, **cuando** mira la barra,
   **entonces** **no** ve esa acción — no hay botón apagado ni botón que no lleva
   a ningún sitio (§V).
3. **Dado** que pulsa la acción de vuelta, **cuando** la cáscara cambia de
   superficie, **entonces** la consola sigue cargada donde estaba y volver a ella
   no la recarga ni pierde lo que la persona estaba viendo.

---

### Historia 2 — entrar con Google (Prioridad: P2)

Un partner cuya cuenta es de Google abre la aplicación, pulsa «continuar con
Google», el navegador del sistema completa el inicio de sesión, y la aplicación
**se entera**. Hoy no se entera nunca.

**Por qué esta prioridad**: va después porque cuesta más y porque hay una salida
mientras tanto —entrar con correo y contraseña funciona—, no porque importe
menos. Es la puerta de entrada para una parte de los partners.

**Prueba independiente**: con una cuenta de Google y sin contraseña de la
consola, se entra en la aplicación de punta a punta.

**Escenarios de aceptación**:

1. **Dado** que la persona no tiene sesión en la aplicación, **cuando** completa
   el inicio de sesión con Google en el navegador del sistema, **entonces** la
   consola le muestra un código y le dice qué hacer con él.
2. **Dado** que tiene el código delante, **cuando** lo teclea en la barra del
   puesto, **entonces** la aplicación queda con su sesión iniciada y la pantalla
   del equipo aparece sin que haga nada más.
3. **Dado** que el código ya se canjeó una vez, **cuando** se vuelve a teclear,
   **entonces** el sistema lo rechaza y lo dice sin revelar de quién era.
4. **Dado** que han pasado más de diez minutos, **cuando** se teclea,
   **entonces** el sistema lo rechaza por caducado y ofrece pedir otro.

---

### Casos límite

- **El código se teclea en otra máquina.** Alguien lee el código de una pantalla
  compartida y lo escribe en su propio portátil. **Cerrado el 2026-09-15: se
  rechaza** (R5.3), porque el código va atado a la máquina que lo pidió.
- **La persona ya tiene sesión de otra cuenta en la cáscara** cuando canjea un
  código de una cuenta distinta.
- **Google no está disponible** (`googleStartAction` devuelve nada). Hoy el botón
  **desaparece** en vez de quedarse gris, y eso está bien: la ausencia se diseña.
  La spec no puede empeorarlo.
- **La persona cierra la aplicación** entre pedir el código y teclearlo.
- **La consola se recarga** con la acción de vuelta pulsada a medias.
- **Cifrado no disponible** (`safeStorage`): la barra ya se queda sin acciones y
  lo explica. ¿Qué pasa con la acción de vuelta, que no guarda nada? Ver R2.4.

## Requisitos *(obligatorio)*

### Requisito 1 — volver a la pantalla del equipo desde la barra

**Historia de usuario:** Como persona que usa la aplicación, quiero volver a mi
equipo desde donde estoy mirando, para no tener que descubrir un atajo.

#### Criterios de aceptación

1. WHILE la superficie visible es la consola, la barra del puesto DEBE ofrecer
   una acción que devuelva a la pantalla del equipo.
2. WHILE la superficie visible es la pantalla del equipo, la barra **NO DEBE**
   ofrecer esa acción, ni apagada ni con texto que explique su ausencia (§V).
3. WHEN la persona activa esa acción THEN el sistema DEBE mostrar la pantalla del
   equipo **sin recargar** la vista de la consola, y volver a la consola DEBE
   dejarla donde estaba.
4. Los tres caminos que ya existen —menú, bandeja y atajo global— DEBEN seguir
   funcionando: esta acción se añade, no los sustituye.

### Requisito 2 — ampliar la lista cerrada del `preload`, y sólo lo justo

**Historia de usuario:** Como responsable de la cáscara, quiero que cada función
nueva del `preload` cueste una justificación escrita, para que la lista no crezca
por costumbre.

> **Por qué aquí sí, y en `bar.ts:125` no.** Aquel caso era un atajo a una versión
> nueva que el actualizador ya iba a coger solo en cuatro horas: el `preload` no
> era el único camino. Aquí sí lo es — sin canal, la barra no puede cambiar de
> superficie ni entregar un código, y no hay segundo camino que espere.

#### Criterios de aceptación

1. El `preload` de la barra DEBE exponer **exactamente** las funciones que
   `specs/002-identidad-app-escritorio/contracts/desktop-bar.md` declare, y el
   contrato DEBE actualizarse en el mismo commit que el código.
2. WHERE se añada una función al `preload`, el sistema DEBE tener un test que
   falle si aparece una séptima —u octava— no declarada. El test que hoy afirma
   «exactamente seis» (`no-own-auth.test.ts:33`) DEBE actualizarse, no borrarse.
3. La vista de la consola DEBE seguir **sin `preload`**: nada de lo que esta spec
   añade puede darle un canal a la página cargada (spec 002, R3.5).
4. IF el cifrado de credenciales no está disponible THEN la acción de vuelta DEBE
   seguir ofreciéndose: no guarda nada, y dejar a la persona encerrada en la
   consola por algo que no le afecta sería un castigo sin causa.
5. El texto del `preload` de la barra NO DEBE contener `login`, `session`,
   `cookie` ni `token` (`no-own-auth.test.ts:38`, Requisitos 2.1 y 2.5 de la spec
   002). **Si la Historia 2 no puede cumplirlo, la spec se detiene y se enmienda
   esa regla por escrito** — es la que garantiza que la aplicación no tiene
   autenticación propia, y saltársela en silencio sería exactamente el fallo que
   pretende evitar.

### Requisito 3 — emitir el código de sesión

**Historia de usuario:** Como persona que acaba de entrar con Google en el
navegador, quiero algo que llevar a la aplicación, para no tener que entrar dos
veces.

#### Criterios de aceptación

1. WHEN una persona termina un inicio de sesión con Google en el navegador del
   sistema THEN la consola DEBE emitir un código de un solo uso y mostrárselo.
   **Sólo por ese camino**: el código no se ofrece a quien entró con correo y
   contraseña, porque ésa ya entra dentro de la cáscara.
2. El código DEBE usar el alfabeto, la longitud y el tiempo de vida que ya usa el
   emparejamiento de máquinas (`core/pairing_codes.py`): sin caracteres
   ambiguos, ocho posiciones, diez minutos.
3. El sistema DEBE guardar **el hash** del código, nunca el código.
4. WHEN se emite un código nuevo para la misma persona THEN el anterior DEBE
   quedar invalidado: no hay dos códigos vivos a la vez.
5. IF la persona no tiene sesión en la consola THEN el sistema NO DEBE emitir
   ningún código, y NO DEBE decir si esa cuenta existe.

### Requisito 4 — canjear el código de sesión

#### Criterios de aceptación

1. WHEN se canjea un código válido dentro de su ventana THEN el sistema DEBE
   **acuñar una sesión nueva** para la aplicación, por el mismo camino por el
   que la consola ya emite sesiones, y con su propia caducidad.
2. La sesión de la aplicación y la del navegador DEBEN ser **independientes**:
   cerrar una NO DEBE cerrar la otra, y el secreto de una NO DEBE servir en la
   otra. Que sean dos es lo que permite decir en la auditoría cuál hizo qué.
3. WHERE alguien necesite retirar el acceso de una máquina, el sistema DEBE
   permitir terminar la sesión de la aplicación **sin** terminar la del
   navegador. *(Consecuencia directa de que sean dos: si revocar exigiera cerrar
   las dos, la independencia sería sólo de nombre.)*
4. WHEN un código se canjea THEN DEBE quedar consumido, y un segundo canje DEBE
   fallar.
5. IF el código está caducado, ya usado o no existe THEN el sistema DEBE
   responder **lo mismo** en los tres casos: quien prueba códigos no puede
   aprender cuáles existieron.
6. El canje DEBE estar limitado por intentos con la misma defensa que el
   emparejamiento (`PairingRateLimiter`: cinco fallos en diez minutos, espera
   creciente hasta quince), y un canje correcto DEBE limpiar la cuenta.
7. WHEN el canje falla THEN la barra DEBE decirlo como estado y **nunca en rojo**,
   igual que el resto de sus siete estados.

### Requisito 5 — lo que el código **no** puede hacer

**Historia de usuario:** Como responsable de que esto no sea una puerta trasera,
quiero que esté escrito qué no puede pasar, para que sea un test y no una
intención.

#### Criterios de aceptación

1. Un código NO DEBE conceder más permisos que los de la persona que lo pidió.
2. Un código NO DEBE poder usarse para entrar como otra persona: lo que se canjea
   es **la sesión de quien lo pidió**, y eso DEBE comprobarse en el servidor.
3. IF el código se canjea desde una máquina distinta de la que lo pidió THEN el
   sistema DEBE rechazarlo, y DEBE responder lo mismo que ante un código
   caducado o inexistente (R4.5): quien prueba no aprende por qué falló.
   *La huella de máquina es la que el emparejamiento ya manda —`hostname` y
   plataforma—; no se inventa una nueva ni se recoge nada más.*
4. El código NO DEBE viajar nunca a la plataforma en claro en un registro, una
   traza ni un mensaje de error.
5. WHEN un código se canjea THEN la auditoría DEBE nombrar a la **persona** y la
   máquina, igual que hace el emparejamiento (§IV: la auditoría nombra a quien
   decidió).
6. IF alguien canjea un código estando ya dentro con otra cuenta THEN el sistema
   DEBE tratarlo como el cambio de persona que ya sabe manejar
   (`session_other_person`), y NO DEBE mezclar las dos sesiones.

### Entidades clave

- **Código de sesión**: un secreto de un solo uso que ata **una persona** —no una
  máquina— a una sesión de la aplicación. Pertenece a la persona (`user_id`), y
  por tanto al partner del que esa persona es miembro; la RLS lo alcanza por la
  misma columna por la que alcanza a `partner_memberships`. Se guarda hasheado,
  con su instante de emisión, su instante de consumo y nada más.

## Criterios de éxito *(obligatorio)*

- **CE-001**: una persona que llega a la consola desde la app y quiere volver lo
  consigue **sin usar el teclado ni el menú**, y sin que nadie se lo explique.
- **CE-002**: un partner con cuenta de Google y **sin** contraseña de la consola
  entra en la aplicación de punta a punta en menos de dos minutos.
- **CE-003**: un código sirve **una vez**: el segundo intento falla siempre.
- **CE-004**: un código caducado, uno ya usado y uno inventado son
  **indistinguibles** desde fuera.
- **CE-005**: la lista de funciones del `preload` sigue siendo cerrada: añadir una
  sin declararla en el contrato pone un test en rojo.

## Fuera de alcance

- **El callback a `127.0.0.1` y el esquema `auphere://`** — descartados el
  2026-09-15. El primero abre un puerto de escucha en la máquina del partner, y
  `apps/desktop/package.json` declara hoy que el puente es *outbound-only*. El
  segundo es superficie del sistema, reclamable por otra aplicación.
- **Cargar el login de Google dentro de la cáscara** — Google bloquea OAuth en
  vistas embebidas desde 2021, y construir sobre algo que el proveedor prohíbe es
  pedir que se rompa sin avisar.
- **El camino general de «traer mi sesión»** — decidido el 2026-09-15: el código
  se ofrece **sólo** al volver del callback de Google. Quien entra con correo y
  contraseña ya entra dentro de la cáscara, y darle un segundo camino sería dos
  formas de hacer lo mismo sin que nadie sepa cuándo toca cada una.
- **Windows** — la mitad de escritorio para Windows no está portada.
- **Rediseñar cómo se cambia de superficie** — las tres superficies y
  `showSurface` se quedan como están; esto añade una forma de invocarlo.
- **El fallo 5** (la app no abre en un Mac Intel) — se aborda por el paquete, en
  0.1.2, y no tiene relación con esto.

## Supuestos

- **La acción de vuelta se ofrece sólo con la consola delante.** Es la lectura de
  §V: ofrecerla siempre significaría un botón que a veces no lleva a ningún sitio.
  Si se prefiere lo contrario, es un cambio de una línea en R1.2.
- **El código lo teclea la persona en la barra**, reutilizando la hoja que ya
  existe para el código de emparejamiento. No se inventa una pantalla.
- **La consola es quien enseña el código**, porque es donde la persona está
  cuando termina de entrar con Google.
- **Diez minutos de vida y ocho caracteres** se heredan del emparejamiento sin
  discutirlos: dos ventanas distintas para dos códigos que se teclean igual sería
  una diferencia que nadie podría explicar.
- **La huella de máquina no recoge nada nuevo.** Se usa la que el emparejamiento
  ya manda (`hostname` y plataforma). Esta spec no añade telemetría.
- Entrar con correo y contraseña **sigue funcionando como hoy** y no se toca.

## Preguntas abiertas

Tres, y ninguna puede quedar abierta al pasar a `/speckit-plan`.

### ~~Q1 — ¿qué transfiere exactamente el código?~~ RESUELTA

**Decidido el 2026-09-15: una sesión nueva y propia** (opción A). Es la única de
las tres en la que «esta sesión es de la aplicación» es un hecho comprobable en
el servidor, y la que deja la auditoría pudiendo nombrar qué máquina hizo qué.
Copiar el secreto habría sido más barato y habría convertido cada revocación en
una conversación. Recogido en R4.1–R4.3.

### ~~Q2 — ¿el código queda atado a la máquina que lo pide?~~ RESUELTA

**Decidido el 2026-09-15: sí, atado** (opción B). Con Q1 ya decidido la máquina
deja de ser un dato incidental —la sesión que se acuña **es de esa máquina**—, así
que atarlo es coherente con lo que se va a construir y no pide un mecanismo
nuevo: la huella es la que el emparejamiento ya manda.

Lo que se pierde es el flujo «lo pido en un sitio y lo tecleo en otro», y aquí no
aplica: el código nace en la consola cargada **dentro de la propia aplicación**.
Recogido en R5.3.

### ~~Q3 — ¿el código es sólo para Google, o es el camino general?~~ RESUELTA

**Decidido el 2026-09-15: sólo Google** (opción A). El alcance más pequeño que
cierra el fallo, y el único que no toca un camino de entrada que hoy funciona.
Ampliarlo después no costará más que hacerlo ahora; romper el login que los
partners ya usan, sí.

---

## Puertas antes de declarar esto hecho

- ~~`/speckit-clarify`~~ — **hecho el 2026-09-15**: cuatro preguntas, cuatro
  respuestas, cero marcas abiertas.
- `/speckit-plan` — Constitution Check completo.
- **`/cso` es obligatorio**: esto toca autenticación y secretos de un solo uso
  (regla del workspace). Un finding 🔴 bloquea.
- `/speckit-analyze` en verde antes de `/speckit-implement`.
- `./scripts/verify.sh` entero antes de fusionar.
