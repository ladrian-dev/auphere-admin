---
name: aesthetic-procedures-kb
description: Base de conocimiento curada de los procedimientos del catálogo medspa + cirugía estética. Para cada uno: qué es, mecanismo general, duración de sesión/cirugía, recovery típica social y completa, resultado esperable en rangos, contraindicaciones absolutas conocidas, mitos frecuentes que el agente puede aclarar. Fuentes: ASPS (American Society of Plastic Surgeons) y ASAPS/The Aesthetic Society 2024-2025, ISAPS Global Survey, AAD, monografías Allergan y Galderma, SVCPREM. Surface this skill on any educational intent — la paciente pregunta qué es un procedimiento, cuánto dura, cómo se recupera, si puede hacerlo, qué incluye el precio.
version: 1
---

# Base de conocimiento — procedimientos estéticos (catálogo medspa + cirugía)

Esta skill es la fuente del conocimiento educativo del agente para el
vertical `aesthetic_clinic_v1`. Cubre los 18 procedimientos del
catálogo de Clínica Boreal — el patrón es replicable a cualquier
clínica del segmento con el mismo conjunto de servicios.

## Regla maestra de uso

**El agente informa con base en esta KB; nunca prescribe.** Las cinco
skills disciplinarias siguen aplicando — esta KB describe, no indica
dosis ni recomienda marcas ni promete resultados. Toda respuesta
educativa cierra con la frase: *"Cada caso es individual — lo
confirmás en la consulta con {clinical.titular_name}."*

Si la paciente pregunta algo que NO está cubierto en esta KB, el
agente NO improvisa: deriva a consulta.

## Fuentes citadas

Estas son las referencias públicas en las que se apoya esta skill.
Cuando el agente cite información técnica, puede invocar el origen
genéricamente ("según las guidelines de la Sociedad Americana de
Cirugía Plástica…") sin enlazar URLs en el chat — el paciente
busca confianza, no una bibliografía.

- **ASPS** — American Society of Plastic Surgeons. Patient education
  + procedure statistics + guidelines (plasticsurgery.org).
- **The Aesthetic Society** (ex-ASAPS) — Aesthetic Plastic Surgery
  Statistics + cosmetic surgery safety reports
  (theaestheticsociety.org).
- **ISAPS Global Survey** — International Society of Aesthetic
  Plastic Surgery, datos anuales por país (isaps.org).
- **AAD** — American Academy of Dermatology. Guidelines de
  procedimientos láser y químicos (aad.org).
- **SVCPREM** — Sociedad Venezolana de Cirugía Plástica
  Reconstructiva, Estética y Maxilofacial. Reglamento de buenas
  prácticas locales.
- **Allergan Aesthetics** — monografías de Botox cosmético y
  Juvederm.
- **Galderma** — monografías de Restylane y Dysport.
- **NICE / NHS** — Reino Unido, guidelines de seguridad en
  procedimientos cosméticos.

Las cantidades específicas (rangos de duración, recovery, precios)
que aparecen abajo son consistentes con publicaciones 2024–2025 de
ASPS / ASAPS y monografías de las casas comerciales. Si un dato
queda desactualizado, se corrige en este archivo y el operador
re-sube la skill — no se hardcodea en el system prompt.

---

# Medspa — procedimientos no quirúrgicos

## 1. Botox cosmético (toxina botulínica tipo A)

**Qué es.** Inyección de una neurotoxina purificada que bloquea
temporalmente la señal entre el nervio y el músculo en la zona
aplicada. El músculo se relaja → la piel sobre él arruga menos →
las líneas dinámicas (frente, entrecejo, patas de gallo) se atenúan.

**Mecanismo general.** Bloqueo reversible de la liberación de
acetilcolina en la placa neuromuscular. La toxina degrada en semanas
y la función del músculo regresa gradualmente.

**Duración de la sesión.** 20–30 min.

**Inicio del efecto.** Visible a los 3–7 días; pico a las 2 semanas.

**Duración del efecto.** Típicamente 4 meses; rango habitual 3–6
meses. Algunos pacientes con metabolismo más rápido o ejercicio
intenso lo "queman" antes; otros lo mantienen hasta 6 meses.

**Recovery social.** Cero. Vida normal la misma tarde. Recomendaciones
post: no masajear ni acostarse boca abajo en las primeras 4 horas;
evitar ejercicio intenso 24h; alcohol con moderación.

**Contraindicaciones absolutas.** Embarazo, lactancia, miastenia
gravis, esclerosis lateral amiotrófica (ELA), síndrome de
Lambert-Eaton, hipersensibilidad conocida a la toxina o sus
componentes.

**Contraindicaciones relativas.** Anticoagulación crónica
(no contraindica, pero aumenta riesgo de hematoma — el médico
ajusta protocolo), infección activa en la zona, enfermedad
neuromuscular en estudio.

**Mitos frecuentes que el agente puede aclarar.**

- *"Si me lo hago una vez voy a depender de él."* — Falso. El efecto
  desaparece progresivamente; el músculo recupera función. No hay
  dependencia farmacológica.
- *"Te queda la cara congelada."* — Solo si la dosis es excesiva o
  mal distribuida. Bien dosificado, la expresión natural se preserva.
- *"Lo importante es la marca."* — Las marcas registradas en su
  indicación aprobada son equivalentes en sus efectos clínicos. La
  diferencia técnica es pequeña y la define el médico estético.
  (Skill `medical-claims-discipline` aplica.)

**Cuándo derivar a consulta sin más conversación.** Paciente
embarazada o amamantando; paciente con enfermedad neuromuscular
declarada; paciente que pide dosis específica; paciente con
expectativa irreal o referencia a celebridad.

---

## 2. Ácido hialurónico labial (relleno de labios)

**Qué es.** Inyección de un gel de ácido hialurónico (HA) reticulado
en los labios para aumentar volumen, definir bordes o corregir
asimetrías leves.

**Mecanismo general.** El HA es una molécula que existe naturalmente
en la piel; el gel reticulado mantiene su forma e hidrata la zona
hasta que el cuerpo lo metaboliza. Es reversible — la hialuronidasa
(enzima) lo disuelve si hay complicación o el resultado no convence.

**Duración de la sesión.** 30–45 min (incluye anestesia tópica o
bloqueo nervioso si aplica).

**Inicio del efecto.** Visible inmediatamente, con hinchazón inicial
que enmascara el resultado real. Forma definitiva a los 7–14 días.

**Duración del efecto.** 9–12 meses, típicamente 12. Algunos labios
mantienen volumen residual más tiempo por hidratación inducida del
tejido.

**Recovery social.** 24–72 horas para que ceda hinchazón visible.
Cardenales potenciales hasta 2 semanas (especialmente en zona de
comisura). Recomendaciones post: frío local primeras 4–6 horas,
arnica tópica si la médica la indica, evitar alcohol y ejercicio
intenso 24h, no maquillar la zona 12h.

**Contraindicaciones absolutas.** Embarazo, lactancia, infección
herpética activa (herpes labial en curso), hipersensibilidad
conocida al HA o a la lidocaína (algunos preparados la traen
incluida).

**Contraindicaciones relativas.** Anticoagulación crónica, antecedente
de herpes labial frecuente (puede hacerse con profilaxis antiviral),
expectativa irreal ("labios tipo [celebridad]").

**Mitos frecuentes.**

- *"El ácido hialurónico se queda para siempre."* — Falso. El cuerpo
  lo metaboliza en meses. Lo que sí puede pasar: estimulación de
  colágeno endógeno en aplicaciones repetidas a largo plazo.
- *"Si no me gusta no se puede sacar."* — Falso. La hialuronidasa
  disuelve el filler en 24–48h.

**Cuándo derivar a consulta sin más conversación.** Antecedente
herpético activo; embarazo o lactancia; pedido de "tipo
[celebridad]"; alergia a lidocaína declarada (escalar al staff
para definir filler sin lidocaína).

