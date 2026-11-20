# Especificación: El modelo de cada agente

**Rama**: `065-modelo-por-agente` · **Creada**: 2026-11-19 · **Estado**: Borrador con las decisiones de Luis del 2026-11-19; pendiente de su revisión

**Entrada**: descripción del usuario (2026-11-19): «En producción tenemos a un cliente usando la app y tiene un consumo muy alto porque está usando un modelo grande y costoso… vas a investigar lo que necesitamos para que desde la consola de partners se le pueda configurar el modelo a cada agente con un selector, ya que por defecto usa Sol». Y después: «Prepara el plan de acción para implementar el selector de los modelos donde vamos a poder seleccionar por Opus 5.5, Sonnet 5.5, Haiku 5.5, Sol, Terra y Luna. Así vamos a poder hacer las pruebas con diferentes modelos… Asegura que al cambiar el modelo a otra familia funcione perfectamente. Se debe poder seleccionar el modelo por cada agente».

## Encabezado Auphere *(obligatorio)*

| Campo | Valor |
|---|---|
| **Superficie de confianza** | `0`: la consola de partners, el panel de operador y su API, que ya existen. No se abre ninguna superficie. |
| **Garantías de aislamiento tocadas** | **1 (RLS)**: la elección de modelo es un dato del cliente, por agente, que se lee y se escribe con su contexto. **7 (una petición por cliente y llamada, sin lotes)**, rozada: entran dos modelos nuevos de Anthropic por el mismo transporte, que no puede mezclar clientes. La **2 (lista blanca de herramientas)** no cambia: el modelo no añade ni quita herramientas. |
| **Nota de KB que la justifica** | `[[decisions/2026-11-19-modelo-por-agente]]` en `/Users/lmatos/Work/Auphere/nexus/`. Estudio: https://claude.ai/artifact/FjcXQbvTRjtxvkc8Q5LU1N |
| **Qué se mide** | Las llamadas de conversación del agente, como hoy, con el modelo que respondió de verdad y sus pesos por carril. Opus 5.5 y Sonnet 5.5 entran con precio y pesos; sin pesos, un turno se quedaría sin cobrar. **Cambia lo que se cobra**: la escritura en caché pasa a tener su propio peso, también la de GPT-5.6, que OpenAI cobra a 1,25× la entrada y hoy no medimos, y el recargo de Haiku 5.5 por encima de 100.000 tokens se repercute (requisito 5). Al desplegar sube el precio de los agentes que ya responden con Sol, Terra o Luna. |

### Lo que enmienda

| Dónde | Qué decía | Qué pasa ahora |
|---|---|---|
| Spec 047, **requisito 64** (64.1 y 64.3) | La consola no enseña modelos; Agente › Avanzado dice que el modelo lo gestiona Auphere, y la API rechaza cambiarlo. | Para el **modelo de respuesta**, la consola enseña el selector de esta spec. «Calidad», «Fijar un modelo» y los perfiles siguen ocultos, y la API sigue respondiendo `409 model_policy_managed` a un cambio de política de modelo. |
| Spec 016, **R5** | El modelo se elige por cliente. | **Desaparece**: la asignación de cada cliente pasa a sus agentes al desplegar y deja de leerse (requisito 12). |
| Spec 007, carriles de la venta | La escritura en caché no lleva peso ni come tope. | Lleva su peso, sacado de su tarifa con el mismo multiplicador, y el recargo por tramos de un modelo se repercute (requisito 5). |
| Spec 059, **requisito 1** | Un modelo que es valor por defecto o que usa un agente o un cliente no se puede retirar. | También cuenta la elección de cada agente, y las reservas de la otra familia son valores por defecto. |
| Spec 059, registro `default_models` | La reserva de responder es el mismo modelo que responde (Sol), y el modelo de los agentes sin elección es el de responder del worker. | La reserva de cada modelo es de la otra familia (requisito 11), y el modelo de los agentes sin elección es un ajuste de plataforma por entorno (requisito 13). |

## Por qué

- **El modelo decide el coste.** Jemma's Hair Salón (partner Autprod) pagaba US$ 0,10 de venta por respuesta con Sol. Con los mismos tokens, Terra cuesta la mitad y Luna 19 veces menos.
- **Hoy no se puede elegir por agente.** Un cliente puede tener varios agentes para cosas distintas, y todos responden con el mismo modelo: el del cliente o, sin él, Sol.
- **Hay tres sitios donde se decide el modelo** (cliente, versión del agente y configuración del worker), y el de la configuración mueve además el constructor y el Playground. Luis pidió un solo sitio por agente y que el modelo por defecto de Auphere sea Claude Haiku 5.5.
- **Luis quiere probar los agentes con modelos distintos**, también de Anthropic, para decidir con datos y no por intuición.
- **La reserva de hoy no salva una caída del proveedor.** Todos los agentes caen a Sol, que es OpenAI como el modelo que falla. Del 8 al 12 de octubre, OpenAI sin saldo dejó turnos reales sin respuesta (63 mensajes con la disculpa). El 2026-11-19 a las 16:58 UTC, el límite de cuota de OpenAI paró la batería de pruebas de un agente nuevo (33 turnos simulados, ningún cliente real).
- **Cambiar de familia hoy no es seguro.** El turno solo ha respondido con herramientas con Sol, y algún cliente con Sonnet 4.6. Los modelos nuevos de Anthropic razonan siempre o por defecto, y el bucle de herramientas descarta ese razonamiento entre una llamada y la siguiente; Opus 5.5 rechaza la segunda. Si un modelo falla, el turno cae a Sol sin decirlo y el informe del turno dice Sol aunque haya respondido otro.
- **«Fijar un modelo» no sirve tal como está.** Pasa por el router, cuyo filtro exige retención cero, y ningún modelo de producción la tiene: un agente fijado se quedaría sin modelo y la conversación pasaría a una persona.

