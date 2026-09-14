---

description: "Tareas de la spec 008 — empaquetado, firma y canal de actualización"
---

# Tasks: la aplicación se instala, y se arregla sola

**Input**: documentos de diseño en `/specs/008-empaquetado-firma-y-canal/`

**Prerequisites**: [plan.md](./plan.md) · [spec.md](./spec.md) ·
[research.md](./research.md) · [data-model.md](./data-model.md) ·
[contracts/release-channel.md](./contracts/release-channel.md) ·
[quickstart.md](./quickstart.md)

**Tests**: obligatorios (§VII). Con una salvedad que se dice aquí y no se
disimula: **el criterio que de verdad importa —que el artefacto abra en un Mac
limpio— no se puede automatizar.** Se ejecuta a mano, con su evidencia, y no se
finge con un test que comprueba otra cosa.

## Reglas de este repo

- Cada tarea cita sus requisitos: `_Requisitos: N.m_`.
- Los commits los ejecuta la persona: el agente entrega el mensaje y para.
- **Antes de un `apply` de Terraform, se enseña el plan y se lee entero.** Si
  aparece algo que nadie pidió, se para y se pregunta.
- **El orden secreto → Terraform → despliegue no se negocia.**
- Producción tiene 3 clientes reales con tráfico.

---

## Phase 1: Setup — el bloqueante y el rescate

**Propósito**: desbloquear lo que no se arregla programando, y recuperar lo que
ya está escrito.

- [X] T001 **Exportar el `.p12` del certificado de firma y guardarlo como secreto
      de repositorio.** Es un acto humano en la máquina donde vive la clave, no
      código. **Bloquea toda la Fase 3 y la Fase 4**: sin él no se puede firmar
      en integración continua y R5.1 es incumplible. Hoy la clave privada está
      **sólo** en el llavero `login` de una máquina y **no hay copia**: si esa
      máquina se pierde antes de esta tarea, hay que pedirle a Facelad que emita
      otro certificado, porque un Developer ID **sólo lo crea el Account
      Holder**. _Requisitos: 5.1, 5.2_
      **HECHO** el 2026-09-14: `gh secret list` muestra los seis `APPLE_*`
      (`APPLE_CERT_P12_BASE64`, `APPLE_CERT_PASSWORD`, `APPLE_TEAM_ID`,
      `APPLE_API_KEY_P8_BASE64`, `APPLE_API_KEY_ID`, `APPLE_API_ISSUER_ID`).
      Falta `AWS_RELEASE_ROLE_ARN`, que no puede existir todavía: lo crea T008.
      **Sin verificar desde aquí**: que exista la copia sellada del `.p12` y su
      contraseña fuera de GitHub — los secretos son de sólo escritura, así que
      si esa copia no está, sigue sin haber respaldo (R5.4).
- [X] T002 [P] Rescatar `e100564` de `feat/desktop-auto-update` con `cherry-pick`,
      conservando autoría y mensaje: entitlements, `.gitignore`, política de
      actualización, actualizador, configuración de empaquetado y sus dos
      ficheros de prueba. No se reescribe nada. _Requisitos: 6.1_
- [X] T003 Ejecutar `cd apps/desktop && pnpm test` y dejar la salida cruda en
      `specs/008-empaquetado-firma-y-canal/evidence/rescued-tests.txt`. **Va
      antes de construir nada**: firmar una aplicación cuyas pruebas nadie corre
      es firmar a ciegas. _Requisitos: 6.2_
      **HECHO**: 38 ficheros, **321 pruebas en verde**. Y una nota que ahorrará
      diez minutos al siguiente: `pnpm test` **dentro de `apps/desktop` no
      funciona** — esa carpeta tiene su propio `pnpm-workspace.yaml` que no lista
      `packages/companion-ui`, y pnpm resuelve el más cercano. Se corre desde la
      RAÍZ con `pnpm --filter @nexus/desktop test`, como hace `ci.yml`, que ya lo
      dejó advertido en un comentario.
