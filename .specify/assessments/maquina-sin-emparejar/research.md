# Research: la máquina se registra con la sesión, sin código

- **Slug**: maquina-sin-emparejar
- **Fecha**: 2026-09-22
- **Método**: lectura directa del código (ruta:línea y cita literal) + el
  precedente de la spec 009 y ADR-039 + los referentes de
  [[research/2026-09-19-auditoria-clase-mundial/06-referentes-externos]] §A y §D.
- **La pregunta que el intake declaró central**: «**qué protege hoy el código
  que la sesión no proteja**», y avisó de que no se respondiera por analogía.

---

## 0 · La respuesta a la pregunta central

**Nada.** Y no es una inferencia: está en el código, en dos líneas.

`apps/desktop/src/app-runtime.ts:291-295`:

```ts
async pair(code: string): Promise<void> {
  if (!hasIdentity(this.transport) || !this.store || !this.machine || !this.userId) {
    this.setBar({ kind: "pair_failed", code: "pairing_unavailable" });
    return;
  }
```

`this.userId` **solo** lo fija `applyGate` después de un `whoami` con éxito
(`app-runtime.ts:272`), y `whoami` es la ruta del BFF llamada con la cookie de
la partición humana desde el proceso principal (`session-gate.ts:4-7`).

O sea: **para poder teclear el código, la aplicación ya tiene una sesión de
consola confirmada.** El código no es un segundo factor: es un segundo acto del
mismo factor. Quien pudiera teclearlo ya había demostrado ser quien dice, en esa
máquina, con esa cuenta. El intake lo sospechaba y pedía no darlo por hecho; el
código lo confirma sin margen.

La única diferencia que quedaba en pie —«la cookie puede estar ahí de antes,
teclear un código es siempre un acto del momento»— **sigue siendo cierta y sigue
siendo la única**. Pero, como el intake ya anticipó, su respuesta no es el
código: es exigir una sesión **recién confirmada** para el canje. Eso es una
condición sobre la frescura de la cookie, no una ceremonia de ocho caracteres.

---

## 1 · Lo que hay que retirar, medido

### La pieza

| Qué | Dónde | Detalle |
|---|---|---|
| Alfabeto y longitud | `core/pairing_codes.py:17-19` | 30 símbolos dictables en voz alta, 8 de largo, 10 minutos |
| Generación | `core/pairing_codes.py:22-23` | `secrets.choice` |
| Hash en reposo | `core/pairing_codes.py:39-40` | SHA-256 sin sal |
| Tabla | `db/models/local_workstation.py:191-203` | `device_pairing_codes`, `code_hash` único |
| Emisión | `api/console/workstation_partner.py:172` | uno vivo por persona; emitir invalida los anteriores |
| Canje | `api/device_bridge.py:296` | **única ruta del puente sin credencial** |
| Límite de intentos | `services/device_pairing.py:31-35` | 5 fallos por `hostname+IP` en 10 min, espera que se duplica hasta 15 |
| Rechazo indistinguible | `api/device_bridge.py:329-331` | un solo cuerpo `pairing_code_invalid` para todo fallo |
| Diálogo de la consola | `components/workstation/pairing-dialog.tsx` | cinco fases, cuenta atrás de 1 s, «al cerrar no se vuelve a mostrar» |
| Diálogo de la app | `app/routes/pair-dialog.tsx` | **el alfabeto está duplicado** aquí: `:30-31` |

Está bien construido. Es una de las piezas más cuidadas del repositorio, y
retirarla no es un juicio sobre su calidad: es que **prueba algo que ya está
probado**.

### Lo que el canje devuelve, y que hay que seguir emitiendo

`api/device_bridge.py:205-215`, `PairedOut`: «Se devuelve **una sola vez**; la
credencial no se puede volver a leer». JWT HS256 de 12 h
(`services/device_credential.py:35,40`), con `svc/sub/pid/gen/…` que **nombra
partner, máquina y generación y nunca tenant** (`device_credential.py:3`).

Esa parte no cambia. Lo que cambia es **quién demuestra tener derecho a
pedirla**.

---

## 2 · El camino de sustitución ya existe, abierto y probado

El intake proponía canjear con la cookie de la partición humana «el camino que
`/api/desktop/redeem` ya usa». Es más fuerte que eso: **ese camino está en
producción y tiene test propio**.

`apps/desktop/src/electron/main.ts:665-671`:

```ts
const response = await session
  .fromPartition(HUMAN_PARTITION)
  .fetch(`${CONSOLE_URL}/api/desktop/redeem`, { … })
```

Y el lado del BFF, `apps/console/src/app/api/desktop/redeem/route.ts:16-20`,
explica por qué contesta 204 y no el token:

> La sesión de la aplicación es la cookie de ESTE origen: la cáscara canjea con
> el `fetch` de su partición humana, la cookie cae en esa partición, y su
> `SessionGate` la ve.