## Escenarios de usuario y pruebas *(obligatorio)*

### Historia 1 — El partner elige el modelo de un agente (Prioridad: P1)

Una persona del partner abre un agente, va a Avanzado y ve el modelo con el que responde y por qué: elegido para el agente, elegido por Auphere o el de Auphere. Abre el selector, ve los modelos que puede elegir con lo que cuesta cada uno, elige otro y guarda. El siguiente mensaje de un cliente final ya lo responde ese modelo, sin publicar ninguna versión.

**Por qué esta prioridad**: es lo que pidió Luis y la palanca directa del coste.

**Prueba independiente**: con un cliente de dos agentes, cambiar el modelo de uno de ellos desde la consola. Comprobar que su siguiente turno responde con el nuevo, que el otro agente sigue con el suyo y que la auditoría guarda quién lo cambió.

**Escenarios de aceptación**:

1. **Dado** un agente sin elección propia, **cuando** el partner abre Avanzado, **entonces** ve los modelos de su cuenta con su precio, y marcado como «Ahora» el modelo con el que responde, sin ninguna opción aparte para «el de Auphere».
2. **Dado** ese agente, **cuando** el partner elige Terra y guarda, **entonces** el siguiente turno del agente responde con Terra, sin publicar versión, y los demás agentes del cliente siguen como estaban.
3. **Dado** un agente con Terra elegido por el partner, **cuando** Auphere lo devuelve al modelo por defecto desde el panel, **entonces** el agente responde con el modelo por defecto de Auphere de ese entorno. Desde la consola no se vuelve al modelo por defecto: el partner elige un modelo.
4. **Dado** un partner con permiso de solo lectura, **cuando** abre Avanzado, **entonces** ve los modelos con su precio y cuál responde, y no puede cambiarlo.

---

### Historia 2 — Cambiar de familia no degrada el turno (Prioridad: P1)

Un agente que reserva citas pasa de Sol a Claude Opus 5.5, después a Claude Haiku 5.5 y después a Luna. En cada caso, una conversación que pide cita, la cambia y pregunta un precio funciona igual: el agente encadena sus herramientas, contesta en el tono de sus instrucciones y no deja ningún mensaje sin respuesta. Si el modelo elegido falla o rechaza la petición a mitad de turno, la reserva termina el turno con lo que ya se hizo.

**Por qué esta prioridad**: Luis lo puso como condición: «asegura que al cambiar el modelo a otra familia funcione perfectamente». Sin esto, el selector sería una forma de dejar mudos a los agentes.

**Prueba independiente**: la batería de compatibilidad de esta spec, con cada uno de los seis modelos, contra los proveedores reales en staging.

**Escenarios de aceptación**:

1. **Dado** un agente con cualquiera de los seis modelos, **cuando** un turno necesita tres herramientas seguidas, **entonces** el turno las encadena y responde, sin un error del proveedor por un parámetro que ese modelo no acepta.
2. **Dado** un modelo que devuelve razonamiento junto a una llamada a herramienta, **cuando** el turno sigue con el resultado, **entonces** el razonamiento vuelve intacto a ese mismo modelo y no se envía a ningún otro.
3. **Dado** un turno a mitad de camino con un modelo de Anthropic, **cuando** la siguiente llamada falla o el proveedor la rechaza, **entonces** el turno sigue con la reserva, de otra familia si hace falta, conserva las herramientas ya ejecutadas sin repetirlas y responde al cliente final.
4. **Dado** una conversación que empezó con Sol, **cuando** el agente cambia a Sonnet 5.5 entre dos mensajes, **entonces** el siguiente turno responde con el historial completo.
5. **Dado** un mensaje con una imagen, **cuando** responde cualquiera de los seis, **entonces** el turno la tiene en cuenta como hoy.

---

### Historia 3 — Lo que se cobra y lo que se informa es del modelo que respondió (Prioridad: P1)

El partner ve en su bolsa lo que cuesta cada respuesta, con el precio del modelo que respondió de verdad. Auphere ve en el informe de cada turno, en las pruebas y en el Playground qué modelo respondió y si tuvo que entrar la reserva.

**Por qué esta prioridad**: el selector existe para pagar menos; si el cobro o el informe no dicen la verdad, nadie sabe si funciona.

**Prueba independiente**: un día de turnos con un agente en Luna y otro en Opus 5.5. Conciliar lo descontado de la bolsa con los tokens de cada llamada al precio de su modelo.

**Escenarios de aceptación**:

