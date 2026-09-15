---
description: "Tareas — spec 009"
---

# Tasks: volver a la aplicación, y entrar con Google

**Input**: [spec.md](spec.md) · [plan.md](plan.md) · [research.md](research.md) · [data-model.md](data-model.md) · [contracts/bar-preload.md](contracts/bar-preload.md) · [quickstart.md](quickstart.md)

**Tests**: obligatorios (§VII). Cada criterio nace como test, **se ve en rojo**, y
sólo entonces se implementa. Nada de `skip`.

## Reglas de este repo

- Cada tarea termina con `_Requisitos: N.m_`.
- Cada tarea entregada se anota: `Entregado: PR #NNN (rama), fusionado YYYY-MM-DD`.
- **`pnpm test` DENTRO de `apps/desktop` no funciona** — esa carpeta tiene su
  propio `pnpm-workspace.yaml` que no lista `packages/companion-ui`. Se corre
  desde la RAÍZ: `pnpm --filter @nexus/desktop test`.

## Las tres puertas, ya respondidas en el plan

| Puerta | Respuesta | Tarea |
|---|---|---|
| **Aislamiento** | **Ninguna de las 7.** No hay frontera de tenant | **Ninguna en `tests/isolation/`, y es correcto** — ver T019, que es de **no suplantación**, que es otra cosa |
| **Licencias** | **Ninguna dependencia nueva** | — |
| **Medidor** | **Nada que medir** | — |

---

## Fase 1 · Preparación

- [X] T001 Confirmar que `0121_companion_run_native_input` sigue siendo la migración más alta antes de escribir la 0122, con `ls apps/api/alembic/versions/ | sort | tail -3`. Si alguien metió otra, renumerar. _Requisitos: —_

---

## Fase 2 · Fundacional (bloquea a las dos historias)

**Propósito**: abrir la lista del `preload` una sola vez, con su contrato y su
test, para que las dos historias añadan su función sin volver a discutirlo.

- [X] T002 **[TEST, ROJO]** Actualizar `apps/desktop/tests/no-own-auth.test.ts:33` de «exactamente seis» a **«exactamente ocho»**, añadiendo `showApp` y `redeemCode` a la lista. **Se actualiza, no se borra.** Se ve en rojo antes de tocar el `preload`. _Requisitos: 2.1, 2.2_
- [X] T003 **[TEST, ROJO]** Añadir en `apps/desktop/tests/no-own-auth.test.ts` un caso que falle si aparece una **novena** función no declarada en el contrato. Es lo que mantiene la lista cerrada mañana. _Requisitos: 2.2_
- [X] T004 Añadir `showApp` y `redeemCode` a `apps/desktop/src/electron/bar-preload.ts`, y los canales `bar:showApp` y `bar:redeem` en `apps/desktop/src/electron/main.ts`. T002 y T003 pasan a verde. _Requisitos: 2.1_
- [X] T005 Actualizar `specs/002-identidad-app-escritorio/contracts/desktop-bar.md` a **siete** funciones (ver la desviación de abajo), con la razón. **EN EL MISMO COMMIT que T004**: un contrato congelado que se queda atrás miente. _Requisitos: 2.1_
- [X] T006b **[PUERTA]** Comprobar que `apps/desktop/tests/session-isolation.test.ts:87` —«la vista de la consola no tiene preload: la página no puede hablarle a la cáscara»— **sigue en verde**, y que `consoleWebPreferences()` sigue sin devolver `preload`. **Es el invariante que esta spec pone en riesgo**: se está ampliando el `preload` de al lado, y el de la consola tiene que seguir sin existir. Si se pone rojo, **parar**. _Requisitos: 2.3_
- [X] T006 Comprobar que `apps/desktop/tests/no-own-auth.test.ts:38` —el que prohíbe `login`, `session`, `cookie` y `token` en el texto del `preload`— **sigue en verde sin tocarlo**. El diseño lo respeta: `redeemCode` entrega ocho caracteres y recibe un estado. Si se pone rojo, **parar**: hay que enmendar la spec 002 por escrito antes de seguir. _Requisitos: 2.5_

**Punto de control**: el `preload` de la barra tiene **siete** funciones declaradas, el
contrato lo dice, tres tests lo vigilan, y **el de la consola sigue sin existir**.

### Desviación registrada el 2026-09-15 · siete funciones, no ocho

Las tareas decían abrir el `preload` **una sola vez** en la Fase 2, dejándolo en
ocho. Al implementarlo se vio el problema: **la Historia 1 se publicaría con un
`redeemCode` sin handler** — un canal que rechaza, en un binario firmado,
ampliando la API declarada por una capacidad que todavía no existe. Es
exactamente lo que este repo rechaza al ampliar una lista cerrada, y rompía la
promesa de que la Historia 1 es entregable sola.