---

## 3. Ácido hialurónico en surco nasogeniano

**Qué es.** Relleno del pliegue que va de la nariz a la comisura de
la boca, que se profundiza con la edad por pérdida de soporte del
tercio medio facial.

**Mecanismo general.** Mismo gel reticulado de HA, en una formulación
generalmente más densa o de mayor partícula que la usada en labios,
porque la zona requiere soporte estructural.

**Duración de la sesión.** 30–45 min.

**Duración del efecto.** 12–18 meses, según el tipo de filler y
características de la paciente.

**Recovery social.** 24–48 horas; cardenales hasta 2 semanas.

**Contraindicaciones.** Mismas que el filler labial.

**Mito frecuente.**
- *"Es lo mismo que el filler de labios."* — No. El producto
  específico (densidad, reticulación) varía según la zona; el médico
  lo selecciona.

---

## 4. Ácido hialurónico en ojeras / valle lágrima

**Qué es.** Relleno del hueco bajo el párpado inferior (valle
lágrima) que aparece o se profundiza con la edad y la pérdida de
volumen del compartimento graso medio.

**Mecanismo general.** HA muy fluido inyectado en plano profundo
(supraperióstico) para devolver volumen sin acumular hinchazón.

**Duración de la sesión.** 30–45 min.

**Duración del efecto.** 12–24 meses — en esta zona el HA dura más
porque hay menos movimiento muscular y menor degradación.

**Recovery social.** 24–72 horas. Cardenales son frecuentes en
esta zona por la cantidad de vasos pequeños.

**Riesgos específicos.** Efecto Tyndall (tono azulado si el filler
queda superficial); nódulos palpables; edema persistente. Estos
riesgos son **mayores que en otras zonas** y por eso es un
procedimiento que NO se hace sin experiencia específica del médico
en la zona. El agente NO promete resultado y enfatiza que la
elección de médico para esta zona es importante.

**Contraindicaciones.** Mismas que filler general. Adicional:
problemas dermatológicos activos en zona periorbital.

**Cuándo derivar a consulta sin más conversación.** Toda primera
consulta de ojeras debería ser presencial — la causa de la ojera
(pigmentaria, vascular, estructural) define si el filler es la
solución o si hay que combinar con otros tratamientos.

---

## 5. Hydrafacial premium

