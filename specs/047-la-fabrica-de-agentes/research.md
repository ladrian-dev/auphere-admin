# Research — spec 047, la fábrica de agentes

Las decisiones del plan, con su porqué y lo que se descartó. Las fuentes son las
de la spec:

- la nota de KB `research/2026-10-26-fabrica-de-agentes-v2/`, de `00` a `06`, con
  citas `ruta:línea` del código del 26 de octubre;
- la investigación `research/2026-10-24-rediseno-creacion-de-agentes/`;
- las decisiones del owner del 26 de octubre.

Las decisiones marcadas **(owner)** no se reabren aquí. El owner puede reabrir
cualquiera de las demás; si cambia una, cambia también la spec en el mismo commit.

---

## Parte 1 — El modelo

### D1 · Una spec para todo el programa, con historias que se entregan solas

**Decisión.** Una sola spec, la 047, con 33 historias y 56 requisitos. `plan.md`
agrupa las historias en olas, y `tasks.md` es el único plan de ejecución. Cada
historia se puede probar y desplegar sola, detrás de la activación por partner (D38).

**Por qué.** El modelo de objetos es uno solo: cliente, ficha, agente, canal y bolsa.
Repartirlo en varias specs habría dejado varias versiones del mismo modelo
avanzando a la vez, que es justo el problema de hoy, con el horario en tres copias.

**Descartado.**
- **Una spec por superficie** (consola, app, admin): duplica las decisiones de datos.
- **Una spec de cimientos aparte**: los requisitos 1 a 3 no tienen valor sin sus
  historias, y el aislamiento se prueba con las tablas reales.

### D2 · Crear un cliente nunca crea un agente

**Decisión.** El alta pide tres datos (nombre, nicho e información) y crea el
cliente, su ficha vacía y su bolsa vacía. Nada más. La plantilla por defecto del
partner (blueprint) pasa a ser el punto de partida de «Nuevo agente». El ciclo de
vida del cliente se separa de la preparación de cada agente:
- `provisioning` deja de significar «sin agente o sin canal»;
- el estado visible de cada agente se deriva (D7).

**Por qué.** Es la tesis del diseño: un cliente es un negocio y un agente es quien lo
atiende. Hoy el alta pide 12 campos porque mezcla los dos objetos (spec 019).

**Descartado.** Crear un agente vacío con cada cliente: deja agentes fantasma en
borrador y obliga a explicar un estado que nadie pidió.

### D3 · La ficha en tablas; el ClientSpec es su vista tipada

**Decisión.** La fuente de verdad del negocio son tablas normalizadas por cliente:
- `business_profiles`;
- `business_locations`;
- horarios con turnos y fechas especiales (D15);
- servicios con `agent_services` (D16);
- `business_links`;
- conocimiento en dos capas (D14).

Cada dato guarda su procedencia y su historial. El `ClientSpec` es un documento
Pydantic con `extra="forbid"`, versionado, con tres usos:
- es la vista que lee el constructor;
- es el formato de los parches que propone (D17);
- es el formato de importar y exportar.

Aplicar un parche pasa por el mismo servicio que la edición a mano, con la
procedencia «propuesto por el constructor».

**Por qué.**
- Las reservas, la consola lite y el agente necesitan consultar campos (huecos por
  servicio, horario de una sede) con RLS y FK compuestas. Un JSON no da eso.
- Un documento tipado da al constructor un contrato que se valida sin LLM, como ya
  hace `ConsolePolicy` (`agent_console_policy.py:37-38`).

**Descartado.**
- **El ClientSpec como JSON fuente en `tenants`**: otra copia más del horario, sin
  FK hacia `reservation_services` ni RLS por fila.
- **Sin documento tipado**: el constructor escribiría directo en tablas, sin un
  formato de propuesta que se pueda comparar y deshacer.

### D4 · El AgentSpec y una compilación determinista por versión y por revisión

**Decisión.** Cada versión de agente guarda un AgentSpec tipado (requisito 16).
La compilación del prompt es código puro:

> AgentSpec + ficha (revisión) + conocimiento del agente (revisión) + herramientas → texto

El resultado se escribe en `agent_configs.system_prompt_rendered` de la versión,
que sigue siendo la verdad del runtime (constitución, «Restricciones adicionales»).
Cada compilación queda además en `agent_version_compilations`, con su huella
`sha256` y las revisiones de las que salió.

Cuando cambia la ficha o el conocimiento, se compila de nuevo la versión activa y
se reescribe su `system_prompt_rendered` en la misma transacción. No se crea una
versión nueva. El runtime sigue leyendo esa columna, ya renderizada: no hay
plantillas en tiempo de ejecución (garantía 5).

**La ficha y el conocimiento van como datos, nunca mezclados con las
instrucciones** (§III). Van en un bloque vallado aparte (`core/guardrails/untrusted.py`),
después de las instrucciones del agente y dentro del prefijo cacheable.

Hay dos modos:
- **«Instrucciones»**: los agentes migrados. El prompt es el de hoy, byte a byte.
  Cuando el negocio cambie por primera vez un dato de la ficha, la compilación
  añade el bloque «Datos vigentes del negocio», que manda sobre las instrucciones.
  Además, la revisión automática propone quitar de las instrucciones la copia vieja.
- **«Estructurado»**: identidad, objetivo, procedimientos, habilidades, políticas y
  disparadores. Es el modo de los agentes nuevos.

