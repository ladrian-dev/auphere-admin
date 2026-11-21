# Especificación: Lo que te necesita

**Rama**: `071-lo-que-te-necesita` · **Creada**: 2026-11-21 · **Estado**: Borrador con decisiones abiertas para el owner y Luis

**Entrada**: el owner dio paso al lote 3 del roadmap de la consola (`[[nexus/UX-CONSOLA-PARTNERS-2026-11-20]]`), con sus palabras en la sesión lateral: «Perfecto podemos continuar con el siguiente paso». El lote dice:
- una sola lista «Necesita tu atención» para el Panel, la campana y Consumo;
- avisos que se resuelven solos;
- el tope de construcción y el saldo bajo a la vista.

El hallazgo más grave del estudio (2026-11-20) fue que el tope de «Construcción y pruebas» al 84 % solo aparecía al final de Consumo.

## Encabezado Auphere *(obligatorio)*

| Campo | Valor |
|---|---|
| **Superficie de confianza** | `0`: la API de la consola y la consola de partners, que ya existen. No se abre ninguna superficie. |
| **Garantías de aislamiento tocadas** | **1 (RLS / partner)**, rozada. La lista junta datos del partner (cuenta, tope de construcción) y de cada uno de sus clientes (bolsas, canales, conectores, agentes), siempre con el contexto del partner que pregunta. Plan: un test de aislamiento que barre la lista y la campana de dos partners y comprueba que ninguno ve nada del otro, ni de un cliente que no es suyo. |
| **Nota de KB que la justifica** | `[[nexus/UX-CONSOLA-PARTNERS-2026-11-20]]`, lote 3. Mapa del código del 2026-11-21 (resumido en «Qué hay hoy»). |
| **Qué se mide** | **Nada nuevo.** No llama a modelos ni a herramientas de pago. |

## Qué hay hoy (2026-11-21, `develop` en d4a605c6)

Hay **tres fuentes distintas**, y nada las une:

1. **Panel, «Necesita tu atención»** (`services/attention.py`, `partner_panel.build_panel`). Se calcula en vivo a partir del estado de cada cliente: sin saldo, problema de canal, conector caducado, tope del agente, agente sin canal, saldo bajo (<20 % de la bolsa o <7 días) y sin agentes. **Solo clientes.** No incluye el tope de construcción, ni el saldo de la cuenta, ni la facturación. El Panel ya pone los datos primero y la atención al final, como pidió el owner.
2. **La campana** (`console_notifications`). Es un registro de eventos que se marcan como leídos a mano. **Solo `inbox.waiting` se resuelve solo** (`handled_at`, spec 056). El resto solo se «rearma»:
   - subir saldo, subir un tope o el cambio de mes permiten que el aviso vuelva a salir;
   - pero el aviso viejo sigue ahí, sin leer y diciendo algo que ya no pasa (§V);
   - `channel.problem` e `integration.reauth_required` no liberan nunca su clave. Un segundo problema idéntico en el mismo canal no avisa jamás, aunque `contracts/events.md` de la 047 promete «hasta que se resuelve».
3. **Consumo**:
   - el tope de construcción solo vive en la tarjeta de «Construcción y pruebas», en el cuarto bloque;
   - el saldo bajo de un cliente no se ve: solo «Sin saldo»;
   - no hay aviso de saldo bajo de la cuenta.

## La propuesta

**Una sola regla, en el servidor, y todo lo demás la lee.**

- `services/attention.py` pasa a dar la lista completa del partner: lo de cada cliente, como hoy, **más lo del partner**:
  - el tope de construcción al 80 % o más, o agotado;
  - el saldo de la cuenta bajo o agotado;
  - un cobro fallido.
- La lista es **estado en vivo**. Lo que deja de pasar desaparece de ella sin que nadie haga nada. Es la única forma de que el Panel, la campana y Consumo digan lo mismo, porque leen lo mismo.
- **La campana** se queda con dos cosas:
  - **«Ahora»**: la misma lista. Su número es el número rojo de la campana;
  - **«Anteriores»**: el registro de eventos de siempre.
- **El servidor resuelve los avisos guardados.** Cuando la regla deja de listar algo, los avisos de esa condición quedan resueltos (`handled_at`, que ya existe y ya cuenta como leído), y su clave se libera para que una vuelta del problema vuelva a avisar. Se hace donde hoy ya se «rearma» (subir saldo, mover saldo, subir un tope, cambio de mes, canal reconectado, conector renovado) y en un repaso del worker cada hora, por si algo se escapa.
- **Panel**:
  - los datos siguen primero (owner, 2026-11-20);
  - las cifras se tiñen cuando su condición está en la lista: «Saldo disponible» en ámbar si la cuenta está baja; una línea del tope de construcción con su barra cuando pasa del 80 %;
  - la lista va al final, con el arreglo en el sitio, como hoy.