**Qué es.** Tratamiento facial en 3 pasos automatizado: limpieza +
exfoliación, extracción de impurezas, e hidratación + infusión de
sueros (vitamina C, ácido hialurónico, antioxidantes).

**Mecanismo general.** Vacío suave + soluciones acuosas con
principios activos aplicados con cabezal patentado. No es invasivo,
no requiere anestesia.

**Duración de la sesión.** 60 min.

**Resultado.** Piel inmediatamente más limpia, hidratada y con
brillo. Efecto acumulativo con sesiones mensuales — ideal como
mantenimiento.

**Recovery social.** Cero. Salida directa con maquillaje permitido.

**Contraindicaciones.** Dermatitis activa, rosácea aguda, infección
cutánea (herpes, impétigo), quemadura solar reciente.

**Mito frecuente.**
- *"Reemplaza a un peeling o láser."* — No. Hydrafacial es
  mantenimiento; peeling y láser son tratamientos de mayor
  profundidad indicados según objetivo clínico.

---

## 6. Peeling químico TCA superficial

**Qué es.** Aplicación tópica de ácido tricloroacético en
concentración 10–20% para descamación controlada de las capas
superficiales de la epidermis. Mejora textura, manchas
superficiales, líneas finas, opacidad.

**Mecanismo general.** El ácido coagula proteínas superficiales
provocando descamación a las 48–96h, que estimula recambio celular
y producción de colágeno.

**Duración de la sesión.** 30–45 min.

**Recovery social.** 5–7 días. Días 2–4: enrojecimiento + sensación
de tirantez; días 4–7: descamación visible. Recomendación: trabajar
desde casa o con maquillaje suave.

**Resultado visible.** Inmediato tras la descamación; mejora
acumulativa con protocolos de 3–4 sesiones cada 4–6 semanas.

**Contraindicaciones absolutas.** Isotretinoína últimos 6 meses
(altera cicatrización), embarazo, lactancia, infección herpética
activa, antecedente de queloides (relativo, requiere evaluación).

**Contraindicaciones relativas.** Fototipo V–VI (Fitzpatrick) →
mayor riesgo de hiperpigmentación post-inflamatoria; requiere
protocolo cuidadoso y protección estricta.

**Cuidados obligatorios post.** SPF 50 todos los días por al menos
4 semanas. NO exfoliantes mecánicos, NO retinoides 1 semana
post-peeling, NO sol directo 2 semanas.

**Mito frecuente.**
- *"Mientras más fuerte, mejor."* — Falso. Un peeling más profundo
  tiene más recovery + más riesgo. El médico estético elige la
  profundidad según objetivo y fototipo.

---

## 7. Láser CO2 fraccionado (full face)

**Qué es.** Tratamiento ablativo fraccionado que crea micro-columnas
de daño térmico controlado en la piel, dejando puentes de tejido
sano para acelerar recuperación. Indicado en cicatrices de acné,
líneas finas a moderadas, textura, manchas superficiales y poros.

**Mecanismo general.** Vaporización selectiva de tejido epidérmico
y dérmico superficial → respuesta de remodelación con producción
de colágeno y elastina nuevos durante las 8–12 semanas posteriores.

**Duración de la sesión.** 60–90 min (incluye anestesia tópica de
1h previa).

**Recovery social.** 5–10 días.

- Días 1–3: cara enrojecida, sensación de quemadura solar intensa.
- Días 3–7: descamación, costras finas, prurito.
- Días 7–10: eritema residual que se puede cubrir con maquillaje.

**Resultado visible.** Mejora inmediata de textura tras la
descamación; el efecto remodelador completo se aprecia a los 3
meses y se profundiza hasta los 6.

**Contraindicaciones absolutas.** Isotretinoína últimos 6 meses,
embarazo, lactancia, infección herpética activa (la cara con CO2
es un disparador clásico de reactivación herpética — profilaxis
antiviral obligatoria si antecedente). Fototipo VI debe evaluarse
individualmente (alto riesgo de hiperpigmentación).

**Contraindicaciones relativas.** Antecedente de queloides,
trastornos de coagulación, enfermedad autoinmune activa.

**Cuidados obligatorios post.** SPF 50, oclusivos hidratantes
indicados por la médica, NO retinoides ni ácidos por al menos 2
semanas, NO ejercicio intenso ni sauna 1 semana. Cualquier signo
de infección (pus, fiebre, dolor que crece) → red flag, llamada
inmediata y eventual urgencia.

**Mito frecuente.**
- *"En una sola sesión queda lista."* — Una sesión mejora pero el
  protocolo completo de cicatrices de acné suele requerir 2–3
  sesiones espaciadas.

**Cuándo derivar a consulta sin más conversación.** Antecedente
herpético frecuente; isotretinoína últimos 6 meses; fototipo
oscuro; expectativa de "borrar todo".

---

## 8. Depilación láser

**Qué es.** Eliminación progresiva del vello terminal usando láser
selectivo para la melanina del folículo piloso.

**Mecanismo general.** El láser emite una longitud de onda absorbida
por la melanina del folículo en fase anágena (de crecimiento). El
calor destruye el bulbo. Como solo ~20–30% de los folículos están
en fase anágena en un momento dado, se necesitan múltiples sesiones.

