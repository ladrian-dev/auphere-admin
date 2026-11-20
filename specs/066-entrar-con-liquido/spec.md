# Especificación: Entrar con el líquido vivo

**Rama**: `066-entrar-con-liquido` · **Creada**: 2026-11-20 · **Estado**: Borrador, pendiente de la revisión de Luis

**Entrada**: descripción del owner (Andrés, 2026-11-20): "Me encanta la app web. ¿Cuál sería el roadmap para ejecutar los cambios en la consola de staging? ¿Cómo implementaríamos la animación de login? Me encanta cómo está, la interacción y el dinamismo. Tenemos el okey para hacer todos estos cambios en la consola de staging. Empieza por Entrar."

## Encabezado Auphere *(obligatorio)*

| Campo | Valor |
|---|---|
| **Superficie de confianza** | `0`: solo las páginas públicas de la consola (`(auth)`): Entrar, Recuperar la cuenta y Contraseña nueva, y el marco que comparten con el alta, la invitación y «sin acceso». No se abre ninguna superficie y no cambia ninguna llamada a la API. |
| **Garantías de aislamiento tocadas** | **Ninguna.** No hay sesión en estas páginas ni datos de ningún tenant. Lo que sí se protege es el oráculo de cuentas de la spec 011 (R1.3): la pantalla de «enviado» sigue siendo la misma exista o no la cuenta (requisito 4.4). |
| **Nota de KB que la justifica** | `[[nexus/UX-CONSOLA-PARTNERS-2026-11-20]]` en `workspace/kb/Auphere/`. Estudio y demo de la consola: https://claude.ai/artifact/C437XiNZt3qgpZPGMTW79c · https://claude.ai/artifact/GaTpyrAnMLz8dFmBz6ErHc |
| **Qué se mide** | **Nada.** No gasta modelo, máquina ni herramientas. El líquido se pinta en el navegador de quien entra. |

### Lo que enmienda

| Dónde | Qué decía | Qué dice ahora |
|---|---|---|
| Spec 011, pantalla de «enviado» (R1) | Un texto fijo. No decía a qué dirección se mandó ni dejaba pedir otro enlace desde ahí. | Repite la dirección que escribió la persona, deja cambiarla y deja pedir otro enlace pasados 30 s. El texto es el mismo tenga cuenta o no (requisito 4). |
| Spec 011, Contraseña nueva (R2) | Un campo. La regla de los 12 caracteres solo se veía al fallar. | Dos campos (nueva y repetir) con mostrar/ocultar. Las dos reglas se marcan mientras se escribe (requisito 5). |
| Marco de `(auth)` (`layout.tsx`) | Una columna centrada, «auphere» en tipografía mono y «Beta» en ámbar. | Pantalla partida con el líquido de Auphere, el logo real y «Beta» neutro (requisitos 1 a 3). |

## Por qué

En la revisión de la consola de partners (estudio del 2026-11-20), la entrada fue lo que más gustó de la demo: el líquido de los verdes de Auphere que se mueve solo, sigue al puntero y abre una onda al hacer clic. Es la primera pantalla que ve un partner y hoy es la más pobre de la consola. Tiene tres problemas:

1. **No parece Auphere.** Pone «auphere» en tipografía mono en vez del logo.
2. **El «Beta» va en ámbar**, el color de los avisos, aunque no avisa de nada.
3. **Recuperar la cuenta deja dudas:**
   - la pantalla de «enviado» no dice adónde se mandó el enlace;
   - no deja corregir una dirección mal escrita;
   - no deja pedir otro enlace sin volver a empezar;
   - en Contraseña nueva, la regla de los 12 caracteres solo aparece al fallar.

Es el primer lote del roadmap de la consola (lote «Entrar»). Va primero porque solo toca `(auth)`, no choca con los otros lotes y se ve enseguida en staging.

## Requisitos

### 1. Pantalla partida

1.1 WHEN se abre cualquier página de `(auth)` en una ventana de 900 px o más THEN se ve partida en dos:
   - a la izquierda, un panel redondeado con el líquido, el logo, «Beta», «Consola de partners» y un titular;
   - a la derecha, el contenido de la página en una columna de 360 px como máximo, centrada.

1.2 WHEN la ventana mide menos de 900 px THEN el líquido es una franja de 200 px encima del contenido, con el logo y «Beta». El titular no se ve.

1.3 WHEN se pasa de una página de `(auth)` a otra (Entrar → Recuperar, Recuperar → Entrar) THEN el líquido sigue donde estaba, sin empezar de cero ni parpadear. Lo comparten porque vive en el marco.

1.4 El contenido de la derecha queda tal cual. La página de cada ruta no cambia de estructura por este requisito: el alta, la invitación, «sin acceso» y la entrada de escritorio se ven en la columna derecha.

### 2. El líquido vivo

2.1 WHILE la página está a la vista THEN el líquido se mueve solo. Un «dedo invisible» lo recorre despacio, y cada 4 a 6 s se abre una onda suave.

2.2 WHEN el puntero se mueve sobre el panel THEN el líquido sigue al puntero y se ilumina por donde pasa. A los 2,5 s sin moverlo, vuelve el dedo invisible.

2.3 WHEN se hace clic o se toca el panel THEN se abre una onda desde ese punto. Como máximo hay cuatro ondas a la vez.

2.4 Se pinta a media resolución, con la densidad de píxeles limitada a 2.

