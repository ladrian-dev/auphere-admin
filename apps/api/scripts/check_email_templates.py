"""Comprueba que las plantillas de Resend y el catálogo del código dicen lo mismo.

Spec 051, R7.1. Las plantillas viven en Resend y se editan en su panel (decisión
D1 de la spec), así que nada en el repositorio impide que alguien quite una
variable, despublique una plantilla o le cambie el alias. Esta comprobación es
la red: recorre ``CATALOG`` y, por cada alias, verifica contra la cuenta que la
plantilla existe, está publicada, declara exactamente las variables que envía
el código y cumple las reglas de redacción que se pueden comprobar.

Uso (con la clave de la cuenta en el entorno)::

    NEXUS_RESEND_API_KEY=re_… uv run python scripts/check_email_templates.py
    NEXUS_RESEND_API_KEY=re_… uv run python scripts/check_email_templates.py --json

Sale con 1 si alguna plantilla falla. **No va en CI**: CI no tiene la clave de
Resend y no debe tenerla. Se ejecuta antes de pasar a producción y su salida se
guarda en ``specs/051-correos-con-oficio/evidence/``.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Any

import httpx

from nexus_api.services.email_catalog import CATALOG, EmailKind, EmailSpec

_API = "https://api.resend.com/templates"

#: ``contracts/redaccion.md`` §«Lo que delata un texto hecho por una máquina».
#: Se comparan en minúsculas con el HTML de la plantilla.
BLACKLIST: tuple[str, ...] = (
    "esperamos que estés bien",
    "espero que este correo te encuentre bien",
    "¡hola!",
    "te escribimos para informarte",
    "te informamos que",
    "nos complace informarte",
    "no dudes en contactarnos",
    "no dudes en escribirnos",
    "estamos aquí para ayudarte",
    "estamos para lo que necesites",
    "gracias por confiar en nosotros",
    "gracias por elegirnos",
    "saludos cordiales",
    "atentamente",
    "un cordial saludo",
    "por favor, ten en cuenta que",
    "cabe destacar que",
    "es importante destacar",
    "recibes este correo porque",
    "recibes este aviso porque",
    "de manera rápida y sencilla",
    "en tan solo unos clics",
    "fácil y rápido",
    "solución integral",
    "transformación digital",
    "revolucionario",
    "de vanguardia",
    "a propósito",
    "haz clic aquí",
    "pulsa aquí",
    "click aquí",
    "i hope this email finds you well",
    "we are pleased to inform you",
    "please be advised",
    "don't hesitate to reach out",
    "feel free to reach out",
    "click here",
    "seamless",
    "delightful",
    "unlock",
    "leverage",
)
#: Palabras de dentro (``redaccion.md``): se buscan como palabra entera.
_INSIDE_WORDS = re.compile(r"\b(tope|bolsa|máquinas|dar de baja)\b", re.IGNORECASE)
_SIGNATURE = {"es": "El equipo de Auphere", "en": "The Auphere team"}
_CTA = re.compile(r'bgcolor="#00DF81"', re.IGNORECASE)
_HREF = re.compile(r'href="([^"]*)"', re.IGNORECASE)
_TAGS = re.compile(r"<[^>]+>")


@dataclass
class Result:
    kind: str
    alias: str
    problems: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return not self.problems


def check_template(
    kind: EmailKind, locale: str, spec: EmailSpec, template: Mapping[str, Any] | None
) -> Result:
    """Lo que falla de una plantilla. Pura: no habla con Resend."""
    alias = spec.aliases[locale]
    result = Result(kind=kind.value, alias=alias)
    if template is None:
        result.problems.append("no existe en Resend")
        return result
    if template.get("status") != "published":
        result.problems.append(f"no está publicada (estado: {template.get('status')})")
    if template.get("has_unpublished_versions"):
        result.warnings.append("tiene cambios sin publicar")

    declared = {str(v.get("key")) for v in template.get("variables") or []}
    if missing := sorted(spec.variables - declared):
        result.problems.append(f"le faltan variables que envía el código: {', '.join(missing)}")
    if extra := sorted(declared - spec.variables):
        result.problems.append(f"declara variables que el código no envía: {', '.join(extra)}")

    html = str(template.get("html") or "")
    for key in sorted(spec.variables):
        if "{{{" + key + "}}}" not in html:
            result.problems.append(f"no usa la variable {key}")

    if kind is not EmailKind.INTERNAL_ALERT and _SIGNATURE[locale] not in html:
        result.problems.append(f"no lleva la firma «{_SIGNATURE[locale]}»")

    text = _TAGS.sub(" ", html).lower()
    for phrase in BLACKLIST:
        if phrase in text:
            result.problems.append(f"contiene «{phrase}»")
    for word in sorted({m.group(1).lower() for m in _INSIDE_WORDS.finditer(text)}):
        result.problems.append(f"usa una palabra de dentro: «{word}»")

    if len(_CTA.findall(html)) > 1:
        result.problems.append("tiene más de un botón de llamada a la acción")
    if not spec.links_allowed:
        bad = [h for h in _HREF.findall(html) if not h.startswith("mailto:")]
        if bad:
            result.problems.append(f"lleva enlaces que este correo no admite: {', '.join(bad)}")
    return result


def _fetch(client: httpx.Client, alias: str) -> Mapping[str, Any] | None:
    resp = client.get(f"{_API}/{alias}")
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    data: Mapping[str, Any] = resp.json()
    return data


def run() -> list[Result]:
    key = os.environ.get("NEXUS_RESEND_API_KEY", "")
    if not key or key.startswith("dev-"):
        raise SystemExit("Falta NEXUS_RESEND_API_KEY con una clave real de Resend.")
    results: list[Result] = []
    with httpx.Client(headers={"Authorization": f"Bearer {key}"}, timeout=20.0) as client:
        for kind, spec in CATALOG.items():
            for locale in spec.aliases:
                results.append(check_template(kind, locale, spec, _fetch(client, spec.aliases[locale])))
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").splitlines()[0])
    parser.add_argument("--json", action="store_true", help="informe en JSON")
    args = parser.parse_args()
    results = run()
    if args.json:
        print(json.dumps([r.__dict__ | {"ok": r.ok} for r in results], ensure_ascii=False, indent=2))
    else:
        for r in results:
            mark = "OK " if r.ok else "MAL"
            print(f"{mark} {r.alias}")
            for problem in r.problems:
                print(f"    ✗ {problem}")
            for warning in r.warnings:
                print(f"    · {warning}")
        bad = sum(not r.ok for r in results)
        print(f"\n{len(results) - bad} de {len(results)} plantillas en orden.")
    return 0 if all(r.ok for r in results) else 1


if __name__ == "__main__":
    sys.exit(main())
