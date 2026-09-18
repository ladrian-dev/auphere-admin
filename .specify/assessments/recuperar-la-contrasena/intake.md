# Idea Intake: recuperar la contraseña

- **Slug**: recuperar-la-contrasena
- **Created**: 2026-09-18
- **Source**: sesión del 2026-09-18 (Luis pidió restablecer la clave de
  `contacto@auphere.com` en producción para poder entrar) · puntero al
  repositorio: `apps/api/src/nexus_api/services/console_identity.py`,
  `apps/api/src/nexus_api/api/console/auth.py`,
  `apps/console/src/app/(auth)/login/`
- **Type**: gap (una capacidad que el producto promete y no tiene)

## Lo que pasó

Luis no podía entrar en producción con su cuenta y pidió que se le
restableciera la contraseña. **No hay forma de hacerlo dentro del producto.**

## Lo que existe y lo que no

| Pieza | Estado |
|---|---|
| `set_password(session, account, password)` | **Existe**, en `services/console_identity.py:294`, con validación y desbloqueo de intentos |
| Ruta de la API que la llame para restablecer | **No existe**. `api/console/auth.py` tiene `login`, `session` y `logout`, nada más |
| Flujo «he olvidado mi contraseña» en la consola | **No existe** |
| Lo que la persona ve en `/login` | «¿Has olvidado la contraseña? **Escríbenos**», sin enlace ni dirección |

El anexo 04 de la evaluación `experiencia-app-escritorio` ya lo había marcado
como callejón sin salida (`[EX][CS]`) el 2026-09-17, sin desarrollar.

## Por qué importa más de lo que parece

Hoy la única salida es que alguien con acceso a la base de datos de producción
escriba el `password_hash` a mano. Eso significa tres cosas:

1. **No escala**: cada partner que pierda su contraseña es una intervención
   manual de alguien del equipo, con acceso a producción.
2. **Empuja a la mala práctica**: la contraseña nueva viaja por el canal que
   haya —un chat, un correo— para que alguien la meta. En esta misma sesión pasó:
   la clave se escribió en un chat antes de que nadie mirara si había otra vía.
3. **El producto promete ayuda y no la da**: «escríbenos» sin dirección es peor
   que no decir nada, porque parece una salida.

## Lo que hay que decidir, no dar por hecho

- **Si hace falta contraseña.** Existe entrada con Google
  (`api/console/auth_google.py`), y `resolve_provider_identity` enlaza por
  correo con una cuenta ya creada. Un producto que solo entra por proveedor
  externo no necesita recuperación de contraseña — necesita no tener contraseñas.
- Si se queda: enlace por correo con caducidad corta y un solo uso, y qué pasa
  con las sesiones vivas al cambiarla.
- Qué ve quien pide el restablecimiento de un correo que no existe (no se puede
  confirmar ni desmentir que la cuenta exista).
- Cómo interactúa con el bloqueo por intentos fallidos (`locked_until`).
- Si el restablecimiento invalida la credencial de las máquinas emparejadas.

## Superficie de confianza

Toca autenticación: superficie `0` y `3a`. Cualquier cosa aquí necesita su
modelo de amenaza escrito **antes** del código, y test de aislamiento.

## Fuera de alcance

Cambiar la contraseña estando dentro (eso es otra cosa y hoy tampoco existe;
merece su propia línea, pero no es lo que bloquea a nadie).
