from datetime import datetime
from typing import TypedDict

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.router import router
from app.api.market_data import router as market_data_router
from app.api.fundamentals import router as fundamentals_router
from app.api.portfolios import router as portfolios_router
from app.core.config import Settings, get_settings
from app.core.request_security import RequestSecurityMiddleware
from app.core.time import utc_now

class HealthResponse(TypedDict):
    status: str
    service: str
    timestamp: datetime


def create_app(settings: Settings) -> FastAPI:
    application = FastAPI(
        title=settings.app_name,
        version="0.1.0",
        description=(
            "Investment research and analytics for positions entered manually by the user. "
            "The service does not connect to brokers or execute trades."
        ),
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=list(settings.cors_origins),
        allow_credentials=False,
        allow_methods=["GET", "POST", "PATCH", "DELETE"],
        allow_headers=["*"],
    )
    # Starlette inserts the last added middleware outermost, before CORS preflight.
    application.add_middleware(RequestSecurityMiddleware, settings=settings)
    application.include_router(router, prefix=settings.api_prefix)
    application.include_router(portfolios_router, prefix=settings.api_prefix)
    application.include_router(market_data_router, prefix="/api")
    application.include_router(fundamentals_router, prefix="/api")

    @application.get("/health", tags=["system"])
    def health() -> HealthResponse:
        return {"status": "ok", "service": settings.app_name, "timestamp": utc_now()}

    return application


app = create_app(get_settings())
