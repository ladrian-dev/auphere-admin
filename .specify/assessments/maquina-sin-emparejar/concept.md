# Concept: la máquina se registra con la sesión, sin código

- **Slug**: maquina-sin-emparejar
- **Fecha**: 2026-09-22
- **Entrada**: [`problem.md`](./problem.md) · [`research.md`](./research.md)

---

## El eje que separa las opciones

El research contestó la pregunta que el intake declaró central —qué protege el
código que la sesión no proteja— y la respuesta fue **nada**, con una excepción
de una sola línea: **la cookie puede estar ahí de antes; teclear un código es
siempre un acto del momento.**

Así que el eje no es «código sí o no». Es:

> **¿Cuánta frescura hay que exigirle a la sesión para que emitir una credencial
> de máquina sea un acto deliberado y no un efecto de haber abierto la app?**

Las opciones se ordenan por esa respuesta, de «ninguna» a «tanta como un código».

---

## Options

### Opción A — Registro silencioso al entrar

Entrar deja la máquina lista. La app, con sesión confirmada, pide la credencial
al BFF con la cookie de la partición humana; el BFF comprueba `workstation:pair`
y devuelve la credencial una vez. Sin diálogo, sin pantalla.

**Cómo se construye, con lo que ya hay:**

| Pieza | De dónde sale |
|---|---|
| La llamada desde la cáscara | `session.fromPartition(HUMAN_PARTITION).fetch(…)` — ya en uso en `electron/main.ts:665-671` |
| La ruta del BFF | La forma de `/api/desktop/redeem/route.ts`, con una diferencia: ésta **sí** devuelve cuerpo |
| La comprobación del permiso | `workstation:pair` ya existe y ya se comprueba en seis sitios. Aquí se **mueve**, no se crea |
| Emitir la credencial | `services/device_credential.py` sin tocar |
| Alta de la máquina | `PartnerDeviceRepository.pair()` sin tocar |

**A favor**: es lo que hacen los referentes; retira un vector conocido
(Storm-2372) en vez de aceptar uno; no abre ningún puerto —a diferencia de la
009, que tuvo que aflojar `no-inbound.test.ts`—; el camino ya está abierto y
tiene test.

**En contra**: no responde a la única diferencia real. Una cookie de siete días
en una partición persistente significa que **abrir la app en una máquina donde
alguien entró hace seis días registra esa máquina sin que nadie decida nada
hoy**.

---

### Opción B — Registro silencioso, con sesión recién confirmada

Igual que A, pero el canje exige que la sesión se haya confirmado hace poco. Si
no, la app manda a entrar por el navegador —el flujo RFC 8252 + PKCE que la 009
ya construyó— y al volver, la máquina se registra.

**A favor**: contesta la única objeción que quedaba en pie, y la contesta en su
propio terreno —frescura de sesión— en vez de con una ceremonia que no mide eso.
Reutiliza un flujo ya construido y ya probado. El acto deliberado sigue siendo
uno solo, y es el que ya se hace: entrar.

**En contra**: hay que elegir un umbral, y todo umbral es arbitrario hasta que
se justifica. Y en el caso normal —instalar y entrar— es idéntico a A, así que
el coste extra solo se paga en el caso raro.

**El umbral, en concreto**: la sesión ya lleva `last_used_at`
(`db/models/console_identity.py:99`), así que no hace falta nada nuevo para
saber cuándo se confirmó por última vez. Lo que sí hace falta es distinguir
«confirmada» de «usada», que no es lo mismo.

---

### Opción C — Se retira el código de la app, pero se conserva en la consola

Registro por sesión como camino normal, y el código sobrevive para el caso de
emparejar una máquina que no es la tuya: un servidor, una máquina compartida.

**A favor**: no cierra una puerta antes de saber si alguien la usa.

**En contra**: **mantiene entero lo que se quería retirar** —la tabla, el
diálogo, el límite de intentos, el alfabeto duplicado en cliente— para un caso
que nadie ha confirmado que exista. Dos caminos para lo mismo es dos caminos que
mantener, dos que auditar y dos por los que entrar.

**El intake ya lo dejó condicionado**: «se conserva el código solo si existe el
caso… **Hay que confirmar si existe**». Sigue sin confirmarse, y eso no lo
contesta el repositorio.

---

### Opción D — No hacer nada

**A favor**: cero código.

**En contra**: el primer uso sigue costando doce pasos frente a los 3-4 del
listón, por una ceremonia que no protege nada. Y —esto es lo que D no puede
alegar a su favor— **los tres huecos del §5 del research siguen abiertos igual**:
la revocación rota, la auditoría a medias y la ausencia de límite no son efectos
de retirar el código. Ya están.

---

## Decisiones transversales — no son opciones, hay que tomarlas igual

Las tres salen del research §5 y **ninguna depende de qué opción se elija**.
Están rotas hoy, con el código puesto.

