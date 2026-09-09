# Fase 1 — Guía de validación

**Rama**: `001-puesto-trabajo-partner` · **Fecha**: 2026-09-09

Cómo se comprueba que esto funciona, en el orden en que hay que comprobarlo. No
lleva implementación: eso es de `tasks.md`.

---

## Antes de nada: las dos puertas

**Ninguna tarea que dependa de los Requisitos 5 u 11 arranca hasta que estas dos
estén en verde.** Van primero porque son las dos apuestas del plan, y salir de
dudas cuesta horas mientras que descubrirlo tarde cuesta el plan entero.

### Puerta 1 — ¿se puede contener el catálogo? (`T001`, Requisito 5)

**Preparación**: máquina con el CLI `claude` **y** con servidores MCP ajenos
declarados en `~/.claude.json` — hace falta un caso sucio, no uno limpio. Un
directorio desechable con `KIROCREW_HOME`, `KIRO_HOME` y `KIROCREW_WORKSPACE`
redirigidos y `KIROCREW_TELEMETRY_DISABLED=1` puesto **antes** del primer arranque.

**Qué se hace**: apuntar `CLAUDE_CODE_EXECUTABLE` a un envoltorio que añada
`--strict-mcp-config`, abrir una sesión y pedir al agente que enumere sus
herramientas.

**Se pasa si** las dos cosas a la vez:
- el catálogo **no** contiene ninguno de los servidores ajenos, y
- el catálogo **sí** contiene las herramientas propias de Crew.

Contrástese con el árbol de procesos del gateway: no basta con que el agente no las
liste, es que sus procesos no deben estar vivos.

**Si falla**: se detiene el plan. La edición tendría que intervenir el lanzamiento
del harness, que es lo primero que obligaría a tocar el núcleo — y entonces se
aplica el repliegue escrito en la evaluación.

### Puerta 2 — ¿puede la app contestar una aprobación de subagente? (`T002`, Requisito 11.1)

**Qué se hace**: con la cáscara de escritorio conectada como cliente de dashboard,
lanzar un subagente y contestar su aprobación desde la aplicación.

**Se pasa si** el subagente **corre**, y su estado mostrado coincide con lo
ocurrido. Compruébese explícitamente el rechazo también: la evaluación observó un
`✅` para un subagente que en realidad había sido rechazado, así que hay que
verificar que **nuestra** pantalla no hereda esa mentira.

**Si falla**: se retira el Requisito 11 y la beta 2 entrega ejecución de un solo
agente. No se intenta ninguno de los tres remedios que sugiere su mensaje de error:
la evaluación comprobó que **no existen** en su código.

---

## Validación de la composición

```bash
# La edición compone sin tocar el núcleo
kirocrew doctor          # espera: edition: ✅ enterprise
git -C <clon del sustrato> status --porcelain   # espera: VACÍO
```

Esa segunda línea es la que importa: **cero archivos modificados** es la frontera
entre componer y forkear. Si algún día imprime algo, el plan se ha salido de su
opción.

---

## Validación por requisito

| Qué se prueba | Cómo | Se pasa si |
|---|---|---|
| **R1** Directorio fijado | Pedir una ejecución con `cwd` que escape por `..` o por enlace simbólico | Se deniega, con `fuera_del_directorio` |
| **R2** Lista blanca | Pedir un ejecutable ausente de la lista | Se deniega y **no** aparece como decisión aprobable |
| **R2.3** Argumentos | Pedir argumentos nuevos de un ejecutable permitido | Pide aprobación; al concederla queda `decided_by` en la auditoría |
| **R2.4** Metacaracteres | `args` con tubería, `&&`, subshell o redirección | Se deniega, aunque el ejecutable esté permitido |
| **R3** Contención | La suite de los seis ataques, en macOS **y** en Windows | **12 de 12**. Un `skip` puntúa como aprobado y por tanto no cubre nada (§VII) |
| **R4** Presencia | Desconectar la máquina a mitad de tarea | El estado aparece en menos de un minuto y las herramientas locales salen del catálogo del turno siguiente |
| **R5** Catálogo | Puerta 1, y después como test de aislamiento permanente | `test_26` en verde |
| **R6** Puente | Escanear puertos de la máquina del partner con la aplicación corriendo | Ningún puerto a la escucha por nuestra causa |
| **R7** Aprobaciones | Una acción que toca a un cliente final | Pasa por `companion.actions`, no por el gate del sustrato |
| **R8** Auditoría | Una ejecución y una denegación | Ambas con tenant, dispositivo y motivo. `test_27` en verde |
| **R11** Subagentes | Puerta 2 | El estado mostrado coincide con el real, también en el rechazo |
| **R12** Techos | Lanzar algo que no termina; y cerrar la sesión con hijos vivos | Se termina el **árbol** al vencer el límite; cero huérfanos al cerrar |

---

## Suites que bloquean

```bash
cd apps/api && uv run pytest tests/isolation/ -x
```

Tres tests nuevos: `test_26_local_tool_catalog_exhaustive.py`,
`test_27_local_execution_audit_tenant_tagged.py` y
`test_28_local_allowlist_device_rls.py`. **Rojo bloquea el merge**, como cualquier
otro test de aislamiento. El número 25 queda reservado a la VM compartida de la
beta 5.

---

## Lo que esta guía NO valida, y hay que recordar

- **Los certificados de firma y notarización**: tienen plazo de entrega, se piden
  aparte y no los produce este plan. Sin ellos el Requisito 9 no se puede probar en
  una máquina real.
- **El rebranding**: la superficie visible está medida, el trabajo no. Y como no
  hay una constante central de marca, cada actualización aguas arriba puede
  reintroducir marcas donde el partner las vea. Es vigilancia recurrente, no una
  tarea que se cierra.
