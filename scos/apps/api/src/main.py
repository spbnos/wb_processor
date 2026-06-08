from fastapi import FastAPI

from src.api.v1.health import router as health_router
from src.core.settings import settings

app = FastAPI(
title=settings.APP_NAME,
version="0.1.0"
)

app.include_router(health_router)

@app.get("/")
async def root():
return {
"service": settings.APP_NAME,
"version": "0.1.0"
}