1. **Dado** un turno que respondió Terra, **cuando** se cobra, **entonces** se cobra con los pesos de Terra y el multiplicador de venta vigente.
2. **Dado** un turno en el que Haiku 5.5 falló y respondió la reserva, **cuando** se cobra, **entonces** cada llamada se cobra al precio del modelo que la hizo, y el informe del turno dice que respondió la reserva.
3. **Dado** el selector abierto, **cuando** el partner mira cada modelo, **entonces** ve lo que costaría una respuesta de ese agente con él, estimado con su consumo de los últimos días o, sin consumo, con uno típico.

---

### Historia 4 — Probar un agente con el modelo elegido (Prioridad: P1)

Antes de dejar un modelo, Auphere o el partner lo eligen, pasan la batería de pruebas del agente y hablan con él en el Playground. Las dos cosas usan el modelo elegido y dicen cuál respondió.

**Por qué esta prioridad**: es como Luis quiere decidir entre modelos («así vamos a poder hacer las pruebas con diferentes modelos»).

**Prueba independiente**: elegir Luna para un agente, pasar su batería y una conversación de Playground, y comprobar que todas las llamadas de conversación fueron de Luna.

**Escenarios de aceptación**:

1. **Dado** un agente con Luna, **cuando** se pasa su batería, **entonces** el agente responde con Luna y el resultado de cada prueba dice qué modelo respondió.
2. **Dado** ese agente, **cuando** el partner habla con él en el Playground, **entonces** responde Luna.
3. **Dado** un cambio de modelo, **cuando** se guarda, **entonces** no lanza pruebas por su cuenta ni obliga a pasarlas.

---

### Historia 5 — Auphere ve y cambia el modelo de cada agente desde el panel (Prioridad: P2)

Una persona de Auphere abre un cliente en el panel y ve, por agente, el modelo con el que responde y su origen. Puede cambiarlo, también a un modelo activo que el partner no tenga en su oferta. En la ficha del partner decide qué modelos puede elegir ese partner.

**Por qué esta prioridad**: el requisito 64 pedía que los modelos se gestionaran desde el panel; Auphere tiene que poder actuar sin entrar en la consola del partner.

**Prueba independiente**: cambiar desde el panel el modelo de un agente y comprobar que la consola del partner lo enseña como elegido por Auphere.

**Escenarios de aceptación**:

1. **Dado** un cliente con dos agentes, **cuando** Auphere abre su ficha, **entonces** ve el modelo efectivo de cada agente y su origen.
2. **Dado** un agente, **cuando** Auphere elige un modelo habilitado que no está en la lista del partner, **entonces** el agente responde con él y el partner lo ve en Avanzado con su precio y una línea que dice que lo eligió Auphere y que no está en su cuenta; puede cambiarlo por uno de su oferta, pero después no puede volver a él.
3. **Dado** Opus 5.5 recién desplegado, **cuando** Auphere lo habilita para responder en staging con la pasada de la batería anotada, **entonces** aparece en la oferta de los partners de staging y en prod sigue sin aparecer.
4. **Dado** un partner, **cuando** Auphere le quita un modelo de su oferta, **entonces** los agentes de sus clientes que lo tenían elegido por el partner pasan al modelo por defecto de Auphere desde el turno siguiente, y el partner recibe un aviso por agente que dice con qué modelo responde ahora.

---

### Historia 6 — Ningún agente se queda sin modelo (Prioridad: P2)

Auphere no puede retirar ni marcar «No disponible» un modelo que un agente tiene elegido. Si un modelo deja de estar disponible por otra causa, el agente responde con la reserva.

**Por qué esta prioridad**: la spec 059 cerró este riesgo para los modelos que usaban los clientes; una elección nueva no puede reabrirlo.

**Prueba independiente**: elegir Opus 5.5 para un agente e intentar retirarlo desde el panel.

**Escenarios de aceptación**:

1. **Dado** un agente con Opus 5.5 elegido, **cuando** Auphere intenta retirarlo o marcarlo «No disponible», **entonces** el panel lo rechaza y dice qué agentes lo usan.
2. **Dado** un modelo elegido que el proveedor deja de servir, **cuando** llega un mensaje, **entonces** responde la reserva y queda registrado.

### Historia 7 — Auphere cambia el modelo por defecto, por etapas (Prioridad: P2)

Luis decidió que el modelo por defecto de Auphere sea Claude Haiku 5.5. Cuando Haiku pasa la batería en un entorno y se habilita, una persona de Auphere lo prueba primero con unos pocos agentes reales, eligiéndolo para ellos desde el panel. Después cambia el por defecto: el panel le enseña qué agentes cambiarán de modelo y le pide confirmación.

**Por qué esta prioridad**: es el mayor ahorro de la spec y el cambio con más riesgo, porque mueve a todos los agentes sin elección propia.

**Prueba independiente**: en staging, con Haiku habilitado, cambiar el por defecto y comprobar que solo cambian los agentes listados, que los que tienen elección propia siguen igual y que se puede volver atrás.

**Escenarios de aceptación**:

1. **Dado** Haiku 5.5 sin habilitar en un entorno, **cuando** Auphere intenta ponerlo por defecto, **entonces** el panel no lo permite.
2. **Dado** Haiku 5.5 habilitado, **cuando** Auphere elige ponerlo por defecto, **entonces** el panel enseña la lista de agentes que cambiarán, con su cliente y su modelo de ahora, y solo cambia si Auphere confirma.
3. **Dado** el por defecto en Haiku 5.5, **cuando** un agente con Terra elegido (Jemma) responde, **entonces** sigue con Terra.
4. **Dado** el por defecto cambiado, **cuando** Auphere vuelve a Sol, **entonces** los mismos agentes vuelven a Sol desde el turno siguiente.

