"""Enmascarado de PII — la capa que faltaba con nombre propio (CO-07 · §24).

De las cinco barandillas que AgentKit nombra (enmascarado de PII, detección
de *jailbreak*, moderación, comprobación contra la base de conocimiento y
pasos de aprobación), cuatro ya estaban en §9 y §10 de la investigación. La
que no teníamos con nombre era esta.

Por qué hace falta en el Companion, concretamente:

- Lee **nombres de clientes finales** en los metadatos de conversación
  (CP-21). Son personas que nunca aceptaron aparecer en el chat de la
  consola de su proveedor.
- Lee **motivos de rechazo de Meta**, que citan literalmente el contenido de
  la plantilla — y las plantillas llevan teléfonos y correos de ejemplo.
- El contrato (§3.4) ya exige ``email_masked`` en el ``preview`` de
  ``kind: invite``, y §14 lo dice sin matices: **nunca correos completos de
  terceros en el chat**.

Regla de diseño: **enmascarar es dejar suficiente para correlacionar y no lo
bastante para contactar.** Una máscara que borra del todo hace inútil el
dato ("un cliente escribió") y empuja al modelo a pedir el original.

Sobre los enmascaradores que ya existían
----------------------------------------
``services/direct_messages.mask_phone`` y
``services/owner_channel_flow._mask_phone`` hacen lo mismo con dos formatos
distintos, y llevan tiempo en los logs de producción. **No se tocan aquí**:
cambiar el formato de una máscara que está en logs es un cambio de
observabilidad, no de este paquete. :func:`mask_phone` adopta el formato del
primero (el más informativo) y queda la convergencia pendiente.
"""

from __future__ import annotations

import re

_MASK = "***"
_ELLIPSIS = "…"

#: Correo. Laxo en el dominio (se prefiere enmascarar de más que dejar pasar
#: ``ana@sub.dominio.co.uk``) y con una guarda por delante para que la
#: función sea **idempotente**: ``m…z@facelad.com`` ya está enmascarado y no
#: se vuelve a detectar como correo.
EMAIL_RE = re.compile(rf"(?<![\w.+\-{_ELLIPSIS}])[\w.+-]+@[\w-]+(?:\.[\w-]+)+\b")

#: Teléfono internacional (``+34 600 11 22 33``) o una tirada larga de
#: dígitos con separadores. Las guardas son de **dígito**, no de puntuación:
#: un teléfono al final de una frase lleva un punto detrás y una guarda de
#: puntuación lo dejaría pasar. Lo que sí cabe en el patrón sin ser teléfono
#: —fechas, importes— se descarta aparte, en :func:`_is_phone`.
PHONE_RE = re.compile(r"(?<!\w)(?:\+\d[\d\s().-]{6,}\d|\d[\d\s().-]{8,}\d)(?!\d)")

#: ``2026-08-18`` encaja con el patrón largo de teléfono y no es un
#: teléfono. Es el falso positivo que de verdad aparece: el Companion lee
#: fechas en casi todas las lecturas.
_ISO_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _is_phone(candidate: str) -> bool:
    """Descarta lo que encaja con el patrón sin ser un teléfono."""
    text = candidate.strip()
    if _ISO_DATE_RE.match(text):
        return False
    digits = sum(c.isdigit() for c in text)
    return digits >= 8


def mask_email(raw: str | None) -> str:
    """``maria.gonzalez@facelad.com`` → ``m…z@facelad.com``.

    El dominio se conserva entero a propósito: es lo que le dice al partner
    "esto es de tu equipo" o "esto es de fuera", y no identifica a nadie.
    """
    if not raw:
        return ""
    if "@" not in raw:
        return mask_person_name(raw)
    local, _, domain = raw.partition("@")
    if not local:
        return f"…@{domain}"
    if len(local) == 1:
        return f"{local}…@{domain}"
    return f"{local[0]}…{local[-1]}@{domain}"


def mask_phone(raw: str | None) -> str:
    """``+56912345678`` → ``+5691***5678``.

    Mismo formato que ``services/direct_messages.mask_phone``: suficiente
    para casar una línea de log con una fila de una hoja, insuficiente para
    convertir el log en una agenda.
    """
    if not raw:
        return ""
    if len(raw) <= 8:
        return f"{raw[:2]}{_MASK}"
    return f"{raw[:5]}{_MASK}{raw[-4:]}"


def mask_person_name(raw: str | None) -> str:
    """``María González`` → ``M. G.``.

    Las iniciales bastan para hablar de la conversación ("la de M. G. sigue
    sin responder") sin poner el nombre completo de un cliente final en el
    chat de su proveedor.
    """
    if not raw:
        return ""
    parts = [p for p in re.split(r"\s+", raw.strip()) if p]
    if not parts:
        return ""
    return " ".join(f"{p[0].upper()}." for p in parts[:3])


def scrub_pii(text: str | None) -> str:
    """Enmascara correos y teléfonos dentro de texto libre.

    Para lo que llega en prosa y no en un campo: un motivo de rechazo de
    Meta, una nota, el cuerpo de un documento. **No** intenta detectar
    nombres de persona en prosa — un detector de nombres sin modelo produce
    más destrozo que protección (se comería "Clínica Boreal"), y los nombres
    llegan casi siempre en un campo propio, donde se usa
    :func:`mask_person_name`.
    """
    if not text:
        return ""

    def _phone(match: re.Match[str]) -> str:
        raw = match.group(0)
        if not _is_phone(raw):
            return raw
        lead = len(raw) - len(raw.lstrip())
        return raw[:lead] + mask_phone(raw.strip())

    out = EMAIL_RE.sub(lambda m: mask_email(m.group(0)), text)
    return PHONE_RE.sub(_phone, out)


def contains_pii(text: str | None) -> bool:
    """¿Queda algún correo o teléfono sin enmascarar?

    Es la forma afirmativa del test: un caso de eval no comprueba que
    ``scrub_pii`` se llamó, comprueba que en lo que sale no hay PII.
    """
    if not text:
        return False
    if EMAIL_RE.search(text):
        return True
    return any(_is_phone(m.group(0)) for m in PHONE_RE.finditer(text))


__all__ = [
    "EMAIL_RE",
    "PHONE_RE",
    "contains_pii",
    "mask_email",
    "mask_person_name",
    "mask_phone",
    "scrub_pii",
]
