# Recuperar la contraseña

Cómo alguien que no puede entrar vuelve a entrar, sin que nadie de Auphere abra
una consola de producción. Implementa la spec
[`011-recuperar-la-contrasena`](../specs/011-recuperar-la-contrasena/spec.md) y
la evaluación `.specify/assessments/recuperar-la-contrasena/`.

Estado al **2026-09-23**: construido, probado y recorrido a mano en local con
Mailhog. Falta el paso por staging.

**Por qué existe, con fecha**: el 2026-09-18 alguien perdió su contraseña y se
resolvió **escribiendo el hash a mano en producción**, con la contraseña nueva
viajando por un chat. Eso no era una anécdota: era el procedimiento.

---

## 1 · El recorrido

```
POST /console/password-reset            → fila en console_auth.password_reset_requests
                                          + correo con el enlace. SIEMPRE 202.
POST /console/password-reset/{token}    → en UNA transacción:
                                            set_password + cerrar sesiones + archivar máquinas
                                          y, ya fuera, el aviso de que cambió.
```

Dos pantallas, las dos públicas: `(auth)/forgot` y `(auth)/reset/[token]`.

**Las dos rutas de la API van detrás del token de servicio del BFF**, como
`/console/auth/*` y `/console/signup/*`. La anonimidad vive en el borde
navegador ↔ BFF; el borde BFF ↔ API no es anónimo nunca, y
`tests/isolation/test_console_scope.py` lo comprueba ruta por ruta.

> **Y las dos rutas del navegador están en la lista pública de `proxy.ts`.**
> Es la línea que más fácil se olvida y la que mata la función entera en
> silencio: quien pide restablecer su contraseña **no tiene sesión** —es lo que
> viene a recuperar— así que sin esa línea rebota a `/login` antes de ver el
> formulario. Le pasó al alta en la spec 006 y volvió a pasar aquí; las dos
> veces con todo en verde, porque ninguna prueba de la API, de componente ni el
> `next build` pasa por esa capa. Lo fija
> `apps/console/src/__tests__/proxy-public-routes.test.ts`.

---

## 2 · Por qué el rechazo es uniforme

**Ésta es la decisión que gobierna el fichero entero**, y es contraintuitiva de
mantener, así que conviene tenerla escrita.

Pedir un enlace responde **siempre `202` y siempre el mismo cuerpo**. Cuatro
caminos, una respuesta:

| Camino | Qué pasa por dentro | Qué se ve |
|---|---|---|
| La dirección **no tiene cuenta** | no se escribe nada, no sale correo | `202 {"status":"sent"}` |
| El **envío falla** | `send_email` devuelve `False`, queda en los registros | lo mismo, byte a byte |
| Se pasó el **tope** | la excepción se traga, no sale correo | lo mismo, byte a byte |
| Todo bien | fila nueva, las vivas invalidadas, correo fuera | lo mismo, byte a byte |

La razón: es **la única ruta del producto que acepta la dirección de
cualquiera**. Un `429` al toparse, o un «no pudimos enviarlo», convierten la
pantalla en un oráculo de qué direcciones están registradas — basta gastarle el
tope a una lista para saber cuáles existen.

Y de ahí sale una consecuencia sobre el **orden del código** que parece un
detalle de estilo y no lo es: **el tope se comprueba antes de mirar si la cuenta
existe**. Al revés, una dirección registrada gastaría una consulta y un envío
antes de toparse y una sin registrar no, así que el reloj diría lo que el cuerpo
calla.

Lo fija `TestNadieAveriguaQueCuentasExisten`, que compara las respuestas
**carácter a carácter**. Un test que sólo mire el código de estado no ve la
diferencia que importa.

**Lo que NO está cerrado**: el texto es idéntico; el **tiempo** no del todo. Con
cuenta hay un `UPDATE`, un `INSERT` y una llamada HTTP al proveedor de correo;
sin cuenta, sólo un `SELECT`. El alta cierra esa diferencia mandando correo
también a quien ya tiene cuenta; aquí el equivalente sería mandar correo a
direcciones **sin** cuenta, que es convertir la ruta en un remitente de correo
ajeno. Queda abierto a propósito.

---

## 3 · La transacción, y por qué la pieza no hace commit

El canje hace **tres cosas o ninguna** (R3.3): fija la contraseña, cierra todas
las demás sesiones y archiva todas las máquinas.

Las dos últimas no se escriben aquí: las hace
`services/principal_access.revoke_all_access`, que construyó la spec 012 **sin
commit a propósito** — su docstring dice que la 011 la usaría dentro de su misma
transacción. Componerla es el motivo por el que existe con esa forma.

El estado que no puede existir es **«contraseña nueva, sesiones vivas»**: alguien
que restablece porque cree que le entraron, y a quien el producto le dice que ha
terminado mientras el intruso sigue dentro con su cookie siete días. Y con las
máquinas es peor, porque una credencial de máquina abre **ejecución local**.

