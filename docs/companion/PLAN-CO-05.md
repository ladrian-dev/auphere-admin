# PLAN-CO-05 · Probar antes de publicar

> Lo construye el **orquestador** en la Fase 2 de la Ola 2, después de aplicar
> los parches de E, D y F. No fue a la Fase 1 a propósito: se apoya en la fase
> de verificación de D y en la capa de herramientas de E, y meterlo en paralelo
> habría puesto a tres agentes a editar `catalog.py`.
>
> Manda [`CONTRACT-V2.md`](CONTRACT-V2.md) §7 y §19.2.

---

## 0. La forma del cambio

```
 modelo pide  companion.run_playground_turn(client_ref, probes[])
      │        arranca un turno contra el agente BORRADOR (versión staged)
      │        mide contra el TOPE DEL PLAYGROUND, no contra el del Companion
      ▼
 nodo verify   verify.result{action_id, checks, ok, trial}
                trial = {ran, client_ref, thread_id, ok, tokens, turns[]}
      ▼
 al proponer   console.propose_publish lee si hubo prueba
 una publicación  preview += {trial_ran, trial_ok, warning_key}
                  → la interfaz AVISA. No prohíbe.
```

---

## 1. Decisiones

### D1 · La prueba es una herramienta de lectura, no una escritura

`companion.run_playground_turn` es `tool_class="read"`, `always_allow`. **No pasa
por `propose → confirm → apply`**, y eso es deliberado: no escribe nada del
cliente. Un turno de playground contra un borrador no cambia el agente, no toca
ningún canal y no llega a ningún cliente final. Exigir confirmación para probar
convertiría la prueba en fricción, y la fricción es exactamente lo que hace que
la gente publique sin probar.

Es la misma lógica que separa `console.get_usage` de `console.propose_prompt`.

### D2 · Se prueba el **borrador**, nunca el activo

Contra la versión `staged`, que es lo que en esta plataforma es un borrador
(PLAN-CO-04 D1). Probar el activo no responde a la pregunta que se está
haciendo, que es *"¿lo que voy a publicar se comporta como quiero?"*.

### D3 · El tope es el del playground, no el del Companion

`qa_monthly_token_cap`, con su `usage_records.source='qa'`. El gasto de probar
es gasto de playground: lo consume el agente del cliente, no el Companion. Meterlo
en el presupuesto del Companion mezclaría dos medidores que ya están separados a
propósito, y haría que probar mucho apagara el Companion.

Un 429 del tope de playground **no tira el turno del Companion**: vuelve como
resultado de herramienta legible, y el Companion lo dice y sigue. Es un límite de
la prueba, no del trabajo.

### D4 · `trial` no lleva la respuesta del agente borrador

Regla dura del contrato §7. Lleva `probe` (que redacta el Companion, como
`citation.claim`), aserciones con nombre estable y metadatos. Quien quiera leer
la conversación abre el hilo de playground por `thread_id` + `client_ref`, donde
ya hay autorización y ya está el guardián del §1.3 de la investigación.

Esto no es prudencia de más: la respuesta del borrador puede citar literalmente
el mensaje de prueba y, en un agente ya entrenado con contenido del cliente,
arrastrar texto que C8 prohíbe sacar por este camino.

### D5 · Dónde vive el hecho "esto se probó"

**En el estado del hilo del Companion**, junto al expediente de D — no en una
tabla nueva.

- `propose_publish` lo recibe del `toolbelt` del run, igual que recibe todo lo
  demás.
- **Limitación conocida y declarada**: si alguien publica desde un hilo distinto
  de aquel donde probó, sale `trial_ran: false`. Eso es honesto —*"en esta
  conversación nadie probó"*— y es la lectura que el aviso quiere dar. Un hecho
  por versión, compartido entre hilos, exige una tabla y una migración, y eso es
  alcance que la Ola 2 no abre. **Queda anotado como deuda con nombre.**

### D6 · Publicar avisa, no prohíbe

`preview` de `kind: publish` gana `{trial_ran, trial_ok, warning_key}` con
`warning_key ∈ not_tried | trial_failed | null`. `evals_warning` sobrevive por
compatibilidad con lo que CO-04 ya emite.

**El usuario puede publicar sin probar.** Se le dice, queda en la fila de la
acción y en la auditoría, y se publica. Prohibirlo convertiría la prueba en un
peaje que la gente aprende a rodear — y quien lo rodea deja de leer el aviso.

---

## 2. Lo que hay que tocar

| Archivo | Qué |
|---|---|
| `companion/tools/catalog.py` | La herramienta nueva. **Después** del parche de E |
| `companion/tools/playground.py` (nuevo) | El ejecutor: arranca el turno, espera, arma `trial` |
| `companion/tools/proposals.py` | `_publish` lee el hecho y llena las tres claves |
| `runtime/companion/graph.py` | `verify.result` lleva `trial`. **Después** del parche de D |
| `api/companion_streaming.py` | Ya lo declara E (`trial` en `verify.result`) |

---

## 3. Lo que NO hace CO-05

- **`companion.run_eval`** (la suite de `services/evals` sobre el borrador, con
  juez y aserciones). Es §6.4 y está marcado "Fase 2" en la propia
  investigación. CO-05 entrega el turno en seco; la suite es otro paquete.
- **Enlazar de verdad al hilo de playground.** El enlace se construye (§19.2),
  pero la página de playground **no lee ningún parámetro de hilo de la URL**: el
  hilo elegido vive en estado local de `components/playground/playground.tsx`.
  Arreglarlo cae fuera de las tres zonas de la Ola 2 y va a un paquete aparte.
