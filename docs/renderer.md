# El navegador de respaldo

> Spec 047, requisito 59.2 (research D50, tarea T203). Un servicio aparte que
> pinta con Chromium las webs que solo enseñan su contenido con JavaScript, para
> que el lector de la ficha pueda leerlas. **Está apagado por defecto**. Con
> `NEXUS_RENDERER_URL` y `NEXUS_RENDERER_TOKEN` puestos, el lector lo llama desde
> la T202 (ver «Cuándo lo pide el lector»).

## Cuándo lo pide el lector (T202)

`reader.read_page` lo pide solo si la página trae **menos de 200 caracteres de
texto y ningún dato estructurado** (o ninguno) y el servicio está configurado
(`reader.default_render`). Como mucho 5 páginas por lectura. La página pintada se
usa si su dirección final pasa la guarda de direcciones públicas (lo comprueba
`renderer_client.render`), el `robots.txt` del sitio la deja, responde con un
código < 400, es del mismo sitio y trae más texto que la original. Si no, el
lector sigue con lo que tenía. Sin configurar, nada cambia: una página sin texto
sigue siendo `no_text`.

## Qué es y por qué va aparte

El lector (`services/business/reader.py`) baja cada página con `httpx`. Una web
hecha con un constructor de páginas o una aplicación de una sola página llega
casi vacía: el texto lo pinta el navegador después. Para esas, el lector puede
pedir la página ya pintada a `apps/renderer`: FastAPI y Playwright con
Chromium, en su propia imagen y su propio servicio de ECS.

Va aparte del worker por tamaño: la imagen del worker pesa unos 400 MB y con
Chromium pasaría de 1,2 GB, en cada arranque de cada réplica. Un servicio de
terceros quedó descartado porque los datos del cliente saldrían a otro
procesador sin contrato de tratamiento (D50).

```
runner (client_read) ──POST /render + token──▶ renderer ──▶ Chromium ──▶ proxy local ──▶ web pública
```

## La API del servicio

| Ruta | Qué hace |
|---|---|
| `POST /render` | Cuerpo `{"url": "https://…"}` y cabecera `Authorization: Bearer <NEXUS_RENDERER_TOKEN>`. Responde `{"final_url", "status", "html"}`: la dirección final tras las redirecciones, el código HTTP de la página y su HTML ya pintado |
| `GET /health` | `{"status": "ok"}`, sin token; la usa la comprobación de salud de ECS |

No hay más rutas, ni documentación ni esquema publicados. Los fallos son un
código cerrado, nunca una traza:

| Código | HTTP | Cuándo |
|---|---|---|
| `bad_request` | 400 / 413 | El cuerpo no es `{"url": …}` o pasa de 8 KB |
| `bad_url` | 400 | No es `http`/`https`, no tiene *host*, lleva usuario y contraseña, o pasa de 2.048 caracteres |
| `forbidden_address` | 422 | La dirección (o una redirección del documento) no es pública, o el puerto no es 80/443 |
| `too_large` | 413 | El HTML pasa de 2 MB |
| `unreachable` | 502 | El nombre no resuelve, la conexión falla o la navegación acaba fuera de la web |
| `timeout` | 504 | Pasan los 20 s |

Sin token, o con uno que no es el bueno, responde 401. El token se compara en
tiempo constante (`hmac.compare_digest`) y **antes** de leer el cuerpo.

## Las guardas

Las mismas que el lector (direcciones públicas, tamaño y tiempo), aplicadas a
todo lo que hace la página y no solo a la dirección de partida:

- **Cada conexión pasa por un proxy propio.** Chromium arranca con
  `--proxy-server` apuntando a un proxy HTTP/CONNECT que corre dentro del mismo
  proceso, en 127.0.0.1. Con `--proxy-bypass-list=<-loopback>` ni siquiera
  `localhost` ni las direcciones de enlace local (169.254.0.0/16) se saltan el
  proxy, que es lo que Chromium hace por defecto. La navegación, cada
  redirección, cada recurso, cada XHR y cada WebSocket entran por ahí.
- **El proxy resuelve una vez y conecta a la IP que ha comprobado.** Para cada
  conexión resuelve el nombre, comprueba **todas** las respuestas y conecta él
  mismo a la IP comprobada; Chromium nunca resuelve el destino. No hay segunda
  consulta de DNS, así que el *rebinding* (contestar pública al comprobar y
  privada al conectar) no tiene dónde colarse. Un nombre que contesta una
  dirección pública y otra privada se rechaza entero, como en
  `assert_public_url`.