Eso no se ve por el camino feliz. Lo prueba `TestLaTransaccion`, que **rompe la
segunda mitad a propósito** con las sesiones ya cerradas dentro de la
transacción y comprueba que no quedó nada aplicado.

**La operación corre con rol dueño, así que la RLS no la protege.** Lo único que
impide que alcance a otra persona es el `WHERE` por `principal_id`. Por eso hay
un test de aislamiento propio del camino nuevo —
`tests/isolation/test_42_reset_scope.py` — con **dos** personas, no una:
restablecer la propia y mirar que la propia quedó fuera no prueba ningún límite.

---

## 4 · Los números, y qué hace el tope de verdad

| Qué | Valor | Por qué |
|---|---|---|
| Caducidad del enlace | **1 hora** | Suficiente para ir al correo; corto para que uno olvidado en una bandeja no siga abriendo la cuenta |
| Tope de peticiones | **5 por dirección**, ventana de 1 h | Suficiente para quien no encuentra el correo; insuficiente para barrer direcciones |

El tope **reutiliza `services/one_time_code_limits.py`**, que ya existía (R5.5):
dos claves, cuenta dentro de una ventana y espera creciente, y las dos borradas
al acertar. Se le añadieron `limit` y `window` como campos con los valores de
siempre por defecto, así que sus dos llamantes anteriores no cambian.

**No es «cinco por hora» a secas**, y conviene no redondearlo: cinco peticiones
dentro de la ventana abren una espera de 60 s que se **dobla** con cada tanda
hasta un tope de 15 minutos. En régimen, cinco cada cuarto de hora.

El secreto del enlace es `secrets.token_urlsafe(32)` —256 bits— y en reposo vive
**sólo** su SHA-256. **No se usa el generador de `core/one_time_codes.py`**: ése
hace códigos de ocho caracteres para **dictarse en voz alta** (~39 bits), y aquí
el secreto viaja en una URL, donde la longitud no cuesta nada y el canje no
tiene techo por token.

---

## 5 · Los dos correos

Los dos van a la **persona dueña de la cuenta**, que puede no ser quien rellenó
el formulario. Por eso el idioma sale de `principals.locale` y **no del cuerpo
de la petición**: dejar que lo eligiera el que pide permitiría a un desconocido
decidir en qué lengua le llega a otra persona un correo sobre su contraseña.

**El enlace** dice que sirve una vez, que caduca en una hora, y avisa de que
restablecer cierra las sesiones y da de baja las máquinas.

**El aviso de que cambió** (R4) dice **cuándo** —en UTC y con la zona escrita, o
no sirve para que alguien diga «yo a esa hora no estaba»— y **a quién escribir**.

> **El aviso no lleva ningún enlace, y no es minimalismo.** Un correo sobre tu
> contraseña que trae un enlace entrena a pulsar enlaces dentro de correos sobre
> tu contraseña, que es justo el gesto que un suplantador necesita. Lo único que
> lleva es un `mailto:`, y escribir a alguien no es entrar en ningún sitio.

Va **después** de la transacción: si pudiera deshacer el restablecimiento, un
proveedor de correo con un mal día dejaría a la persona sin entrar **y** sin
enterarse.

**`NEXUS_SECURITY_CONTACT_EMAIL` es obligatoria en producción** y la API se
niega a arrancar sin ella. Sin dirección el aviso sale igual —R4.1 no admite
condiciones— y entonces a quien le acaban de robar la cuenta se le entrega el
susto sin la salida: el mismo fallo que la evaluación nombró en `login.forgot`,
«Escríbenos» sin destino.

---

## 6 · Recorrerlo en local

`send_email` habla con Resend por HTTP. Para poder recorrer el circuito entero
en local (CE-006) tiene un **repliegue SMTP** que se enciende **sólo cuando no
hay clave de Resend y sí hay `NEXUS_SMTP_URL`**. En producción hay clave y no
hay `SMTP_URL`, así que ese camino no cambia ni un byte.

Se descartó la alternativa fácil —escribir el enlace en los registros en
desarrollo— porque es cómo un secreto acaba en producción.

```bash
docker compose up -d          # mailhog incluido, ya cableado
# la bandeja: http://localhost:8025
```

---

## 7 · Lo que queda fuera

- **Retirar las contraseñas** (Opción B de la evaluación): mejor idea, peor
  decisión hoy — toca la ruta por la que entra todo el mundo.
- **Segundo factor**: otra conversación.
- **Cambiar la contraseña estando dentro**: otra pantalla y otro flujo.
- **Recuperar la cuenta de un operador de Auphere** (`operator_identity`): otra
  identidad, otras reglas.

---

## Referencias

- Spec: [`specs/011-recuperar-la-contrasena/`](../specs/011-recuperar-la-contrasena/spec.md)
- La pieza que se compone: `apps/api/src/nexus_api/services/principal_access.py` (spec 012)
- Aislamiento: `apps/api/tests/isolation/test_42_reset_scope.py` y `test_38_principal_access_revocation_scope.py`
