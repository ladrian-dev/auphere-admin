"""El ejecutor de herramientas, con un ASGI de mentira (CO-02).

Aquí se prueba lo que el ejecutor hace ANTES y DESPUÉS de la petición:
validar, traducir errores, recortar, contar y citar. La petición en sí se
sustituye por una app ASGI mínima, así que estos tests no tocan base de
datos y corren en milisegundos.

La otra mitad —que el router de verdad rechaza el cliente de otro partner—
vive en ``tests/isolation/test_companion_tool_scope.py``, contra la
aplicación real.
"""

from __future__ import annotations

import json
import uuid
from typing import Any

import pytest
from fastapi import FastAPI, HTTPException, Query

from nexus_api.companion.tools import CompanionToolbelt
from nexus_api.companion.tools.runner import TRUNCATION_MARK
from nexus_api.core.console_auth import InProcessActor

pytestmark = pytest.mark.unit

ACTOR = InProcessActor(user_id="user_x", partner_id=uuid.uuid4(), jti="companion:test")


def _stub_app(status_by_path: dict[str, int] | None = None, body: Any = None) -> FastAPI:
    """Una app que imita las rutas del catálogo sin nada detrás."""
    app = FastAPI()
    codes = status_by_path or {}

    async def _handler(path: str) -> Any:
        code = codes.get(path)
        if code:
            raise HTTPException(status_code=code, detail=f"stub {code}")
        return body if body is not None else {"path": path}

    @app.get("/console/me")
    async def me() -> Any:
        return await _handler("/console/me")

    @app.get("/console/clients")
    async def clients(
        q: str | None = Query(default=None),
        limit: int | None = Query(default=None),
        status: str | None = Query(default=None),
    ) -> Any:
        return {"q": q, "limit": limit, "status": status}

    @app.get("/console/clients/{ref}")
    async def client(ref: str) -> Any:
        codes_for = codes.get("/console/clients/{ref}")
        if codes_for:
            raise HTTPException(status_code=codes_for, detail=f"stub {codes_for}")
        return {"ref": ref}

    @app.get("/console/usage")
    async def usage(
        client: str | None = Query(default=None),
        days: int | None = Query(default=None),
        source: str | None = Query(default=None),
    ) -> Any:
        return {"client": client, "days": days, "source": source}

    @app.get("/console/onboarding")
    async def onboarding() -> Any:
        return await _handler("/console/onboarding")

    return app


async def _belt(app: FastAPI, **kwargs: Any) -> CompanionToolbelt:
    belt = CompanionToolbelt(actor=ACTOR, app=app, **kwargs)
    await belt.__aenter__()
    return belt


# ── validación de argumentos ───────────────────────────────────────────


async def test_an_unknown_tool_says_which_ones_exist() -> None:
    """Un modelo que se inventa una herramienta necesita la lista, no un
    "no existe" a secas: si no, prueba otra invención."""
    belt = await _belt(_stub_app())
    out = await belt.call("console.delete_everything", {})
    payload = json.loads(out.content)
    assert payload["error"] == "unknown_tool"
    assert "console.list_clients" in payload["message"]


async def test_an_unknown_argument_is_refused_before_the_request() -> None:
    belt = await _belt(_stub_app())
    out = await belt.call("console.get_usage", {"tenant_id": "x"})
    assert out.ok is False
    payload = json.loads(out.content)
    assert payload["error"] == "bad_arguments"
    assert "tenant_id" in payload["message"]


async def test_a_missing_required_argument_is_refused() -> None:
    belt = await _belt(_stub_app())
    out = await belt.call("console.get_client", {})
    assert json.loads(out.content)["error"] == "bad_arguments"


async def test_a_wrong_type_is_refused() -> None:
    belt = await _belt(_stub_app())
    out = await belt.call("console.get_usage", {"days": "treinta"})
    assert json.loads(out.content)["error"] == "bad_arguments"


async def test_a_boolean_does_not_pass_as_an_integer() -> None:
    """``bool`` es subclase de ``int`` en Python: sin la exclusión
    explícita, ``days=True`` llegaría al router como ``days=1``."""
    belt = await _belt(_stub_app())
    out = await belt.call("console.get_usage", {"days": True})
    assert json.loads(out.content)["error"] == "bad_arguments"


async def test_a_value_outside_the_enum_is_refused() -> None:
    belt = await _belt(_stub_app())
    out = await belt.call("console.get_usage", {"source": "companion"})
    payload = json.loads(out.content)
    assert payload["error"] == "bad_arguments"
    assert "channel" in payload["message"]


async def test_a_refused_call_does_not_consume_the_budget() -> None:
    """Los argumentos malos son del modelo, no del partner. Cobrárselos al
    presupuesto del turno castigaría al usuario por un error ajeno."""
    belt = await _belt(_stub_app(), max_calls=2)
    await belt.call("console.get_usage", {"days": "treinta"})
    await belt.call("console.get_usage", {"nope": 1})
    assert belt.calls_made == 0
    assert (await belt.call("console.whoami", {})).ok


