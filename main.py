
from typing import Dict, Any
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse

app = FastAPI(
    title="EnTrus Cloud Core",
    description="Core API for EnTrus frequency data and simple Creator Station view.",
    version="1.0.0",
)

# ---------------------------------------------------------
# CORS (safe defaults, allows browser access if you call
# this API from other front-ends later)
# ---------------------------------------------------------
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # you can tighten this later
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------
# Frequency map (EnTrus frequency lines)
# ---------------------------------------------------------
FREQUENCY_MAP: Dict[int, Dict[str, Any]] = {
    285: {
        "hz": 285,
        "seal": "Seal of Form",
        "phrase": "Return to Origin",
        "colors": ["Earth Iron", "Deep Terra", "Pine Stone", "Smoke Gray"],
        "notes": "Restorer frequency line — repair, stability, physical renewal.",
    },
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
        "notes": "Drive band — connection, creativity, and energy exchange.",
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


# ---------------------------------------------------------
# Root route
# ---------------------------------------------------------
@app.get("/", response_class=JSONResponse)
async def root() -> Dict[str, Any]:
    """
    Simple root route so you know the API is alive.
    """
    return {
        "status": "online",
        "service": "entrus_cloud-core",
        "routes": [
            "/",
            "/frequency/{hz}",
            "/creator",
        ],
    }


# ---------------------------------------------------------
# Frequency lookup
# ---------------------------------------------------------
@app.get("/frequency/{hz}", response_class=JSONResponse)
async def get_frequency(hz: int) -> Dict[str, Any]:
    """
    Return information about an EnTrus frequency line.
    """
    if hz not in FREQUENCY_MAP:
        raise HTTPException(status_code=404, detail="Frequency not found")
    return FREQUENCY_MAP[hz]


# ---------------------------------------------------------
# Simple Creator Station view
# ---------------------------------------------------------
CREATOR_HTML = """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <title>EnTrus Creator Station — Cloud Core</title>
  <style>
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      background: radial-gradient(circle at top, #f6efe0 0, #0f1115 60%);
      color: #f7f5ef;
      min-height: 100vh;
      display: flex;
      align-items: stretch;
      justify-content: center;
    }
    .shell {
      width: 100%;
      max-width: 1100px;
      margin: 32px;
      padding: 24px;
      border-radius: 18px;
      background: rgba(10, 12, 18, 0.92);
      box-shadow: 0 18px 40px rgba(0,0,0,0.65);
      display: grid;
      grid-template-columns: 260px 1fr;
      gap: 20px;
    }
    .left {
      border-right: 1px solid rgba(255, 232, 184, 0.15);
      padding-right: 18px;
    }
    h1 {
      margin: 0 0 8px 0;
      font-size: 1.4rem;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      color: #ffe8a3;
    }
    h2 {
      margin-top: 18px;
      font-size: 0.9rem;
      letter-spacing: 0.16em;
      text-transform: uppercase;
      color: #c9ccb8;
    }
    .tagline {
      font-size: 0.85rem;
      color: #c3c5cf;
      margin-bottom: 18px;
    }
    .chip-row {
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-top: 10px;
    }
    .chip {
      border-radius: 999px;
      padding: 6px 12px;
      border: 1px solid rgba(255, 232, 184, 0.25);
      font-size: 0.8rem;
      cursor: pointer;
      background: rgba(20, 24, 32, 0.9);
      color: #f5f2e5;
      transition: background 0.15s ease, transform 0.1s ease, border-color 0.15s ease;
    }
    .chip:hover {
      transform: translateY(-1px);
      border-color: #ffe8a3;
    }
    .chip.active {
      background: linear-gradient(135deg, #f7d58a, #f2b86a);
      color: #20140a;
      border-color: transparent;
    }
    .right {
      display: flex;
      flex-direction: column;
      gap: 10px;
    }
    .panel-title {
      display: flex;
      justify-content: space-between;
      align-items: baseline;
      font-size: 0.9rem;
      color: #dadfe8;
    }
    .panel-title span {
      font-size: 0.75rem;
      opacity: 0.7;
    }
    pre {
      margin: 0;
      padding: 14px 16px;
      border-radius: 12px;
      background: #05070b;
      color: #f5f2e5;
      font-size: 0.8rem;
      max-height: 360px;
      overflow: auto;
      border: 1px solid rgba(255, 232, 184, 0.18);
    }
    .status {
      font-size: 0.8rem;
      color: #a1e8b5;
      margin-top: 6px;
      min-height: 18px;
    }
    a {
      color: #ffe8a3;
      text-decoration: none;
    }
    a:hover {
      text-decoration: underline;
    }
    @media (max-width: 800px) {
      .shell {
        grid-template-columns: 1fr;
      }
      .left {
        border-right: none;
        border-bottom: 1px solid rgba(255, 232, 184, 0.15);
        padding-bottom: 16px;
        margin-bottom: 10px;
      }
    }
  </style>
</head>
<body>
  <div class="shell">
    <div class="left">
      <h1>EnTrus Cloud Core</h1>
      <div class="tagline">
        Live frequency data API on <strong>entrusritualarts.com</strong><br/>
        Tap a seal to query <code>/frequency/&lt;hz&gt;</code>.
      </div>
      <h2>Frequency Lines</h2>
      <div class="chip-row">
        <button class="chip" data-hz="285">285 — Form</button>
        <button class="chip" data-hz="396">396 — Protector</button>
        <button class="chip" data-hz="528">528 — Flow</button>
        <button class="chip" data-hz="639">639 — Drive</button>
        <button class="chip" data-hz="741">741 — Expression</button>
        <button class="chip" data-hz="852">852 — Seer</button>
      </div>
      <h2 style="margin-top: 22px;">API Routes</h2>
      <div style="font-size: 0.8rem; color:#c9ccb8; line-height:1.5;">
        <code>GET /</code> → health & route list<br/>
        <code>GET /frequency/&lt;hz&gt;</code> → frequency data<br/>
        <code>GET /creator</code> → this panel
      </div>
    </div>
    <div class="right">
      <div class="panel-title">
        <strong>API Response Preview</strong>
        <span id="hz-label">No frequency selected</span>
      </div>
      <pre id="output">{ "hint": "Tap a frequency on the left to query the live API." }</pre>
      <div class="status" id="status"></div>
    </div>
  </div>

  <script>
    const chips = document.querySelectorAll(".chip");
    const output = document.getElementById("output");
    const status = document.getElementById("status");
    const hzLabel = document.getElementById("hz-label");

    function setActiveChip(hz) {
      chips.forEach(chip => {
        if (chip.dataset.hz === hz.toString()) {
          chip.classList.add("active");
        } else {
          chip.classList.remove("active");
        }
      });
    }

    async function loadFrequency(hz) {
      try {
        setActiveChip(hz);
        status.textContent = "Loading " + hz + " Hz…";
        hzLabel.textContent = hz + " Hz";

        const res = await fetch("/frequency/" + hz);
        if (!res.ok) {
          const err = await res.json().catch(() => ({}));
          throw new Error(err.detail || ("HTTP " + res.status));
        }
        const data = await res.json();
        output.textContent = JSON.stringify(data, null, 2);
        status.textContent = "OK • Live from /frequency/" + hz;
      } catch (err) {
        output.textContent = JSON.stringify({ error: err.message }, null, 2);
        status.textContent = "Error: " + err.message;
        hzLabel.textContent = "Error";
      }
    }

    chips.forEach(chip => {
      chip.addEventListener("click", () => {
        const hz = chip.dataset.hz;
        loadFrequency(hz);
      });
    });

    // Auto-load one frequency on first open
    loadFrequency("528");
  </script>
</body>
</html>
"""


@app.get("/creator", response_class=HTMLResponse)
async def creator_view() -> HTMLResponse:
    """
    Simple HTML view for the Creator Station panel.
    """
    return HTMLResponse(content=CREATOR_HTML) 