**Por qué.**
- La ficha se aplica al momento (requisito 3.1), y el agente tiene que decir el
  horario nuevo desde el siguiente mensaje (historia 29). Una versión nueva por
  cada cambio de horario llenaría el historial de ruido y obligaría a pasar la
  puerta por un dato.
- La compilación por revisión mantiene la garantía 5 y deja trazado qué prompt
  respondió cada turno.

**Descartado.**
- **Plantilla en tiempo de ejecución** con la ficha: rompe la garantía 5.
- **Una herramienta «horario» en vez de un bloque en el prompt**: el agente no la
  llamaría en las preguntas de pasada («¿abrís mañana?»), y sumaría una llamada por turno.
- **Recompilar los agentes migrados al migrar**: rompería el «responde igual» (CE-009).

### D5 · Un solo borrador por agente, con concurrencia optimista

**Decisión.** Hay como mucho un borrador por agente, con un número de revisión.
Cada escritura manda `If-Match` con la revisión que leyó. Si no coincide, la API
responde 412 con lo que cambió, y la consola enseña los dos cambios sin perder
ninguno. Las propuestas del constructor, el copiloto o las sugerencias se aplican
sobre el borrador con el `state_hash` del mapa de propuestas de hoy, y caducan a
los 15 minutos (§IV).

**Por qué.** Hoy hay tres formas de guardar en la ficha del agente y se pierden
cambios (historia 2). Ya existe el patrón `If-Match` con 412 en Reservas (spec 043),
y el de `state_hash` en el Companion.

**Descartado.**
- **Varios borradores** con fusión: nadie del segmento lo necesita y complica la puerta.
- **Bloqueo pesimista**: deja agentes bloqueados por pestañas abiertas.

### D6 · Guardar es publicar, a través de la puerta, con deshacer

**Decisión.** «Guardar» encadena compilar, validar, pasar la suite, la revisión
automática y la puerta, y publica si pasa. Después hay 10 minutos para «Deshacer»,
y el historial permite «Restaurar». El estado que el diseño llamaba «Publicado» se
rotula «Atendiendo» solo si hay un canal en «A todos» (D7).

**Por qué.**
- La crítica del diseño marcó «Revisar borrador» como una pantalla de más.
- El riesgo de publicar lo cubren la suite, la puerta y el deshacer, no un clic más.
- El driver de evaluación ya sabe ejecutar una versión sin publicar: el playground
  y la suite corren sobre el borrador.

**Descartado.**
- **Guardar sin publicar y un «Publicar» aparte**: dos estados de «guardado» que el
  partner no distingue.
- **Publicar sin suite**: deja pasar regresiones (CE-006).

### D7 · Estados guardados y estado visible derivado

**Decisión.** Se guarda poco y se deriva lo demás:
- **Del agente** se guarda el estado de vida (borrador, publicado, en pausa con
  motivo, archivado).
- **De cada canal** se guarda su estado.
- **El estado visible** se calcula en un solo sitio de la API: Borrador, Listo · sin
  canal, En prueba, Atendiendo, Pausado · motivo o Archivado. Lo consumen la consola,
  la consola lite y la app, con los mismos textos y colores.

**Por qué.** Hoy la consola infiere estados por su cuenta y se contradice entre
pantallas (el prototipo también: `01` §10). Un estado guardado que se puede derivar
acaba desincronizado.

**Descartado.** Guardar el estado visible como columna: se desincroniza al pausar un
canal o al cambiar la audiencia.

---

## Parte 2 — El turno y los mensajes

### D8 · Guardar antes de decidir, y la Bandeja con motivo

**Decisión.** El despachador guarda el mensaje entrante antes de cualquier puerta:
saldo, tope, pausa o audiencia. Hoy la puerta de saldo va antes de
`persist_inbound_message` (`dispatcher.py:215` frente a `:374`). El resolutor de
números reconoce también los canales en pausa, degradados y con su agente en pausa.

Si el agente no responde, la conversación guarda el motivo, con un código de una
lista cerrada (`no_balance`, `agent_cap`, `paused_agent`, `paused_channel`,
`paused_client`, `out_of_audience`, `no_model`, `provider_failure`, `turn_limit`) y,
salvo fuera de audiencia, pasa a «Espera a una persona».

Una conciliación diaria compara lo que Meta entregó con lo guardado.

**Por qué.** Hoy, sin saldo, el mensaje ni se guarda (`04` §A6). Es la pérdida más
grave del sistema, y el arreglo es de orden, no de diseño.

**Descartado.** Responder con un mensaje genérico sin guardar: sigue sin dejar rastro.

### D9 · Un turno a la vez por conversación, con agrupación de 3 segundos

**Decisión.**
- Un candado por conversación (advisory lock de Postgres, con la clave de la conversación).
- Una ventana de agrupación de 3 segundos, configurable por Auphere.
- Idempotencia de cada efecto con la clave `turno:acción`.
- En la última iteración de herramientas, una respuesta final forzada sin herramientas.

**Por qué.** Los mensajes seguidos («hola» / «quería una cita» / «para mañana»)
producen hoy respuestas cruzadas y acciones repetidas. Los candados por advisory
lock ya se usan en Reservas.

**Descartado.** Una cola por conversación en Redis: otra pieza que operar, y Redis
no es la fuente de verdad del turno.

### D10 · La audiencia vive en el canal (enmienda a la spec 024)

