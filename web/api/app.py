from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from web.api.routes import config, service, status, tools
from tools.registry import ToolRegistry
from observability.logger import get_logger

app = FastAPI(title="WeChat-Claude Management Panel", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(config.router)
app.include_router(service.router)
app.include_router(status.router)
app.include_router(tools.router)
app.include_router(tools.skills_router)

FRONTEND_DIST = Path(__file__).parent.parent / "frontend" / "dist"


@app.on_event("startup")
async def startup_event():
    get_logger()
    ToolRegistry.discover()


@app.get("/api/health")
def health_check():
    return {"status": "ok"}


if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIST / "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        file_path = FRONTEND_DIST / full_path
        if full_path and file_path.exists() and file_path.is_file():
            return FileResponse(str(file_path))
        return FileResponse(str(FRONTEND_DIST / "index.html"))
