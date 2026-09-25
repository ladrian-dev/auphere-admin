# Especificación: Diagnóstico IA de Amacrux para el evento (acceso por QR)

**Rama**: `DEMO-AMACRUX-EVENT` (carpeta de spec `009-diagnostico-evento-amacrux`) · **Creada**: 2026-09-16 · **Estado**: Borrador

**Entrada**: descripción del usuario: "Diagnóstico IA de Amacrux para evento con QR:
web mobile-first que entrevista a empresarios y perfiles técnicos, detecta
oportunidades de automatización e IA, entrega 3 recomendaciones priorizadas y
captura un lead con consentimiento". Brief completo en el plan de sesión
(`~/.claude/plans/rol-act-a-como-squishy-shamir.md`) y en la nota de KB enlazada.

## Encabezado Auphere *(obligatorio)*

| Campo | Valor |
|---|---|
| **Superficie de confianza** | **Ninguna de las superficies de agente (`0`–`3b`).** Es una web pública para visitantes de un evento, sin agente, sin tenant, sin herramientas y sin sesión autenticada. La única salida hacia fuera es un correo con el lead a Amacrux. No abre superficie nueva porque no toca la plataforma Nexus: vive en `apps/` como aplicación aislada con su propio despliegue |
| **Garantías de aislamiento tocadas** | **Ninguna de las 7** de `architecture/agent-isolation.md`. No hay `tenant_id`, ni RLS, ni catálogo de herramientas. Las respuestas del visitante no se guardan en ninguna base de datos de Nexus |
| **Nota de KB que la justifica** | `[[Auphere/partnerships/amacrux-diagnostico-evento/amacrux-diagnostico-evento]]` en `/Users/matos/workspace/kb/` |
| **Qué se mide** | **Nada.** El motor de recomendaciones es determinista y local; no consume modelo, reloj de máquina ni herramienta de pago. El envío de correo es coste de infraestructura del partner |

> La spec no abre superficie: entrega su valor entera dentro de "web pública +
> correo saliente". Un modelo de IA en tiempo de ejecución queda explícitamente
> fuera de alcance de esta versión (ver §Fuera de alcance).

## Contexto

> **Revisión v2 (2026-09-16, decisión del usuario tras probar en local):** el
> formulario de contacto pasa a ser la **puerta al resultado**. Tras las 12
> preguntas se piden nombre y apellido, empresa, correo, teléfono opcional y el
> consentimiento; al enviarlos se muestra el diagnóstico. Quien revisa sus
> respuestas no vuelve a pasar por el formulario. Esta decisión invierte el
> principio original "valor antes que datos" (Req. 8.1 y 10.1 anteriores) y se
> registra como riesgo aceptado: puede reducir la tasa de finalización. Las
> secciones siguientes se leen con esta revisión por encima.

Amacrux (Amacrux Lab, Maturín, Venezuela; partner *Embedded* de Auphere)
presenta en un evento de IA y empresas dentro de 2 días. En la pantalla
principal habrá un QR grande. Quien lo escanee llega a una web y, en 2–4
minutos, responde preguntas breves con tarjetas y botones, recibe un resultado
personalizado (perfil, nivel de oportunidad, tres oportunidades priorizadas,
recomendaciones y advertencias) y, solo si quiere, deja sus datos para que
Amacrux le contacte. Debe funcionar en móvil, con ruido alrededor, con poco
tiempo y con conexión móvil normal o lenta, y sin depender de ningún servicio
externo para producir el resultado.

## Escenarios de usuario y pruebas *(obligatorio)*

### Historia 1 — Completar el diagnóstico y ver un resultado útil sin dejar datos (Prioridad: P1)

Una persona escanea el QR, entiende en la primera pantalla qué va a obtener y
cuánto tarda, responde 12 preguntas cortas en 6 pantallas (perfil, empresa,
cómo trabajan hoy, fricciones, objetivos, restricciones) y recibe un resultado
con tres oportunidades concretas ligadas a lo que respondió. No tiene que dar
ningún dato personal para llegar ahí.

**Por qué esta prioridad**: es el valor de la pieza. Sin resultado convincente
no hay motivo para dejar un contacto, y el evento se demuestra con esta historia
sola.

**Prueba independiente**: recorrer el flujo en un móvil de 360 px con cada uno
de los cuatro perfiles de prueba (gerente de pyme, responsable de operaciones,
ingeniero de software, empresa exploratoria) y comprobar que en menos de 4
minutos se ven tres recomendaciones distintas y coherentes con las respuestas,
sin haber tecleado nombre, correo ni teléfono.

**Escenarios de aceptación**:

1. **Dado** un visitante en la pantalla de bienvenida, **cuando** la lee,
   **entonces** ve el nombre de Amacrux, un titular con el beneficio, el tiempo
   estimado (2–4 min), el número aproximado de preguntas (12), un botón
   principal para empezar, una nota breve de privacidad y la indicación de que
   puede obtener el resultado sin registrarse.
2. **Dado** un visitante que empieza, **cuando** responde cada pantalla (una
   pregunta por pantalla), **entonces** contesta tocando chips o tarjetas, nunca
   con texto libre; las de respuesta única avanzan solas y en las de selección
   múltiple "Continuar" solo se habilita con al menos una opción.
