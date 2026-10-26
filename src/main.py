import traceback
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from src.api.routes import router as core_router
from src.api.regulatory_compliance_routes import router as compliance_router
from src.utils.config import get_settings
from src.utils.logging import configure_logging

settings = get_settings()
configure_logging(settings)

app = FastAPI(
    title=settings.app_name,
    description="Agentic Data Compliance Platform API"
)

# Enable CORS for Swagger UI
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Catch ALL internal 500 errors and return full error details in JSON
@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={
            "error_type": type(exc).__name__,
            "error_message": str(exc),
            "traceback": traceback.format_exc().splitlines()[-5:]  # Last 5 lines of stack trace
        },
    )

prefix = getattr(settings, "api_prefix", "/api/v1") or "/api/v1"

app.include_router(core_router, prefix=prefix)
app.include_router(compliance_router, prefix=prefix)