# ── traducción de la respuesta del router ──────────────────────────────


@pytest.mark.parametrize(
    ("status_code", "expected"),
    [
        (404, "unknown_client"),
        (403, "forbidden"),
        (409, "conflict"),
        (422, "bad_arguments"),
        (429, "rate_limited"),
        (401, "unauthenticated"),
        (500, "unavailable"),
        (503, "unavailable"),
    ],
)
async def test_every_router_status_becomes_something_actionable(
    status_code: int, expected: str
) -> None:
    belt = await _belt(_stub_app({"/console/clients/{ref}": status_code}))
    out = await belt.call("console.get_client", {"client_ref": "boreal"})
    payload = json.loads(out.content)
    assert payload["error"] == expected
    # Nunca un volcado: siempre una frase que dice qué hacer.
    assert len(payload["message"]) > 40


async def test_the_404_message_never_says_it_belongs_to_someone_else() -> None:
    """Es la mitad del 404 opaco. La otra mitad —que el router responda
    igual— la prueba el test de aislamiento."""
    belt = await _belt(_stub_app({"/console/clients/{ref}": 404}))
    out = await belt.call("console.get_client", {"client_ref": "ajeno"})
    lowered = json.loads(out.content)["message"].lower()
    for leak in ("otro partner", "no es tuyo", "pertenece", "ajeno"):
        assert leak not in lowered


# ── construcción de la petición ────────────────────────────────────────


async def test_the_client_ref_goes_into_the_path() -> None:
    belt = await _belt(_stub_app())
    out = await belt.call("console.get_client", {"client_ref": "boreal"})
    assert out.ok
    assert json.loads(out.content)["ref"] == "boreal"


async def test_the_client_ref_becomes_the_routers_own_query_name() -> None:
    """El catálogo habla el idioma del partner (``client_ref``) y el router
    el suyo (``client``). La traducción vive en un sitio."""
    belt = await _belt(_stub_app())
    out = await belt.call("console.get_usage", {"client_ref": "boreal", "days": 7})
    body = json.loads(out.content)
    assert body["client"] == "boreal"
    assert body["days"] == 7


async def test_omitted_optional_arguments_are_not_sent() -> None:
    belt = await _belt(_stub_app())
    out = await belt.call("console.list_clients", {"q": "clin"})
    body = json.loads(out.content)
    assert body["q"] == "clin"
    assert body["limit"] is None and body["status"] is None


# ── recorte, citas y contadores ────────────────────────────────────────


async def test_a_long_response_is_truncated_with_a_visible_mark() -> None:
    """Sin recorte, tres lecturas caras llenan la ventana y el resto del
    turno responde a ciegas. Y el recorte va marcado: el modelo tiene que
    saber que vio una parte."""
    belt = await _belt(_stub_app(body={"rows": ["x" * 200] * 200}))
    out = await belt.call("console.whoami", {})
    assert out.ok
    spec_max = 2_000
    assert len(out.content) <= spec_max + len(TRUNCATION_MARK.format(n=999_999))
    assert "recortado" in out.content


async def test_a_short_response_is_not_touched() -> None:
    belt = await _belt(_stub_app())
    out = await belt.call("console.get_onboarding", {})
    assert "recortado" not in out.content
    assert json.loads(out.content)["path"] == "/console/onboarding"


async def test_the_citation_carries_the_claim_the_source_and_the_time() -> None:
    belt = await _belt(_stub_app())
    out = await belt.call("console.get_usage", {"client_ref": "boreal", "days": 7})
    assert out.citation is not None
    payload = out.citation.as_payload()
    assert payload["claim"].startswith("Consumo del partner")
    assert "client_ref=boreal" in payload["claim"]
    assert payload["source"] == "/console/usage?client=boreal&days=7"
    assert payload["fetched_at"]


async def test_reads_done_counts_only_successes() -> None:
    """Es el numerador de R1. Si un 404 contara, la regla dejaría pasar
    justo los turnos que tiene que marcar."""
    belt = await _belt(_stub_app({"/console/clients/{ref}": 404}))
    await belt.call("console.get_client", {"client_ref": "no"})
    assert belt.reads_done == 0
    await belt.call("console.whoami", {})
    assert belt.reads_done == 1


async def test_propose_model_rejects_extra_keys_and_oversize() -> None:
    belt = await _belt(_stub_app())
    extra = await belt.call(
        "console.propose_model",
        {
            "client_ref": "boreal",
            "model_id": "openai/gpt-5.6-sol",
            "partner_id": "x",
        },
    )
    assert extra.ok is False
    assert json.loads(extra.content)["error"] == "bad_arguments"
    assert "partner_id" in json.loads(extra.content)["message"]

    oversize = await belt.call(
        "console.propose_model",
        {"client_ref": "boreal", "model_id": "gpt-5.6" + ("x" * 200)},
    )
    assert oversize.ok is False
    assert json.loads(oversize.content)["error"] == "bad_arguments"
