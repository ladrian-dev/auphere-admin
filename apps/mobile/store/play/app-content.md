# «Contenido de la app» en Play Console — Auphere Customers

Play Console › Política y programas › Contenido de la app. Las declaraciones de 2026-10-22 siguen valiendo para la 1.3.0 salvo lo que se marca. Revisado el 2026-11-21.

## Hecho (2026-10-22)

| Declaración | Respuesta |
|---|---|
| Política de privacidad | https://www.auphere.com/es/privacidad |
| Anuncios | No tiene anuncios |
| Clasificación de contenido | Categoría «Social o comunicación» → Comunicación (uno a uno con personas que el usuario conoce). Sin ubicación compartida, sin compras digitales, sin bloquear ni denunciar, sin moderación, no limitado a amigos invitados. Contacto de IARC: contacto@auphere.com. Resultado: ESRB Everyone, PEGI guía parental, IARC 12+, USK 16+ (todo por «los usuarios interactúan») |
| Apps de gobierno | No |
| Funciones financieras | Ninguna |
| Apps de salud | Ninguna |
| ID de publicidad | No lo usa. Comprobado en los manifiestos de los AAB 1.1.0 (3) y 1.3.0 (12): ninguno trae `AD_ID` |

## Te toca (Luis)

### Datos de inicio de sesión

Toda la app pide una cuenta, y Play quiere una que funcione para su revisión: la misma cuenta de revisión que Apple (ver `../README.md`, «Antes de enviar»). Instrucciones, en inglés, para pegar:

> Auphere Customers is the companion app for businesses that use Auphere. Accounts are issued by Auphere; the app has no sign-up. Sign in with the email and password provided. You will see Home, the Inbox (the business's WhatsApp, Instagram and Messenger conversations), Bookings and Usage. No other code or step is needed.

El público objetivo no se puede empezar hasta guardar esta declaración.

### Público objetivo y contenido

Edad: **18 y más** solamente. No está dirigida a niños.

### Seguridad de los datos («Data safety»)

**Rellenada en Play Console el 2026-11-21 y guardada como borrador.** Play no deja enviarla hasta declarar el público objetivo, y el público objetivo no se puede empezar sin los datos de inicio de sesión. Es el mismo inventario que la privacidad del App Store (`../app-store/revision.md`); si cambia uno, cambia el otro.

- ¿Recoge o comparte datos? **Sí**. ¿Cifrados en tránsito? **Sí** (HTTPS).
- Creación de cuentas: **«My app does not allow users to create an account»**. A la pregunta «Can users login with accounts created outside of the app?» se respondió **Sí**, y en «How are these accounts created?», **«Through employment, or enterprise accounts»**: las da Auphere o el partner.
- ¿Se puede pedir el borrado de los datos? **Sin responder (es opcional).** Responder «Sí» obliga a poner una URL web que explique cómo pedirlo, y esa página no existe. La app ya permite pedirlo desde Ajustes › «Solicitar el borrado de la cuenta» y por correo a contacto@auphere.com. Cuando haya página en auphere.com, se responde «Sí» con su URL.
- Ningún dato se «comparte» en el sentido de Play: lo que sale hacia WhatsApp, Instagram o Messenger es el envío que pide la propia persona, y Play no lo cuenta como compartir.

| Tipo (Play) | Qué es en la app | ¿Obligatorio? | Para qué |
|---|---|---|---|
| Información personal › Nombre | El nombre de quien entra y el de los clientes a los que reserva | Sí | Funcionalidad, gestión de la cuenta |
| Información personal › Dirección de correo | El correo con el que entra | Sí | Gestión de la cuenta |
| Información personal › ID de usuario | El identificador de su cuenta de Auphere | Sí | Funcionalidad, gestión de la cuenta |
| Información personal › Número de teléfono | El teléfono del cliente al crear una reserva | No | Funcionalidad |
| Mensajes › Otros mensajes en la app | Lo que escribe a un cliente desde la Bandeja | No | Funcionalidad |
| Fotos y vídeos › Fotos | Una imagen enviada a un cliente (galería o cámara) | No | Funcionalidad |
| Archivos y documentos | Un documento enviado a un cliente | No | Funcionalidad |
| ID del dispositivo u otros | El token de avisos (FCM) y el identificador del servicio de actualizaciones de Expo | Sí (el de actualizaciones se envía siempre) | Funcionalidad (avisos y actualizaciones) |

Ninguno se procesa de forma efímera ni se comparte, y ninguno se usa para analítica, publicidad ni personalización.

Sin analítica ni informes de errores de terceros: la app no los lleva y el proyecto de Firebase se creó sin Google Analytics.

### Permisos del AAB

La 1.3.0 bloquea `RECORD_AUDIO` y `ACCESS_FINE_LOCATION` (`android.blockedPermissions` en `app.config.ts`).

Manifiesto del AAB 1.3.0 (12), leído con `aapt2 dump xmltree` el 2026-11-21. Pide:

- los que usa: `INTERNET`, `ACCESS_NETWORK_STATE`, `ACCESS_WIFI_STATE`, `CAMERA`, `POST_NOTIFICATIONS`, `VIBRATE`, `WAKE_LOCK`, `RECEIVE_BOOT_COMPLETED` y `com.google.android.c2dm.permission.RECEIVE` (avisos de FCM);
- `USE_BIOMETRIC` y `USE_FINGERPRINT`, que la app no usa (no hay desbloqueo con huella ni cara en el código). No vienen de ningún paquete de `node_modules`: los trae una librería de Android, seguramente `androidx.biometric` por `expo-secure-store`, sin comprobar;
- los de los globos con el número de avisos en el icono (`READ_APP_BADGE` y los de los lanzadores de Samsung, Huawei, HTC, Sony, Oppo y otros), que vienen de la librería de avisos;
- `BIND_GET_INSTALL_REFERRER_SERVICE`, de una dependencia de Google;
- y los que sobran, igual que en la 1.1.0: `SYSTEM_ALERT_WINDOW`, `READ_EXTERNAL_STORAGE` y `WRITE_EXTERNAL_STORAGE`.

`android.permission.DUMP` aparece en el manifiesto pero no lo pide la app: protege el receptor `androidx.profileinstaller.ProfileInstallReceiver`, que llevan todas las apps con androidx. Ninguno de la lista exige una declaración de permisos en Play, y Play no ha pedido ninguna al subir la versión 12 a la pista interna (comprobado el 2026-11-21). Lo que sobra se bloquea con su spec (la 070), porque es un cambio de la app.
