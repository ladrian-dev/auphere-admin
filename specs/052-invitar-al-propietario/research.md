# Investigación: Invitar al propietario

Decisiones de diseño, comprobadas contra el código de `develop` (`09d579ef`).

## R1 · Qué es una invitación de Auphere

**Decisión**: rol `owner` e `invited_by IS NULL`, sin columna nueva.

**Por qué**: es la definición de la spec («una invitación de rol propietario que no emitió ninguna persona del partner»), y ya lo cumplen las del script. El alta autónoma también crea una así, pero la acepta en la misma transacción, de modo que nunca está viva.

**Límite conocido**: `invited_by` es `ON DELETE SET NULL`. Una invitación de propietario emitida por una persona del partner que después sale del equipo pasa a parecer de Auphere. Es raro, y el daño es que el operador pueda reenviarla o revocarla, cosa que ya puede pedir. No compensa una columna.

**Descartado**: `issued_by_operator` u otra columna de origen. Solo distinguiría ese caso, y no sabría qué valor dar a las filas que ya existen.

## R2 · Cómo se garantiza una sola invitación viva

**Decisión**: `SELECT … FOR NO KEY UPDATE` sobre la fila del partner al principio de invitar y reenviar.

**Por qué**: R3.5 exige una por partner, a cualquier dirección, «incluso con dos peticiones simultáneas», y el índice único existente es por `(partner_id, email)`. El segundo que entra espera y, ya con el bloqueo, ve la fila del primero.

- **`FOR NO KEY UPDATE`, no `FOR UPDATE`**: aceptar inserta una pertenencia con FK a `partners`, que toma `FOR KEY SHARE`. Con `FOR UPDATE` sobre el partner, reenviar y aceptar a la vez podrían interbloquearse. `with_for_update(key_share=True)`.
- **Descartado un índice único parcial por `partner_id`**: no se puede crear sin más sobre datos de producción, donde el script ha podido dejar dos, y una fila vencida sin marcar haría fallar la inserción. El índice no aportaría nada que el bloqueo no dé.

## R3 · Vencidas sin marcar (R3.9)

**Decisión**: toda lectura usa `invitation_is_live_clause(now)`; `invite` además marca `expired` las vencidas del partner antes de crear.

**Por qué**: el índice único parcial mira `status = 'pending'`, así que una fila vencida sin marcar impediría reinvitar a esa dirección. Marcarla es decir la verdad sobre ella, sea quien sea quien la emitió.

`invitation_is_live_clause` se escribe con esa firma exacta porque la rama `fix/invitaciones-vencidas-y-enlace` expone la misma; se unifican al fusionar. No se cambia la firma de `create`, `list_pending` ni `get_pending_by_token`.

## R4 · Qué dirección se valida y cómo (R1.3, R3.8, R1.5)

**Decisión**: forma con la misma expresión que `api/admin/client_access.py`, recortada y en minúsculas; **no** `EmailStr`.

**Por qué**: `EmailStr` rechaza dominios de uso especial, y la prueba de verdad es que el enlace llega. Sin espacios no hay inyección de cabeceras.

Para saber dónde vive una dirección se mira la pertenencia por **dos** vías: la cuenta (`console_auth.principals` → `user_id`), que es lo que `accept` comprueba, y la copia del correo en la pertenencia, porque hay filas con `user_id` antiguos que no son una cuenta. Las pertenencias de cliente cuentan estén o no activas, porque `accept` tampoco las distingue.

`client_memberships` no es tabla de tenant: `test_21_rls_covers_every_tenant_table.py` la declara identidad, sin política, leída antes de que exista ámbito. El enforcer de aislamiento tampoco la cubre. Leerla no incumple R7.5.

**«Tabla de tenant» en R7.5** es, para la prueba, una tabla con RLS activa según el catálogo de Postgres (`pg_class.relrowsecurity`), no una lista escrita a mano. Las excepciones son `audit_log` y `embed_audit_log`: lo que esta spec escribe ahí son filas de plataforma, con `tenant_id` nulo (Entidades clave), y la prueba lo comprueba fila a fila.

**§V** dice que no hay «pantalla que explique lo que no tienes». R3.6 y R3.7 piden decir por qué no se puede invitar. No chocan: es el panel de operador, el estado se resuelve desde ahí, con su enlace, y no hay botón apagado.

## R5 · El resultado del envío

**Decisión**: `deliver` envuelve `send_template` en `try/except Exception` y `asyncio.wait_for(25 s)`; `email_sent` es lo que devolvió. `last_sent_at` se escribe en una transacción aparte, solo si salió.

**Por qué**:

- `send_template` solo captura `httpx.HTTPError`. R2.3 incluye «un error interno».
- El `timeout=20` de `httpx` es por fase: conexión, escritura y lectura pueden sumar 60 s. CE-002 pide menos de 30 s.
- Si falla apuntar la fecha después de que el correo saliera, la respuesta sigue diciendo que salió y lleva el enlace; la ficha dirá «no consta», que es verdad desde el punto de vista de la base. Perder el enlace por esto sería peor.
- Un correo retenido por el modo del entorno cuenta como enviado (spec 051, R1.2): `send_template` devuelve `True`.

**Asunto**: `{inviter} te ha invitado a unirte a {partner} en Auphere`, con «Auphere» de quien invita, se leería «Auphere te ha invitado a unirte a Acme en Auphere». Aquí es «Auphere te ha invitado a unirte a Acme». La plantilla no cambia.

## R6 · Reenviar crea otra fila

