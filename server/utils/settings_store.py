"""Persistent app-wide settings, stored as a single JSON file on disk —
survives server restarts, shared across every browser/session of this
locally-run app (unlike anything in session_store, which is per-upload and
TTL'd). Not version-controlled — see .gitignore.
"""
import json
import os

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SETTINGS_PATH = os.path.join(_PROJECT_ROOT, "data", "app_settings.json")

DEFAULTS = {
    "extra_contour_keywords": [],
    "cut_contour_default": True,  # matches today's hardcoded `checked` attribute
}


def load_settings() -> dict:
    if not os.path.exists(SETTINGS_PATH):
        return dict(DEFAULTS)
    try:
        with open(SETTINGS_PATH, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, json.JSONDecodeError):
        return dict(DEFAULTS)
    # Merge over defaults so an old settings file missing a newer key still works.
    return {**DEFAULTS, **data}


def save_settings(data: dict) -> None:
    os.makedirs(os.path.dirname(SETTINGS_PATH), exist_ok=True)
    with open(SETTINGS_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
