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

### D43 · Los trabajos y la agrupación van por Redis, no por Dramatiq (implementación)

**Decisión** (2026-10-26, al empezar el bloque A): `plan.md` habla de «un actor de
Dramatiq por tipo de trabajo» (T003) y de «un mensaje diferido de Dramatiq» para la
agrupación (T034). **Dramatiq no está en el repo**: el worker son tareas asyncio por
familia (`runner`, `egress`, `scheduler`) sobre Redis Streams, registradas con
`_spawn` en `wk/bootstrap.py`.
- Los trabajos se encolan en el stream `nexus:jobs` con su `tenant_id` y su
  `job_id`. Los consume `jobs-consumer`, de la familia `runner`, que despacha por
  `kind` a un manejador registrado. La fila de `jobs` es la verdad; el stream solo
  avisa.
- La caducidad de un trabajo colgado no necesita cron: un trabajo vivo sin latido
  (`updated_at`) más allá de su plazo se da por `failed` (`timeout`) al leerlo, y
  el consumidor lo marca igual si su manejador no termina a tiempo.
- La agrupación de T034 usa una cola diferida en Redis (un conjunto ordenado por
  vencimiento, deduplicado por conversación), con el candado por conversación de
  la base.

**Por qué.** Meter Dramatiq sería una dependencia nueva con licencia LGPL-3.0, que
§VIII obliga a leer y que nada pide: el mismo ciclo ya existe con los streams del
repo, sus reintentos (`stream-claimer`) y su contrato de nombres por familia.

---

### D44 · Ningún despliegue de hoy tiene la retención cero comprobada (implementación)

**Hecho** (2026-10-27, bloque B): el filtro duro del router exige
`zero_retention` (requisito 41.2; «al catálogo solo entran proveedores con
contrato sin retención ni entrenamiento»). Las ocho filas de `model_profiles` de
hoy (OpenAI y Anthropic directos) nacieron en la 0180 con `zero_retention=false`,
porque nadie lo ha comprobado. Con eso, `chain_for` responde `no_model` a toda
tarea nueva, también con el modelo de reserva, que pasa el mismo filtro.

**Decisión** (sin el owner, se puede reabrir):
- **Los agentes que ya existen no cambian** (D24, Historia 13): siguen fijados en su
  modelo por el camino de hoy, fuera del router nuevo, hasta que su partner elija
  un perfil. Que la pantalla no mienta: la consola no les ofrece «Automático» hasta
  que haya un despliegue que pase el filtro.
- **Ninguna fila se marca con retención cero sin su evidencia.** Hace falta que Luis
  confirme el acuerdo de retención cero con OpenAI y con Anthropic (y su
  `retention_how`), o que entren Bedrock y Scaleway (T142, tras darlos de alta como
  subprocesadores). Es la única forma de que el router nuevo elija.
- **En local**, la semilla puede marcar un despliegue de desarrollo como certificado
  y sin retención, solo en la base de desarrollo, para ver al router decidir
  (`quickstart.md` §1).

**Por qué.** Marcar la retención cero para desbloquear el router sería afirmar un
contrato que no se ha leído (§VIII, §V). Mantener fijados a los agentes de hoy es lo
que ya decía D24 y es lo que exige «lo que ya existe sigue funcionando».

---

### D45 · El perfil de modelo vive en la versión, y «Automático» solo si puede atender (implementación)

**Decisión** (2026-10-27, bloque C, T145; se puede reabrir):
- Hasta que llegue el AgentSpec (bloque D), el perfil va en
  `agent_configs.policies["model_policy"]`, con la forma exacta del `model_policy`
  del AgentSpec. Va con la versión: el borrador, la puerta, deshacer y restaurar le
  valen tal cual, y al pasar al AgentSpec se copia.
- **Una versión sin `model_policy` es un agente de hoy**: fijado en su modelo por el
  camino de hoy. A los agentes migrados no se les escribe `pinned`, porque con D44 el
  filtro duro lo rechazaría y se quedarían sin modelo.
- **Un agente nuevo nace en «Automático» solo si «Automático» puede atenderlo en ese
  cliente**: hace falta un despliegue de reserva que pase el filtro duro del cliente
  para `classify`, `answer` y `tool_turn`. Con D44 no lo hay, así que hoy los agentes
  nuevos nacen como los de hoy. Ampliación de D44 y de D24, pendiente de que Luis la
  confirme.

**Por qué.** Que un agente nuevo naciera en un perfil sin ningún modelo que lo atienda
lo dejaría mudo desde el primer mensaje: la pantalla diría «Automático» y la Bandeja,
«Sin modelo disponible».

---

## Parte 6b — Enmienda del 2026-10-29: lista para staging

La auditoría del constructor del 2026-10-29 (`research/2026-10-29-auditoria-del-constructor/_index.md` en la KB) se hizo leyendo el código de `develop` (`17943701`) contra esta spec y el prototipo. Estas decisiones salen de las respuestas del owner de ese día. Las marcadas «owner» son suyas; las demás, recomendaciones que aceptó y que se pueden reabrir.

---

### D46 · El sector lo identifica un modelo y vive en la ficha (owner)

**Hecho.** `sector_of_niche` buscaba fragmentos de palabra: «Despacho de abogados» caía en clínica porque contiene «spa»; «Psicóloga» y «Veterinaria», en clínica dental; «Clases de yoga online», en tienda; «Gimnasio», «Hotel rural», «Óptica» y «Ferretería», en «otro», que no recibe ninguna prueba del sector. El sector se recalculaba en cada uso.

**Decisión.**
- La ficha guarda `sector`: clave (una de las guías de Auphere, u `otro`), etiqueta, confianza, origen y quién decidió.
- Lo identifica un modelo barato en segundo plano: al alta, al terminar la lectura y al cambiar el nicho o la información. La salida se valida contra la lista cerrada de claves.
- Una persona puede corregirlo; entonces el sistema solo propone.
- Sin modelo, una regla de **palabras enteras** da un sector con confianza baja, que se vuelve a identificar cuando haya modelo.

**Por qué.** El owner pidió que no fuera genérico. Un clasificador con la lista cerrada y la etiqueta libre entiende «barbería de barrio», «peluquería masculina» o «despacho laboralista» sin mantener listas de palabras, y deja trazado de dónde salió.

**Descartado.** Ampliar la regla de palabras: falla con cada nicho nuevo y con los falsos amigos («spa» en «despacho»).

---

### D47 · Especializar es guía del sector × papel × ficha

**Hecho.** El constructor recibía cuatro patrones de una línea y no veía las 13 plantillas verticales (unas 2.400 líneas de oficio), aunque la investigación del 24 de octubre decía usarlas como ejemplo. «Desde una plantilla» creaba un agente en modo «instrucciones», sin pruebas.