- **Consumo**: los avisos de dinero de la misma lista (cuenta, tope de construcción, clientes bajos o sin saldo) van al final de la página, cada uno con su acción («Comprar saldo», «Pedir ampliación», «Asignar saldo»), como la demo aprobada. La tabla de clientes enseña «Saldo bajo» y no solo «Sin saldo».

## Requisitos

### 1. La regla única

1.1 `GET /console/attention` devuelve la lista del partner, de peor a mejor. Cada fila trae:
- su código;
- su alcance: `partner` o `client` (con `external_client_ref`);
- su gravedad: `critical` o `warning`;
- su texto;
- su arreglo: la acción en el sitio o el enlace.

1.2 Los códigos del partner son tres. **[NEEDS CLARIFICATION D2]**
- `build_cap_warning` (80 % o más), `build_cap_exhausted` (100 %);
- `account_low` y `account_empty`. ¿Qué es «bajo» para la cuenta? Propuesta: el mismo criterio que el de las bolsas, menos del 20 % de lo cargado en el mes o menos de 7 días al ritmo de los últimos 7;
- `billing_payment_failed`.

Los de cliente son los de hoy.

1.3 `/console/home` (bloque `panel`) y Consumo usan la misma función, no una copia.

1.4 Gating: cada fila respeta los permisos de hoy (quien no puede asignar ve «Pedir saldo») y los módulos del partner.

### 2. Los avisos que se resuelven solos

2.1 Cada clase de aviso de condición se asocia a su código de la regla:

| Aviso | Código de la regla |
|---|---|
| `client.wallet.low` | `low_balance` |
| `client.wallet.empty` | `no_balance` |
| `build.budget.warning` | `build_cap_warning` |
| `build.budget.exhausted` | `build_cap_exhausted` |
| `wallet.low` | `account_low` |
| `wallet.empty` | `account_empty` |
| `agent.cap.reached` | `agent_cap` |
| `channel.problem` | `channel_problem` |
| `integration.reauth_required` | `integration_reauth` |
| `billing.payment_failed` | `billing_payment_failed` |

Los informativos (miembro nuevo, cliente activado, sugerencias…) no se resuelven: se leen.

2.2 Cuando su código deja de estar en la lista de ese partner (o de ese cliente), sus avisos pendientes quedan con `handled_at` y la `dedupe_key` se libera. Si el problema vuelve, vuelve a avisar.

2.3 Se resuelven en los sitios donde hoy se rearma (bolsas, topes, canal reconectado, conector renovado, cambio de mes) y en un repaso del worker cada hora.

2.4 `build.budget.*` deja de colgarse de un cliente cualquiera: es un aviso del partner, sin `external_client_ref`.

2.5 Resolver no manda correo ni push. **[NEEDS CLARIFICATION D3]** Propuesta: nada.

### 3. La campana

3.1 El número rojo es el número de filas de la regla, más los avisos informativos sin leer.

3.2 El desplegable empieza por **«Ahora»**, la lista viva con su arreglo. Después vienen **«Anteriores»**: los últimos avisos, con los resueltos marcados «Resuelto» y sin punto de no leído. **[NEEDS CLARIFICATION D1]**

3.3 «Marcar todo como leído» solo afecta a los informativos. Lo de «Ahora» no se puede marcar como leído: se arregla.

3.4 La página Avisos tiene los mismos dos bloques.

### 4. Panel

4.1 El orden no cambia: el gasto del mes, las tres cifras, el gráfico y, al final, «Necesita tu atención».

4.2 «Saldo disponible» se tiñe de ámbar con `account_low` y de rojo con `account_empty`, con texto, no solo color.

4.3 Con `build_cap_warning` o `build_cap_exhausted`, la tarjeta del gasto lleva una línea «Construcción y pruebas: 52,23 de 62,00 USD (84 %)» con su barra y «Pedir ampliación».

4.4 La lista muestra lo del partner y lo de los clientes juntos, de peor a mejor. «Todos tus clientes están atendiendo» pasa a «Nada te necesita ahora» cuando la lista está vacía.

### 5. Consumo

5.1 Al final de la página, «Avisos» con las filas de dinero de la regla y su acción.

5.2 La tabla de clientes dice «Saldo bajo», además de «Sin saldo».

## Decisiones abiertas

- **D1 · La campana.** Propuesta: «Ahora», con la lista viva que se arregla, y «Anteriores», con el historial. Alternativa: una sola lista, con los resueltos atenuados.
- **D2 · Saldo bajo de la cuenta.** Propuesta: menos del 20 % de lo cargado en el mes o menos de 7 días al ritmo de los últimos 7, como las bolsas.
- **D3 · Al resolverse.** Propuesta: no avisar. Desaparece de «Ahora» y queda «Resuelto» en el historial.

## Fuera de alcance

- La app móvil: tiene su propia campana. Gana lo mismo cuando lea `/console/attention`, en otra spec.
- Cambiar umbrales de los avisos que ya existen.
