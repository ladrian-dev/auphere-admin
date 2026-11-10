# Fix: las pruebas esperan lo que nadie mide

- `judge.CHECKABLE_STATE`: lo único que se puede esperar. `firm_state` lo aplica al comprobar, así que lo ya guardado deja de dar rojos falsos, y `clean_state` al guardar.
- Los dos prompts dicen las claves. Lo que el modelo invente se quita y se cuenta (`builder.tests.state_dropped`).
- Una persona que escribe otra clave por la API recibe `422 unknown_state_key`.
- El juez recibe la ficha en `<ficha>`, pasada por `inert` como el resto.
- Los fallos de estado se dicen en palabras.
- Un disparador en palabras se guarda como `{custom}` y, sin ninguno utilizable, se aplican los de por defecto.
