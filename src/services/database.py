from contextlib import contextmanager
from typing import Iterator
from sqlalchemy import create_engine
from sqlalchemy.engine import Connection, Engine
from src.utils.config import Settings


class MetadataDatabase:
    def __init__(self, settings: Settings):
        self.engine: Engine = create_engine(settings.database_url, pool_pre_ping=True)

    @contextmanager
    def connect(self) -> Iterator[Connection]:
        with self.engine.begin() as connection:
            yield connection
