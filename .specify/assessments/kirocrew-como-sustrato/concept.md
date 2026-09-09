# Concept: el puesto de trabajo del teammate en la máquina del partner

- **Slug**: kirocrew-como-sustrato
- **Created**: 2026-09-09
- **Recommended option**: **A — sustrato externo compuesto**, con **C** como forma
  de repliegue si falla su primera tarea
- **Etapa anterior**: [`problem.md`](./problem.md)
- **Superficie**: **3a** — ejecutar en la máquina del partner (Constitución §II)

> Esta etapa **esboza opciones en sus bordes**. No es una spec ni un plan: sin
> arquitectura, sin contratos, sin modelo de datos y sin tareas. Eso es de
> `/speckit-specify` en adelante.

---

## Una no-opción, dicha antes de empezar

**«Comprarlo en vez de construirlo» no existe en esta categoría.** La tabla de
licencias de `15-kirocrew-y-alternativas` §5 se leyó archivo a archivo: todo lo
que es mono-usuario y local viene con licencia permisiva, y todo lo que tiene
forma de SaaS multi-tenant viene con licencia que prohíbe exactamente revenderlo
—Suna es Elastic License 2.0, Dify prohíbe el multi-tenant, n8n es Sustainable
Use—. No es casualidad: los segundos venden la versión alojada. Y «no hacer nada»
ya está escrito como *Cost of Inaction* en `problem.md`. Quedan tres opciones
reales.

---

## Options

### Option A — Sustrato externo compuesto («edición Auphere»)

- **Sketch**: el puesto de trabajo del agente no se construye: se compone sobre un
  runtime open source Apache-2.0 fijado a un commit, a través de su propio punto
  de extensión, sin tocar su núcleo. Nexus se queda como plano de control y dueño
  de todo lo que toca datos de cliente final: las herramientas `console.*` llegan
  al agente por un servidor MCP nuestro, y las aprobaciones que afectan a un
  cliente final siguen siendo las durables de Nexus. Las del runtime se quedan solo
  para lo que pasa dentro de la máquina —un comando nuevo—. El partner ve una
  aplicación de Auphere; el sustrato no se nombra.
- **Appetite**: **medium** (semanas). La talla la sostiene el `research`: el seam
  compuso con un paquete de ~60 líneas y el núcleo quedó a **0 archivos
  modificados**. Lo que no sostiene es una fecha: el calendario hasta el criterio
  de aceptación sigue marcado `[NEEDS CLARIFICATION]` en `problem.md`.
- **Trade-offs**:
  - *Gana*: sandbox de SO, contención de escrituras en macOS y Windows,
    empaquetado firmado con autoactualización, cron con locking entre procesos,
    TaskRunner con checkpoints, subagentes, memoria con embeddings en proceso, log
    de auditoría encadenado por HMAC y gobernanza `POLICY ∩ PROFILE` — construidos
    y con tests. Es la totalidad de las ocho piezas de `14-mvp-y-fases` §3.2 salvo
    el puente saliente y la presencia de dispositivo, que son nuestros de todas
    formas.
  - *Sacrifica*: **no hay rueda pública**. `pypi.org/pypi/kirocrew` da 404 y los
    releases publican solo bundles de escritorio. La edición dependería de un wheel
    **que construimos nosotros** desde un commit fijado: mantenimiento recurrente,
    no una dependencia declarada. Se acepta un componente de Amazon en el corazón
    del diferencial, y seguir aguas arriba de un repositorio que se mueve muy
    rápido.
  - *Riesgo mayor*: el hallazgo del `research` **muerde justo en esta beta**. El
    backend hereda los servidores MCP del usuario de la máquina, y en la beta 2 esa
    máquina es la del partner. La mitigación —un envoltorio con
    `--strict-mcp-config` apuntado por `CLAUDE_CODE_EXECUTABLE`— está identificada
    y **sin verificar**.
- **Rabbit holes**:
  - **El envoltorio.** Si no basta, la edición tendría que intervenir el
    lanzamiento del harness, y eso sería lo primero que obligue a tocar el núcleo:
    A deja de ser composición y se convierte en el camino C de la KB, que ya está
    descartado. Por eso va como **primera tarea del plan**, no como la última.
  - **Su gate de aprobación es síncrono y muere con el turno** (300 s,
    deny-on-silence, en memoria). El nuestro es un objeto de dominio durable con
    `state_hash`, caducidad e idempotencia (§IV). Convivir sin tocar el núcleo está
    por demostrar.
  - **Tres cosas que hay que apagar el primer día**: telemetría anónima encendida
    por defecto, canal de WhatsApp por protocolo no oficial —contra los ToS de
    Meta, y nosotros tenemos el oficial en producción— e instalación de apps, que
    concede privilegios completos del proceso gateway.
  - **Subagentes sin superficie de aprobación**: hoy el spawn se rechaza si ningún
    cliente puede contestar. Y sus mensajes de error recomiendan tres remedios que
    no existen en su código, así que la documentación no ayuda.