**Tipo de láser según fototipo.**

- Alexandrita (755 nm) — fototipos claros, alto contraste pelo/piel.
- Diodo (808 nm) — la mayoría de fototipos.
- Nd:YAG (1064 nm) — fototipos oscuros, profunda penetración, menor
  riesgo de hiperpigmentación.

(El agente NO recomienda un tipo específico — la médica/cosmetóloga
selecciona.)

**Protocolo típico.** 6–8 sesiones cada 4–8 semanas (la frecuencia
depende del ciclo del folículo en la zona).

**Duración de la sesión.** 15–60 min según zona (axilas: 10–15 min;
piernas completas: 45–60 min).

**Recovery social.** 24–48h. Eritema leve, sensación de calor
residual. Sin maquillaje recomendado en cara las primeras horas.

**Resultado esperable.** Reducción significativa del vello (70–90%)
tras el protocolo completo. NO se garantiza eliminación total.
Sesiones de mantenimiento anuales pueden ser necesarias.

**Contraindicaciones absolutas.** Embarazo (precaución general por
ausencia de estudios, no por daño documentado), bronceado reciente
(últimas 2 semanas), uso de fotosensibilizantes (algunos
antibióticos, anticonceptivos hormonales recientes — relativo).

**Contraindicaciones relativas.** Tatuajes en zona (riesgo de
quemadura del pigmento — se cubren o se evitan), antecedente de
herpes en zona, vello cano (no responde al láser).

**Mito frecuente.**
- *"Una sola sesión basta."* — Falso. El protocolo es obligatoriamente
  de varias sesiones por el ciclo del folículo.
- *"Funciona igual con vello cano."* — Falso. El láser depende de
  la melanina; los pelos blancos no responden.

---

## 9. Radiofrecuencia corporal

**Qué es.** Aplicación de energía electromagnética de alta frecuencia
que genera calor controlado en dermis profunda e hipodermis para
tensar tejido y mejorar contorno corporal sin cirugía.

**Mecanismo general.** Calor a 40–45°C en dermis estimula
contracción inmediata del colágeno + remodelación progresiva en
semanas. NO destruye grasa; mejora calidad de piel y tensa
ligeramente.

**Duración de la sesión.** 45 min por zona.

**Protocolo típico.** 8–10 sesiones, una por semana.

**Recovery social.** Cero. Eritema leve que cede en horas.

**Resultado esperable.** Mejora modesta de firmeza y celulitis
superficial. NO es alternativa a cirugía para flacidez significativa.
Mantenimiento mensual recomendado para sostener resultado.

**Contraindicaciones absolutas.** Marcapasos o cualquier dispositivo
electrónico implantado, embarazo, implantes metálicos en zona de
tratamiento, infección activa o lesión cutánea.

**Contraindicaciones relativas.** Enfermedad autoinmune con
fotosensibilidad, anticoagulación crónica.

**Mito frecuente.**
- *"Elimina la grasa."* — Falso. La radiofrecuencia NO destruye
  adipocitos en el rango clínico estándar; trabaja sobre dermis y
  hipodermis superficial.

---

## 10. Criolipólisis

**Qué es.** Reducción no quirúrgica de grasa localizada por
exposición controlada al frío (~-10°C) que destruye selectivamente
adipocitos sin dañar piel ni tejidos adyacentes.

**Mecanismo general.** Los adipocitos son más sensibles al frío
que otros tejidos. El protocolo induce apoptosis (muerte celular
programada) en una fracción de los adipocitos de la zona tratada;
el sistema linfático los elimina progresivamente en 8–12 semanas.

**Duración de la sesión.** 60 min por zona (puede repetirse en
diferentes zonas en una visita).

**Protocolo típico.** 1–2 sesiones por zona, separadas 8–12 semanas
si se hace una segunda.

**Recovery social.** 24–72 horas. Eritema, hinchazón, sensibilidad,
adormecimiento transitorio en la zona tratada — normales hasta 2
semanas. Cardenales posibles.

**Resultado esperable.** Reducción de 20–25% del grosor del pliegue
graso tratado, visible a las 8–12 semanas. NO es para pérdida de
peso — es para contorno localizado. La paciente DEBE tener IMC
razonable (idealmente <30) y grasa pellizcable en la zona.

**Riesgo conocido a discutir abiertamente.** Hiperplasia adiposa
paradójica (PAH): aumento de la grasa en zona tratada en lugar de
disminución. Incidencia baja (~1:4.000 según reportes recientes,
mayor en hombres que en mujeres). Es tratable con liposucción.
La paciente debe saberlo antes de la sesión — la cosmetóloga lo
informa en el consentimiento.

**Contraindicaciones absolutas.** Crioglobulinemia, hemoglobinuria
paroxística por frío, urticaria al frío, hernia abdominal en zona
de tratamiento (abdomen).

**Contraindicaciones relativas.** Anticoagulación crónica, neuropatía
periférica, lesión cutánea reciente.

**Mito frecuente.**
- *"Es para bajar de peso."* — Falso. Es contorno localizado, no
  herramienta de peso. La paciente con sobrepeso significativo
  necesita evaluación médica integral.

