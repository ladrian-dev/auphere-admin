# Preparación de las tiendas — spec 031 (T109)

Estado al 2026-10-20. Lo marcado ☐ necesita al dueño de las cuentas.

## Hecho en el repo

- ☑ `apps/mobile/eas.json`: perfiles `development` (cliente de desarrollo,
  `com.auphere.customers.dev`), `preview` (staging) y `production`, cada uno
  con su canal de `expo-updates` y sus URLs de API y consola. `runtimeVersion`
  sigue la versión de la app (D19: por aire, solo arreglos).
- ☑ `app.config.ts`: `com.auphere.customers`, esquema `auphere-customers`,
  entitlement `time-sensitive`, textos de cámara y galería en ES y EN
  (`locales/`), permisos de micrófono y ubicación bloqueados en Android,
  `ITSAppUsesNonExemptEncryption: false` (solo TLS del sistema).
- ☑ Icono, icono adaptativo y monocromo de Android, icono de avisos y splash,
  desde el `BrandMark` de `@nexus/ui`.

## Borradores para las fichas (de la lectura de RGPD de la KB)

**Política de privacidad**, párrafo nuevo
(`kb/Auphere/nexus/compliance/2026-10-19-avisos-del-telefono.md`):

> «Si usas la app Auphere Customers y activas los avisos, enviamos a Apple o a
> Google, según tu teléfono, el aviso que ves: el nombre del contacto y un texto
> corto. Lo hacen como encargados del tratamiento, solo para entregarlo.»

**App Store — App Privacy** (Data Linked to You; nada para *Tracking*):

| Tipo | Para qué |
|---|---|
| Contact Info → Email Address, Name | Funcionalidad de la app (entrar, Ajustes) |
| User Content → Other User Content (mensajes de WhatsApp de la Bandeja, notas, etiquetas) | Funcionalidad de la app |
| Identifiers → Device ID (destino de avisos e identificador de instalación) | Funcionalidad de la app (avisos, cerrar un teléfono) |

Sin analítica, sin publicidad, sin SDK de terceros de errores (D20).

**Google Play — Data safety**: las mismas categorías (Información personal:
correo y nombre; Mensajes: otros mensajes de la app; IDs del dispositivo).
Cifrados en tránsito. No se comparten (Apple y Google entregan los avisos como
encargados). La persona puede pedir el borrado de su cuenta desde la app
(Ajustes → «Solicitar el borrado de la cuenta», R11.4).

## Pendiente del dueño

- ☐ El App ID `com.auphere.customers` en el team de FACELAD con Push
  Notifications y Time Sensitive Notifications; la clave APNs `.p8`; una API
  key **nueva** de App Store Connect para EAS (T004).
- ☐ La app en Google Play Console y el proyecto de Firebase con su cuenta de
  servicio de FCM (`fcm_project_id`, `fcm_service_account_json`) y su
  `google-services.json` como secreto de archivo de EAS.
- ☐ `eas init` con la cuenta de Expo de FACELAD (`EAS_PROJECT_ID`, `EAS_OWNER`).
- ☐ Publicar el párrafo en la política de privacidad y revisar los borradores
  con un abogado.
- ☐ El cliente de demostración en producción bajo Auphere Internal Partner,
  con una cuenta de revisión para Apple y Google. **Su Bandeja no puede enviar
  WhatsApp a personas reales**: un número de prueba de Meta sin destinatarios
  reales; si hiciera falta código para garantizarlo, va en su propia spec.
