"""Ningún sitio compone su propio correo — spec 051, R2.2 y CE-003.

El defecto que esta spec retira no era un correo feo: era que cada sitio que
enviaba escribía su HTML a mano, y por eso había veintiún estilos, un enlace
relativo dentro de ``<code>`` y un aviso que volcaba claves internas. Este
barrido falla si vuelve a aparecer un camino así.
"""

from __future__ import annotations

import pathlib
import re

_REPO = pathlib.Path(__file__).resolve().parents[4]
_ROOTS = (
    _REPO / "apps" / "api" / "src",
    _REPO / "apps" / "api" / "scripts",
    _REPO / "apps" / "worker" / "src",
)
#: Los dos únicos sitios que hablan con Resend: el envío y la comprobación.
_RESEND_OK = {
    "apps/api/src/nexus_api/services/email.py",
    "apps/api/scripts/check_email_templates.py",
}
#: ``send_email`` como función: importada o llamada. ``body.send_email`` (la
#: casilla del panel para mandar un recibo) es un campo, no esto.
_OLD_SENDER = re.compile(r"import[^\n]*\bsend_email\b|(?<![.\w])send_email\s*\(")


def _sources() -> list[tuple[str, str]]:
    out = []
    for root in _ROOTS:
        for path in sorted(root.rglob("*.py")):
            out.append((str(path.relative_to(_REPO)), path.read_text()))
    return out


def test_send_email_ya_no_existe() -> None:
    offenders = [p for p, text in _sources() if _OLD_SENDER.search(text)]
    assert offenders == [], f"siguen enviando con send_email: {offenders}"


def test_solo_el_envio_habla_con_resend() -> None:
    offenders = [p for p, text in _sources() if "api.resend.com" in text and p not in _RESEND_OK]
    assert offenders == [], f"hablan con Resend por su cuenta: {offenders}"


#: El recibo imprimible de la consola es un documento para el navegador, no un
#: correo: conserva su propio HTML (``partner_receipt_document``).
_DOCUMENTS = {"apps/api/src/nexus_api/services/partner_receipt_document.py"}


def test_no_queda_el_maquetado_viejo() -> None:
    """La envoltura que se copiaba de un correo a otro."""
    old_wrapper = "font-family:-apple-system,Segoe UI,Roboto"
    offenders = [p for p, text in _sources() if old_wrapper in text and p not in _DOCUMENTS]
    assert offenders == [], f"queda maquetado de correo en: {offenders}"
