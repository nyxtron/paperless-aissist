"""Application metadata endpoint."""

from fastapi import APIRouter

from ..constants import APP_VERSION

router = APIRouter(prefix="/api/app-info", tags=["app-info"])


@router.get("")
async def get_app_info():
    return {
        "version": APP_VERSION,
    }

