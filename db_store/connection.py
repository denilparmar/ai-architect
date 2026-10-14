import os
from urllib.parse import quote

from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from config import config


def create_connection_pool(max_pool_size: int = 10) -> ConnectionPool:
    """Create the shared PostgreSQL pool used by the application."""
    memory_config = config["memory"]
    db_user = os.getenv("DB_USER", "postgres")
    db_password = os.getenv("DB_PASSWORD", "postgres")
    db_uri = (
        f"postgresql://{quote(db_user, safe='')}:{quote(db_password, safe='')}"
        f"@{memory_config['host']}:{memory_config['port']}"
        f"/{quote(memory_config['database'], safe='')}"
    )

    return ConnectionPool(
        conninfo=db_uri,
        max_size=max_pool_size,
        open=True,
        kwargs={
            "autocommit": True,
            "prepare_threshold": 0,
            "row_factory": dict_row,
        },
    )
