from fastapi import APIRouter

from server import session_store

router = APIRouter()


@router.delete("/api/session/{upload_id}")
def drop_session(upload_id: str) -> dict:
    """Explicitly free an uploaded artwork — called when the user starts a new task."""
    session_store.drop_upload(upload_id)
    return {"ok": True}