### Option B — Construirlo nosotros, cosechando el repositorio

- **Sketch**: el plan de `14-mvp-y-fases` §3.2 tal cual, sin dependencia externa en
  el producto. El repositorio se usa como cantera con atribución, que Apache-2.0
  permite: la suite de contención de los seis ataques, el modelo
  `POLICY ∩ PROFILE`, la escalera de aprobaciones, el orden de apagado y los specs
  de módulo se leen y se copian donde convenga.
- **Appetite**: **large** (meses). Son las ocho piezas de §3.2, y la séptima —la
  misma contención en Windows con rutas relativas NT— la propia KB la marca como
  más cara que en macOS.
- **Trade-offs**: gana control total, cero rebranding, cero marcas ajenas, cero
  riesgo de seguir a un tercero, y un núcleo que entendemos entero. Sacrifica
  exactamente lo que el problema pide acortar: el calendario del diferencial.
- **Rabbit holes**: la contención en Windows; la firma y notarización, que tienen
  **plazo de entrega y hoy no están** (en esta máquina solo hay certificados
  «Apple Development», que no sirven para distribuir, y los OV de Windows duran
  460 días desde marzo de 2026); y `shell_local`, que sigue siendo una decisión
  abierta (`10-decisiones` §2.7) en cualquiera de las tres opciones.

### Option C — La mitad barata de la superficie 3a

- **Sketch**: lo más pequeño que podría funcionar, y encaja con la regla de §II
  —abrir cada superficie por su mitad barata primero—. El teammate obtiene puente
  saliente, presencia de dispositivo y ejecución acotada con lista blanca en un
  directorio fijado, **sin herramientas de escritura de fichero del agente**. Corre
  el build, lee el log y propone el arreglo; quien lo aplica es la persona. Se
  aplaza la pieza más cara del recorte: la suite de contención de escrituras, con
  sus seis ataques, en macOS **y** en Windows.
- **Appetite**: **small-medium** (días a pocas semanas) para lo que entra; el resto
  no desaparece, se aplaza.
- **Trade-offs**: gana llegar antes a la mitad de la historia de §3.1 y pagar el
  precio de entrada de la 3a una sola vez. Sacrifica el «arregla y vuelve a
  correr», que es justo la mitad que convierte al teammate en uno que **hace**. Y
  concentra toda la seguridad en la lista blanca: la propia documentación de
  Anthropic dice que la contención de ficheros *no* restringe `bash`, así que una
  lista blanca floja anula la opción entera.
- **Rabbit holes**: la lista blanca se vuelve el producto —cada comando nuevo es
  una decisión de seguridad—; y el criterio de aceptación de §3.5 no se cumple, con
  lo que la beta 2 se declararía cerrada sin estarlo.

---

## El coste del rebranding, medido

El `intake` lo dejaba sin cuantificar y `research` no lo tocó. Medido sobre el clon
fijado en `37933a5` (solo aplica a la opción A):

| Zona | Ficheros con la marca | Ocurrencias | ¿Hay que cambiarlo? |
|---|---|---|---|
| Repositorio entero | 5.401 de 10.552 | 105.221 | **No.** El número asusta y engaña |
| `src/kiro_crew/` (identificadores internos) | 1.356 | 24.482 | **No.** Apache-2.0 concede el uso del código; lo que **no** concede es la marca (§6). Una ruta de importación no es uso de marca — y renombrarla garantizaría no poder seguir aguas arriba, que es justo lo que el seam existe para evitar |
| Catálogo de cadenas visibles en inglés | 2 | **17** | **Sí**, y es pequeño. El resto de idiomas deriva de aquí |
| UI (`website/src`, sin tests) | 432 | 5.926 | **Casi nada.** Dominado por nombres de componente, clases e imports, no por copy visible |
| Empaquetado e instaladores | 23 | 386 | **Sí.** Nombres de bundle, identificadores de aplicación y feeds de actualización. Es la parte que además tiene que ser correcta para firmar y notarizar |
| Rutas del data home | concentradas en `config/paths.py` | — | **Sí**, y son pocas líneas: `.kiro`, `.kirocrew`, `kirocrew-workspace`, la migajita de recuperación. Poco código, comportamiento no trivial (hay migración y un diseño que asume compartir base con la familia Kiro) |

**Conclusión, y corrige la impresión del `intake`**: el rebranding **no** es el
monstruo de 105.000 ocurrencias que sugiere el `grep`. Es una superficie visible
pequeña —el catálogo inglés, el empaquetado y un puñado de constantes de ruta—.