**Decisión.**
- Cada plantilla se convierte en **guía del sector**: qué preguntar, procedimientos, riesgos, escalados, herramientas típicas y pruebas. El constructor la recibe como ejemplo de oficio, junto con el patrón del papel y la ficha vallada.
- La identidad sale de la ficha y la descripción. Dos negocios del mismo sector comparten guía, no agente.
- Sin guía, el constructor genera una **para ese cliente** (RLS), con sus 12 pruebas, marcadas «Generada». La entrada es la etiqueta del sector y la guía genérica de Auphere, nunca datos de otro cliente (garantía 5).
- Auphere ve en el panel de operador los sectores sin guía que más se repiten y puede convertir una generada, revisada, en guía propia.

**Por qué.** Es lo que hacen los constructores medidos el 24 de octubre (Sierra y Decagon parten de procedimientos del sector) y es lo que ya teníamos escrito en las plantillas. Generar por cliente, y no compartida, mantiene el aislamiento sin perder la cobertura de los sectores nuevos.

**Descartado.** Una guía generada compartida entre clientes: sale de lo que escribió un partner y llegaría a otros.

---

### D48 · Sin relectura periódica (owner)

**Decisión.** Se retira el cron semanal de relectura. Se relee cuando cambia la web o una red del cliente, cuando se añade una fuente o cuando una persona pulsa «Volver a leer». Enmienda el requisito 12.3.

**Por qué.** El owner no quiere relecturas que nadie ha pedido. La relectura semanal, además, pisaba lo no confirmado sin pasar por propuestas.

---

### D49 · Leer mejor sin navegador: datos estructurados, sitemap y en paralelo

**Hecho.** El lector tiraba todas las etiquetas `<script>`, también el JSON-LD de schema.org, que es donde muchas webs de pymes (Wix, Squarespace, WordPress con Yoast) publican horario, dirección y teléfono. Recorría de una en una, sin `sitemap.xml`, y solo leía redes si no había web.

**Decisión.**
- Leer el JSON-LD y los microdatos sin modelo, y darles la procedencia más fiable.
- Usar el `sitemap.xml` para priorizar páginas, y leer varias a la vez con un máximo por sitio (4), sin pasar de 25 páginas ni de 3 minutos.
- Leer también las redes permitidas cuando hay web. Las que lo prohíben (Instagram, Facebook, LinkedIn y X, comprobado el 2026-10-29) salen como «no deja leer», no como fallo.
- Reintentar una vez la extracción que no valida.

**Por qué.** Es lo más barato y fiable: no cuesta modelo y no añade dependencias.

---

### D50 · El navegador, solo de respaldo y fuera del worker

**Decisión.** Cuando una página trae poco texto, se pide a un servicio de renderizado aparte (Playwright con Chromium), si está configurado. Aplica las mismas guardas: direcciones públicas (también en cada redirección y en cada petición que haga la página), `robots.txt`, tamaño y tiempo. No corre en la imagen del worker.

**Por qué.** El Dockerfile del worker cifra la imagen en unos 400 MB y en 1,2 GB con Playwright. Un servicio aparte se despliega cuando haga falta y no penaliza cada arranque del worker. Licencias: Playwright, Apache-2.0; Chromium, BSD-3-Clause.

**Descartado.** Meter Playwright en el worker (tamaño) o un servicio de terceros (los datos del cliente saldrían a otro procesador sin DPA).

---

### D51 · El constructor del cliente se lanza solo al terminar la lectura (owner)

**Hecho.** `client_profile.py` y su endpoint existían, pero `ClientBuilderPanel` no estaba montado y nada lo lanzaba. Las políticas y las preguntas frecuentes de la ficha no tenían pantalla, aunque entraban en el prompt de todos los agentes.

**Decisión.**
- Se lanza al terminar la lectura de las fuentes y al cambiar el sector, en segundo plano, idempotente por la huella de la ficha.
- Reintenta como mucho 3 veces con espera creciente.
- Sus propuestas se deciden en Negocio, en las secciones nuevas «Políticas» y «Preguntas frecuentes»; los agentes sugeridos, en Agentes, sin crearse solos.

---

### D52 · Pruebas de varios turnos con cliente simulado (owner)

**Hecho.** Cada pasada era un solo `run_turn` con el primer mensaje; la persona y el plan no se usaban. Una prueba de «reservar» solo pasaba si el agente reservaba sin confirmar, que es justo lo que no queremos.

**Decisión.**
- Un cliente simulado, con su persona y su plan, conversa con el agente hasta cumplir el plan, despedirse, pasar a una persona o llegar a 8 turnos.
- Se comprueba el estado final en la agenda simulada de Reservas, el escalado y el enlace de pago.
- El cliente simulado y el juez van con un modelo distinto del que responde; el juez, configurable, con aviso si es de la misma familia (D18).
- Las tres pasadas siguen siendo independientes y se guarda la conversación de cada una.

**Coste.** Una prueba pasa de 1 a unas 4 llamadas del agente de media, más el cliente simulado y el juez. Se estima antes de ejecutar la suite y se mide en «Construcción y pruebas».

---

### D53 · Herramientas pendientes de conexión

**Hecho.** El constructor quitaba del borrador las herramientas de un conector no conectado, y activar el conector solo filtraba la lista del agente. Conectar no daba nada: el agente seguía sin poder reservar.

**Decisión.** El AgentSpec guarda las herramientas que pide una habilidad aunque falte la conexión, marcadas «pendientes de conexión». El runtime sigue viendo la intersección de la lista con las activaciones del agente, así que no ve nada hasta conectar y activar. «Conectar {X}» conecta en el sitio y deja las pruebas afectadas desactualizadas. Enmienda el requisito 15.4.

**Por qué.** La garantía 2 la da la intersección, no quitar herramientas del borrador. Así conectar basta, y nadie tiene que rehacer el agente.

---

### D54 · Canal, Rendimiento y Conectores como el prototipo (owner: H5, H9 y H10; H8 no)

**Decisión.** Se alinean con `evidence/prototipo/agente.md` §H5, §H9 y §H10:
- **H5.** El canal se configura dentro del agente (pestaña Canales con `?canal=`), con dos modos; las excepciones, solo con «A todos»; «Mensaje de espera» e «Historial», en «Más ajustes».
- **H9.** Rendimiento solo con versión guardada, resumen de 30 días y sugerencias arriba, y gráfica y tabla debajo. «Listo · sin canal» abre en Canales.
- **H10.** Conectores en una tarjeta con filas, filtro segmentado con recuentos y el permiso en «Ajustes».

H8 (la cabecera y «Pausar» a la vista) queda fuera por decisión del owner.

---

### D55 · Los modelos los gestiona Auphere hasta tener su panel (owner)

