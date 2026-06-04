from fastapi import APIRouter

from app.core.config import get_settings

router = APIRouter(tags=["health"])
settings = get_settings()


@router.get("/health")
async def health_check():
    return {"status": "ok", "service": settings.APP_NAME, "version": settings.APP_VERSION}


@router.get("/ready")
async def readiness_check():
    # Extend with actual DB/Redis/Chroma probes as needed
    return {"status": "ready"}
