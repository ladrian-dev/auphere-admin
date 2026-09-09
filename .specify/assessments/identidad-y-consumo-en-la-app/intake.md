# Idea Intake: la identidad y el consumo en la aplicación de escritorio

- **Slug**: identidad-y-consumo-en-la-app
- **Created**: 2026-09-09
- **Source**: puntero al repositorio — `apps/desktop/src/electron/main.ts`,
  `apps/console/src/app/(auth)/`, `apps/console/src/lib/session.ts`,
  `apps/api/scripts/enrol_device_dev.py`,
  `apps/api/src/nexus_api/services/device_credential.py`,
  `apps/api/src/nexus_api/api/console/workstation.py` ·
  KB: `[[14-mvp-y-fases]]` §3 y `[[10-decisiones]]` decisiones 2 y 9
  (`/Users/lmatos/Work/Auphere/teammates/`)
- **Type**: new-capability

## Idea (as captured)

> Cuando el partner descarga la app, ¿cómo entra, cómo sabemos quién es, y cómo
> ve lo que tiene disponible — todo conectado con el login de Auphere y sin que
> la app guarde una credencial de backend?

La pregunta no se inventa aquí: está escrita en el repositorio, en el docstring
de la herramienta temporal que hoy suple lo que falta
(`apps/api/scripts/enrol_device_dev.py`):

> «Existe porque hoy no hay forma de emparejar un dispositivo desde el producto:
> el endpoint de alta existe, la superficie de uso no. El emparejamiento de
> verdad —quién eres, desde dónde entras, qué máquina reclamas— es una decisión
> de identidad, y esa evaluación **está sin abrir**. Escribir aquí un flujo
> provisional para "salir del paso" sería inventar esa decisión por la puerta de
> atrás.»

Esta es esa evaluación.

## Restated

La beta 2 entregó una cáscara de escritorio que carga la consola y un puente
saliente con credencial de dispositivo, pero **no existe ningún camino de
producto** desde «acabo de instalar la aplicación» hasta «estoy dentro, la
plataforma sabe quién soy, esta máquina está reclamada y veo lo que tengo
disponible». Hoy ese tramo lo cubre una variable de entorno y un script de
operador. La evaluación decide si ese camino se construye, con qué forma y con
qué alcance.

## Origin & Context

- **Raised by**: Luis, 2026-09-09.
- **Trigger**: cerrar el bloque de la spec 001 (73 de 76 tareas) dejó a la vista
  que las tres tareas pendientes —contención en Windows y firma— no son de
  identidad, y que la identidad no la cubría ninguna. El puente funciona de
  punta a punta **solo** si un operador ejecuta un script y pega el token en una
  variable de entorno.
- **Restricción de partida**: la spec 001 **no se reabre**. Lo ya resuelto
  —credencial de dispositivo (6.3), aislamiento de sesión (15.3) y que la app
  cargue la consola en vez de reimplementarla (15.1)— entra aquí como
  restricción heredada, no como pregunta.

## Superficie de confianza (§II)

`0` — API de la consola, y el tramo de emparejamiento sobre la `3a` ya abierta.
**No abre superficie nueva**, y ése es su argumento a favor bajo §II: agota
valor dentro de dos superficies cuyo precio de entrada ya se pagó en la beta 1 y
en la beta 2.

## Estado verificado del código (2026-09-09)

Lo que sigue está comprobado leyendo el código, no supuesto. Es contexto de
partida para `research`, no un veredicto.

| Hallazgo | Dónde |
|---|---|
| El login de la consola es propio: correo + contraseña (scrypt), la API devuelve un token **opaco** y la consola lo guarda en una cookie `httpOnly` de 7 días. La clave EdDSA vive en el servidor del BFF, nunca en el cliente | `services/console_identity.py` · `lib/session.ts` · `lib/jwt.ts` |
| La cáscara carga la consola hospedada en la partición **persistente** de la persona; la del agente no persiste | `electron/main.ts` · `session-isolation.ts` |
| **No hay ruta de registro.** Solo `login`, `invite/[token]` y `no-access`: se es partner por invitación y pertenencia en `partner_memberships` | `app/(auth)/` |
| **El alta de dispositivo no tiene superficie de producto.** El endpoint existe y devuelve `pairing_token` una sola vez, pero el cliente de la consola solo expone `listDevices`, y el panel es de lectura | `console/workstation.py` · `lib/backend/workstation.ts` · `components/workstation/workstation-panel.tsx` |
| La app toma la credencial de `AUPHERE_DEVICE_TOKEN`; sin ella abre la ventana y **no** arranca el puente | `electron/main.ts` |
| La credencial de dispositivo dura **12 h**, es apátrida y **no hay camino de renovación** | `services/device_credential.py` (`DEFAULT_TTL`) |
| El medidor es **uno**: el consumo de modelo de las sesiones locales ya entra por `debit_wallet` y se ve en `/usage`. No hay un segundo libro | `services/local_workstation_metering.py` · spec 001 T015 |
| `partner_devices` lleva `tenant_id`: el dispositivo pertenece a un **tenant cliente**, no al partner, y la ruta es `/console/clients/{ref}/workstation` | `data-model.md` §1 · `console/workstation.py` |
| `principal_id` se **escribe** (desde `scope.principal.user_id`) y **nunca se lee**: `list_active()` no filtra por persona | `repositories/local_workstation.py` |