**Decisión.** Cada canal tiene «Solo mi equipo» (números de prueba) o «A todos»
(con excepciones). Los permisos de las personas del equipo (`full` o `readonly`),
que deciden qué herramientas usan, siguen en el agente. Una plantilla de solo
administradores bloquea «A todos».

**Por qué.** La audiencia depende del número, no del comportamiento: el mismo agente
puede estar «A todos» en un número y en prueba en otro. Hoy, cambiar a quién
responde obliga a publicar una versión.

**Descartado.** Dejarla en la versión: el estado «En prueba» por canal sería imposible.

### D11 · El escalado avisa a los destinatarios del canal

**Decisión.**
- **Disparadores** (cuándo se pasa a una persona): en el AgentSpec.
- **Destinatarios** (a quién se avisa y por dónde): en el canal, hasta 10 personas,
  por WhatsApp, correo o Bandeja, con un resumen opcional.

Las tres vías implícitas de hoy pasan a ser destinatarios explícitos:
- la plantilla al `owner_phone`;
- el canal de respaldo de ADR-018;
- la Bandeja.

**Por qué.** Hoy no hay destinatarios: se avisa por tres caminos que nadie configura
(`02` §C2).

### D12 · WhatsApp: coexistencia con Embedded Signup v5 en el móvil del dueño, y la beta por país (owner)

**Decisión.** Es la opción A de la nota `05`, con la B como piloto donde Meta la habilite:
- **Por defecto**: el enlace del dueño abre ES v5 en coexistencia, en el navegador del
  móvil. El dueño entra una vez en Meta, y el QR le llega por WhatsApp.
- **Migración**: ES pasa de `sessionInfoVersion: "3"` a v5 (cuentas WAAC,
  `messaging_account_ids`, `is_on_biz_app`). La suscripción incluye los avisos de
  coexistencia (`smb_message_echoes`, `history`, `smb_app_state_sync`, `account_update`).
- **Ecos**: un mensaje que el negocio envía desde la app es de una persona del negocio,
  y la conversación pasa a «La lleva una persona» durante 2 horas (requisito 30.11).
- **La beta «WhatsApp login»** se activa por país desde el admin cuando Meta la dé a
  la app de Auphere, nunca para números de la UE.
- **Reconectar** combina lo nuevo con lo que había: corrige el `config` que se
  sobrescribía (`signup.py:473`).

**Por qué.**
- Meta no ofrece una vía general sin identidad de Meta. YCloud la ofrecía con una beta
  de BSP que no vale para la UE.
- Alojar números de clientes en la WABA de Auphere va contra el modelo de Tech
  Provider (ADR-027), y el cliente perdería sus activos (`05` §3.2).

**Descartado.**
- **WABA propia de Auphere para clientes** (opción D).
- **Clientes no oficiales** (opción E): prohibidos.
- **Volver a un BSP** para tener la beta: deshace ADR-027.

### D13 · La configuración, en su canal o su integración; autorizar una vez y activar por agente

**Decisión.**
- **Canales.** La página de cada canal reúne su audiencia, sus excepciones, sus
  destinatarios de escalado, su mensaje de espera, su catálogo, sus horas de silencio
  y su salud.
- **Integraciones.** La conexión (cuenta y credenciales) es del cliente con el
  servicio, y queda como hoy en `tenant_connectors` con UNIQUE (cliente, servicio).
  La activación es nueva y por agente (`agent_connector_activations`), con su permiso
  («Solo leer», «Preguntar antes de escribir» o «Leer y escribir») y sus ajustes,
  declarados en el catálogo de la integración.
- **Ajustes repartidos.** Los de hoy (la URL de AgendaPro, WooCommerce, Amigable,
  los recordatorios) pasan a la página de su integración.

**Por qué.**
- El usuario lo pidió.
- Hoy los ajustes viven repartidos y `default_mode` no se aplica (`02` §D).
- Una autorización por agente obligaría a repetir OAuth y multiplicaría credenciales.

**Descartado.** Conexiones por agente: el negocio tiene una sola cuenta de Google
Calendar, no una por agente.

### D14 · Conocimiento en dos capas y búsqueda exacta por cliente

**Decisión.**
- **Dos capas**: la del negocio (`agent_id` nulo) y la propia del agente. Un agente
  ve la suya y la del negocio, nunca la de un hermano (garantía 9).
- **Si cabe en el presupuesto de conocimiento** del agente (por defecto 20.000
  caracteres, el recorte de hoy, que Auphere puede ajustar), va entera en la
  compilación, como bloque de datos vallado (D4), y se aprovecha la caché.
- **Si no cabe**, búsqueda híbrida:
  - semántica, con pgvector, que ya está instalado y sin usar;
  - por palabras, con la configuración `spanish` de Postgres;
  - las dos combinadas por fusión de rangos;
  - filtradas por cliente y capa dentro de la propia consulta.
- **Sin índice ANN compartido**: búsqueda exacta sobre las filas del cliente (cientos
  o pocos miles de fragmentos por negocio), con un índice btree por (`tenant_id`, `agent_id`).
- **Embeddings**: los calcula Titan v2 en `eu-south-2` (tarea 10 del router).

**Por qué.**
- El requisito 38.4 pide que el índice no se comparta entre clientes.
- Un HNSW sobre una tabla común es un índice compartido, y con filtros pierde
  recall (post-filtrado).
- A este tamaño, la búsqueda exacta cuesta milisegundos.