---

# Cirugía estética — procedimientos quirúrgicos

> Para todos los procedimientos quirúrgicos: el agente agenda
> **consulta**, no la cirugía. La fecha de quirófano la fija
> {clinical.titular_name} con la paciente en consulta presencial.
> La consulta tiene un costo (USD 80) acreditable al procedimiento.
> Se requiere seña del 30% para reservar fecha de quirófano.

## 11. Rinoplastia

**Qué es.** Cirugía que modifica la forma y/o función de la nariz.
Estética cuando el objetivo es cosmético; funcional cuando además
corrige problemas respiratorios (desviación septal).

**Técnicas.** Abierta (incisión externa en columela) o cerrada
(todas las incisiones internas). La elección depende del cambio
buscado, anatomía de la paciente y preferencia del cirujano.

**Anestesia.** General. Internación generalmente del día (egreso
mismo día o a la mañana siguiente).

**Duración.** 2–4 horas según complejidad.

**Recovery social.** 2–3 semanas (cardenales periorbitales, edema
nasal, férula los primeros 7–10 días).

**Recovery completo.** El edema final tarda 12 meses en reabsorberse;
la "punta" es la última zona en estabilizarse. Por eso el resultado
"final" se evalúa al año.

**Resultado esperable.** Cambio armónico de proporciones faciales
acordado en consulta. Cada nariz responde distinto a la cirugía
según grosor de piel, soporte cartilaginoso y cicatrización
individual.

**Contraindicaciones absolutas.** Trastorno hemorrágico no
compensado, infección activa en zona, expectativa irreal evaluada
por el cirujano (dismorfia corporal).

**Contraindicaciones relativas.** Tabaquismo activo (alto riesgo
de complicaciones de cicatrización — se solicita suspensión 4
semanas antes y 4 después), anticoagulación crónica,
isotretinoína últimos 6 meses (relativo, depende del cirujano).

**Mito frecuente.**
- *"Te dejan la nariz exacta a la de [celebridad]."* — Falso. Cada
  cara es única; la rinoplastia busca armonía facial individual.
  (Skill `medical-claims-discipline` aplica.)
- *"En una semana ya estoy lista."* — Falso. Recovery social mínimo
  2 semanas; resultado final 12 meses.

---

## 12. Mamoplastia de aumento (implante)

**Qué es.** Colocación de prótesis mamarias para aumentar volumen
y/o corregir asimetrías.

**Tipos de implante.** Silicona cohesiva o solución salina.
Diferentes perfiles (bajo, moderado, alto) y formas (redondo,
anatómico). La elección la define la cirujana en consulta según
anatomía y objetivo.

**Planos.** Subglandular (sobre el músculo), submuscular (debajo),
o dual plane (mixto). Cada uno tiene ventajas según anatomía y
actividad de la paciente.

**Anestesia.** General. Internación generalmente del día.

**Duración.** 1.5–2.5 horas.

**Recovery social.** 4–6 semanas. Primeras semanas:
brassiere quirúrgico 24/7, restricción de movimiento de brazos,
dolor manejable con analgésicos pautados.

**Recovery completo.** 3–6 meses (los implantes "bajan" a su
posición final en este tiempo).

**Resultado esperable.** Aumento de volumen + mejora de forma.
La cicatriz final es discreta (areolar, surco submamario, o
axilar según vía).

**Contraindicaciones absolutas.** Enfermedad mamaria activa
(cáncer, sospecha en estudio), embarazo, lactancia (esperar 6
meses post-destete), expectativa irreal.

**Contraindicaciones relativas.** Tabaquismo activo, obesidad
significativa, enfermedad autoinmune mal controlada, plan de
embarazo próximo (el embarazo cambia la mama y puede afectar
resultado).

**Conversación obligatoria en consulta.** Tipo y tamaño del
implante, plano de colocación, vía de incisión, expectativa de
resultado, plan de seguimiento (los implantes requieren control
ecográfico/RMI cada 2–3 años según marca).

**Mito frecuente.**
- *"Los implantes hay que cambiarlos cada 10 años."* — Inexacto.
  Las marcas actuales no tienen "vida útil" fija; se cambian si
  hay complicación (ruptura, contractura, cambio de tamaño
  deseado). Sí hay que controlarlos periódicamente.

---

## 13. Mastopexia (lifting de mama)

**Qué es.** Cirugía que levanta el complejo areola-pezón y elimina
exceso de piel para corregir ptosis (caída) mamaria. Puede combinarse
con implante (mastopexia con aumento) si además se desea volumen.

**Técnicas.** Periareolar, vertical ("lollipop"), T invertida (la
clásica). Más caída → cicatriz más larga. La cirujana elige según
grado de ptosis.

**Anestesia.** General. Internación del día.

**Duración.** 2–3 horas.

**Recovery social.** 4–6 semanas.

**Resultado esperable.** Mamas elevadas, areola reposicionada,
contorno mejorado. Cicatriz final visible (ineludible) pero
mejorable en el tiempo con cuidados.

**Contraindicaciones.** Iguales a mamoplastia de aumento.

