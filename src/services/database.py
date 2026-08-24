from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.engine import Connection, Engine

from src.utils.config import Settings


class MetadataDatabase:
    """
    Manages connections to the PostgreSQL metadata store.

    Each call to connect() opens a transaction-managed SQLAlchemy
    connection. Successful operations are committed automatically.
    Exceptions cause the transaction to roll back automatically.
    """

    def __init__(
        self,
        settings: Settings,
    ) -> None:
        self.engine: Engine = create_engine(
            settings.database_url,
            pool_pre_ping=True,
        )

    @contextmanager
    def connect(
        self,
    ) -> Iterator[Connection]:
        """
        Provide a transaction-managed metadata-store connection.
mmits automatically when the context exits
        successfully and rolls back automatically when an exception
        occurs.
        """

        with self.engine.begin() as connection:
            yield connection

    def dispose(self) -> None:
        """
        Close all pooled database connections owned by this engine.

        This is called after a background Discovery run completes.
        """

        self.engine.dispose()