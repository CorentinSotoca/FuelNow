from fastapi import FastAPI

from app.routes import fuels, health, stations

app = FastAPI(title="FuelNow API")

app.include_router(health.router)
app.include_router(fuels.router)
app.include_router(stations.router)