- [X] T004 [P] Actualizar `T057` en `specs/001-puesto-trabajo-partner/tasks.md`:
      dejó de estar bloqueada por certificados el 2026-09-13. Y `T070`, que da
      por pendiente lo que `e100564` ya hizo. _Requisitos: 6.3_

**Checkpoint**: el cliente está en la rama y sus pruebas pasan. Nada se ha
firmado ni publicado.

---

## Phase 2: Foundational — el sitio donde publicar

**Propósito**: sin canal no hay nada que publicar, y sin el rol acotado no se
puede afirmar que sólo la cadena escribe.

**⚠️ Bloquea las tres historias.**

### Tests primero

- [X] T005 [P] `terraform validate` y `terraform plan` del módulo nuevo, con el
      plan **leído entero** y su salida guardada en `evidence/terraform-plan.txt`.
      Un recurso que aparezca sin que nadie lo pidiera **para la tarea**.
      _Requisitos: 7.1, 7.3_
      **HECHO.** El `plan` **sí se pudo ejecutar**: había un perfil `nexus` en
      esta máquina (`arn:aws:iam::793033583982:user/nexus-admin`) que no comprobé
      la primera vez. Y leerlo entero valió la pena: la primera versión del
      módulo **borraba un `ordered_cache_behavior`** de producción —
      `desktop/*.yml` con `CachingDisabled`, que es lo que hace que una
      publicación se vea al instante sin depender de una invalidación. Se
      reprodujo antes de aplicar.
- [X] T006 [P] Comprobación de que `NEXUS_DEVICE_TOKEN_SECRET` **existe en el
      almacén de secretos** antes de aplicar nada de `20-services`. Está
      declarada en `variables.tf:89` desde hace tiempo y Terraform no se aplica
      en el despliegue automático: el día que alguien lo aplique, ECS aborta el
      arranque si falta. Cuesta un minuto comprobarlo y una tarde descubrirlo.
      _Requisitos: 7.4_

### Implementación

- [X] T007 `infra/terraform/40-releases/main.tf`: bucket **privado** y
      distribución de CloudFront con *Origin Access Control*, certificado en
      **`us-east-1`** (donde CloudFront los exige, aunque todo lo demás viva en
      `eu-south-2`) y `updates.auphere.com` como CNAME desde Cloudflare, que es
      quien ya lleva el DNS. **Un solo canal**, sin gradual ni canal de pruebas
      separado: con tres partners, lo que contiene una versión mala es que la
      anterior siga disponible y una llamada de teléfono. _Requisitos: 2.1, 3.6, 7.1_
- [X] T008 `infra/terraform/40-releases/iam.tf`: el rol OIDC que publica,
      **distinto del de despliegue** y acotado a escribir sólo en el prefijo del
      canal. Es lo que hace comprobable que quien despliega no puede publicar
      binarios y al revés. _Requisitos: 2.2_
- [X] T009 Borrar `infra/terraform/40-releases/prod.tfplan`. Es un plan binario
      huérfano de un módulo que nunca se versionó, y un plan binario en el
      repositorio no es documentación: es estado que nadie puede leer.
      _Requisitos: 7.2_
- [X] T010 Aplicar la infraestructura **después** de enseñar el plan, y comprobar
      desde fuera que el canal responde por HTTPS **sin credenciales** y que una
      identidad de persona **no puede escribir** en él. _Requisitos: 2.1, 2.2, 2.3_
      **HECHO, y el canal ya existía.** Doce recursos aplicados el 2026-09-13
      desde un módulo que nunca se versionó: bucket, CloudFront `E1UACSCSVRLYPG`
      **Deployed**, certificado ACM **ISSUED**, DNS resolviendo y TLS válido. Lo
      único que faltaba era el rol de publicación, creado ahora:
      `arn:aws:iam::793033583982:role/nexus-prod-desktop-publisher`
      (`2 added, 0 changed, 0 destroyed`). Tras el apply, `terraform plan` dice
      **«No changes»**: el código del repositorio describe ya exactamente lo que
      hay, que es lo que R7.1 pedía.