3. **Dado** un visitante que ha respondido las 12 preguntas, **cuando** confirma
   la última, **entonces** ve una pantalla de procesamiento breve (menos de 3 s)
   y después un resultado con: resumen de perfil, nivel de oportunidad
   cualitativo, tres oportunidades ordenadas, recomendación de corto plazo, de
   medio plazo, advertencias o dependencias y una llamada a la acción.
4. **Dado** el perfil de prueba A (gerente de pyme, pocos sistemas conectados,
   muchas tareas manuales, quiere ahorrar tiempo, sin equipo técnico, interés
   en un piloto), **cuando** termina, **entonces** las tres oportunidades
   pertenecen a automatización operativa, clasificación de solicitudes,
   asistentes internos o integraciones sencillas, y ninguna exige equipo
   técnico especializado.
5. **Dado** el perfil B (operaciones, alto volumen, coordinación y reporting,
   herramientas desconectadas, urgencia alta), **cuando** termina, **entonces**
   aparecen automatización de operaciones, integración de sistemas y reporting
   o flujos de trabajo, y la llamada a la acción es la de alta intención.
6. **Dado** el perfil C (ingeniería de software, equipo técnico interno,
   productividad del desarrollo, documentación o testing, madurez alta),
   **cuando** termina, **entonces** aparecen IA para desarrollo, documentación,
   testing o integración de agentes en producto.
7. **Dado** el perfil D (no tiene claro el problema, quiere conocer
   posibilidades, baja urgencia, madurez inicial), **cuando** termina,
   **entonces** recibe tres recomendaciones marcadas como orientativas, de tipo
   quick win o educativas, y una invitación a una sesión de descubrimiento sin
   presión comercial.
8. **Dado** cualquier combinación válida de respuestas, **cuando** se genera el
   resultado, **entonces** siempre hay exactamente tres oportunidades, cada una
   con nombre, problema que resuelve, cómo podría funcionar, beneficio potencial,
   complejidad estimada, tiempo aproximado a un primer piloto, sistemas que
   podría conectar, primer paso recomendado, nivel de confianza (orientativo,
   relevante, prioritario) y una explicación de por qué se ha seleccionado que
   cita al menos una respuesta del visitante.

---

### Historia 2 — Dejar un contacto cualificado con consentimiento (Prioridad: P2)

Después de ver el resultado, la persona decide si quiere que Amacrux le
contacte. Rellena nombre, empresa, correo profesional, cargo y, si quiere,
teléfono; el interés principal viene preseleccionado según su resultado; marca
un consentimiento explícito para ser contactada y, por separado, si acepta
comunicaciones comerciales. También puede elegir "Prefiero no dejar mis datos"
y conservar el resultado.

**Por qué esta prioridad**: es el objetivo comercial del evento, pero solo tiene
sentido después de haber entregado valor (Historia 1).

**Prueba independiente**: desde un resultado ya generado, enviar el formulario
con datos válidos y comprobar la confirmación; enviarlo con datos inválidos y
comprobar los errores; pulsar dos veces y comprobar que solo se registra una
vez; elegir "no dejar datos" y comprobar que el resultado sigue visible.

**Escenarios de aceptación**:

1. **Dado** un visitante en el resultado, **cuando** pulsa la llamada a la
   acción, **entonces** ve el formulario con los campos nombre, empresa, correo
   profesional, cargo, teléfono (opcional), interés principal preseleccionado,
   una casilla de consentimiento para ser contactado (obligatoria) y otra
   separada para comunicaciones comerciales (opcional), más un enlace a la
   política de privacidad y una explicación de para qué se usan los datos.
2. **Dado** el formulario con un correo mal formado, un nombre vacío o el
   consentimiento sin marcar, **cuando** intenta enviar, **entonces** ve el
   error junto al campo correspondiente y no se envía nada.
3. **Dado** un formulario válido, **cuando** lo envía, **entonces** el botón se
   bloquea mientras se procesa, y al terminar ve una confirmación que dice qué
   pasará a continuación; un segundo toque durante el envío no genera un
   segundo registro.
4. **Dado** que el envío falla (sin conexión o servicio caído), **cuando**
   termina el intento, **entonces** ve un mensaje comprensible con la opción de
   reintentar y una vía alternativa de contacto, y no pierde el resultado ni las
   respuestas.
5. **Dado** un visitante que elige "Prefiero no dejar mis datos", **cuando** lo
   confirma, **entonces** vuelve al resultado completo, puede copiarlo o
   compartirlo, y no se le vuelve a pedir el contacto salvo que lo pida.
6. **Dado** un lead enviado con éxito y la entrega configurada, **cuando**
   Amacrux lo recibe, **entonces** contiene los datos de contacto, el resumen de
   respuestas, el nivel de oportunidad con su desglose interno, la etiqueta
   interna de cualificación, las tres recomendaciones y la campaña de origen.

---

### Historia 3 — Robustez en un evento: volver atrás, recargar, reiniciar, errores (Prioridad: P3)

La persona se equivoca y vuelve atrás sin perder lo respondido; recarga la
página por accidente y sigue donde estaba; termina y deja el móvil a un colega,
que reinicia en dos toques; si algo falla, ve un mensaje claro y puede seguir.

**Por qué esta prioridad**: en un evento hay prisa, ruido y manos ajenas. Sin
esto, la Historia 1 se rompe en la práctica.

**Prueba independiente**: responder tres pantallas, volver dos atrás, cambiar
una respuesta, recargar, comprobar que se restaura el mismo paso con las
respuestas; reiniciar desde el resultado y comprobar que empieza limpio; forzar
datos corruptos en el almacenamiento y comprobar que arranca limpio con aviso.

