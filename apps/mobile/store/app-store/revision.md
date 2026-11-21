# Revisión del App Store — Auphere Customers 1.3.0

Lo que App Store Connect pide además de la ficha (`ficha.md`): la información para App Review, la privacidad y la clasificación por edad. Las respuestas se apoyan en lo que hace el build 1.3.0, no en lo que hará.

**Aquí no van credenciales.** La cuenta de revisión se escribe solo en App Store Connect y en Play Console.

## Información para App Review

| Campo | Valor |
|---|---|
| Requiere iniciar sesión | Sí |
| Usuario y contraseña | **Lo pone Luis**: la cuenta de revisión en producción (ver `../README.md`, «Antes de enviar») |
| Nombre, teléfono y correo de contacto | **Lo pone Luis**: quien atiende a Apple si llama |
| Archivo adjunto | Ninguno |

### Notas (en inglés, para pegar)

> Auphere Customers is the companion app for businesses that use Auphere, a managed service that runs an AI agent on the business's WhatsApp, Instagram and Messenger channels. Accounts are issued by Auphere or by the company that manages the business's agent. The app has no sign-up and sells nothing.
>
> The review account belongs to a demo business set up for App Review. Its conversations are test conversations: replying from the app does not reach real people.
>
> Suggested path:
> 1. Home shows today's bookings, recent conversations and the balance.
> 2. Inbox: open a conversation marked "Waiting for a person" and tap "Answer" to reply as the business. "Give back" returns the conversation to the agent.
> 3. Bookings shows the day's schedule. Tap a booking to confirm, move or cancel it.
> 4. Usage shows the balance and the spend. The balance is part of the business's service agreement with Auphere and cannot be bought in the app. The link to the Auphere web console opens the same usage, read-only for this account; nothing can be bought there either.
>
> Sign in with Apple: the app signs in with email and password, or with Google for businesses whose accounts are Google accounts. Every account is issued by the business's organization, so the app falls under the exception in guideline 4.8 for business apps that require an existing enterprise account.
>
> Account deletion: Settings > "Request account deletion". Auphere confirms the request by email and deletes the account and its personal data within one month at most.

La segunda frase del segundo párrafo solo se pega si la cuenta de revisión cumple eso. Si no, se quita: Apple prueba lo que se le dice.

## Privacidad de la app (App Privacy)

Mismo inventario que la sección «Seguridad de los datos» de Play (`../play/app-content.md`). Si cambia uno, cambia el otro.

- **¿Se usan datos para rastrear?** No. La app no tiene anuncios, analítica ni informes de errores de terceros, y no lee el identificador de publicidad.
- **Datos vinculados a la persona**, todos con la finalidad «Funcionalidad de la app» (App Functionality):

| Categoría de Apple | Tipo | Qué es en la app |
|---|---|---|
| Contact Info | Name | El nombre de quien entra y el de los clientes a los que reserva |
| Contact Info | Email Address | El correo con el que entra |
| Contact Info | Phone Number | El teléfono del cliente al crear una reserva |
| User Content | Photos or Videos | Una foto o imagen enviada a un cliente desde la Bandeja |
| User Content | Other User Content | Los mensajes que escribe a sus clientes y los archivos que les envía |
| Identifiers | User ID | El identificador de su cuenta de Auphere |
| Identifiers | Device ID | El token de avisos del teléfono y el identificador que usa el servicio de actualizaciones de Expo |

- **No se recogen**: ubicación, salud, datos financieros, contactos del teléfono, historial de navegación, historial de búsqueda, audio ni diagnósticos.
- El manifiesto de privacidad (`PrivacyInfo.xcprivacy`) del build 4 de TestFlight declara las razones de uso de `UserDefaults`, marcas de tiempo de archivos y hora de arranque, y `NSPrivacyTracking: false`, pero su lista de datos recogidos (`NSPrivacyCollectedDataTypes`) está vacía. Hay que alinearla con esta tabla: es un cambio de la app y va en su spec (`../README.md`).

## Clasificación por edad

Respuestas al cuestionario de App Store Connect. Apple calcula la edad a partir de ellas; no se elige.

| Tema | Respuesta |
|---|---|
| Violencia, sexo, desnudez, lenguaje soez, drogas, alcohol, tabaco, terror, temas maduros | Ninguno |
| Información médica o de tratamientos | No. La app no da información médica, aunque la use una clínica |
| Juegos de azar, concursos | No |
| Acceso a la web sin restricciones | No. Solo abre en el navegador la consola de Auphere y la política de privacidad |
| Mensajería o chat entre usuarios | Sí: la persona del negocio escribe a sus clientes |
| Contenido generado por usuarios | Sí: los mensajes de los clientes del negocio |
| Anuncios | No |
| Controles parentales o verificación de edad | No |

Play ya está clasificada (IARC 12+ y equivalentes) por «los usuarios interactúan». Es de esperar que Apple llegue a algo parecido por la mensajería.

## Cifrado

`ITSAppUsesNonExemptEncryption: false` en el `Info.plist`: la app solo usa el TLS del sistema. App Store Connect no pide documentación de exportación.
