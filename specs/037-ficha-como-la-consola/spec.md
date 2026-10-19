# Especificación: la ficha del cliente se ve como en la consola de Partners

**Rama**: `035-canales-y-conectores` (continúa) · **Creada**: 2026-10-19 · **Estado**: Implementada

**Entrada**: owner, 2026-10-19, con capturas de la consola: «No veo esta vista como en la
de partners».

## Encabezado Auphere

| Campo | Valor |
|---|---|
| **Superficie de confianza** | `0` — panel de operador |
| **Garantías de aislamiento tocadas** | **1** — Habilidades lee y escribe el cliente con su GUC. Test en `tests/integration/test_admin_tenant_capabilities.py` |
| **Nota de KB** | `[[ADR-047-clientes-comodos]]` (la amplía) |
| **Qué se mide** | Nada nuevo |

## Requisitos

1. Las pestañas del cliente DEBEN usar el mismo `NavTabs` que la consola, con los rótulos de grupo visibles (Observar · Configurar · Conectar).
2. El panel DEBE tener Habilidades con la misma lectura y la misma escritura que la consola: nombres de negocio, grupos por función, filtro por sector, un cambio por llamada, al borrador.
   - La API la sirve en `GET/PUT /admin/tenants/{id}/capabilities`, ejecutando el código de la consola sobre el ámbito del cliente.
   - La auditoría la firma el operador (`operator:<correo>`).
3. Agente DEBE verse como en la consola: «Nuevo borrador a partir de la versión N», una tarjeta por versión con su estado y «⋯» para publicar, revertir o ver el prompt, ambas con confirmación. Debajo, runtime y evaluaciones.
   - Las herramientas salen del editor: viven en Habilidades.
4. El Playground DEBE ser una pestaña del cliente, enmarcada en la ficha.
   - «Probar agente» y las pruebas del Resumen llevan ahí.

## Diferencias que se mantienen con la consola

- **Pestañas propias del panel.** El panel conserva Auditoría, Aislamiento, Acceso, Facturación y Canal del dueño, que el partner no tiene.
- **Conocimiento y Puesto de trabajo.** No entran: son del partner, no del cliente. En el panel, Conocimiento vive en la ficha del partner.
- **«Requiere aprobación».** La API de la consola lo retiró de Habilidades (spec 017 R5.7). El editor de permisos de Conectores sigue ofreciéndolo para los tres modos del motor.