**Escenarios de aceptación**:

1. **Dado** un visitante en cualquier pantalla de preguntas, **cuando** pulsa
   "Atrás", **entonces** ve la pantalla anterior con sus respuestas marcadas y
   puede cambiarlas.
2. **Dado** un visitante a mitad del flujo, **cuando** recarga la página o
   vuelve a la pestaña, **entonces** se restaura el mismo paso con las mismas
   respuestas durante la sesión del navegador.
3. **Dado** un visitante en cualquier pantalla, **cuando** pulsa "Reiniciar" y
   confirma, **entonces** el flujo vuelve a la bienvenida sin ninguna respuesta
   ni dato previo, en dos acciones como máximo.
4. **Dado** un almacenamiento de sesión con datos corruptos o de una versión
   anterior, **cuando** se abre la aplicación, **entonces** arranca limpia sin
   error visible más que un aviso breve.
5. **Dado** un navegador sin alguna capacidad moderna (compartir nativo,
   almacenamiento de sesión), **cuando** se usa la aplicación, **entonces** el
   flujo completo sigue funcionando y solo desaparece la función que depende de
   esa capacidad, sin botones apagados ni pantallas de disculpa.
6. **Dado** un fallo inesperado al generar el resultado, **cuando** ocurre,
   **entonces** se muestra un estado de error con explicación breve y las
   opciones de reintentar y de reiniciar; las respuestas no se pierden.

---

### Historia 4 — Llegar desde el QR con la campaña identificada y medir el embudo sin datos personales (Prioridad: P4)

El QR del evento apunta a una dirección corta y estable que identifica la
campaña. Cada paso del embudo emite un evento de analítica sin datos personales
para que Amacrux sepa cuántas personas empezaron, cuántas terminaron y cuántas
dejaron contacto.

**Por qué esta prioridad**: sin medición no se puede evaluar el evento, pero la
experiencia funciona sin ella.

**Prueba independiente**: abrir la dirección de campaña, completar el flujo y
comprobar en el registro de eventos que aparecen, en orden, los eventos
previstos con la campaña y sin ningún dato personal.

**Escenarios de aceptación**:

1. **Dado** un visitante que abre la dirección de campaña (con o sin parámetros
   UTM), **cuando** carga, **entonces** ve la bienvenida y la campaña queda
   asociada a su sesión sin aparecer nunca junto a datos personales en la
   dirección.
2. **Dado** cualquier paso del embudo, **cuando** ocurre, **entonces** se
   registra el evento correspondiente (`landing_viewed`, `assessment_started`,
   `question_answered`, `assessment_completed`, `result_viewed`,
   `recommendation_selected`, `contact_form_viewed`, `lead_submitted`,
   `contact_skipped`, `assessment_restarted`, `error_shown`) con, como máximo,
   paso, categoría de perfil, categoría de recomendación, nivel de madurez,
   nivel de intención, campaña y marca de tiempo.
3. **Dado** que no hay proveedor de analítica configurado, **cuando** se usa la
   aplicación, **entonces** los eventos se descartan silenciosamente y nada
   falla.

---

### Casos límite

- ¿Qué pasa cuando el visitante elige "Otro" en perfil, sector o fricción? El
  motor usa señales genéricas y sigue produciendo tres recomendaciones, con
  confianza orientativa si no hay más señales.
- ¿Qué pasa cuando responde lo mínimo (una fricción, un objetivo, todo
  "explorar")? Recibe tres recomendaciones orientativas de tipo quick win para
  su perfil y una invitación a una sesión de descubrimiento.
- ¿Qué pasa cuando marca fricciones que apuntan a seis categorías distintas? El
  resultado muestra tres, con como máximo dos de la misma categoría, y explica
  por qué esas.
- ¿Qué pasa si la madurez es inicial y el visitante marca fricciones de
  desarrollo de software con equipo técnico especializado? Las recomendaciones
  respetan la capacidad técnica y marcan la advertencia de madurez en lugar de
  contradecirla.
- ¿Qué pasa si el envío del lead tarda más de lo razonable? El visitante ve el
  estado de carga, y pasado el tiempo límite un error con reintento; el
  resultado sigue visible.
- ¿Qué pasa si dos personas usan el mismo móvil seguidas? "Reiniciar" en dos
  acciones borra todo lo anterior; el lead nunca se conserva en el dispositivo.
- ¿Qué ve el usuario cuando una capacidad **no está disponible**? Si no hay
  entrega de leads configurada (modo demostración), el formulario sigue
  funcionando y la confirmación es honesta: "hemos registrado tu interés en
  modo demostración"; no hay botones apagados. Si no hay analítica, no hay
  rastro en pantalla. Si el navegador no puede compartir, no aparece el botón
  de compartir, sí el de copiar.
- ¿Qué pasa con conexión lenta? La primera carga es ligera, el resultado se
  calcula en el dispositivo y no hay llamadas de red hasta el envío del lead.
- ¿Qué pasa en pantallas muy pequeñas o muy grandes? El diseño se adapta de
  360 px a escritorio sin desplazamiento horizontal y con zonas táctiles de
  al menos 44 px.
- ¿Qué pasa si el sistema está en modo oscuro? La aplicación respeta la
  preferencia con la misma legibilidad y contraste.

