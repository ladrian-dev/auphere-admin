"""Garantía de aislamiento — el alta no alcanza nada que no sea suyo (spec 006).

`test_console_scope.py` ya cubre estructuralmente **toda** ruta de
``/console/*`` en cuanto se monta. Lo que este fichero añade es lo propio de
esta spec, que aquél no puede saber:

1. **Un alta no puede colgar una membresía de un partner que ya existe.** Es el
   único camino nuevo que crea membresías, y si se pudiera dirigir a un partner
   ajeno sería una escalada entre tenants con formulario público.
2. **Ningún objeto nuevo lleva ``tenant_id``.** ``signup_requests`` y
   ``principal_identities`` son de plataforma e identidad. Que no lo lleven es
   la afirmación, no la omisión: no hay tenant al que pertenecer.
3. **Las tres rutas nuevas responden 401 sin token**, igual que el resto.
"""

from __future__ import annotations

import uuid
from typing import Any

import pytest
import sqlalchemy as sa
from fastapi.routing import APIRoute

from nexus_api.db.models import Partner, PartnerMembership, SignupRequest
from nexus_api.db.models.console_identity import PrincipalIdentity
from nexus_api.main import app
from nexus_api.repositories.signup import SignupRequestRepository
from nexus_api.services.signup import complete_signup

pytestmark = [pytest.mark.isolation]

_SIGNUP_PATHS = [
    r.path for r in app.routes if isinstance(r, APIRoute) and r.path.startswith("/console/signup")
]


def test_las_tres_rutas_estan_montadas() -> None:
    """Si el router deja de montarse, el resto de este fichero pasaría por
    vacío y nadie se enteraría."""
    assert len(_SIGNUP_PATHS) == 3, _SIGNUP_PATHS


def test_ninguna_ruta_del_alta_acepta_partner_ni_tenant() -> None:
    """El alta **crea** un partner; nunca recibe a cuál apuntar.

    Un parámetro así convertiría el formulario público en una forma de colgar
    una membresía de una empresa ajena.

    Se lee del OpenAPI y no de los internos de FastAPI: el esquema publicado es
    lo que un llamante ve, y no cambia de forma entre versiones de pydantic.
    """
    prohibidos = {"tenant_id", "partner_id", "tenant", "partner"}
    spec = app.openapi()
    for path, operations in spec["paths"].items():
        if not path.startswith("/console/signup"):
            continue
        for method, op in operations.items():
            if method not in {"get", "post", "put", "patch", "delete"}:
                continue
            nombres = {p["name"] for p in op.get("parameters", [])}
            assert not (nombres & prohibidos), f"{method} {path} acepta {nombres & prohibidos}"
            ref = (
                op.get("requestBody", {})
                .get("content", {})
                .get("application/json", {})
                .get("schema", {})
                .get("$ref")
            )
            if ref:
                modelo = spec["components"]["schemas"][ref.rsplit("/", 1)[-1]]
                campos = set(modelo.get("properties", {}))
                assert not (campos & prohibidos), (
                    f"{method} {path} acepta en el cuerpo {campos & prohibidos}"
                )


def test_las_tablas_nuevas_no_tienen_tenant_id() -> None:
    for model in (SignupRequest, PrincipalIdentity):
        columnas = set(model.__table__.columns.keys())
        assert "tenant_id" not in columnas, f"{model.__tablename__} lleva tenant_id"


@pytest.mark.asyncio
async def test_un_alta_no_puede_colgarse_de_un_partner_existente(db_session: Any) -> None:
    """El servicio del alta **siempre** crea su propio partner.

    No hay argumento por el que dirigirlo, y esta prueba lo fija contra el
    futuro: si algún día alguien añade uno «por comodidad», esto se pone rojo.
    """
    ajeno = Partner(id=uuid.uuid4(), name="Ajeno", slug=f"ajeno-{uuid.uuid4().hex[:8]}")
    db_session.add(ajeno)
    await db_session.commit()

    repo = SignupRequestRepository(db_session)
    row, _token = await repo.create(email=f"intruso-{uuid.uuid4().hex[:8]}@x.com", ttl_hours=24)
    await db_session.commit()

    outcome = await complete_signup(
        db_session,
        signup=row,
        company_name="Propia",
        user_id=f"acct_{uuid.uuid4().hex[:12]}",
        display_name=None,
    )
    await db_session.commit()

    assert outcome.partner.id != ajeno.id, "el alta aterrizó en un partner ajeno"
    ajenas = (
        await db_session.execute(
            sa.select(sa.func.count())
            .select_from(PartnerMembership)
            .where(PartnerMembership.partner_id == ajeno.id)
        )
    ).scalar_one()
    assert ajenas == 0, "el alta creó una membresía en el partner ajeno"


@pytest.mark.asyncio
async def test_sin_token_las_tres_rutas_dan_401(client: Any) -> None:
    """Misma regla que el resto de ``/console/*``. La anonimidad del registro
    vive en el borde navegador ↔ BFF, nunca aquí."""
    assert (await client.post("/console/signup", json={"email": "a@b.com"})).status_code == 401
    assert (await client.get("/console/signup/" + "z" * 40)).status_code == 401
    complete = await client.post(
        "/console/signup/" + "z" * 40 + "/complete",
        json={"company_name": "X", "password": "una-contrasena-larga"},
    )
    assert complete.status_code == 401
