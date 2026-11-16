# Guía de validación: Conector de Quédate

> Enmienda del 2026-11-16: sobre la API del agente de Quédate, con la clave del cliente.

## En local (sin red)

1. Migra y siembra los conectores:

   ```bash
   cd apps/api && uv run alembic upgrade head && uv run python scripts/seed_connectors.py
   ```

   Esperado: `quedate` existe con 27 herramientas en `tool_catalog`, `auto_enable_on_connect=false`, `connector_access_defaults.enabled=false`, y `customer_connector_accounts` no tiene columna de credencial.

2. Corre las pruebas del conector (contrato, catálogo y públicas, persona y equipo):

   ```bash
   cd apps/mcp && uv run --frozen pytest tests/test_quedate_*.py tests/test_registry_unit.py -q
   ```

3. Corre las de aislamiento y las de la API tocadas, de una en una:

   ```bash
   cd apps/api && uv run --frozen pytest tests/isolation/test_061_customer_connector_accounts.py tests/isolation/test_51_new_tools_take_no_end_customer.py tests/isolation/test_44_agent_within_client.py -q
   ```

   ```bash
   cd apps/api && uv run --frozen pytest tests/unit/connectors tests/integration/connectors/test_quedate_connect.py -q
   ```

4. Panel en local (`http://localhost:3100`):
   - En Conectores → Quédate: «Deshabilitado por defecto».
   - Habilítalo para un partner de prueba con un motivo.
   - En la ficha de un cliente de ese partner, Conectores → Quédate muestra «Anfitriones vinculados: ninguna persona».

## Contra Quédate dev (T060)

Con una clave de **dev** con alcance `agent:onboarding` (nunca la de alcance `*`), y datos ficticios: Quédate no borra, y todo lo que se cree se queda.

1. Conectar Quédate en un cliente de prueba con la clave y el entorno `dev`. Una clave inválida deja la conexión en «revisar la clave».
2. Activar las herramientas en un agente de prueba y, desde un WhatsApp de prueba:
   1. Buscar alojamientos y cotizar uno: sin datos del anfitrión.
   2. Darse de alta como anfitriona con datos ficticios. El agente lee el correo y espera la confirmación.
   3. Pedirlo otra vez: dice que ya es anfitriona y en Quédate hay una sola.
   4. Pedir el enlace de verificación: abre `dev.quedate.net`.
   5. Mandar tres fotos, crear un anuncio, subirlas y mandarlo a revisión: queda `pending_approval`, nunca `published`.
   6. Ocultarlo: queda `hidden`.
3. En el panel de Auphere, la ficha del conector del cliente dice «1 persona» vinculada.

## En staging, con Quédate

1. Tras el despliegue, en el panel: Conectores → Quédate → «Decidir para un partner» → el partner → Habilitado, con un motivo.
2. En la consola de un cliente de ese partner, conectar Quédate con la clave que el cliente genera en su panel de Quédate. Para probar contra su entorno de pruebas, entorno `dev`.
3. Repetir el paso 2 de «Contra Quédate dev».
4. Generar en Quédate una clave nueva y conectarla: la siguiente acción de una persona ya vinculada la deja «en revisión» y el panel lo cuenta.