---

### Casos límite

- **Un agente nuevo**: nace sin elección propia y responde con el modelo por defecto de Auphere, también en un cliente que antes tenía modelo propio (un agente nuevo de Jemma nacería con el de Auphere, no con Terra).
- **Un agente archivado**: conserva su elección, que no cuenta como «en uso» para retirar un modelo.
- **Dos personas cambian el modelo a la vez**: gana la última, y la auditoría guarda las dos.
- **El agente usa algo que un modelo no puede ejecutar** (por ejemplo, Skills de Anthropic, que no existen en OpenAI): el selector no ofrece ese modelo. Si el agente lo empieza a usar después de elegir el modelo, Avanzado lo avisa y el turno responde con un modelo que sí pueda.
- **El prompt pasa del umbral de precio de un modelo** (Haiku 5.5 cobra cinco veces más por encima de 100.000 tokens): se cobra lo que cobra el proveedor.
- **El proveedor rechaza por seguridad** (los Claude 5.5 pueden devolver un rechazo sin error): cuenta como fallo y entra la reserva.
- **Todas las llamadas fallan**: el cliente final recibe la frase de siempre («Disculpa, tuve un inconveniente.») y el fallo queda visible como hoy.
- **El turno ya ejecutó una reserva de cita cuando falla el modelo**: la reserva no se repite; la reserva de modelo termina el turno con el resultado.
- **Un cliente con modelo propio al desplegar**: sus agentes pasan a tenerlo elegido, y desde ese momento cada uno se cambia por separado.
- **Una asignación de cliente con reservas propias o tope por turno**: el modelo pasa a sus agentes; las reservas propias y el tope dejan de usarse y quedan listados para Auphere antes del despliegue.
- **El presupuesto del cliente en degradación** (spec WP-20): sigue pasando al modelo más barato, por encima de cualquier elección, como hoy.
- **Una conversación a medias cuando cambia el modelo**: el turno siguiente responde con el nuevo y la primera llamada sale sin caché.

## Requisitos *(obligatorio)*

### Requisito 1 — La oferta

**Historia de usuario:** Como partner, quiero ver los modelos que puedo elegir con lo que cuesta cada uno, para elegir sabiendo lo que gasto.

#### Criterios de aceptación

1. El sistema DEBE ofrecer a cada partner, como máximo, seis modelos de respuesta: Sol, Terra y Luna, de OpenAI, y Claude Opus 5.5, Claude Sonnet 5.5 y Claude Haiku 5.5, de Anthropic.
2. El sistema DEBE ofrecer a un partner solo los modelos activos, **habilitados para responder** en ese entorno y presentes en su lista de modelos permitidos. Al desplegar esta spec, los seis DEBEN quedar en la lista de todos los partners, también de los que se den de alta después.
3. Un modelo DEBE quedar habilitado para responder solo cuando Auphere lo habilite desde el panel, en cada entorno por separado, y el panel NO DEBE permitirlo sin perfil de llamada ni sin anotar la pasada de la batería de compatibilidad (requisito 4.9) en la que se apoya. Al desplegar, Sol, Terra y Luna DEBEN quedar habilitados y los tres de Anthropic NO.
4. WHEN Auphere deshabilita un modelo para responder THEN el sistema DEBE tratarlo como si saliera de la lista de todos los partners (requisito 8.2).
5. El sistema DEBE enseñar de cada modelo ofrecido su nombre, su proveedor, una línea sobre para qué sirve (según su gama: «Para agentes con muchas herramientas o casos difíciles», «Para la mayoría de agentes de atención y reservas», «Para preguntas frecuentes y respuestas cortas») y lo que costaría una respuesta de ese agente con él, marcado como estimación.
6. El sistema DEBE estimar ese coste con el consumo del agente de los últimos 7 días o, sin consumo, con un turno típico, al precio de venta del modelo y corregido por lo que ese modelo gasta de más o de menos según la batería (razonamiento, tokenizador).
7. Claude Opus 5.5 y Claude Sonnet 5.5 DEBEN entrar en el catálogo con sus tarifas y sus pesos por carril antes de ofrecerse.

### Requisito 2 — La elección por agente

**Historia de usuario:** Como partner, quiero elegir el modelo de cada agente y que valga desde el mensaje siguiente, para ajustar coste y calidad por lo que hace cada uno.

#### Criterios de aceptación

