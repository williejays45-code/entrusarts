
from fastapi import FastAPI

app = FastAPI()

@app.get("/")
def home():
    return {
        "status": "online",
        "service": "entrus_cloud_core",
        "message": "EnTrus Cloud Core is live."
    } 
