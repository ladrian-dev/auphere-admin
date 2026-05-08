from fastapi import APIRouter

router = APIRouter(tags=["health"])


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/health/live")
async def liveness() -> dict[str, str]:
    return {"status": "alive"}


@router.get("/health/ready")
async def readiness() -> dict[str, str]:
    # Block B will add real checks (DB, Redis, LiteLLM). For block A this
    # mirrors /health so Railway/Vercel probes have a target.
    return {"status": "ready"}