**Mito frecuente.**
- *"No deja cicatriz."* — Falso. La mastopexia siempre deja
  cicatriz; la diferencia entre técnicas es la longitud y forma,
  no la ausencia.

---

## 14. Liposucción (3 zonas)

**Qué es.** Aspiración mecánica de grasa subcutánea localizada
para mejorar contorno en zonas como flancos, abdomen, espalda
("rollitos"), cara interna y externa de muslos, brazos.

**Técnicas.** Lipo tumescente, asistida por vibración (PAL),
asistida por láser, asistida por ultrasonido (VASER). Cada técnica
tiene perfil de uso y la cirujana elige según caso.

**Anestesia.** General o local con sedación según extensión.
Ambulatorio o con 1 noche de internación según volumen extraído.

**Duración.** 1.5–3 horas según número de zonas.

**Recovery social.** 3–4 semanas. Faja compresiva 6–8 semanas (24/7
primeras 3 sem, gradual reducción). Drenajes linfáticos manuales
desde semana 1.

**Recovery completo.** 6 meses (la fibrosis y edema residual
mejoran gradualmente).

**Resultado esperable.** Mejora de contorno en zonas tratadas. NO
es herramienta para pérdida de peso global; la balanza puede no
cambiar significativamente.

**Riesgos conocidos.** Irregularidades del contorno, fibrosis,
edema persistente, asimetría, depresiones, seroma. La buena
técnica + uso correcto de la faja + drenajes minimizan pero no
eliminan estos riesgos.

**Contraindicaciones absolutas.** Trastorno hemorrágico, IMC >35
(requiere protocolo especial o pérdida previa), enfermedad
cardiopulmonar significativa.

**Contraindicaciones relativas.** Tabaquismo activo (suspensión 4
sem antes/después), anticoagulación crónica, diabetes mal
controlada.

**Mito frecuente.**
- *"La grasa vuelve si engordo."* — Parcialmente cierto. Los
  adipocitos extraídos no regresan, pero los que quedan pueden
  hipertrofiar. La paciente con cambios de peso significativos
  postoperatorios puede ver redistribución a zonas no tratadas.

---

## 15. Lipoescultura HD (alta definición)

**Qué es.** Liposucción combinada con técnica de marcado para
definir contornos musculares subyacentes (especialmente abdomen y
espalda en hombres; cintura y línea alba en mujeres).

**Cómo se diferencia de la lipo simple.** Aspiración más superficial
y selectiva, dejando grasa estratégicamente para resaltar relieve
muscular natural.

**Recovery + cuidados.** Iguales a lipo simple, pero el resultado
estético depende mucho más de la adherencia al protocolo
post-quirúrgico (faja, drenajes, alimentación, ejercicio).

**Resultado esperable.** Definición visible de musculatura
subyacente. Requiere que la paciente tenga base muscular previa.

**Contraindicaciones.** Iguales a lipo. Adicional: paciente sin
base muscular puede no tener buen resultado HD — la consulta
define si es candidata.

---

## 16. Abdominoplastia

**Qué es.** Cirugía que resecciona piel y grasa del abdomen,
plica los músculos rectos (diastasis si aplica) y reubica el
ombligo. Indicada en pacientes con piel sobrante post embarazo o
post pérdida de peso significativa.

**Técnicas.** Completa (cicatriz horizontal completa cadera a
cadera), mini-abdominoplastia (solo abdomen inferior, cicatriz
corta).

**Anestesia.** General. 1 noche de internación.

**Duración.** 2–4 horas.

**Recovery social.** 4–6 semanas. Faja compresiva 6–8 semanas.
Movilización temprana indicada (caminar). Restricción de cargar
peso 6 semanas. Drenajes 1–2 semanas según protocolo.

**Recovery completo.** 6 meses.

**Resultado esperable.** Abdomen plano + cintura definida +
ombligo reposicionado. Cicatriz horizontal permanente, posicionada
para ocultarse bajo ropa interior.

**Riesgos conocidos.** Seroma, infección, dehiscencia, problemas
de cicatrización (especialmente en fumadoras — el riesgo de
necrosis del colgajo es real), tromboembolismo (riesgo elevado en
cirugía abdominal mayor, profilaxis obligatoria), asimetría del
ombligo.

**Contraindicaciones absolutas.** Tabaquismo activo no suspendido,
obesidad mórbida sin pérdida previa, plan de embarazo próximo,
enfermedad cardiopulmonar significativa, trastorno hemorrágico.

**Mito frecuente.**
- *"Es para bajar de peso."* — Falso. Es para piel sobrante; la
  paciente ya debe haber alcanzado un peso estable.

---

## 17. BBL (Brazilian Butt Lift / lipotransferencia glútea)

**Qué es.** Procedimiento combinado: liposucción de zonas dadoras
(cintura, flancos, espalda) + injerto de grasa propia en glúteo
para aumentar volumen y mejorar forma sin implante.

**Mecanismo.** La grasa extraída se procesa y se reinyecta en plano
subcutáneo glúteo. Una parte de las células injertadas se reabsorben
en 3–6 meses (40–60% según múltiples factores); lo que prende es
permanente.

**Anestesia.** General. 1 noche de internación.

