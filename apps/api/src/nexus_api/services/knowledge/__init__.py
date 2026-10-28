"""El conocimiento en dos capas — spec 047, historia 22 (requisitos 37 y 38;
research D14).

- ``layers``: qué fuentes ve cada agente (las del negocio y las suyas, nunca las
  de un hermano), fragmentar e indexar, quitar con 10 minutos para deshacer y la
  revisión de cada capa.
- ``retrieval``: lo que entra en el turno (entero si cabe; si no, búsqueda híbrida
  exacta por cliente y capa) y sus fuentes.
- ``teach``: «Enseñar», con su alcance, que se aplica al momento y vuelve a pasar
  las pruebas afectadas.
- ``embeddings``: el modelo de embeddings, si lo hay.
"""