## Requisitos *(obligatorio)*

### Requisito 1 — Bienvenida clara

**Historia de usuario:** Como visitante que llega desde un QR, quiero entender
en segundos qué voy a obtener y cuánto tarda, para decidir si empiezo.

#### Criterios de aceptación

1. WHEN el visitante abre la dirección de bienvenida THEN el sistema DEBE
   mostrar la marca de Amacrux (wordmark cromado centrado en la cabecera; sin
   isotipo en el cuerpo), un titular breve con el beneficio (≤ 10 palabras), el botón
   principal "Empezar diagnóstico" y, debajo y en tamaño pequeño, la línea con
   el número de preguntas y las tres recomendaciones. Toda la bienvenida,
   incluido el pie con el sticker, DEBE caber sin scroll en un celular de
   375×667. (Revisión 2026-09-16: se retiran la sección
   "Qué te llevas", el párrafo de propuesta de valor y la nota de privacidad
   bajo el botón; la privacidad queda enlazada en el pie.)
2. El sistema DEBE mostrar la bienvenida sin ningún inicio de sesión, cuenta ni
   dato personal.
3. WHERE la dirección incluye una campaña o parámetros UTM EL sistema DEBE
   asociarlos a la sesión sin mostrarlos ni mezclarlos con datos personales.

### Requisito 2 — Preguntas breves con respuestas estructuradas

**Historia de usuario:** Como visitante con prisa, quiero responder tocando
opciones, para terminar en pocos minutos sin escribir.

#### Criterios de aceptación

1. El sistema DEBE presentar exactamente 12 preguntas, **una por pantalla**
   (revisión 2026-09-16 tras la prueba en móvil: el agrupado en 6 pantallas
   exigía demasiada lectura): perfil, sector, tamaño del equipo, tipo de
   clientes, cómo trabajan hoy (5 niveles), uso de IA, dónde vive la
   información, fricciones (hasta 3 de 19), objetivos (hasta 2 de 12),
   urgencia, apoyo técnico y nivel de inversión. Las etiquetas de las opciones
   tienen como máximo 4 palabras y se muestran como chips en dos columnas.
2. WHEN una pregunta es de selección única THEN el sistema DEBE permitir una
   sola opción, reflejarla visualmente y **avanzar automáticamente** a la
   siguiente pantalla tras un instante; IF la respuesta ya estaba marcada (el
   visitante volvió atrás) THEN el sistema NO DEBE avanzar solo y DEBE mantener
   "Continuar" habilitado.
3. WHEN una pregunta es de selección múltiple THEN el sistema DEBE impedir
   superar el máximo indicado y mostrar cuántas quedan.
4. El sistema NO DEBE pedir texto libre en ninguna pregunta; "Otro" es una
   opción más, sin campo de texto.
5. El sistema NO DEBE mostrar la palabra "madurez" al visitante; los niveles se
   describen con lenguaje cotidiano (inicial, explorando, adoptando, avanzado,
   escalando).
6. WHEN la pantalla no tiene una respuesta válida THEN el sistema DEBE mantener
   "Continuar" deshabilitado con indicación visible de qué falta.

### Requisito 3 — Navegación, progreso y tiempo

**Historia de usuario:** Como visitante, quiero saber cuánto me falta y poder
volver atrás, para no sentirme atrapado.

#### Criterios de aceptación

1. El sistema DEBE mostrar en todas las pantallas de preguntas una barra de
   progreso accesible y el tiempo estimado restante en minutos.
2. WHEN el visitante pulsa "Atrás" THEN el sistema DEBE mostrar la pantalla
   anterior con sus respuestas conservadas.
3. WHEN el visitante cambia una respuesta anterior THEN el sistema DEBE
   conservar las respuestas posteriores que sigan siendo válidas y recalcular el
   resultado al final.
4. WHEN el visitante pulsa "Reiniciar" THEN el sistema DEBE pedir una
   confirmación única y, al confirmar, borrar todas las respuestas y volver a la
   bienvenida (dos acciones en total).

### Requisito 4 — Persistencia temporal durante la sesión

**Historia de usuario:** Como visitante que recarga por accidente, quiero seguir
donde estaba, para no repetir todo.

#### Criterios de aceptación

1. WHEN el visitante avanza de pantalla THEN el sistema DEBE guardar el paso y
   las respuestas en el almacenamiento de sesión del navegador, sin datos
   personales.
2. WHEN se recarga o se vuelve a la pestaña durante la misma sesión THEN el
   sistema DEBE restaurar el mismo paso y las mismas respuestas.
3. IF el contenido almacenado es inválido, está corrupto o es de otra versión
   THEN el sistema DEBE descartarlo, arrancar limpio y mostrar un aviso breve, y
   NO DEBE mostrar un error técnico.
4. El sistema NO DEBE guardar nunca en el dispositivo los datos del formulario
   de contacto una vez enviado o descartado.
5. IF el almacenamiento de sesión no está disponible THEN el sistema DEBE
   funcionar en memoria durante la visita sin fallar.

### Requisito 5 — Motor de recomendaciones determinista y explicable

**Historia de usuario:** Como visitante, quiero recomendaciones que se noten
hechas para mi situación, para creer que merece la pena hablar con Amacrux.

#### Criterios de aceptación

