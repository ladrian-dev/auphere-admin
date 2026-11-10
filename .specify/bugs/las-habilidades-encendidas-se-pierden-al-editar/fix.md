# Fix: las habilidades encendidas se pierden al editar las instrucciones

- **Date**: 2026-11-08
- **Assessment**: `assessment.md` (verdict: valid, severity: high)

## Change

`apps/api/src/nexus_api/api/console/agent_spec_drafts.py`:

- `_version_tools(stored, version)`: las herramientas de la versión, quedándose con lo
  que la spec ya nombraba y con lo que tiene la forma del catálogo, en el orden de la
  versión y con el tope de 60.
- `spec_of`: en una spec guardada en modo `instructions`, `tools` sale de
  `_version_tools(spec.tools, cfg.tools)`. Los agentes estructurados y los que no
  tienen spec no cambian.

Todo lo que lee la spec de un agente pasa por `spec_of` (la ruta del borrador,
`current_spec`, la puerta de publicar y las sugerencias), así que la ficha, la
revisión, la edición y la publicación ven la misma lista que el runtime. Apagar una
herramienta también se ve: sale de la versión y por tanto de la lectura.

## Tests

- Nuevo: `apps/api/tests/integration/test_skills_survive_an_instructions_edit.py`
  (rojo antes, verde después).

## Staging

El borrador v9 de Ana ya estaba desfasado (spec con 12, versión con 18). Con el
arreglo desplegado, la ficha lo lee bien sin tocar nada.