**Checkpoint**: hay dónde publicar, y está probado que sólo la cadena escribe.

---

## Phase 2b: Las puertas de la constitución

- [X] T011 **Aislamiento: ninguna de las 7 garantías se toca, y es una decisión
      escrita, no un descuido.** No hay tenant, ni RLS, ni herramienta nueva. Lo
      que esta superficie sí exige es una prueba de **integridad de artefacto**,
      que no vive en `tests/isolation/` porque no es aislamiento entre tenants:
      son T019 y T024. Esta tarea comprueba que sigue siendo verdad — que la
      versión mínima no gana `tenant_id` y que el canal no distingue quién
      descarga. _Requisitos: 1.5, 3.4_
- [X] T012 **Licencias (§VIII): no aplica, y es una decisión.** Ninguna
      dependencia nueva: `electron-builder` y `electron-updater` ya están (MIT),
      `codesign`/`notarytool`/`stapler` vienen con Xcode, y
      `aws-actions/configure-aws-credentials` ya se usa en `deploy-prod.yml`.
      _Requisitos: —_
- [X] T013 **Medidor: no gasta nada que se mida.** Ni modelo, ni reloj de
      máquina, ni herramienta de pago. El coste del canal es de infraestructura y
      se ve donde ya se ven los demás. Esta tarea lo deja escrito para que nadie
      lo busque en Consumo. _Requisitos: —_

**Checkpoint**: las puertas tienen dueño. Sin esto `/speckit-analyze` no da verde.

---

## Phase 3: US1 — Alguien ajeno instala la aplicación y entra (P1) 🎯 MVP

**Goal**: existe algo que instalar, y se abre en un Mac que nunca ha visto el
proyecto.

**Independent Test**: se construye el artefacto, se copia a un Mac limpio y se
abre. Se demuestra solo, sin canal y sin actualización.

**⚠️ Depende de T001.** Sin el `.p12` no se firma.

### Tests primero ⚠️

- [X] T014 [P] [US1] Prueba de humo de la cadena en
      `.github/workflows/release-desktop.yml`: **abrir el `.app` firmado antes de
      publicar**, y no publicar si no abre. `hardenedRuntime` sin los permisos
      correctos **no falla al construir: falla al abrir**, así que construir en
      verde no prueba nada. _Requisitos: 1.6_
      **ESCRITO, sin primera ejecución.** El paso «Abrir el .app firmado» está en
      `release-desktop.yml` y falla el trabajo si el proceso no sigue vivo a los
      20 s. No se ha ejecutado nunca: necesita el rol de T010.
- [X] T015 [P] [US1] Verificación del artefacto en la propia cadena: cadena de
      firma hasta la raíz de Apple, `flags=0x10000(runtime)`, veredicto de
      Gatekeeper y **sello grapado**. La salida cruda se guarda como evidencia
      de la ejecución. _Requisitos: 1.2, 1.3_

### Implementación

- [X] T016 [US1] `.github/workflows/release-desktop.yml` sobre **`macos-latest`**
      — el primer runner no-Ubuntu del repo—, disparado por marca de versión **y
      por disparo manual**, que corre `./scripts/verify.sh` antes de construir.
      _Requisitos: 1.1, 2.6_
      **ESCRITO, sin primera ejecución.** 14 pasos, `macos-latest`, OIDC, tag `v*`
      y disparo manual con motivo obligatorio. Corre `typecheck` y `test` del
      escritorio **antes** de construir. Usa `pnpm --filter` desde la raíz, que es
      la trampa que ya me tragué una vez en T003.
- [X] T017 [US1] Importar el `.p12` a un **llavero temporal creado para esa
      ejecución** y destruirlo al terminar, pase lo que pase. Que «no depende del
      llavero de nadie» y «no queda accesible después» sean lo mismo.
      _Requisitos: 5.1, 5.2_
- [X] T018 [US1] Firmar, notarizar con la clave de App Store Connect que ya
      existe, y **grapar el sello al artefacto** para que la primera apertura no
      dependa de tener red. Construir dmg y zip para arm64 y x64.
      _Requisitos: 1.1, 1.2, 1.3_