**Descartado.**
- **HNSW global con RLS**: lo descartan el requisito 38.4 y el recall con filtros.
- **Particiones por cliente**: demasiado pronto. Se revisa si un cliente pasa de
  50.000 fragmentos.
- **Un servicio vectorial externo**: un subprocesador más, sin necesidad.

### D15 · Una sola fuente del horario, con turnos nocturnos y fechas especiales

**Decisión.**
- **Tablas.** `business_schedules` (del cliente, o de una sede), `business_shifts` y
  `business_special_dates`.
- **Turnos.** Se guardan en minutos desde la medianoche del día en que abren. Un
  cierre por encima de 1.440 cae al día siguiente, y «abierto 24 horas» es 0–1.440.
- **API.** Habla `HH:MM`, y un cierre igual o anterior a la apertura significa
  «día siguiente», como en el prototipo.
- **Un solo servicio** (`business_hours`) responde «¿abierto ahora?», da la frase
  «Así lo dirá el agente» y da los huecos de Reservas. Usa la zona del negocio, los
  nocturnos y las fechas especiales, también los días de cambio de hora.
- **Las tres copias de hoy** desaparecen:
  - la frase del prompt (`tenant.business_hours_label`) pasa a ser derivada;
  - `policies.console.schedule` migra a la ficha y sale de la versión;
  - `tenants.business_hours` se escribe como proyección, en la misma transacción,
    hasta que Reservas lea el servicio nuevo, y después se retira.

**Por qué.**
- Hoy hay tres copias que no se hablan, y el agente no lee nunca la de Reservas
  (`03` §2.2).
- Ninguna de las tres admite turnos nocturnos.

**Descartado.**
- **Marcar «día siguiente» con un booleano por turno**: dos representaciones del
  mismo hecho (cierre ≤ apertura y la marca) que pueden contradecirse.
- **Guardar intervalos UTC**: rompe en los cambios de hora.

### D16 · Servicios: los de Reservas, más los no reservables y quién los ofrece

**Decisión.**
- **Tabla.** Se reutiliza `reservation_services` (spec 043, hoy en `develop`), con
  estos añadidos:
  - descripción;
  - `bookable` (los no reservables no llevan duración);
  - precio en la moneda de precios del cliente;
  - procedencia.
- **Quién atiende.** Las personas que lo atienden siguen como hoy (`all_staff` y su
  tabla). `agent_services` dice qué agentes lo ofrecen, y una marca en el agente dice
  «todos los servicios».
- **Moneda.** La moneda de precios es ISO 4217, deducida del país del cliente.

**Por qué.** Es el mismo objeto: duplicarlo para la ficha volvería a crear dos
fuentes. La 043 ya resolvió el equipo y la duración.

**Descartado.** Una tabla `business_services` aparte.

---

## Parte 3 — Construir, probar y publicar

### D17 · El constructor: un motor que propone, para agentes, clientes y canales

**Decisión.** El constructor es un motor del núcleo, sin depender del módulo
`companion`, que siempre propone y nunca aplica:
1. Lee la descripción, la ficha (ClientSpec) y el catálogo de herramientas.
2. Hace como mucho 5 preguntas, cada una con su porqué.
3. Devuelve un parche tipado (AgentSpec o ClientSpec) con salida estructurada estricta.
4. Un validador sin LLM comprueba el parche antes de enseñarlo y otra vez al aplicarlo.

Funcionamiento:
- **Dónde corre**: en el worker, como un trabajo con estado en una tabla
  (`build_jobs`), igual que el indexador.
- **Cómo lo sigue la consola**: consulta el estado con espera creciente.
- **Objetivo**: el borrador en menos de 30 s en el p90.
- **Modelo**: el de la tarea «construir» (Sonnet 5.5 `eu.` por defecto; Haiku 5.5 para
  preguntas y pruebas).
- **Quién paga**: «Construcción y pruebas».

**Por qué.**
- Es lo que hacen Copilot Studio, Agentforce, Fin y Sierra: describir, revisar un
  borrador y simularlo (`2026-10-24` §2).
- Propuesta y confirmación humana es la regla §IV.
- Un trabajo en el worker sobrevive a cerrar la pestaña.

**Descartado.**
- **Que el constructor escriba directamente**: viola §IV.
- **Una llamada síncrona desde la API**: 30 segundos colgados de una petición.
- **Seguir con el Companion como constructor**: es un módulo que la 032 permite
  apagar, y su expediente pierde datos (`03` §2.3).

### D18 · Veinte pruebas, tres pasadas y un juez de otra familia

**Decisión.**
- **Las pruebas**: 8 del caso, que genera el constructor, y 12 del sector, de un
  catálogo versionado por sector que edita Auphere.
- **Las pasadas**: cada prueba corre 3 veces. Pasa con 3 de 3; con 1 o 2 de 3 es
  «Inestable».
- **Quién simula**: el cliente simulado es un modelo barato, y el juez es de una
  familia distinta a la del agente.
- **Los lotes**: van por cliente (garantía 7).
- **Las pruebas que no aplican**: se marcan con su razón y no cuentan para la puerta.

**Por qué.**
- Una sola pasada no distingue un acierto de una casualidad. τ-bench mide pass^k
  por eso.
- Un juez de la misma familia perdona sus propios sesgos.

**Descartado.** Cinco pasadas: duplica el coste de la partida sin cambiar la
decisión en el segmento pyme.

---

## Parte 4 — Modelos

### D19 · Perfiles con paso directo (owner)