- **Solo direcciones públicas** (`apps/renderer/src/nexus_renderer/addresses.py`):
  fuera loopback, RFC 1918, enlace local (incluidas 169.254.169.254, la de
  metadatos de EC2, y 169.254.170.2, la de credenciales de ECS), CGNAT
  (100.64.0.0/10), multidifusión, difusión, reservadas, documentación y pruebas,
  IPv6 de ámbito único local (incluida fd00:ec2::254) y de enlace local, y toda
  forma de IPv4 metida en IPv6 (mapeada, compatible, NAT64, 6to4, Teredo). La
  tabla es explícita para que el veredicto no cambie con la versión de Python.
  Desde la T217 (revisión de seguridad del 2026-10-30) la API usa la misma tabla,
  copiada en `apps/api/src/nexus_api/core/public_addresses.py` (el renderer tiene
  su propio entorno y su propio lock y no depende de la API):
  `apps/api/tests/unit/test_public_http.py` exige que las dos copias coincidan, y
  `test_renderer_client.py` que nunca acepte una que la API rechaza. El lector de
  la API también resuelve una vez y conecta a la IP comprobada
  (`core/public_http.py`).
- **Solo los puertos 80 y 443.** Un `CONNECT` o una petición a otro puerto
  recibe un 403 sin conectar a nada.
- **Una página por petición**, en un contexto nuevo que se cierra siempre: sin
  cookies, caché ni almacenamiento compartidos entre peticiones. Sin *service
  workers*, sin descargas, sin selector de ficheros, sin ventanas emergentes (se
  cierran al abrirse) y con los diálogos de JavaScript descartados. Imágenes,
  vídeo y fuentes no se piden; lo que no es `http`/`https`, tampoco.
- **Sin otros caminos de red en Chromium:** QUIC apagado (sería UDP, fuera del
  proxy), WebRTC solo por el proxy (es decir, nada) y sin el tráfico propio de
  Chromium (actualizaciones, *pings*, precarga de DNS).
- **Tiempo y tamaño.** 20 s en total por petición, incluida la espera por un
  hueco (dos páginas a la vez, `NEXUS_RENDERER_MAX_CONCURRENCY`). El HTML que
  se devuelve no lleva `<script>` ni `<style>` —salvo el JSON-LD, que el lector
  usa para los datos de schema.org (requisito 59.1)— y no pasa de 2 MB.
- **`robots.txt` es del lector**, como hoy en `read_page`: lo mira con la
  dirección de partida antes de pedir la página y con la `final_url` que vuelve.
  El servicio se presenta con el mismo `User-Agent` que el lector
  (`NexusReader/1.0`), para que las reglas de la web sean las mismas.

### Lo que contiene a Chromium

Chromium corre **sin su propio *sandbox***: Fargate no da espacios de nombres
de usuario ni `SYS_ADMIN`. Lo que lo contiene es, por capas: el proxy de
arriba; un usuario sin privilegios (uid 10001) y sin *capabilities* (`drop
ALL`); una task **sin rol de IAM** (en 169.254.170.2 no hay credenciales que
pedir, y el proxy ni siquiera deja llegar); y un grupo de seguridad que solo deja entrar
al runner por el 8080 y solo deja salir por el 80 y el 443.

## El cliente en la API

`nexus_api.services.business.renderer_client.render(url) -> Rendered | None`:

- Sin `NEXUS_RENDERER_URL` (o sin `NEXUS_RENDERER_TOKEN`) devuelve `None` sin
  hacer nada. Las lee con su propio `BaseSettings` (prefijo `NEXUS_RENDERER_`).
- Pasa `assert_public_url` sobre la dirección antes de enviarla y sobre la
  `final_url` que vuelve.
- Tiene su propio tope de tiempo (25 s: los 20 del servicio más el viaje) y de
  tamaño (2 MB de HTML; la respuesta entera se corta mientras llega).
- **Nunca lanza**: un fallo del servicio es `None` y una línea de log con el
  motivo y el *host*, nunca la URL entera ni el token.

**Todavía no está conectado al lector.** Lo conecta la T202, para las páginas
que traen menos texto del necesario (requisito 59.2).

