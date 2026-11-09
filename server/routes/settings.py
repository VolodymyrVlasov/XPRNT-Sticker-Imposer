from fastapi import APIRouter

from server.models import AppSettings
from server.utils.settings_store import load_settings, save_settings

router = APIRouter()


@router.get("/api/settings", response_model=AppSettings)
def get_settings() -> AppSettings:
    return AppSettings(**load_settings())


@router.post("/api/settings", response_model=AppSettings)
def update_settings(payload: AppSettings) -> AppSettings:
    save_settings(payload.model_dump())
    return payload