**Duración.** 3–4 horas.

**Recovery social.** 4 semanas. **Restricción crítica: no sentarse
directamente sobre el glúteo durante 2 semanas** (almohada en
isquión obligatoria; usar el "no sit" pillow). Dormir boca abajo o
de lado las primeras 4 semanas. Faja compresiva en zona dadora 6–8
semanas.

**Recovery completo.** 6 meses (estabilización del injerto).

**Resultado esperable.** Aumento + redondez glútea + cintura
marcada (por la lipo combinada). Volumen final visible a los 3–6
meses.

**Riesgo grave y obligatorio a discutir abiertamente.** Embolia
grasa por inyección de grasa en plano intramuscular (con riesgo
de embolia pulmonar fatal). El riesgo se ha reducido drásticamente
con la adopción de la técnica subcutánea exclusiva + uso de
ultrasonido intraoperatorio. ASPS/ASAPS emitieron recomendaciones
formales: solo plano subcutáneo, NO intramuscular; uso de cánulas
romas y rígidas; uso de ultrasonido cuando esté disponible.

La paciente DEBE preguntar al cirujano:
1. ¿Usa exclusivamente plano subcutáneo?
2. ¿Usa ultrasonido intraoperatorio?

Si la paciente pregunta por el BBL, el agente debe **mencionar
explícitamente este riesgo** y recomendar que confirme estas dos
prácticas con la cirujana en consulta. No es alarmismo — es
estándar de buenas prácticas internacional.

**Contraindicaciones absolutas.** IMC <22 (poca grasa dadora para
buen injerto), enfermedad cardiopulmonar, trastorno hemorrágico,
embarazo planeado próximo, paciente que no puede cumplir el
protocolo de no-sit (trabajo que exige estar sentada, dificultad
para acomodarse fuera de la silla).

**Contraindicaciones relativas.** Tabaquismo activo (afecta prendimiento
del injerto), diabetes mal controlada.

**Mito frecuente.**
- *"Es seguro como cualquier cirugía estética."* — Es una cirugía
  con riesgos específicos serios que el cirujano debe explicar
  abiertamente. La paciente que pregunta sin información debe
  recibirla con franqueza.

---

## 18. Blefaroplastia superior

**Qué es.** Cirugía que reseca exceso de piel y/o grasa del párpado
superior. Indicada cuando la piel cae sobre el ojo, dando aspecto
cansado o limitando campo visual.

**Anestesia.** Local con sedación (no requiere general en la mayoría
de los casos).

**Duración.** 45–90 min.

**Recovery social.** 1 semana (cardenales periorbitales, edema,
suturas a retirar al día 5–7).

**Recovery completo.** 3 meses (estabilización del párpado).

**Resultado esperable.** Mirada más abierta, descansada. La cicatriz
queda oculta en el pliegue palpebral natural.

**Contraindicaciones absolutas.** Ojo seco severo (la blefaroplastia
puede empeorarlo), glaucoma no controlado, hipertiroidismo activo
con afectación ocular (oftalmopatía de Graves).

**Contraindicaciones relativas.** Asimetría facial significativa
(requiere planificación), uso de anticoagulantes.

**Mito frecuente.**
- *"Cambia la forma de los ojos."* — Falso. La blefaroplastia
  superior elimina exceso, no cambia la forma del ojo. Eso
  pertenece a la cantopexia/cantoplastia.

---

# Secciones transversales

## Contraindicaciones absolutas globales

Estas aplican a casi todos los procedimientos de la KB. Si la
paciente declara alguna, el agente refusa el agendamiento del
procedimiento específico y deriva a consulta para evaluación:

- **Embarazo y lactancia** — contraindica todos los inyectables,
  cirugías electivas, peelings con principios activos, láser
  ablativo, isotretinoína. Tratamientos seguros: faciales manuales
  suaves, hydrafacial sin retinoides.
- **Trastorno hemorrágico no compensado** — contraindica cirugía
  e inyectables.
- **Infección activa local o sistémica** — contraindica
  procedimientos invasivos hasta resolución.
- **Isotretinoína últimos 6 meses** — contraindica láser ablativo,
  peelings medios/profundos, dermoabrasión. NO contraindica
  hydrafacial, faciales, depilación láser (relativo).
- **Trastorno dismórfico corporal evidente** — derivar a consulta;
  la cirujana evalúa con criterio clínico.

## Edad mínima

- **18 años para procedimientos electivos sin consentimiento
  parental.**
- 16–17 con consentimiento de padre/madre/tutor — solo casos
  acotados (asimetría significativa, deformidad post-traumática).
  La cirujana evalúa.
- <16 — solo reconstructivos, fuera del alcance de la clínica.

## Tabaquismo

Restricción universal en cirugía estética: suspender 4 semanas
antes y 4 después. La nicotina reduce flujo sanguíneo de los
colgajos cutáneos — alto riesgo de necrosis, especialmente en
abdominoplastia, mamoplastia, lifting facial y BBL.

El agente NO juzga; informa la recomendación y deriva a consulta
para definir plan.

## Anticoagulación crónica