## Encenderlo

Está apagado (`renderer_enabled = false`): con el interruptor así, Terraform no
crea nada y la definición de tarea del runner no cambia.

1. **El repositorio de ECR.** `nexus-renderer` no está todavía en la lista de
   `infra/terraform/bootstrap/main.tf` (`aws_ecr_repository.repos`): se añade y
   se aplica *bootstrap*.
2. **La imagen.** Los flujos de despliegue no la construyen todavía. A mano,
   para `linux/amd64` (Fargate corre en `X86_64`):

   ```bash
   docker build --platform linux/amd64 -t <ecr>/nexus-renderer:<tag> apps/renderer
   docker push <ecr>/nexus-renderer:<tag>
   ```

   La imagen base es la oficial de Playwright para Python, fijada por versión y
   *digest* (`v1.64.1-noble`). El paquete `playwright` del `uv.lock` tiene que
   ser la misma versión; la construcción falla si no encuentra su Chromium.
3. **Terraform** (`infra/terraform/20-services`), en el *workspace* que toque:

   ```bash
   terraform apply -var renderer_enabled=true    # o en <ws>.tfvars
   ```

   Crea el secreto `nexus/<ws>/renderer` **ya con un token** de 48 caracteres
   (generado con GetRandomPassword; Terraform no lo vuelve a tocar), la task
   (0,5 vCPU y 2 GB por defecto: `renderer_cpu`, `renderer_memory`), el
   servicio, su grupo de seguridad, su nombre en Cloud Map
   (`renderer.nexus-<ws>.internal`) y los permisos para leer el token. Al
   runner le añade `NEXUS_RENDERER_URL` y `NEXUS_RENDERER_TOKEN`
   (`taskdefs.tf`, contenedor `runner`), y solo después de que su *execution
   role* pueda leer el token, para que sus tasks nuevas arranquen.
   `renderer_image` cambia la imagen; vacía, es `<ecr>/nexus-renderer:<image_tag>`.
4. **Comprobarlo**: el servicio sano en ECS (su comprobación de salud llama a
   `/health` dentro de la task) y sus logs en `/nexus/<ws>/renderer`
   (`renderer.render host=… outcome=…`) cuando el lector empiece a usarlo.

Coste aproximado con los valores por defecto: unos 25 US$ al mes por réplica
encendida todo el mes en eu-south-2. El apagado nocturno de staging
(`staging_parking.tf`) no lo incluye.

**Apagarlo** es `renderer_enabled = false` y `apply`: se borra todo, el runner
pierde las dos variables y el lector sigue como sin él.

### Rotar el token

1. Poner un valor nuevo (32 caracteres o más) en `NEXUS_RENDERER_TOKEN` del
   secreto `nexus/<ws>/renderer`.
2. Forzar un despliegue nuevo del renderer y del runner (las tasks leen el
   secreto al arrancar). Entre uno y otro, las peticiones del runner reciben 401
   y el lector sigue sin el renderer.

## En local

```bash
cd apps/renderer
uv sync --extra dev
uv run pytest                 # sin navegador: Playwright simulado, proxy con sockets locales
```

Para arrancarlo de verdad hace falta bajar Chromium (más de 100 MB), que las
pruebas no necesitan:

```bash
uv run playwright install chromium
NEXUS_RENDERER_TOKEN=$(openssl rand -hex 24) uv run nexus-renderer    # :8080
```

y en la API o el worker, `NEXUS_RENDERER_URL=http://localhost:8080` y el mismo
token.

## Verificación

- `./scripts/verify.sh lint` revisa el renderer con su propio entorno (ruff y
  `mypy --strict`); `./scripts/verify.sh py` corre sus pruebas. En la tubería,
  el job `test-renderer` de `ci.yml` hace lo mismo desde su `uv.lock`.
- `./scripts/verify.sh locks` incluye `apps/renderer/uv.lock`.
- Licencias leídas y citadas: `docs/licenses/renderer.md` (Playwright,
  Apache-2.0; Chromium, BSD-3-Clause; FastAPI, MIT; uvicorn, BSD-3-Clause).

**No verificado todavía:** la imagen no se ha construido (ni en local ni en la
tubería), así que no hay una prueba de punta a punta con Chromium de verdad; la
lista de componentes de terceros de Chromium (`about:credits`) se lee en la
primera construcción.