**Se parte**: `showApp` en la Fase 2 (siete), `redeemCode` con la Historia 2
(ocho). El argumento de por qué la lista puede crecer se hace una sola vez, que
era el propósito original; lo que se separa es **cuándo se publica cada
función**. `contracts/bar-preload.md` y el contrato de la spec 002 lo dicen.

Afecta a T002, T004 y T005. T029 y siguientes de la Historia 2 añaden la octava.

---

## Fase 3 · Historia 1 (P1) — volver a la pantalla del equipo

**Meta**: que se vea cómo volver.

**Prueba independiente**: se instala sólo esto, se va a la consola y se vuelve sin
teclado ni menú. Cierra el fallo 4.

**No toca autenticación ni la plataforma. Si el trabajo se para aquí, lo entregado
vale y se puede publicar.**

- [X] T007 **[TEST, ROJO]** [P] [US1] En `apps/desktop/tests/bar-state.test.ts`: con `surface: "console"` la barra ofrece `volver_a_la_app`; **sin** ese campo, no la ofrece — ni apagada ni con texto. _Requisitos: 1.1, 1.2_
- [X] T008 **[TEST, ROJO]** [P] [US1] En `apps/desktop/tests/bar-state.test.ts`: con `encryptionAvailable: false`, `volver_a_la_app` **sigue ofreciéndose**. Es el caso que se cuela si alguien la mete en `actionsFor(state)`, donde la filtra el `if (!state.encryptionAvailable) return []`. _Requisitos: 2.4_
- [X] T009 [US1] Añadir `volver_a_la_app` a `BarAction` y `surface?: "console"` a `BarState` en `apps/desktop/src/bar-state.ts`. **Fuera de `actionsFor(state)`**: es ortogonal a los siete estados de conexión, como `update`. _Requisitos: 1.1, 1.2, 2.4_
- [X] T010 [US1] Pintar la acción en `apps/desktop/src/bar/bar.ts`, con su copia en `es` y `en`, llamando a `window.auphere.showApp()`. _Requisitos: 1.1_
- [X] T011 [US1] En `apps/desktop/src/electron/main.ts`: empujar `surface` al estado de la barra cada vez que `showSurface(...)` cambia, y cablear `bar:showApp` a `showSurface("app")`. **Sin parámetro**: `showApp` sólo sabe volver. _Requisitos: 1.1, 1.3_
- [ ] T012 [US1] Comprobar a mano que el menú «Ver → Equipo», el icono de bandeja y `Cmd+Shift+A` siguen funcionando. Esta acción **se añade**, no sustituye. _Requisitos: 1.4_
- [ ] T013 [US1] Recorrer los seis pasos de la Historia 1 del [quickstart](quickstart.md), incluido el paso 5 —volver a la consola y ver que **sigue donde estaba**— y el caso del llavero cancelado. Dejar la salida en `.evidence/009/`. _Requisitos: 1.3, 1.4, 2.4_

**Punto de control**: **la Historia 1 es publicable sola.** Fallo 4 cerrado.

---

## Fase 4 · Historia 2 (P2) — entrar con Google

**Meta**: que una cuenta de Google entre.

**Prueba independiente**: con cuenta de Google y sin contraseña de la consola, se
entra de punta a punta.

### 4.1 · La plataforma

