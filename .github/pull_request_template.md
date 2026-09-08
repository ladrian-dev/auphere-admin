<!--
  Este repo corre sobre Spec-Driven Development desde el 2026-09-08.
  El método está en docs/spec-driven-development.md y la ley en
  .specify/memory/constitution.md. Borra las secciones que no apliquen,
  pero borrar una es una decisión: di por qué en una línea.
-->

## Qué cambia

<!-- Una o dos frases. El qué, no el cómo. -->

## Spec que lo respalda

- **Carpeta**: `specs/NNN-<slug>/`
- **Nota de KB**: `[[nota]]` en `/Users/lmatos/Work/Auphere/`
- **Superficie de confianza**: `0` API consola · `1` navegador · `2` VM · `3a` máquina del partner · `3b` escritorio

<!--
  ¿Sin spec? Solo hay tres excepciones (docs/spec-driven-development.md §2):
  hotfix P0 (spec retroactiva en 48 h o se revierte), cambio trivial sin
  cambio de comportamiento, o spike acotado (que no se fusiona aquí).
  Marca cuál y por qué:
-->

- [ ] Va sin spec por la excepción: **[hotfix P0 / trivial / spike]** — razón:

## Las puertas

- [ ] **Constitution Check** relleno en `plan.md`, las nueve filas con su prueba
- [ ] **Aislamiento** (§I): las garantías tocadas tienen su test en `tests/isolation/` y está en verde
- [ ] **Licencias** (§VIII): toda dependencia nueva trae su licencia leída y el párrafo citado
- [ ] **Medidor**: lo que gasta declara en qué pantalla lo ve el partner
- [ ] **Trazabilidad**: cada tarea de `tasks.md` cita sus `_Requisitos: N.m_`
- [ ] `/speckit-analyze` en verde

## Spec viva

- [ ] Los documentos que describen lo que este PR cambia van **en este mismo PR**

<!--
  Esta es la casilla que evita que la documentación mienta. Si cambias
  comportamiento documentado en docs/ o architecture/ y no tocas su documento,
  el PR se devuelve. Si no cambia nada documentado, dilo:
-->

- [ ] No aplica — este cambio no toca nada que esté documentado, porque:
