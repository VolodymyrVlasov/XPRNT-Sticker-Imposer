"""In-memory registry of uploaded artwork PDFs, keyed by an opaque upload_id.

Files live under the OS temp dir and are dropped either when consumed by
/api/generate or after TTL_SECONDS of inactivity.
"""

import os
import shutil
import tempfile
import threading
import time
import uuid

SESSIONS_ROOT = os.path.join(tempfile.gettempdir(), "rect_sticker_imposer_sessions")
os.makedirs(SESSIONS_ROOT, exist_ok=True)

TTL_SECONDS = 2 * 3600

_lock = threading.Lock()
_uploads: dict[str, dict] = {}


def save_upload(filename: str, data: bytes) -> str:
    upload_id = uuid.uuid4().hex
    session_dir = os.path.join(SESSIONS_ROOT, upload_id)
    os.makedirs(session_dir, exist_ok=True)
    safe_name = os.path.basename(filename) or "artwork.pdf"
    path = os.path.join(session_dir, safe_name)
    with open(path, "wb") as f:
        f.write(data)
    with _lock:
        _uploads[upload_id] = {
            "path": path, "filename": safe_name, "dir": session_dir, "created": time.time(),
        }
    _cleanup_stale()
    return upload_id


def get_upload(upload_id: str) -> tuple[str, str]:
    """Return (path, original_filename) for a previously saved upload."""
    with _lock:
        entry = _uploads.get(upload_id)
    if not entry:
        raise KeyError("Сесію завантаження не знайдено або її термін дії минув — завантажте файл ще раз")
    return entry["path"], entry["filename"]


def touch_upload(upload_id: str) -> None:
    """Reset the TTL clock so a session the user keeps working in doesn't expire."""
    with _lock:
        entry = _uploads.get(upload_id)
        if entry:
            entry["created"] = time.time()


def drop_upload(upload_id: str) -> None:
    with _lock:
        entry = _uploads.pop(upload_id, None)
    if entry:
        shutil.rmtree(entry["dir"], ignore_errors=True)


def _cleanup_stale() -> None:
    now = time.time()
    with _lock:
        stale = [uid for uid, e in _uploads.items() if now - e["created"] > TTL_SECONDS]
        entries = [_uploads.pop(uid) for uid in stale]
    for entry in entries:
        shutil.rmtree(entry["dir"], ignore_errors=True)


def new_work_dir() -> str:
    return tempfile.mkdtemp(prefix="rsi_gen_", dir=SESSIONS_ROOT)


def cleanup_dir(path: str) -> None:
    shutil.rmtree(path, ignore_errors=True)
