# Fase 1 — Modelo de datos: la experiencia de la aplicación de escritorio

**Spec**: [spec.md](./spec.md) · **Plan**: [plan.md](./plan.md)

Esta spec **no crea tablas ni migraciones**. Todo lo que aparece aquí es una de
dos cosas: un **derivado** de datos que ya existen (para que una misma verdad se
cuente igual en todas partes), o una **preferencia local** de la ventana. Por eso
no hay entidad con `tenant_id`: lo que la aplicación lee llega por el BFF con la
sesión de la persona, y la RLS ya decidió antes.

---

## 1. Derivados (lógica pura, con test, sin estado propio)

### 1.1 `Waiting` — «lo que te espera»

| Campo | Tipo | Regla |
|---|---|---|
| `count` | entero ≥ 0 | **La única cifra**. La consumen lista lateral, icono de la aplicación, icono de la barra del sistema y Pendientes |
| `items[]` | `{action_id, teammate_id, level, since}` | Lo que espera **a esta persona** |

- **Origen**: la misma lectura de Pendientes que ya existe.
- **Regla que se unifica**: hoy la pestaña cuenta todo, el icono de la barra
  excluye lo informativo y corta en «9+», y el icono de la aplicación excluye lo
  informativo sin tope. A partir de ahora **hay una definición** —lo que espera
  una decisión— y las presentaciones (tope visual, texto) son decoración de la
  misma cifra.
- **Transición**: al decidir, `count` baja en las cuatro superficies **a la vez**.

### 1.2 `WorkstationState` — el puesto

Forma completa en [`contracts/desktop-app-ipc-v2.md`](./contracts/desktop-app-ipc-v2.md).
Lo relevante como modelo:

| Campo | Novedad | Por qué |
|---|---|---|
| `status` | `comprobando` añadido a los ocho existentes | No decir «no emparejada» antes de saberlo |
| `since` | nuevo | Poder decir desde cuándo |
| `cause` | nuevo: `sin_red` · `sin_ejecutor` · `sesion_perdida` · `desconocida` | Que `reconectando` deje de ser perpetuo y mudo |
| `actions[]` | derivado del estado | La acción disponible se calcula, no se escribe a mano en cada superficie |

**Invariante**: todas las superficies pintan **este** objeto. Si la consola dice
«máquina emparejada» y el armazón dice «reconectando», no es un desacuerdo: son
dos hechos distintos (emparejada ≠ conectada) y el texto lo dice así.

### 1.3 `SetupChecklist` — la puesta en marcha

| Paso | Estado derivado de |
|---|---|
| `cuenta_lista` | hay sesión y pertenencia a partner |
| `maquina_emparejada` | `WorkstationState.status` |
| `ejecutor_presente` | `WorkstationState.cause ≠ sin_ejecutor` |
| `primer_teammate` | el roster tiene al menos uno |
| `primer_turno` | existe al menos un turno terminado |
| `avisos_concedidos` | permiso del sistema operativo |

Cada paso lleva la sección a la que lleva su acción, o el motivo por el que está
bloqueado (por ejemplo, el plan). **No bloquea nada**: es una lectura.

### 1.4 `Connectivity`

`online` · `offline` · `unconfirmed`, con `since`.

**La distinción que hoy no existe**: `unconfirmed` significa «no pude preguntar»
y **conserva el último veredicto de sesión**; hoy una excepción se convierte en
«nadie ha iniciado sesión» y echa a la persona al inicio de sesión sin red.

### 1.5 `SignInState` y `HandoffState`

Estados de la espera cuando algo ocurre en el navegador: `idle`, `esperando`,
`vuelto`, `cancelada`, `caducada`, `error`. `HandoffState` añade `kind`
(`sign_in` o `payment`) y, al volver, dispara la relectura de plan y consumo.

### 1.6 `UpdateState`

`idle` · `descargando` · `lista` · `esperando_trabajo`. Ortogonal al puesto: una
versión lista no cambia el estado de la máquina.

**Dónde vive «esta versión ya no se admite»**: en el **puesto**
(`version_no_admitida`, con `required_version`), no aquí. Describe que la máquina
no puede trabajar, no el ciclo de una descarga. Es la aplicación de la regla «un
hecho, un mecanismo»: si estuviera en los dos sitios, dos superficies podrían
contarlo distinto.

---

## 2. Preferencias locales de la ventana

| Clave | Valor | Regla |
|---|---|---|
| `windowBounds` | posición y tamaño | Ya existe; se corrige contra las pantallas actuales |
| `section` | última sección canónica | **Nueva**: se restaura al reabrir |
| `sidebarWidth` | entero acotado | **Nueva** |
| `theme` | `system` · `light` · `dark` | Ya está permitida; ahora se usa y arrastra a la consola |
| `silenceAviso` | booleano | Ya existe el canal; ahora tiene pantalla |