**Hecho.** «Calidad» ofrecía los cuatro perfiles «sin precio estimado», y ninguno podía atender (D44); «Fijar un modelo» salía vacío.

**Decisión.** La consola no enseña «Calidad» ni «Fijar un modelo» hasta que llegue la gestión de modelos en el panel de operador (otra spec). Agente › Avanzado dice que el modelo lo gestiona Auphere. La API rechaza un cambio de política desde la consola con un código propio. Los modelos del constructor, la lectura, el sector, el cliente simulado y el juez salen de la configuración de la plataforma.

**Por qué.** Una pantalla que ofrece lo que no puede atender rompe §V. El owner prefiere controlar la selección, los precios y el catálogo desde el panel de operador.

---

### D56 · Lo que el prototipo no decide en H5, H9, H10 y H11 (consola, 2026-10-29)

**Decisión.** Al alinear la consola con `evidence/prototipo/agente.md` (T211–T214):
- **Rendimiento (H9).** El resumen de arriba es siempre de 30 días; la píldora 7 · 30 · 90 se queda, pero en la gráfica de debajo (D5), y solo cambia la gráfica. «Consumido de la bolsa» es el gasto de 30 días de la API (a precio, en USD) y el tope es el mensual del agente, en la moneda de su bolsa. «Sugerencias de esta semana» lista las sugerencias y las correcciones del negocio; «Aceptar» y «Descartar» viven dentro de «Ver».
- **Conectores (H10).** «Conectados» cuenta lo que usa este agente. Un conector que el cliente ya tiene y este agente no usa lleva «Conectar», que lo activa con su permiso (35.4). La página de cada conexión se abre desde «Ajustes» (y, si la conexión está rota o pendiente, desde la fila).
- **«Conectar {X}» en el sitio (H11, 62.3).** Abre el diálogo de la pestaña Conectores sin cambiarla; si el conector no está en el catálogo del agente, va a la pestaña. Al terminar, la pantalla vuelve a leer el borrador y sus pruebas (la API las marca desactualizadas, T207); con OAuth, el aviso de «Ya la terminé» sale donde está la persona.
- **El canal (H5).** La configuración vive en `?canal=` dentro de la pantalla del agente; la ruta vieja redirige (308). Guardar no vuelve a la lista: se queda para que «Deshacer» siga a la vista (32.7); «Decidir luego» sí vuelve. Quitar a la última persona del escalado se puede, como hasta ahora (la conversación sigue llegando a la Bandeja). El método («Coexistencia» o «Cloud API») sale en la cabecera cuando la API lo mande en `ChannelPage.method`; hoy no lo manda.

**Por qué.** Son los huecos que el prototipo deja abiertos; se resuelven sin quitar nada que ya funcionaba (deshacer, el periodo, escalar sin nadie) y sin inventar API.

---

### D57 · Lo que el contrato del 2026-10-29 no fija para la consola (T209, T210 y T215, consola, 2026-10-29)

**Decisión.** Al construir contra `contracts/console-api.md` §10 antes de que la API lo implemente:
- **Dónde llegan las redes de la lectura (59.4).** `GET …/business/read` ya tenía `networks: Network[]` (las redes por leer). La consola acepta `networks` con objetos `{network, status, reason?}` ahí o en el `result` del trabajo `client_read`, y `structured` en los dos sitios. De una lectura de antes, un `blocked` en una red social se dice como «no deja leer perfiles sin cuenta» y no como fallo (`client-read-model.ts`, `networkLines`). La frase la pone la consola; `reason` solo se usa en una red que falló, con el vocabulario de `ReadFailure`.
- **La tarjeta de lectura se queda al terminar (59.7).** El prototipo la quitaba al acabar; el requisito pide qué se leyó y qué falta revisar, así que se queda con el título «Lo que leímos». «Por revisar» es lo aplicado «revísalo» más lo propuesto (`applied + suggested`). Sin trabajo de lectura, no hay tarjeta.
- **La conversación de una prueba (61.6).** El contrato dice «cada intento», pero `TestOut` no tiene intentos. La consola lee `transcript`/`stop` de la prueba (la pasada que se enseña) y, si llegan pasadas en `attempts[]`, la primera que falló. `actions` son frases ya en palabras del negocio y se pintan como «Lo que habría hecho: …». Un `stop` que no conoce no se enseña.
- **«Generada» en la guía (58.4).** La guía no tiene pantalla propia: «Generada» sale en el sector de Datos básicos (`has_guide: false`), en cada prueba con `origin: "generated"` y como una línea bajo el grupo «Del sector».
- **El sector.** Sin el campo en la respuesta (la API de hoy), Datos básicos no habla del sector; `null` es «Identificando el sector…». La propuesta del sistema (`/business/sector`) solo se acepta o se descarta: corregirla a mano es «Editar». Sin `GET /console/sectors`, el selector ofrece el actual y «Otro».
- **Lo sugerido de Políticas y Preguntas frecuentes.** Va en su sección con su procedencia, sin nombrar al constructor («Propuesto a partir de la ficha»). Una pregunta guardada con `suggested: true` sale también en «Por confirmar» (aceptar es `suggested: false`; descartar, archivarla), con la procedencia genérica «Sugerido» porque la fila no la trae. `decide` devuelve solo la revisión: aceptar o editar vuelve a leer la sección; descartar solo la quita.
- **Agentes sugeridos.** Si `GET …/suggested-agents` falla, la pestaña se pinta sin ellos y sin aviso (todavía no son del cliente). «Descartar» pide `agents:write`, como crear. El papel se dice «Para recepción/ventas/cobros/soporte».

**Por qué.** Son los huecos del contrato congelado; se resuelven aceptando las dos formas razonables en vez de adivinar una, y sin enseñar nada que la API aún no manda.

---

### D58 · Dónde se escribe el sector y quién manda (API, 2026-10-29)

**Decisión.**
- Lo que identifica el sistema se guarda **directamente** en `business_profiles.sector`, sin `write_section`: el sector no entra en el prompt de ningún agente, así que no mueve la revisión de Datos básicos (no provoca un `412` a quien edita a la vez), no recompila y no deja pruebas desactualizadas. Lo que fija una persona sí pasa por `update_basics`, con historial, procedencia y deshacer.
- Un sector fijado por una persona solo recibe propuestas: una sugerencia de la ficha con el puntero `/business/sector`, `source = "builder"` (la consola la dice «Propuesto a partir de la ficha»). La misma clave pendiente no se repite; una pendiente distinta queda sustituida (`discarded`, `decided_by = "system:superseded"`). Lo de respaldo nunca se propone contra una persona.
- Aceptar la propuesta deja `decided_by = "person"` y conserva su origen y su confianza; editarla a mano es de la persona, con confianza 1.
- Lo de respaldo no pisa a lo que dijo el modelo.
- Sin sector todavía, quien lo necesita para trabajar (las pruebas del sector, el constructor del cliente) lo deja guardado **una vez** con la regla de respaldo (`sector.ensure_stored`): nadie espera a la identificación ni vuelve a clasificar el nicho en cada uso (57.6).
- **La lectura pública** del sector desde el servidor es `services/business/sector.stored(session)` (el objeto) o `sector.sector_key(session)` (la clave), con el cliente puesto. La usa, por ejemplo, el paso automático a Reservas de la spec 048 (su decisión 13) para saber si un negocio es un restaurante.