**Pero tiene un coste recurrente y hay que decirlo**: no existe una constante
central de marca (`PRODUCT_NAME`, `APP_NAME` o equivalente), así que cada
actualización aguas arriba puede reintroducir marcas en superficie visible. El
trabajo no es «renombrar una vez», es «renombrar y **vigilar en cada bump**».
Appetite: **small** la primera vez, **recurrente** para siempre.

---

## Recommendation

**Opción A**, y con una condición que ya está puesta en el calendario.

La razón es la asimetría que dibuja `15-kirocrew-y-alternativas` §4: ellos tienen
el puesto de trabajo del agente y nosotros tenemos el plano de control
multi-cliente, y ninguna de las dos mitades se regala. El multi-tenant con RLS, el
medidor, las aprobaciones durables y el canal oficial de WhatsApp no existen en
ninguna base open source que permita revenderla —eso es el foso, y ya está
cavado—. Lo que sí se puede componer es la otra mitad, y el `research` lo demostró
ejecutándolo, no razonándolo: el seam aguantó, el floor de seguridad quedó intacto
y el núcleo terminó a **0 archivos modificados**.

Frente a eso, **B paga con el activo escaso**: el calendario del diferencial, que
es precisamente lo que `problem.md` pide acortar. B no se descarta —se hace igual,
como cantera, y eso ya está escrito como el piso—; lo que no compensa es
construirlo entero.

**C es una opción honesta y no la recomiendo como destino**, porque bajo A su
razón de ser casi desaparece: la pieza que C aplaza —la suite de contención en dos
sistemas operativos— es exactamente la que A obtiene ya construida. C se queda
como **forma de repliegue**: si la primera tarea del plan de la beta 2 demuestra
que el envoltorio no basta y hay que tocar el núcleo, A deja de ser composición y
el camino corto pasa a ser C sobre B.

**La condición**: A entra con la verificación del envoltorio
(`--strict-mcp-config` vía `CLAUDE_CODE_EXECUTABLE`) como **primera tarea del plan
de la beta 2**. No es una formalidad de proceso: en la beta 2 el `~/.claude.json` es
del partner, y sin esa verificación la opción A entrega un agente con herramientas
que nadie puso en la lista blanca del tenant — que es lo que §I prohíbe con todas
las letras.

---

## Out of Scope (for the recommended option)

Hereda todos los *Non-Goals* de [`problem.md`](./problem.md), y añade:

- **Renombrar identificadores internos** (`kiro_crew` y compañía). Cuesta la
  capacidad de seguir aguas arriba y no lo exige la licencia.
- **Contribuir aguas arriba** o comprometerse a hacerlo. Puede convenir; no es
  parte de esta decisión.
- **El canal de WhatsApp del sustrato.** Protocolo no oficial, contra los ToS de
  Meta, y nosotros tenemos el oficial en producción. Apagado, no adaptado.
- **El cargador de apps del sustrato.** Instalar una app concede privilegios
  completos del proceso gateway. Apagado.
- **Su telemetría.** A cero desde antes del primer arranque.
- **Su gate de aprobación como sustituto del nuestro.** Se queda para lo que pasa
  dentro de la máquina; nada que toque a un cliente final pasa por él.

---

## Assumptions to Validate

Cada una es una suposición de la que depende la recomendación. La primera es la
única que puede tumbarla.

1. **Un envoltorio con `--strict-mcp-config` deja el catálogo solo con las
   herramientas de Crew, y Crew sigue viendo las suyas.** Si no, A deja de ser
   composición. *Primera tarea del plan de la beta 2.*
2. **Un wheel construido desde un commit fijado se instala y se reproduce** en
   macOS y en Windows, y ese proceso es automatizable — porque no hay rueda
   pública y esto se repetirá en cada bump.
3. **Las dos escaleras de aprobación conviven sin tocar el núcleo**: la suya,
   síncrona y dentro del turno, para lo de la máquina; la nuestra, durable y
   auditada con `decided_by`, para todo lo que toque a un cliente final.
4. **La cáscara de escritorio puede ser la superficie que contesta las
   aprobaciones de spawn**, o los subagentes no arrancan en la beta 2.
5. **El rebranding se sostiene en la superficie visible** y los bumps aguas arriba
   no reintroducen marcas donde el partner las vea sin que nadie se entere.
6. **Los certificados de distribución llegan a tiempo.** No depende del sustrato
   —es de las dos opciones— y tiene plazo de entrega. Se pide cuando arranca la
   beta 1.
7. **El aislamiento del sustrato se fija con las tres variables**, no con una:
   `KIROCREW_HOME` no gobierna el workspace del agente. Durante el `research` el
   home real se materializó dos veces, una de ellas con un simple `--version`.

---

**Siguiente etapa**: `/speckit-assess-decide slug=kirocrew-como-sustrato`
