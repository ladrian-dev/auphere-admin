# Decision: la máquina se registra con la sesión, sin código

- **Slug**: maquina-sin-emparejar
- **Decided**: 2026-09-22
- **Verdict**: **go** — Opción B, con seis decisiones tomadas en esta puerta.
  Las dos últimas (D-5, D-6) las cerró Luis el mismo día al contestar lo que el
  repositorio no podía saber
- **Artifacts reviewed**: [`intake.md`](./intake.md) · [`research.md`](./research.md)
  · [`problem.md`](./problem.md) · [`concept.md`](./concept.md)
- **Superficie de confianza (§II)**: `3a` (el puente) y la API. El intake decía
  «**abre superficie**: un endpoint que emite una credencial de máquina a partir
  de una sesión web». **Matiz que cambia la lectura**: ese endpoint sustituye a
  otro que hoy emite la misma credencial a partir de un código tecleado desde
  una app que **ya tiene esa misma sesión**. No es superficie nueva: es la misma
  puerta con una llave menos redundante.

---

## Scorecard

| Criterio | Valoración | Justificación |
|---|---|---|
| **Validez del problema** | **strong** | La pregunta central del intake —qué protege el código que la sesión no proteja— tiene respuesta en dos líneas de código: `pair()` aborta sin `userId`, y `userId` solo llega de un `whoami` con éxito. El segundo acto prueba lo que el primero ya probó |
| **Fuerza de la evidencia** | **strong** | Lectura directa con ruta y línea, los dos hechos decisivos verificados a mano. Y tres huecos que el intake no tenía —revocación rota, auditoría a medias, sin límite de máquinas— encontrados por el barrido, no supuestos |
| **Valor frente a no hacer nada** | **adequate** | El valor de experiencia es real pero no urgente: 12 pasos frente a 3-4. Lo que sube esta fila es que los tres huecos **ya están abiertos** con el código puesto, y esta es la ocasión de cerrarlos con contexto |
| **Viabilidad / apetito** | **strong** | El camino de sustitución está abierto, en uso y con test (`redeem`). El permiso se **mueve**, no se crea. Y a diferencia de la 009, **no abre ningún puerto** ni enmienda ningún requisito de aislamiento |
| **Encaje estratégico** | **strong** | Retira un paso que la industria entera retiró, y que además **es un vector conocido** (Storm-2372 contra el device code flow). No se acepta riesgo a cambio de comodidad: se retira riesgo |
| **Postura de riesgo** | **adequate** | El riesgo real está nombrado y tiene respuesta: la cookie persistente puede estar ahí de antes, y por eso se elige B y no A. No es `strong` porque el umbral de frescura hay que elegirlo, y todo umbral es arbitrario hasta que se justifica con datos que hoy no hay |

---

## Verdict & Rationale

**Go, Opción B**: registro silencioso al entrar, **con sesión recién
confirmada** para el canje.

El intake pidió expresamente no responder por analogía a la pregunta central, y
tenía razón en pedirlo, porque la analogía con Remote Control habría bastado
para convencer sin probar nada. El código contesta mejor que la analogía:
`app-runtime.ts:291-295` y `:272` demuestran que **la aplicación ya tiene sesión
confirmada antes de poder teclear el código**. No es que el código sea
redundante en teoría: es que en la práctica solo se puede teclear desde una app
que ya demostró quién es.

Queda una única diferencia y el intake la había visto: la cookie puede estar ahí
de antes. **Esa objeción es cierta y por eso se elige B y no A.** Pero su
respuesta no es un código de ocho símbolos —que tampoco mide frescura de sesión,
mide tener acceso a otra pantalla del mismo navegador—: es exigir que la sesión
se haya confirmado hace poco, y mandar a entrar si no. El flujo de entrar ya
existe, es RFC 8252 + PKCE, y la 009 lo adoptó a propósito.

En el camino que importa —instalar y usar por primera vez— **B es idéntica a
A**: la sesión se acaba de confirmar, no hay paso extra, y se pasa de doce pasos
a cuatro. El coste solo se paga donde debe pagarse.

