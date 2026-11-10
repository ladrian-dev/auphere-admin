# Bug Assessment: el playground y las pruebas consultan al dueño de verdad

- **Slug**: el-playground-consulta-al-dueno-de-verdad
- **Created**: 2026-10-29
- **Source**: auditoría del constructor (`research/2026-10-29-auditoria-del-constructor/_index.md`, fallo 4)
- **Verdict**: valid
- **Severity**: high

## Report (verbatim or summarized)

En el playground y en las pruebas del agente, una herramienta con el permiso
«Preguntar antes de escribir» crea una consulta real al dueño. Además, las
herramientas de lectura de los conectores (Composio) leen datos reales del
negocio, que el partner ve en las respuestas del playground.

## Symptom

Un partner prueba en el playground «resérvame mañana a las 10» con un conector
en «Preguntar antes de escribir»: el dueño recibe por WhatsApp una consulta de
aprobación real (`auphere_owner_consult`) de una conversación que no existe. Lo
esperado (requisito 20.1): ningún envío y ningún efecto fuera del playground.
Con una lectura de Composio (por ejemplo, la agenda de Google), el agente del
playground responde con citas reales de clientes finales, que el partner no debe
ver (C8).

## Reproduction

1. Un agente con un conector activado en «Preguntar antes de escribir».
2. Playground o prueba (`SimulatedRegistry`, `dry_run=True`).
3. El agente llama a una herramienta de escritura del conector.
4. `pipeline.py` ejecuta `_approval_envelope` antes de mirar `dry_run` →
   `tool_approvals.gate` crea una `OwnerConsultation` y se envía la plantilla.

## Suspected Code Paths

- `apps/worker/src/nexus_worker/runtime/pipeline.py:~1831` — la puerta de aprobación corre antes de la comprobación de `dry_run` (`~1843`).
- `apps/worker/src/nexus_worker/runtime/pipeline.py:2007-2046` `_approval_envelope`.
- `apps/api/src/nexus_api/services/tool_approvals.py:96-114` `gate` — crea la `OwnerConsultation`.
- `apps/worker/src/nexus_worker/simulation/registry.py:68-69, 96-108` — `dry_run=True`; las herramientas de solo lectura se ejecutan de verdad.

## Root Cause Hypothesis

La puerta de aprobación (spec de permisos por conector) se añadió delante de la
rama de simulación, y el registro simulado da por buena cualquier lectura. Ninguna
de las dos piezas sabe que está en el playground. Confianza: **alta**.

## Proposed Remediation

**Preferred**:
- En `dry_run`, la puerta de aprobación no llama a `gate`: el turno anota «Lo que
  habría hecho: preguntar al dueño antes de {acción}» y sigue como si el dueño
  hubiera aprobado, para que la prueba pueda comprobar el resto.
- En el registro simulado, las lecturas de conectores externos (Composio y
  cualquier herramienta con `connector_id`) no se ejecutan: devuelven un resultado
  simulado y vacío, marcado como tal, y una acción «Lo que habría consultado: …».
  Las herramientas internas de solo lectura sobre datos del propio cliente que no
  son de clientes finales (la ficha, los servicios) siguen ejecutándose.

## Test plan

- Unitario del pipeline: en `dry_run`, una herramienta con aprobación no crea
  `OwnerConsultation` y deja la acción simulada.
- Unitario del registro simulado: una lectura de Composio no llama al proveedor.
- Integración del playground: ninguna fila nueva en `owner_consultations` tras
  una conversación que pide una escritura con aprobación.