- [X] T014 **[TEST, ROJO]** [US2] `apps/api/tests/integration/test_session_codes.py`: emisión. Sólo tras Google; se guarda **el hash** y nunca el código; emitir uno nuevo invalida el anterior; sin sesión no se emite y **no se dice si la cuenta existe**. _Requisitos: 3.1, 3.2, 3.3, 3.4, 3.5_
- [X] T015 **[TEST, ROJO]** [US2] Mismo fichero: canje. Acuña **sesión nueva**; las dos sesiones son **independientes** (cerrar una no cierra la otra); se puede terminar la de la app sin la del navegador. _Requisitos: 4.1, 4.2, 4.3_
- [X] T016 **[TEST, ROJO]** [US2] Mismo fichero: un solo uso; caducado, usado e inexistente devuelven **exactamente lo mismo**; límite de intentos con espera creciente y un canje correcto limpia la cuenta. _Requisitos: 4.4, 4.5, 4.6_
- [X] T017 [US2] Migración `apps/api/alembic/versions/0122_session_codes.py` — tabla `console_auth.session_codes` tal y como la describe [data-model.md](data-model.md): `code_hash varchar(64)` **PK**, `principal_id uuid NOT NULL` FK a `console_auth.principals.id` `ON DELETE CASCADE`, `machine_hint varchar(255) NOT NULL` (hasheada), `created_at timestamptz NOT NULL`, `expires_at timestamptz NOT NULL`, `consumed_at timestamptz NULL` (**NULL = sin usar**; no se borra la fila). Índices en `principal_id` y `expires_at`. **Sin índice único parcial** para «uno vivo por persona»: se resuelve marcando `consumed_at`, porque un único devolvería error de base de datos donde toca una sustitución silenciosa. _Requisitos: 3.3, 3.4, 4.4_
- [X] T018 [US2] `apps/api/src/nexus_api/services/session_codes.py`: emitir y canjear, reutilizando `core/pairing_codes.py` (`ALPHABET`, `CODE_LENGTH = 8`, `CODE_TTL = 10 min`, `generate_code`, `display_code`, `normalize_code`, `hash_code`) y `PairingRateLimiter`. El canje llama a `console_identity.start_session(...)` — **el mismo camino del callback de Google**, no una copia. _Requisitos: 3.2, 4.1, 4.6_
- [X] T019 **[TEST, ROJO]** [US2] `test_session_codes.py`: **no suplantación**. Un código no concede más permisos que los de quien lo pidió; no sirve para entrar como otra persona; **rechazado desde otra máquina, con el mismo mensaje que un caducado**; no aparece en claro en registros ni trazas; la auditoría nombra a la persona y la máquina; canjear con otra cuenta dentro se trata como cambio de persona. **Va aquí y NO en `tests/isolation/`**: allí viven las 7 garantías entre tenants y esto no cruza ninguna — esconderlo ahí sería mezclarlo con algo distinto. _Requisitos: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6_
- [X] T020 [US2] `apps/api/src/nexus_api/api/console/session_codes.py`: las dos rutas, emisión y canje. El canje recibe la huella de máquina que `HttpTransport.pair()` ya manda (`hostname` + plataforma) y la compara **hasheada**. _Requisitos: 3.1, 4.1, 5.3_
- [X] T021 **[MUTACIÓN]** [US2] Por **cada** criterio de R5: romper la guarda y ver el test en rojo. Al menos: quitar la comprobación de máquina (5.3), quitar la de persona (5.2), y devolver mensajes distintos para caducado y usado (4.5 + 5.3). **Un test de seguridad que nadie ha visto fallar no es una guarda, es una intención.** _Requisitos: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6_

> **Hallazgo de la 4.1, y decide cómo se escribe la 4.2.** El plan no cerraba
> *cómo llega el token a la partición de Electron sin que la aplicación lo
> toque*. La respuesta, que evita tener que tocarlo: el principal hace la
> petición con `session.fromPartition(HUMAN_PARTITION).fetch(...)`, y **las
> cookies que el BFF devuelva se guardan solas en esa partición**. Así que el
> BFF canjea contra la API y pone la cookie con `setSessionToken`, igual que
> hace hoy el callback de Google; la cáscara nunca ve un token.
>
> Eso mantiene intacto el Requisito 2.1 de la spec 002 —la aplicación no tiene
> autenticación propia— sin excepciones que justificar. **La ruta de canje del
> BFF tiene que ser pública**: el código *es* la credencial, y pedirle sesión a
> quien viene a conseguir una sería pedirle la llave para darle la llave.

### 4.2 · La consola

- [X] T022 **[TEST, ROJO]** [P] [US2] Test de la pantalla del código en `apps/console/src/app/(auth)/__tests__/`: se pinta el código, se dice qué hacer con él, y **no** se ofrece a quien entró con correo y contraseña. _Requisitos: 3.1_
- [X] T023 [US2] `apps/console/src/app/auth/google/callback/route.ts`: tras `outcome === "session"`, redirigir a la pantalla del código **cuando la petición viene de la cáscara**. El resto sigue yendo a `/`. _Requisitos: 3.1_
- [X] T024 [P] [US2] `apps/console/src/app/(auth)/desktop-code/page.tsx` y el proxy `apps/console/src/app/api/session/code/route.ts`, con la sesión de la persona y sin credencial de backend. _Requisitos: 3.1_

### 4.3 · El escritorio

