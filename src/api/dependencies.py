from functools import lru_cache
from fastapi import Depends
from src.services.database import MetadataDatabase
from src.services.key_vault_service import KeyVaultService
from src.utils.config import Settings, get_settings


def get_database(settings: Settings = Depends(get_settings)) -> MetadataDatabase:
    return MetadataDatabase(settings)


def get_key_vault(settings: Settings = Depends(get_settings)) -> KeyVaultService:
    return KeyVaultService(settings)
