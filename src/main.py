from fastapi import FastAPI
from src.api.routes import router
from src.utils.config import get_settings
from src.utils.logging import configure_logging

settings = get_settings()
configure_logging(settings)

app = FastAPI(title=settings.app_name)
app.include_router(router, prefix=settings.api_prefix)
