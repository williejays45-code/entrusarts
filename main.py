
from typing import List, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel


# -------------------------------------------------------------------
# EnTrus Cloud Core – Public API
# -------------------------------------------------------------------

app = FastAPI(
    title="EnTrus Cloud Core",
    description="Public API for EnTrus Ritual Arts – frequencies, status, and render stubs.",
    version="0.1.0",
)


# -------------------------------------------------------------------
# Models
# -------------------------------------------------------------------

class FrequencyInfo(BaseModel):
    hz: int
    seal: str
    phrase: str
    colors: List[str]
    notes: Optional[str] = None


# -------------------------------------------------------------------
# In-memory frequency map (stub)
# -------------------------------------------------------------------

FREQUENCIES: dict[int, FrequencyInfo] = {
    285: FrequencyInfo(
        hz=285,
        seal="Seal of Form",
        phrase="Return to Origin",
        colors=["Earth Iron", "Deep Terra", "Pine Stone", "Smoke Gray"],
        notes="Foundational grounding line – physical renewal and repair.",
    ),
    396: FrequencyInfo(
        hz=396,
        seal="Seal of Protector",
        phrase="Guard the Flame",
        colors=["Burnt Copper", "Warm Ember", "Coal Black"],
        notes="Protector band – courage, protection, and inner fire.",
    ),
    528: FrequencyInfo(
        hz=528,
        seal="Seal of Flow",
        phrase="Live in Rhythm",
        colors=["Forest Green", "Sage Mist", "Morning Gold"],
        notes="Flow band – alignment, growth, and natural movement.",
    ),
    639: FrequencyInfo(
        hz=639,
        seal="Seal of Drive",
        phrase="Fuel the Bond",
        colors=["Sandstone Taupe", "Ruby Ember", "Slate Blue"],
        notes="Connection band – relationships, creativity, and shared momentum.",
    ),
    741: FrequencyInfo(
        hz=741,
        seal="Seal of Expression",
        phrase="Speak the Light",
        colors=["Indigo Pulse", "Desert Gold", "White Clarity", "Obsidian Echo"],
        notes="Expression band – voice, truth, and liberation.",
    ),
    852: FrequencyInfo(
        hz=852,
        seal="Seal of Seer",
        phrase="Reveal the Light",
        colors=["White Clarity", "Gold Eclipse"],
        notes="Vision band – intuition, perception, illumination.",
    ),
}


# -------------------------------------------------------------------
# Core routes
# -------------------------------------------------------------------

@app.get("/", tags=["core"])
async def root() -> dict:
    """
    Simple root endpoint so hitting the base URL shows that the API is alive.
    """
    return {
        "status": "online",
        "service": "entrus_cloud_core",
        "message": "Welcome to the EnTrus Cloud Core API.",
        "docs": "/docs",
    }


@app.get("/health", tags=["core"])
async def health() -> dict:
    """
    Lightweight health check for uptime monitors.
    """
    return {"ok": True}


# -------------------------------------------------------------------
# Frequency routes
# -------------------------------------------------------------------

@app.get("/frequency", response_model=list[FrequencyInfo], tags=["frequency"])
async def list_frequencies() -> list[FrequencyInfo]:
    """
    List all configured frequencies and their basic info.
    """
    return list(FREQUENCIES.values())


@app.get(
    "/frequency/{hz}",
    response_model=FrequencyInfo,
    tags=["frequency"],
)
async def get_frequency(hz: int) -> FrequencyInfo:
    """
    Get info for a specific frequency line.
    """
    if hz not in FREQUENCIES:
        raise HTTPException(status_code=404, detail="Frequency not configured in core.")
    return FREQUENCIES[hz]


# -------------------------------------------------------------------
# Render stub (for later expansion)
# -------------------------------------------------------------------

class RenderRequest(BaseModel):
    frequency: int
    style: str = "apparel_mockup"
    note: Optional[str] = None


class RenderResponse(BaseModel):
    request: RenderRequest
    status: str
    mock_url: str


@app.post("/render/mock", response_model=RenderResponse, tags=["render"])
async def render_mock(req: RenderRequest) -> RenderResponse:
    """
    Stub endpoint for future image/mockup rendering.
    Right now it just echoes back a fake URL based on the frequency.
    """
    if req.frequency not in FREQUENCIES:
        raise HTTPException(status_code=404, detail="Frequency not configured in core.")

    fake_url = f"https://cdn.entrusritualarts.com/mockups/{req.frequency}-{req.style}.png"
    return RenderResponse(
        request=req,
        status="queued",
        mock_url=fake_url,
    ) 