2.5 WHEN la pestaña se oculta o el panel sale de la vista THEN deja de pintar. Vuelve al volver a verse.

2.6 WHEN el sistema pide reducir movimiento THEN pinta un solo cuadro quieto y no reacciona al puntero ni al clic.

2.7 WHEN el navegador no tiene WebGL, o el shader no compila THEN queda el fondo de respaldo: los mismos verdes en manchas difuminadas, que con reducir movimiento tampoco se mueven. Nunca queda un hueco vacío ni un error.

2.8 El formulario no espera al líquido. El panel se pinta primero con el fondo de respaldo y el líquido aparece encima con un fundido de 0,6 s, sin mover nada de sitio.

2.9 El líquido no es contenido. Va con `aria-hidden`, no recibe el foco y no tapa nada de la columna del formulario.

2.10 WHEN se sale de `(auth)` (al entrar en la consola) THEN se cancela el pintado, se quitan los eventos y se libera el contexto WebGL.

### 3. Una cabecera que es Auphere

3.1 El panel lleva el logo real (`BrandLockup` de `@nexus/ui`) en blanco sobre el líquido, no la palabra en mono.

3.2 «Beta» va en una píldora neutra translúcida, no en ámbar. El ámbar queda para los avisos.

3.3 La cabecera, el titular y el pie salen en el mismo idioma que la página. El marco sigue usando `getT()` sin argumento, como dejó la spec 056 (14.1).

3.4 El texto del panel se lee: blanco sobre la zona oscura del líquido, con un degradado oscuro bajo el titular que asegura un contraste de 4,5:1 o más.

### 4. Entrar y recuperar la cuenta

4.1 Entrar gana el botón de mostrar/ocultar contraseña, con su `aria-label` y `aria-pressed`. El foco se queda en el campo.

4.2 Entre «Entrar» y «Continuar con Google» va un separador «o».

4.3 WHEN se pulsa «¿Has olvidado la contraseña?» con un correo ya escrito en Entrar THEN Recuperar la cuenta se abre con ese correo puesto.
   - El correo viaja en `sessionStorage`, nunca en la URL, porque una URL acaba en el historial y en los registros.
   - Se borra al leerlo.

4.4 WHEN se pide el enlace THEN la pantalla de «enviado»:
   - dice «Si {correo} tiene cuenta, ya tiene un enlace esperando…», con la dirección que escribió la persona;
   - tiene «Cambiar», que vuelve al formulario con el correo puesto;
   - tiene «Reenviar el enlace», que se activa a los 30 s con una cuenta atrás visible.

   **El texto, los botones y los tiempos son los mismos tenga cuenta o no**, como exige la spec 011 (R1.3). La dirección que se enseña es la que se escribió, no una que haya confirmado el servidor.

4.5 WHEN se reenvía THEN se llama a la misma acción y la cuenta atrás vuelve a empezar. Un aviso dice «Te mandamos otro enlace. El anterior deja de valer.». Igual que en 4.4, no cambia nada según exista la cuenta.

### 5. Contraseña nueva

5.1 Hay dos campos, «Contraseña nueva» y «Repítela». Un solo botón de mostrar/ocultar sirve para los dos.

5.2 Debajo hay dos reglas que se marcan mientras se escribe, con icono y texto (nunca solo color):
   - «12 caracteres o más»;
   - «Las dos coinciden».

   Se anuncian a lectores de pantalla sin interrumpir (`aria-live="polite"`).

5.3 WHEN se pulsa «Cambiar la contraseña» sin cumplir las reglas THEN el error va en el campo que falla y el foco va a ese campo. El botón nunca se apaga sin explicar por qué.

5.4 Se mantiene lo que decide la spec 011:
   - el aviso de que te deja fuera de todas partes va **antes** de pulsar (R3.6);
   - al terminar **no se abre sesión** (D-5);
   - el enlace muerto tiene una sola pantalla para sus tres casos.

### 6. Movimiento y accesibilidad

6.1 Al cambiar de página dentro de `(auth)`, la columna derecha aparece con un fundido de 0,2 s y una subida de 8 px. Con reducir movimiento, sin desplazamiento.

6.2 Todo se usa con teclado, con el foco visible. El contraste es de 4,5:1 en texto y de 3:1 en controles, en claro y en oscuro.

6.3 axe no encuentra violaciones graves ni críticas en `/login`, `/forgot` y `/reset/{token}`.

## Fuera de alcance, con su porqué

- **Decir a quien entra con Google que no necesita contraseña.** La demo lo hacía en Recuperar la cuenta. Aquí no se hace: contestar distinto según la cuenta es el oráculo que cierra la spec 011 (R1.3).
- **Entrar directamente al guardar la contraseña nueva.** La demo lo hacía. La spec 011 lo descarta (D-5): el canje acaba de cerrar todas las sesiones, y entrar con la contraseña nueva es la prueba de que funciona.
- **Un medidor de seguridad de la contraseña.** La política del servidor es de 12 caracteres. Un medidor que puntúe otras cosas prometería una regla que el servidor no aplica. Si se quiere, va en una spec que cambie la política.
- **El alta (`NEXUS_SIGNUP_ENABLED`)** solo gana el marco nuevo. Sus pantallas no cambian.
- **La app móvil**, que tiene su propia spec (042). El shader es el mismo y se podrá compartir.
