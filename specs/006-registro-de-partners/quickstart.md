# Validación: el registro de partners

Cómo se comprueba que esto funciona, de punta a punta. Es la guía que se ejecuta
antes de decir que la spec está entregada — no la implementación, que vive en
`tasks.md`.

## Antes de empezar

```bash
docker compose up -d                     # Postgres + Redis + Mailhog
cd apps/api && uv run alembic upgrade head
curl -s http://localhost:8000/health     # {"status":"ok"}
```

**Mailhog es parte de la prueba, no un adorno:** el correo de verificación es un
paso del recorrido, y leerlo en `http://localhost:8025` es cómo se consigue el
enlace sin mirar la base de datos.

Para el tramo de Google hace falta un cliente OAuth de prueba con
`http://localhost:3000/auth/google/callback` entre los redirect URIs, y sus dos
valores en el entorno de la API.

---

## 1 · El recorrido entero, sin operador

**Es el criterio de éxito CE-001 y CE-002**, así que se hace de la forma más
hostil posible: **con una terminal en la que nadie ha ejecutado ningún script de
siembra**, y sin credencial de operador en ninguna parte.

1. Abrir `http://localhost:3000/signup`, poner un correo nuevo, enviar.
2. Comprobar en Mailhog que llega **un** correo, con un enlace.
3. Abrir el enlace, poner nombre de empresa y contraseña.
4. **Debería aterrizar dentro de la consola, como `owner`.**

Lo que hay que verificar además de que «se ve bien»:

```sql
-- El partner existe, está en Free y NADIE le sembró una suscripción
SELECT p.slug, p.console_enabled, s.tier_code
  FROM partners p LEFT JOIN partner_subscriptions s ON s.partner_id = p.id
 WHERE p.slug = 'agencia-bonita';
-- → console_enabled = t, tier_code = NULL   (NULL es Free, y es lo correcto)

-- La solicitud se consumió y no quedó colgando
SELECT status, consumed_at FROM signup_requests WHERE email = '…';
-- → consumed

-- La membresía llegó por el camino de siempre
SELECT role, status FROM partner_memberships WHERE email = '…';
-- → owner, active
```

**El `tier_code = NULL` no es un fallo.** Un partner sin fila es Free, y la
ausencia es un estado válido y diseñado. Si algún día sale `free` en vez de
`NULL`, alguien sembró algo que no hacía falta.

## 2 · Que nadie pueda averiguar qué correos existen

**CE-004.** Se piden dos altas, una con un correo que existe y otra con uno que
no, y se comparan **las tres cosas**:

```bash
# el cuerpo, byte a byte
diff <(curl -s … -d '{"email":"existe@x.com"}') <(curl -s … -d '{"email":"nuevo@x.com"}')
# → sin diferencias
```

El código y el cuerpo tienen que ser idénticos, y **los tiempos de respuesta
comparables**: si consultar un correo que existe tarda sistemáticamente más, el
canal lateral sigue abierto aunque el cuerpo sea igual. Se miden veinte de cada
y se comparan las medianas.

Y en Mailhog: al correo que existe le llega el aviso de «ya tienes cuenta»; al
nuevo, el enlace. **Dos correos distintos, una sola respuesta.**

## 3 · Que el partner nazca entero o no nazca

Se fuerza un fallo en medio de la transacción (por ejemplo, `accept()` lanzando)
y se comprueba que **no queda nada**:

```sql
SELECT count(*) FROM partners WHERE slug = '…';               -- → 0
SELECT count(*) FROM partner_memberships WHERE email = '…';   -- → 0
SELECT status FROM signup_requests WHERE email = '…';         -- → pending, reutilizable
```

Un partner sin owner es el peor estado posible de esta tabla: nadie puede entrar
y nadie puede invitar. Por eso se prueba a propósito y no por si acaso.

## 4 · Google

1. `http://localhost:3000/signup` → «Continuar con Google» → completar.
2. Termina en el paso de nombrar la empresa, **sin haber escrito contraseña**
   (CE-005).
3. Cerrar sesión y entrar otra vez con Google: **misma cuenta**, no una segunda.

```sql
SELECT count(*) FROM console_auth.principals WHERE lower(email) = '…';  -- → 1
SELECT provider, subject IS NOT NULL FROM console_auth.principal_identities …;
```

Y los tres rechazos, que son lo que de verdad hay que ver caer:

| Se manipula | Lo que debe pasar |
|---|---|
| `state` cambiado en un byte | `400`, y **cero filas nuevas** en `principals` y `principal_identities` |
| `state` reutilizado | `400`. Un `state` vale una vez |
| `email_verified: false` | `403`, sin cuenta, sin vínculo, sin sesión |

Para el tercero hace falta una cuenta de Google con el correo sin verificar, o
un doble del verificador de `id_token` en la prueba de integración. **Lo que no
vale es dar por hecho que Google siempre manda `true`:** es el único criterio
que impide que un correo ajeno se convierta en una cuenta.

## 5 · Que la app siga en pie con Google caído

**CE-006.** Se apunta el descubrimiento OIDC a un host que no responde y se
comprueba que **el alta y el login con contraseña siguen funcionando** y que la
página no se queda colgada esperando.

## 6 · Los límites de ritmo

```bash
for i in $(seq 1 15); do curl -s -o /dev/null -w "%{http_code} " … -d '{"email":"x@y.com"}'; done
# → 202 ×N y luego 429, con Retry-After
```

Y el que de verdad importa, porque es el que hoy no funciona (research R3):
**veinte correos distintos desde la misma IP**. Tienen que empezar a caer.

Si eso no cae, es que `X-Nexus-Client-IP` no está llegando y el cubo por IP
sigue siendo el cubo global de Vercel. **No se declara cerrado el Requisito 7
sin ver ese 429.**

## 7 · Aislamiento — bloquea el merge

```bash
cd apps/api && uv run pytest tests/isolation/ -x
```

`test_console_scope.py` es estructural sobre todas las rutas: las nuevas quedan
cubiertas al montarlas. `test_signup_scope.py` añade lo propio de esta spec — que
un alta no pueda colgar una membresía de un partner existente, y que ninguna de
las rutas nuevas acepte `partner_id`.

**Un test de aislamiento en rojo bloquea el merge.** Sin excepciones.

## 8 · Antes de decir que está

```bash
./scripts/verify.sh          # lo que corre la tubería, no una parte
```

«Verde en local» y «verde en la tubería» no significan lo mismo cuando cada uno
corre una lista distinta. Lo que se olvida en este repo no son las pruebas de la
API: son **el worker, `mypy --strict`, el paquete compartido y el `next build`**.

Y la regla de la casa sobre los tests nuevos: **cada guarda se verifica por
mutación.** Se rompe a propósito lo que vigila y se comprueba que el test se
pone rojo. Un test que pasa no prueba que vigile.
