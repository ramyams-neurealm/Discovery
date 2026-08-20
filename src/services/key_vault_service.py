import logging
from azure.identity import ClientSecretCredential
from azure.keyvault.secrets import SecretClient
from src.utils.config import Settings

logger = logging.getLogger(__name__)


class KeyVaultService:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._credential = ClientSecretCredential(
            tenant_id=settings.azure_tenant_id,
            client_id=settings.azure_client_id,
            client_secret=settings.azure_client_secret.get_secret_value(),
        )
        self._client = SecretClient(
            vault_url=settings.azure_keyvault_url,
            credential=self._credential,
        )

    def get_openai_api_key(self) -> str:
        # No application-level API-key cache. Each LLM need triggers get_secret().
        secret = self._client.get_secret(self.settings.azure_keyvault_secret_name)
        if not secret.value:
            raise RuntimeError("OpenAI credential retrieved from Key Vault is empty")
        logger.info("OpenAI credential retrieved from Azure Key Vault")
        return secret.value

    def get_source_password(self, secret_name: str) -> str:
        secret = self._client.get_secret(secret_name)
        if not secret.value:
            raise RuntimeError("Source database credential is empty")
        return secret.value

    def close(self) -> None:
        self._client.close()
        self._credential.close()