**Invariante de seguridad**: la lista de claves persistibles es cerrada y **no
admite credenciales**; su test ya existe y se amplía con las claves nuevas.

---

## 3. Vocabulario (glosario único)

| Se dice | No se dice |
|---|---|
| teammate | agente, Companion (al hablar del interlocutor de la persona) |
| pool semanal, consumo incluido de la semana | tope mensual |
| puesto de trabajo, esta máquina | el puente, el gateway |
| pendiente, decisión que te espera | acción requerida |
| sin conexión | sin sesión (cuando es red) |

El paquete compartido del hilo recibe **el nombre del interlocutor** por contexto,
para que en la aplicación diga el nombre del teammate y en la consola siga
diciendo Companion.

---

## 4. Tokens: pares que el test de contraste vigila

| Par | Umbral | Hoy |
|---|---|---|
| texto principal / fondo (claro y oscuro) | 4,5:1 | pasa |
| texto apagado / fondo y / tarjeta | 4,5:1 | **3,83:1 en tarjeta oscura** |
| aviso / fondo claro | 4,5:1 | **2,97:1** |
| peligro / tarjeta oscura | 4,5:1 | **1,24:1** |
| anillo de foco / fondo claro | 3:1 | **2,09:1** (1,46:1 con la variante translúcida) |
| punto de estado / fondo | 3:1 | **2,09:1–2,69:1** |

El test recorre esta tabla en ambos temas y **falla** por debajo del umbral. Es
la garantía de que R2.4 no se degrada con el tiempo.

---

## 5. Estados por pantalla — la tabla que hace comprobable «la pantalla no miente»

`L` cargando · `V` vacío · `E` error · `P` parcial · `R/O` reconectando u offline
· `B/T` bloqueado o tope. Cada celda es un caso de test; **cada estado lleva su
salida** (acción o a quién pedirla).

| Pantalla | L | V | E | P | R/O | B/T | Salida en el peor caso |
|---|---|---|---|---|---|---|---|
| Armazón (ventana) | armazón pintado | — | «no se pudo cargar la sección» | — | banner sin conexión + reintento | versión no admitida | Reintentar · Actualizar |
| Hoy | esqueleto | primer uso: qué hacer | error por tarjeta, el resto vive | lo que sí cargó | sin conexión | plan sin capacidad | Cada tarjeta con su acción |
| Lista lateral | esqueleto | sin teammates: crear | error con reintento | — | estado del puesto visible | — | Crear teammate |
| Pendientes | esqueleto | «nada te espera» | error con reintento; **fallo al decidir se dice** | lista posiblemente desfasada, dicho | sin conexión | sin permiso: a quién pedirlo | Reintentar · Ver el hilo |
| Hilo | «abriendo» | hilo vacío **solo si de verdad está vacío** | **error propio con reintento** | alcance acotado | reconectando, el trabajo sigue | pausa por consumo con una sola explicación | Reintentar · Mejorar · Comprar · Esperar hasta X |
| Turno | enviando · pensando · herramienta | — | turno fallido con motivo legible | respuesta acotada | reconectando | tope | Detener · Reintentar |
| Cuenta | esqueleto | sin consumo aún | error con reintento | equipo ilegible sin tumbar la pantalla | — | plan, saldo y reinicio visibles | Ver planes · Comprar saldo · a quién pedirlo |
| Puesta en marcha | esqueleto | todo hecho: se felicita y se sale | error por paso | pasos parcialmente leídos | — | paso bloqueado por plan | Acción por paso |
| Puesto (pie del sidebar) | `comprobando` | — | último error con motivo | directorios pendientes | `reconectando` **con causa** | versión no admitida | Emparejar · Directorios · Actualizar |
| Secciones de administrar | esqueleto de la consola | lo de la consola | «no se pudo cargar» con reintento | — | sin conexión | sin permiso: no se ofrece | Reintentar |
| Nuevo teammate | carga de oficios | sin modelos: a quién pedirlo | fallo conserva lo escrito | — | — | **el tope se dice antes de rellenar** | Ver planes · a quién pedirlo |
| Entrar | — | — | error con reintento | — | sin conexión | — | Reintentar · Copiar enlace · Cancelar |

---

## 6. Lo que este modelo **no** introduce

- Ninguna tabla, columna ni migración.
- Ningún dato de cliente final en la máquina.
- Ninguna cifra absoluta del pool (004 R7): solo proporción y fecha de reinicio.
- Ningún dato de tarjeta, en ningún sitio.
- Ningún identificador interno visible a la persona.