- [X] T019 [US1] `apps/desktop/tests/`: un artefacto modificado después de
      firmarlo **se rechaza**. Es media puerta de aislamiento (T011): la
      integridad del artefacto es la garantía de esta superficie.
      _Requisitos: 1.5_
- [X] T020 [US1] Fijar como **prueba** que el repositorio no acepta material de
      firma: un caso que recorra `git check-ignore` sobre `*.p12`, `*.pfx`,
      `*.p8`, `*.cer`, `*.certSigningRequest`, `*.mobileprovision`, `*.keychain`
      y `*.keychain-db`, **en la raíz y dentro de `apps/desktop/`**, y falle si
      alguno deja de ignorarse.

      **Esta tarea estaba escrita sobre una premisa falsa.** Decía que el
      `.gitignore` «ya rechaza» ese material y que sólo faltaba fijarlo. **No lo
      rechazaba**: el 2026-09-14, al preparar la exportación del certificado, se
      comprobó con `git check-ignore -v` que un `cert.p12` en la raíz **habría
      entrado en un commit sin avisar**. El bloque se añadió ese día y se
      verificó caso por caso; lo que falta es el test que impida que alguien lo
      revierta.

      Dos cosas que conviene no perder: **`grep` sobre el `.gitignore` no vale**
      —hay reglas que se anulan entre sí, y de hecho una excepción de
      `apps/desktop/build/` convivía con esto—, y **la historia ya se auditó**:
      ningún `.p12`, `.p8`, `.cer` ni `.pem` entró nunca, comprobado sobre todas
      las ramas. Si lo hubiera hecho, no bastaría borrarlo: habría que revocar.
      _Requisitos: 5.3_
      **HECHO, y verificado por sabotaje.** 25 casos: los ocho patrones en tres
      ubicaciones, más uno que comprueba que los entitlements **sí** viajan. Al
      quitar `*.p12` y `*.p8` del `.gitignore` se ponen en rojo **6 casos exactos**
      y el resto sigue verde — cada caso mira su patrón, no un genérico.
- [ ] T021 [US1] **Abrir el artefacto en un Mac limpio**, a mano, y dejar la
      evidencia en `evidence/clean-mac.md`: qué máquina, qué versión, y si
      apareció **algún** diálogo del sistema. **Esto no se puede automatizar y no
      se sustituye por ningún test.** Si aparece cualquier aviso, la cadena no
      está lista por muy verde que esté todo lo demás. _Requisitos: 1.4_

**Checkpoint**: hay un instalador que funciona. Todavía no se actualiza nada.

---

## Phase 4: US2 — Una corrección llega sola, sin interrumpir trabajo (P2)

**Goal**: una instalación existente adopta una versión nueva sin que nadie
reinstale y sin matar trabajo vivo.

**Independent Test**: se publican dos versiones seguidas y se observa a una
instalación real coger la segunda.

### Tests primero ⚠️

- [X] T022 [P] [US2] Con una aprobación pendiente **y sin sesiones vivas**, la
      decisión sigue siendo esperar. _Requisitos: 3.2_
      **YA ESTABA CUBIERTO** por el test rescatado «con una acción esperando a
      una persona, también espera». La premisa de esta tarea —que nadie pasaba
      la segunda cifra— era falsa (ver T026).
- [X] T023 [P] [US2] Los dos estados nuevos de la barra en
      `apps/desktop/tests/`: «lista, se instala al cerrar» y «esperando, y por
      qué» son **distintos**, y sin versión esperando la barra **no dice nada**
      sobre actualizaciones — ni indicador apagado ni explicación de lo que no
      hay (§V). _Requisitos: 3.7, 3.8_
- [X] T024 [P] [US2] Un binario **sin firma de distribución no pide nada al
      canal**, ni siquiera con un paquete ya descargado en disco. La otra media
      puerta de T011. _Requisitos: 3.4_