1. El sistema DEBE guardar, por agente, un modelo de respuesta elegido o ninguno (sigue el modelo por defecto de Auphere).
2. El sistema DEBE resolver el modelo de respuesta de un agente en este orden: su elección; si no, la de su versión; si no, el modelo por defecto de Auphere de ese entorno (requisito 13).
3. WHEN el partner o Auphere cambian el modelo de un agente THEN el sistema DEBE aplicarlo desde el turno siguiente de ese agente, sin publicar versión y sin tocar a los demás agentes del cliente.
4. Solo quien tenga `agents:write` sobre el cliente DEBE poder cambiar el modelo desde la consola; con `agents:read` DEBE poder verlo.
5. El sistema DEBE rechazar en el servidor un modelo que no esté en la oferta del partner, venga de una pantalla o de una llamada directa a la API.
6. El sistema DEBE guardar en la auditoría del cliente cada cambio: quién, cuándo, qué agente, el modelo anterior y el nuevo.
7. El sistema DEBE enseñar en Avanzado solo modelos que el partner puede elegir y pagar, de menor a mayor precio, con el modelo con el que responde marcado como «Ahora» y seleccionado al abrir (el más barato arriba; Luis, 2026-11-20), y NO DEBE enseñar de dónde sale (elección del partner, de Auphere, de la versión o por defecto) ni ofrecer volver al modelo por defecto (Luis, 2026-11-20: si confunde a Auphere, confunde al partner). WHEN el modelo con el que responde no está entre los que puede elegir THEN la consola DEBE decirlo en una línea, con su precio estimado y el motivo: que ya no se ofrece o que lo eligió Auphere.
8. La consola lite del cliente final y la app móvil NO DEBEN enseñar ni cambiar el modelo.
9. WHEN el copiloto de la consola propone un cambio de modelo THEN DEBE proponerlo para un agente, con los modelos de la oferta del partner, y aplicarlo por el mismo camino que la pantalla, con la confirmación de la persona como hoy.

### Requisito 3 — Qué llamadas usan el modelo del agente

**Historia de usuario:** Como partner, quiero que todo lo que el agente dice lo diga el modelo que elegí, para que el coste y la calidad sean los que veo.

#### Criterios de aceptación

1. El sistema DEBE usar el modelo del agente en todas sus llamadas de conversación de un turno: las que llevan herramientas, las que no, la llamada que cierra el turno y la reescritura que pide el corrector de respuestas.
2. El sistema DEBE seguir usando los modelos de la plataforma en lo que no es la conversación del agente: clasificar, el freno de reservas, el corrector, el juez y el cliente simulado de las pruebas, el constructor, el copiloto, la visión y la transcripción.
3. WHILE el presupuesto del cliente esté en degradación THE sistema DEBE seguir pasando al modelo más barato del catálogo, por encima de cualquier elección.

### Requisito 4 — Cambiar de familia sin degradar el turno

**Historia de usuario:** Como Auphere, quiero que cualquiera de los seis modelos atienda un turno completo, y que pasar de uno a otro no rompa nada, para poder elegir por coste y calidad sin miedo.

#### Criterios de aceptación

1. El sistema DEBE enviar a cada modelo solo los parámetros que ese modelo acepta: ningún modelo DEBE recibir un parámetro que rechace, ni de temperatura, ni de respuesta empezada, ni de herramienta forzada, ni de razonamiento que no admita.
2. El nivel de razonamiento de cada modelo DEBE fijarlo Auphere por modelo, de modo que cada uno responda con el coste y la latencia de un turno de recepción; el partner no lo elige.
3. WHEN un modelo devuelve razonamiento junto a una llamada a herramienta THEN el sistema DEBE devolverlo intacto a ese mismo modelo en la siguiente llamada del turno, y NO DEBE enviarlo a un modelo distinto.
4. WHEN una llamada falla, agota su plazo o el proveedor la rechaza (también un rechazo por seguridad que llega sin error) THEN el sistema DEBE tratarla como fallo, seguir con la reserva en la misma llamada del turno, aunque sea de otra familia, y conservar las herramientas ya ejecutadas sin repetirlas.
5. El sistema DEBE poder responder un turno con cualquiera de los seis modelos con un historial escrito por otro de ellos.
6. El sistema DEBE aprovechar la caché del proveedor de cada modelo, y un cambio de modelo NO DEBE hacer fallar un turno.
7. El plazo de cada llamada DEBE bastar para el modelo que la hace, también para los que razonan.
8. WHEN un agente usa algo que un modelo no puede ejecutar THEN el sistema NO DEBE ofrecer ese modelo para ese agente (ni como opción apagada) y, si ya estaba elegido, DEBE responder con un modelo que sí pueda y avisarlo en Avanzado.
9. El sistema DEBE tener una batería de compatibilidad en dos niveles, y un modelo NO DEBE habilitarse sin pasar los dos:
   - en el cable, en cada cambio: los parámetros que salen, el razonamiento entre llamadas, el saneado al cambiar de familia, un rechazo del proveedor y la permanencia en la reserva;
   - con el proveedor real, en staging: una respuesta sin herramientas, una cadena de tres herramientas, una imagen, un cambio de modelo entre turnos, la caída a la reserva a mitad de turno en las dos direcciones, el freno de reservas con reintento y un turno largo hasta el cierre.
10. WHILE un turno use un modelo que razona THE sistema NO DEBE cambiar, entre dos llamadas del turno, nada de lo que ya envió: ni las instrucciones de sistema, ni el conjunto de herramientas, ni los mensajes anteriores. Lo nuevo se añade al final.
11. IF el proveedor detecta un cambio en lo enviado que invalida un bloque de razonamiento THEN el sistema DEBE seguir el turno sin ese bloque, sin error. La batería de compatibilidad DEBE correr en modo estricto, de modo que cualquier cambio así sea un fallo visible antes de habilitar un modelo.
12. LiteLLM DEBE comportarse igual en todos los servicios y entornos: la misma versión en la API y en el worker, y su mapa de modelos fijo, sin descargarlo al arrancar.

