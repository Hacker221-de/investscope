from datetime import datetime
from typing import TypedDict

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import router
from app.api.market_data import router as market_data_router
from app.api.fundamentals import router as fundamentals_router
from app.core.config import get_settings
from app.core.time import utc_now

settings = get_settings()

app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description=(
        "Investment research and analytics for positions entered manually by the user. "
        "The service does not connect to brokers or execute trades."
    ),
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)
app.include_router(router, prefix=settings.api_prefix)
app.include_router(market_data_router, prefix="/api")
app.include_router(fundamentals_router, prefix="/api")


class HealthResponse(TypedDict):
    status: str
    service: str
    timestamp: datetime


@app.get("/health", tags=["system"])
def health() -> HealthResponse:
    return {"status": "ok", "service": settings.app_name, "timestamp": utc_now()}
