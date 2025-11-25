
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from utils.cors import build_cors_config
from brain.mesh import router as mesh_router
from brain.frequency import router as frequency_router
from brain.guardians import router as guardians_router
from brain.render import router as render_router
from creator.station import router as creator_router
from ritual.engine import router as ritual_router
from apparel.mockup import router as apparel_router


app = FastAPI(
    title="EnTrus Cloud Brain",
    version="1.0.0",
    description="Cloud brain for EnTrus Arts — frequencies, guardians, creator station, and render stubs.",
)

# -------------------------------------------------------------------
# CORS / security
# -------------------------------------------------------------------

cors_config = build_cors_config()
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_config["allow_origins"],
    allow_credentials=cors_config["allow_credentials"],
    allow_methods=cors_config["allow_methods"],
    allow_headers=cors_config["allow_headers"],
)

# -------------------------------------------------------------------
# Root & health
# -------------------------------------------------------------------


@app.get("/")
async def root() -> dict:
    """
    Simple root endpoint so visiting api.entrusiritualarts.com shows something friendly.
    """
    return {
        "name": "EnTrus Cloud Brain",
        "status": "online",
        "mesh": "core",
        "message": "Welcome to the EnTrus Cloud Brain v1.",
        "docs": "/docs",
        "endpoints": [
            "/mesh/state",
            "/frequency/list",
            "/frequency/{hz}",
            "/guardian/council",
            "/creator/ui",
            "/apparel/render/{hz}",
            "/render/scene/{hz}",
            "/ritual/sigil/{code}",
        ],
    }


@app.get("/health")
async def health() -> dict:
    """
    Basic health check, useful for uptime monitoring.
    """
    return {"status": "ok"}


# -------------------------------------------------------------------
# Routers
# -------------------------------------------------------------------

app.include_router(mesh_router, prefix="/mesh", tags=["mesh"])
app.include_router(frequency_router, prefix="/frequency", tags=["frequency"])
app.include_router(guardians_router, prefix="/guardian", tags=["guardians"])
app.include_router(render_router, prefix="/render", tags=["render"])
app.include_router(creator_router, prefix="/creator", tags=["creator"])
app.include_router(ritual_router, prefix="/ritual", tags=["ritual"])
app.include_router(apparel_router, prefix="/apparel", tags=["apparel"])


# -------------------------------------------------------------------
# Entrypoint for Uvicorn on Render:
# uvicorn main:app --host 0.0.0.0 --port 10000
# ------------------------------------------------------------------- 
