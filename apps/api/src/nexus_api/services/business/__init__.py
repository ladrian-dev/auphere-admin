"""La ficha del negocio — spec 047, ola 2 (``plan.md`` §Ola 2, research D3).

La fuente de verdad del negocio son tablas por cliente (``db/models/business.py``);
el ClientSpec es su vista tipada. Aquí viven los servicios que la escriben:

- ``links``: la detección de enlaces del alta, una función pura;
- ``profile``: lo básico, lo que el alta deduce (país, zona, monedas) y las
  sugerencias de nicho;
- ``sections``: la revisión y el estado de cada sección, y ``content_rev``;
- ``reader``: la lectura de la web y de las redes en segundo plano (el trabajo
  ``client_read`` del worker), con lo leído como **dato y nunca instrucción**
  (§III).

La ficha **nunca** se escribe en el grafo (garantía 3,
``tests/isolation/test_46_business_profile_not_in_kg.py``).
"""