**Decisión.** Cada turno se cobra a 2,2× el coste del modelo que respondió, como
hoy; ADR-037 no cambia. Los perfiles cambian qué modelo responde, no el multiplicador.
El partner ve el precio estimado por mensaje antes de elegir y el real después.

**Consecuencias:**
- el precio por mensaje varía con el modelo que el router elige, así que la pantalla
  enseña una estimación con el perfil de turno medido del agente;
- el margen se mantiene constante (54,5 %);
- bajar el modelo por defecto baja el precio al partner, no el margen.

**Descartado** por el owner: el precio fijo por perfil que recomendaba la
investigación.

### D20 · El router: una política en Nexus; LiteLLM solo transporta

**Decisión.** La política vive en `model_resolver.chain_for`, que ya es el único
punto de decisión, ampliada con la tarea y el perfil. Sigue los seis pasos de `06` §4.2:
1. catálogo de despliegues;
2. calidad certificada por (despliegue, tarea, idioma);
3. filtro duro (capacidad, residencia, retención, licencia, lista permitida);
4. orden por precio dentro de la latencia;
5. cadena de dos alternativas en otros proveedores;
6. registro de la decisión.

Reparto del trabajo:
- **LiteLLM** (librería, fijada `<1.106`, ADR-036) pone el transporte: grupos de
  despliegues, enfriamientos y reintentos.
- **La afinidad** va en `pinned_model`, dentro del checkpoint del hilo
  (`TenantScopedPostgresSaver`): está aislada por cliente, sobrevive a reinicios y no
  depende de Redis.
- **El escalado** es una subllamada aislada: el bucle principal no cambia de modelo
  y conserva su caché.

**Por qué.**
- Los sistemas que lo hacen bien no adivinan la complejidad del texto: aplican una
  política declarativa sobre un catálogo (`06` §4.2).
- Las señales que predicen dificultad salen de lo que pasa en el turno.

**Descartado.**
- **El auto-router de LiteLLM**: es beta, y su propio benchmark sale casi al azar.
- **Jev como decisor**: alojado en EE. UU. y sin región UE (`06` §4.5).
- **El Model Router de Azure**: en la UE no enruta a Claude.
- **Cambiar de modelo a mitad de conversación**: pierde la caché y la coherencia.

### D21 · Proveedores nuevos: Bedrock y Scaleway; licencias

**Decisión.** Entran AWS Bedrock (inferencia en la UE) y Scaleway, además de los
directos (`06` §5.2). Los modelos abiertos solo entran con licencia leída y
compatible:

| Licencia | Modelos |
|---|---|
| Apache-2.0 | gpt-oss, Mistral Small 4, Gemma 4 |
| MIT | GLM, DeepSeek V3.2 y V4 |
| MIT modificada | Kimi, que se lee entera antes de activar |
| Excluidos | Llama 4, por su cláusula UE para modelos multimodales; Qwen3.8-Flash-Next, por su cláusula MaaS sin umbral |

Tres condiciones más:
- **Subprocesadores.** Antes de activar, Bedrock (inferencia) y Scaleway entran en el
  DPA y en la lista pública.
- **Credenciales.** Bedrock usa el rol IAM de la tarea ECS. La clave de Scaleway va
  en Secrets Manager.
- **Fuera**: Groq, Together, Fireworks, DeepInfra y Cerebras, que no tienen
  inferencia serverless en la UE.

**Por qué.**
- Bedrock está en la misma cuenta, AWS ya es subprocesador y da Claude con residencia UE.
- Scaleway es el respaldo europeo fuera de AWS: retención cero por defecto y avisos
  de retirada de 3 meses o más.

### D22 · Residencia por cliente, con valor por defecto según su país, y la restricción soberana

**Decisión.**
- **«Solo UE»** nace activada en los clientes de la UE y del EEE, y el partner la
  puede cambiar.
- **La restricción soberana** (solo proveedores europeos y pesos abiertos) la fija
  Auphere por contrato. El partner la ve como insignia.
- **Los proveedores sin región UE**: solo en tareas sin datos personales, y nunca con
  «Solo UE».

**Por qué.**
- La residencia es una exigencia del cliente final, no del partner.
- Un quinto perfil mezclaría calidad con jurisdicción (`06` §5.1).

### D23 · Certificación por clase y por agente

**Decisión.**
- **Por clase de tarea**: una batería común en español, con variantes de cinco países
  y tú y usted. Incluye los 95 casos del driver, el paquete `es` de τ-bench 2.0 y un
  dominio propio de reservas.
- **Por agente**: su suite. Pasa si todas las críticas pasan 3 de 3 y la nota no baja
  más de 2 puntos frente al despliegue con el que está publicado.
- **Caducidad**: se certifica por despliegue, no por modelo, porque la cuantización y
  el parser de herramientas cambian por host.
- **Quién paga**: el partner, en «Construcción y pruebas», cuando lo lanza él; Auphere,
  fuera de las partidas, cuando lo lanza Auphere.

**Por qué.** No hay evidencia pública de tool-calling en español (`06` §3): la
batería propia es la única puerta honesta.

### D24 · Los agentes nuevos nacen en «Automático»; los existentes conservan su modelo

**Decisión.**
- **Agentes nuevos**: nacen en «Automático».
- **Agentes migrados**: quedan con su modelo de hoy fijado, y la pantalla «Calidad»
  les propone «Automático» con su precio estimado. El cambio lo hace una persona y
  pasa por su suite.
