"""La certificación de despliegues (spec 047, T143 y T144).

- :mod:`battery`: la batería común en español, versionada (``battery_v1/``).
- :mod:`metrics`: lo que mide (pass^3, repreguntas, afirmaciones sin fuente,
  argumentos válidos, cambio de idioma, latencias) y la nota.
- :mod:`runner`: ejecutarla por clase y por agente, con un juez de otra familia
  y en lotes de un solo cliente.

Dónde se guarda y cuándo caduca: ``nexus_api.services.certification``.
"""
