# Tiendas — Auphere Customers

Lo que hace falta para mandar la app a revisión en el App Store y en Google Play: textos, capturas y declaraciones. Nada de esto se sube solo: lo pega o lo sube Luis en App Store Connect y en Play Console.

| Archivo | Qué es |
|---|---|
| `app-store/ficha.md` | Ficha del App Store en español e inglés, y los datos de la app |
| `app-store/revision.md` | Información para App Review, privacidad, clasificación por edad y cifrado |
| `app-store/capturas/6.9/`, `6.3/` | Siete capturas de iPhone, 1320 × 2868 y 1206 × 2622 |
| `play/ficha.md` | Ficha de Play en es-419 y en-US, y la lista de imágenes |
| `play/app-content.md` | Declaraciones de «Contenido de la app» y seguridad de los datos |
| `play/*.png` | Icono, imagen destacada (es y en) y siete capturas de 1080 × 2424 |
| `play_assets.py` | Genera las imágenes de Play |
| `check_limits.py` | Comprueba la longitud de los textos de las dos fichas |

Antes de pegar un texto, `python3 apps/mobile/store/check_limits.py` tiene que salir en verde.

## Cómo se rehacen las capturas

Con el negocio de ejemplo (`EXPO_PUBLIC_DEMO=1`, Clínica Brisa), en español, con la zona horaria de Santiago y sin teléfonos visibles. El botón de herramientas del cliente de desarrollo se apaga desde su menú («Tools button»).

**iPhone** (simulador iPhone 17 Pro Max, iOS 26):

1. `xcrun simctl status_bar booted override --time 12:40 --batteryState charged --batteryLevel 100 --cellularBars 4 --wifiBars 3`.
2. Zona horaria: `xcrun simctl spawn booted launchctl setenv TZ America/Santiago` y volver a abrir la app.
3. Captura: `xcrun simctl io booted screenshot <archivo>.png`; se exporta a JPEG sin transparencia y se escala a 1206 × 2622 para el tamaño de 6,3″.

**Android** (emulador Pixel 9, Android 16):

1. `adb shell cmd alarm set-timezone America/Santiago` y `adb shell settings put system time_12_24 24`.
2. Barra de estado en modo demostración: `adb shell settings put global sysui_demo_allowed 1`, y luego `am broadcast -a com.android.systemui.demo` con `-e command enter`, `-e command clock -e hhmm <hora>`, `-e command battery -e level 100 -e plugged false`, `-e command network -e wifi show -e level 4 -e fully true`, `-e command network -e mobile hide` y `-e command notifications -e visible false`.
3. Captura: `adb exec-out screencap -p > <carpeta>/01-inicio.png`, con los nombres que lista `play_assets.py`.
4. `uv run --with pillow python apps/mobile/store/play_assets.py "$PWD" <carpeta>` desde la raíz del repo.

Las de las dos tiendas son las mismas siete pantallas en el mismo orden: Inicio, Bandeja, una conversación que espera a una persona, la misma tras tomar el control, Reservas, Consumo y el preaviso de los avisos.

Dos cosas del negocio de ejemplo que se ven en las capturas y decide Luis si se arreglan:

- **Reservas enseña los servicios de una barbería** (Corte, Barba) bajo el nombre Clínica Brisa.
- **Suena a España, y las fichas son para Latinoamérica.** La app estaba en es-ES, así que el saldo sale como «23,91 US$»; y los mensajes de ejemplo de Lucía dicen «¿Me podéis devolver la seña?» y «Os paso el justificante».

Arreglarlo es cambiar los datos de ejemplo, poner la app en es-419 y repetir las capturas 1, 3, 4 y 5 de las dos tiendas.

## App Store Connect, estado el 2026-11-21

Rellenado en la consola y comprobado al recargar la página:

