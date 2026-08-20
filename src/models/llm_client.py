from langchain_openai import ChatOpenAI
from src.services.key_vault_service import KeyVaultService
from src.utils.config import Settings


def build_llm(settings: Settings, key_vault: KeyVaultService) -> ChatOpenAI:
    # Intentionally retrieve the current key for every LLM client creation.
    # The OpenAI key is not stored in Settings or application configuration.
    api_key = key_vault.get_openai_api_key()
    return ChatOpenAI(
        model=settings.llm_model,
        api_key=api_key,
        temperature=settings.llm_temperature,
        max_retries=settings.llm_max_retries,
    )