**Decisión**: la anterior pasa a `revoked` y nace otra, en una transacción. Primero se revoca, con `flush`, porque el índice parcial no admite dos `pending` de la misma dirección.

**Por qué**: es D5. Solo se guarda el hash, así que no hay nada que reenviar. La fila nueva tiene otro `id`: la vista de resultado reintenta sobre el `id` que recibió.

Toca también el contacto (R1.10): si está vacío, se rellena; si es la misma dirección, no cambia.

**A qué invitación sustituye una invitación nueva** (R1.10, Historia 3 escenario 3): a la última de Auphere del partner, si está revocada o caducada. Una aceptada no se sustituye: esa persona ya entró, y que hoy no esté no hace suyo el contacto.

**Decisiones que salen de `/speckit-analyze`**, ninguna contradice la spec:

- **`resend` repite la comprobación de la dirección.** La spec permite dos invitaciones vivas en dos partners, y gana la primera que acepte. Reenviar la perdedora mandaría un enlace que falla al aceptarlo, que es justo lo que R1.5 evita. Se rechaza con la misma negativa, sin tocar el enlace.
- **`revoke` devuelve `changed`.** R5.4 pide éxito al revocar una ya revocada. Si otro operador acaba de reenviar, esa fila vieja está revocada y hay otra viva: decir «el enlace ya no sirve» sería falso.
- **Revocar una caducada** es éxito sin cambio, igual que una revocada: el enlace ya no abre, que es lo que se pedía.

## R7 · La auditoría se lee en el panel (R6.4)

**Hallazgo**: la spec da por hecho que el panel enseña la auditoría, pero la pestaña Auditoría de la ficha solo lee `embed_audit_events` (`GET /admin/partners/{id}/audit`), y ninguna otra pantalla lee las filas de plataforma de un partner. Con solo añadir el vocabulario, nada de esta spec se vería en el panel.

**Decisión**: `GET /admin/partners/{id}/audit-log`, con las filas `tenant_id IS NULL AND target = 'partner:{id}'`, la frase de `summarise()` y el operador por su correo. La consola sigue diciendo «Auphere» (`_human_actor`). Es una tarjeta más en la pestaña, encima de la de actividad del embed. La frase es lo único que sale: ni `before_json` ni `after_json`.

## R8 · Qué se autentica

**Decisión**: `require_enabled_operator` para las acciones de esta spec, y una comprobación equivalente en las acciones de servidor del panel.

**Hallazgo**: `require_operator` acepta una cuenta con `disabled_at` pasado, y `requireOperator()` del panel también («entra igual y es el layout el que enseña sin acceso»). Una cuenta deshabilitada con la cookie viva puede llamar a una acción de servidor. R6.3 pide un operador válido, así que aquí se rechaza. Las demás rutas de operador siguen como están: queda anotado para quien decida cambiarlo en todas.

## R9 · El enlace en el panel (R6.6)

**Decisión**: el resultado vive en estado de cliente. El alta no navega: `/partners/new` pinta la vista en el sitio del formulario y la salida es un enlace a la ficha.

El estado está en un padre estable, no en el formulario que desaparece, y mientras haya un enlace en pantalla no se refresca nada (R10).

**Descartado** navegar a `/partners/{id}/team?…`: pondría el resultado a merced de la URL. Un `sessionStorage` tampoco: el enlace es un secreto y no debe quedarse en el navegador.

## R10 · Lo que salió de la revisión independiente del código

Una revisión a ciegas del diff, antes de cerrar, encontró cinco cosas que las pruebas no veían. Resueltas:

- **El token llegaba a los registros de producción.** No por el envío, sino al abrir el enlace: va en la ruta de `/console/invitations/{token}`, y eso lo escribían la línea de acceso de `uvicorn`, el `path` de cada línea de la petición y el span. Es anterior a esta spec, pero CE-005 promete lo contrario. **Decisión:** `core/logging_context.safe_path` quita de los tres cualquier tramo con forma de token; por la forma y no por una lista, para que una ruta nueva quede cubierta. Una prueba barre las rutas con `{token}`. Cubre también el alta y restablecer la contraseña. Queda fuera el registro de peticiones de Vercel, que ve `/invite/<token>` y no pasa por esta API.
- **Revalidar podía llevarse el enlace.** `revalidatePath` repinta la página en la respuesta de la acción, y si esa lectura falla la pestaña se desmonta con el único ejemplar. **Decisión:** las acciones no revalidan. El cliente refresca cuando no queda ningún enlace en pantalla, y la vista de resultado sustituye a las filas, para que una negativa en otra fila tampoco pueda quitarlo. A cambio, la cabecera de la ficha se queda atrás hasta que el operador pulsa «Entendido».
- **Un reintento con la respuesta perdida dejaba en pantalla un enlace que quizá estaba muerto.** Ahora el enlace se retira y se manda a Equipo.
- **El panel firmaba como «Auphere» las acciones de las personas del partner.** Ahora solo el operador se nombra por su correo, y lo demás se traduce como en la consola.
- **El filtro «Auphere» de la consola no encontraba al operador.** Filtraba por `admin:`, y `partner.create` pasa a escribir `operator:`. Se corrige en el filtro, y arregla también las filas de las specs 030 y 032.

Se queda como está, por lo dicho en R1: una invitación de propietario emitida por una persona que luego sale del equipo parece de Auphere.

## R11 · Lo que no se toca

- **Consola del partner**: `/console/team` sigue igual, con el mismo defecto de vencidas sin marcar (fuera de alcance en la spec).
- **Plantilla**: `auphere-team-invite-{es,en}`, sin cambios.
- **Cobro**: nada. El correo no gasta saldo.