## Restricciones heredadas que esta evaluación no reabre

- **Requisito 15.2** — la aplicación no almacena ninguna credencial de backend.
  Cualquier opción que lo incumpla queda descartada sin discusión.
- **Requisito 15.3** — la sesión de la persona no es alcanzable desde el ambiente
  del agente. Particiones separadas, la del agente sin persistencia.
- **Requisito 15.1** — la app carga las pantallas de la consola, no las
  reimplementa.
- **Requisito 6.3** — la credencial de dispositivo es propia de la máquina,
  acotada a su tenant y a cuatro operaciones.
- **§VI** — un agente no navega la consola de Auphere.
- **Un solo medidor.** Todo lo que se muestre de consumo sale de `usage_ledger` y
  del wallet que ya existen. Dos contadores es donde las cifras dejan de cuadrar.

## First-Glance Unknowns

- [NEEDS CLARIFICATION: **¿basta el login de la consola dentro de la ventana?**
  Hay que probarlo, no razonarlo: cookie `sameSite=lax` y `secure` dentro de un
  `BrowserWindow`, el enlace de invitación que llega por correo y hoy es un GET
  de nivel superior en un navegador, la caducidad a los 7 días, el camino
  `no-access`, y qué ocurre con los enlaces externos. La respuesta es una lista
  de lo que falta de verdad.]
- [NEEDS CLARIFICATION: **¿cómo se empareja la máquina con la persona que acaba
  de entrar?** Es el hueco entero: el endpoint existe, la superficie no, y el
  token viaja hoy por variable de entorno.]
- [NEEDS CLARIFICATION: **multi-seat.** La decisión 9 dice hilo privado por
  persona. El modelo tiene `principal_id` y nadie lo lee. La spec 001 supuso
  «el partner es dueño de su máquina», supuesto que en una máquina compartida
  deja de ser cierto — y la 001 dejó multi-seat explícitamente fuera de alcance.]
- [NEEDS CLARIFICATION: **un dispositivo, ¿de quién es?** `partner_devices` está
  acotado por tenant cliente. Un portátil que trabaja para cinco clientes, ¿son
  cinco altas y cinco credenciales, o el modelo tiene que cambiar de dueño?]
- [NEEDS CLARIFICATION: **¿qué es cerrar sesión, y qué es desemparejar?** Son dos
  actos distintos. Qué implica cada uno sobre el otro está sin decidir, y la
  credencial de 12 h sin renovación obliga a decidirlo.]
- [NEEDS CLARIFICATION: **¿qué ve el partner de su consumo dentro de la app, y se
  conforma con cargar `/usage`?** Si la app enseña saldo por su cuenta, ahí es
  por donde entra el segundo contador.]
- [NEEDS CLARIFICATION: **¿hay registro desde la app?** Hoy no lo hay en ningún
  sitio: se entra por invitación. Y choca con la decisión **§2.3 abierta** de
  `[[10-decisiones]]` («¿qué sobrevive, el onboarding del diseño o el
  autoservicio?»). Esta evaluación **no cierra esa decisión por la puerta de
  atrás**: la declara como dependencia y acota su alcance a lo que sea cierto en
  los dos escenarios.]

## Lo que esta evaluación declara fuera desde el minuto uno

- **La revocación de dispositivo, que hoy no funciona.** `verify_device_token` no
  mira `revoked_at` y `record_heartbeat` tampoco: un dispositivo archivado desde
  la consola sigue latiendo y sondeando hasta que caduca su token. El Requisito
  6.3 dice «revocable por sí sola» y ningún test lo cubre — es el mismo patrón
  que ya se destapó dos veces en la 001: **cobertura por cita no es cobertura por
  capacidad**. No es idea nueva: es la 001 incumpliendo un criterio que ella
  misma escribió, y va por `/speckit-bug-assess` o por una tarea de converge
  sobre `specs/001-puesto-trabajo-partner/`. Se anota aquí para que esta
  evaluación no se lo trague por comodidad.
- **Controlar el escritorio (`3b`)**, el navegador embebido y la beta 5. Fuera de
  alcance en la 001 y siguen fuera.
- **Precio y facturación.** Esta evaluación mira qué **ve** el partner de su
  consumo, no cuánto cuesta.
