
from typing import Dict, List

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware


app = FastAPI(
    title="EnTrus Cloud Core",
    description="Core API for EnTrus Ritual Arts frequencies and creator console.",
    version="1.0.0",
)

# -------------------------------------------------------------------
# CORS (so the front-end or other tools can call this API)
# -------------------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],   # you can lock this down later
    allow_methods=["*"],
    allow_headers=["*"],
)

# -------------------------------------------------------------------
# Frequency data
# -------------------------------------------------------------------
FREQUENCY_MAP: Dict[int, Dict] = {
    396: {
        "hz": 396,
        "seal": "Seal of Protector",
        "phrase": "Guard the Flame",
        "colors": ["Burnt Copper", "Warm Ember", "Coal Black"],
        "notes": "Protector band — courage, protection, and inner fire.",
    },
    528: {
        "hz": 528,
        "seal": "Seal of Flow",
        "phrase": "Live in Rhythm",
        "colors": ["Forest Green", "Sage Mist", "Morning Gold"],
        "notes": "Flow band — alignment, growth, and natural movement.",
    },
    639: {
        "hz": 639,
        "seal": "Seal of Drive",
        "phrase": "Fuel the Bond",
        "colors": ["Sandstone Taupe", "Ruby Ember", "Slate Blue"],
        "notes": "Drive band — connection, creation, and energy exchange.",
    },
    741: {
        "hz": 741,
        "seal": "Seal of Expression",
        "phrase": "Speak the Light",
        "colors": ["Indigo Pulse", "Desert Gold", "White Clarity", "Obsidian Echo"],
        "notes": "Expression band — awakening, truth, and liberation.",
    },
    852: {
        "hz": 852,
        "seal": "Seal of Seer",
        "phrase": "Reveal the Light",
        "colors": ["White Clarity", "Gold Eclipse"],
        "notes": "Seer band — intuition, vision, and illumination.",
    },
}

# -------------------------------------------------------------------
# Root / health check
# -------------------------------------------------------------------
@app.get("/")
def root() -> Dict:
    return {
        "status": "ok",
        "service": "entrus_cloud_core",
        "message": "EnTrus Cloud Core online.",
        "routes": [
            "/",
            "/frequency/{hz}",
            "/creator",
            "/docs",
        ],
    }


# -------------------------------------------------------------------
# Frequency endpoint
# -------------------------------------------------------------------
@app.get("/frequency/{hz}")
def get_frequency(hz: int) -> Dict:
    data = FREQUENCY_MAP.get(hz)
    if not data:
        raise HTTPException(status_code=404, detail=f"Frequency {hz} not found")
    return data


# -------------------------------------------------------------------
# Creator console endpoint
# -------------------------------------------------------------------
@app.get("/creator")
def creator_console() -> Dict:
    """
    Simple JSON console so you can hit:
      https://entrusritualarts.com/creator
    and see that the cloud core is alive.
    """
    return {
        "status": "online",
        "console": "EnTrus Creator Station — Cloud Core",
        "message": "Cloud node is live and ready to connect to the front-end.",
        "examples": {
            "frequency_528": "/frequency/528",
            "frequency_396": "/frequency/396",
            "docs": "/docs",
            "openapi": "/openapi.json",
        },
    } 