Y por qué pasa por el BFF y no por la API (`route.ts:9-12`): «La ruta de la API
exige la credencial de servicio del BFF (`require_console_service`), y la
cáscara no tiene ninguna ni puede tenerla».

**Es exactamente la forma que necesita el registro de máquina**, con una
diferencia que importa: `redeem` deja una cookie en la partición, y esto tiene
que devolver una credencial que la app guarda cifrada. O sea, esta ruta **sí**
devuelve cuerpo. Es la primera decisión de forma que la puerta tiene que tomar.

Tiene test: `apps/console/src/app/api/desktop/__tests__/redeem.test.ts:2-10`,
que existe «por el fallo desplegado de llamar directo a la API (`401 Missing
bearer token`)». Un aviso ya pagado sobre por dónde no ir.

---

## 3 · El permiso no se crea: se mueve

`workstation:pair` se define en dos sitios que tienen que coincidir —
`core/console_auth.py:117` y `apps/console/src/lib/permissions.ts:26-27` — y lo
tienen owner, admin y builder. Está congelado por test
(`lib/__tests__/permissions.test.ts:23`).

**Dónde se comprueba hoy**: seis rutas de consola, todas de
`workstation_partner.py` (emitir el código `:174`, renombrar `:214`, archivar
`:228`, vincular `:257`, desvincular `:281`, `GET /setup` `:297`).

**Dónde NO se comprueba**:

- En `POST /device/pair`. Leído entero (`device_bridge.py:296-345`): sus
  dependencias son `get_db_session` y `get_redis`, y nada más. **No hay ninguna
  comprobación de permiso en el canje.** El permiso se gastó al emitir, y la
  persona dueña sale de la fila del código (`device_bridge.py:340-341`).
- En la aplicación de escritorio: `grep -rn "workstation:pair" apps/desktop/`
  → cero. Lo único que mira es `workstation:read` para la sección
  (`sections.ts:27`).

Consecuencia para el alcance: **mover la comprobación al canje del BFF es mover
una comprobación existente, no inventar una.** El intake lo proponía como paso
2 y resulta ser lo más barato de todo el cambio.

---

## 4 · El precedente, y lo que dejó escrito que se conserva

La spec 009 hizo **este mismo movimiento** con el otro código. `specs/009-…/spec.md:39-44`:

> **Lo que se construyó era un Device Authorization Grant (RFC 8628) hecho a
> mano y al revés**… En el RFC el **dispositivo** genera el secreto y
> **sondea**; aquí lo generaba el navegador y la persona lo tecleaba.

Y `:50-52`: se pasó a RFC 8252 (*authorization code* + PKCE con retorno a
`127.0.0.1`), «es lo que hacen Claude Code, `gh`, `gcloud` y Heroku».

**Lo más útil de ese precedente no es la decisión: es la lista de lo que
conservó.** `specs/009-…/spec.md:64-65`:

> **Lo que NO cambia**: la tabla, el TTL de diez minutos, el uso único, el hash
> y el rechazo indistinguible. Todo eso hace la misma falta aquí.

Y la lección que ADR-039 se escribió a sí mismo
(`/Users/lmatos/Work/Auphere/nexus/decisions/ADR-039-…:124-129`, en la KB, que
es otro working dir):

> ### Lo que este ADR debería haber hecho y no hizo
> Preguntarse **«¿cómo resuelve esto la industria?»** antes de inventariar
> opciones propias… Dos enmiendas en un día salen de ahí.

El mismo ADR ya había visto el solapamiento que esta evaluación viene a cerrar
(`:160-162`): «**El código de emparejamiento y el de sesión se parecen y atan
cosas distintas**: uno una máquina, otro una persona. Se teclean igual a
propósito…». Se retiró uno y se dejó el otro.

La 009 también pagó un precio que conviene recordar porque **aquí no se paga**:
enmendar el Requisito 6 de la spec 001 y aflojar `no-inbound.test.ts` a
«exactamente uno» (`spec.md:58-62`), porque el loopback abre un puerto. **El
registro con la sesión no abre ninguno**: es una petición saliente más.

---

## 5 · Tres huecos que el barrido encontró y que el intake no tenía

Ninguno bloquea la decisión, y los tres son alcance si la puerta dice *go*.

### 5.1 Desemparejar no toca el servidor

`apps/desktop/src/app-runtime.ts:368-376`:

```ts
/** Desemparejar: olvida la credencial. Archivar es de la consola (R11.2). */
unpair(): void {
  this.stop();
  if (this.store && this.userId) this.store.forget(this.userId);
```

La fila `partner_devices` queda **viva y sin revocar**, y su JWT sigue siendo
válido hasta `exp` — **hasta 12 horas**. Para el olvido normal da igual; para
«desempareja esta máquina porque ya no la controlo» no sirve, y la copia de la
aplicación dice justo lo segundo: «tus teammates dejarán de poder leer y
ejecutar aquí» (`app/i18n.ts:410-414`). Dejan de poder **desde esta app**. La
credencial no.

