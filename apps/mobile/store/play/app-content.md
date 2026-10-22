# «Contenido de la app» en Play Console — Auphere Customers

Estado el 2026-10-22 (Play Console › Política y programas › Contenido de la app).

## Hecho

| Declaración | Respuesta |
|---|---|
| Política de privacidad | https://www.auphere.com/es/privacidad |
| Anuncios | No tiene anuncios |
| Clasificación de contenido | Categoría «Social o comunicación» → Comunicación (uno a uno con personas que el usuario conoce). Sin ubicación compartida, sin compras digitales, sin bloquear ni denunciar, sin moderación, no limitado a amigos invitados. Contacto de IARC: contacto@auphere.com. Resultado: ESRB Everyone, PEGI guía parental, IARC 12+, USK 16+ (todo por «los usuarios interactúan») |
| Apps de gobierno | No |
| Funciones financieras | Ninguna |
| Apps de salud | Ninguna |
| ID de publicidad | No lo usa (el manifiesto del AAB 1.1.0 (3) no trae `AD_ID`) |

## Te toca (Luis)

### Datos de inicio de sesión («Sign in details»)

Toda la app pide una cuenta. Play quiere unas credenciales que funcionen para su
revisión. Hace falta una persona de un cliente de prueba **en el entorno al que
apunta el build** (staging hoy, producción cuando se publique), con los módulos
que quieras enseñar. Texto propuesto para las instrucciones:

> La app es para los negocios clientes de Auphere. Entra con el correo y la
> contraseña de prueba. Verás Inicio, la Bandeja (conversaciones de WhatsApp de
> los clientes del negocio), Reservas y Consumo. No hace falta ningún código
> adicional.

El público objetivo (siguiente punto) no se puede empezar hasta guardar esta.

### Público objetivo y contenido

Edad: **18 y más** solamente. No está dirigida a niños. (Se habilita tras los
datos de inicio de sesión.)

### Seguridad de los datos («Data safety») — borrador para revisar

Es una declaración legal: revísala antes de enviarla.

- ¿Recoge o comparte datos? **Sí**. ¿Cifrados en tránsito? **Sí** (HTTPS).
  ¿Se puede pedir el borrado? **Sí**: Ajustes › «Solicitar el borrado de la
  cuenta» (y por correo a contacto@auphere.com).
- Datos recogidos (ninguno se «comparte» en el sentido de Play: lo que va a
  WhatsApp es el envío que pide el propio usuario):

| Tipo (Play) | Qué es en la app | ¿Obligatorio? | Para qué |
|---|---|---|---|
| Información personal › Nombre | Nombre de la persona que entra; nombres de clientes finales al crear una reserva | Sí | Funcionalidad, gestión de la cuenta |
| Información personal › Correo | Correo con el que entra | Sí | Gestión de la cuenta |
| Información personal › Teléfono | Teléfono del cliente final en una reserva | No | Funcionalidad |
| Mensajes › Otros mensajes en la app | Lo que se escribe a un cliente desde la Bandeja | No | Funcionalidad |
| Fotos y vídeos › Fotos | Imagen adjunta a un mensaje (galería o cámara) | No | Funcionalidad |
| Archivos y documentos | Documento adjunto a un mensaje | No | Funcionalidad |
| ID del dispositivo u otros | Token de avisos (APNs/FCM) del teléfono | No | Funcionalidad (avisos) |

Sin analítica ni informes de errores de terceros en la app (el proyecto de
Firebase se creó sin Google Analytics).

### A revisar en el manifiesto

El AAB pide `SYSTEM_ALERT_WINDOW`, `READ_EXTERNAL_STORAGE` y
`WRITE_EXTERNAL_STORAGE`, que vienen de dependencias. `SYSTEM_ALERT_WINDOW` no lo
usa la app; los de almacenamiento pueden hacer falta para elegir fotos en
Android antiguo. No bloquean la prueba interna; antes de producción conviene
revisarlos y quitar los que sobren con `android.blockedPermissions` en
`app.config.ts` (es un cambio de la app: con su spec).