- **`classify`**: deja `gpt-5.6-sol` en todos, porque no es una tarea de conversación
  y el modelo fijado no la cubre (requisito 39.8). Pasa al certificado más barato.

**Por qué.**
- Es la palanca de 28 a 40 veces (`06` §5.3), y el owner pidió básicos y medios por defecto.
- Cambiar en silencio el modelo de respuesta de un agente en producción rompe el
  «responde igual» (CE-009).
- El clasificador sí puede moverse, porque su efecto se mide con la batería.

**Descartado.** Mover todos los agentes a «Automático» en la migración.

---

## Parte 5 — Dinero

### D25 · La bolsa es dinero apartado, con libro de doble entrada (owner)

**Decisión.**
- **Asientos gemelos.** Cada traspaso escribe dos asientos: uno en la cuenta del
  partner y otro en la bolsa del cliente.
- **Saldo.** La bolsa materializa su saldo, con un CHECK que lo mantiene en cero o más.
- **Idempotencia.** Cada traspaso lleva su clave.
- **Cambio.** Cada asiento guarda el cambio del día que usó.
- **Turnos.** El débito de un turno va a la bolsa. El turno que cruza el cero se cobra
  hasta lo que quedaba, y el resto lo absorbe Auphere, como hoy (`wallet.py:104-111`).
- **Unidades.** Cien milésimas de la moneda, como los créditos de hoy.
- **Cuadre.** Un proceso diario comprueba que cuenta + bolsas + gastado cuadran al céntimo.

**Por qué.**
- Hoy «asignar» es un límite mensual que no aparta dinero, y la suma de topes puede
  superar el saldo (`04` §A3).
- El owner eligió dinero apartado.

**Descartado** por el owner: el límite mensual de hoy.

### D26 · Dos monedas que no se mezclan, con el cambio del BCE

**Decisión.**
- **Dinero.** La cuenta y las bolsas van en EUR o USD.
- **Precios del negocio.** Van en ISO 4217, deducida del país.
- **Cambio.** El de referencia del BCE, que un cron del worker descarga cada día
  hábil a las 16:30 CET a `fx_rates`. Los días sin publicación se usa el último.
- **Cobro.** Stripe cobra en la moneda de la cuenta.
- **Partners existentes.** Quedan en USD.

**Por qué.** Es una fuente pública, gratuita y diaria, que la consola puede citar
(«BCE {fecha}»). Mezclar las dos monedas es justo lo que el prototipo hacía mal
(una rama CLP muerta).

**Descartado.**
- **Un proveedor de cambio comercial**: un subprocesador más, sin necesidad.
- **Bolsas en la moneda local**: el dinero de Auphere no se mueve en CLP.

### D27 · El tope por agente y la base del 20 %

**Decisión.**
- **Tope por agente**: opcional, mensual (mes natural UTC) y en la moneda de la bolsa.
- **Avisos**: avisa al 80 %; al 100 %, el agente se pausa con su motivo.
- **«Queda poco»**: se mide contra una base, que es el saldo al empezar el mes más lo
  asignado en el mes.

**Por qué.** Una bolsa sin periodo no tiene un 100 % natural. La base da un 20 %
estable, que no salta con cada asignación.

**Descartado.** El 20 % sobre lo asignado de toda la vida de la bolsa: con meses de
historia, el aviso no saltaría nunca.

### D28 · «Pedir saldo»: lo ven builder, analyst y billing en la consola de partners

**Decisión.** Quien no puede asignar ve «Pedir saldo». Avisa a owners y admins, como
mucho una vez al día por cliente. No existe en la consola lite ni en la app (specs
031 R4.4 y 044 R13.4).

**Por qué.** Hoy, sin permiso, la acción desaparece y nadie se entera (`04` §A8).
Billing paga pero no reparte.

### D29 · «Construcción y pruebas»: un tope en dinero por partner

**Decisión.**
- **Qué incluye**: el constructor, el playground, las pruebas, las simulaciones y su
  juez, la lectura de webs, la indexación, las sugerencias semanales y las
  certificaciones que lanza el partner.
- **Quién paga**: Auphere, hasta un tope mensual a precio. Por defecto son 50 en la
  moneda de la cuenta, y Auphere lo ajusta por partner.
- **Tokens**: sustituye al tope de 2 M de tokens del playground, que hoy se enseña en
  tokens contra la spec 033.

**Por qué.**
- Crear un agente cuesta a Auphere unos 2–3 $: el borrador, unos 0,3 $, y cada suite
  completa, algo más de 1 $.
- 50 a precio dan para unos 8 agentes nuevos al mes, con sus iteraciones.

**Descartado.**
- **Cobrar la construcción al partner**: frena justo lo que se quiere fomentar.
- **Dejarla sin tope**: abre el abuso.

### D30 · «Mensajes de Meta» se enseña, pero no se cobra de la bolsa

**Decisión.** La partida enseña la estimación de `messages.cost_usd`: las plantillas
y los mensajes de servicio por encima de los 1.000 gratuitos al mes por número, desde
el 2026-10-01. Va convertida a la moneda de la cuenta, con «aprox.».

**Por qué.** Con Auphere como Tech Provider, Meta factura a la cuenta de WhatsApp
del negocio, no a Auphere (`pricing_policy.py:52-71`). Cobrarlo de la bolsa sería
cobrarlo dos veces.

---

## Parte 6 — Personas, consola, app y operación

### D31 · Sin papeles dentro del cliente (owner)