**Por qué.** El requisito 57.3 pide que el sistema no cambie lo de una persona; el resto es el camino más barato que no ensucia la concurrencia por sección ni la suite.

---

### D59 · Cuándo se identifica el sector (API, 2026-10-29)

**Decisión.** El trabajo `sector_identify` (un tipo nuevo de `jobs`, migración 0206) se encola:
- al alta, en la misma transacción y avisando al worker al confirmar: el alta no espera;
- al terminar la lectura de la web y las redes (no la de cada documento suelto), marcado `after_read`, para lanzar después el constructor del cliente;
- cuando una persona cambia el nicho o la información;
- al abrir Datos básicos sin sector, o con el de respaldo, si no hay uno vivo ni se pidió en la última hora. Así los clientes de antes de la enmienda y los identificados sin modelo acaban con el del modelo («cuando lo haya», 57.4), sin bucles cuando no hay modelo.

Con uno vivo no se encola otro, salvo el de después de una lectura. El modelo es uno barato (`classify`, `NEXUS_LLM_SECTOR_MODEL`); sin modelo, o con una respuesta que no está en la lista cerrada, vale la regla de palabras enteras con confianza 0,3. La etiqueta se limpia (sin marcas, saltos ni símbolos) y se corta a 40.

---

### D60 · El constructor del cliente: huella, lanzamiento y reintentos (API, 2026-10-29)

**Decisión.**
- La huella de la ficha es el `state_hash` de su ClientSpec (lo escribible, con el sector). No se genera si hay un `client_builder` en cola, en marcha o hecho con esa huella; uno fallido no cuenta.
- Se lanza: al terminar `sector_identify` marcado `after_read`; cuando el sistema cambia el sector y no hay una lectura viva (que lo lanzará al terminar: así un alta con web no genera dos veces); y cuando una persona cambia el sector. Sin saldo en «Construcción y pruebas» del partner (46.5), no se lanza.
- «Reintentar como mucho 3 veces» son tres reintentos tras el primer intento, con esperas de 2, 4 y 8 s, **dentro del mismo trabajo** (el consumidor no reintenta a ciegas, D43). Después, `failed` con `builder_unavailable`. El plazo del trabajo pasa a 360 s.

---

### D61 · Lo descartado no vuelve, y los agentes sugeridos (API, 2026-10-29)

**Decisión.**
- Una política o una pregunta frecuente que una persona descartó (el mismo valor) no se vuelve a proponer nunca, ni para otra ficha. Un agente sugerido descartado (por su nombre normalizado) tampoco. Es más estricto que el requisito 60.5 («para la misma ficha») y lo cumple.
- Los agentes sugeridos viven en `suggested_agents` (tabla de cliente): uno pendiente por nombre; una pasada nueva actualiza el que repite y deja `superseded` los que ya no propone. Uno cuyo nombre ya tiene un agente del cliente no se enseña. `role` es `reception | sales | billing | support` o `null` si el modelo dice otra cosa.
- «Descartar» deja auditoría (`suggested_agent.dismissed`, categoría Agentes) y pide `agents:write`; listar pide `agents:read`. Descartar dos veces no falla; un id de otro cliente es un `404`.

---

### D62 · Herramientas pendientes en el turno y pruebas al activar (API, 2026-10-29)

**Decisión.**
- `sanitize` deja de quitar la herramienta sin conexión **si su integración es un conector del catálogo** (con activación por agente): la guarda con su petición en `connection_requests`, y el validador la acepta. Las que dependen de otra cosa sin activación que las retenga en el turno (`catalog.*`, el catálogo de Meta del canal) siguen como antes: fuera del borrador, con su petición, y `tool_not_connected` si una persona las añade. Lo desconocido, lo interno, lo retirado y lo no permitido siguen siendo problemas.
- En el turno (`activations.tool_policy`), con la consola nueva, **también** se bloquean las herramientas de un conector que el cliente aún no conectó. Antes la unión interna con `tenant_connectors` las dejaba fuera de la regla, y una herramienta pendiente habría llegado al modelo. Fuera de la consola nueva, nada cambia.
- Activar una conexión en un agente (o cambiar su permiso o sus ajustes) deja **todas** sus pruebas desactualizadas: cambió lo que el agente puede hacer, como un cambio del borrador (21.7).

---

### D63 · Releer cuando cambia (API, 2026-10-29)

**Decisión.**
- Una web distinta en Datos básicos o una red añadida en Redes, escritas por una persona, encolan la lectura de la web y las redes (una viva a la vez). Quitar una red no lee nada. Lo que escribe el lector (`system`) o el constructor no encola nada.
- Añadir una fuente ya encolaba su lectura (12.1); sigue igual. «Volver a leer» sigue.
- `source_reread_cron` nunca estuvo en el contrato de nombres de `bootstrap.py` (no corría): se borra con `reread_due`, y `test_bootstrap_split.py` comprueba que no vuelve.

---

### D64 · Modelos: el `409` y la tabla de la plataforma (API, 2026-10-29)

**Decisión.**
- `PATCH …/draft` con un AgentSpec que trae otra política de modelo que la del agente (o, sin AgentSpec todavía, que la que le daría la plataforma) responde `409 model_policy_managed` y no escribe nada; lo demás del borrador se sigue editando. `POST …/quality/check` responde siempre `409 model_policy_managed`. El constructor, «Desde una plantilla» y el panel de operador ponen la política como hasta ahora.
- Los modelos de los trabajos de la plataforma salen de una sola tabla del worker (`nexus_worker/platform_models.py`): `build`, `read_source`, `sector`, `customer_sim` y `judge`, cada uno con su variable `NEXUS_LLM_*_MODEL` y, sin ella, el de su familia.
- `ChannelPage.method`: `coexistence` si el canal está en coexistencia (la columna o el modo del alta), `cloud_api` si se dio de alta así, y `null` si no se sabe (la consola no lo inventa).

---

### D65 · El esquema que deja la 0206 para el paso 4 (API, 2026-10-29)

