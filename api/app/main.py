from fastapi import FastAPI

app = FastAPI(title="FuelNow API")


@app.get("/health")
async def health():
    return {"status": "ok"}
