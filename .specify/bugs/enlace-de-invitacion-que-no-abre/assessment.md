# Bug Assessment: el panel enseña un enlace que no abre y calla el fallo de envío

- **Slug**: enlace-de-invitacion-que-no-abre
- **Created**: 2026-11-03
- **Source**: encargo de Luis, «soluciones estables y no parches en el alta de partners»; leído en el código y reproducido con pruebas contra `develop` (`09d579ef`). Es lo que la spec 052 deja fuera de alcance: «La invitación de personas de un cliente en el panel»
- **Verdict**: valid
- **Severity**: medium. Cuando el correo falla, que es justo cuando hace falta el enlace a mano, el operador recibe una ruta que no lleva a ningún sitio y un aviso que se va solo. Nadie queda sin acceso de forma irreversible: se puede reenviar

## Report

> `apps/admin/src/app/(dashboard)/tenants/[id]/access/invite-form.tsx` y `members-list.tsx` muestran `accept_path`, una ruta relativa (`/invite/<token>`), como el enlace para pasar a mano. Un envío fallido (`email_sent: false`) solo se avisa con un toast que desaparece. El endpoint está en `apps/api/src/nexus_api/api/admin/client_access.py`.

## Symptom

Tras invitar o reenviar a una persona del cliente, la pestaña Acceso enseña `/invite/<token>`: pegada en un mensaje no abre nada, y desde el panel apuntaría al panel. Si el correo no sale, el único aviso es un toast. Lo esperado: un enlace absoluto a la consola del entorno y un aviso de fallo que siga ahí.

## Reproduction

Con pruebas nuevas, en rojo contra el código sin arreglar:

1. `POST /admin/tenants/{id}/client-members`: la respuesta solo trae la ruta (`KeyError: 'accept_url'`), con el correo enviado y sin enviar. Lo mismo en `…/resend`.
2. En el panel, con `email_sent: false`: no hay ningún `role="alert"`, solo la llamada al toast. No aparece ningún campo con el enlace absoluto.

## Suspected Code Paths

- `apps/api/src/nexus_api/api/admin/client_access.py`: `ClientInvitationOut` solo devuelve `accept_path`. La dirección de la consola la conoce la API (`console_link`, la misma que usa el correo).
- `apps/admin/src/app/(dashboard)/tenants/[id]/access/invite-form.tsx` y `members-list.tsx`: pintan la ruta y confían el fallo al toast.

## Root Cause

Confianza alta, demostrada por los pasos 1 y 2.

El correo y la pantalla construyen el enlace por dos caminos. `send_client_invitation` lo hace absoluto con `console_link`; la respuesta se queda con la ruta y nadie la completa antes de pintarla. La consola sí la completa con su propio `origin`, porque ahí el origen es el suyo, y de ahí viene el contrato; el panel vive en otro host y copió la forma sin el arreglo.

**Hay un segundo fallo que el encargo no nombra.** Cada componente guarda su propio último enlace. Si la invitación falla en el formulario y luego se pulsa «Reenviar» en la lista, se ven los dos enlaces, y el del formulario ya está muerto porque reenviar lo retira. Con un aviso que no desaparece esto empeoraría, así que hay que resolverlo a la vez.

## Proposed Remediation

**Preferred**:

1. **API**: `ClientInvitationOut` añade `accept_url`, construido con `console_link`, en invitar y en reenviar. Es la misma función que usa el correo, de modo que lo que se pasa a mano y lo que se envía no pueden divergir, y su origen es `NEXUS_CONSOLE_BASE_URL`, que producción ya exige que no sea `localhost`. `accept_path` se queda en la respuesta: un despliegue puede dejar un rato el panel anterior delante de la API nueva, y varias pruebas lo usan.
2. **Panel**: un único estado de avisos, en un `PeopleSection` que envuelve formulario y lista. Un aviso por dirección: un enlace nuevo sustituye al anterior, y revocar lo retira, porque en ambos casos el enlace anterior está muerto. Invitar a otra persona no borra el aviso de la primera.
3. **El aviso** usa `Callout` de `@nexus/ui`, sus tonos y sus tokens: `warning`, con `role="alert"`, si el correo no salió; `positive`, con `role="status"`, si salió. Solo se va si el operador lo cierra, si se sustituye o si se revoca. Sin toast en el fallo. Con el correo enviado se mantiene el toast, porque es lo que anuncia de forma fiable a un lector de pantalla un `role="status"` insertado con contenido.
4. **El enlace queda fuera de la región viva**, en un campo de solo lectura con botón de copiar, para que el lector de pantalla no deletree el token. El foco visible viene de `Input` y `Button`.
5. **El token no toca la dirección del panel**: todo vive en estado de React y la respuesta de la acción de servidor; nada de `router.push`, `replace` ni parámetros de consulta.

**Alternatives**:

- Construir el enlace en el panel con `CONSOLE_URL` (`consoleHref`): dos fuentes para lo mismo, una en la API y otra en una variable del panel. Si divergen, el operador pasaría un enlace distinto al del correo. Descartado.
- Quitar `accept_path` de la respuesta: rompería al panel anterior durante un despliegue. Sin beneficio. Descartado; en el tipo del panel sí se quita, para que nadie vuelva a pintarlo.
- Un diálogo modal, como el de la clave de API: bloquea seguir invitando a otras personas, y aquí perder el enlace no es irreversible, porque se reenvía. Descartado.
- Guardar el resultado del envío en la invitación, con migración, para que el aviso sobreviva a recargar: es lo que hace la spec 052 para el propietario (R2.5). Aquí pediría una columna y una migración que el encargo no pide, y el enlace tampoco se podría volver a mostrar. Queda como posible mejora y el aviso avisa de ello.

**Files likely to change**:

- `apps/api/src/nexus_api/api/admin/client_access.py`
- `apps/admin/src/lib/backend.ts`
- `apps/admin/src/app/(dashboard)/tenants/[id]/access/{invite-form,members-list,page}.tsx`, y nuevos `people-section.tsx` e `invitation-notices.tsx`
- `docs/consola-lite.md`

**Tests to add or update**:

- `apps/api/tests/unit/test_admin_client_members.py`: enlace absoluto igual al del correo, al invitar y reenviar, con el correo enviado y sin enviar.
- `apps/admin/.../access/__tests__/people-section.test.tsx`: enlace absoluto, alerta sin toast, permanencia con el tiempo y tras refrescar, cierre explícito, sustitución al reenviar, retirada al revocar, varias personas, token fuera de la dirección y de la región viva, copia con teclado y fallo de copia.

## Risks & Considerations

- **El enlace es un secreto de un solo uso**: ya salía en la respuesta como ruta; no se añade superficie. Sigue sin ir a la auditoría ni a los registros.
- **Aislamiento**: sin cambios. La ruta toma el cliente del path y exige operador; solo cambia cómo se forma una cadena en la respuesta.
- **Recargar pierde el aviso.** Es inevitable sin migración, y por eso el texto lo dice: el enlace no se volverá a mostrar y, si se recarga, hay que reenviar. Otro operador que abra la ficha tampoco verá que el correo falló.

## Open Questions

Ninguna.