**Decisión.**
- `generated_guides`: la guía generada para un cliente (`guide` JSONB, `tests` con 12 como mucho), `status` `generated | reviewed | promoted | archived`, una viva por etiqueta normalizada (`label_key`) y cliente, `promoted_to` para «Convertir en guía de Auphere» (58.5). La escribe la T201.
- `agent_tests.generated_guide_id` (FK compuesta): una prueba del sector salida de una guía generada lleva `origin: "generated"` en la consola.
- `agent_test_results.stop` (`plan_done | goodbye | handoff | turn_limit`): la conversación ya vivía en `transcript` (0187). Los escribe la T206.

---

### D66 · «Convertir en guía de Auphere»: tabla de plataforma y guía por etiqueta (API, 2026-10-30)

**Hecho.** La 0206 dejó `generated_guides.promoted_to` (40) pero ningún sitio donde viva una guía de Auphere convertida: las seis de las plantillas son código, y una guía del cliente no se puede leer desde otro cliente (garantía 1).

**Decisión.**
- **Migración 0207**: `sector_guides`, de plataforma, sin `tenant_id` ni nada que apunte al cliente del que salió. Sus 12 pruebas van a `sector_test_catalog` (versión 1) con la misma clave. `nexus_app` solo la lee; la escribe el panel.
- **La lista cerrada de claves no crece** (57.7): el sector guardado sigue siendo `otro`. La guía se resuelve por la **etiqueta normalizada** (`label_key`): sector de la lista → guía de su plantilla; `otro` con guía convertida para su etiqueta → esa; si no, la generada del cliente; si no, se genera (`guides/resolve.py`). La consola dice «Con guía» también para una etiqueta convertida (`sector.sector_out_for`).
- **Revisar y convertir** (`contracts/admin-sector-guides.md`): revisar lo hace una persona de Auphere (`X-Operator-Id`), puede corregir la guía y las pruebas, y no se guarda si quedan **datos del cliente**: su nombre, su web, sus sedes, direcciones, teléfonos, personas del equipo, sus usuarios de redes, y cualquier URL, correo o teléfono de nadie (`guides/client_data.py`). Convertir exige `reviewed`, lo vuelve a comprobar y escribe, en una transacción, la guía de plataforma, sus pruebas y la del cliente como `promoted`, con dos filas de auditoría (la del cliente y una de plataforma sin nada del cliente).
- **Los sectores sin guía más repetidos** se calculan cliente a cliente con su contexto declarado (RLS FORCE), no con una consulta que cruce clientes.

**Descartado.** Hacer dinámica la lista de claves (`SECTOR_KEYS`): obliga a tocar la validación del sector, el clasificador y la columna de la ficha, y abre la lista cerrada que valida lo que dice el modelo.

---

### D67 · La agenda solo con Reservas encendido; los papeles son ejemplos (API, 2026-10-30)

**Hecho.** Con Reservas apagado, `sanitize` y el validador aceptaban `reservas.*`: el borrador las llevaba y en el turno respondían «Reservas no está activo»; las pruebas pasaban en verde contra la agenda simulada. Y el constructor solo veía nombres de herramientas, con las de Composio (mayúsculas, sin punto) capaces de tumbar el borrador entero.

**Decisión** (Luis, 2026-10-30: no hay papeles fijos, el agente solo usa herramientas que existen):
- **Determinista, en `validator.load_context`**: `reservas.*` necesitan el módulo Reservas (`capability_names.requires_module`); conectadas solo con `ClientAccess.reservas_on` y su modo elegido. Apagado, cuentan como sin conectar y sin activación: `sanitize` las quita (`tool_not_connected`), la puerta las rechaza y el constructor las ve «SIN ACTIVAR». El registro simulado (playground y pruebas) responde lo mismo que el servidor de Reservas. La evaluación del constructor supone Reservas encendido.
- **Los patrones de papel** (Recepción, Ventas, Cobros, Soporte) son ejemplos combinables: se pasan todos los que encajan con la descripción, o todos si ninguno; no deciden herramientas ni pruebas; no nombran acciones sin herramienta (ningún enlace de pago, tampoco en las guías ni en el prompt).
- **El catálogo que ve el constructor** lleva lo que hace cada herramienta (`capability_names`) y excluye los nombres que el AgentSpec no admite (`TOOL_NAME_PATTERN`).
- Sustituye una primera versión de este paso que filtraba la agenda por palabras de la descripción: dejaba fuera «clases», «sesiones» o «visitas».

**Fuera de este paso** (lo prepara la enmienda siguiente): decir con honestidad lo que falta, `PUT /tools` sin validador, la política de herramientas que falla abierta, las pruebas del sector impuestas a cualquier agente y el mínimo de pruebas de la puerta. `/console/clients` con `seed_template` y `…/agent/from-seed` (de la consola de antes) siguen montando la plantilla en modo «instrucciones».

---

### D68 · La guía generada y «Desde una plantilla» (API, 2026-10-30)

**Decisión.**
- La genera el trabajo `agent_draft` **antes** del borrador, con el modelo `build` y medida en «Construcción y pruebas»: su entrada es la etiqueta (vallada) y la guía genérica de Auphere, nada más (`guides/generated.generation_messages`). La salida se valida (forma cerrada, 12 pruebas, herramientas solo de las que conocen las guías de Auphere); lo que no vale se reintenta una vez con el error, y si tampoco, o sin modelo, se guarda la guía genérica con sus 12 pruebas: sigue saliendo solo de la etiqueta y la genérica, sigue siendo «Generada» y Auphere la revisa antes de convertirla.
- Una viva por etiqueta y cliente: el segundo borrador la reutiliza. Sus pruebas entran como pruebas del sector con `generated_guide_id` y la referencia `generated:<id>#<clave>`; la consola las sirve con `origin: "generated"`.
- **«Desde una plantilla»** pasa por `write_new_agent` sin modelo: el borrador determinista con la guía del sector de la plantilla y sus herramientas (filtradas por lo que el cliente tiene), las pruebas del caso y las del sector del cliente. Si el cliente es de «otro» sin guía, se guarda la genérica en ese momento.

---

### D69 · La lectura: estructurados, sitemap, redes y reintento (API, 2026-10-30)