- [X] T025 [P] [US2] Un artefacto que no supera la comprobación de firma **no se
      aplica**. _Requisitos: 3.5_

### Implementación

- [X] T026 [US2] Pasar a la política el **número de aprobaciones pendientes**,
      junto al `liveCount` que `e100564` ya añadió al concentrador de streams.
      _Requisitos: 3.2_
      **YA ESTABA HECHO en `e100564`**, y la tarea partía de una premisa falsa
      (research D7, corregido). `main.ts` cablea las dos cifras, y filtra las
      de nivel `informativo`: no esperan a nadie, así que no deben impedir una
      instalación. Comprobado leyendo `readActivity`; no hizo falta tocar nada.
- [X] T027 [US2] `apps/desktop/src/bar-state.ts`: el estado nuevo, con sus dos
      formas. Es superficie de interfaz nueva y por eso se nombra, en vez de
      colarse como detalle. _Requisitos: 3.7, 3.8_
- [X] T028 [US2] Publicar al canal desde la cadena, asumiendo el rol OIDC de
      T008. **Publicar es añadir y mover el puntero**: los paquetes anteriores
      **no se borran** — son la única marcha atrás que existe cuando el puente es
      saliente. Y se publica **al único canal**: no hay cohortes ni fracciones
      que decidir. _Requisitos: 2.1, 2.4, 2.5, 3.6_
      **ESCRITO, sin primera ejecución.** Los paquetes suben **antes** que el
      índice: al revés, el canal anunciaría durante unos segundos una versión
      cuyo binario no está, y el actualizador que la pidiera se llevaría un 404.
- [X] T029 [US2] Dejar constancia de cada publicación: qué versión, desde qué
      punto de la historia del código y quién la disparó. _Requisitos: 2.4_
- [X] T030 [US2] Comprobar que **no hay ninguna vía de poner un artefacto en el
      canal que no sea la cadena** (R2.7). Un binario firmado en el portátil de
      alguien y subido a mano no es una emergencia resuelta: es la garantía de
      esta superficie rota, y para eso existe el disparo manual de T016.
      _Requisitos: 2.7_
- [ ] T031 [US2] Recorrer el ciclo completo a mano: instalar N en el Mac limpio,
      publicar N+1, dejar una tarea esperando confirmación, y comprobar que
      descarga, **espera y lo dice**, y se aplica al cerrar tras resolverla.
      Evidencia en `evidence/update-cycle.md`. Y se anota si la cadena publicó
      **sin nadie delante** desde la marca de versión: es lo único que demuestra
      CE-003, y se demuestra aquí o no se demuestra.
      _Requisitos: 3.1, 3.2, 3.3_

**Checkpoint**: se puede hacer llegar una corrección sin que nadie reinstale.

---

## Phase 5: US3 — La plataforma puede dejar fuera una versión vieja (P3)

**Goal**: cuando haya que exigir un mínimo, la cañería existe y la respuesta es
legible.

**Independent Test**: se fija un mínimo por encima de la versión instalada y se
comprueba qué ve la persona.

### Tests primero ⚠️

- [X] T032 [P] [US3] `apps/api/tests/`: **sin mínimo declarado, el latido no
      rechaza nada** — y ése es el estado del primer despliegue. El caso va
      primero a propósito: es el comportamiento por defecto y el que más fácil se
      rompe al añadir la puerta. _Requisitos: 4.4_
- [X] T033 [P] [US3] Con un mínimo declarado, una versión por debajo recibe
      **código y motivo legibles**, en el mismo idioma que `device_archived` y
      `pairing_required`, y no algo que parezca un fallo de red.
      _Requisitos: 4.1, 4.2_
- [X] T034 [P] [US3] **Avisar y bloquear son distintos**: una versión vieja pero
      admisible recibe aviso y **sigue funcionando**; sólo la que cae por debajo
      del mínimo se rechaza. _Requisitos: 4.6_

### Implementación

