# Recorrido del quickstart — spec 031 (T111)

Recorrido el 2026-10-20 sobre la rama `031-auphere-customers-movil`, sin
confirmar. ☑ hecho y en verde · ◐ hecho en parte · ☐ pendiente (con motivo).

## 1. Lo que corre la tubería

| Paso | Estado |
|---|---|
| `./scripts/verify.sh lint` (ruff y `mypy --strict` en api, worker, channels y mcp) | ☑ |
| `./scripts/verify.sh py`: worker 459, channels 61, mcp 123 en verde; api, ver «Python» abajo | ◐ |
| `./scripts/verify.sh mobile` (lockfile, `tsc`, ESLint, Jest con 106 pruebas, generados y contrato OpenAPI) | ☑ |
| Consola: `tsc`, ESLint, 804 pruebas de Vitest, sin token de admin | ☑ |
| Panel: `tsc`, ESLint (3 avisos previos, ninguno de esta spec), 139 pruebas | ☑ |
| `next build` de la consola (con `/account/phones` y `/app-auth`) | ☑ |
| `expo export` para Android e iOS (bundles Hermes de 4,7–4,8 MB) | ☑ |
| Build nativo de Android (`assembleDebug`, arm64) e instalación en el emulador | ☑ |
| `expo-doctor` (20/20, tras añadir `expo-font`) | ☑ |

El `--check` de los generadores demostró su valor en el propio recorrido: un
cambio de texto en la consola dejó `lite.gen.ts` viejo y el paso `mobile` lo
paró hasta regenerarlo.

### Python

- API entera: **5354 en verde**; 390 `skip` y 4 `xfail` previos. Fallaron 4 de
  `tests/unit/test_config.py` porque el arranque de producción de prueba no
  definía el secreto nuevo: corregido (y una prueba más que comprueba que
  producción se niega a arrancar sin él), 15/15.
- worker 459, channels 61, mcp 123, en verde.
- Encontrado de paso, **previo y ajeno a la spec**:
  `tests/integration/test_local_dispatch.py::test_the_same_work_is_never_handed_out_twice`
  espera 0,2 s fijos a que aparezca el trabajo; con el equipo cargado falla y
  después `await running` se queda esperando, lo que cuelga la suite entera.
  Solo, pasa (12/12).

## 2. Los barridos de aislamiento

☑ `uv run pytest tests/isolation/`: **1989 en verde** (tras el pase vivo), 1
`skip` previo y ajeno (`test_37_customer_axis_contract`). Incluye los seis de
la spec y el barrido de los seis disparadores de revocación
(`test_phone_revocation.py`), que ahora comprueba también la línea en vivo.

## 3. Entrar y quedarse

- ☑ La API: canje, renovación con rotación y reutilización, versión mínima,
  cierres (`test_phone_enrollment.py`, `test_client_auth_phone.py`,
  `test_phone_revocation_triggers.py`).
- ☑ **Enmienda de R1 (2026-10-20): la entrada es de la app.** API:
  `test_app_sign_in_password.py`, `test_app_sign_in_google.py` (Google
  simulado: la regla del correo, el `sub` vinculado con otro correo, sin
  verificar, partner, sin acceso, cancelar, `state` reutilizado o falso),
  `test_app_password_reset.py` y la lista cerrada de rutas públicas
  (`tests/isolation/test_app_public_routes.py`). La consola ya no tiene
  `/app-auth`.
- ☑ La app: los dos métodos, cada error con su texto, el autocompletado, mostrar
  la contraseña, Google solo si la API lo ofrece, el olvido (Jest).
- ☑ En el emulador, contra la pila local: contraseña mala (mensaje genérico),
  contraseña buena, la pantalla de avisos una vez por entrada (R10.1) y el
  olvido de contraseña (202, mismo mensaje). **Maestro** `e2e/sign-in.yaml` en
  verde de punta a punta. Google necesita el cliente OAuth de staging (runbook
  en `docs/app-movil.md`).