**Decisión.**
- **Estructurados**: el JSON-LD y los microdatos se convierten a la forma que pide el modelo y pasan por la misma validación (`parse_extraction`). Al mezclar, mandan (sus sedes, horario, servicios y preguntas van primero; del modelo solo entra lo que no repite un nombre). La procedencia guardada sigue siendo `web` —añadir otra exige migrar el CHECK de `business_field_provenance`—; el resultado dice `structured: true`.
- **Sitemap**: el de `robots.txt` o `/sitemap.xml`, un nivel de índice; 1 MB, 3 sitemaps, 200 direcciones; se leen solo las `<loc>` con una expresión regular (sin XML ni entidades). Nunca hace fallar la lectura.
- **Concurrencia**: lotes de 4 con un semáforo de 4, dentro de 25 páginas, 40 intentos y 3 minutos.
- **Redes**: también con web. Instagram, Facebook, LinkedIn y X no dejan leer perfiles sin cuenta (D49): no se piden y van como `blocked_by_network`; una red cuyo `robots.txt` lo prohíbe, igual. Si solo había redes así, la lectura termina sin nada que proponer, no fallida. `sources` conserva su forma de siempre para la consola de antes; lo nuevo va en `networks`.
- **Reintento**: lo que no es un objeto JSON se reintenta una vez con el error. Si tampoco y no hay estructurados, `extract_failed` («Sin datos útiles», el vocabulario cerrado de la consola); con estructurados, se aplican esos.
- **Navegador**: solo con menos de 200 caracteres y sin estructurados, configurado, y como mucho 5 páginas por lectura.

---

### D70 · Las pruebas de varios turnos (worker, 2026-10-30)

**Decisión.**
- El cliente simulado llama con el rol `customer_sim` (tarea `answer`, la de la taxonomía v1: no hay otra que encaje sin versión nueva) y se mide en la partida de la pasada. Su persona, su plan y la conversación van vallados; su respuesta es `{message, status}` con `status` de una lista cerrada; texto suelto es el mensaje, nada es una despedida.
- **Ocho turnos del cliente**: el primer mensaje cuenta. Tras la respuesta del agente al octavo, `turn_limit` y la pasada falla con ese motivo aunque el estado se cumpla. Un paso a una persona para la conversación sin preguntar al cliente.
- **Estado final**: `booking.items` (servicio, día y hora en la zona del negocio), `escalation` (`to: "team"`: las pruebas no tienen destinatarios; el motivo es el que dio el agente) y `payment.requested`.
- **Modelos** (61.5): el cliente cambia al del juez o al de clasificar si coincide con el que respondió; un juez que es el modelo que respondió no cuenta en esa pasada; si es de la misma familia se dice en `summary.warnings` y en el log `tests.judge_warning`. Es el aviso al operador mientras no haya gestión de modelos en el panel (64.4): `router_anomalies` no tiene ese tipo y añadirlo pide migración.
- Sin cliente simulado (en local, en memoria) una pasada es un turno, como antes.

---

### D71 · Estimar antes de correr, y la evaluación con guías (API, 2026-10-30)

**Decisión.**
- `POST …/test-runs` con `dry_run: true` responde `200` con `{tests, estimate: Money | null, calls, unknown_prices}` y no encola nada. De media 4 turnos del agente, 4 mensajes del cliente simulado y 1 del juez por pasada, 3 pasadas, con un tamaño nominal por llamada y el precio vigente del catálogo, por 2,2 como «Construcción y pruebas». Un precio desconocido no es cero: `estimate: null`.
- **Banco v2** (`eval_bank_v2.json`, 120): las 100 de antes con su negocio (nombre, servicios y horario) y 20 de sectores sin guía. La evaluación da a cada borrador su guía (la de un sin guía, generada con su etiqueta), mide sus pruebas del sector con `battery(draft, tests)` y lo separa en `by_guide`. El panel pasa las pruebas vigentes del catálogo; todavía no corre la batería (las pasadas necesitan un cliente y su agenda): `sector_pass_unedited_pct` queda vacío desde el panel hasta que se cablee.

---

### D72 · Qué tenemos: disponible, conector ofrecido y capacidad que falta (API, 2026-10-30)

**Hecho.** El constructor convertía cualquier integración que nombrara el modelo en
«Conectar {X}», también Reservas (un módulo) y el catálogo de Meta (se enlaza en
Canales). Y un borrador de antes de la enmienda puede llevar todavía una de esas
integraciones en una habilidad.

**Decisión.**
- **Disponible** (`Context.usable`, 65.2). Una herramienta está disponible si:
  - existe y se ofrece;
  - no está retirada;
  - el AgentSpec admite su nombre;
  - su conector está conectado o tiene activación, y su módulo está encendido.

  **Conector ofrecido** (`offered_connectors`): una integración con activación y al
  menos una herramienta disponible, derivada del catálogo y sin columna nueva.
  Composio no lo es para un AgentSpec: sus nombres no caben (65.13), así que
  conectarlo no daría nada.
- Una **habilidad** puede apoyarse en un conector ofrecido o en algo que el cliente
  ya tiene y no se conecta (Reservas encendido). Una **petición de conexión**, solo
  en un conector ofrecido.
- Lo demás sale como capacidad que falta, con una sola forma
  (`agent_spec/missing.py`, contrato §11). Lo que dejó fuera el constructor se
  guarda en `policies["builder"].missing_capabilities` de la versión: no hace falta
  columna, y `policies` ya es una bolsa de claves (`console`, `model_policy`…). Las
  promesas se calculan en cada lectura, para que quitarlas las borre.
- **Borradores de antes** (lo pidió la consola, T228). La consola nueva no edita
  habilidades ni peticiones de conexión. Por eso la API las quita en cada lectura
  (`current_spec`, `GET …/draft`, `target_spec` de correcciones y sugerencias, la
  puerta) y en cada escritura (`PATCH …/draft`, `write_spec`, que las anota).
  Nunca rechaza un cambio por ellas. `integration_unknown` queda como código del
  validador y como `reason`; ninguna ruta responde un error con él.

**Descartado.** Una lista escrita de «conectores ofrecidos»: se desincronizaría
del catálogo, que es la fuente.

---

### D73 · Las promesas, por acción (API, 2026-10-30)

**Decisión.**
- `capability_names.TOOL_ACTIONS` dice qué acción hace cada herramienta, leído de
  su descripción. Hay diez acciones: `book`, `modify_booking`, `charge`, `collect`,
  `invoice`, `order`, `modify_order`, `send_media`, `remind` y `catalog`. Una
  herramienta que no está ahí no cumple ninguna promesa. `compiler.PROMISES`
  empareja cada promesa con las acciones que la cumplen. «Cobrar» lo cumple
  cobrar (`charge`) o llevar los cobros (`collect`, la cobranza de `billing.*`).
  «Cobrar con tarjeta o con enlace», solo `charge`, que hoy solo hace
  `woocommerce.build_checkout_link`. Facturar no lo hace nada que el AgentSpec
  admita.
- No es promesa:
  - lo negado («no cobramos»);
  - lo que el cliente pide («si quieren reservar…», «cuando pida cambiar la
    cita…»);
  - un propósito («para reservar, pasa al equipo»);
  - un sustantivo con determinante, en las que también son nombre («su reserva»,
    «el cobro»).
