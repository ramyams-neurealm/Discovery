from functools import lru_cache
from fastapi import Depends
from src.services.database import MetadataDatabase
from src.services.key_vault_service import KeyVaultService
from src.utils.config import Settings, get_settings

@lru_cache
def build_database() -> MetadataDatabase:
    return MetadataDatabase(get_settings())

def get_database() -> MetadataDatabase:
    return build_database()

def get_key_vault(settings: Settings = Depends(get_settings)):
    service = KeyVaultService(settings)
    try:
        yield service
    finally:
        service.close()
