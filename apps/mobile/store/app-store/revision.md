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

La segunda frase del segundo párrafo solo se pega si la cuenta de revisión cumple eso. Si no, se quita: Apple prueba lo que se le dice. **El 2026-11-21 se pegó sin ella**, porque la cuenta de revisión aún no existe; se añade cuando exista y cumpla.

## Privacidad de la app (App Privacy)

Mismo inventario que la sección «Seguridad de los datos» de Play (`../play/app-content.md`). Si cambia uno, cambia el otro.

- **¿Se usan datos para rastrear?** No. La app no tiene anuncios, analítica ni informes de errores de terceros, y no lee el identificador de publicidad.
- **Datos vinculados a la persona**, todos con la finalidad «Funcionalidad de la app» (App Functionality):

| Categoría de Apple | Tipo | Qué es en la app |
|---|---|---|
| Contact Info | Name | El nombre de quien entra y el de los clientes a los que reserva |
| Contact Info | Email Address | El correo con el que entra |
| Contact Info | Phone Number | El teléfono del cliente al crear una reserva |
| User Content | Emails or Text Messages | Los mensajes que escribe a sus clientes desde la Bandeja |
| User Content | Photos or Videos | Una foto o imagen enviada a un cliente desde la Bandeja |
| User Content | Other User Content | Los archivos que envía a sus clientes |
| Identifiers | User ID | El identificador de su cuenta de Auphere |
| Identifiers | Device ID | El token de avisos del teléfono y el identificador que usa el servicio de actualizaciones de Expo |

- **No se recogen**: ubicación, salud, datos financieros, contactos del teléfono, historial de navegación, historial de búsqueda, audio ni diagnósticos.
- **Publicada en App Store Connect el 2026-11-21**, tal como está esta tabla. Los mensajes van como «Emails or Text Messages», que Apple define como el contenido y los destinatarios de un mensaje; los archivos, como «Other User Content».
- El manifiesto de privacidad (`PrivacyInfo.xcprivacy`) del build 4 de TestFlight declara las razones de uso de `UserDefaults`, marcas de tiempo de archivos y hora de arranque, y `NSPrivacyTracking: false`, pero su lista de datos recogidos (`NSPrivacyCollectedDataTypes`) está vacía. Hay que alinearla con esta tabla: es un cambio de la app y va en su spec (`../README.md`).

## Clasificación por edad

Respuestas dadas en App Store Connect el 2026-11-21, con las definiciones de Apple a la vista. Apple calcula la edad a partir de ellas: **4+** (A12 en Brasil, ALL en Corea, 00+ en Vietnam), sin subirla a mano.

| Pregunta de Apple | Respuesta |
|---|---|
| Parental Controls, Age Assurance | No |
| Unrestricted Web Access | No. Solo abre en el navegador la consola de Auphere y la política de privacidad |
| User-Generated Content («broad distribution of content created by users») | No. Los mensajes van de un cliente al negocio; no se difunden a otros usuarios |
| Social Media, Shared Location, Advertising | No |
| Messaging and Chat («users can directly communicate with one another») | Sí: la persona del negocio escribe a sus clientes |
| Temas maduros, sexo, desnudez, violencia | Ninguno |
| Medical or Treatment Information, Health or Wellness Topics | No. La app no da información médica, aunque la use una clínica |
| Juegos de azar, concursos, cajas de botín | No |

Play está clasificada IARC 12+ por «los usuarios interactúan»: los cuestionarios son distintos y no tienen por qué coincidir.

## Cifrado

`ITSAppUsesNonExemptEncryption: false` en el `Info.plist`: la app solo usa el TLS del sistema. App Store Connect no pide documentación de exportación.