### Requisito 5 — Lo que se mide y se informa

**Historia de usuario:** Como partner y como Auphere, quiero que el cobro y el informe de cada turno digan qué modelo respondió, para saber lo que pago y si el modelo elegido funciona.

#### Criterios de aceptación

1. El sistema DEBE registrar cada llamada con el modelo que la hizo y cobrarla con los pesos de ese modelo y el multiplicador de venta vigente.
2. IF un modelo usado no tiene pesos THEN el sistema DEBE avisar a Auphere y NO DEBE ofrecerse.
3. El sistema DEBE informar en cada turno del modelo que dio la respuesta y de si entró la reserva, también en los resultados de las pruebas y en el Playground.
4. El sistema DEBE dejar registrado cada fallo del modelo elegido, con el agente y el modelo, para que Auphere vea si un modelo falla más que otro.
5. El sistema DEBE cobrar la escritura en caché como un carril propio, con su peso sacado de la tarifa de escritura del modelo y el mismo multiplicador de venta que los demás, y NO DEBE cobrar esos tokens además como entrada. Los modelos sin tarifa de escritura no cambian.
6. WHEN una llamada pasa el umbral de un tramo de precio de su modelo (Haiku 5.5, más de 100.000 tokens de prompt) THEN el sistema DEBE cobrarla con los pesos de ese tramo.
7. Los pesos nuevos DEBEN seguir las reglas de la spec 059: editables en el panel, recalculados al cambiar el multiplicador y obligatorios para cobrar, también en el camino del copiloto.
8. El sistema DEBE registrar lo que GPT-5.6 escribe en caché, que el proveedor informa aparte de lo leído, y cobrarlo por el carril de escritura con la tarifa que publica OpenAI (1,25× la entrada).

### Requisito 6 — Pruebas y Playground

**Historia de usuario:** Como partner, quiero probar el agente con el modelo elegido antes de dejarlo, para no descubrir un problema con un cliente final.

#### Criterios de aceptación

1. La batería de pruebas y el Playground DEBEN usar el modelo efectivo del agente, resuelto como en el requisito 2.
2. Cambiar el modelo NO DEBE lanzar pruebas por su cuenta ni obligar a pasarlas para que el cambio valga.
3. Las pruebas que se pasen después de un cambio de modelo DEBEN cobrarse como cualquier otra pasada (spec 047, requisito 68).

### Requisito 7 — El panel de operador

**Historia de usuario:** Como Auphere, quiero ver y cambiar el modelo de cada agente y decidir qué modelos ve cada partner, para operar sin entrar en la consola de nadie.

#### Criterios de aceptación

1. El panel DEBE enseñar en la ficha de un cliente el modelo efectivo de cada agente y su origen.
2. El panel DEBE permitir a Auphere elegir para un agente cualquier modelo habilitado para responder en ese entorno, esté o no en la lista del partner, o devolverlo al modelo por defecto.
3. WHEN Auphere elige un modelo fuera de la oferta del partner THEN la consola DEBE enseñarlo con su precio estimado y una línea que diga que lo eligió Auphere y no está en su cuenta, y el partner solo DEBE poder cambiarlo a uno de su oferta.
4. El panel DEBE seguir permitiendo decidir, en la ficha de un partner, qué modelos tiene en su oferta.

### Requisito 8 — Ningún agente sin modelo

**Historia de usuario:** Como Auphere, quiero que retirar un modelo o quitárselo a un partner no deje a ningún agente sin responder.

#### Criterios de aceptación

1. El sistema DEBE contar como «en uso» un modelo que tenga elegido cualquier agente no archivado, y DEBE rechazar retirarlo o marcarlo «No disponible» diciendo qué agentes lo usan (spec 059).
2. WHEN Auphere quita un modelo de la oferta de un partner THEN el sistema DEBE pasar al modelo por defecto de Auphere los agentes que lo tenían elegido por el partner, desde el turno siguiente, y DEBE avisar al partner con el nombre de cada agente y el modelo con el que responde ahora.
3. Una elección hecha por Auphere fuera de la oferta NO DEBE quitarse al cambiar la oferta del partner.

### Requisito 9 — Lo que sigue apagado

**Historia de usuario:** Como Auphere, quiero que esta spec no reactive un camino que deja a los agentes sin modelo.

#### Criterios de aceptación

1. La consola NO DEBE enseñar «Calidad», «Fijar un modelo» ni los perfiles de modelo, y la API DEBE seguir respondiendo `409 model_policy_managed` a un cambio de política de modelo, hasta que una spec haga cierta la retención cero de los modelos.
2. Agente › Avanzado DEBE enseñar el selector de esta spec en lugar de la línea «El modelo de este agente lo gestiona Auphere».
3. La pantalla de modelo por cliente de la consola antigua DEBE desaparecer; la elección por cliente sigue disponible para Auphere desde el panel.

### Requisito 10 — Aislamiento

**Historia de usuario:** Como Auphere, quiero que la elección de modelo de un cliente no la lea ni la cambie nadie más.

#### Criterios de aceptación

