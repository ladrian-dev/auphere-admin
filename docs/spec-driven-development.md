# Spec-Driven Development en Nexus

**Regla del repositorio, en una frase: en este repo no entra código sin una
especificación aprobada detrás.**

Adoptado el 2026-09-08. Aplica a `nexus` entero — plataforma, consola, companion
y teammates — y a todo el trabajo a partir de esa fecha. El método es
[GitHub Spec Kit](https://github.com/github/spec-kit) (MIT) sobre las plantillas
propias de este repo, con los criterios de aceptación escritos en **EARS**, el
formato de las specs de Kiro.

---

## 1. Por qué

Un plan escrito en el chat se pierde con la sesión. Un plan escrito en un `.md`
suelto envejece sin que nadie se entere. Lo que este método añade no es
ceremonia: es que **la spec sea el artefacto contra el que se compila**, con
trazabilidad de cada tarea a su requisito y de cada requisito a su test.

Y hay una razón específica de esta plataforma. Aquí el coste de una pieza no lo
fija la pieza: lo fija **qué frontera de confianza abre**. Ese cálculo hay que
hacerlo antes de escribir código, en un documento que alguien pueda discutir.
Eso es la spec.

---

## 2. La regla dura, y sus tres excepciones

> Todo cambio de comportamiento del producto empieza por `/speckit-specify` y
> pasa por `/speckit-plan` y `/speckit-tasks` antes de tocar código.

Tres excepciones, y son las únicas:

| Excepción | Qué es | Qué se exige igualmente |
|---|---|---|
| **Hotfix P0** | Producción caída o datos en riesgo | Se arregla primero. La spec retroactiva se escribe **en las 48 h siguientes**, o se revierte |
| **Cambio trivial** | Typo, versión de dependencia sin cambio de comportamiento, formato, comentario | Nada. No es un cambio de comportamiento |
| **Spike acotado** | Investigación con tiempo tasado y una pregunta escrita | Va por el flujo `assess` (§4). **Su código no se fusiona a `develop`**: el spike responde una pregunta, no entrega producto. Lo que sí viaja es el documento — `.specify/assessments/<slug>/` es la memoria de por qué se dijo que sí o que no |

Un bug **no** es excepción: tiene su propio flujo
(`/speckit-bug-assess` → `/speckit-bug-test` → `/speckit-bug-fix`), que es una
spec con menos ceremonia.

---

## 3. Las tres capas

Se copian de cómo lo hace KiroCrew, que es el ejemplo mejor construido que
encontramos de esto aplicado a un repo grande.

| Capa | Responde a | Dónde vive | Cuándo se escribe |
|---|---|---|---|
| **Evaluación** (`assess`) | ¿Esto se construye siquiera? | `.specify/assessments/<slug>/` | Antes de comprometer nada. Termina en *go* o *kill* |
| **Spec de cambio** | ¿Qué se construye, cómo y en qué tareas? | `specs/NNN-<slug>/{spec,plan,tasks}.md` | Antes del código. Es lo que este documento gobierna |
| **Spec viva** | ¿Qué existe hoy? | `docs/` — junto a `architecture/` y los contratos | Se actualiza **en el mismo commit** que cambia lo que documenta |

La tercera es la que casi todo el mundo se salta y la que evita que la
documentación mienta. La regla: **si cambias lo que un documento describe, el
documento va en el mismo commit.** Un PR que cambia comportamiento documentado y
no toca su documento se devuelve.

---

## 4. El flujo

```
              ¿se construye?                    ¿qué y cómo?                     ejecutar
   idea ──► /speckit-assess-* ──► go ──► /speckit-specify ──► /speckit-clarify ──► /speckit-plan
                    │                                                                  │
                   kill                                                     /speckit-tasks
              (cerrado con                                                             │
               su razón)                                                    /speckit-analyze
                                                                                       │
                                                                          /speckit-implement
```

| Comando | Produce | Regla |
|---|---|---|
| `/speckit-constitution` | `.specify/memory/constitution.md` | Se toca poco y por enmienda razonada |
| `/speckit-specify` | `specs/NNN-slug/spec.md` + rama `NNN-slug` | **El qué y el porqué.** Sin stack, sin API, sin código |
| `/speckit-clarify` | Respuestas dentro de la spec | Obligatorio si queda una sola marca `[NEEDS CLARIFICATION]` |
| `/speckit-plan` | `plan.md`, contratos, modelo de datos | **El cómo.** Rellena la tabla de Constitution Check entera |
| `/speckit-tasks` | `tasks.md` | Cada tarea con `_Requisitos: N.m_` |
| `/speckit-analyze` | Informe de consistencia | Spec, plan y tareas tienen que decir lo mismo |
| `/speckit-implement` | Código | Ejecuta las tareas en orden |
| `/speckit-checklist` | Checklist de calidad | Opcional, útil en specs grandes |
| `/speckit-converge` | Tareas que faltan | Cuando el código se ha desviado de la spec |

Los comandos de las tres extensiones instaladas (§8) se escriben igual, con
guiones — no con puntos, aunque los archivos que los definen usen puntos:

| Extensión | Comandos | Para qué |
|---|---|---|
| `assess` | `/speckit-assess-intake` · `-research` · `-define` · `-shape` · `-decide` | Decidir si una idea se construye. Termina en *go* o *kill* |
| `bug` | `/speckit-bug-assess` · `-test` · `-fix` | El flujo de un bug: reproducir, fijar el test, arreglar |
| `git` | `/speckit-git-feature` · `-commit` · `-validate` · `-remote` · `-initialize` | Ramas y validación. **`-commit` no commitea nada aquí** (§8) |

### Las puertas que no se saltan

Son siete y **las define la constitución**, en su §Flujo de trabajo:
[`.specify/memory/constitution.md`](../.specify/memory/constitution.md). Ahí está
la tabla con lo que comprueba cada una y el principio del que sale.

En corto: antes de `/speckit-plan`, cero `[NEEDS CLARIFICATION]` y superficie
declarada. Antes de `/speckit-tasks`, el Constitution Check completo, el
aislamiento, las licencias y el medidor. Antes de `/speckit-implement`,
`/speckit-analyze` en verde.

> Este documento **cita** esa tabla, no la copia. Dos copias de una lista de
> puertas divergen — de hecho estas dos ya habían divergido en una fila el mismo
> día que se escribieron. Si una puerta cambia, cambia en la constitución.

---

## 5. Cómo se escriben los requisitos: EARS

Los criterios de aceptación se escriben en **EARS**, igual que las specs de
Kiro. Una frase, un verbo normativo, comprobable, y se convierte en un test.

```
WHEN  <disparador>              THEN el sistema DEBE <respuesta observable>
IF    <condición no deseada>    THEN el sistema DEBE <respuesta>
WHERE <característica presente> EL   sistema DEBE <respuesta>
WHILE <estado>                       el sistema DEBE <respuesta>
      El sistema DEBE <respuesta>    (ubicuo, sin disparador)
```

Numeración jerárquica: **Requisito N**, criterio **N.m**. Las tareas citan
`_Requisitos: 2.1, 3.4_`. Esa cadena — requisito → tarea → test → PR — es toda
la trazabilidad que este método pide, y es innegociable.

Ejemplo real, de la spec del gate de aprobación de KiroCrew:

> 1. WHEN un agente emite una llamada a herramienta THEN el sistema DEBE
>    evaluarla en el gate ANTES de que la herramienta se ejecute.
> 2. IF el gate no puede verificar el comando de un shell THEN la llamada DEBE
>    denegarse, y NO DEBE aparecer como decisión pendiente aprobable.

---

## 6. Dónde vive cada cosa

```
nexus/
├── .specify/
│   ├── memory/constitution.md          # los 9 principios. La ley
│   ├── templates/overrides/            # NUESTRAS plantillas (EARS, puertas)
│   ├── extensions/{assess,git,bug}/    # flujos de evaluación, ramas y bugs
│   └── assessments/<slug>/             # evaluaciones: go / kill
├── specs/NNN-<slug>/
│   ├── spec.md                         # qué y por qué
│   ├── plan.md                         # cómo, con el Constitution Check
│   ├── tasks.md                        # tareas con _Requisitos: N.m_
│   └── contracts/, data-model.md       # cuando aplican
├── docs/                               # spec viva de lo que existe
└── .claude/skills/speckit-*            # los comandos (NO se versionan: .claude/ está en .gitignore)
```

**`.claude/` y `CLAUDE.md` están en `.gitignore` en este repo.** Los comandos y
las reglas locales del agente **no viajan con el repo**: cada máquina los instala
(§8). Lo que sí viaja y es la fuente de verdad del proceso es `.specify/`,
`specs/` y este documento.

### El puente con la KB, obligatorio en las dos direcciones

La KB del vault (`/Users/lmatos/Work/Auphere/`) sigue siendo dueña del **porqué**:
investigación, decisiones, ADRs y roadmap. El repo guarda lo que el código lee o
contra lo que se compila: contratos congelados, `capabilities.yaml` y los
artefactos de spec.

- Toda `spec.md` cita en su encabezado la nota de KB que la justifica.
- Toda decisión de KB que se implemente enlaza a su carpeta `specs/NNN-*/`.

Una spec sin nota de KB detrás es una spec que nadie ha justificado. Una decisión
de KB sin spec delante es una decisión que nadie ha ejecutado.

---

## 7. Relación con las skills que ya había

`.claude/skills/` trae `writing-plans`, `executing-plans` y
`subagent-driven-development`. **No se retiran, se subordinan:**

| Situación | Qué se usa |
|---|---|
| Cambio de comportamiento del producto | **Spec Kit**, siempre. Es el proceso oficial |
| Ejecutar el `tasks.md` que ya existe | `/speckit-implement`, o `subagent-driven-development` si se quiere paralelizar por subagentes — ejecuta **las mismas tareas**, no un plan alternativo |
| Refactor interno sin cambio de comportamiento | `writing-plans` basta |
| Explorar antes de saber qué se quiere | `brainstorming`, y el resultado entra por `assess` |

La regla que resuelve cualquier duda: **`tasks.md` de la spec es el único plan de
ejecución.** Si hay dos planes, uno sobra.

---

## 8. Montar el tooling en otra máquina

```bash
uv tool install specify-cli --from git+https://github.com/github/spec-kit.git@v1.0.5
cd nexus
specify init --here --integration claude --force
specify extension add assess
specify extension add git
specify extension add bug
```

`.specify/` ya está en el repo, así que la constitución y las plantillas propias
se conservan; lo que instala el comando son las skills locales bajo `.claude/`.

**Auto-commit está desactivado** en `.specify/extensions/git/git-config.yml`
(`auto_commit.default: false`, y las dieciséis claves por comando también en
`false`) y debe quedarse así: en este equipo los commits los ejecuta la persona,
nunca la herramienta.

`.specify/extensions.yml` sí trae los ganchos `before_*`/`after_*` en `enabled:
true`, y eso confunde a primera vista. No commitean: el gancho invoca
`speckit.git.commit`, que antes de hacer nada lee `git-config.yml` y se
encuentra todo apagado. **La llave está en `git-config.yml`, no en
`extensions.yml`** — que además lo regenera la CLI al reinstalar la extensión, así
que apagarlo ahí no duraría.

---

## 9. Qué NO cambia

- Los tests de aislamiento siguen bloqueando el merge.
- `develop` → staging automático, `main` → producción. Sin cambios.
- Español para documentación, inglés para código, Conventional Commits.
- Los contratos congelados (`CONTRACT-V1.md`, `CONTRACT-V2.md`) y
  `capabilities.yaml` siguen donde están y siguen siendo la verdad para el código.

---

## Referencias

- [`.specify/memory/constitution.md`](../.specify/memory/constitution.md) — los nueve principios
- [Spec Kit](https://github.com/github/spec-kit) — el toolkit (MIT)
- KB: `/Users/lmatos/Work/Auphere/teammates/` — la investigación del producto
