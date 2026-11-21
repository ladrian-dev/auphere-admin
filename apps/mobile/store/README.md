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

## Antes de enviar a revisión

Lo que decide o hace Luis:

1. **Cuenta de revisión en producción.** Un negocio de prueba bajo Auphere Internal Partner, con conversaciones de prueba y una Bandeja que no escriba a personas reales. Sus credenciales van solo en App Store Connect y en Play Console, nunca en el repo.
2. **Copyright y países.** El titular de los derechos (Auphere o FACELAD SpA) y dónde se publica.
3. **Contacto de App Review.** Nombre, teléfono y correo de quien atiende a Apple.
4. **Política de privacidad.** La de auphere.com tiene que hablar de la app: los avisos, las fotos y archivos enviados, el borrado de la cuenta. La app ya la enlaza desde Ajustes.
5. **Build de Android.** El de staging de la 1.3.0 ha fallado dos veces en EAS el 2026-11-21 con «Gradle build daemon disappeared unexpectedly», en la máquina por defecto. En el segundo, Gradle murió mientras R8 reducía el código de la app y, a la vez, se compilaba el código nativo de react-native-screens y react-native-worklets para cuatro arquitecturas: es memoria. Las salidas:
   - una máquina más grande en EAS, `resourceClass: "large"` en el perfil `staging` (y en `production`). Es configuración del build, sin cambio de comportamiento: entra como cambio trivial, pero cuesta dinero y lo aprueba Luis;
   - compilar el AAB en este Mac con `eas build --local`, que usa las credenciales de EAS. Sin coste, pero ocupa disco y tarda.
6. **Subida a Play.** EAS no tiene la cuenta de servicio de Play, así que cada AAB se sube a mano a la pista interna, o se crea esa cuenta y se guarda en EAS.

Cambios de la app que piden su spec (la 070, cuando se abra):

- `EXPO_PUBLIC_APP_STORE_ID` en el perfil de producción, para que «Actualizar» abra la ficha y no una búsqueda.
- La pista de producción de Play en `submit.production.android` (hoy `internal` y `draft`).
- Los permisos que sobren en el AAB 1.3.0 (`SYSTEM_ALERT_WINDOW` y los de almacenamiento venían en la 1.1.0).
- La lista de datos recogidos del manifiesto de privacidad de iOS, hoy vacía, alineada con la de App Store Connect (`app-store/revision.md`).

Lo que la investigación del 2026-11-21 da además como bloqueo para un envío público, y no es de las fichas (`research/2026-11-21-app-movil-a-tiendas/04-la-app-hoy-y-las-tiendas.md`, §4.12): los avisos en producción (secretos de APNs y FCM), el límite por IP de las rutas de entrada en Cloudflare y la evidencia en dispositivo (avisos reales, VoiceOver y TalkBack).