1. El sistema DEBE tratar la elección de modelo de un agente como dato de su cliente: solo se lee y se escribe con el contexto de ese cliente, que decide el servidor, nunca un argumento del llamante.
2. Un partner NO DEBE poder leer ni cambiar el modelo de un agente de un cliente que no es suyo; la respuesta DEBE ser la misma que para un agente que no existe.
3. El transporte de los modelos nuevos DEBE hacer una petición por cliente y llamada, como los demás (garantía 7).

### Requisito 11 — La reserva es de la otra familia

**Historia de usuario:** Como Auphere, quiero que un fallo o un límite de cuota de un proveedor no deje sin respuesta a los clientes, para que la reserva sirva de verdad.

#### Criterios de aceptación

1. El sistema DEBE dar a cada modelo una reserva de la otra familia: un modelo de OpenAI cae a Claude Sonnet 5.5 y uno de Anthropic cae a Terra. Vale también para los agentes sin elección, que responden con el modelo por defecto de Auphere.
2. WHILE la reserva de la otra familia no esté habilitada para responder en ese entorno (requisito 1.3) THE sistema DEBE seguir usando la reserva de hoy (Sol).
3. WHEN la reserva de Anthropic entra en un turno después de que un modelo de OpenAI llamara a herramientas THEN el sistema DEBE seguir ese turno con el razonamiento apagado, de modo que ninguna llamada dependa de un bloque de razonamiento que no existe.
4. Las reservas propias de una asignación de cliente (`fallback_chain`) DEBEN dejar de usarse con el requisito 12; la cadena es: modelo efectivo → reserva de la otra familia.

### Requisito 12 — Un solo sitio: el modelo del cliente pasa a sus agentes

**Historia de usuario:** Como Auphere, quiero que el modelo de un agente se decida en un solo sitio, para que nadie tenga que adivinar de dónde sale.

#### Criterios de aceptación

1. Al desplegar, por cada cliente con modelo de respuesta propio, cada agente no archivado DEBE quedar con ese modelo como elección propia y responder con el mismo modelo que antes (CE-005). Quién la hizo DEBE salir de la auditoría (partner o Auphere) y, si no consta, DEBE marcarse como de Auphere.
2. La migración DEBE dejar en la auditoría de cada cliente qué asignación pasó a qué agentes, para poder deshacerlo, y NO DEBE fallar por los datos que encuentre.
3. Antes del despliegue, Auphere DEBE poder ver qué clientes tienen asignación de respuesta, con qué modelo, y cuáles tienen reservas propias o tope por turno, que dejan de usarse.
4. Después de la migración, el sistema NO DEBE leer la asignación de respuesta del cliente para decidir un modelo, y la consola y el panel DEBEN rechazar fijarla con un código propio. Las asignaciones de otros roles, como clasificar, NO DEBEN cambiar.
5. Un modelo heredado que no se ofrece (por ejemplo, Claude Sonnet 4.6) DEBE seguir respondiendo como hoy. El partner lo ve como elegido por Auphere y solo puede cambiarlo a uno de su oferta.
6. Las filas de las asignaciones de respuesta DEBEN conservarse sin uso durante una versión y borrarse después.

### Requisito 13 — El modelo por defecto de Auphere

**Historia de usuario:** Como Auphere, quiero decidir el modelo de los agentes sin elección propia en cada entorno, sin desplegar y sin mover los modelos de la plataforma, para pasar a todos a un modelo más barato de forma controlada.

#### Criterios de aceptación

1. El modelo por defecto de los agentes DEBE ser un ajuste de cada entorno, separado de los modelos de la plataforma (constructor, Playground, clasificador y sus reservas), que solo admite modelos habilitados para responder. Al desplegar DEBE ser el modelo con el que respondían los agentes sin elección (hoy Sol).
2. WHEN Auphere va a cambiarlo THEN el panel DEBE enseñar los agentes que cambiarán, con su cliente y su modelo de ahora, y DEBE cambiarlo solo tras la confirmación, con motivo y auditoría.
3. El cambio DEBE valer desde el turno siguiente de cada agente afectado, y volver atrás DEBE funcionar igual.
4. Las guardas de la spec 059 DEBEN tratar el modelo por defecto como en uso.
5. WHEN Auphere cambia el modelo de un agente por su cuenta (por defecto o elección) THEN el sistema DEBE devolverle la pasada de pruebas pagada por Auphere, como en la spec 047, requisito 68.14.
6. WHEN Auphere cambia el modelo por defecto THEN el sistema NO DEBE avisar a los partners: la consola enseña el modelo nuevo como «Ahora» desde el turno siguiente (Luis, 2026-11-20).

### Entidades clave

- **Elección de modelo de un agente**: el agente, el modelo elegido o ninguno, quién la hizo (partner o Auphere), cuándo. Es un dato del cliente.
- **Oferta de modelos de un partner**: los modelos que el partner puede elegir. Ya existe como lista de modelos permitidos por partner; esta spec la amplía a seis.
- **Modelo del catálogo**: un modelo con su proveedor, su estado, sus tarifas, sus pesos por carril, lo que sabe hacer y si ha pasado la batería de compatibilidad.
- **Perfil de llamada de un modelo**: lo que Auphere fija para cada modelo al responder: razonamiento, plazo y qué parámetros acepta.
- **Registro de auditoría**: cada cambio de modelo de un agente, con la persona, el agente, el modelo anterior y el nuevo.

## Criterios de éxito *(obligatorio)*

