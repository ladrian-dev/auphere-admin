# Builds 1.1.0 — lo que falta de Luis y los comandos (spec 044, R19, T043–T045)

Nada de esto se lanzó desde la sesión: `eas build` y `eas submit` usan la cuenta
de Luis y sus minutos, y solo se lanzan cuando él lo pida. La configuración del
repo ya está lista:

- `version` **1.1.0** (`app.config.ts`, `package.json`); `runtimeVersion` sigue
  la versión (`appVersion`), así que ninguna actualización por aire llega a la
  1.0.0 que está en TestFlight (no tiene el módulo nativo de la 042).
- `eas.json`: `preview` → **APK** para instalar a mano contra staging;
  `staging` → **AAB** para Play y build de tienda para TestFlight;
  `submit.staging`: iOS al `ascAppId 6825002452`, Android a la pista
  **internal**, `releaseStatus: completed`. El número de build lo lleva EAS
  (`appVersionSource: remote`, `autoIncrement`).
- Ningún perfil que no sea de desarrollo lleva los datos de ejemplo de Reservas
  (`__tests__/version.test.ts`).

## Dos arreglos que pidió el primer build (2026-10-22)

- **`expo-doctor`** fallaba por 11 parches del SDK 58 publicados ese día. Se
  aplicaron con `npx expo install --fix` (con el visto bueno de Luis) en un
  commit de dependencias aparte; `@expo/metro-runtime` ~58.0.15 pasa a
  dependencia directa porque el `expo-router` nuevo la pide. `verify.sh mobile`
  queda entero en verde.
- **El primer AAB falló en `lintVitalRelease`**: los archivos de `locales/`
  tenían las cadenas de iOS (`CFBundleDisplayName` y los textos de permisos) como
  claves sueltas, y Expo las copia también a Android (`values-b+es`, `values-b+en`)
  sin el idioma por defecto → `ExtraTranslation`. Ahora van bajo `"ios"`: iOS
  recibe lo mismo y Android nada (`__tests__/version.test.ts`). No se había visto
  porque era el primer build de publicación de Android.

## iOS → TestFlight

Ya existe todo (equipo de FACELAD, App ID, ficha en App Store Connect, clave
APNs en el secreto de staging). Solo:

```bash
cd apps/mobile && eas build -p ios --profile staging --auto-submit
```

Lo sube a TestFlight al terminar; los probadores internos lo tienen en cuanto
Apple lo procesa.

## Android → Play (pista interna) + Firebase

### Hecho el 2026-10-22 (con Luis, desde la sesión)

- **Play Console**, cuenta de organización **Facelad** (la misma de Astroluv y
  del equipo de iOS): app «Auphere Customers», `com.auphere.customers`, español
  de Latinoamérica, App, gratis (ID de Play 4973322287045435016).
  - Ficha principal: nombre, descripciones, categoría Empresa, contacto
    `contacto@auphere.com` y `https://www.auphere.com`. Textos en
    `apps/mobile/store/play/listing-es-419.md`.
  - Contenido de la app: privacidad, anuncios, clasificación, gobierno, finanzas
    y salud (`apps/mobile/store/play/app-content.md`).
  - Pruebas internas: lista «Auphere Customers - interno» (contacto@ladrian.dev)
    marcada en la pista.
- **EAS**: build `staging` de Android **1.1.0 (3)**, terminado; el (2) falló en
  `lintVitalRelease` por los `locales` (arriba). EAS creó y guarda la clave de
  subida de Android. El AAB, descargado en `~/Downloads/auphere-customers-1.1.0-3-staging.aab`
  (71 MB); su manifiesto no trae `AD_ID`. **No lleva Firebase**: no subirlo.
- **EAS, build 1.1.0 (4)** (`f11a3e7a-7681-4c54-a7fa-94f9ab1a3d23`), terminado el
  2026-10-22 a las 14:19 UTC: es el que va a Play. El log muestra
  `GOOGLE_SERVICES_JSON` cargada, `googleServicesFile` en la configuración,
  `:app:processReleaseGoogleServices`, `APP_VARIANT=staging` y
  `EXPO_PUBLIC_API_URL=https://api.staging.auphere.com`. El «production» que
  sale en el log es el entorno de variables de EAS (el que toma por defecto un
  build de tienda), no el servidor: la URL la pone el perfil `staging`.
- **Firebase**: proyecto `auphere-customers` (organización de Google Cloud
  ladrian.dev, sin Analytics ni Gemini), con las apps Android
  `com.auphere.customers` y `com.auphere.customers.dev`.

### Lo que falta, de Luis