- [X] T025 **[TEST, ROJO]** [P] [US2] `apps/desktop/tests/bar-state.test.ts`: el fallo del canje se pinta **como estado y nunca en rojo**, igual que los otros siete. _Requisitos: 4.7_
- [X] T026 **[TEST, ROJO]** [P] [US2] `apps/desktop/tests/app-runtime-identity.test.ts`: el canje correcto deja la app dentro y **avisa del cambio de identidad**, igual que `pair()`. _Requisitos: 4.1_
- [X] T027 [US2] El canje en `apps/desktop/src/app-runtime.ts`, **junto a `pair()`** — son hermanos y conviene que se lean seguidos. Manda la huella de máquina que el runtime ya tiene. _Requisitos: 4.1, 5.3_
- [X] T028 [US2] La hoja del código en `apps/desktop/src/bar/bar.ts`, **reutilizando la que ya existe** para el emparejamiento. Copia en `es` y `en` que deje claro que este código trae la sesión y no empareja la máquina: se teclean igual y hacen cosas distintas. _Requisitos: 4.7_
- [ ] T029 [US2] Recorrer los nueve pasos de la Historia 2 del [quickstart](quickstart.md), **incluidas las tres comprobaciones que nadie hace**: sesiones independientes, cerrar la de la app sin la del navegador, y el `grep` del alfabeto sobre los logs. Salida cruda en `.evidence/009/`. _Requisitos: 4.2, 4.3, 5.4_
- [ ] T030 **[PUERTA]** [US2] Ejecutar **`/cso`**. Toca autenticación y secretos de un solo uso. **Un finding 🔴 bloquea el ship** hasta mitigar o aceptar el riesgo por escrito. _Requisitos: 5.1, 5.2, 5.3, 5.4_

**Punto de control**: fallo 1 cerrado. Una cuenta de Google entra.

---

### Enmienda del 2026-09-15 · el código no se ata a la máquina

Al escribir la pantalla de la consola se vio que **R5.3 y R3.1 no podían ser
ciertos a la vez**: quien pide el código es el navegador del sistema, que no
conoce el Mac donde corre la aplicación. `/speckit-analyze` no lo cazó porque
comprueba cobertura y trazabilidad, no si el flujo es físicamente posible — y
conviene saber que esa puerta tiene ese límite.

**Decidido por Luis: se retira la atadura** (spec §Enmienda, `[[ADR-039]]`).
Afecta a T017 (la columna `machine_hint` sale de la migración, que no estaba
desplegada), T018, T019 y T020. El test que comprobaba la atadura se sustituyó
por **uno que fija la pérdida**: cualquiera con el código entra, y si alguien
vuelve a atarlo se pondrá rojo y leerá el porqué.

## Fase 5 · Cierre

- [ ] T031 Actualizar `docs/desktop-workstation.md`: la barra tiene una acción más y el `preload` ocho funciones. **Mismo commit** que el código que lo cambia. _Requisitos: 1.1, 2.1_
- [ ] T032 Marcar en `docs/bugs-app-escritorio-2026-09-15.md` los fallos 1 y 4 como arreglados, con el enlace a esta spec. _Requisitos: —_
- [ ] T033 **[PUERTA]** `./scripts/verify.sh` **entero**, leyendo la cola en crudo. No vale `js` ni `py` sueltos: lo que se olvida es el worker, `mypy --strict`, el paquete compartido y el `next build`. _Requisitos: —_
- [ ] T034 Entregar el mensaje de commit y **PARAR**. Los commits los ejecuta la persona; hay un hook que bloquea `git commit`. _Requisitos: —_

---

## Dependencias

```
T001 ──► Fase 2 (T002–T006) ──┬──► Historia 1 (T007–T013) ──► ENTREGABLE
                              │
                              └──► Historia 2 (T014–T030) ──► ENTREGABLE
                                                    │
                                          Fase 5 (T031–T034)
```

- **Fase 2 bloquea a las dos**: las dos añaden una función al mismo `preload`.
- **Las dos historias son independientes entre sí.** La 2 no necesita nada de la 1.
- Dentro de la Historia 2: T017 (migración) antes de T018; T018 antes de T020;
  **T021 después de que T019 esté en verde** — no se puede mutar lo que aún no pasa.

## Qué se puede hacer en paralelo

- **T007 y T008**: mismo fichero, pero casos distintos y sin dependencia.
- **T022 y T024** (consola) con **T025 y T026** (escritorio): repos distintos del
  monorepo, sin tocarse.
- **T014, T015 y T016** son el mismo fichero: **en serie**, no en paralelo.

## Estrategia

**MVP = Historia 1.** Trece tareas, ninguna toca autenticación, y cierra el fallo
4. Si la Historia 2 se complica en `/cso` o en la revisión, la 1 ya está entregada
y publicada.

**La Historia 2 tiene su propia puerta** (T030) y es la única que puede
detenerse por seguridad. Que esté separada es lo que permite que esa puerta
bloquee sólo lo que tiene que bloquear.
