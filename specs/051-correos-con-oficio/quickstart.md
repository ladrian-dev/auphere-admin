# Guía de validación: Correos con oficio

## 1 · En local: nada sale, todo se registra

```bash
docker compose up -d
curl -s -X POST localhost:8000/console/password-reset \
  -H 'content-type: application/json' -d '{"email":"<una cuenta de tu semilla>"}'
docker compose logs api | grep email.suppressed
```

**Esperado**: una línea con `kind=password_reset`, `template=auphere-password-reset-es`, el destinatario, el asunto y `links={"RESET_URL": "http://localhost:3000/reset/…"}`. Con ese enlace se completa el restablecimiento. No hay ninguna llamada a `api.resend.com`.

## 2 · Producción no arranca en modo registro

```bash
cd apps/api && NEXUS_ENVIRONMENT=production NEXUS_EMAIL_DELIVERY=log uv run python -c "from nexus_api.config import get_settings; get_settings()"
```

**Esperado**: falla y el mensaje nombra `NEXUS_EMAIL_DELIVERY`. La prueba unitaria `test_email_delivery_mode.py` cubre lo mismo junto con las demás guardias de producción.

## 3 · Las plantillas existen y cuadran con el código

```bash
cd apps/api && NEXUS_RESEND_API_KEY=<clave> uv run python scripts/check_email_templates.py
```

**Esperado**: 39 alias en verde. Si se quita una variable de una plantilla en el panel, la siguiente ejecución falla y nombra la plantilla y la variable.

## 4 · En staging, tras desplegar

1. Recorrer alta, invitación de equipo y restablecimiento: **los tres correos llegan**.
2. Provocar un aviso de saldo: en Resend → Emails **no** aparece; en el registro sí.
3. En CloudWatch Logs Insights, sobre los grupos de la API y del worker de staging:

   ```
   fields @timestamp, kind, template, subject, links.0
   | filter event = "email.suppressed"
   | sort @timestamp desc
   ```

   Aparece una entrada por correo, con su enlace.

## 5 · Las pruebas

```bash
cd apps/api && uv run pytest tests/unit/test_email_delivery_mode.py tests/unit/test_email_send_template.py \
  tests/unit/test_email_catalog.py tests/unit/test_email_no_inline_html.py \
  tests/isolation/test_55_email_owner_tagging.py -x
./scripts/verify.sh
```
