# Especificación: Crear cuenta, con el mismo oficio que Entrar

**Rama**: `067-crear-cuenta` · **Creada**: 2026-11-20 · **Estado**: Borrador, pendiente de la revisión de Luis

**Entrada**: el owner (Andrés, 2026-11-20), al ver «¿No tienes cuenta? Crea una.» en staging: "No, más bien agrégale el flujo de crear cuenta porque la vamos a necesitar, pero hazlo que se vea bien el flujo como debe ser. Puedes utilizar el que llegamos a tener en la demo."

## Encabezado Auphere *(obligatorio)*

| Campo | Valor |
|---|---|
| **Superficie de confianza** | `0`: las páginas públicas del alta (`/signup` y `/signup/{token}`), que ya existen detrás de `NEXUS_SIGNUP_ENABLED` (spec 006). No se abre ninguna superficie y no cambia ninguna llamada a la API. |
| **Garantías de aislamiento tocadas** | **Ninguna.** Se protege el oráculo de cuentas de la spec 006 (R1.2): la pantalla de «enviado» es la misma pueda registrarse la dirección o no (requisito 3.2). |
| **Nota de KB que la justifica** | `[[nexus/UX-CONSOLA-PARTNERS-2026-11-20]]` en `workspace/kb/Auphere/`. Lote «Entrar» del roadmap, ampliado al alta. |
| **Qué se mide** | **Nada.** |

### Lo que enmienda

| Dónde | Qué decía | Qué dice ahora |
|---|---|---|
| Spec 006, `/signup` (R1) | Un campo de correo y «Continuar». Google debajo, sin separador. Un «enviado» que no repite el correo ni deja corregirlo. | Google primero, «o con tu correo», «Correo de trabajo». El «enviado» repite el correo, deja usar otro y reenviar a los 30 s (requisitos 2 y 3). |
| Spec 006, `/signup/{token}` (R2, R3) | El correo en un campo deshabilitado (contraste bajo), y la regla de la contraseña solo al fallar. | El correo como texto legible con su icono. Contraseña con mostrar/ocultar y la regla en vivo (requisito 4). |
| Spec 066, el panel del líquido | El mismo titular en todas las páginas de `(auth)`. | En el alta, el panel dice «Empieza con Auphere» y enseña los tres pasos del arranque, con el primero marcado (requisito 1). |

## Por qué

El alta existe desde la spec 006, pero tiene el aspecto de antes de la 066. Junto al Entrar nuevo se nota mucho:
- un formulario suelto sin contexto;
- Google sin separador;
- un «enviado» que no dice adónde fue el enlace;
- el correo del segundo paso en un campo gris casi ilegible.

El owner pidió que el flujo se vea como debe y que se use el de la demo de la consola (versión 1, 2026-11-19). Allí el alta enseñaba los tres pasos del arranque, para que el siguiente nunca fuera una sorpresa.

## Requisitos

### 1. El panel del alta

1.1 WHEN la ruta es `/signup` o `/signup/{token}` THEN el panel del líquido muestra:
   - «Empieza con Auphere» como titular;
   - «Tres pasos y el agente de tu primer cliente ya responde.»;
   - los tres pasos del arranque:
     1. Crea tu cuenta (tu correo y una contraseña);
     2. Añade tu primer cliente (nombre, nicho y su web);
     3. Configura tu agente y publícalo (su agente empieza a responder). Owner, 2026-11-20: sustituye a «Conecta su WhatsApp».

1.2 El primer paso se ve como el actual, con `aria-current="step"`. Los otros dos se ven como pendientes. El número va en el círculo y el estado nunca se dice solo con color.

1.3 En las demás páginas de `(auth)` el panel sigue como en la 066. **El líquido no se vuelve a montar al pasar de Entrar al alta** (R1.3 de la 066): solo cambia el texto.

1.4 Por debajo de 900 px el panel es la franja de la 066, sin titular ni pasos.

### 2. Pedir el alta (`/signup`)

2.1 Arriba, «Paso 1 de 3». Después el `h1` «Crea tu cuenta.» y «Te mandamos un enlace para confirmar que el correo es tuyo.».

2.2 WHEN Google está disponible THEN «Registrarte con Google» va primero, seguido de un separador «o con tu correo». Sin Google no hay ni botón ni separador (spec 006, 5.6).

2.3 El campo se llama «Correo de trabajo», con el ejemplo «nombre@agencia.com», `autocomplete="email"` y `inputMode="email"`.

2.4 Debajo del botón, «¿Ya tienes cuenta? Iniciar sesión», que lleva a `/login`.

### 3. Enviado

3.1 WHEN se pide el alta THEN la pantalla de «enviado» muestra un icono de correo, «Revisa tu correo» y «Si {correo} puede registrarse, ya tiene un enlace esperando. Ábrelo para terminar tu cuenta. Caduca en 24 horas.».

3.2 **El texto es el mismo pueda registrarse o no** (spec 006, R1.2). La dirección es la que se escribió.

3.3 «Usar otro correo» vuelve al formulario con el correo puesto.

3.4 «Reenviar el enlace» se activa a los 30 s, con la cuenta atrás visible. WHEN la API contesta 429 THEN se dice «Demasiadas solicitudes. Prueba dentro de un minuto.», como hoy.

3.5 La cuenta atrás no está dentro de la región que se anuncia a los lectores de pantalla.

### 4. Terminar la cuenta (`/signup/{token}`)

4.1 Arriba, «Paso 1 de 3». Después «Ya casi.» y su texto.

4.2 El correo verificado se ve como texto legible con un icono de verificado, no como un campo deshabilitado. Sigue sin mandarse (lo lee la API de la solicitud).

4.3 Los campos «Nombre de la empresa» (con su ayuda), «Tu nombre» y «Contraseña». La contraseña tiene mostrar/ocultar y la regla «12 caracteres o más», que se marca mientras se escribe, con icono y texto.

4.4 Al enviar con errores, el error va en el campo y el foco también.

4.5 Al terminar, se entra en la consola como hoy: la sesión la abre el servidor (spec 006).

4.6 Un enlace muerto tiene una sola pantalla para sus cuatro casos, como hoy. Gana un enlace «Pedir otro enlace» que lleva a `/signup`.

### 5. Entrar ↔ alta

5.1 En Entrar, «¿No tienes cuenta? Regístrate», con solo «Regístrate» como enlace (owner, 2026-11-20; antes «Crea una.»). Solo aparece con `NEXUS_SIGNUP_ENABLED`.

5.2 Desde el alta, «¿Ya tienes cuenta? Iniciar sesión» lleva a Entrar. Desde el «enviado», «Volver a la entrada» también.

### 6. Sin pie

6.1 Las páginas de `(auth)` ya no llevan el pie «Auphere» bajo el formulario (owner, 2026-11-20): el logo ya está en el panel.

## Fuera de alcance

- **Encender el alta en producción.** Es la variable `NEXUS_SIGNUP_ENABLED` de Vercel y una decisión de negocio, no de esta spec.
- **Los pasos 2 y 3 del arranque** (primer cliente y WhatsApp). Ya existen en la consola. Aquí solo se anuncian.
