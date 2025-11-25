
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from datetime import datetime
import os
import uuid

app = FastAPI(
    title="EnTrus Cloud Imaging Pipeline",
    description="Core rendering + frequency preview service",
    version="1.0.0"
)

# --------------------------------------------------
# Models
# --------------------------------------------------

class RenderRequest(BaseModel):
    prompt: str
    style: str = "entrus_signature"
    frequency: int | None = None

class MockupRequest(BaseModel):
    apparel_type: str
    color: str
    sigil: str | None = None
    frequency: int | None = None

# --------------------------------------------------
# Utilities
# --------------------------------------------------

GENERATED_DIR = "generated"
os.makedirs(GENERATED_DIR, exist_ok=True)

def save_dummy_image(name: str) -> str:
    """
    Since we cannot use heavy GPU tools on Render free tier,
    this creates a placeholder image file to prove pipeline functionality.
    """
    file_id = f"{name}-{uuid.uuid4().hex}.txt"
    path = os.path.join(GENERATED_DIR, file_id)

    with open(path, "w") as f:
        f.write(f"GENERATED PLACEHOLDER FILE\n")
        f.write(f"Timestamp: {datetime.utcnow()}\n")
        f.write(f"Render ID: {uuid.uuid4().hex}\n")

    return path

# --------------------------------------------------
# Base routes
# --------------------------------------------------

@app.get("/")
def home():
    return {
        "service": "EnTrus Cloud Imaging Pipeline",
        "status": "online",
        "generated_dir": GENERATED_DIR,
        "message": "Ready to generate EnTrus visuals."
    }

# --------------------------------------------------
# Render endpoints
# --------------------------------------------------

@app.post("/render")
def render_image(req: RenderRequest):
    """
    Placeholder / mock image generator.
    Later: plug into Cloudflare AI, Replicate, or your own GPU server.
    """
    path = save_dummy_image("render")
    return {
        "status": "ok",
        "prompt_used": req.prompt,
        "frequency": req.frequency,
        "style": req.style,
        "file_saved": path
    }

@app.post("/mockup/apparel")
def build_mockup(req: MockupRequest):
    """
    Generates a placeholder mockup for hoodies, tees, joggers, shoes, etc.
    """
    if req.apparel_type not in ["hoodie", "tee", "joggers", "shoes", "kids", "bracelet"]:
        raise HTTPException(400, "Invalid apparel type")

    path = save_dummy_image(req.apparel_type)
    return {
        "status": "ok",
        "apparel": req.apparel_type,
        "color": req.color,
        "sigil": req.sigil,
        "frequency": req.frequency,
        "file_saved": path
    }

@app.get("/frequency/{hz}")
def frequency_preview(hz: int):
    presets = {
        285: ("Seal of Form", "Return to Origin"),
        396: ("Seal of Protector", "Guard the Flame"),
        528: ("Seal of Flow", "Live in Rhythm"),
        639: ("Seal of Drive", "Fuel the Bond"),
        741: ("Seal of Expression", "Speak the Light"),
        852: ("Seal of Seer", "Reveal the Light")
    }

    if hz not in presets:
        raise HTTPException(404, "Unknown frequency.")

    seal, phrase = presets[hz]
    return {
        "hz": hz,
        "seal": seal,
        "phrase": phrase,
        "status": "ok"
    } 