**Decisión.** Todas las personas del cliente pueden pausar, editar la ficha y
corregir. Cada cambio lleva su nombre y su origen, avisa al partner y se puede
deshacer.

**Mitigaciones:**
- el historial y el deshacer de cada sección;
- el aviso al partner;
- la auditoría con nombre;
- las acciones de comportamiento (corregir cómo responde) siguen pasando por el partner.

**Descartado** por el owner: los papeles «Responsable» y «Equipo» que recomendaba la
investigación.

### D32 · La consola lite y la app: Agentes y Negocio, y escrituras solo con conexión

**Decisión.**
- **Secciones nuevas**: «Agentes» y «Negocio», en web y en móvil, solo por
  `/console/lite/*` y `/app/*`.
- **Sin conexión**: la app no encola escrituras. Dice que hace falta conexión y
  conserva lo escrito.
- **Avisos**: tipos de push nuevos.
- **Publicación**: una versión nueva en las tiendas. OTA, solo para arreglos.

**Por qué.**
- Una cola local de cambios de horario o de pausas que se aplica horas después es
  peor que no guardarla.
- La regla de la 031 es que lo que cambia permisos o pantallas va por las tiendas.

### D33 · El marco común y `@nexus/ui`

**Decisión.**
- **Evolucionar, no sustituir.** `@nexus/ui` gana el primario verde profundo
  (≥ 4,5:1, objetivo 6,8:1), las pestañas en píldora, los modales con trampa de foco,
  los avisos que no se van mientras tienen el foco y la gráfica de bloques.
- **La gráfica de bloques** es SVG y CSS propios, sin dependencias nuevas.
- **La paleta ⌘K** se monta sobre los primitivos que ya tenga la consola. Si hiciera
  falta una librería, entra con su tarea de licencia.
- **Lo que no se toma del prototipo** está en `01` §10:
  - avisos sin pausa;
  - el menú de perfil oculto en móvil;
  - la navegación sin historial;
  - la paleta que no busca agentes;
  - guardar un canal que reanuda el agente;
  - los importes que no leen lo que se teclea.

**Por qué.**
- La crítica del diseño suspendió la consola en consistencia (29 de 40).
- La regla del workspace pide tokens y cinco estados por vista.

### D34 · Rendimiento y sugerencias, sin que el partner lea nada

**Decisión.**
- **Dónde se generan**: en el worker, con el contexto del cliente (garantía 1).
- **Qué agrupan**: al menos 5 conversaciones de al menos 5 contactos.
- **Qué llevan**: una paráfrasis sin datos personales y una propuesta con su prueba.
- **Qué sale hacia la API**: solo el resultado agregado.
- **Barrido**: comprueba que ninguna respuesta de `/console/*` lleva cuerpos de mensaje.

**Por qué.** C1: el partner puede hacer todo menos leer conversaciones. Con 5
contactos o más, una sugerencia no apunta a nadie.

**Descartado.** Enseñar fragmentos «anonimizados»: no hay anonimización fiable de
texto libre.

### D35 · Corregir desde la Bandeja: dato o comportamiento

**Decisión.**
- **Un dato** se aplica al momento a la ficha o al conocimiento, con historial y deshacer.
- **Un comportamiento** llega al partner como propuesta con su prueba.
- **La paráfrasis** la genera un modelo y la revisa la persona antes de enviarla.
- **Datos personales**: un detector (teléfonos, correos, documentos y nombres del
  contacto) bloquea guardarlos en el conocimiento del negocio (garantía 8).

**Por qué.** El negocio sabe la respuesta y el partner no puede leer el mensaje (C1).
Los datos son del negocio; el comportamiento, del partner.

### D36 · Recepción que deriva, como herramienta (P3)

**Decisión.**
- **La herramienta**: `recepcion.derivar` (nombre provisional), limitada a los agentes
  de su lista.
- **Qué cambia en el hilo**: el agente que responde, pero no la clave del hilo.
- **Qué separa el estado del hilo** por agente: el modelo fijado y la versión.
- **Corte de bucles**: a la tercera ida y vuelta, la conversación pasa a una persona.

**Por qué.**
- ADSL lo pidió.
- ADR-041 L7 lo permitía, pero la 030 lo quitó.
- Una herramienta es auditable y respeta la lista blanca (garantía 2).

**Descartado.** Un clasificador previo que elige el agente: añade un modelo en cada
mensaje y una regla invisible.

### D37 · Memoria compartida por defecto; «memoria propia» opcional

**Decisión.** La memoria del contacto es del cliente y la comparten sus agentes. Un
agente marcado «memoria propia» lee y escribe solo la suya (garantía 9).

**Por qué.** El cliente final es del negocio: si dijo su alergia a Recepción, Ventas
también debe saberlo. La excepción cubre líneas que no deben cruzarse, como las
clínicas.

### D38 · Activación por partner y migración que no cambia nada

**Decisión.**
- **La activación**: la consola nueva se activa por partner desde el admin. La API
  sirve a las dos consolas mientras haga falta.
- **La migración de datos** corre para todos. Es idempotente, tiene modo ensayo e
  informe de diferencias: compara la batería de cada agente y la audiencia efectiva
  de cada número antes y después.
- **Una diferencia** bloquea la activación de ese partner.
- **«Repartir tu saldo en bolsas»** propone, para cada cliente, lo que le queda este
  mes. Hasta que el partner confirme, sus clientes siguen con el tope de hoy.