1. **Imágenes de la ficha** (el navegador de la sesión no sube archivos):
   `apps/mobile/store/play/icon-512.png`, `feature-1024x500.png` y las siete
   `phone-*.png` en Ficha principal › Recursos gráficos. Son capturas de iOS:
   cambiarlas por las de Android tras la prueba en el dispositivo.
2. **Datos de inicio de sesión, público objetivo (18+) y seguridad de los
   datos**: borradores en `apps/mobile/store/play/app-content.md`. El ID de
   publicidad ya está declarado («No»).
3. **Primer AAB a mano**: Pruebas internas › Crear versión (queda abierta) ›
   Subir el AAB del build **1.1.0 (4)** (desde la página del build en expo.dev;
   el (3) no lleva Firebase), aceptar la firma de
   apps de Google Play, notas de la versión (abajo) › Siguiente › Guardar y
   publicar. Después, copiar el enlace de adhesión de la pista y abrirlo en el
   teléfono con contacto@ladrian.dev. Notas propuestas (es-419):
   «Primera versión de prueba: Reservas en los dos modos, quién espera y desde
   cuándo en la Bandeja, y Consumo con hasta cuándo te alcanza el saldo.»
4. ~~**`google-services.json`**~~ **Hecho el 2026-10-22**: el de Firebase (las dos
   apps, proyecto `auphere-customers`) está en EAS como variable de archivo
   secreta `GOOGLE_SERVICES_JSON` en development, preview y production. Lo
   lleva el build 1.1.0 (4); el (3) no.
5. ~~**Firebase › Configuración del proyecto › Cuentas de servicio › Generar
   clave privada** (JSON) para la API (FCM)~~ **Hecho por Luis el 2026-10-22**
   (clave en el secreto de staging, `push_secret_keys` y `terraform apply`). Es
   una clave privada: no pasó por la sesión.
6. **Google Cloud (proyecto `auphere-customers`) › IAM › Cuentas de servicio ›
   Crear cuenta** para EAS Submit, con su clave JSON; y en **Play Console ›
   Usuarios y permisos › Invitar** a su correo con permiso para publicar en
   pruebas.

### Antes de pasar de la prueba interna a producción

- Play exige que la política de privacidad **se enlace también dentro de la
  app** y que **hable de la app**. Hoy Ajustes no la enlaza y la de la web habla
  de la web y del servicio. Es un cambio de comportamiento (una fila «Política de
  privacidad» en Ajustes) y un cambio de texto en la web: va con su spec.
- Cambiar las capturas de iOS por capturas de Android.

### Dónde va cada cosa

| Qué | Dónde | Comando |
|---|---|---|
| `google-services.json` | Variable de archivo de EAS `GOOGLE_SERVICES_JSON` (la lee `app.config.ts`) | `eas env:create --name GOOGLE_SERVICES_JSON --type file --value ./google-services.json --visibility secret --environment development --environment preview --environment production` |
| Clave de la cuenta de servicio de Firebase (paso 3) | Secreto de **staging** en AWS: `NEXUS_FCM_PROJECT_ID` y `NEXUS_FCM_SERVICE_ACCOUNT_JSON` | `AWS_PROFILE=nexus ./infra/scripts/add_app_secret_keys.sh staging NEXUS_FCM_PROJECT_ID NEXUS_FCM_SERVICE_ACCOUNT_JSON`, descomentar `push_secret_keys` en `staging.tfvars` y `terraform apply` del workspace `staging` (`infra/terraform/20-services`) |
| Clave de la cuenta de servicio de Play (paso 4) | Credenciales de EAS (Android) | `eas credentials -p android` → «Google Service Account Key for Play Store Submissions» → subir el JSON |

### Los builds

```bash
cd apps/mobile && eas build -p android --profile staging
```

- **El primer AAB se sube a mano** (Play no deja que una herramienta cree la
  primera versión): descárgalo del build y súbelo en **Pruebas internas ›
  Crear versión**.
- Los siguientes:

```bash
cd apps/mobile && eas submit -p android --profile staging --latest
```

Para probar sin Play, un APK interno contra staging:

```bash
cd apps/mobile && eas build -p android --profile preview
```

## Qué verás en esos builds

- Hablan con **staging**. La pestaña Reservas aparece cuando la API de la 043
  esté desplegada en staging y el cliente tenga el módulo (orden de fusión
  042 → 045 → 043 → 044). Antes, la app es la de hoy con las mejoras que no
  dependen de Reservas; nada de datos de ejemplo.
- Los avisos de Android necesitan los pasos 2 y 3; sin ellos la app funciona y
  el worker lo registra.
