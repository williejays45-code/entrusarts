
# ==== EnTrus Cloud Core — hard reset main.py (ONE SHOT) ====
$ErrorActionPreference = "Stop"

$projectRoot = Get-Location
$srcDir      = Join-Path $projectRoot "src"
$mainPath    = Join-Path $srcDir "main.py"

if (!(Test-Path $srcDir)) {
    throw "src folder not found at $srcDir. Run this in the repo root (same place as requirements.txt)."
}

# Full replacement of main.py
@'
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="EnTrus Cloud Core")

# CORS wired directly here – no external utils needed
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/")
async def root():
    return {
        "status": "online",
        "service": "entrus_cloud_core",
        "message": "EnTrus Cloud Core is live."
    }
'@ | Set-Content -Encoding UTF8 $mainPath

Write-Host "main.py reset for EnTrus Cloud Core." -ForegroundColor Green 
