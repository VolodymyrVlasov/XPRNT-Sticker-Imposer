import os

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from server.routes import analyze, analyze_shape, config, generate, generate_batch, layout, session

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
WEB_DIR = os.path.join(PROJECT_ROOT, "web")

app = FastAPI(title="Rect Sticker Imposer")

app.include_router(config.router)
app.include_router(analyze.router)
app.include_router(analyze_shape.router)
app.include_router(layout.router)
app.include_router(generate.router)
app.include_router(generate_batch.router)
app.include_router(session.router)

app.mount("/", StaticFiles(directory=WEB_DIR, html=True), name="web")
