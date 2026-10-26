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
            connect_args={
                # Increased timeout to 60000ms (60 seconds) so batch inserts do not get aborted[cite: 8]
                "options": "-c statement_timeout=60000ms",
                "keepalives": 1,
                "keepalives_idle": 30,
                "keepalives_interval": 10,
                "keepalives_count": 5,
            },
            pool_pre_ping=True,
            pool_recycle=300,  # Recycle stale idle connections every 5 minutes
        )

    @contextmanager
    def connect(
        self,
    ) -> Iterator[Connection]:
        """
        Provide a transaction-managed metadata-store connection.

        Commits automatically when the context exits successfully and
        rolls back automatically when an exception occurs.
        """

        with self.engine.begin() as connection:
            yield connection

    def dispose(self) -> None:
        """
        Close all pooled database connections owned by this engine.

        This is called after a background Discovery run completes.
        """

        self.engine.dispose()