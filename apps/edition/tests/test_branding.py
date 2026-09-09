"""Requisito 9.1 — las marcas ajenas no viajan en lo que distribuimos.

Apache-2.0 §6 excluye expresamente los nombres comerciales del otorgamiento: el
código sí, las marcas no. Y la evaluación midió que el problema **no** es el
monstruo que sugiere un `grep` —105.221 apariciones— sino una superficie
pequeña: el catálogo de cadenas visibles, el empaquetado y unas constantes de
ruta. Los 24.482 identificadores internos (`kiro_crew`) **no se tocan**: la
licencia no lo exige y renombrarlos impediría seguir aguas arriba, que es la
única razón de usar el seam.

Lo que este módulo protege no es el renombrado de hoy: es que un bump de mañana
no vuelva a colar una marca donde el partner la vea. No hay constante central de
marca en el sustrato, así que la vigilancia tiene que ser nuestra.
"""

from __future__ import annotations

import pytest

from auphere_edition.branding import (
    FORBIDDEN_MARKS,
    PRODUCT_NAME,
    BrandLeak,
    assert_no_marks,
    scrub_user_facing,
)


def test_our_product_has_its_own_name():
    assert PRODUCT_NAME == "Auphere"
    assert "kiro" not in PRODUCT_NAME.lower()


@pytest.mark.parametrize(
    "text",
    [
        "Welcome to Kiro Crew",
        "kirocrew doctor says hello",
        "instala Kiro para continuar",
        "~/.kiro/crew",
    ],
)
def test_a_visible_mark_is_refused(text: str):
    with pytest.raises(BrandLeak):
        assert_no_marks(text)


def test_text_without_marks_passes():
    assert_no_marks("El teammate ha terminado el build.") is None


def test_scrubbing_replaces_the_mark_with_our_name():
    assert scrub_user_facing("Kiro Crew is ready") == "Auphere is ready"
    assert scrub_user_facing("kirocrew gateway") == "Auphere gateway"


def test_internal_identifiers_are_not_our_business():
    """`kiro_crew` como módulo NO es uso de marca: es la ruta de importación.

    Renombrarlo costaría el seguimiento aguas arriba y la licencia no lo pide.
    """
    assert_no_marks("from kiro_crew.platform import bootstrap") is None
    assert "kiro_crew" not in FORBIDDEN_MARKS


def test_the_forbidden_list_covers_the_shapes_that_actually_appear():
    lowered = {m.lower() for m in FORBIDDEN_MARKS}
    assert {"kiro crew", "kirocrew", "kiro"} <= lowered
