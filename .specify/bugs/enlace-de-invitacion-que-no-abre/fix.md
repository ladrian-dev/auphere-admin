# Bug Fix: el panel enseña un enlace que no abre y calla el fallo de envío

- **Slug**: enlace-de-invitacion-que-no-abre
- **Fixed**: 2026-11-03
- **Assessment**: ./assessment.md
- **Status**: applied

## Summary

La API devuelve `accept_url`, construido con `console_link`, igual que el correo. La pestaña Acceso tiene un único estado de avisos: un aviso por dirección, que no se va solo, con el enlace absoluto para copiar. Un envío fallido es una alerta, no un toast.

## Changes

| File | Change | Notes |
|------|--------|-------|
| `apps/api/src/nexus_api/api/admin/client_access.py` | modified | `accept_url`, y `_invitation_out` compartido por invitar y reenviar |
| `apps/admin/src/lib/backend.ts` | modified | El tipo lleva `accept_url` y deja de llevar `accept_path`, para que nadie vuelva a pintarlo |
| `apps/admin/src/app/(dashboard)/tenants/[id]/access/people-section.tsx` | added | Los avisos viven aquí, por encima de formulario y lista |
| `…/access/invitation-notices.tsx` | added | `Callout` de `@nexus/ui`, y el enlace en un campo de solo lectura fuera de la región viva |
| `…/access/invite-form.tsx`, `members-list.tsx`, `page.tsx` | modified | Sueltan su enlace propio y avisan por `onInvited`, `onResent` y `onRevoked` |
| `…/access/__tests__/access-form.test.tsx`, `phones-list.test.tsx` | modified | `MembersList` pide las dos propiedades nuevas |
| `docs/consola-lite.md` | modified | Spec viva |

## Tests Added or Updated

- `apps/api/tests/unit/test_admin_client_members.py::test_invite_and_resend_answer_the_absolute_link_the_email_carries[sent|not_sent]`: el enlace es absoluto, sale de `NEXUS_CONSOLE_BASE_URL`, coincide con el del correo y abre, con el correo enviado y sin enviar.
- `apps/admin/.../access/__tests__/people-section.test.tsx`, 13 casos: enlace absoluto y nunca la ruta; alerta sin toast; el token fuera de la región viva; permanencia con el tiempo y tras refrescar; solo se va al cerrarla; invitar a otra persona no borra la primera; reenviar sustituye; un reenvío fallido también alerta; revocar retira; una negativa de la API no crea aviso; el token nunca toca la dirección; copiar con teclado; fallo al copiar.

## Local Verification

- En rojo antes del arreglo: 2 fallos en la API (`KeyError: 'accept_url'`) y 12 de 13 en el panel (sin `role="alert"` ni enlace absoluto). El caso que pasaba es el de la negativa de la API, que no cambia.
- En verde después: ver `./test.md`.

## Deviations from Assessment

- `access-form.test.tsx` y `phones-list.test.tsx` no estaban en la lista de archivos: `pnpm typecheck` los señaló porque renderizan `MembersList`.

## Follow-ups

- **Texto muy largo en la tabla de personas**: con una dirección de 100 caracteres, la tabla hace scroll horizontal y «Reenviar» queda fuera de vista hasta desplazarse. `truncate` no recorta sin `table-fixed`. Ya pasaba antes y no se ha tocado.
- **Recargar pierde el aviso**, y otro operador no ve que el correo falló. Arreglarlo pide guardar la fecha del último envío, como hace la spec 052 para el propietario.
- `accept_path` puede salir de la respuesta cuando ya no haya un panel anterior desplegado; varias pruebas lo usan para sacar el token.