### 5.2 `device.unpaired` está en el vocabulario y no lo escribe nadie

La migración `0108_device_audit_vocab.py:66` lo declara. `grep -rn
"device.unpaired" apps/api/src/` → cero. Lo mismo con el motivo de revocación
`"desemparejada"` (`db/models/local_workstation.py:97-105`), declarado y sin
escritor. **Desemparejar no deja asiento ninguno.**

Esto importa más si el registro pasa a ser silencioso: el intake ya preguntaba
«si el registro silencioso necesita quedar en auditoría (probablemente sí)». La
respuesta se vuelve obvia al ver que **el otro extremo del par tampoco está**.
Registrar y desregistrar sin asiento es peor que la ceremonia que se retira.

### 5.3 No hay límite de máquinas

Buscado en `apps/`, `specs/` y `docs/`: cero. `PartnerDeviceRepository.pair()`
(`repositories/local_workstation.py:64-85`) inserta sin contar filas previas. Lo
único acotado es **un código vivo por persona** (`:228`), que no es un límite de
máquinas: es un límite de códigos.

Hoy el límite práctico es la fricción de pedir un código. **Al retirarla, el
límite desaparece del todo**, y cada registro emite una credencial de 12 h que
sobrevive al desemparejado (§5.1). Las tres cosas juntas son el argumento de que
el límite y la revocación entran en el alcance, no después.

---

## 6 · Los referentes, que el intake ya había leído bien

De [[06-referentes-externos]] §A:

> **Ninguna app de escritorio de agentes empareja la máquina con un código.**
> Cowork tiene la misma arquitectura que Nexus —sesión en la nube, archivos vía
> la app, «only for the folders you've connected»— y el vínculo es el login.
> RFC 8628 es para dispositivos sin navegador; con navegador local el código es
> fricción, y además abre superficie (phishing de device code, Storm-2372).

Merece subrayarse lo último, porque cambia el signo del argumento de seguridad:
**el código no solo no protege — el patrón de «teclea este código» es en sí un
vector**, el que Storm-2372 explotó. Retirarlo no es aceptar un riesgo a cambio
de comodidad. Es retirar uno.

Y el sitio donde el acto deliberado sí tiene que estar, que es la otra mitad del
intake: la carpeta. `link_declared` ya existe (`POST /device/links`,
`device_bridge.py:574`) con su asiento de auditoría y su denegación
(`device.link_declared` / `device.link_denied`). **La pieza buena ya está
construida y enterrada** debajo de la ceremonia que sobra.

---

## 7 · Lo que esta fase deja decidido, y lo que es de la puerta

**Decidido por el código:**

- El código no aporta un factor que la sesión no dé (§0). La pregunta central
  del intake está contestada y la respuesta es «nada».
- El camino de sustitución existe, se usa y tiene test (§2).
- Mover el permiso al canje es mover, no crear (§3).
- No se abre ningún puerto ni se enmienda ningún requisito de aislamiento, a
  diferencia de la 009 (§4).
- Conservar del código retirado: **uso único, hash, rechazo indistinguible y
  límite de intentos**. La 009 ya dejó esa lista escrita (§4).

**Lo que decide la puerta:**

1. **Qué significa «sesión recién confirmada»** para el canje, y si hace falta.
   Es la única diferencia real que queda en pie (§0), y su respuesta es un
   umbral, no una ceremonia.
2. **Si el registro silencioso trae consigo cerrar los tres huecos** —
   revocación de verdad al desemparejar, asiento de auditoría en los dos
   extremos, y límite de máquinas (§5). Recomendación de esta fase: **sí, los
   tres**, porque la fricción que se retira era el límite de facto.
3. **Si se conserva el código para el caso «emparejar una máquina que no es la
   tuya»** (servidor, máquina compartida). El intake pedía confirmar si ese caso
   existe; **el código no lo sabe** — es una pregunta para Luis, no para el
   repositorio.
4. **Qué pasa al desemparejar y volver a entrar**: ¿se registra sola otra vez?
   Con registro por sesión la respuesta por defecto es «sí», y hay que decidir
   si eso es lo que se quiere o si desemparejar debe ser pegajoso.
5. **Cruce con `recuperar-la-contrasena`**: si restablecer la contraseña
   invalida las credenciales de máquina. Las dos evaluaciones tienen que
   contestar igual o se contradicen, y hoy **ninguna de las dos piezas de
   revocación existe** (allí, cerrar todas las sesiones; aquí, revocar de
   verdad).

---

## 8 · Lo que no se comprobó

- **Si el caso de la máquina ajena existe de verdad** en la operación de
  Auphere. Decide si el código se retira o se conserva como camino secundario.
- **Cuántas máquinas hay registradas hoy por persona** en producción. Da la
  medida de si el límite es teórico o ya hay alguien con seis.
- El comportamiento real del `SessionGate` cuando la cookie caduca **durante**
  el registro. Hay tests de la puerta (`session-gate.test.ts`) pero no de esa
  carrera concreta.
