# Decision: recuperar la contraseña

- **Slug**: recuperar-la-contrasena
- **Decided**: 2026-09-22
- **Verdict**: **go** — Opción A, con tres decisiones tomadas en esta puerta
- **Artifacts reviewed**: [`intake.md`](./intake.md) · [`research.md`](./research.md)
  · [`problem.md`](./problem.md) · [`concept.md`](./concept.md)
- **Superficie de confianza (§II)**: `0` (API de la consola) y `3a` solo si se
  decide que restablecer revoca credenciales de máquina (D-3). **No abre
  superficie nueva**: el correo ya es autoridad de la cuenta hoy, por Google.

---

## Scorecard

| Criterio | Valoración | Justificación |
|---|---|---|
| **Validez del problema** | **strong** | No es hipótesis: ocurrió el 2026-09-18 y se resolvió escribiendo el hash a mano en producción, con la contraseña nueva viajando por un chat. El producto además promete una salida sin destino (`messages.ts:166`) |
| **Fuerza de la evidencia** | **strong** | Todo es lectura de este repositorio con ruta y línea, y los tres hallazgos que cambian la forma se verificaron a mano contra el código, no contra el informe del barrido |
| **Valor frente a no hacer nada** | **strong** | No hacer nada no es «más lento»: es un procedimiento manual con acceso a producción, recurrente, y que ya empujó a una mala práctica una vez |
| **Viabilidad / apetito** | **strong** | Todas las piezas tienen precedente vivo: dos patrones de token de un solo uso en producción, el límite reutilizable, el envío de correo, cuatro pantallas hermanas en `(auth)/`. Lo único nuevo de verdad es la revocación en bloque, y es una sentencia |
| **Encaje estratégico** | **strong** | §II se cumple de frente: agota valor dentro de una superficie ya pagada. El correo **ya** decide quién entra (`identity_link.py:72-90`); esto lo usa, no lo abre |
| **Postura de riesgo** | **adequate** | Dos riesgos con dueño: la fiabilidad real de Resend en producción (sin medir) y el hecho de que la respuesta uniforme obliga a que un fallo de envío sea invisible para la persona. No es `strong` porque el camino feliz depende de un envío que no lanza excepciones |

---

## Verdict & Rationale

**Go, Opción A.** Un enlace de un solo uso por correo, con la contraseña
manteniéndose como credencial.

El argumento que lo decide no es el del intake —«falta una capacidad»— sino el
que apareció al leer el código: **el correo ya es la autoridad de esta cuenta y
nadie lo decidió.** Quien tiene el correo verificado en Google entra hoy sin dar
la contraseña. Eso significa que un enlace por correo **no abre una superficie
nueva**: usa la que ya decide, y la usa para el partner que hoy queda fuera —el
de correo propio de dominio, que es el cliente real de Auphere.

Se rechaza la Opción B (retirar las contraseñas) siendo **mejor idea**, y
conviene que quede escrito por qué, porque volverá: toca la ruta por la que
entra todo el mundo para resolver el problema de quien olvida su contraseña;
`password_hash` es NOT NULL y su retirada es migración de datos sobre la tabla
de identidad; y pone el correo en el camino crítico de cada entrada cuando
`send_email` **no lanza, devuelve `False`** y en local está apagado. La Opción A
construye la mitad de la maquinaria de B —token de un solo uso, pantalla de
canje, límites— sin comprometer el camino de todos.

Se rechaza la C porque deja fuera al partner sin Google, que es el caso real.

---

## Las cuatro decisiones que esta puerta toma

Las tres primeras se tomaron con el expediente; la cuarta la cerró Luis el mismo
día al contestar la pregunta cruzada.

**D-1 · Restablecer cierra todas las demás sesiones, y eso entra en el
alcance.**

Hoy es **imposible**: no existe ningún `DELETE` sobre `ConsoleSession` por
`principal_id`. La spec que salga de aquí lo construye.

No es una mejora opcional. La mitad de los motivos para recuperar una contraseña
no son «se me olvidó» sino «creo que alguien entró», y para ése, restablecer sin
cerrar sesiones **no arregla nada** y además da por resuelto lo que no lo está:
el intruso sigue dentro con su cookie siete días. Una capacidad que parece
resolver algo que no resuelve es peor que su ausencia.