1. El sistema DEBE generar el resultado a partir de un catálogo estructurado de
   oportunidades (al menos 24, cubriendo 8 categorías: automatización
   operativa, IA para conocimiento y soporte, automatización comercial,
   procesamiento documental, datos y reporting, IA para desarrollo de software,
   integraciones y orquestación, optimización de producto digital), donde cada
   oportunidad declara título, categoría, perfiles y sectores aplicables,
   señales de problema, resultados deseados, rango de madurez, complejidad
   técnica, tiempo a piloto, beneficio, información necesaria, primer paso,
   encaje con Amacrux, herramientas relacionadas, advertencia y llamada a la
   acción comercial.
2. WHEN se calculan las recomendaciones THEN el sistema DEBE puntuar cada
   oportunidad según las fricciones, objetivos, perfil, sector y categorías
   detectadas, ordenar de forma reproducible y seleccionar tres.
3. El sistema DEBE producir el mismo resultado para las mismas respuestas en
   cualquier dispositivo y momento (determinismo).
4. IF una oportunidad exige más capacidad técnica de la declarada THEN el
   sistema NO DEBE recomendarla; IF está fuera del rango de madurez THEN el
   sistema DEBE penalizarla y, si aun así se muestra, añadir la advertencia
   correspondiente.
5. WHEN hay menos de tres oportunidades con señales THEN el sistema DEBE
   completar con recomendaciones educativas por perfil marcadas como
   orientativas.
6. El sistema DEBE limitar a dos las oportunidades de una misma categoría en el
   resultado.
7. WHEN se muestra una recomendación THEN el sistema DEBE incluir su nivel de
   confianza (orientativo, relevante, prioritario) y una explicación que cite
   al menos una respuesta del visitante.
8. El sistema NO DEBE incluir en ningún texto cifras de ahorro, retorno de
   inversión o resultados garantizados; el impacto se expresa de forma
   cualitativa ("alto potencial", "puede reducir tareas manuales", "requiere
   validar datos, volumen y sistemas actuales").
9. El sistema DEBE exponer una interfaz de proveedor de recomendaciones con una
   implementación por reglas y un punto de validación que rechace cualquier
   resultado que invente datos de la empresa, garantice ahorros, dé consejo
   legal, financiero o médico, exponga datos personales o ignore las respuestas,
   preparado para un proveedor con modelo de IA en una versión posterior.

### Requisito 6 — Segmentación y puntuación internas

**Historia de usuario:** Como Amacrux, quiero que cada resultado lleve una
segmentación y una puntuación reproducibles, para priorizar el seguimiento.

#### Criterios de aceptación

1. El sistema DEBE clasificar cada resultado en cinco dimensiones: perfil
   (decisor de negocio, operaciones, tecnológico, ingeniería, producto e
   innovación, marketing y ventas, consultor o independiente), madurez
   (explorador, inicial, en adopción, integrador, escalador), categorías de
   oportunidad (las 8 del catálogo), intención (baja, media, alta, muy alta) y
   complejidad (quick win, piloto de baja complejidad, proyecto de integración,
   transformación de proceso, solución estratégica o de producto).
2. El sistema DEBE calcular una puntuación de 0 a 100 sumando claridad del
   problema (0–20), impacto potencial (0–20), urgencia (0–15), capacidad de
   implementación (0–15), madurez digital (0–10), encaje con los servicios
   (0–10) e intención de contacto (0–10), con desglose por factor.
3. El sistema DEBE asignar el rango 0–29 exploración y educación, 30–54
   oportunidad inicial, 55–74 oportunidad prioritaria, 75–100 alta intención.
4. El sistema DEBE mostrar al visitante solo un nivel de oportunidad
   cualitativo, y NO DEBE mostrar la puntuación numérica ni etiquetas como
   "frío" o "caliente"; esas etiquetas existen solo en el registro que recibe
   Amacrux.
5. La llamada a la acción del resultado DEBE ser única para todos los
   perfiles: "Solicita una DEMO" (decisión del usuario, 2026-09-16;
   sustituye a la variación por intención). La intención sigue calculándose
   para el correo y la analítica.

### Requisito 7 — Pantalla de resultado

**Historia de usuario:** Como visitante, quiero un resultado visual y concreto,
para llevarme algo útil aunque no deje mis datos.

#### Criterios de aceptación

1. WHEN se muestra el resultado THEN el sistema DEBE incluir, en este orden:
   perfil resumido, nivel de oportunidad, tres oportunidades prioritarias con
   sus ocho atributos (Requisito 5.1) y su explicación, recomendación de corto
   plazo, recomendación de medio plazo, advertencias o dependencias, y la
   llamada a la acción según intención.
2. El sistema DEBE abrir el resultado con una frase que conecte con las
   respuestas ("Por lo que nos cuentas, el mayor potencial parece estar en …").
3. El sistema DEBE incluir la nota "Las recomendaciones son orientativas" y un
   enlace a la política de privacidad.
4. (v2) El resultado cierra con un bloque "Siguiente paso: una DEMO con
   Amacrux" que confirma que el contacto ya se envió (o que está en modo
   demostración), y ofrece revisar respuestas o reiniciar. Sin botones de
   copiar ni compartir. (Cal.com se valoró y se descartó el 2026-09-16.)

### Requisito 8 — Captura de lead con consentimiento explícito

**Historia de usuario:** Como visitante convencido, quiero dejar mis datos de
forma rápida y segura, para que Amacrux me contacte.

#### Criterios de aceptación

