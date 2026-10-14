import contextlib
import time

import structlog
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from starlette.responses import JSONResponse

from app.config import settings
from app.limiter import limiter
from app.mcp_server import mcp
from app.routes import be, fuels, health, stations
from mcp.server.transport_security import TransportSecuritySettings

structlog.configure(
    processors=[
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.add_log_level,
        structlog.processors.JSONRenderer(),
    ],
)
logger = structlog.get_logger("api")

# Build the MCP streamable HTTP app — must be called before accessing mcp.session_manager
# DNS rebinding protection disabled: nginx is the front-facing server and validates Host headers
mcp_app = mcp.streamable_http_app(
    transport_security=TransportSecuritySettings(enable_dns_rebinding_protection=False),
)


@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    async with mcp.session_manager.run():
        yield


app = FastAPI(title="FuelNow API", lifespan=lifespan)

app.state.limiter = limiter
app.add_middleware(SlowAPIMiddleware)


@app.middleware("http")
async def request_logging_middleware(request: Request, call_next):
    start = time.perf_counter()
    response = await call_next(request)
    duration_ms = round((time.perf_counter() - start) * 1000, 2)
    logger.info(
        "request",
        method=request.method,
        path=request.url.path,
        status_code=response.status_code,
        duration_ms=duration_ms,
    )
    return response


@app.exception_handler(RateLimitExceeded)
async def rate_limit_handler(request: Request, exc: RateLimitExceeded) -> JSONResponse:
    return JSONResponse(status_code=429, content={"detail": "Too many requests, please retry later."})


# CORS — always enabled for public MCP access (POST/DELETE needed for Streamable HTTP)
if settings.cors_allow_origins:
    origins = [o.strip() for o in settings.cors_allow_origins.split(",") if o.strip()]
else:
    origins = ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)

# API routes
app.include_router(health.router)
app.include_router(fuels.router)
app.include_router(stations.router)
app.include_router(be.router)


# Well-known MCP server discovery manifest (before Mount("/", ...) catch-all)
@app.get("/.well-known/mcp-server")
async def mcp_well_known() -> dict:
    return {
        "endpoint": "/mcp",
        "transport": "streamable-http",
        "protocolVersion": "2025-11-25",
        "serverInfo": {
            "name": "FuelNow",
            "version": "1.0.0",
            "description": "Find the cheapest fuel stations near a location in France and Belgium",
        },
        "capabilities": {"tools": {}},
    }


# MCP server — Streamable HTTP transport (mounted at root, internal route at /mcp)
app.mount("/", mcp_app)