Se rechaza la C (conservar el código para máquinas ajenas) porque mantiene
entero lo que se quería retirar —tabla, diálogo, alfabeto duplicado en cliente,
límite de intentos, dos caminos que auditar— por un caso que **nadie ha
confirmado que exista**. Si existe, se reabre; reabrir después es barato.

---

## Las cuatro decisiones que esta puerta toma

**D-1 · Los tres huecos entran en el alcance. No son efectos secundarios: son
la condición para que el cambio sea honesto.**

- **Desemparejar revoca de verdad.** Hoy `unpair()` solo olvida localmente y la
  credencial vive hasta 12 h; la copia de la app promete otra cosa. Archivar ya
  existe y el motivo `"desemparejada"` está declarado **sin escritor**: es
  llamarlo desde donde falta.
- **Los dos extremos dejan asiento.** `device.unpaired` está en el vocabulario
  desde `0108_device_audit_vocab.py:66` y nadie lo escribe. Registrar deja cinco
  asientos; retirar, ninguno.
- **Hay límite de máquinas.** No existe ninguno. El límite práctico era la
  fricción de pedir un código; **retirarla sin poner un tope quita el único
  freno que había**.

La razón de que los tres vayan juntos y ahora: con registro gratis, desemparejar
tiene que significar algo, y con desemparejar significando algo, la auditoría
tiene que contarlo. Separarlos deja un sistema donde entrar es gratis y salir no
existe.

**D-2 · El acto deliberado sube a la carpeta, y eso es la mitad del valor.**

`POST /device/links` ya existe con sus asientos y su denegación. Lo que falta no
es construirlo: es que **se vea**. Hoy la ceremonia está sobre la caja y los
directorios están enterrados en una hoja que casi no se veía. Al revés es como
lo hacen Claude y Grok, y es la decisión que de verdad importa.

**D-3 · Se hereda sin discusión la lista que la 009 dejó escrita.**

`specs/009-…/spec.md:64-65`: **uso único, hash, rechazo indistinguible y límite
de intentos**. Aplicado al canje nuevo: la credencial se emite una vez, el fallo
se responde igual sea cual sea el motivo, y hay techo de intentos. Que el canje
pase a ser por cookie no relaja ninguna de las cuatro.

**D-4 · El permiso se comprueba en el canje del BFF.**

`workstation:pair` hoy se comprueba al **emitir** el código, y `POST /device/pair`
**no comprueba ningún permiso** — leído entero, sus dependencias son la sesión de
base de datos y Redis, nada más. Con el código retirado, la comprobación tiene
que viajar al sitio donde ahora se decide. Es mover una comprobación que existe,
no inventar una.

---

## La pregunta que esta puerta no podía contestar, contestada

**¿Existe el caso de emparejar una máquina que no es la tuya?** Un servidor, una
máquina compartida, un portátil de alguien del equipo configurado por otra
persona.

El repositorio no lo sabe y no hay forma de deducirlo del código.

> **Respuesta de Luis, 2026-09-22: «no existe ese caso».**

**D-5 · El código de emparejamiento se retira entero.** No sobrevive como camino
secundario. Se van con él la tabla `device_pairing_codes`, su migración, el
emisor de la consola, el diálogo de la consola, el diálogo de la app, el
alfabeto duplicado en cliente (`app/routes/pair-dialog.tsx:30-31`), el limitador
de intentos del canje viejo y los canales IPC `app:workstation.pair`.

Lo que **no** se va con él es la lista de la 009 (D-3): uso único, hash, rechazo
indistinguible y límite de intentos siguen aplicando al canje nuevo. Se retira la
ceremonia, no las propiedades.

La Opción C queda descartada por dato, no por juicio. Si algún día aparece el
caso —una máquina de equipo, un servidor de un partner grande— se reabre con su
propia evaluación, y entonces tendrá un caso de uso real detrás en vez de una
hipótesis.

---

## Lo que queda abierto y no lo cierra esta puerta

1. **El umbral de «sesión recién confirmada».** `last_used_at` existe
   (`db/models/console_identity.py:99`), pero **«confirmada» puede no ser lo
   mismo que «usada»** y hay que mirarlo antes de fijar el número. Es trabajo de
   la fase de plan, no de ésta.