**Por qué.** Facelad y Amacrux operan clientes reales (C6). Un corte para todos a la
vez no se puede revertir.

**Descartado.** Una migración en caliente sin modo ensayo.

### D39 · «Próximamente», solo en el catálogo de canales (decisión del owner del 2026-10-24)

**Decisión.** Se sigue la constitución 1.2.0, que viene de la spec 046:
- el catálogo de canales de la consola de partners enseña lo que viene, marcado
  «Próximamente» o «Pendiente», sin poder iniciarse, sin fecha ni enlace;
- la consola lite no tiene excepción;
- las integraciones que el partner no puede usar siguen sin aparecer.

**Por qué.** Lo decidió el owner el 2026-10-24: el partner ve qué canales vienen,
igual que el equipo. El borrador de esta spec decía lo contrario («sin
Próximamente»); se corrige al encontrar la 046.

**Cuidado.** El prototipo enseñaba un canal de Instagram activo y a la vez
«Próximamente». Ningún canal «Próximamente» puede tener filas ni estados.

### D40 · El borrado RGPD del cliente sigue, como excepción escrita

**Decisión.**
- **El cliente** se sigue borrando como hoy: lo hace un owner o un admin, con el
  cliente archivado antes y el nombre tecleado. Responde 409 si es una línea de
  factura o tiene pagos.
- **La excepción** se escribe en ADR-049 y en la enmienda de §IV de la constitución (1.3.0).
- **Los agentes** nunca se borran: se archivan, y sus datos se purgan solo con su cliente.

**Por qué.** Es una obligación legal. «Borrar no existe» sigue siendo la regla para
todo lo demás.

### D41 · Ninguna superficie nueva

**Decisión.** Superficie `0`. La lectura de la web de un negocio ya existía en
Conocimiento. Ahora corre en segundo plano, con las mismas guardas:
- solo direcciones públicas;
- un tamaño máximo;
- `robots.txt`;
- como mucho 25 páginas.

Lo leído es dato, vallado como no confiable (§III). El constructor no navega: pide
páginas desde el servidor.

---

### D42 · La 047 sustituye las iteraciones 2 y 3 de la spec 046 (owner)

**Decisión** (owner, 2026-10-26):
- «Encender tu agente» (5 pasos) y el Companion que propone el alta (iteraciones
  2 y 3 de la 046) no se construyen. Los cubren el alta en tres datos, el
  constructor, el playground sobre el borrador y la página del canal.
- «Activar» pasa a ser por canal: «A todos» exige agente publicado y saldo
  (requisito 32.8). El cliente no se activa, y la T011 de la 046 tampoco se construye.
- Se quedan de la 046:
  - la iteración 1a (el catálogo y el asistente de canales);
  - la iteración 1b (ningún cliente mudo), salvo la T011;
  - la constitución 1.2.0;
  - el modo prueba al conectar;
  - los 6 grupos de plantillas, como grupos de nichos y de plantillas.

**Por qué.** Con dos planes para el mismo alta, uno sobra (constitución, flujo de
trabajo). El modelo de esta spec separa el cliente de sus agentes, y la
activación por cliente no cabe en él.

---

## Parte 7 — Números y límites

| Qué | Valor | De dónde sale |
|---|---|---|
| Ventana de agrupación | 3 s, configurable por Auphere | Mensajes seguidos de WhatsApp; los sistemas del segmento usan de 2 a 5 s |
| Nombre del cliente / nicho / información | 1–60 / 2–80 / ≤ 2.000 caracteres | Prototipo y alta de hoy |
| Lectura de la web | ≤ 25 páginas | Coste (~0,01 $ por web) y tiempo |
| Turnos por día | ≤ 6 | Negocios con turnos partidos y nocturnos |
| Duración de un servicio | 5–480 min | La de Reservas |
| Preguntas del constructor | ≤ 5 | Investigación del 24 de octubre |
| Nombre / descripción / instrucciones del agente | 1–40 / 20–1.024 / ≤ 8.000 caracteres | Prototipo y Copilot Studio |
| Pruebas | 20 (8 del caso + 12 del sector), 3 pasadas | D18 |
| Puerta | Críticas 3/3; regresión ≤ 2 pp | D18 y D23 |
| Deshacer / caducidad de una propuesta | 10 min / 15 min | §IV y el Companion |
| Enlace del dueño | 7 días, de un solo uso | Spec 040 |
| Destinatarios de escalado | ≤ 10 por canal | Negocios con turnos |
| Mensaje de espera | 1 cada 6 h por conversación | La regla de hoy en `budget_gate.py` |
| Toma de control por eco | 2 h sin mensajes del negocio | Coexistencia (D12) |
| Llamadas por turno / escalados | ≤ 12 / ≤ 3 por hora | ReAct ≤ 6 + clasificar + juez + multimedia + escalados |
| Sugerencias | ≥ 5 conversaciones de ≥ 5 contactos | D34 |
| Avisos de la bolsa | 20 % de la base, 7 días, cero | D27 |
| Tope del agente | Avisa al 80 %, corta al 100 % | Spec |
| «Construcción y pruebas» | 50 al mes por defecto | D29 |
| Aviso de cambio de precio | +10 % en el precio estimado | Evitar ruido con céntimos |
| Aviso de retirada | ≥ 30 días | Scaleway da ≥ 3 meses; Bedrock, menos |
| Relleno de las bolsas | Día 1, 00:00 UTC | Los periodos mensuales de la consola son UTC |