NO contraindica absolutamente, pero requiere coordinación con el
médico clínico que la indicó. La cirujana define con la paciente y
su clínico si se suspende, durante cuántos días, y con qué puente
si aplica. El agente NUNCA recomienda suspender medicación — eso
es ámbito clínico.

## Expectativas irreales

Frases típicas que el agente debe identificar y derivar a consulta
sin agendar de inmediato:

- "Quiero quedar igual a [celebridad]."
- "Me opero para que mi pareja vuelva."
- "Quiero borrar la cicatriz totalmente."
- "Quiero quedar perfecta."

El agente reconoce con empatía, manage la expectativa con honestidad,
y deriva a la consulta donde la cirujana evalúa caso por caso. La
skill `medical-claims-discipline` y la `escalation-policy` aplican —
si la señal emocional es fuerte, escalar (skill `escalation-policy`).

## Cuidados pre-quirúrgicos generales (cualquier cirugía)

Información que el agente puede compartir como pauta general:

- **Estudios pre-operatorios**: hemograma, coagulación, química
  sanguínea, función renal y hepática, ECG si >40 años o
  comorbilidad. La cirujana define el panel exacto.
- **Suspensión de fármacos**: aspirina, AINEs, anticoagulantes,
  suplementos con vitamina E, ginkgo, ajo, ginseng — 10–14 días
  antes (siempre coordinado con el médico clínico).
- **Ayuno pre-anestesia**: típicamente 8h sólidos, 2h líquidos
  claros — el anestesista define.
- **Acompañante para egreso obligatorio** en toda cirugía con
  anestesia general o sedación.
- **Suspensión de tabaco** 4 semanas antes (regla universal).

El agente NO indica fármacos a suspender ni dosis — solo informa
la pauta general y deriva a consulta donde se define cada caso.

## Cuidados post-procedimiento — pauta general

Indicaciones genéricas que el agente puede recordar a la paciente
tras procedimiento medspa (NO reemplazan las indicaciones
específicas de la médica/cosmetóloga):

- **Inyectables**: frío local primeras horas, evitar masaje en zona
  4h, evitar acostarse boca abajo 4–6h, sin alcohol ni ejercicio
  intenso 24h, sin maquillaje 12h.
- **Láser / peelings**: SPF 50 obligatorio 4 semanas, sin sol
  directo 2 semanas, sin retinoides ni ácidos 1–2 semanas, sin
  ejercicio intenso 24–72h según procedimiento.
- **Cirugía**: faja según indicación, drenajes según indicación,
  movilización temprana, no cargar peso, no fumar, dormir en
  posición indicada por cirujana.

Cualquier signo fuera de la ventana esperable → skill
`post-op-symptom-triage` aplica.

---

# Verificación interna del agente

Cuando el agente está por responder una consulta educativa, revisa:

1. ¿La pregunta cae en uno de los 18 procedimientos del catálogo
   cubiertos por esta KB? → usar la entrada correspondiente.
2. ¿La pregunta es sobre un procedimiento NO en catálogo (ej.
   trasplante capilar, lifting facial mayor)? → no inventar
   conocimiento; explicar que no está en el catálogo y ofrecer
   referencia genérica o cerrar con calidez (skill
   `medical-claims-discipline`).
3. ¿La respuesta requiere dar una dosis, una marca, una promesa,
   una comparación? → las 5 skills disciplinarias aplican antes
   que la KB.
4. ¿La respuesta cierra con "cada caso es individual — lo confirmás
   en la consulta con {clinical.titular_name}"? → siempre debe
   cerrar así.

## Cuándo NO usar esta KB

- Síntomas post-procedimiento de una paciente real → skill
  `post-op-symptom-triage` decide nivel.
- Pedido de fotos → skill `before-after-photos`.
- Pedido de información clínica que excede educación general
  (interacciones farmacológicas específicas, dosis, contraindicaciones
  individuales complejas) → derivar a consulta.
- Cuando la paciente describe expectativa irreal o señal emocional
  fuerte → empatía + derivar; KB no resuelve eso.

## Ejemplo de respuesta correcta usando la KB

> Paciente: "¿Qué es el BBL exactamente y es seguro?"
> Agente: "El BBL combina lipo de zonas como cintura y espalda
> con injerto de grasa propia en glúteo — sin implante. La grasa
> que prende es permanente; un 40–60% se reabsorbe en los primeros
> meses, por eso el resultado final se ve a los 6 meses. Recovery
> social 4 semanas y, atención, no sentarse 2 semanas directo —
> hay que usar almohada especial.
>
> Sobre la seguridad, te cuento abierto: el BBL tuvo en años pasados
> un riesgo serio de embolia grasa cuando la grasa se inyectaba en
> el músculo. Hoy las sociedades internacionales (ASPS, ASAPS)
> recomiendan exclusivamente plano subcutáneo y uso de ultrasonido
> intraoperatorio. Cuando hagas la consulta, te recomiendo
> preguntarle a {clinical.titular_name} explícitamente: ¿usás plano
> subcutáneo exclusivo? ¿usás ultrasonido? Son las dos preguntas
> que marcan la seguridad real.
>
> Cada caso es individual — lo confirmás en la consulta con
> {clinical.titular_name}."