**D-2 · El texto de `login.forgot` se arregla ya, no con la spec.**

Hoy dice «¿Has olvidado la contraseña? Escríbenos» sin `href`, sin `mailto`, sin
destino, mientras el botón de Google dos centímetros más arriba habría dejado
entrar a media base de partners. Es **cambio trivial** en el sentido del método
(`docs/spec-driven-development.md` §2): una cadena de i18n, sin cambio de
comportamiento. No espera a la spec.

Lo que diga mientras tanto tiene que ser verdad: que se entre con Google si el
correo coincide, y a quién escribir si no.

**D-3 · La respuesta es uniforme también cuando el envío falla.**

`send_email` devuelve `False` en silencio. La tentación es decir «no pudimos
enviar el correo», y eso **revela que la cuenta existe**. La pantalla dice
siempre lo mismo —«si esa dirección tiene cuenta, le llega un enlace»— y el
fallo de envío es un problema de Auphere, visible en sus registros, no en la
pantalla de la persona.

Va con esto el aviso por correo de que la contraseña cambió, que es lo que
convierte un secuestro silencioso en uno que la víctima ve.

---

## D-4 · Restablecer la contraseña revoca las máquinas

> **Decisión de Luis, 2026-09-22**, común a esta evaluación y a
> [`maquina-sin-emparejar`](../maquina-sin-emparejar/decision.md) D-6.

La pregunta cruzada queda cerrada con un **sí**: quien recupera su contraseña
sale con **todas** sus sesiones cerradas y **todas** sus máquinas archivadas.

Es coherente con el motivo real de recuperar. Si alguien pudo entrar en la
cuenta, pudo registrar una máquina; cerrar solo las sesiones habría dejado
abierta la puerta más peligrosa de las dos, porque una credencial de máquina
abre **ejecución local**.

Tres consecuencias que cambian el alcance de esta spec:

1. **D-1 crece y se convierte en una pieza con nombre**: no es «cerrar
   sesiones», es **«retirar todo el acceso de esta persona»** — sesiones y
   máquinas, en una transacción. Media ya existe:
   `archive_all_for_principal` (`repositories/local_workstation.py:138-147`),
   hoy llamada solo al retirar la pertenencia. La otra media no existe en
   ninguna forma.
2. **Esa pieza se construye una vez.** La comparte con la 012; la spec que vaya
   primero la construye y la otra la usa. Duplicarla es garantizar que un día
   divergen.
3. **El coste hay que decirlo en la pantalla**: recuperar la contraseña obliga a
   volver a entrar en cada máquina. Hoy eso significa repetir la ceremonia del
   código en cada una — lo que hace esta decisión difícil de defender. Con la
   012 entregada, baja a «abre la app y entra». **Por eso la 012 va antes que la
   011**, aunque el intake las listara en el otro orden.

---

## Lo que queda abierto y no lo cierra esta puerta

1. **Mailhog.** Está en `docker-compose.yml:34-39` sin conectar a nada desde
   que se eligió Resend. O se cablea, o se acepta por escrito que este flujo no
   se prueba de punta a punta en local. **Decidirlo, no descubrirlo a mitad.**
3. **Cuántos partners entran por Google.** Es una consulta a producción y decide
   si la Opción B sube en la próxima revisión. No bloquea.

---

## Lo que la spec tiene que declarar en su encabezado

- **Superficie**: `0` **y `3a`** — D-4 lo confirma: restablecer archiva las
  máquinas, así que esta spec alcanza al puente.
- **Garantías tocadas**: ninguna de las ocho. Pero **sí toca identidad**, así
  que el modelo de amenaza va escrito antes del código, como pedía el intake, y
  con test propio del rechazo uniforme —texto **y tiempo**.
- **Qué se mide**: nada nuevo.
- **Prioridad de entrega**: **«retirar todo el acceso de esta persona» (D-1 +
  D-4) va primera y es entregable sola**, con valor inmediato: hoy no hay forma
  de echar a nadie de ninguna sesión ni de ninguna máquina, ni siquiera a mano.
  El resto del flujo de recuperación va después.
- **Dependencia declarada**: la 012 debería ir antes. Con el código de
  emparejamiento todavía puesto, D-4 obliga a repetir la ceremonia en cada
  máquina tras cada restablecimiento, y eso convierte una decisión correcta en
  una que nadie querrá usar.
