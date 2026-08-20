import logging
from src.utils.config import Settings


def configure_logging(settings: Settings) -> None:
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    for logger_name in (
        "azure.core.pipeline.policies.http_logging_policy",
        "azure.identity",
        "httpx",
        "openai",
    ):
        logging.getLogger(logger_name).setLevel(logging.WARNING)