1. (v2) El sistema DEBE pedir los datos de contacto **después de las 12
   preguntas y antes de mostrar el resultado**; el resultado se calcula en el
   dispositivo en ese momento y se adjunta al contacto enviado.
2. El formulario DEBE contener (revisión 2026-09-16, versión reducida a
   petición del usuario): nombre, empresa, correo profesional, teléfono
   opcional, consentimiento para ser contactado (obligatorio y desmarcado por
   defecto). El botón "Prefiero no dejar mis datos" se retiró a petición del
   usuario (2026-09-16): quien no quiera dejar datos usa "Volver al resultado".
   El interés principal se rellena solo con la categoría principal del resultado; el cargo y el
   consentimiento de comunicaciones comerciales no se piden en esta versión
   (viajan vacíos / en falso).
3. WHEN el visitante envía THEN el sistema DEBE validar nombre (2–120
   caracteres), empresa (1–160), correo con formato válido (máx. 200), cargo
   opcional (máx. 120), teléfono opcional (7–20 caracteres si se rellena) y consentimiento
   marcado, mostrando el error junto a cada campo inválido.
4. WHILE un envío está en curso el sistema DEBE deshabilitar el botón e ignorar
   envíos repetidos; cada envío lleva una clave de idempotencia de la sesión.
5. IF el envío falla THEN el sistema DEBE mostrar un mensaje comprensible con
   reintento y una vía alternativa de contacto, y NO DEBE perder el resultado.
6. WHEN el envío tiene éxito THEN el sistema DEBE mostrar una confirmación con
   los siguientes pasos y no volver a pedir el contacto en esa sesión.
7. El sistema DEBE incluir una protección contra envíos automatizados que no
   añada fricción visible a las personas (sin captcha).

### Requisito 9 — Entrega del lead a Amacrux

**Historia de usuario:** Como Amacrux, quiero recibir cada lead de forma
inmediata y estructurada, para hacer seguimiento tras el evento.

#### Criterios de aceptación

1. WHEN llega un lead válido y la entrega está configurada THEN el sistema DEBE
   enviar a la dirección de correo configurada de Amacrux un mensaje
   estructurado con: datos de contacto, resumen de respuestas, nivel y
   puntuación con desglose, etiqueta interna de cualificación, las tres
   recomendaciones y la campaña de origen.
2. El sistema DEBE realizar la entrega desde el servidor; ninguna clave o
   secreto de proveedor DEBE existir en el código que llega al navegador.
3. IF la entrega no está configurada (modo demostración) THEN el sistema DEBE
   aceptar el lead, indicar honestamente al visitante que está en modo
   demostración y registrar solo un aviso sin datos personales.
4. IF la entrega está configurada pero falla THEN el sistema DEBE responder con
   un error que el formulario muestre como reintentable, y NO DEBE confirmar
   como entregado lo que no se entregó.
5. El sistema DEBE limitar el número de envíos por origen en una ventana de
   tiempo para contener abusos.
6. El sistema DEBE definir la entrega tras una interfaz de repositorio de leads
   con una implementación local (desarrollo y demostración) y otra conectada al
   servidor, de modo que se pueda cambiar el destino (correo, webhook, CRM) sin
   tocar la experiencia.
7. (v2, decisión 2026-09-16) WHEN llega un lead válido y la base de leads está
   configurada THEN el sistema DEBE guardar una fila en Supabase con contacto,
   consentimientos, campaña/UTM, las 12 respuestas (valores y etiquetas
   legibles), puntuación, rango, etiqueta interna, segmento, las tres
   recomendaciones y si el correo salió; una clave de idempotencia repetida NO
   DEBE duplicar la fila. Solo se guardan leads enviados con consentimiento.
8. El correo de aviso DEBE poder enviarse a varias direcciones (Amacrux y
   Auphere) configuradas en el servidor.
9. IF falla uno de los destinos configurados (base o correo) pero otro funciona
   THEN el sistema DEBE responder éxito indicando qué se hizo (`stored`,
   `delivered`) y registrar el fallo sin datos personales; IF fallan todos THEN
   DEBE responder error reintentable.
10. WHERE hay un webhook configurado EL sistema DEBE enviar además una copia
   plana del lead (una columna por dato) para una hoja de cálculo, tras los
   destinos principales y sin bloquear la respuesta si falla.

### Requisito 10 — Privacidad y seguridad

**Historia de usuario:** Como visitante, quiero saber qué se hace con mis
datos y que no se recojan antes de tiempo, para confiar.

#### Criterios de aceptación

1. El sistema NO DEBE recoger ni almacenar datos personales antes de la
   pantalla de contacto (que en v2 precede al resultado); nunca en el
   almacenamiento del dispositivo.
2. El sistema DEBE explicar junto al formulario qué datos se piden y para qué,
   y enlazar una política de privacidad legible.
3. El sistema NO DEBE incluir datos personales en direcciones, parámetros de
   consulta, eventos de analítica ni registros del servidor.
4. El sistema NO DEBE guardar las respuestas completas en registros de
   producción.
5. El sistema NO DEBE enviar datos a terceros sin una integración configurada
   explícitamente por variable de entorno.
6. El sistema DEBE sanear y validar en el servidor todo dato recibido.
7. El sistema DEBE documentar cómo eliminar o anonimizar los leads recibidos
   (sentencia SQL de borrado por correo en la migración y en `docs/CONFIG.md`).