- **Gravedad**:
  - **bloquea** en un agente estructurado, y en la puerta va en `overridable`
    (lo salta un owner o un admin con motivo, como todo bloqueante de la revisión);
  - **avisa** en uno de antes («instructions»): su prompt es el de siempre, byte a
    byte, y bloquear en la API de partners (que publica plantillas al aprovisionar)
    rompería lo que existe (historia 13).

  Su arreglo es editar el texto (`fix: edit` con puntero), no Conectores.
- `sanitize` quita los procedimientos y las reglas que prometen algo sin
  herramienta y los anota (65.4). Deja las secciones de instrucciones y la
  descripción, que es de la persona: su promesa se lista y bloquea hasta que se
  edita.

---

### D74 · Lo que necesita cada prueba del sector (API, 2026-10-30)

**Decisión.**
- `SectorTest.needs` es una lista de acciones de D73, opcional.
  - La migración **0208** la escribe en la versión 1 sembrada por la 0188 sin
    cambiarle el número: es un dato de cuándo aplica la prueba, no de lo que
    comprueba. Las de pedir cita (barbería `book` y `closed_day`, clínica `book`,
    restaurante `book_table`) necesitan `book`; las demás, nada. Una versión
    publicada desde el panel no se toca.
  - Sin `needs` (una guía generada por un modelo), se deduce del estado esperado:
    `booking` → `book`, `payment` → `charge`, `order` → `order`.
- `add_sector_tests(tools=…)` marca «No aplica» al añadir, con la razón sin prefijo
  («Este agente no tiene herramienta para reservar citas.»); la consola pone «No
  aplica:». No se reevalúa si el agente gana la herramienta después: una persona la
  reactiva con `PATCH …/tests/{id}`, como hoy.
- Las pruebas con alternativa en el criterio («o pasa al equipo») no necesitan
  nada: aplican a cualquier agente.

---

### D75 · La puerta sin pruebas y las rutas que esquivaban el validador (API, 2026-10-30)

**Decisión.**
- **Sin pruebas aplicables** (65.9): un agente estructurado no se publica. Va en
  `gate.hard` (`no_applicable_tests`) y nadie lo salta, porque el requisito dice
  «NO DEBE publicar».
- **`PUT /console/clients/{ref}/tools`** y **`PATCH …/draft` con `tools`** dan
  `409 structured_agent` a un agente cuya versión tiene un AgentSpec
  `structured`. Sus herramientas solo cambian con `spec` y el validador.
- **Rutas de plantillas de la consola de antes** (`POST /console/clients` con
  `seed_template`, `…/agent/from-seed`, `POST …/agents` con `seed_template`). Un
  grep en `apps/console` muestra que solo las llaman pantallas de la consola v1 (el
  asistente de alta, el diálogo de nuevo agente del selector), que la v2 no monta;
  y desde la 0204 todos los partners están en la v2.
  - Se **cierran** para un partner con la consola nueva: `410` (`422` en el alta,
    sin crear nada), código `seed_template_retired`.
  - No se pasan por `draft_from_template` porque `from-seed` siembra una versión en
    un agente que ya existe y lleva marcadores, y `draft_from_template` crea un
    agente nuevo.
  - Para un partner de la v1 (solo en pruebas) siguen como estaban. Se borran con
    la consola de antes.

---

### D76 · La política de herramientas que no se lee cierra (worker, 2026-10-30)

**Decisión.** Si `_load_tool_policy` no puede leer la política, devuelve
`ToolPolicy(closed=True)`. Entonces el turno ofrece solo las herramientas de los
servidores de la casa: `activations.NATIVE_TOOLKITS`, una **lista de permitidos**.
Un servidor nuevo cuenta como de conector hasta que se añade, así que nunca falla
abierto. Fuera queda también lo que no tiene servidor en el nombre (WooCommerce de
antes) y lo de Composio (en mayúsculas).

`test_44` barre el catálogo: ninguna herramienta con `connector_id` pasa una
política cerrada.

**Descartado.** Leer en ese momento las herramientas de conector del catálogo: si
la base no responde para la política, tampoco para eso.

---

### D77 · Ficha, instrucciones, copiloto y sugerencias (API, 2026-10-30)

**Decisión.**
- **65.12**:
  - una ficha que no carga es `FactsUnavailable` (`facts_unavailable`): el trabajo
    falla con ese código y «Desde una plantilla» responde 503;
  - una ficha **incompleta** se sigue leyendo como esté;
  - sin instrucciones del modelo, `BuilderUnavailable("no_instructions")`: no hay
    sección «Qué haces» de relleno.
- **Copiloto**:
  - el modelo recibe las herramientas del agente y las disponibles del cliente,
    con lo que hace cada una;
  - de lo que propone se quita lo que no tenemos (las mismas funciones de D72) y se
    propone el resto (`diff_ops` sobre lo limpio);
  - un cambio que añade una promesa sin herramienta no se propone;
  - una regla sin modelo que promete algo que el agente no hace no se propone. Si
    el cliente tiene una herramienta que lo haría, lo dice; si no, «No tenemos
    herramienta para: …» con `missing_capabilities`.
- **Sugerencias de agentes**:
  - el modelo recibe las herramientas disponibles;
  - el papel es opcional (`"role"?`) y uno fuera de los cuatro llega como `null`.
    La columna y su CHECK no cambian: los cuatro siguen sirviendo a la consola para
    el icono;
  - `feasible_agents` quita la sugerencia cuya descripción promete algo que ninguna
    herramienta disponible hace. Si no queda ninguna, propone «Atención», que
    atiende con la ficha y pasa al equipo.
- **Sin modelo** (`offline_output`):
  - la agenda solo entra si `reservas.create` está disponible. Si no, el
    procedimiento es tomar los datos y pasar al equipo, y su prueba lo comprueba;
  - ya no inventa «Conectar stripe» para cobrar: pone lo que de verdad cobra o
    lleva los cobros, y la revisión de comprobantes.

---

### D78 · La revisión de seguridad del 2026-10-30 (T217)

**Decisión.**
- **Lo que una prueba puede llevar de un cliente final** (`TestOut.transcript`).
  La conversación de una pasada no tiene canal, pero una prueba creada desde una
  sugerencia semanal tiene su `first_message`, su `persona` y su `plan` escritos
  por un modelo que leyó conversaciones reales (tapadas solo en nombres,
  teléfonos, correos y documentos). Se contiene así:
  - `suggestions._store` descarta la sugerencia cuya prueba copia casi al pie de
    la letra un mensaje del lote (`copies_a_message`): n-gramas de 4 palabras,
    sin mayúsculas, tildes ni puntuación; copia si comparte al menos 3 y son la
    mitad, como poco, de los del más corto de los dos. Así cuenta un mensaje
    metido en una persona larga y no cuenta una frase corriente («¿dónde puedo
    aparcar?»). El lote guarda lo que leyó el modelo, ya tapado (`Batch.said`).
  - `attempts` y los turnos van tipados (`TestAttemptOut`, `TestTurnOut`): el
    barrido de `test_console_scope.py` los ve y sus excepciones son explícitas,
    con el residuo escrito (una paráfrasis no literal que no nombra a nadie).
