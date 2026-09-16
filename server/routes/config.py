from fastapi import APIRouter

from server.utils.constants import (
    CUSTOM_MATERIAL, DEFAULT_FIELD_MARGIN, DEFAULT_GAP, DEFAULT_MARK_OFFSET,
    MATERIALS, SHEET_PRESETS,
)

router = APIRouter()


@router.get("/api/config")
def get_config() -> dict:
    return {
        "materials": MATERIALS,
        "custom_material": CUSTOM_MATERIAL,
        "sheet_presets": {name: {"w": w, "h": h} for name, (w, h) in SHEET_PRESETS.items()},
        "defaults": {
            "mark_offset": DEFAULT_MARK_OFFSET,
            "field_margin": DEFAULT_FIELD_MARGIN,
            "gap": DEFAULT_GAP,
        },
    }
