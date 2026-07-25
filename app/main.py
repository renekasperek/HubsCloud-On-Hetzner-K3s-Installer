from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from api.routes import router
from config import APP_VERSION, ensure_data_dirs

app = FastAPI(title="Hubs Installer", version=APP_VERSION)
app.include_router(router)

ensure_data_dirs()

UI_DIST = Path(__file__).resolve().parent / "ui" / "dist"


def _ui_file(path: str) -> Path | None:
    """Resolve a path under UI_DIST; reject traversal."""
    if not path or path.startswith(".."):
        return None
    candidate = (UI_DIST / path).resolve()
    try:
        candidate.relative_to(UI_DIST.resolve())
    except ValueError:
        return None
    return candidate if candidate.is_file() else None


@app.get("/")
def index():
    index_file = UI_DIST / "index.html"
    if index_file.exists():
        return FileResponse(index_file)
    return {"message": "Hubs Installer API", "version": APP_VERSION}


if UI_DIST.exists():
    app.mount("/assets", StaticFiles(directory=UI_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}")
    def spa_fallback(full_path: str):
        if full_path.startswith("api/"):
            return {"detail": "Not found"}
        static_file = _ui_file(full_path)
        if static_file is not None:
            return FileResponse(static_file)
        index_file = UI_DIST / "index.html"
        if index_file.exists():
            return FileResponse(index_file)
        return {"detail": "UI not built"}
