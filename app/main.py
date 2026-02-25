"""
FastAPI application factory with New Relic APM, CORS, lifespan, and all routers.
"""
import logging
import os

# New Relic must be initialized BEFORE any other imports that it instruments.
if os.getenv("NEW_RELIC_LICENSE_KEY"):
    import newrelic.agent
    newrelic.agent.initialize("newrelic.ini")

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import get_settings
from app.redis_client import get_redis, close_redis
from app.routers import rides, drivers, trips, payments

settings = get_settings()
logger = logging.getLogger(__name__)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Starting %s [%s]", settings.app_name, settings.env)
    await get_redis()          # warm up connection pool
    yield
    await close_redis()
    logger.info("Shutdown complete")


app = FastAPI(
    title=settings.app_name,
    version="1.0.0",
    description="Multi-tenant ride-hailing platform — GoComet SDE-2 Assignment",
    lifespan=lifespan,
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Global error handler
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    logger.error("Unhandled error on %s: %s", request.url, exc, exc_info=True)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error"},
    )


# Health check (no auth)
@app.get("/health", tags=["Health"])
async def health():
    return {"status": "ok"}


# Register routers
app.include_router(rides.router)
app.include_router(drivers.router)
app.include_router(trips.router)
app.include_router(payments.router)