2. **Qué pasa al desemparejar y volver a entrar.** Con registro por sesión, por
   defecto se registra sola otra vez. Hay que decidir si desemparejar debe ser
   pegajoso, y eso choca con D-1: si archivar es terminal —y lo es: «Borrar no
   existe: se archiva, y queda por qué»—, volver a registrar crea una fila
   nueva. Hay que comprobar que eso no tropieza con la archivada.
3. ~~**T-5, el cruce con `recuperar-la-contrasena`**~~ → **cerrado el 2026-09-22.
   Respuesta de Luis: sí, restablecer la contraseña revoca las máquinas.** Ver
   D-6.

---

## D-6 · Restablecer la contraseña revoca las máquinas

> **Decisión de Luis, 2026-09-22**, común a esta evaluación y a
> [`recuperar-la-contrasena`](../recuperar-la-contrasena/decision.md).

Quien recupera su contraseña sale con **todas** sus sesiones cerradas y
**todas** sus máquinas archivadas. Es coherente con el motivo real de recuperar:
si alguien pudo entrar en la cuenta, pudo registrar una máquina, y cerrar solo
las sesiones habría dejado abierta la puerta más peligrosa de las dos — una
credencial de máquina abre ejecución local.

**Lo que esto obliga, y que conviene ver junto:**

1. **Hay una pieza común a las dos specs**: «retirar todo el acceso de esta
   persona» — sus sesiones y sus máquinas, en una transacción. Ya existe media:
   `archive_all_for_principal` (`repositories/local_workstation.py:138-147`), hoy
   llamada solo al retirar la pertenencia. Falta el lado de las sesiones, que no
   existe en ninguna forma.
2. **Se entrega una vez, no dos.** Sea cual sea la spec que vaya primero, esa
   construye la pieza y la otra la usa. Duplicarla sería garantizar que un día
   divergen.
3. **El coste para la persona es real y hay que decirlo en la pantalla**:
   recuperar la contraseña significa volver a entrar en cada máquina. Con
   registro por sesión (esta spec) ese coste baja a «abre la app y entra», que
   es precisamente lo que hace la decisión asumible. **Las dos specs juntas se
   sostienen mejor que cualquiera de las dos sola**, y ése es el argumento para
   hacer la 012 antes que la 011.
4. **Archivar es terminal.** Volver a registrar crea una fila nueva; hay que
   comprobar que no tropieza con la archivada (ya estaba anotado arriba, y ahora
   es camino principal y no caso raro).

---

## Lo que la spec tiene que declarar en su encabezado

- **Superficie**: `3a` y la API. Se declara **sustitución**, no apertura, con el
  matiz de arriba escrito — y aun así, modelo de amenaza antes del código, como
  pedía el intake.
- **Garantías tocadas**: ninguna de las ocho se debilita. La credencial sigue
  nombrando partner, máquina y generación y nunca tenant
  (`services/device_credential.py:3`), y eso lo vigila
  `test_29_device_credential_scope.py`. Los tests de
  `test_30_device_partner_scope.py` tienen que seguir verdes sin tocarlos: si
  hay que aflojar uno, el cambio está mal.
- **Qué se mide**: nada nuevo.
- **Orden de entrega**, con cada tramo entregable solo:
  1. **Retirar todo el acceso de una persona** — sesiones **y** máquinas, en una
     transacción (D-1 + D-6). Tiene valor **hoy**, con el código puesto, y no
     depende de retirar nada. Es además **la pieza que comparte con la 011**: se
     construye aquí y allí se usa.
  2. **Los otros dos huecos de D-1**: asiento en los dos extremos y límite de
     máquinas.
  3. **El registro por sesión (B)**.
  4. **La carpeta al frente (D-2)**.
  5. **Retirar el código entero (D-5)**, una vez que nadie lo usa: tabla,
     migración, emisor, los dos diálogos, el alfabeto duplicado y los canales
     IPC.
- **Esta spec va antes que la 011**, y la razón está en D-6: con el código de
  emparejamiento todavía puesto, revocar máquinas al restablecer la contraseña
  obliga a repetir la ceremonia en cada una.