- [X] T035 [US3] La versión mínima admisible como configuración de plataforma,
      **ausente por defecto**, con su motivo y su fecha de entrada en vigor — la
      fecha es lo que hace comprobable el preaviso en vez de dejarlo en una
      intención. _Requisitos: 4.1, 4.5_
- [X] T036 [US3] La puerta en `POST /device/heartbeat`, que es lo único que corre
      solo y cada poco. El latido **ya recibe** `app_version` y **la ignora a
      propósito** (`T072`): esta tarea la lee para decidir y **sigue sin
      persistirla**. _Requisitos: 4.1, 4.2_
- [X] T037 [US3] La barra nombra el rechazo como un estado y ofrece actualizar,
      en vez de comportarse como si no hubiera red. _Requisitos: 4.3_
      **HECHO, y destapó dos huecos de lo que ya había escrito:**
      (a) **el latido no mandaba `app_version`**, así que la puerta de T036 no se
      habría disparado nunca — `is_blocked` deja pasar a quien no dice su
      versión; (b) tratar el rechazo como `BridgeRejected` **habría borrado la
      credencial**, o sea que exigir una versión mínima habría desemparejado a
      todo el mundo a la vez. Ahora es `AppUpdateRequired`, que para el puente y
      **no olvida nada**.
      El estado `version_no_admitida` obligó a **ampliar el contrato de la
      spec 002** (`contracts/desktop-bar.md`): un test comparaba la enumeración
      contra esa lista y se puso rojo, que es justo lo que debía pasar. Y el
      botón reutiliza `openInBrowser`, que ya está en el preload, en vez de
      añadir una séptima función a la única superficie con `preload`.
- [X] T038 [US3] Dejar escrito que el bloqueo se reserva a **contrato roto o
      seguridad**, y que no se usa para empujar mejoras. Es lo que separa este
      mecanismo de una palanca de marketing. _Requisitos: 4.7_

**Checkpoint**: las tres historias funcionan de forma independiente.

---

## Phase 6: Polish y documentación

- [X] T039 [P] `docs/desktop-workstation.md`: la spec viva gana la cadena, el
      canal, los estados nuevos y la puerta de versión mínima. **En el mismo
      commit** que el código que describe. _Requisitos: 6.3_
- [X] T040 [P] Escribir el procedimiento de **rotación y revocación** de la
      identidad de firma, y **probar la rotación una vez**. Incluye decir **quién
      puede revocar** —hoy Facelad, no Auphere— y qué les pasa a las
      instalaciones existentes si ocurre: caducar no rompe nada ya firmado,
      **revocar deja las aplicaciones sin arrancar**. _Requisitos: 5.4, 5.5_
- [ ] T041 Recorrer `quickstart.md` entero y dejar la salida cruda en
      `evidence/quickstart.txt`. _Requisitos: 1.4, 2.3, 3.1_
- [X] T042 `./scripts/verify.sh` **entero**, leyendo la cola en crudo — no un
      resumen propio. _Requisitos: 6.2_
- [X] T043 Invocar **`/cso`** sobre el cambio. No es opcional ni es mi criterio:
      el `CLAUDE.md` del workspace lo exige antes de declarar *done* cualquier
      cambio que toque «autenticación, manejo de secretos, tokens, claves API o
      variables de entorno», y esta spec introduce **seis secretos de
      producción, un rol de AWS nuevo y una superficie de confianza entera**.
      Es un audit de solo lectura: no toca código, produce un informe con
      severidades. **Un hallazgo 🔴 alto o crítico bloquea el ship** hasta
      mitigarlo o aceptar el riesgo por escrito. _Requisitos: —_
      **HECHO el 2026-09-14: 4 hallazgos, los 4 corregidos.** Informe en
      `.gstack/security-reports/`. El crítico era mío y el contraste que lo
      delató estaba en la propia cuenta: el rol de publicación aceptaba
      `repo:…:*` mientras el de despliegue lleva cuatro refs acotadas desde
      siempre. Se copió el patrón de OIDC sin copiar el alcance, justo en el rol
      que publica binarios. También: script injection por el input del disparo
      manual, un secreto interpolado en `run:`, y cuatro acciones sin pin. Y
      `.gstack/` no estaba en `.gitignore`.
