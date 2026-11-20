import os

__version__ = "0.1.0"

# Spec 065 (research.md §D13): LiteLLM lee su mapa de modelos al importarse. Fijarlo aquí,
# antes de que nada lo importe, hace que use el local en todos los procesos que cargan
# ``nexus_api`` (la API y el worker); ``core.litellm_map`` registra encima nuestras entradas.
os.environ.setdefault("LITELLM_LOCAL_MODEL_COST_MAP", "True")