### T-1 · Desemparejar tiene que revocar de verdad

Hoy `unpair()` solo olvida la credencial localmente
(`app-runtime.ts:368-376`). La fila sigue viva y el JWT vale hasta 12 h. La
copia de la app dice otra cosa.

Con registro silencioso esto pasa de incómodo a incoherente: si volver a
registrar es gratis, desemparejar tiene que significar algo. **Archivar ya
existe** (`repositories/local_workstation.py:126-136`) y el motivo
`"desemparejada"` está declarado sin escritor: es llamarlo desde el sitio que
falta.

### T-2 · Los dos extremos dejan asiento

`device.unpaired` está en el vocabulario desde la migración
`0108_device_audit_vocab.py:66` y **nadie lo escribe**. Registrar deja cinco
asientos; retirar, ninguno. Si el registro pasa a ser silencioso, la auditoría
es lo único que queda para contar la historia — y hoy le falta la mitad.

### T-3 · Límite de máquinas

No existe ninguno (buscado en `apps/`, `specs/`, `docs/`). El límite práctico
era la fricción de pedir un código. **Retirarla sin poner un tope es quitar el
único freno que había.** Hay que elegir el número y qué pasa al pasarlo.

### T-4 · El acto deliberado sube a la carpeta

Es la mitad buena del intake y no requiere construir casi nada:
`POST /device/links` ya existe con sus asientos (`device.link_declared` /
`device.link_denied`). Lo que falta es que **se vea**: hoy está enterrado y la
ceremonia está sobre la caja.

### T-5 · Coherencia con `recuperar-la-contrasena`

Si restablecer la contraseña cierra las sesiones, ¿revoca también las máquinas?
Las dos evaluaciones tienen que contestar igual. Hoy **ninguna de las dos piezas
de revocación existe**, así que es el momento de decidirlo una vez.

---

## Recommendation

**Opción B**, con T-1, T-2, T-3 y T-4 dentro del alcance, y T-5 decidido a la
vez que la otra evaluación.

### Por qué B y no A

Porque A deja en pie la única objeción honesta, y deja en pie precisamente la
que el intake pidió no responder por analogía. Una cookie de siete días en una
partición persistente no es un acto del momento, y registrar una máquina sí
debería serlo. B contesta eso **sin reintroducir la ceremonia**: reutiliza el
flujo de entrar, que ya existe, ya está probado y es el estándar que la 009
adoptó a propósito.

Y en el camino que importa —instalar y usar por primera vez— B **es** A: la
sesión se acaba de confirmar, así que no hay paso extra. El coste solo se paga
donde debe pagarse.

### Por qué no C

Porque conserva entero lo que se quería retirar, por un caso que nadie ha
confirmado. Si el caso existe, se reabre; reabrirlo después es barato, y
mantener dos caminos mientras tanto no lo es.

### Lo que B hereda de la 009 sin discusión

`specs/009-…/spec.md:64-65` ya dejó la lista al retirar el otro código: **uso
único, hash, rechazo indistinguible y límite de intentos**. Todo eso hace la
misma falta aquí, aplicado al canje nuevo: una credencial de máquina se emite
una vez, el fallo se responde igual sea cual sea, y hay techo de intentos.

### Y la lección que ADR-039 se escribió a sí mismo

> Preguntarse **«¿cómo resuelve esto la industria?»** antes de inventariar
> opciones propias… Dos enmiendas en un día salen de ahí.

Esta vez se preguntó primero. La respuesta —§A del informe de referentes— es que
**ninguna app de escritorio de agentes empareja la máquina con un código**, y
que el que más se parece a Nexus en arquitectura, Cowork, ata la máquina con el
login. Eso no es una analogía: es la misma forma de sistema.

---

## Out of Scope (para la opción recomendada)

- Mover la ejecución del agente a la máquina.
- Rediseñar la credencial de máquina o su renovación.
- Tocar el inicio de sesión (la 009 ya lo resolvió).
- Segundo factor.

---

## Assumptions to Validate

1. **Que no existe el caso de la máquina ajena.** Si existe, la Opción C vuelve
   a la mesa. Es una pregunta para Luis, no para el código.
2. **Que la sesión sabe cuándo se confirmó**, no solo cuándo se usó. `last_used_at`
   existe; «confirmada» puede no ser lo mismo y hay que mirarlo antes de fijar
   el umbral.
3. **Que nadie tiene hoy tantas máquinas que un límite razonable le rompa el
   trabajo.** Consulta a producción, barata.
4. **Que archivar al desemparejar no rompe nada del flujo de reinstalar.** Si
   archivar es terminal —y lo es: «Borrar no existe: se archiva, y queda por
   qué»— hay que comprobar que volver a registrar crea una fila nueva sin
   tropezar con la archivada.