- **El gasto con tope** («Construcción y pruebas» la paga Auphere hasta el tope):
  - **Una pasada viva por agente.** `POST …/test-runs` devuelve la de un trabajo
    `tests` del agente en cola o en marcha (con la caducidad perezosa) y no encola
    otra. La fila del agente se bloquea para que dos peticiones a la vez no lancen
    dos. La pasada que corre dentro de «Guardar» (trabajo `publish`) no cuenta.
  - **«Volver a leer»** pasa por `require_build_room` (`402`).
  - **Identificar el sector** sin partida no llama al modelo: la regla de
    respaldo, que no cuesta, y se vuelve a identificar en la siguiente ocasión.
  - **La suite** vuelve a mirar la partida antes de cada prueba (una vez por
    prueba, en orden). Agotada, la empezada termina sus tres pasadas (una prueba
    con una pasada sola diría «Pasa» con 1 de 1) y las que faltan no empiezan; la
    pasada queda `failed` con `stopped: build_budget_exhausted` y `not_started`, y
    el trabajo falla con ese código. **Sustituye** a «la suite empezada termina»
    de `build_budget.py`. Para que la partida vea lo que gasta la propia suite,
    cada pasada abre su turno de uso (`job:{id}:{prueba}:{pasada}`) y lo publica
    al terminar; antes era uno por trabajo, publicado al final.
  - **`PUT …/basics` que cambia el nicho o la información** identifica como mucho
    una vez por hora (`sector.request_after_edit`, la hora del GET, D59). Solo
    cuentan las identificaciones que lanzó una edición: si contaran la del alta, la
    primera corrección del nicho tras crear el cliente esperaría una hora. Lo que
    cambia dentro de la hora no se pierde: `GET …/basics` llama siempre a
    `request_if_needed`, que lo identifica pasada la hora si el nicho o la
    información se escribieron (`business_field_provenance.at`) después de que la
    última identificación empezara a leer.
- **El lector sin rebinding.** `core/public_http.py`: un `AsyncNetworkBackend` de
  `httpcore` que, por conexión, rechaza los puertos que no son 80 ni 443, resuelve
  una vez, valida todas las direcciones y conecta a una validada; la URL no se
  toca, así que el `Host`, el SNI y la comprobación del certificado son del
  nombre. `httpx` no acepta un backend, así que `PublicTransport` sustituye el
  `_pool` que construye; una prueba comprueba que el backend está puesto, para que
  un `httpx` que lo renombre no lo deje pasar en silencio. El cliente lleva
  `trust_env=False`: un proxy del entorno montaría otro transporte sin guardas. La
  tabla es una copia de la del renderer (`core/public_addresses.py`) porque el
  renderer no puede depender de la API; `test_public_http.py` exige que coincidan.
  `assert_public_url` usa la misma tabla y los mismos puertos.
- **Lo que lee el juez y el cliente simulado.** `neutralise_tags` solo desactiva la
  apertura de las etiquetas con guion bajo: `<plan>` o `<criterios>` seguían siendo
  marcado. `untrusted.inert` la aplica a cada etiqueta del bloque y, después, pasa
  cualquier ángulo a comilla angular. Cada turno, criterio, acción, persona y plan
  pasa por ella. No se cambió `neutralise_tags` (tiene su prueba de paridad).
- **`POST …/agent/versions` con `tools`** sobre un agente estructurado: `409
  structured_agent`. La consola solo manda el texto.
- **El bloqueo por herramienta que no se lee** (`_load_gated_tools`) cierra del
  todo: ninguna herramienta, ni las de la casa. A diferencia de la política de
  activaciones (D76), es una lista de excluidas en la que puede estar cualquier
  herramienta del catálogo (`reservas.create` también), así que «solo las de la
  casa» no bastaría.
- **JSON-LD**: un bloque que tumba `json.loads` con `RecursionError` se salta.
- **La etiqueta del sector** deja de eximir cuando es el nombre del cliente (o el
  de una red) o el de una de sus sedes: entonces es como se llama.
- **`sector_test_catalog`**: `nexus_app` solo la lee (0210, `REVOKE ALL` y `GRANT
  SELECT`, como `sector_guides`). La escriben el panel y la conversión de una guía,
  con el rol de la plataforma.

**Descartado.**
- Reescribir la URL de cada petición con la IP (habría que poner a mano el `Host` y el
  SNI en cada petición y en cada redirección).
- Parar la suite entre pasadas de una misma prueba.
- Una hora de espera que cuente también la identificación del alta y de la
  lectura.

---

### D79 · `PUT …/capabilities` cambia un agente estructurado por su AgentSpec

**Decidida por Luis el 2026-10-30: «Por el validador».** En un agente
estructurado, encender o apagar una herramienta en «Capacidades» edita
`spec.tools` y pasa por el mismo camino que `PATCH …/draft`: lo que no tenemos
se quita y queda anotado (65.3), `validate_spec` decide (un problema da
`422 spec_invalid`) y `write_spec` recompila el prompt y deja `draft.tools`
igual que el documento (`_set_spec_tool`, `api/console/capabilities_client.py`).
Los agentes «instructions» siguen escribiendo `draft.tools`, como antes. La
pantalla y las citas del copiloto no cambian. Prueba:
`test_capabilities_change_a_structured_agent_through_its_spec`.

Lo que sigue es el contexto que llevó a la decisión.

**Contexto.** La revisión pidió `409 structured_agent` también aquí. Un grep en
`apps/console` muestra que la consola nueva llega a esta ruta con agentes
estructurados: el copiloto cita cada herramienta con un enlace a
`/clients/{ref}/capabilities` (`citationHref`, `copilot-panel.tsx`; también
`reviewFixLink` en `quality-model.ts`, aunque la API ya no emite ese arreglo), y
esa pantalla enciende y apaga herramientas (`capability-card.tsx` →
`setCapabilityAction`). Sin `?agent=`, actúa sobre el agente principal.

**Decisión.** No se cierra: devolver `409` rompería esa pantalla. Queda para Luis
elegir entre:
- llevar el cambio de una herramienta de un agente estructurado por su AgentSpec y
  el validador (como `PATCH …/draft` con `spec`), o
- que la cita del copiloto lleve al bloque de herramientas del agente y cerrar la
  ruta con `409`.

El cambio de `mode` (bloqueo por herramienta del cliente) y el de habilidades no
tocan `draft.tools` y no entran aquí.

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
