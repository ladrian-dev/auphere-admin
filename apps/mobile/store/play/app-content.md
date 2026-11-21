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
| ID de publicidad | No lo usa. Comprobado en el manifiesto del AAB 1.1.0 (3), que no trae `AD_ID`; **falta comprobarlo en el AAB 1.3.0** cuando exista |

## Te toca (Luis)

### Datos de inicio de sesión

Toda la app pide una cuenta, y Play quiere una que funcione para su revisión: la misma cuenta de revisión que Apple (ver `../README.md`, «Antes de enviar»). Instrucciones, en inglés, para pegar:

> Auphere Customers is the companion app for businesses that use Auphere. Accounts are issued by Auphere; the app has no sign-up. Sign in with the email and password provided. You will see Home, the Inbox (the business's WhatsApp, Instagram and Messenger conversations), Bookings and Usage. No other code or step is needed.

El público objetivo no se puede empezar hasta guardar esta declaración.

### Público objetivo y contenido

Edad: **18 y más** solamente. No está dirigida a niños.

### Seguridad de los datos («Data safety») — borrador para revisar

Es una declaración legal: revísala antes de enviarla. Es el mismo inventario que la privacidad del App Store (`../app-store/revision.md`); si cambia uno, cambia el otro.

- ¿Recoge o comparte datos? **Sí**. ¿Cifrados en tránsito? **Sí** (HTTPS).
- ¿Se puede pedir el borrado? **Sí**: Ajustes › «Solicitar el borrado de la cuenta», o por correo a contacto@auphere.com. La app no crea cuentas; **por verificar en la consola** si Play pide de todos modos una URL web para el borrado. Si la pide, hace falta una página en auphere.com que explique cómo solicitarlo.
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
| ID del dispositivo u otros | El token de avisos (FCM) y el identificador del servicio de actualizaciones de Expo | No | Funcionalidad (avisos y actualizaciones) |

Sin analítica ni informes de errores de terceros: la app no los lleva y el proyecto de Firebase se creó sin Google Analytics.

### Permisos del AAB

La 1.3.0 bloquea `RECORD_AUDIO` y `ACCESS_FINE_LOCATION` (`android.blockedPermissions` en `app.config.ts`). El AAB 1.1.0 pedía además `SYSTEM_ALERT_WINDOW`, `READ_EXTERNAL_STORAGE` y `WRITE_EXTERNAL_STORAGE`, que vienen de dependencias. Hay que mirar el manifiesto del AAB 1.3.0 cuando el build salga: lo que sobre se bloquea con su spec, porque es un cambio de la app.
