# Auphere Customers — spec viva

> Qué existe hoy de la app del teléfono para las personas de cliente: el código
> en `apps/mobile`, lo que la API añade para ella en `apps/api` y el reparto de
> avisos en `apps/worker`. Nace con la spec
> [031](../specs/031-auphere-customers-movil/spec.md); su porqué está en
> `kb/Auphere/nexus/decisions/ADR-042-la-consola-lite-en-el-telefono.md`. Se
> actualiza en el mismo commit que cambia lo que describe (constitución §IX).

## Qué es

La Consola Lite ([consola-lite.md](consola-lite.md)) en iOS y Android, para la
misma persona y con la misma cuenta. Cuatro módulos —Inicio (el Panel),
Bandeja, Reservas (spec [044](../specs/044-la-app-con-reservas/spec.md)) y
Consumo—, las pestañas que el cliente tenga y en el orden de la web, y avisos
normales de lo que necesita a una persona. Desde la 1.2.0 (spec
[047](../specs/047-la-fabrica-de-agentes/spec.md), requisito 50), además:
**Agentes** (el estado de cada uno, sus números, pausar y reanudar),
**Negocio** (horario y fechas especiales, servicios, sedes) y «Corregir esta
respuesta» en la conversación; ver [más abajo](#agentes-negocio-y-correcciones-spec-047). Convive con la consola web, que no
cambia: la app no tiene ninguna regla de negocio propia, lee las mismas rutas
`/console/lite/*`.

Lo que **no** hace: comprar o recargar saldo (decisión del owner, 2026-10-22),
mover o editar una reserva (044), responder desde el aviso, plantillas de WhatsApp fuera de la ventana de 24 h, deslizar
para actuar sobre una conversación (todo está en su menú) y el enlace universal
para entrar (solo esquema propio). Tampoco crear, archivar o publicar agentes,
cambiar sus instrucciones o su calidad, conectar canales o integraciones ni
tocar la bolsa (047, 50.3): la app lo dice, no lo ofrece.

## Arquitectura

- **Expo SDK 58** (React Native 0.88, React 19.3), sin código nativo propio:
  todo son módulos de Expo y de Software Mansion. Licencias en
  [research.md §Licencias](../specs/031-auphere-customers-movil/research.md#licencias-de-lo-que-entra-constitución-viii)
  y, para `expo-glass-effect` (~58.0.4, MIT, el vidrio de iOS 26), en la
  [research de la spec 042](../specs/042-liquid-glass-en-la-app/research.md#licencias-de-lo-que-entra-constitución-viii).
- **Su propio workspace de pnpm** (`apps/mobile/pnpm-workspace.yaml`, su
  lockfile y `pnpm@10.15.0`): Expo fija React 19.3 y la consola 19.2, y dos
  Reacts en un árbol rompen en ejecución. Nunca se añade `apps/mobile` al
  workspace raíz ni se usa `workspace:*` desde la app.
  Los parches a dependencias publicadas viven en `apps/mobile/patches/` y se
  declaran, con su porqué, en `pnpm-workspace.yaml`. Hoy hay uno:
  `expo-symbols`, que en Android dejaba al texto del sistema agrandar el icono
  hasta recortarlo. Se retira cuando una versión publicada lo arregle.
- **Rutas** (`src/app`, expo-router):
  - `_layout.tsx` monta los proveedores y decide qué pantallas existen según la
    sesión con `Stack.Protected`: la de actualizar (R13), la app, o la entrada.
    Cambiar de estado lleva a `index.tsx`, que manda a cada uno a su sitio.
  - `(app)/_layout.tsx` son las **pestañas nativas** (`expo-router/native-tabs`)
    construidas con `GET /console/lite/me` → `nav`. Se declaran los tres
    módulos que la app sabe pintar y los que el cliente no tiene van `hidden`
    (las pestañas nativas no se pueden añadir en caliente). Si `nav` cambia, la
    barra se vuelve a montar a propósito (`key`) y la persona cae en el primer
    módulo. Con un módulo no hay barra. Un módulo desconocido se ignora.
    Las etiquetas de la barra van a 10 pt en iOS, como las de Apple
    (`tabLabelStyle`, spec 044 D13): dejadas al tamaño del texto del teléfono
    crecían y se recortaban (042 H25).
    La barra **no se encoge** al desplazar (`TAB_BAR_MINIMIZE = "never"`,
    spec 042, H22): encogida, iOS 26 esconde la insignia de la Bandeja.
  - Cada pestaña es una pila nativa (título grande en iOS, cabecera propia en
    Android) con Ajustes a la derecha. En iOS 26 la cabecera es la del sistema,
    **sin fondo propio**: pintarle uno apaga el vidrio y deja el título grande
    invisible (spec 042, D1 y H14); antes de iOS 26 y en Android lleva el fondo
    de siempre (`useHeaderOptions`, decidido con `isLiquidGlassAvailable()`).
    El botón de Ajustes es un elemento de barra nativo en iOS
    (`SettingsToolbar`, `Stack.Toolbar`) y un `headerRight` en Android. La
    Bandeja lleva la búsqueda nativa en la cabecera, con la colocación que
    elija el sistema; en Android, el icono, el texto y la pista de la búsqueda
    salen del tema (`headerIconColor`, `textColor`, `hintTextColor`): sin eso
    Android los pinta con sus grises y en oscuro la lupa no se ve (H23). En iOS el tamaño del título grande sale de la tabla de
    Dynamic Type de Apple (`headerSize`, en `type.ts`): en cuanto se le pone
    un color, react-native-screens lo pinta con una fuente fija y dejaría de
    crecer con el texto del teléfono (H8). El título normal de la barra se
    queda fijo, como el de Apple: la barra no crece. En Android sí crece
    (los títulos de barra van en sp); el de la conversación (`ConversationTitle`)
    tiene un tope de 1,3, lo que cabe en la barra de 64 dp con sus dos líneas
    (H24). Con «Aumentar contraste» iOS 26
    vuelve opacos los botones de vidrio de la barra siguiendo el esquema
    (disco claro en claro, oscuro en oscuro) y el tinte `primaryText` sigue
    leyéndose en los dos (spec 042, `evidence/a11y.md`).
  - **Los ajustes de apariencia se leen en vivo** (`useSystemAppearance`):
    «Reducir transparencia», «Aumentar contraste» (o el contraste alto de
    Android) y «Reducir movimiento». `FloatingSurface` es la única superficie
    de vidrio propia (`expo-glass-effect`, MIT): flota en iOS 26 y, sin vidrio
    o con «Reducir transparencia», se presenta anclada y opaca, como el pie de
    la 031. Nunca lleva `opacity`; nunca va vidrio dentro de vidrio.
  - La **conversación** (`conversacion/[id]`) y su contacto (una hoja,
    `formSheet`) se abren **por encima de las pestañas**, en la pila raíz,
    como en cualquier app de mensajes: el cuadro de escribir es dueño del
    borde de abajo. El menú de la conversación es el de la barra del sistema
    en iOS (`ConversationToolbar`, `Stack.Toolbar.Menu`, con «Devolver al
    agente» la primera) y la hoja de acciones de siempre en Android; la lista
    de acciones es una sola (`conversationMenu`). El hilo es un `FlatList`
    invertido envuelto en el `ScrollViewMarker` de react-native-screens
    (`ContentScroll`; en Android, una vista normal) con los efectos de borde
    de iOS 26 ocultos y, con la cabecera de vidrio, empieza bajo ella: con la
    lista invertida, el efecto del sistema atenuaba el hilo entero (spec 042,
    H20, research D4). El relleno que deja sitio al pie es un separador en
    estado de React animado con `LayoutAnimation`, nunca una propiedad de
    layout animada por Reanimated dentro de la lista. No ocultar la barra desde
    dentro de una pestaña: con expo-router 58 eso entra en un bucle de foco
    («Maximum update depth»). La pila raíz ancla `index`, así que un enlace
    abierto con la app cerrada deja algo debajo y «atrás» no saca de la app.
  - **Las dos hojas** salen de `useSheetOptions` (spec 042, R1.7): el contacto
    y, en iOS, también Ajustes son `formSheet` con paradas en `[0.6, 1]` y
    asa; en Android el contacto es una hoja inferior con las esquinas de la
    app y Ajustes, una pantalla. Con Liquid Glass el contenedor de la hoja no
    pinta fondo (se ve el material del sistema y su cabecera es transparente,
    así que el `ScrollView` lleva `contentInsetAdjustmentBehavior="automatic"`);
    sin vidrio, el fondo de siempre. `glassAvailable()` (`src/theme/glass.ts`)
    es la única pregunta de «¿hay vidrio?»; lo que la persona pidió en
    accesibilidad se lee aparte, en vivo.
  - **Formas y tacto** (spec 042, R7, D12): botones y chips en cápsula
    (`radius.full`); tarjetas y grupos con `CARD_RADIUS` y lo que va dentro
    con esquinas concéntricas (`concentric`). La pulsación es la de cada
    plataforma: en iOS el control se encoge a 0,97 en `durations.fast` y su
    fondo pasa al tono de pulsación; en Android, la ondulación de Material.
    Nunca una bajada de opacidad: sobre vidrio un control translúcido deja de
    leerse como control. `disabled` baja el contraste del contenido y apaga el
    relleno; `busy` conserva tamaño y tonos. La tipografía (`src/theme/type.ts`)
    son los estilos de texto del sistema en iOS (cuerpo 17/22, título 22,
    título grande 34, cifras 28 tabulares) y los tokens de la consola en
    Android; sin `letterSpacing`. En iOS cada estilo deja de crecer donde lo
    hace la tabla de Apple (`maxScale`, como `maxFontSizeMultiplier`): con el
    texto al máximo un título de 22 pt escalado linealmente pasaría de los 60
    pt del título grande.
- **Datos**: `openapi-fetch` tipado con `src/api/schema.gen.ts` y React Query
  en memoria (nada de los clientes finales en disco). Al volver al primer plano
  se relee lo visible; sin red se lee lo último marcado como no actualizado y
  no se ofrece nada que escriba. Lo que cambia la Bandeja se invalida junto
  (`invalidateInbox`: listas, recuentos e Inicio), porque «Necesita tu
  atención» es el mismo número que la insignia. Consumo lee primero la serie
  de 90 días, que contiene a las de 7 y 30, y solo ofrece elegir periodo
  cuando hay algo que pintar (spec 042, R9.2).
- **Tiempo real**: SSE propia sobre `expo/fetch` y `eventsource-parser`, solo
  en primer plano. Los eventos dicen qué cambió y la app lo relee. «Reconectando…»
  aparece tras 3 s sin línea; al recuperarla se relee la Bandeja entera (la API
  no numera eventos, así que no hay `Last-Event-ID`). La API corta la línea de
  un teléfono cada 5 minutos para que la reconexión vuelva a pasar por la
  puerta (R7.2); la app reconecta en 1 s, sin que se vea. Un 403 en la línea
  cierra la sesión con su motivo, como en cualquier otra ruta, y no se
  reintenta.
- **Movimiento** (D24): duraciones de los tokens, ninguna por encima de 300 ms,
  sin rebotes y una sola coreografía: «Tomar el control» (sale la tarjeta,
  entra el cuadro, vibración de éxito y el cursor en el cuadro). Con
  «Reducir movimiento» todo pasa a fundidos, y el ajuste se sigue en vivo, no
  solo al arrancar: a Reanimated se le dice `ReduceMotion.Never` siempre,
  porque el fundido *es* la alternativa y `Always` lo saltaría (spec 042,
  D5). Lo único que va en bucle es el punto de «Reconectando», que se queda
  quieto con movimiento reducido.

## Entrar y quedarse dentro

Contrato completo en
[phone-auth.md](../specs/031-auphere-customers-movil/contracts/phone-auth.md).

**La app tiene su propia entrada** (R1 enmendado el 2026-10-20, research D2b):
correo y contraseña, o Google. **Nada pasa por la consola de partners**; los
partners tendrán su propia app. Todo vive en `api/app_public.py`.

1. **Con contraseña:** la pantalla «Entrar» (`src/app/sign-in.tsx`) manda correo
   y contraseña a `POST /app/sign-in/password`. La API los comprueba con
   `console_identity.authenticate` (el hash, el bloqueo tras diez fallos y la
   regla de la web) y un límite por correo. La contraseña no se guarda; los
   campos llevan el autocompletado del sistema. Errores en la raíz:
   `invalid_credentials` (igual para correo desconocido, contraseña mala o
   cuenta bloqueada), `not_a_client`, `no_access`, `rate_limited`.
2. **Con Google:** la app genera PKCE S256 y un `state`, y abre en la **ventana
   segura del sistema** `https://<api>/app/sign-in/google?state&code_challenge`.
   La API hace el flujo web de Google (su propio PKCE, `select_account`), y a
   la vuelta (`/app/sign-in/google/callback`) exige que el correo verificado de
   Google sea **el de la membresía** de la persona en el cliente, aunque el
   `sub` ya esté vinculado. Si vale, emite un código de un uso
   (`session_codes`, `purpose=client_phone`) atado al reto de la app y vuelve a
   `auphere-customers://auth/callback?code&state`; si no, vuelve con `error`
   (`google_account_mismatch`, `email_not_verified`, `not_a_client`,
   `no_access`, `cancelled`, `failed`). La app canjea en
   `POST /app/sign-in/google`. Sin Google configurado en la API,
   `GET /app/config` dice `sign_in.google: false` y la app no enseña el botón.
3. «¿Olvidaste tu contraseña?» llama a `POST /app/password-reset`, el mismo
   servicio que la web (misma respuesta exista o no la cuenta). El enlace del
   correo abre la página de la web para crear la contraseña.
4. Las dos puertas acaban igual: la API crea el teléfono y la app guarda **dos credenciales**
   en el almacén seguro (`keychainService: "auphere-customers"`,
   `WHEN_UNLOCKED_THIS_DEVICE_ONLY`): el acceso (JWT HS256 de 1 h con
   `svc: "customers_phone"`, firmado con `customers_app_token_secret`) y la
   renovación (opaca, rota en cada uso, vale 60 s la anterior, caduca a los 90
   días sin uso).
5. Cada petición lleva `Authorization`, `X-App-Platform` y `X-App-Version`. La
   API la resuelve con `require_client_principal`, que por el algoritmo del
   token distingue la rama del teléfono y acaba en **el mismo**
   `ClientPrincipal` que la web: ninguna ruta lite cambió su autorización.
   Cada petición vuelve a leer la fila del teléfono, así que un teléfono
   cerrado deja de leer en la siguiente.
6. Un 401 renueva **una sola vez** aunque haya varias peticiones a la vez
   (`src/api/client.ts`). Un `phone_closed` en cualquier respuesta vacía el
   almacén y vuelve a «Entrar» diciendo por qué; un `app_update_required`
   lleva a la pantalla de actualizar.

Una reinstalación no despierta con la sesión de antes: el primer arranque, sin
el marcador de `Paths.document`, vacía el almacén y crea un `install_id` nuevo.

**Cerrar un teléfono**: la persona desde la app (`DELETE /phones/current`) o
desde la consola web («Tus teléfonos», `/account/phones`); Auphere desde el
admin (Acceso → persona → Teléfonos). Además, cierran todos los teléfonos de
una persona o un cliente: quitar a la persona, apagar el acceso del cliente y
restablecer la contraseña. Barrido en
`tests/isolation/test_phone_revocation.py`.

**Versión mínima**: `customers_app_min_version_{ios,android}` y su razón en la
configuración de la API, servidas en `GET /app/config`. La app la consulta al
arrancar y al volver al primer plano; subirla no exige publicar nada.

## El camino de los avisos

Contrato en [push.md](../specs/031-auphere-customers-movil/contracts/push.md).

1. **El hecho escribe un evento** en `client_push_events`, en su misma
   transacción: un escalado (`inbox_lifecycle.mark_waiting`), un mensaje en
   una conversación que atiende una persona (despachador del worker) o un aviso
   de saldo (`wallet_alerts`). Si el hecho se deshace, no hay aviso.
2. **El worker** (`push-dispatcher`, familia egress) despierta con
   `pg_notify('nexus_push')` y barre cada 30 s. `push_fanout.claim` calcula los
   destinatarios **al repartir** (teléfono activo, persona con acceso, tipo
   encendido, destino registrado), comprueba que el hecho sigue siendo verdad y
   compone el título y el texto en el idioma del teléfono. «Persona con
   acceso» es **la misma regla** que cada petición del teléfono
   (`open_client` en `core/client_auth.py`): un cliente archivado, un partner
   suspendido o un acceso apagado no reciben ni lo que estaba pendiente.
3. **Lo mínimo viaja**: el nombre del contacto (o «Un contacto» si su nombre
   es un número), el motivo del agente o el principio del mensaje recortado a
   100 caracteres con los teléfonos tapados, y el estado del saldo. Nunca
   números, mensajes completos, archivos ni notas
   (`tests/isolation/test_push_payload_no_customer_content.py`).
4. **Se envía** a APNs (HTTP/2, token ES256) o FCM (HTTP v1, aserción RS256),
   sin relevo de terceros. Lo transitorio se reintenta (15 s·2^(n-1), cinco
   veces); un destino dado de baja se quita del teléfono.
5. **En el teléfono**: canales de Android `waiting_v1`, `messages_v1`,
   `balance_v1` (y `reservations_v1` y `agents_v1`, de las specs 044 y 047), todos privados en la pantalla bloqueada; categorías de iOS sin
   acciones y con texto neutro para las previsualizaciones ocultas; «espera a
   una persona» va como `time-sensitive`. El aviso de la conversación abierta no
   se muestra. Tocarlo abre la conversación, Consumo, una reserva o un agente
   (spec 047), con la app abierta o cerrada. La placa del icono es lo que espera a una persona.

El permiso se pide después de una pantalla propia que explica los tres tipos y
deja decir «Ahora no»; Ajustes tiene un interruptor por tipo para ese teléfono
y, con el permiso negado, lo dice y lleva a los ajustes del teléfono.

## Lo compartido entra generado

| Generador | De | A | `--check` |
|---|---|---|---|
| `apps/api/scripts/export_openapi.py` | la API (solo `/console/lite` y `/app`) | `apps/mobile/src/api/openapi.json` | tubería `test-api` |
| `scripts/gen-schema.mts` | `openapi.json` | `src/api/schema.gen.ts` | `pnpm gen:check` |
| `scripts/gen-tokens.mts` | `packages/ui/src/styles/tokens.css` (OKLCH) | `src/theme/tokens.gen.ts` (hex sRGB, claro y oscuro) | `pnpm gen:check` |
| `scripts/gen-i18n.mts` | `apps/console/src/i18n` (prefijos `inbox.`, `lite.`, `ui.`, los del Panel y, desde la 047, los estados del agente y del canal, la pausa y las secciones de Negocio: `clients.v2.agent.`, `clients.v2.pause.`, `builder.channel.state.`, `builder.life.pause.`, `business.{hours,special,services,locations,history,prov,section}.`, `panel.bag.*`) | `src/i18n/lite.gen.ts` | `pnpm gen:check` |

Las palabras propias de la app (pestañas, entrar, Ajustes, avisos) están en
`src/i18n/app.{es,en}.ts`. Una regla de ESLint prohíbe escribir un hex en la
app: el color sale de `useTheme().colors`. Los iconos son de cada plataforma
(SF Symbols en iOS, Material Symbols en Android) y sus nombres se comprueban al
compilar. El icono y la marca salen del `BrandMark` de `@nexus/ui`.

## Verificar

```bash
./scripts/verify.sh mobile   # instalación con lockfile, tsc, eslint, jest, generados y contrato OpenAPI
```

La tubería tiene el trabajo `test-mobile` (lo mismo con `pnpm verify`) y el
paso del contrato OpenAPI en `test-api`. Lo que solo se ve en un teléfono —el
aviso real, la pantalla bloqueada, VoiceOver y TalkBack— tiene su lista en
`specs/031-auphere-customers-movil/evidence/`.

## Builds, tiendas y actualizaciones

- **Perfiles** (`apps/mobile/eas.json`): `development` (cliente de desarrollo,
  `com.auphere.customers.dev`, contra la pila local), `preview` (instalación
  interna contra staging), `staging` (build de tienda contra staging, para
  TestFlight y las pruebas internas de Play) y `production`. Solo
  `development` cambia el identificador; los demás son la misma app. Cada uno
  tiene su canal de `expo-updates` y sus `EXPO_PUBLIC_API_URL` y
  `EXPO_PUBLIC_CONSOLE_URL`. Fuera de producción, Ajustes enseña el entorno
  junto a la versión («Versión 1.0.0 · staging»).
- **En local**: `pnpm --dir apps/mobile android` o `ios` (necesita Xcode 26.4
  o posterior para el SDK 58). Sin variables, un build de desarrollo habla con
  la máquina donde se compiló (`10.0.2.2` en el emulador de Android).
- **El simulador de iOS sin compilar en local** (spec 042, D16): el perfil
  `development-simulator` es el de desarrollo con `ios.simulator: true`. Se
  compila en la nube con la imagen del SDK 58 (Xcode 27, que trae Liquid
  Glass) y el `.app` se instala en el simulador local con
  `xcrun simctl install booted <ruta>`. Es la forma de ver iOS 26 cuando la
  máquina no puede compilar para iOS. El simulador de referencia es «13 26»
  (iPhone 13, iOS 26.0.1); en Android, la imagen del Pixel 9 (API 36) con
  8 GB de datos (el build de desarrollo no cabe en los 6 GB por defecto). En
  un build de desarrollo, apagar el botón
  flotante del dev client (menú → «Tools button») antes de capturar, porque
  tapa el botón de Ajustes.
- **En la nube**: el proyecto de EAS `@lmatos/auphere-customers` (creado con
  `eas init` el 2026-10-20). Su ID y su dueño están fijados en
  `app.config.ts` porque no son secretos; `EAS_PROJECT_ID` y `EAS_OWNER` los
  sustituyen si el proyecto cambia de cuenta. Firebase entra como variable de
  archivo de EAS (`GOOGLE_SERVICES_JSON`). La firma de iOS es del equipo de
  Apple que se elija en el primer build, no de la cuenta de Expo.
- **Actualizaciones por aire** (D19): **solo arreglos**. `runtimeVersion`
  sigue la versión de la app, así que algo que cambie lo nativo exige versión
  nueva en las tiendas. Nunca se publica por aire algo que cambie qué datos se
  piden o se muestran.

## Probar en staging con TestFlight y Play

Lo que hace falta, en orden, para que alguien pruebe la app contra staging.
Ningún valor secreto va en este repositorio: los secretos se crean en AWS con
`./infra/scripts/add_app_secret_keys.sh`, que no imprime valores.

**1. Antes de fusionar la spec 031 en `develop`** (dueño):

- Crear `NEXUS_CUSTOMERS_APP_TOKEN_SECRET` (por ejemplo `openssl rand -base64 48`)
  en el secreto de **staging y de prod**:
  `AWS_PROFILE=nexus ./infra/scripts/add_app_secret_keys.sh staging NEXUS_CUSTOMERS_APP_TOKEN_SECRET`
  (y lo mismo con `prod`). Luego `terraform apply` del workspace `staging`
  (`infra/terraform/20-services`, con `-var-file=staging.tfvars`). La tubería
  **no aplica Terraform**: solo reinicia los servicios con la imagen nueva.
- En el cliente OAuth de Google de staging (el de la consola), añadir el URI de
  redirección autorizado `https://api.staging.auphere.com/app/sign-in/google/callback`.
  Sin él, «Continuar con Google» vuelve con error; correo y contraseña
  funcionan igual.
- En Cloudflare, una regla de ritmo por IP para `/app/sign-in/*` y
  `/app/password-reset` de `api.staging.auphere.com`, y la misma en
  `api.auphere.com` **antes de abrir la app a más personas**. La API limita
  por correo y bloquea la cuenta tras diez fallos; el límite por IP es del
  borde.

**2. Fusionar en `develop`.** Con `ci` en verde, `deploy-staging` corre las
migraciones 0165–0169 y reinicia los servicios (el worker ya lleva
`push-dispatcher`). Comprobación: `GET https://api.staging.auphere.com/app/config`
devuelve `sign_in`.

**3. Una persona de prueba** (dueño, en el admin de staging): un cliente con
WhatsApp conectado a un número de prueba → Acceso → encender la Consola lite
con sus módulos → invitar a la persona con un correo que controles. Acepta la
invitación desde el correo (`console.staging.auphere.com`) y crea su
contraseña. Con esa cuenta se entra en la app.

**4. La app** (dueño):

- El proyecto de EAS ya existe (`@lmatos/auphere-customers`) y está en
  `app.config.ts`: no hay variables que definir.
- **iOS:** la ficha de App Store Connect con `com.auphere.customers` (equipo de
  FACELAD; EAS crea el App ID y los certificados en el primer build; su id en
  App Store Connect, `6825002452`, está en el `submit` de `eas.json`). Después
  `eas build -p ios --profile staging --auto-submit`, que lo sube a TestFlight
  al terminar. Los probadores internos de TestFlight la tienen en cuanto Apple
  procesa el build; los externos pasan antes la revisión beta.
- **Android:** la app en Play Console (`com.auphere.customers`) y, en Firebase,
  una app Android con ese paquete: su `google-services.json` va como variable
  de archivo de EAS `GOOGLE_SERVICES_JSON`. Después
  `eas build -p android --profile staging`. **El primer AAB se sube a mano** a
  la pista de pruebas internas en Play Console; los siguientes, con
  `eas submit -p android --profile staging` y la cuenta de servicio de Play en
  EAS.

**5. Avisos push** (opcional para la primera prueba; sin ellos la app funciona
y el worker lo registra):

- Una clave APNs (`.p8`) del equipo de FACELAD y la cuenta de servicio de
  Firebase. Crear en el secreto de staging `NEXUS_APNS_KEY_ID`,
  `NEXUS_APNS_TEAM_ID`, `NEXUS_APNS_KEY_PEM`, `NEXUS_FCM_PROJECT_ID` y
  `NEXUS_FCM_SERVICE_ACCOUNT_JSON`; descomentar `push_secret_keys` en
  `staging.tfvars` y `terraform apply` de staging. Los builds de TestFlight y
  de tienda usan APNs de producción; la app se lo dice a la API sola.

**6. Qué probar:** el recorrido de
[quickstart.md](../specs/031-auphere-customers-movil/quickstart.md):

- entrar con contraseña y con Google (también con otra cuenta de Google, que
  tiene que rechazarse);
- «¿Olvidaste tu contraseña?» (llega el correo y el enlace abre la web);
- Inicio y Consumo contra la consola web;
- tomar el control y contestar por WhatsApp al número de prueba;
- un aviso con la app cerrada;
- cerrar el teléfono desde «Tus teléfonos» y desde el admin;
- oscuro y texto grande.

**Antes de producción:** lo mismo con `prod` (el secreto, el
`terraform apply` y el URI de Google) **antes** de fusionar en `main`. Sin
`NEXUS_CUSTOMERS_APP_TOKEN_SECRET`, la API de producción **no arranca**. Y
decidir lo de «Iniciar sesión con Apple» (guía 4.8, en la spec).

## Migrar de FACELAD a Auphere

Cuando la app pase a la cuenta de desarrollador de Auphere:

- cambian el Team ID, el App ID y la clave de APNs (`apns_key_id`,
  `apns_team_id`, `apns_key_pem` en la API) y la cuenta de Expo
  (`EAS_OWNER`, `EAS_PROJECT_ID`);
- el llavero de iOS queda ligado al Team anterior: **todas las personas vuelven
  a entrar una vez**. Al entrar, el teléfono conserva su `install_id` y su fila
  anterior se cierra (`signed_out`); la de quien no vuelva a abrir la app se
  cierra con `abandoned` en su primer intento tras 90 días;
- si para entonces existe el enlace universal (T041), el AASA de la consola
  cambia de Team ID.

## Dónde está cada cosa

- API: `core/phone_credential.py`, `core/client_auth.py` (rama del teléfono),
  `services/client_phones.py`, `services/session_codes.py` (propósito
  `client_phone`), `services/push_{events,texts,payloads,fanout}.py`,
  `api/app_public.py`, `api/console/lite/phones.py`, migraciones 0165–0169.
- Worker: `push/{apns,fcm,dispatcher}.py`, `push-dispatcher` en `bootstrap.py`.
- Consola: `app/(console)/account/phones` («Tus teléfonos»). La entrada de la
  app no pasa por ella.
- Admin: `tenants/[id]/access/phones-list.tsx`.
- App: `apps/mobile/src/{app,api,auth,features,push,motion,theme,ui,i18n}`.

## Reservas (spec 044)

La pestaña del módulo `reservas`, en el modo que diga la API (`/me.reservas.mode`:
Servicios o Aforo; lo elige el admin y el teléfono no lo cambia). Contrato:
[`specs/043-reservas/contracts/lite-api.md`](../specs/043-reservas/contracts/lite-api.md)
(rutas `/console/lite/reservas/*`, congelado el 2026-10-22).

- **Un adaptador** (`src/api/reservas.ts`) entre el contrato y el modelo de las
  pantallas ([data-model.md](../specs/044-la-app-con-reservas/data-model.md)).
  Las rutas aún no están en `openapi.json` y van por `authedFetch` (la misma
  credencial y la misma renovación). Cada acción manda la `version` de la reserva
  en `If-Match`; un 412 `stale` se dice en una frase y se relee.
- **La hora es la del negocio** (D3): fechas y horas de pared de su zona
  (`settings.timezone`); «ahora» es el reloj del teléfono en esa zona.
- **Pantallas**: `src/app/(app)/reservas/` (Día, Semana y Mes; Lista de espera
  y Ajustes de reservas apiladas) y cuatro hojas en la pila raíz,
  `src/app/reserva/{[id],nueva,llegada,bloquear}` (`useSheetOptions().reserva` y
  `.reservaForm`). En Servicios, el día en lista o cuadrícula por profesional;
  en Aforo, cifras, tira de franjas y grupos por hora con «Llegó» y «No vino».
  Los botones son los que la API deja (`allowed`).
- **Los dos «+»** (D6): «Nueva reserva» es un botón de barra con un calendario
  en iOS y el flotante extendido en Android; el «+» redondo es solo «Llegada sin
  reserva» (Aforo, Día, hoy), en vidrio en iOS 26 (`src/ui/fab.tsx`).
- **El aviso breve** (`src/ui/toast.tsx`, D7): una frase para lo que no queda a
  la vista, anunciada al lector de pantalla, con «Deshacer» tras «Llegó» o «No
  vino». Cancelar pide confirmación porque avisa al cliente por WhatsApp.
- **Inicio** cuenta las reservas de hoy sin confirmar y «Hoy en Reservas» con
  la misma lectura que la pestaña (D4), no con `/summary`.
- **Datos de ejemplo** (D2): un build de desarrollo con
  `EXPO_PUBLIC_RESERVAS_DEMO=services|capacity` (y, para ver estados,
  `EXPO_PUBLIC_RESERVAS_DEMO_STATE=empty|error|slow`) enseña Barbería Norte o
  Casa Lucía desde `src/api/reservas-demo.ts`, con «Datos de ejemplo» en cada
  pantalla. Fuera de `__DEV__` ese archivo no se carga.
- Nada de Reservas va a disco (`__tests__/reservas-no-disk.test.ts`).

Lo que dejó la primera pasada en el simulador (hallazgos R1–R16 en
`specs/044-la-app-con-reservas/evidence/hallazgos.md`), como reglas:

- **Un reloj que avanza es estado** (`useNowMs` en `src/lib/use-now.ts`), y la
  hora se pasa a la cuenta. Un `useMemo` con un tic que la cuenta no lee lo
  congela React Compiler: «Ahora» se quedaba en la hora de la lectura.
- **Tirar para recargar gira solo con el gesto** (`usePullRefresh`), nunca con
  `isRefetching`: cada relectura en segundo plano lo encendía y en la Bandeja
  dejaba el título grande bajo la búsqueda.
- **iOS 26 desordena las etiquetas de la barra** si la pestaña cambia con una
  pantalla de la pila raíz encima (el enlace del contacto a su reserva): las
  pestañas reenvían su estilo al volver a verse (`useTabRelayout` en
  `src/app/(app)/_layout.tsx`).
- **Una renovación rechazada cierra el teléfono**, venga con el código que
  venga (`phone_closed`, `invalid_grant`…), salvo `app_update_required`: si no,
  la app se quedaba en «No se pudo cargar» sin volver a Entrar (R17).
- **Una hoja dice sus errores dentro**: el aviso breve vive en la raíz y en iOS
  queda debajo de un `formSheet`. Al acertar, la hoja se cierra y el aviso se
  ve; al fallar, la frase va en la hoja (`useActOn(t)` con `onError`).

La revisión con los gates de UI (G1–G5 en `evidence/revision.md`) dejó dos más:
un periodo que se está leyendo nunca enseña el anterior como si fuera él
(`showsOtherPeriod`), y los controles de Ajustes no se desmontan al guardar.

## Mejoras de la spec 044 en lo que ya había

- **Bandeja**: con «Todas» y sin búsqueda, las que esperan a una persona van
  arriba con el motivo y «hace N min» (`waiting` de la 045 §2); al pie, qué
  conversaciones enseña.
- **Conversación**: la tarjeta de espera dice desde cuándo y quién lo pidió; con
  el control, «Devolver» a un toque y las respuestas guardadas como chips.
- **Contacto**: su próxima reserva (`contact.next_booking`), que lleva a ella.
- **Consumo**: empieza por «Te alcanza hasta el …» (`balance.runs_out_on`).
- **Avisos**: tres de Reservas (`reservas.agent_change`,
  `reservas.cancelled_today`, `reservas.waitlist_accepted`, este apagado de
  partida), agrupados por módulo en Ajustes; «Silenciar fuera del horario del
  negocio» si la API lo trae (045 §5), con el horario de `/me.business`. Canal
  de Android `reservations_v1` y categoría de iOS `reservations`. Un aviso de
  Reservas (`auphere-customers://reservas/{id}`) abre la reserva.

## Agentes, Negocio y correcciones (spec 047)

Contrato: [`specs/047-la-fabrica-de-agentes/contracts/lite-app-api.md`](../specs/047-la-fabrica-de-agentes/contracts/lite-app-api.md)
(rutas `/console/lite/{agents,channels,business,corrections}/*`, ya en
`openapi.json`) y [`events.md`](../specs/047-la-fabrica-de-agentes/contracts/events.md)
(estados, motivos y avisos). Tareas T169, T170, T171 y la parte de la app de T176.

- **Agentes** (módulo `agents` en `/me.nav`): un grupo en Inicio, una fila por
  agente con su estado en palabras y tono de la consola (`visible_state`, que la
  app nunca recalcula; 25.5), y `src/app/agente/[id].tsx` en la pila raíz, por
  encima de las pestañas. La API no lee un agente suelto: la pantalla sale de la
  misma lista que Inicio (`useAgents`). Enseña qué significa el estado, quién lo
  pausó, desde dónde y desde cuándo («Lo pausó Marta desde la app. En pausa desde
  hace 5 min»: `paused_by_name`, `paused_origin`, `paused_at`; sin nombre ni hora
  si fue el sistema), sus números con su
  estado y su propia pausa, y **solo** «Pausar» o «Reanudar» si están en
  `allowed`. Pausar con conversaciones en curso pregunta y dice cuántas (409
  `confirm_required`, 27.8); una pausa del sistema o del partner no tiene botón:
  dice por qué y a quién pedírselo (`whyNoResume`, 409 `system_pause`). Lo que
  la persona no puede hacer va en una frase al pie, nunca como botón.
- **Negocio** (módulo `business`): `src/app/negocio/{index,horario,servicios,sedes}.tsx`
  en la pila raíz, desde Inicio y desde Ajustes. En iOS Ajustes es una hoja y una
  pantalla apilada debajo se abriría detrás: la hoja cede su sitio
  (`router.replace`); en Android se apila. Índice con lo que guarda cada sección
  y su procedencia («Editado por Marta desde la app», 13.1) y el último cambio
  con «Deshacer». Horario: «Así lo dirá el agente» primero (el `label` de la API),
  la semana día a día con su interruptor y sus turnos (hasta seis), y las fechas
  especiales con un calendario propio (sin dependencias nuevas). Con sedes,
  «Horario de» elige el negocio o una sede (`features/business/week-pane.tsx`,
  `GET /business/hours?location_id=`): la sede usa el del negocio hasta tener el
  suyo («Usar el horario del negocio») y se guarda con la revisión de Sedes, en
  su propio borrador. Servicios:
  precio (sin precio, gratis o importe en la moneda y los decimales del negocio,
  `exponent`), duración solo si se reserva (la API rechaza
  `duration_not_allowed`), descripción; el nombre, quién lo hace y qué agentes lo
  ofrecen son del partner y solo se leen. Sedes: nombre, dirección y teléfono
  E.164; archivar pregunta y el aviso breve la restaura (`/restore`), porque la
  lista no trae las archivadas.
- **Cada escritura** pasa por `useSectionWrite` (`src/features/business/`):
  `If-Match` con la revisión de la sección e `Idempotency-Key`. Un 412
  `revision_conflict` mete en la caché la sección como está (`current`), conserva
  lo escrito y da a elegir: «Guardar lo mío» (con la revisión nueva) o «Ver lo
  nuevo» (13.4). Al guardar, el aviso breve ofrece «Deshacer» del cambio recién
  hecho (`POST /business/history/{id}/undo`); 412 y 409 del deshacer se dicen
  con las frases de la consola.
- **Sin conexión no se guarda ni se encola nada** (50.5): la barra lo dice, los
  botones de escribir se apagan y lo escrito vive en un borrador **en memoria**
  (`src/lib/drafts.ts`, `useDraft`), que sobrevive a salir y volver a la
  pantalla y se borra al guardar o al cerrar sesión. Nunca va a disco: una
  corrección puede llevar palabras de un cliente final.
- **«Corregir esta respuesta»** (T176, requisito 52): bajo cada respuesta del
  agente en el hilo, un «Corregir» discreto con objetivo de 44 pt
  (`MessageBubble`), que abre `conversacion/[id]/corregir` como hoja alta. Tres
  pasos: cómo debió responder y para quién (todo el negocio o solo este agente);
  antes de enviar, si es **dato** o **comportamiento** y qué pasa con cada uno, con
  la lección y la paráfrasis editables (lo que verá el partner, nunca el
  mensaje); los datos personales que la API marca (`pii`) se enseñan con sus
  palabras y bloquean enviar hasta quitarlos, y lo editado se vuelve a revisar
  (`PATCH` y luego `send`; un 422 `pii_present` vuelve a la lista). Un dato
  enviado se puede deshacer; un comportamiento queda como propuesta del partner.
- **Bandeja** (T170, 50.7): cada fila dice «La atiende {agente}»
  (`handled_by_agent`, mientras la lleva un agente) y, si espera, el motivo por
  su código (`waiting_reason` de la lista, `events.md` §2). En la conversación,
  el agente de `handled_by_agent` bajo el nombre y, en el pie, el motivo por su
  código (`waiting_code` del detalle) encima de las palabras del agente
  (`waiting_reason`, de la 045); con código y sin palabras ya no dice «El agente
  no dijo por qué».
- **Consumo** (50.6): «Queda poco», «No llega a fin de mes» o «Agotada»
  (`bag_state`), los días al ritmo de 7 días (`days_left`, o «Aún no hay datos
  para estimarlo») y «Pídeselo a {partner}» (`partner_name`), sin botón de pedir.
  El saldo va en la moneda de la bolsa (`balance.currency`).
- **Avisos** (T170, `events.md` §3.1): un tipo nuevo del teléfono,
  `agents.state` («Agentes y números»: el tope de un agente, sus pausas y las de
  sus números, y un número con problemas), con su grupo y su interruptor en
  Ajustes solo con el módulo `agents`; nace encendido y la API lo encendió en los
  teléfonos que ya había. Su URL es `auphere-customers://agents/<id>` (con
  `/channels/<id>` detrás para un número, que se ve en su agente) y `routeFor` la
  abre en `agente/[id]`; canal de Android `agents_v1` y categoría de iOS
  `agents`. Los tres de la bolsa (`client.wallet.*`) viajan como
  `client.balance` (`balance_v1`, `client_balance`, `auphere-customers://usage`
  → Consumo). Un aviso sin URL o con una que la app no conoce no abre nada.
- **Accesibilidad** (50.9): todo crece con el texto del teléfono (filas que se
  apilan, botones que parten la etiqueta), cada control tiene nombre para el
  lector de pantalla (los de cada número dicen cuál), los estados van en
  palabras además de en color, y los objetivos son de 48 × 48 (44 pt con su
  margen en «Corregir»).
- **Abierto en la API** (la app no lo rodea): las pausas de agentes y números
  no declaran `If-Match` ni `Idempotency-Key`; `GET /business` no lista
  servicios y sedes archivados (por eso «Restaurar» sale solo en el aviso de
  archivar); el 412 de Negocio trae
  quién por su id, no por su nombre; `PriceOut` y `HoursIn` van poco tipados en
  el OpenAPI.
- **Pruebas**: `__tests__/{agentes,negocio,corregir,fabrica-avisos}.test.tsx`
  (Jest y RNTL con `fireEvent` asíncrono, caché real de React Query) y el flujo
  de Maestro `e2e/agentes-negocio.yaml` (pausar y reanudar, cambiar el horario
  y deshacerlo).

## Versión 1.2.0

`version` 1.2.0 (spec 047, T171) y `runtimeVersion` que la sigue: Agentes,
Negocio y las correcciones son pantallas y datos nuevos, y entran por las
tiendas (50.8). Por aire, solo arreglos de la 1.2.0. Sin módulos nativos nuevos
ni permisos nuevos; revisada contra las guías: nada se compra ni se pide dentro
de la app (App Store 3.1.1; «Pídeselo a {partner}» no lleva botón), ningún
permiso nuevo del sistema (5.1.1) y la ficha de datos de Play no cambia de
categoría (el texto de una corrección es contenido del usuario, como un
mensaje). Los builds no se lanzan sin que Luis lo pida.

## Versión 1.1.0

`version` 1.1.0 y `runtimeVersion` que la sigue: la 1.0.0 de TestFlight no
tiene `expo-glass-effect` y no puede recibir nada por aire. `preview` hace un
APK; `staging`, AAB para la pista interna de Play y el build de TestFlight. Lo
que falta crear (Play Console, Firebase, claves) y los comandos están en
[`specs/044-la-app-con-reservas/evidence/builds.md`](../specs/044-la-app-con-reservas/evidence/builds.md).
