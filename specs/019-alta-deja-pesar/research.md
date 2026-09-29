# Fase 0 · Investigación — el alta deja de pesar

Tres preguntas, tres comprobaciones **ejecutadas**. Las tres cambiaron el plan,
y una cambió la propia spec.

---

## 1. ¿Cuántos campos necesita de verdad cada plantilla?

**Decisión**: el alta pide *exactamente* los campos que el renderizador exige
para la plantilla elegida, calculados de la plantilla y no de una lista escrita
a mano.

**Cómo se comprobó**: `research-probe.py`, en este mismo directorio. Carga las
trece semillas, intenta renderizar con los campos vacíos y va añadiendo los que
el renderizador exige, uno por excepción, hasta que renderiza.

```
plantilla                 imprescindibles
aesthetic_clinic_v1                    12
barbershop_v1                           2   tenant.address tenant.business_hours_label
beauty_salon_v1                         2
clinica_v1                              2
cobranza_v1                             0
dental_v1                               2
generic_v1                              2
inventario_v1                           0
medspa_v1                               2
nail_studio_v1                          2
restaurante_v1                          2
spa_v1                                  2
woocommerce_sales_v1                    0
```

**Lo que esto cambia**: la spec decía «tres datos y ningún campo de plantilla».
Era falso para diez de trece. Se corrigió antes de planificar: el alta pide
cuatro campos en diez plantillas, dos en tres, y doce en una.

**Y lo que revela**: no son trece problemas distintos. Diez plantillas exigen
**los mismos dos campos** —dirección y horario—, porque casi todos los prompts
verticales los mencionan. El caso peor es uno solo.

**Alternativa descartada**: dar valores por defecto a los doce de
`aesthetic_clinic_v1`. Arreglaría el caso peor y es lo correcto a largo plazo,
pero se hace en la semilla de la API y en la KB, no en la consola.

---

## 2. ¿Qué pasa si un campo se queda vacío?

**Hallazgo**: `render_seed_template` levanta `SeedTemplatePlaceholderMissing`
cuando un `{a.b.c}` no tiene valor ni valor por defecto. **No degrada: rompe.**

**Por qué importa**: convierte «¿sale un agente coherente?» —un juicio de
calidad, discutible— en «¿renderiza?» —una comprobación automática—. El número
de la tabla de arriba es fiable porque lo dice el propio código, no yo mirando
prompts.

Es también la razón de que el supuesto más arriesgado de la spec dejara de ser
un supuesto antes de escribir una línea de código.

---

## 3. ¿Qué puede hacer el Companion en el alta?

**Hallazgo**: las 41 herramientas de su catálogo son de lectura, y hay un test
que lo recorre y lo exige. Es la capa 2 del aislamiento (CO-02 §5). **El
Companion no puede crear el cliente**, y darle esa capacidad sería una decisión
de seguridad con su propio ADR, no un cambio de interfaz.

**Decisión**: su papel es **redactar**. Lee `console.list_templates`, propone
plantilla y valores, y la consola los aplica al formulario **marcados como
propuestos**. El partner acepta, cambia o descarta; el clic que escribe es suyo.

**Consecuencia para el diseño**: la propuesta no puede llegar como un alta
hecha ni como un estado «creando». Llega como contenido de campos, y la
pantalla tiene que distinguir lo propuesto de lo escrito — R5.2, con test.

**Alternativa descartada**: que el panel del Companion rellene la página. Exige
que el panel escriba en la pantalla del alta, un acoplamiento nuevo entre dos
piezas que hoy no se conocen. El owner eligió la caja dentro del alta
(aclaración del 2026-09-28).

---

## 4. ¿La consola ya sabe cuáles son imprescindibles?

**Sí, y los enseña todos igual.** `SeedPlaceholder` trae `required: boolean` y
el asistente lo usa para validar (`missingPlaceholders`), pero **pinta también
los opcionales**. Medido en la pantalla: la plantilla marcada por defecto
enseña 23 campos de los que 12 van marcados obligatorios — exactamente los 12
que el renderizador exige.

**Lo que esto abarata**: la iteración 1 no necesita ningún dato nuevo de la API.
`requiredPlaceholders()` es un filtro sobre lo que ya llega. El trabajo es
decidir **no enseñar** once campos, no ir a buscar una información que falte.

---

## Dependencias nuevas

**Ninguna.** Ni de npm ni de Python. `T-LIC` lo comprueba al cerrar cada
iteración.