- **CE-001**: un partner cambia el modelo de un agente en menos de 30 segundos desde Avanzado, y el siguiente mensaje lo responde el modelo nuevo sin publicar versión.
- **CE-002**: cada uno de los seis modelos pasa entera la batería de compatibilidad contra el proveedor real en staging, con 0 turnos sin respuesta y 0 errores del proveedor por un parámetro no aceptado.
- **CE-003**: con el modelo elegido caído o rechazando, el 100 % de los turnos reciben respuesta y su informe dice que respondió la reserva.
- **CE-004**: en la conciliación de un día, lo descontado de la bolsa coincide al céntimo con los tokens de cada llamada a los pesos de venta del modelo que la hizo, y el margen de cada modelo queda por encima del suelo de 1,5.
- **CE-005**: al desplegar, ningún agente cambia de modelo: todos responden con el mismo que el día anterior.
- **CE-006**: un agente de recepción como el de Jemma, con la batería en verde, paga al menos un 45 % menos por respuesta con Terra o Luna que con Sol.
- **CE-008**: el cambio del modelo por defecto a Haiku 5.5 en prod se hace después de probarlo en unos pocos agentes reales, y no cambia ningún agente que no apareciera en la lista confirmada.
- **CE-007**: con el proveedor del modelo elegido sin servicio (simulado en staging), el 100 % de los turnos responden con la reserva de la otra familia.

## Fuera de alcance

- **El router, «Fijar un modelo» y los perfiles «Automático», «Económico», «Equilibrado» y «Máximo»**: siguen apagados (requisito 9).
- **Comparar modelos sin cambiar el del agente** (pasar la batería con un modelo candidato y ver los resultados lado a lado): se puede añadir después sobre esta spec.
- **Elegir modelo por intención** (uno para reservar y otro para informar).
- **Que el partner elija el nivel de razonamiento.**
- **Residencia en la UE**: los seis van por la API de cada proveedor, como hoy. Los borradores de Bedrock UE siguen siendo borradores.
- **Los modelos de la plataforma**: clasificador, constructor, copiloto, juez, visión y transcripción no cambian.
- **Cambiar el modelo por defecto a Haiku 5.5 en prod**: lo decidió Luis, pero es una operación posterior al despliegue (Historia 7), no parte de él.
- **La caché fría de la primera llamada de cada turno**: es otra palanca de coste y va aparte.

## Supuestos

- **Jemma pasa a Terra antes de esta spec**, con la asignación del cliente que ya existe (Luis, 2026-11-19, aplicado a las 19:00 UTC). Al desplegar, su agente queda con Terra elegido, y no cambia cuando el por defecto pase a Haiku 5.5.
- **Los seis modelos y la elección por agente** los pidió Luis el 2026-11-19, igual que la condición de que cambiar de familia funcione sin degradar el turno.
- **Decidido por Luis el 2026-11-19** (una pregunta, cuatro respuestas):
  - Los modelos de Anthropic se ofrecen **solo después de pasar la batería real en staging**, habilitados por Auphere desde el panel, entorno por entorno.
  - Es un **ajuste vivo**, fuera de la versión publicada: cambiar de modelo no obliga a publicar ni a pasar pruebas.
  - **La reserva es de la otra familia**: OpenAI → Claude Sonnet 5.5; Anthropic → Terra.
  - **Los seis, para todos los partners** por defecto. Auphere restringe por partner con la lista que ya existe en el panel.
- **Decidido por Luis después**, el mismo día:
  - **Se cobra todo al partner**: la escritura en caché y el recargo por tramos, porque el modelo solo cambia cuando el partner lo elige.
  - **También la escritura en caché de GPT-5.6** (Luis, 2026-11-19), que según la documentación de OpenAI se cobra a 1,25× la entrada y hoy el medidor registra a 0. Sube el precio de quien ya responde con Sol, Terra o Luna: en Jemma, un 21 %. Sin aviso a los partners (Luis, 2026-11-20).
  - **Un solo sitio**: el modelo del cliente pasa a sus agentes y deja de existir.
  - **El modelo por defecto de Auphere es Claude Haiku 5.5**, salvo Jemma (Terra). Detrás de la batería real y por etapas (Historia 7).
- Decidido en esta spec, para que Luis lo revise:
  - **El nivel de razonamiento lo fija Auphere por modelo**: adaptativo con esfuerzo bajo en los Claude 5.5, apagado en GPT-5.6 con herramientas (como hoy).
- **La reserva se cobra a su precio**: un agente en Luna que cae a Sonnet 5.5 paga esa llamada unas 9 veces más cara. Es raro (solo cuando su proveedor falla) y queda en `llm.respond_fell_back`. Alternativa para Luis: que Auphere absorba la diferencia.
- Opus 5.5, Sonnet 5.5 y Haiku 5.5 se llaman por la API de Anthropic, como Haiku 5.5 hoy, con la misma clave. Producción y staging ya llaman a Anthropic directamente.
- Las tarifas de Opus 5.5 y Sonnet 5.5 son las publicadas por Anthropic el 2026-11-19 (Opus 5.5: 4 / 20 por millón; Sonnet 5.5: 2 / 10), y Auphere puede editarlas en el panel como las demás (spec 059).
- Los pesos por carril de los modelos nuevos salen de sus tarifas con el mismo multiplicador que los demás, como en la migración del clasificador.