### Requisito 11 — Analítica anónima del embudo

**Historia de usuario:** Como Amacrux, quiero medir el embudo del evento, para
saber cuántas personas empezaron, terminaron y dejaron contacto.

#### Criterios de aceptación

1. El sistema DEBE emitir los once eventos listados en la Historia 4 con, como
   máximo, las propiedades: paso, categoría de perfil, categoría de
   recomendación, nivel de madurez, nivel de intención, campaña y marca de
   tiempo.
2. El sistema DEBE definir la emisión tras una interfaz independiente del
   proveedor, con un adaptador nulo por defecto y la posibilidad de activar un
   proveedor por configuración.
3. IF no hay proveedor configurado THEN el sistema DEBE descartar los eventos
   sin efecto visible ni error.

### Requisito 12 — Acceso desde el QR y direcciones

**Historia de usuario:** Como organizador, quiero una dirección corta y estable
para el QR, para que funcione aunque la gente la teclee.

#### Criterios de aceptación

1. El sistema DEBE responder en la raíz del sitio con la bienvenida y en una
   dirección de campaña con forma `/eventos/<identificador>` que preseleccione
   la campaña.
2. El sistema DEBE aceptar parámetros UTM en cualquiera de las dos direcciones
   y asociarlos a la sesión.
3. El sistema DEBE ofrecer título, descripción, imagen para vista previa en
   redes y favicon con la marca de Amacrux, e indexación abierta para las
   páginas públicas.
4. El sistema NO DEBE exigir navegación compleja: el flujo completo se recorre
   desde una sola dirección de entrada.

### Requisito 13 — Diseño responsive, accesible y con la marca de Amacrux

**Historia de usuario:** Como visitante en un evento con ruido, quiero una
interfaz legible y cómoda en el móvil, para responder sin esfuerzo.

#### Criterios de aceptación

1. El sistema DEBE usar los colores oficiales del manual de marca de Amacrux
   (navy `#01103f`, turquesa `#5bdfd2`, gris `#39383b`, blanco; la carpeta
   "Logos" usa variantes cercanas `#01224b`/`#5dddd1`/`#3c3b3e`) y sus
   logotipos (wordmark, isotipo hexagonal y variante simplificada), definidos como
   variables de diseño sustituibles (color principal, secundario, fondo,
   superficie, texto principal, texto secundario, éxito, advertencia, radios,
   sombras, espaciado, tipografía).
2. El sistema DEBE funcionar sin desplazamiento horizontal desde 360 px hasta
   escritorio, con botones y zonas táctiles de al menos 44 px.
3. El sistema DEBE ser operable por teclado de principio a fin, con foco
   visible, etiquetas y nombres accesibles, semántica correcta y contraste AA.
4. El sistema DEBE ofrecer estados de foco, hover, deshabilitado, carga y error
   en los controles, y respetar la preferencia de movimiento reducido.
5. El sistema DEBE respetar el modo oscuro del sistema con la misma
   legibilidad.
6. El sistema DEBE usar un tono inteligente, consultivo, claro, cercano y sin
   jerga, sin urgencia falsa ni patrones manipulativos, y marcar con
   `TODO_COMERCIAL: validar con Amacrux` todo texto pendiente de validación
   comercial.
8. El sistema DEBE mostrar en el pie de todas las páginas salvo la bienvenida
   el sello de partner:
   el texto "Partner oficial de" fuera del sticker y, debajo, un sticker
   holográfico 3D rectangular con el logo de Auphere (generado con Higgsfield a
   partir del logo real; versión 4K en la KB de marca), enlazado a auphere.com,
   igual en tema claro y oscuro, con nombre accesible
   (`TODO_COMERCIAL: validar la fórmula exacta`).
9. El sistema DEBE ofrecer un interruptor claro/oscuro en la cabecera a partir
   del diagnóstico (no en la bienvenida), con persistencia en el dispositivo y
   aplicado antes de pintar; por defecto arranca en modo claro.
10. Todo el copy DEBE estar en español latinoamericano (ustedes, costo,
   celular), sin formas de España (vosotros, coste, móvil).
7. El sistema NO DEBE afirmar servicios concretos de Amacrux que no consten en
   el repositorio; usa categorías prudentes (automatización de procesos,
   asistentes internos con IA, integraciones, automatización de operaciones,
   extracción y clasificación de información, flujos inteligentes, IA aplicada
   a producto, prototipado y desarrollo, optimización de tareas repetitivas).

### Requisito 14 — Estados, errores y funcionamiento sin servicios externos

**Historia de usuario:** Como quien demuestra la pieza en el evento, quiero que
funcione aunque falle todo lo externo, para no depender de nada en directo.

#### Criterios de aceptación

1. El sistema DEBE calcular y mostrar el resultado sin ninguna llamada de red.
2. El sistema DEBE ofrecer un modo demostración controlable por configuración
   en el que la entrega de leads y la analítica se simulan localmente.
3. WHEN ocurre un error inesperado THEN el sistema DEBE mostrar un estado de
   error comprensible con reintentar y reiniciar, y emitir `error_shown`.
4. El sistema DEBE mostrar estados de carga durante el procesamiento del
   resultado y el envío del lead.
5. El sistema DEBE cargar la bienvenida en menos de 3 segundos en una conexión
   móvil 4G típica y mantenerse usable en 3G.

### Requisito 15 — Pruebas y documentación de entrega