- ☑ Cerrar el teléfono desde el panel (R7.4): el panel lo marca «Cerrado · Lo
  cerró Auphere · operador», y la app vuelve a «Entrar» diciendo «Auphere cerró
  la sesión de este teléfono» unos segundos después
  ([captura](capturas/android-cerrado-por-auphere-claro.jpg),
  [panel](capturas/admin-telefonos.jpg)).
- ☑ Un enlace `auphere-customers://inbox/<id>` con la app cerrada abre esa
  conversación, y «atrás» lleva al primer módulo, no fuera de la app.

## 4. Inicio y Consumo

- ☑ Cifras idénticas con la credencial del teléfono y con la BFF, en seis rutas
  (`test_lite_phone_figures_match_web.py`).
- ☑ Los cinco estados y la ausencia de compra o recarga (Jest).
- ☑ En vivo: Inicio y Consumo con los datos sembrados; con la app delante, un
  escalado nuevo en el servidor cambia «Necesita tu atención», «Esperando a una
  persona» y la insignia de la Bandeja a la vez, sin tocar nada.

## 5. Atender

- ☑ Idempotencia en la API (`test_lite_send_idempotency.py`) y en la app (la
  misma clave al reintentar, el texto conservado).
- ☑ Conflicto 412, ventana de 24 h, adjuntos validados, menú con «Devolver a
  {agente}» primero (Jest).
- ☑ Tiempo real con la credencial del teléfono (`test_lite_stream_phone.py`).
- ☑ En vivo: tomar el control (la tarjeta da paso al cuadro con el cursor
  dentro), enviar (201, una fila `pending` del miembro; sin worker local queda
  «Enviando…», igual que en la web), devolver al agente, buscar sin acentos,
  filtros, etiqueta y nota interna desde la hoja del contacto.
- ☐ `e2e/send-flaky.yaml` (Maestro): escrito, sin ejecutar.

## 6. Avisos

- ☑ Outbox en la transacción del hecho, reparto, textos mínimos, reintentos y
  destinos dados de baja (API y worker).
- ☑ Canales, categorías, registro del destino, supresión de la conversación
  abierta y apertura al tocar (Jest).
- ☐ Un aviso real de APNs y de FCM: faltan la clave de Apple y Firebase (T004).

## 7. Accesibilidad, tema, idioma y movimiento

- ☑ Contraste de los tokens generados y lo automático:
  [a11y.md](a11y.md) y [motion.md](motion.md).
- ☐ VoiceOver, TalkBack, capturas y vídeos: en dispositivo.

## 8. Piloto

☐ Tras dos semanas de pruebas cerradas (T112).

## Lo que el pase vivo encontró (corregido, con prueba)

- **Abrir una conversación entraba en un bucle** («Maximum update depth»): la
  conversación ocultaba la barra de pestañas desde dentro de su pestaña, y
  expo-router 58 volvía a disparar el foco. Ahora la conversación y su hoja de
  contacto se abren **por encima de las pestañas** (`app/conversacion/[id]`),
  como en cualquier app de mensajes; en iOS, además, la barra flotante ya no
  tapa el cuadro de escribir.
- **Inicio se quedaba viejo** tras atender: la insignia decía 0 y la tarjeta
  seguía diciendo 1. Lo que cambia la Bandeja ahora refresca también Inicio.
- **La línea en vivo del teléfono se renueva cada 5 minutos**: la sesión se
  comprueba al abrir la línea, así que renovarla es lo que mantiene el plazo de
  R7.2 para lo que se cierre con la app delante; la reconexión de un teléfono
  cerrado se rechaza (barrido de aislamiento ampliado a la línea). La de la web
  no cambia. Y la app, si la línea le devuelve 403, cierra la sesión con su
  motivo en vez de reintentar.
- Al 200 % de texto, iconos recortados y palabras partidas (ver
  [a11y.md](a11y.md)).

## Bloqueos de esta sesión

- **Disco**: el Mac llegó a 177 MB libres a mitad del build de Android. Se
  borraron solo salidas de compilación creadas en esta sesión; quedaron 8 GB.
- **Xcode 26.0.1**: el SDK 58 pide 26.4 o posterior para compilar iOS.
- ~~**Base de desarrollo local en la migración 0128**~~: migrada a la cabeza
  (copia previa fuera del repo), y con ella el pase vivo de arriba.