- **Información de la app:** subtítulo en es-MX, es-ES y en-US; categorías Empresa y Productividad; sin contenido de terceros; edad 4+ (respuestas en `app-store/revision.md`).
- **Versión 1.3.0** (antes «1.0»): ficha en los tres idiomas, URLs de soporte y marketing, copyright «2026 FACELAD SpA», notas para App Review, «Sign-in required» marcado y lanzamiento manual tras la aprobación.
- **Capturas:** las siete de 1206 × 2622 en el hueco de iPhone con Dynamic Island de tamaño medio. Apple las usa para todos los tamaños e idiomas.
- **Precio y disponibilidad:** gratis; 174 países, sin China continental. Siguen marcadas por defecto «disponible en Mac con Apple silicon» y «en Apple Vision Pro».
- **Privacidad:** URL de la política en los tres idiomas y los ocho tipos de datos, **publicada**.

No se ha pulsado «Add for Review».

Revisado otra vez por la noche, campo por campo:

- ficha de la versión en es-MX, en-US y es-ES;
- nombre «Auphere Customers» y subtítulo en los tres idiomas;
- las siete capturas;
- notas para App Review y lanzamiento manual;
- edad 4+ (172 países);
- gratis, en 174 países sin China continental;
- privacidad publicada;
- categorías y contenido de terceros.

Las capturas de iPad no hacen falta, porque `supportsTablet` es `false`. En TestFlight, el build 4 está «Ready to Submit» para el grupo Auphere Team. Vacíos, a propósito: usuario y contraseña de «Sign-in Information», el contacto de App Review y el build. Opcionales sin rellenar: la cabecera nueva del producto («Header») y las etiquetas de accesibilidad (App Accessibility), que conviene declarar solo cuando VoiceOver y el texto grande estén probados en un teléfono. Los dos avisos de App Compliance (evaluación de seguridad y contenido generado por IA) son solo para China continental, que no está en la disponibilidad. El «trader» de la DSA ya está declarado.

## Play Console, estado el 2026-11-21

- **Ficha principal:** textos en es-419 (por defecto) y en-US, icono, imagen destacada en cada idioma y las siete capturas en orden. En «AI asset declaration» se marcó «Don't label assets»: las imágenes son capturas de la app y gráficos hechos por script, no generados con IA. Guardada; **no se ha enviado a revisión** desde «Publishing overview».
- **Pista interna:** la versión 12 (1.3.0), subida por Luis, está activa para la lista «Auphere Customers - interno». Hasta que la app pase la primera revisión, quien la instala ve el nombre provisional «com.auphere.customers (unreviewed)».
- **Firma:** Play firma la app (Play App Signing). La clave de subida es la de EAS, y la versión 12 entró con ella.
- **Producción, bloqueada:** todos sus pasos (países, crear la versión, enviarla a revisión) siguen con candado hasta que «Contenido de la app» esté en 11 de 11. Hoy está en 8. La cuenta Facelad es de organización, así que, una vez desbloqueada, no hace falta la prueba cerrada de 14 días con 12 personas.
- **Lo que falta, en este orden:** la cuenta de revisión en producción, después los datos de inicio de sesión con esa cuenta, después el público objetivo (18+) y por último enviar la seguridad de los datos, que ya está rellenada como borrador (`play/app-content.md`).
- **Declaración de «trader»:** antes de febrero de 2027, y solo la puede hacer el propietario de la cuenta de Play.
- **Permisos:** Play no ha pedido ninguna declaración de permisos para la versión 12. Tras subirla, «Contenido de la app» solo pide esas tres cosas.
- El aviso de política de la cuenta es de Restaurant AI, no de esta app. Hay además un aviso de la cuenta de pagos de Facelad, del 2 de noviembre, que no se ha abierto: es de la cuenta, y lo tiene que mirar su propietario.

## Antes de enviar a revisión

Lo que decide o hace Luis:

