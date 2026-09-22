# Problem Definition: recuperar la contraseña

- **Slug**: recuperar-la-contrasena
- **Fecha**: 2026-09-22
- **Entrada**: [`intake.md`](./intake.md) · [`research.md`](./research.md)

---

## Problem Statement

**Un partner que olvida su contraseña no puede volver a entrar, y el producto le
dice que escriba a un sitio que no existe.**

La única salida real hoy es que alguien del equipo de Auphere, con acceso a la
base de datos de producción, le escriba el `password_hash` a mano. Eso ya pasó
una vez, el 2026-09-18, y la contraseña nueva viajó por un chat porque nadie
miró si había otra vía. No la había.

No es que falte el mecanismo: `set_password` está escrita, valida y desbloquea
(`services/console_identity.py:294-300`). **Falta la puerta.** Cero llamantes en
toda la consola.

Y hay un segundo problema debajo, que el research destapó y que es más
incómodo: **para quien entra con Google, la recuperación ya funciona y nadie se
la ofrece.** `identity_link.py:72-90` cuelga el vínculo de la cuenta existente
sin pedir la contraseña. La pantalla de login dice «escríbenos» dos centímetros
por debajo del botón que le habría dejado pasar.

---

## Affected Users & Stakeholders

| Quién | Cómo le pega |
|---|---|
| **El partner con correo propio de dominio** | Es el caso real y el que no tiene salida. Sin Google, olvidar la contraseña es quedarse fuera hasta que alguien de Auphere intervenga |
| **El partner con Gmail** | Tiene salida y no lo sabe. El producto le miente por omisión |
| **Quien sospecha que le han entrado** | Peor servido que los dos anteriores: aunque hubiera reset, **no hay forma de cerrar las demás sesiones** (`console_identity.py:353,414` son los dos únicos DELETE, y ninguno es en bloque). Restablecer sin cerrar sesiones deja al intruso dentro 7 días |
| **El equipo de Auphere** | Cada olvido es una intervención manual con acceso a producción. No escala, y empuja a escribir contraseñas en chats |
| **Auphere como responsable del tratamiento** | Escribir credenciales a mano en la base de producción es la clase de operación que un DPA no quiere tener que describir |

---

## Goals

1. **Que un partner recupere el acceso solo, sin que nadie de Auphere toque
   producción.**
2. **Que la pantalla no prometa una salida que no existe** — o la da, o no la
   menciona (§V: la pantalla no miente).
3. **Que recuperar el acceso sirva también cuando el motivo es sospecha**, no
   solo olvido. Eso exige cerrar las demás sesiones, que hoy no se puede.
4. **Que la respuesta no revele si una dirección tiene cuenta**, con el mismo
   texto y el mismo tiempo. El repositorio ya practica esa disciplina en el
   login (`auth.py:67`, `console_identity.py:155`).
5. **Que la vía que ya existe —Google— quede dicha en voz alta**, decidida a
   propósito en vez de heredada de un módulo de enlazado.

---

## Non-Goals

- **Cambiar la contraseña estando dentro.** El intake ya lo apartó: hace falta,
  pero no bloquea a nadie.
- **Verificación de correo en el alta.** Es otro hueco (`email_verified` no
  existe como columna) y otra decisión.
- **Segundo factor.** Ni a favor ni en contra: no es lo que bloquea a nadie hoy.
- **Rediseñar la política de contraseñas.** 12-256 sin reglas de complejidad es
  defendible y no es lo que impide entrar.

---

## Success Metrics

- **Intervenciones manuales en producción por contraseña olvidada: cero.** Es la
  métrica entera. Hoy es una por incidente, y una ya ocurrió.
- Tiempo desde «no puedo entrar» hasta «estoy dentro»: de *indeterminado, a
  criterio de cuándo responde alguien de Auphere* a **minutos, sin intermediario**.
- Ninguna pantalla que ofrezca una acción sin destino.

No se instrumenta nada nuevo para medir esto: son hechos observables, no
telemetría. (Cumple el requisito del encabezado Auphere de decir qué se mide:
**nada nuevo**.)

---

## Cost of Inaction

No es una degradación gradual: es **un partner que se queda fuera y una persona
de Auphere que abre una consola contra la base de producción para arreglarlo.**

Tres costes concretos, en orden de gravedad:

1. **Riesgo operacional recurrente.** Cada olvido normaliza el acceso manual a
   producción y el envío de credenciales por canales que nadie eligió. Ya pasó.
2. **No escala con el producto que se vende.** El alta autónoma está encendida
   en producción (`config.py:267` con la bandera puesta). Cada partner nuevo es
   una lotería de si algún día llama.
3. **Una pantalla que miente.** «¿Has olvidado la contraseña? Escríbenos» sin
   dirección es peor que el silencio, porque parece una salida y consume el
   intento de la persona.

Y un coste oculto: **mientras no se decida, sigue sin decidirse si hacen falta
contraseñas.** Hoy conviven una contraseña de 12 caracteres que nadie puede
recuperar y un acceso por Google que recupera solo. Es lo peor de las dos
opciones, y no lo eligió nadie.

---

## Open Questions

Las que van a la puerta de decisión, en orden de cuánto cambian la forma:

1. **¿Hacen falta contraseñas?** Si el correo es ya la autoridad de la cuenta
   (§2 del research), la opción honesta puede ser enlace mágico + Google y
   retirar las contraseñas, en vez de construir recuperación para algo que
   quizá sobra.
2. **¿Restablecer cierra las demás sesiones?** Si sí, esta evaluación arrastra
   construir la revocación en bloque, que **hoy no existe en ninguna forma**.
   Recomendación: sí, y decirlo en el alcance ahora.
3. **¿Qué pasa si el correo no sale?** `send_email` devuelve `False` y sigue
   (`services/email.py:31`). En local está apagado por defecto y Mailhog está
   declarado en compose sin estar conectado a nada.
4. ~~**¿El restablecimiento invalida la credencial de las máquinas
   emparejadas?**~~ → **contestada por Luis el 2026-09-22: sí.** Ver
   [`decision.md`](./decision.md) D-4. De ahí sale una pieza común con la 012 y
   el orden entre las dos.
5. **¿Cuántos partners entran por Google y cuántos por contraseña?** No se puede
   leer en el código; es una consulta a producción, y decide el tamaño real del
   problema.
