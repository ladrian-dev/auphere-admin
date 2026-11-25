# Contrato: editar una plantilla

Lo mismo en la consola y en el panel. Las dos rutas llaman a la misma función de servicio.

```
PUT /console/clients/{ref}/channels/whatsapp/templates/{name}/{language}   # permiso channels:write
PUT /admin/tenants/{tenant_id}/whatsapp/templates/{name}/{language}        # operador
```

## Petición — `TemplateEditIn`

```json
{
  "version": "3f9a0c1d2b4e5f60",
  "confirm": false,
  "category": "UTILITY",
  "header_text": null,
  "body_text": "Hola {{nombre}}, te esperamos {{cuando}}.",
  "footer_text": null,
  "buttons": [],
  "examples": {"nombre": "Camila", "cuando": "el jueves a las 20:30"}
}
```

## Respuestas

| Código | `detail` | Cuándo |
|---|---|---|
| 200 | `TemplateEditOut` con `changed: true` | Meta aceptó; `status` es el que devuelve la lectura posterior |
| 200 | `TemplateEditOut` con `changed: false` | El contenido no cambia; no se llama a Meta (3.4) |
| 400 | `invalid template name` | `name` no cumple `^[a-z0-9_]{1,512}$` |
| 404 | `{"code": "template_not_found"}` | No existe ese nombre e idioma en la cuenta de la sesión (8.2) |
| 409 | `{"code": "template_changed"}` | La huella no coincide (7.1) |
| 409 | `{"code": "not_editable", "blocker": "<código>"}` | La plantilla tiene un bloqueo (3.1, 3.2) |
| 409 | `{"code": "confirmation_required", "reasons": [{"kind": "approved"}, {"kind": "queued_sends", "count": 3}]}` | Falta `confirm: true` (2.2, 5.1) |
| 409 | `{"code": "whatsapp_not_connected"}` | Sin credenciales de Meta (como hoy al crear o borrar) |
| 422 | `{"code": "category_locked"}` | Categoría distinta en una aprobada (2.3) |
| 422 | `{"code": "system_variables", "missing": [...], "extra": [...]}` | Plantilla de sistema con variables que no valen (4.2, 4.3) |
| 422 | `{"code": "missing_examples", "variables": [...]}` | Variable sin ejemplo (9.4) |
| 422/429/502 | `{"code": "meta_rejected", "meta_code": <int>, "meta_subcode": <int\|null>, "user_message": "<error_user_msg de Meta>\|null"}` | Meta rechaza la edición (1.6, 2.4). `user_message` va a la pantalla, **nunca** a los registros (8.5) |

## Cliente de Meta

```
MetaClient.edit_template(*, template_id, access_token, components, category=None, parameter_format=None) -> dict
POST /{template_id}  {"components": [...], "category"?: ..., "parameter_format"?: "NAMED"}
```

## Lista (campos añadidos a cada fila)

```json
{
  "edit_blocker": null,
  "draft": {"category": "UTILITY", "header_text": null, "body_text": "…", "footer_text": null, "buttons": [], "examples": {}},
  "version": "3f9a0c1d2b4e5f60",
  "system_variables": {"mode": "exact", "variables": ["nombre", "negocio", "cuando"]}
}
```