**Historia de usuario:** Como equipo, quiero pruebas y guías, para publicar con
confianza en 2 días y operar el evento sin sorpresas.

#### Criterios de aceptación

1. El sistema DEBE incluir pruebas automatizadas de: puntuación, segmentación,
   motor de recomendaciones (incluidos los cuatro perfiles A–D y los casos
   límite), validación del formulario, navegación entre pasos, persistencia
   temporal, respuestas incompletas, envío duplicado y estados de error.
2. El sistema DEBE incluir documentación de instalación, configuración,
   variables de entorno de ejemplo, decisiones técnicas, lista de
   `TODO_COMERCIAL`, guía de prueba rápida para el evento y lista de
   comprobación de publicación.
3. El sistema DEBE ejecutarse con comandos documentados y sin dependencias más
   allá de las declaradas en el plan.

### Entidades clave

- **Respuestas**: las 12 respuestas del visitante más la campaña de origen. No
  contienen datos personales. Viven en la sesión del navegador.
- **Segmento**: perfil, madurez, categorías de oportunidad, intención y
  complejidad derivados de las respuestas.
- **Puntuación**: total 0–100, rango, desglose por factor y etiqueta interna de
  cualificación. Solo el nivel cualitativo llega al visitante.
- **Oportunidad**: entrada del catálogo con los atributos del Requisito 5.1.
- **Recomendación**: oportunidad seleccionada más puntuación, confianza,
  razones y advertencias.
- **Resultado**: resumen, tres recomendaciones, corto y medio plazo,
  advertencias, llamada a la acción, segmento y puntuación, con versión.
- **Lead**: datos de contacto, interés, consentimientos, instantánea del
  resultado (puntuación, segmento, identificadores de recomendación), campaña
  y clave de idempotencia. Se entrega y no se conserva en el dispositivo. **No
  pertenece a ningún tenant de Nexus**: no se persiste en la plataforma.
- **Evento de analítica**: nombre y propiedades anónimas.

## Criterios de éxito *(obligatorio)*

- **CE-001**: una persona completa el flujo desde un celular, de bienvenida a
  resultado, en menos de 4 minutos; en v2 el resultado requiere dejar nombre,
  empresa y correo (decisión del usuario).
- **CE-002**: el 100 % de las combinaciones válidas de respuestas producen
  exactamente tres recomendaciones con todos sus atributos, y las mismas
  respuestas producen siempre el mismo resultado.
- **CE-003**: los cuatro perfiles de prueba (A–D) reciben recomendaciones de
  las categorías esperadas descritas en la Historia 1.
- **CE-004**: ningún dato personal aparece en direcciones, eventos de analítica
  ni registros; el formulario rechaza el 100 % de los envíos inválidos y no
  registra dos veces un doble toque.
- **CE-005**: el flujo se reinicia en dos acciones como máximo y sobrevive a
  recargas, vuelta atrás y almacenamiento corrupto.
- **CE-006**: la pieza se demuestra completa sin ningún servicio externo
  activo (modo demostración).
- **CE-007**: navegación completa por teclado y sin errores críticos de
  accesibilidad automatizada; la bienvenida carga en menos de 3 s en 4G.
- **CE-008**: la lógica crítica (puntuación, segmentación, motor, validación,
  navegación, persistencia, duplicados, errores) tiene pruebas automatizadas en
  verde y el proyecto se ejecuta con comandos documentados.

## Fuera de alcance

- Conversación libre con un modelo de IA en tiempo de ejecución — coste,
  latencia y riesgo en un evento; queda la interfaz preparada para una versión
  posterior.
- Integración con un CRM o panel de leads — no hay integración configurada; el
  correo estructurado cubre el evento.
- Persistencia de respuestas o resultados en servidor — no aporta valor al
  evento y añade obligaciones de privacidad.
- Varios idiomas — el evento es en español.
- Autenticación, cuentas o historial — contradice el acceso por QR sin
  registro.
- Cálculo de ahorro o retorno de inversión — el brief lo prohíbe expresamente.
- Uso de las mascotas 3D y de las tipografías del manual (Agrandir y SF Pro) o
  de la guía anterior (Akira y Rocking Horse) — sin licencia web ni piezas
  vectoriales; se usan sustitutas libres (Outfit e Inter) y queda anotado como
  `TODO_COMERCIAL`.

## Supuestos

- Amacrux aprueba que la experiencia se presente como "Diagnóstico IA de
  Amacrux" y validará los textos marcados `TODO_COMERCIAL` antes o después del
  evento; mientras tanto se usan categorías prudentes de servicios.
- El destinatario del correo de leads y el remitente verificado los proporciona
  Amacrux (o Auphere en su nombre) antes de publicar; sin ellos la pieza corre
  en modo demostración.
- El idioma es español neutro con guiños a Venezuela solo donde no resten
  claridad.
- Los visitantes usan navegadores modernos de los últimos dos años; en los
  demás se degrada con elegancia.
- La campaña del evento se identifica con un identificador en la dirección
  (por ejemplo `ia-empresas-2026`) definido por el organizador.
- La aplicación se publica en el mismo proveedor que el resto de aplicaciones
  web del repositorio, con su propio proyecto y dominio.
- La marca proviene del "Manual de marca simplificado" (PDF, 2026-09-16) y de
  la carpeta "Logos" compartida por Amacrux (logotipos en PNG, guía de tono);
  el vector maestro se pedirá después.
