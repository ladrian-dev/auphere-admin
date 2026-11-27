# Bug Fix: aceptar una pregunta frecuente del constructor la deja sugerida

- **Slug**: aceptar-una-faq-la-deja-sugerida
- **Fixed**: 2026-11-26
- **Assessment**: ./assessment.md
- **Status**: applied

## Summary

Decidir una propuesta de `/faqs/…` (aceptar o editar) aplica el valor sin `suggested`: lo
que decide una persona queda confirmado. La pregunta aceptada sale entre las confirmadas, no
vuelve a «Por confirmar» y entra en el prompt de los agentes activos del cliente en la misma
transacción. Las que el fallo ya dejó sugeridas se confirman con su «Aceptar» de «Por
confirmar», que ya funcionaba y ahora tiene prueba.

## Changes

| File | Change | Notes |
|------|--------|-------|
| `apps/api/src/nexus_api/services/business/suggestions.py` | modified | `_confirmed`: el valor decidido de `/faqs/…` sin `suggested` |
| `apps/api/tests/integration/builder/test_accepting_a_builder_faq.py` | added test | Aceptar y editar confirman; la forma que dejó el fallo se confirma con `PATCH` |

## Diff Highlights

```python
chosen = _confirmed(row.pointer, row.proposed_value if decision == "accept" else value)
```

`faqs._apply` no cambia: también lo usa deshacer, que debe devolver `suggested` tal como
estaba.

## Tests Added or Updated

- `test_accepting_a_builder_faq.py::test_accepting_a_faq_of_the_builder_confirms_it_and_it_reaches_the_prompt`
  — con el constructor de verdad (sin modelo): la fila, `GET …/faqs`, la decisión guardada y
  el `system_prompt_rendered` de la versión activa, para «aceptar» y para «editar».
- `test_accepting_a_builder_faq.py::test_a_faq_the_bug_left_suggested_is_confirmed_by_accepting_it_again`
  — una fila `suggested = true` (lo que dejó el fallo) se confirma con
  `PATCH {"suggested": false}` y entra en el prompt.

## Local Verification

- `pytest tests/integration/builder/test_accepting_a_builder_faq.py` antes del arreglo →
  1 failed (`assert True is False`: la fila aceptada seguía `suggested`), 1 passed.
- Después, con `test_client_builder_and_copilot.py`, `test_client_builder_launch.py`,
  `test_provenance_history.py` y `test_sector_identify.py` (los que deciden propuestas) →
  36 passed.

## Deviations from Assessment

- La prueba de deshacer no se escribió: el adaptador de deshacer (`faqs._restore`) no se tocó.

## Follow-ups

- Contar en prod las que quedaron sugeridas tras aceptarlas (solo lectura, con un rol que
  salte la RLS):

  ```sql
  SELECT f.tenant_id, count(*)
  FROM business_faqs f
  JOIN business_suggestions s
    ON s.tenant_id = f.tenant_id AND s.pointer = '/faqs/-' AND s.source = 'builder'
   AND s.decision = 'accepted' AND s.proposed_value->>'q' = f.q
  WHERE f.suggested AND f.archived_at IS NULL
  GROUP BY f.tenant_id;
  ```

- La spec 081 cambia la deduplicación por la pregunta normalizada; con ella, el constructor
  puede dejar de escribir `suggested` en lo que propone.