- [ ] T045 Tras la primera publicación real, arreglar las dos cosas anotadas en
      [`docs/pendientes-tras-el-go-live.md`](../../docs/pendientes-tras-el-go-live.md)
      §2: **(a)** declarar `minimumSystemVersion: "13.0"` — Electron 44 exige
      macOS 13 y sin el campo el `.dmg` deja instalar en un Mac que luego no
      puede abrir la app; **(b)** el workflow sube `latest-mac.yml` por nombre
      exacto y `electron-builder` puede generar un índice por arquitectura, así
      que el glob pasa a `latest-mac*.yml` o la actualización queda rota para una
      de las dos. Ninguna impide instalar. Se dejaron para después de ver la
      cadena correr, a propósito. _Requisitos: 1.1, 2.1_
- [ ] T044 Entregar el mensaje de commit y **parar**. Los commits los ejecuta la
      persona. _Requisitos: —_

---

## Dependencies & Execution Order

### La dependencia que manda sobre todas

**T001 (el `.p12`) bloquea las Fases 3 y 4 enteras.** No es una tarea de código y
no se puede adelantar programando. Todo lo demás —el rescate, la infraestructura,
la puerta de versión mínima— puede avanzar sin ella.

### Entre fases

- **Setup (1)**: sin dependencias. T002–T004 no esperan a T001.
- **Foundational (2)**: sin dependencias de la 1. **Bloquea publicar** (T028),
  no construir.
- **Puertas (2b)**: en paralelo con las historias; `/speckit-analyze` las exige.
- **US1 (3)**: depende de **T001** y de T002. **Es el MVP.**
- **US2 (4)**: depende de US1 (no hay nada que actualizar sin algo instalado) y
  de la Fase 2 (no hay dónde publicar).
- **US3 (5)**: **no depende de ninguna de las otras dos.** Es API y barra, y se
  puede hacer en paralelo con toda la cadena si hay manos.
- **Polish (6)**: T039 y T040 van **en el mismo commit** que lo que describen.

### Paralelizable

- T002 ‖ T004 · T005 ‖ T006 · T014 ‖ T015 · T022–T025 · T032–T034 · T039 ‖ T040.
- **US3 entera en paralelo con US1 y US2.**
- **T007 y T008 no son paralelos**: el rol de T008 apunta a recursos de T007.

### Lo que no se puede paralelizar aunque lo parezca

**T021 y T031 son manuales y secuenciales**, y van al final de su fase a
propósito: son los únicos que prueban lo que de verdad se prometió. Un Mac limpio
sólo es limpio una vez — después de instalar, ya no sirve para probar la primera
instalación.

---

## Implementation Strategy

### MVP (Setup + Fase 2 + US1)

1. **T001 primero, y en paralelo T002–T004.**
2. Fase 2 completa: hay dónde publicar y está probado que sólo la cadena escribe.
3. US1 completa, **incluido T021**: el Mac limpio.
4. **PARAR Y VALIDAR**: con esto ya hay beta. Un partner puede instalar.

### Entrega incremental

1. Setup + Fase 2 → hay canal, no hay nada dentro.
2. US1 → **hay algo que instalar**. Se puede empezar la beta.
3. US2 → se puede arreglar lo que salga mal sin que nadie reinstale.
4. US3 → se puede dejar fuera una versión vieja cuando haga falta.

### Despliegue

El **orden secreto → Terraform → despliegue no se negocia**. Y el plan de
Terraform se enseña y se lee entero antes de aplicar: si aparece algo que nadie
pidió, se para.

---

## Notes

- `[P]` = ficheros distintos, sin dependencias.
- Los tests se ven **fallar** antes de implementar (§VII).
- **Lo que no se puede automatizar se hace a mano y se deja por escrito**, no se
  finge con un test que comprueba otra cosa.
- Los commits los ejecuta la persona: el agente entrega el mensaje y para.
- Producción tiene 3 clientes reales con tráfico.