1. **Cuenta de revisión en producción.** Un negocio de prueba bajo Auphere Internal Partner, con conversaciones de prueba y una Bandeja que no escriba a personas reales. Sus credenciales van solo en App Store Connect y en Play Console, nunca en el repo. Cuando exista, se añade a las notas la frase de que las respuestas no llegan a personas reales.
2. **Build de producción para iOS.** El build 4 es del perfil `staging` (apunta a `api.staging.auphere.com`) y no se ha asociado a la versión. La revisión necesita uno del perfil `production`, porque la cuenta de revisión estará en producción.
3. **Contacto de App Review.** Nombre, teléfono y correo de quien atiende a Apple.
4. **Política de privacidad.** La de auphere.com tiene que hablar de la app: los avisos, las fotos y archivos enviados, el borrado de la cuenta. La app ya la enlaza desde Ajustes.
5. **Build de Android.** El de staging de la 1.3.0 ha fallado dos veces en EAS el 2026-11-21 con «Gradle build daemon disappeared unexpectedly», en la máquina por defecto. En el segundo, Gradle murió mientras R8 reducía el código de la app y, a la vez, se compilaba el código nativo de react-native-screens y react-native-worklets para cuatro arquitecturas: es memoria. Ese mismo día salió en este Mac (versionCode 12, 6 min 51 s, `~/Downloads/auphere-customers-1.3.0-staging.aab`) con:

   ```bash
   cd apps/mobile && ANDROID_HOME=$HOME/Library/Android/sdk GOOGLE_SERVICES_JSON=$HOME/Downloads/google-services.json GRADLE_OPTS='-Dorg.gradle.jvmargs="-Xmx6g -XX:MaxMetaspaceSize=2g -Dfile.encoding=UTF-8"' npx eas-cli build --platform android --profile staging --local --output $HOME/Downloads/auphere-customers-1.3.0-staging.aab
   ```

   `GOOGLE_SERVICES_JSON` tiene que apuntar a un archivo local, porque el build local no puede leer la variable secreta de EAS. `GRADLE_OPTS` hace falta porque el `gradle.properties` que genera Expo da a Gradle 2 GB y 512 MB de Metaspace, y `lintVitalAnalyzeRelease` se queda sin Metaspace. Cada build, local o en EAS, sube el versionCode remoto. Para no depender del Mac, la otra salida es una máquina más grande en EAS (`resourceClass: "large"` en `staging` y `production`): es configuración del build, sin cambio de comportamiento, pero cuesta dinero y la aprueba Luis.
6. **Subida a Play.** EAS no tiene la cuenta de servicio de Play, así que cada AAB se sube a mano a la pista interna, o se crea esa cuenta y se guarda en EAS.

## Builds de producción

El perfil `production` de `eas.json` apunta a `api.auphere.com` y `console.auphere.com`, usa el canal `production` y sube el número de build solo. La variable `GOOGLE_SERVICES_JSON` existe en el entorno `production` de EAS (comprobado el 2026-11-21). El paquete y el bundle id son los mismos que en staging, y también las credenciales de EAS.

- **iOS:** `npx eas-cli build --platform ios --profile production` y después `npx eas-cli submit --platform ios --profile production --latest`. Ese build se asocia a la versión 1.3.0 en App Store Connect.
- **Android:** en EAS fallará igual que el de staging mientras no se cambie la máquina (punto 5). En este Mac es el mismo comando del punto 5, con `--profile production` y otro nombre de salida. El AAB se sube a mano a la pista de producción, o primero a la interna para probarlo.

Cambios de la app que piden su spec (la 070, cuando se abra):

- `EXPO_PUBLIC_APP_STORE_ID` en el perfil de producción, para que «Actualizar» abra la ficha y no una búsqueda.
- La pista de producción de Play en `submit.production.android` (hoy `internal` y `draft`).
- Los permisos que sobran en el AAB 1.3.0: `SYSTEM_ALERT_WINDOW`, `READ_EXTERNAL_STORAGE`, `WRITE_EXTERNAL_STORAGE`, y `USE_BIOMETRIC` y `USE_FINGERPRINT` si se confirma que no hacen falta (lista completa en `play/app-content.md`).
- La lista de datos recogidos del manifiesto de privacidad de iOS, hoy vacía, alineada con la de App Store Connect (`app-store/revision.md`).

Lo que la investigación del 2026-11-21 da además como bloqueo para un envío público, y no es de las fichas (`research/2026-11-21-app-movil-a-tiendas/04-la-app-hoy-y-las-tiendas.md`, §4.12): los avisos en producción (secretos de APNs y FCM), el límite por IP de las rutas de entrada en Cloudflare y la evidencia en dispositivo (avisos reales, VoiceOver y TalkBack).
