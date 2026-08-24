from src.services.key_vault_service import KeyVaultService
from src.utils.config import Settings


class BaseAgent:
    agent_name = "base_agent"
    agent_version = "v1"

    def __init__(self, settings: Settings, key_vault: KeyVaultService):
        self.settings = settings
        self.key_vault = key_vault
